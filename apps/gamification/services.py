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
      `MemberProfile.objects.select_for_update()` trong `transaction.atomic()`
      (Security Hardening §5.3).

OOP (SKILL.md):
    - **Strategy Pattern**: `IRewardStrategy` + các chiến lược tính XP cụ thể,
      khởi tạo qua `RewardStrategyFactory` (OCP — thêm nguồn thưởng mới không
      phải sửa `GamificationService`).
    - **DSA 2**: Leaderboard dùng `core.algorithms.leaderboard_heap.LeaderboardEngine`
      (Min-Heap O(N log K) + hash map tra cứu rank O(1)).
"""
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Any, ClassVar, Final, Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.common.exceptions import ValidationException
from apps.gamification.models import Badge, MemberBadge, XpLedger
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
    """

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
        badge, _created = Badge.objects.get_or_create(
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
            "ATTENDANCE_10": AttendanceRecord.objects.filter(
                member=member,
                trang_thai__in=[
                    AttendanceRecord.TrangThaiDiemDanh.CO_MAT,
                    AttendanceRecord.TrangThaiDiemDanh.DI_MUON,
                ],
            ).count() >= 10,
            "DOC_CONTRIBUTOR_3": XpLedger.objects.filter(
                member=member,
                source=XpLedger.Source.DOCUMENT_SHARE,
            ).count() >= 3,
            "LEVEL_5": member.current_level >= 5,
        }

        for ma_badge, passed in conditions.items():
            if not passed:
                continue
            if MemberBadge.objects.filter(member=member, badge__ma_badge=ma_badge).exists():
                continue  # đã mở → bỏ qua (không nhân đôi)
            badge = cls._ensure_badge(ma_badge)
            _mb, created = MemberBadge.objects.get_or_create(member=member, badge=badge)
            if created:
                newly_unlocked.append(badge.ten_badge)

        return newly_unlocked


# ----------------------------------------------------------------------
# GAMIFICATION SERVICE — award XP + nhiệm vụ tuần
# ----------------------------------------------------------------------
class GamificationService:
    """Nghiệp vụ cộng XP (Server-Authoritative) và widget nhiệm vụ tuần."""

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
            6. BadgeService.evaluate_and_unlock → danh sách badge mới.

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
            member = MemberProfile.objects.select_for_update().get(pk=member.pk)

            # Bước 2 — Idempotency chống cộng lặp
            if idempotency_key and XpLedger.objects.filter(
                idempotency_key=idempotency_key
            ).exists():
                return {
                    "awarded": False,
                    "xp_gained": 0,
                    "member_xp": member.xp_points,
                    "member_level": member.current_level,
                    "new_badges": [],
                    "message": "Đã thưởng trước đó",
                }

            new_badges = BadgeService.evaluate_and_unlock(member)

            # Bước 3+4 — Daily cap 300 XP/ngày
            if amount == 0:
                return {
                    "awarded": False,
                    "xp_gained": 0,
                    "member_xp": member.xp_points,
                    "member_level": member.current_level,
                    "new_badges": new_badges,
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
                        "new_badges": new_badges,
                        "message": "Đã đạt trần XP ngày",
                    }
                actual_amount: int = min(amount, remaining)
            else:
                # Phạt (amount < 0) luôn áp dụng nguyên vẹn
                actual_amount = amount

            # Bước 5 — ghi sổ + cập nhật hồ sơ
            XpLedger.objects.create(
                member=member,
                amount=actual_amount,
                reason=reason,
                source=ledger_source,
                idempotency_key=idempotency_key,
            )
            member.xp_points += actual_amount
            member.current_level = level_from_xp(member.xp_points)
            member.save(update_fields=["xp_points", "current_level", "updated_at"])

            new_badges = BadgeService.evaluate_and_unlock(member)

            return {
                "awarded": True,
                "xp_gained": actual_amount,
                "member_xp": member.xp_points,
                "member_level": member.current_level,
                "new_badges": new_badges,
                "message": f"Đã cộng {actual_amount} XP",
            }

    @staticmethod
    def _xp_used_today(member: MemberProfile) -> int:
        """Tổng XP dương đã nhận hôm nay (múi giờ địa phương) từ XpLedger."""
        today = timezone.localdate()
        result = XpLedger.objects.filter(
            member=member,
            amount__gt=0,
            created_at__date=today,
        ).aggregate(total=Coalesce(Sum("amount"), Value(0)))
        return int(result["total"] or 0)

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

        ledger_this_week = XpLedger.objects.filter(
            member=member,
            created_at__date__gte=monday,
        )
        xp_this_week: int = int(
            ledger_this_week.aggregate(total=Coalesce(Sum("amount"), Value(0)))["total"] or 0
        )
        attendance_count: int = AttendanceRecord.objects.filter(
            member=member,
            trang_thai__in=[
                AttendanceRecord.TrangThaiDiemDanh.CO_MAT,
                AttendanceRecord.TrangThaiDiemDanh.DI_MUON,
            ],
            created_at__date__gte=monday,
        ).count()
        document_shared: int = ledger_this_week.filter(
            source=XpLedger.Source.DOCUMENT_SHARE
        ).count()
        task_completed: int = ledger_this_week.filter(
            source=XpLedger.Source.TASK_COMPLETION
        ).count()

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

    @classmethod
    def get_leaderboard(cls, member_profile: Optional[MemberProfile] = None) -> dict:
        """
        Lấy Top 10 + vị trí cá nhân (nếu truyền `member_profile`).

        Args:
            member_profile: hồ sơ của user hiện tại (có thể None).

        Returns:
            {"top_10": [...], "my_position": {...}|None, "total_members": int}
        """
        active_profiles = (
            MemberProfile.objects.filter(
                trang_thai_hd=MemberProfile.TrangThai.ACTIVE,
            )
            .select_related("user")
            .order_by("-xp_points", "ho_ten")
        )
        members: list[dict[str, Any]] = [
            {
                "id": profile.pk,
                "xp": profile.xp_points,
                "name": profile.ho_ten,
                "avatar": profile.avatar or "",
            }
            for profile in active_profiles
        ]

        engine = LeaderboardEngine(top_k=cls.TOP_K)
        top_10 = engine.compute_top_k(members)

        my_position: Optional[dict] = None
        if member_profile is not None:
            my_position = engine.find_my_position(member_profile.pk, members)

        return {
            "top_10": top_10,
            "my_position": my_position,
            "total_members": len(members),
        }
