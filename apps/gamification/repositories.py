"""
Repository Layer — apps.gamification
====================================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion), làm theo mẫu
`apps/funds/repositories.py`.

`BadgeService` / `GamificationService` / `LeaderboardService` và tầng View chỉ
phụ thuộc trừu tượng `IGamificationRepository`, không đụng trực tiếp vào ORM
(`.objects.`). 100% truy vấn dùng Django ORM parameterized (TUYỆT ĐỐI không raw
SQL — Security Hardening §2.1).

Lưu ý ranh giới xuyên app (KHÔNG sửa app khác khi refactor này):
    - `find_member_profile_by_user`: members.repository chưa có lookup theo
      `user` → helper bridge đặt tại đây thay vì đụng vào apps/members.
    - `count_attended_records(_since)`: truy vấn XUYÊN APP sang attendance
      (điều kiện mở badge ATTENDANCE_10 + nhiệm vụ tuần) — apps.attendance
      giữ nguyên, điều kiện CO_MAT/DI_MUON copy đúng logic cũ.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from django.db.models import QuerySet, Sum, Value
from django.db.models.functions import Coalesce

from apps.attendance.models import AttendanceRecord
from apps.gamification.models import Badge, MemberBadge, XpLedger
from apps.members.models import MemberProfile


class IGamificationRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Gamification — phụ thuộc trừu tượng (DIP)."""

    # ---------------- MemberProfile (xuyên app: apps.members) ----------------
    @abstractmethod
    def find_member_profile_by_user(self, user: Any) -> Optional[MemberProfile]:
        """Hồ sơ thành viên theo user đăng nhập (None nếu chưa có)."""

    @abstractmethod
    def get_active_profiles_ordered(self) -> QuerySet[MemberProfile]:
        """Thành viên ACTIVE kèm user, sắp theo XP giảm dần rồi họ tên (bảng vàng)."""

    @abstractmethod
    def iter_leaderboard_rows(self):
        """Duyệt nhẹ (id, xp, ho_ten, avatar) của thành viên ACTIVE — KHÔNG order_by.

        QA-Audit nhóm 5: leaderboard dùng Min-Heap tự xếp O(N log K), việc
        order_by toàn bảng ở DB là lãng phí; values_list tránh dựng model instance.
        """

    @abstractmethod
    def count_active_profiles(self) -> int:
        """Tổng số thành viên ACTIVE (total_members cho leaderboard)."""

    @abstractmethod
    def count_active_profiles_with_xp_greater_than(self, xp: int) -> int:
        """Số thành viên ACTIVE có XP cao hơn `xp` — tính rank cá nhân bằng DB
        Count thay vì quét O(N) Python (QA-Audit nhóm 5)."""

    @abstractmethod
    def lock_member_profile(self, pk: int) -> MemberProfile:
        """Lấy hồ sơ theo pk VỚI KHÓA BI (select_for_update) — chống race cộng XP."""

    # ---------------- Badge / MemberBadge ----------------
    @abstractmethod
    def list_all_badges(self) -> QuerySet[Badge]:
        """Toàn bộ định nghĩa huy hiệu (thứ tự theo Meta.ordering = ma_badge)."""

    @abstractmethod
    def get_or_create_badge(self, ma_badge: str, defaults: dict) -> tuple[Badge, bool]:
        """Lấy hoặc tạo badge theo mã (idempotent — catalog mặc định)."""

    @abstractmethod
    def get_unlocked_badge_ids(self, member: MemberProfile) -> set[int]:
        """Set id badge thành viên đã mở (1 query duy nhất — chống N+1)."""

    @abstractmethod
    def list_member_badges(self, member: MemberProfile) -> QuerySet[MemberBadge]:
        """Huy hiệu đã mở của thành viên, nạp sẵn badge (select_related)."""

    @abstractmethod
    def member_has_badge(self, member: MemberProfile, ma_badge: str) -> bool:
        """Thành viên đã mở badge theo mã chưa (chặn nhân đôi badge)."""

    @abstractmethod
    def get_or_create_member_badge(
        self, member: MemberProfile, badge: Badge
    ) -> tuple[MemberBadge, bool]:
        """Mở badge cho thành viên (idempotent — unique constraint)."""

    # ---------------- AttendanceRecord (xuyên app: apps.attendance) ----------------
    @abstractmethod
    def count_attended_records(self, member: MemberProfile) -> int:
        """Số buổi có mặt/đi muộn toàn bộ lịch sử (điều kiện badge ATTENDANCE_10)."""

    @abstractmethod
    def count_attended_records_since(
        self, member: MemberProfile, since_dt: datetime
    ) -> int:
        """Số buổi có mặt/đi muộn tính từ mốc `since_dt` (nhiệm vụ tuần)."""

    # ---------------- XpLedger ----------------
    @abstractmethod
    def count_ledger_entries(
        self,
        member: MemberProfile,
        *,
        source: str,
        since_dt: Optional[datetime] = None,
    ) -> int:
        """Đếm dòng sổ XP theo nguồn (tùy chọn: chỉ tính từ mốc `since_dt`)."""

    @abstractmethod
    def sum_xp_since(self, member: MemberProfile, since_dt: datetime) -> int:
        """Tổng XP (âm + dương) trong sổ từ mốc `since_dt` (nhiệm vụ tuần)."""

    @abstractmethod
    def sum_positive_xp_between(
        self, member: MemberProfile, start_dt: datetime, end_dt: datetime
    ) -> int:
        """Tổng XP dương trong khoảng [start_dt, end_dt) — phục vụ Daily XP Cap."""

    @abstractmethod
    def exists_idempotency_key(self, key: str) -> bool:
        """Khóa chống cộng lặp đã tồn tại trong sổ XP chưa."""

    @abstractmethod
    def create_ledger_entry(self, **fields) -> XpLedger:
        """Ghi một dòng biến động XP vào sổ cái."""


