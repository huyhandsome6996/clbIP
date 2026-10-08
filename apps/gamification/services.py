"""
Service Layer — apps.gamification
=================================
100% business logic XP / Huy hiệu / Bảng vàng nằm ở đây (Clean Layered).

Điểm cốt lõi về bảo mật (Security Hardening §5.2 — Server-Authoritative XP):
    - Client TUYỆT ĐỐI KHÔNG được gửi `xp` lên server. XP chỉ sinh từ các
      strategy phía server dựa trên sự kiện đã xác minh.
    - **Idempotency Key**: mỗi lần thưởng có khóa riêng; gọi lặp → trả kết quả
      cũ, KHÔNG cộng thêm (chống spam request cộng điểm).
    - **Daily XP Cap**: mỗi thành viên nhận tối đa `DAILY_XP_CAP` (300 XP)/ngày
      (tính trên tổng ledger dương trong ngày — timezone địa phương).
    - Chống race condition: khóa bi hồ sơ thành viên bằng
      `IGamificationRepository.lock_member_profile()` (select_for_update)
      trong `transaction.atomic()` (Security Hardening §5.3).

OOP (SKILL.md):
    - **Strategy Pattern**: `IRewardStrategy` + các chiến lược tính XP cụ thể,
      khởi tạo qua `RewardStrategyFactory` (OCP — thêm nguồn thưởng mới không
      phải sửa `GamificationService`).
    - **Repository Pattern (DIP)**: 100% truy vấn CSDL nằm ở
      `apps.gamification.repositories.DjangoGamificationRepository`; Service chỉ
      phụ thuộc trừu tượng `IGamificationRepository` qua DI
      `_repository_class` + `_repo()` (mẫu của apps.funds).
    - **DSA 2**: Leaderboard dùng `core.algorithms.leaderboard_heap.LeaderboardEngine`
      (Min-Heap O(N log K) + hash map tra cứu rank O(1)).
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, ClassVar, Final, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import ValidationException
from apps.common.timeutils import local_day_range, local_day_start
from apps.gamification.models import Badge, XpLedger
from apps.gamification.repositories import (
    DjangoGamificationRepository,
    IGamificationRepository,
)
from apps.gamification.serializers import BadgeSerializer
from apps.members.models import MemberProfile
from core.algorithms.leaderboard_heap import LeaderboardEngine

# ----------------------------------------------------------------------
# Hệ thống cấp độ (Level 1 → 10): ngưỡng XP tối thiểu của từng cấp
# ----------------------------------------------------------------------
LEVEL_THRESHOLDS: Final[list[int]] = [0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000]


def level_from_xp(xp: int) -> int:
    """
    Quy đổi XP → cấp độ (1..10) theo LEVEL_THRESHOLDS.

    Biên: xp=99 → 1; xp=100 → 2; xp=5000 → 10; xp=6000 → 10 (trần cấp 10).
    """
    level: int = 1
    for idx, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
        if xp >= threshold:
            level = idx
    return level


def level_progress_for_xp(xp: int) -> dict:
    """
    Tiến độ Level CHUẨN theo backend (M10 — audit luồng thành viên 1114efd).

    Nguồn sự thật DUY NHẤT cho frontend khi vẽ ring/bar "còn X XP nữa lên
    Level N" — profile.html cũ tự chế `xp % 200` nên tính sai mọi mốc không đều.

    Returns:
        {"current_level": int, "current_level_xp": int, "next_level_xp": int|None,
         "xp_into_level": int, "xp_to_next": int|None, "progress_percent": int 0..100,
         "max_level": bool}

        - max_level=True (Level 10, xp ≥ 5000): next_level_xp/xp_to_next = None,
          progress_percent = 100 — UI KHÔNG được gợi "Level 11".
        - progress_percent luôn clamp [0, 100] chống XP âm/đầu vào lạ.
    """
    xp = max(0, int(xp))
    level = level_from_xp(xp)
    current_level_xp = LEVEL_THRESHOLDS[level - 1]
    is_max = level >= len(LEVEL_THRESHOLDS)
    if is_max:
        return {
            "current_level": level,
            "current_level_xp": current_level_xp,
            "next_level_xp": None,
            "xp_into_level": xp - current_level_xp,
            "xp_to_next": None,
            "progress_percent": 100,
            "max_level": True,
        }
    next_level_xp = LEVEL_THRESHOLDS[level]
    span = next_level_xp - current_level_xp
    into = xp - current_level_xp
    percent = int(round((into / span) * 100)) if span > 0 else 100
    return {
        "current_level": level,
        "current_level_xp": current_level_xp,
        "next_level_xp": next_level_xp,
        "xp_into_level": into,
        "xp_to_next": max(0, next_level_xp - xp),
        "progress_percent": max(0, min(100, percent)),
        "max_level": False,
    }


# ----------------------------------------------------------------------
# STRATEGY PATTERN — các chiến lược tính XP thưởng
# ----------------------------------------------------------------------
class IRewardStrategy(ABC):
    """Hợp đồng chiến lược tính XP — context chứa dữ liệu sự kiện đã xác minh."""

    @abstractmethod
    def calculate_xp(self, context: dict) -> int:
        """Trả về số XP sẽ thưởng dựa trên `context` (server-side only)."""


class EarlyAttendanceStrategy(IRewardStrategy):
    """
    Điểm danh đúng giờ / sớm: base = XP_ATTENDANCE (50).
        - Sớm ≥ 15 phút: +20 XP (XP_ATTENDANCE_EARLY_BONUS).
        - Sớm trong khoảng (0, 15) phút: +10 XP.
    """

    EARLY_BONUS_SMALL: Final[int] = 10  # thưởng nhỏ khi sớm ít hơn 15 phút

    def calculate_xp(self, context: dict) -> int:
        clb = settings.CLB_SETTINGS
        base: int = clb["XP_ATTENDANCE"]
        minutes_early: int = int(context.get("minutes_early", 0) or 0)
        if minutes_early >= 15:
            return base + clb["XP_ATTENDANCE_EARLY_BONUS"]
        if minutes_early > 0:
            return base + self.EARLY_BONUS_SMALL
        return base


class LateAttendanceStrategy(IRewardStrategy):
    """Điểm danh muộn: chỉ nhận XP_ATTENDANCE_LATE (25)."""

    def calculate_xp(self, context: dict) -> int:
        return settings.CLB_SETTINGS["XP_ATTENDANCE_LATE"]


class DocumentContributionStrategy(IRewardStrategy):
    """Chia sẻ tài liệu cho kho chung: XP_DOCUMENT_SHARE (100)."""

    def calculate_xp(self, context: dict) -> int:
        return settings.CLB_SETTINGS["XP_DOCUMENT_SHARE"]


class TaskCompletionStrategy(IRewardStrategy):
    """Hoàn thành task trong DAG chuẩn bị sự kiện: XP_TASK_COMPLETION (30)."""

    def calculate_xp(self, context: dict) -> int:
        return settings.CLB_SETTINGS["XP_TASK_COMPLETION"]


class EventOrganizerStrategy(IRewardStrategy):
    """
    Tham gia tổ chức sự kiện:
        - role = 'ORGANIZER' → XP_EVENT_ORGANIZER (150).
        - role = 'PARTICIPANT' (mặc định) → 50.
    """

    PARTICIPANT_XP: Final[int] = 50

    def calculate_xp(self, context: dict) -> int:
        role = context.get("role", "PARTICIPANT")
        if role == "ORGANIZER":
            return settings.CLB_SETTINGS["XP_EVENT_ORGANIZER"]
        return self.PARTICIPANT_XP


class RewardStrategyFactory:
    """Factory ánh xạ `source` → chiến lược tính XP (OCP: chỉ thêm registry)."""

    _registry: ClassVar[dict[str, IRewardStrategy]] = {
        "ATTENDANCE": EarlyAttendanceStrategy(),
        "ATTENDANCE_LATE": LateAttendanceStrategy(),
        "DOCUMENT_SHARE": DocumentContributionStrategy(),
        "TASK_COMPLETION": TaskCompletionStrategy(),
        "EVENT_ORGANIZER": EventOrganizerStrategy(),
    }

    @classmethod
    def get(cls, source: str) -> IRewardStrategy:
        """
        Lấy strategy theo nguồn thưởng.

        Raises:
            ValidationException: nếu `source` chưa đăng ký (400).
        """
        strategy = cls._registry.get(source)
        if strategy is None:
            raise ValidationException(f"Nguồn thưởng XP không hợp lệ: {source!r}.")
        return strategy


# ----------------------------------------------------------------------
# BADGE SERVICE — tự động mở huy hiệu
# ----------------------------------------------------------------------
class BadgeService:
    """
    Engine mở huy hiệu tự động — điều kiện kiểm tra theo hồ sơ/ledger hiện tại.
    Hoàn toàn idempotent: badge đã mở thì bỏ qua, không nhân đôi (unique constraint).
    Truy vấn CSDL đi qua `IGamificationRepository` (DI `_repository_class`).
    """

    _repository_class: ClassVar[type[IGamificationRepository]] = (
        DjangoGamificationRepository
    )

    @classmethod
    def _repo(cls) -> IGamificationRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # Catalog mặc định — badge chưa có trong DB sẽ được get_or_create (idempotent)
    CATALOG: ClassVar[dict[str, dict[str, str]]] = {
        "STREAK_7": {
            "ten_badge": "Chuỗi 7 ngày 🔥",
            "mo_ta": "Điểm danh chuyên cần 7 ngày liên tiếp.",
            "icon": "🔥",
        },
        "ATTENDANCE_10": {
            "ten_badge": "Chăm chỉ 10 buổi",
            "mo_ta": "Có mặt (hoặc đi muộn) đủ 10 buổi sinh hoạt.",
            "icon": "📅",
        },
        "DOC_CONTRIBUTOR_3": {
            "ten_badge": "Nhà hảo tâm tri thức",
            "mo_ta": "Chia sẻ 3 tài liệu cho kho tài liệu chung của CLB.",
            "icon": "📚",
        },
        "LEVEL_5": {
            "ten_badge": "Cao thủ cấp 5",
            "mo_ta": "Đạt cấp độ 5 trên hệ thống XP.",
            "icon": "⭐",
        },
    }

    @classmethod
    def _ensure_badge(cls, ma_badge: str) -> Badge:
        """Lấy hoặc tạo badge trong DB theo catalog mặc định (idempotent)."""
        meta = cls.CATALOG[ma_badge]
        badge, _created = cls._repo().get_or_create_badge(
            ma_badge=ma_badge,
            defaults={
                "ten_badge": meta["ten_badge"],
                "mo_ta": meta["mo_ta"],
                "icon": meta["icon"],
            },
        )
        return badge

    @classmethod
    def evaluate_and_unlock(cls, member: MemberProfile) -> list[str]:
        """
        Đánh giá mọi điều kiện và mở các badge đủ điều kiện.

        Returns:
            Danh sách TÊN badge vừa mở lần này (đã mở trước đó thì không lặp).
        """
        newly_unlocked: list[str] = []

        conditions: dict[str, bool] = {
            "STREAK_7": member.streak_count >= 7,
            # Cross-app query (attendance) — đặt trong repository, không sửa apps.attendance
            "ATTENDANCE_10": cls._repo().count_attended_records(member) >= 10,
            "DOC_CONTRIBUTOR_3": cls._repo().count_ledger_entries(
                member, source=XpLedger.Source.DOCUMENT_SHARE
            )
            >= 3,
            "LEVEL_5": member.current_level >= 5,
        }

        for ma_badge, passed in conditions.items():
            if not passed:
                continue
            if cls._repo().member_has_badge(member, ma_badge):
                continue  # đã mở → bỏ qua (không nhân đôi)
            badge = cls._ensure_badge(ma_badge)
            _mb, created = cls._repo().get_or_create_member_badge(member, badge)
            if created:
                newly_unlocked.append(badge.ten_badge)

        return newly_unlocked

    @classmethod
    def list_badges_with_status(cls, profile: Optional[MemberProfile]) -> dict:
        """
        Danh mục badge toàn hệ thống + flag `unlocked` của user (dời từ
        BadgeListView.get — View chỉ còn gọi Service và bọc envelope).

        Args:
            profile: hồ sơ của user hiện tại (có thể None → mọi badge khóa).

        Returns:
            {"items": [badge serializer data + unlocked], "unlocked": [ma_badge]}
        """
        unlocked_ids: set[int] = set()
        if profile is not None:
            # Một query duy nhất cho MemberBadge của user
            unlocked_ids = cls._repo().get_unlocked_badge_ids(profile)

        items: list[dict] = []
        unlocked: list[str] = []
        for badge in cls._repo().list_all_badges():
            is_unlocked = badge.pk in unlocked_ids
            item = BadgeSerializer(badge).data
            item["unlocked"] = is_unlocked
            items.append(item)
            if is_unlocked:
                unlocked.append(badge.ma_badge)

        return {"items": items, "unlocked": unlocked}


# ----------------------------------------------------------------------
# GAMIFICATION SERVICE — award XP + nhiệm vụ tuần
# ----------------------------------------------------------------------
class GamificationService:
    """Nghiệp vụ cộng XP (Server-Authoritative) và widget nhiệm vụ tuần."""

    _repository_class: ClassVar[type[IGamificationRepository]] = (
        DjangoGamificationRepository
    )

    @classmethod
    def _repo(cls) -> IGamificationRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # Ánh xạ source nghiệp vụ → giá trị hợp lệ của XpLedger.Source
    _LEDGER_SOURCE_MAP: ClassVar[dict[str, str]] = {
        "ATTENDANCE": XpLedger.Source.ATTENDANCE,
        "ATTENDANCE_LATE": XpLedger.Source.ATTENDANCE,
        "DOCUMENT_SHARE": XpLedger.Source.DOCUMENT_SHARE,
        "TASK_COMPLETION": XpLedger.Source.TASK_COMPLETION,
        "EVENT_ORGANIZER": XpLedger.Source.EVENT_ORGANIZER,
    }

    @classmethod
    def award_xp(
        cls,
        member: MemberProfile,
        amount: int,
        reason: str,
        source: str,
        idempotency_key: Optional[str] = None,
        strategy: Optional[IRewardStrategy] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """
        Cộng (hoặc phạt) XP cho thành viên — an toàn & công bằng.

        Quy trình (trong 1 DB transaction, khóa bi hồ sơ):
            1. Nếu có `strategy` → amount = strategy.calculate_xp(context)
               (client không được quyết định XP — Server-Authoritative).
            2. Idempotency: trùng `idempotency_key` → trả kết quả cũ, không cộng.
            3. Daily cap: tổng XP dương hôm nay ≥ DAILY_XP_CAP (300) → KHÔNG cộng,
               KHÔNG raise (để luồng điểm danh vẫn thành công).
            4. amount > 0 vượt phần dư cap → chỉ cộng phần còn được phép.
               amount < 0 (phạt) → cộng nguyên phần phạt.
            5. Ghi XpLedger + cập nhật xp_points / current_level.
            6. BadgeService.evaluate_and_unlock — CHÍNH XÁC 1 LẦN mỗi lượt GHI XP,
               luôn SAU khi cập nhật XP (QA-Audit nhóm 3: bản cũ gọi 2 lần trong
               luồng thành công → doubled query + badge stale). Luồng idempotent-
               replay trả new_badges=[] và không đánh giá badge.

        Returns:
            {"awarded": bool, "xp_gained": int, "member_xp": int,
             "member_level": int, "new_badges": list[str], "message": str}
        """
        # Bước 1 — XP luôn do server tính qua strategy
        if strategy is not None:
            amount = strategy.calculate_xp(context or {})

        ledger_source: str = cls._LEDGER_SOURCE_MAP.get(source, XpLedger.Source.BONUS)

        with transaction.atomic():
            # Bước 0 — khóa bi hồ sơ để chống cộng song song (race condition)
            member = cls._repo().lock_member_profile(member.pk)

            # Bước 2 — Idempotency chống cộng lặp
            if idempotency_key and cls._repo().exists_idempotency_key(idempotency_key):
                return {
                    "awarded": False,
                    "xp_gained": 0,
                    "member_xp": member.xp_points,
                    "member_level": member.current_level,
                    "new_badges": [],
                    "message": "Đã thưởng trước đó",
                }

            # Bước 3+4 — Daily cap 300 XP/ngày
            # (evaluate badge chạy ĐÚNG 1 LẦN tại mỗi điểm return — không gọi
            # trước ở đầu luồng như bản cũ gây double-evaluate trong luồng thành công)
            if amount == 0:
                return {
                    "awarded": False,
                    "xp_gained": 0,
                    "member_xp": member.xp_points,
                    "member_level": member.current_level,
                    "new_badges": BadgeService.evaluate_and_unlock(member),
                    "message": "Không có thay đổi XP.",
                }

            if amount > 0:
                cap: int = settings.CLB_SETTINGS["DAILY_XP_CAP"]
                used_today: int = cls._xp_used_today(member)
                remaining: int = cap - used_today
                if remaining <= 0:
                    return {
                        "awarded": False,
                        "xp_gained": 0,
                        "member_xp": member.xp_points,
                        "member_level": member.current_level,
                        "new_badges": BadgeService.evaluate_and_unlock(member),
                        "message": "Đã đạt trần XP ngày",
                    }
                actual_amount: int = min(amount, remaining)
            else:
                # Phạt (amount < 0) luôn áp dụng nguyên vẹn
                actual_amount = amount

            # Bước 5 — ghi sổ + cập nhật hồ sơ
            cls._repo().create_ledger_entry(
                member=member,
                amount=actual_amount,
                reason=reason,
                source=ledger_source,
                idempotency_key=idempotency_key,
            )
            # M09 (audit 1114efd): service KHÔNG gọi member.save() trực tiếp —
            # mọi ghi CSDL đi qua repository (`persist_member_gamification`),
            # giữ nguyên update_fields hẹp + khóa bi đã lấy ở Bước 0.
            cls._repo().persist_member_gamification(
                member,
                xp_points=member.xp_points + actual_amount,
                current_level=level_from_xp(member.xp_points + actual_amount),
            )

            new_badges = BadgeService.evaluate_and_unlock(member)

            return {
                "awarded": True,
                "xp_gained": actual_amount,
                "member_xp": member.xp_points,
                "member_level": member.current_level,
                "new_badges": new_badges,
                "message": f"Đã cộng {actual_amount} XP",
            }

    @classmethod
    def _xp_used_today(cls, member: MemberProfile) -> int:
        """Tổng XP dương đã nhận hôm nay (múi giờ địa phương) từ XpLedger.

        Aggregate (Coalesce/Sum) nằm trong repository (`sum_positive_xp_between`).
        Dùng range datetime thay vì `__date` — di động đa CSDL (xem
        apps/common/timeutils.py: MySQL không cần bảng timezone).
        """
        day_start, day_end = local_day_range(timezone.localdate())
        return cls._repo().sum_positive_xp_between(member, day_start, day_end)

    @classmethod
    def get_weekly_quests(cls, member: MemberProfile) -> dict:
        """
        Widget 'Nhiệm vụ tuần kiếm XP': XP + tiến độ từ đầu tuần (thứ 2) đến nay.

        Returns:
            {"week_start": 'YYYY-MM-DD', "xp_this_week": int,
             "attendance_count": int, "document_shared": int, "task_completed": int}
        """
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        week_start: datetime = local_day_start(monday)

        repo = cls._repo()
        xp_this_week: int = repo.sum_xp_since(member, week_start)
        attendance_count: int = repo.count_attended_records_since(member, week_start)
        document_shared: int = repo.count_ledger_entries(
            member, source=XpLedger.Source.DOCUMENT_SHARE, since_dt=week_start
        )
        task_completed: int = repo.count_ledger_entries(
            member, source=XpLedger.Source.TASK_COMPLETION, since_dt=week_start
        )

        return {
            "week_start": monday.isoformat(),
            "xp_this_week": xp_this_week,
            "attendance_count": attendance_count,
            "document_shared": document_shared,
            "task_completed": task_completed,
        }


# ----------------------------------------------------------------------
# LEADERBOARD SERVICE — Bảng vàng Min-Heap (DSA 2)
# ----------------------------------------------------------------------
class LeaderboardService:
    """Bảng xếp hạng XP dùng `LeaderboardEngine` (Min-Heap O(N log K))."""

    TOP_K: Final[int] = 10

    _repository_class: ClassVar[type[IGamificationRepository]] = (
        DjangoGamificationRepository
    )

    @classmethod
    def _repo(cls) -> IGamificationRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # Cache ngắn hạn cho Top 10 (QA-Audit nhóm 5): bộ chia sẻ sử dụng cache
    # dùng chung (DatabaseCache/Redis) — các worker gunicorn nhìn thấy cùng
    # bảng vàng, tránh tính lại heap O(N log K) mỗi request.
    CACHE_KEY: Final[str] = "clbip:leaderboard:top10"
    CACHE_TTL_SECONDS: Final[int] = 45

    @classmethod
    def get_leaderboard(cls, member_profile: Optional[MemberProfile] = None) -> dict:
        """
        Lấy Top 10 + vị trí cá nhân (nếu truyền `member_profile`).

        Hiệu năng (QA-Audit nhóm 5):
            - Top 10: Min-Heap O(N log K) trên iterator `values_list` nhẹ
              (không order_by toàn bảng, không dựng model instance).
            - Rank cá nhân: 1 câu SQL Count thay vì quét O(N) Python.
            - Top 10 + tổng số được cache 45s (cache dùng chung giữa worker).

        Định dạng trả về GIỮ NGUYÊN: {"top_10", "my_position", "total_members"}.
        """
        from django.core.cache import cache  # noqa: PLC0415

        repo = cls._repo()

        cached = cache.get(cls.CACHE_KEY)
        if cached is None:
            engine = LeaderboardEngine(top_k=cls.TOP_K)
            members_iter = (
                {"id": row[0], "xp": row[1], "name": row[2] or "", "avatar": row[3] or ""}
                for row in repo.iter_leaderboard_rows()
            )
            top_10 = engine.compute_top_k(members_iter)
            total_members = repo.count_active_profiles()
            cached = {"top_10": top_10, "total_members": total_members}
            cache.set(cls.CACHE_KEY, cached, cls.CACHE_TTL_SECONDS)

        top_10: list[dict[str, Any]] = cached["top_10"]
        total_members: int = cached["total_members"]

        my_position: Optional[dict] = None
        if member_profile is not None:
            my_position = cls._compute_my_position(repo, member_profile, top_10, total_members)

        return {
            "top_10": top_10,
            "my_position": my_position,
            "total_members": total_members,
        }

    @staticmethod
    def _compute_my_position(repo, member_profile: MemberProfile, top_10: list, total_members: int) -> dict:
        """
        Vị trí cá nhân — semantics GIỐNG HỆT LeaderboardEngine.find_my_position cũ:
            rank = 1 + số thành viên ACTIVE có XP cao hơn (Count bằng SQL);
            in_top_k = id nằm trong top_10;
            xp_gap_to_top_k = max(xp ngưỡng top K − xp mình + 1, 0) khi ngoài top.
        """
        from apps.members.models import MemberProfile as _MP  # noqa: PLC0415

        threshold_xp: int = top_10[-1]["xp"] if top_10 else 0
        in_top = any(entry["id"] == member_profile.pk for entry in top_10)

        # Thành viên không ACTIVE không nằm trong danh sách xét hạng —
        # rank = số thành viên ACTIVE hiện tại (khớp hành vi cũ: total của
        # danh sách active lúc gọi), gap = 0
        if getattr(member_profile, "trang_thai_hd", "") != _MP.TrangThai.ACTIVE:
            return {
                "in_top_k": False,
                "rank": repo.count_active_profiles(),
                "xp_gap_to_top_k": 0,
            }

        higher = repo.count_active_profiles_with_xp_greater_than(member_profile.xp_points)
        rank = higher + 1
        gap = max(threshold_xp - member_profile.xp_points + 1, 0) if not in_top else 0
        return {"in_top_k": in_top, "rank": rank, "xp_gap_to_top_k": gap}