class DjangoGamificationRepository(IGamificationRepository):
    """Triển khai cụ thể bằng Django ORM cho `IGamificationRepository`."""

    # ---------------- MemberProfile ----------------
    def find_member_profile_by_user(self, user: Any) -> Optional[MemberProfile]:
        """Hồ sơ theo user — ủy quyền cho members repository (nguồn chuẩn)."""
        from apps.members.repositories import DjangoMemberRepository  # noqa: PLC0415

        return DjangoMemberRepository().get_by_user(user)

    def get_active_profiles_ordered(self) -> QuerySet[MemberProfile]:
        """ACTIVE + select_related user + thứ tự XP giảm dần, họ tên tăng dần."""

    def iter_leaderboard_rows(self):
        return (
            MemberProfile.objects.filter(
                trang_thai_hd=MemberProfile.TrangThai.ACTIVE
            )
            .values_list("id", "xp_points", "ho_ten", "avatar")
            .iterator()
        )

    def count_active_profiles(self) -> int:
        return MemberProfile.objects.filter(
            trang_thai_hd=MemberProfile.TrangThai.ACTIVE
        ).count()

    def count_active_profiles_with_xp_greater_than(self, xp: int) -> int:
        return MemberProfile.objects.filter(
            trang_thai_hd=MemberProfile.TrangThai.ACTIVE,
            xp_points__gt=xp,
        ).count()
        return (
            MemberProfile.objects.filter(
                trang_thai_hd=MemberProfile.TrangThai.ACTIVE,
            )
            .select_related("user")
            .order_by("-xp_points", "ho_ten")
        )

    def lock_member_profile(self, pk: int) -> MemberProfile:
        """
        Lấy hồ sơ theo pk VỚI KHÓA BI (pessimistic locking).

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — hai request cộng XP
        song song sẽ tuần tự hóa tại đây (Security Hardening §5.3).
        """
        return MemberProfile.objects.select_for_update().get(pk=pk)

    # ---------------- Badge / MemberBadge ----------------
    def list_all_badges(self) -> QuerySet[Badge]:
        """Toàn bộ badge — thứ tự do Meta.ordering của Badge quyết định (ma_badge)."""
        return Badge.objects.all()

    def get_or_create_badge(self, ma_badge: str, defaults: dict) -> tuple[Badge, bool]:
        """get_or_create badge theo `ma_badge` (idempotent, khớp logic cũ)."""
        return Badge.objects.get_or_create(ma_badge=ma_badge, defaults=defaults)

    def get_unlocked_badge_ids(self, member: MemberProfile) -> set[int]:
        """Một query duy nhất lấy id badge đã mở của member (tránh N+1)."""
        return set(
            MemberBadge.objects.filter(member=member).values_list("badge_id", flat=True)
        )

    def list_member_badges(self, member: MemberProfile) -> QuerySet[MemberBadge]:
        """Huy hiệu đã mở, nạp sẵn badge cha (thứ tự Meta: -awarded_at)."""
        return member.badges.select_related("badge").all()

    def member_has_badge(self, member: MemberProfile, ma_badge: str) -> bool:
        """Đã mở badge theo mã chưa — đánh giá lại badge không nhân đôi."""
        return MemberBadge.objects.filter(
            member=member, badge__ma_badge=ma_badge
        ).exists()

    def get_or_create_member_badge(
        self, member: MemberProfile, badge: Badge
    ) -> tuple[MemberBadge, bool]:
        """Ghi nhận mở badge (idempotent nhờ UniqueConstraint member+badge)."""
        return MemberBadge.objects.get_or_create(member=member, badge=badge)

    # ---------------- AttendanceRecord (xuyên app — KHÔNG sửa apps.attendance) ----------------
    def count_attended_records(self, member: MemberProfile) -> int:
        """Toàn bộ lịch sử CO_MAT/DI_MUON — điều kiện mở badge ATTENDANCE_10."""
        return AttendanceRecord.objects.filter(
            member=member,
            trang_thai__in=[
                AttendanceRecord.TrangThaiDiemDanh.CO_MAT,
                AttendanceRecord.TrangThaiDiemDanh.DI_MUON,
            ],
        ).count()

    def count_attended_records_since(
        self, member: MemberProfile, since_dt: datetime
    ) -> int:
        """Số buổi CO_MAT/DI_MUON từ mốc `since_dt` — widget nhiệm vụ tuần."""
        return AttendanceRecord.objects.filter(
            member=member,
            trang_thai__in=[
                AttendanceRecord.TrangThaiDiemDanh.CO_MAT,
                AttendanceRecord.TrangThaiDiemDanh.DI_MUON,
            ],
            created_at__gte=since_dt,
        ).count()

    # ---------------- XpLedger ----------------
    def count_ledger_entries(
        self,
        member: MemberProfile,
        *,
        source: str,
        since_dt: Optional[datetime] = None,
    ) -> int:
        """Đếm dòng sổ XP theo nguồn; có `since_dt` thì lọc từ mốc đó trở đi."""
        queryset = XpLedger.objects.filter(member=member, source=source)
        if since_dt is not None:
            queryset = queryset.filter(created_at__gte=since_dt)
        return queryset.count()

    def sum_xp_since(self, member: MemberProfile, since_dt: datetime) -> int:
        """Tổng XP (cả âm lẫn dương) từ mốc `since_dt` — XP tích lũy trong tuần."""
        result = XpLedger.objects.filter(
            member=member,
            created_at__gte=since_dt,
        ).aggregate(total=Coalesce(Sum("amount"), Value(0)))
        return int(result["total"] or 0)

    def sum_positive_xp_between(
        self, member: MemberProfile, start_dt: datetime, end_dt: datetime
    ) -> int:
        """Tổng XP dương trong [start_dt, end_dt) — dùng tính phần dư Daily Cap."""
        result = XpLedger.objects.filter(
            member=member,
            amount__gt=0,
            created_at__gte=start_dt,
            created_at__lt=end_dt,
        ).aggregate(total=Coalesce(Sum("amount"), Value(0)))
        return int(result["total"] or 0)

    def exists_idempotency_key(self, key: str) -> bool:
        """Khóa chống cộng lặp đã ghi sổ chưa (idempotency replay)."""
        return XpLedger.objects.filter(idempotency_key=key).exists()

    def create_ledger_entry(self, **fields) -> XpLedger:
        """Ghi một dòng biến động XP (INSERT một dòng duy nhất)."""
        return XpLedger.objects.create(**fields)
