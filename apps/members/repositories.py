"""
Repository Layer — apps.members
Repository Pattern (DIP): tách tầng truy vấn CSDL khỏi tầng nghiệp vụ.
Service chỉ phụ thuộc interface, không phụ thuộc ORM trực tiếp.
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Iterable, Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.members.models import BoardMember, MemberProfile

User = get_user_model()

# Whitelist các trường được phép sort (chống SQL injection qua order_by — Security §2.1)
ALLOWED_SORT_FIELDS = {
    "created_at", "-created_at",
    "xp_points", "-xp_points",
    "ho_ten", "-ho_ten",
}
DEFAULT_SORT = "-xp_points"


def _build_search_q(search: str) -> Q:
    """Q object tìm kiếm họ tên / MSSV / email (ORM parameterized — an toàn SQLi)."""
    return (
        Q(ho_ten__icontains=search)
        | Q(user__mssv__icontains=search)
        | Q(user__email__icontains=search)
    )


class IMemberRepository(ABC):
    """Interface repository thành viên (Dependency Inversion Principle)."""

    # ------------------------------------------------------------------
    # Truy vấn cơ bản
    # ------------------------------------------------------------------
    @abstractmethod
    def get_by_id(self, member_id: int) -> Optional[MemberProfile]:
        """Lấy profile theo ID (kèm user)."""

    @abstractmethod
    def get_by_user(self, user) -> Optional[MemberProfile]:
        """Lấy profile theo User sở hữu (None nếu user chưa có hồ sơ)."""

    @abstractmethod
    def get_all(self) -> QuerySet:
        """QuerySet toàn bộ thành viên."""

    @abstractmethod
    def get_active_members(self) -> QuerySet:
        """Danh sách thành viên đang ACTIVE."""

    @abstractmethod
    def filter_by_class(self, lop: str) -> QuerySet:
        """Lọc theo lớp."""

    @abstractmethod
    def search_by_keyword(self, keyword: str) -> QuerySet:
        """Tìm kiếm icontains (họ tên / MSSV)."""

    @abstractmethod
    def save(self, member: MemberProfile) -> MemberProfile:
        """Lưu profile."""

    # ------------------------------------------------------------------
    # Kiểm tra trùng lặp tài khoản (User)
    # ------------------------------------------------------------------
    @abstractmethod
    def exists_user_by_email(self, email: str, exclude_pk: Optional[int] = None) -> bool:
        """Email đã thuộc về một User nào đó chưa (tùy chọn loại trừ chính user)."""

    @abstractmethod
    def exists_user_by_mssv(self, mssv: str, exclude_pk: Optional[int] = None) -> bool:
        """MSSV đã thuộc về một User nào đó chưa (tùy chọn loại trừ chính user)."""

    # ------------------------------------------------------------------
    # Tạo tài khoản + hồ sơ
    # ------------------------------------------------------------------
    @abstractmethod
    def create_user_with_profile(
        self,
        *,
        email: str,
        password: str,
        ho_ten: str,
        mssv: Optional[str] = None,
        lop: str = "",
        sdt: str = "",
        gioi_tinh: str = "",
        ngay_sinh: Optional[date] = None,
        role: Optional[str] = None,
    ) -> MemberProfile:
        """Tạo User + MemberProfile trong MỘT transaction (mặc định role MEMBER)."""

    # ------------------------------------------------------------------
    # Hồ sơ 360° (truy vấn quan hệ — nhận profile instance)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_profile_registrations(self, profile: MemberProfile) -> QuerySet:
        """Đăng ký sự kiện của thành viên (loại CANCELLED, kèm event)."""

    @abstractmethod
    def count_profile_registrations(self, profile: MemberProfile) -> int:
        """Số đăng ký sự kiện hợp lệ (đã loại CANCELLED)."""

    @abstractmethod
    def get_profile_attendance_records(self, profile: MemberProfile) -> QuerySet:
        """Bản ghi điểm danh của thành viên (kèm session)."""

    @abstractmethod
    def count_profile_attendance(
        self, profile: MemberProfile, trang_thai_in: Optional[Iterable[str]] = None
    ) -> int:
        """Đếm bản ghi điểm danh (tùy chọn lọc theo danh sách trạng thái)."""

    @abstractmethod
    def get_profile_badges(self, profile: MemberProfile) -> QuerySet:
        """Huy hiệu đã mở khóa của thành viên (kèm badge)."""

    @abstractmethod
    def get_recent_xp_entries(self, profile: MemberProfile, limit: int = 5) -> QuerySet:
        """`limit` dòng XP ledger gần nhất của thành viên."""

    @abstractmethod
    def get_profile_board_positions(self, profile: MemberProfile) -> QuerySet:
        """Các chức vụ BCN của thành viên (mọi nhiệm kỳ)."""

    # ------------------------------------------------------------------
    # Trie search (DSA 3)
    # ------------------------------------------------------------------
    @abstractmethod
    def iter_search_index_profiles(self) -> QuerySet:
        """Dòng dữ liệu dựng chỉ mục Trie — chỉ select các trường tối thiểu (.only)."""

    @abstractmethod
    def get_by_ids_ordered_by_xp(
        self, ids: Iterable[int], only_active: bool = False
    ) -> QuerySet:
        """Lấy profile theo danh sách ID, sắp XP giảm dần (tùy chọn chỉ ACTIVE)."""

    # ------------------------------------------------------------------
    # Danh sách / xuất Excel
    # ------------------------------------------------------------------
    @abstractmethod
    def get_all_ordered_by_name(self) -> QuerySet:
        """Toàn bộ thành viên sắp theo họ tên A→Z (phục vụ xuất Excel)."""

    @abstractmethod
    def filter_profiles(
        self,
        lop: Optional[str] = None,
        trang_thai: Optional[str] = None,
        q: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> QuerySet:
        """Lọc + sắp danh sách thành viên (whitelist sort chống SQLi)."""


class DjangoMemberRepository(IMemberRepository):
    """Repository cài đặt bằng Django ORM (select_related chống N+1)."""

    def get_by_id(self, member_id: int) -> Optional[MemberProfile]:
        return (
            MemberProfile.objects.select_related("user")
            .filter(pk=member_id)
            .first()
        )

    def get_by_user(self, user) -> Optional[MemberProfile]:
        """Hồ sơ thành viên gắn với `user` (None nếu chưa có) — tra cứu theo
        user đăng nhập để thao tác trên dữ liệu của chính mình."""
        return MemberProfile.objects.filter(user=user).first()

    def get_all(self) -> QuerySet:
        return MemberProfile.objects.select_related("user").all()

    def get_active_members(self) -> QuerySet:
        return (
            MemberProfile.objects.select_related("user")
            .filter(trang_thai_hd=MemberProfile.TrangThai.ACTIVE)
        )

    def filter_by_class(self, lop: str) -> QuerySet:
        return MemberProfile.objects.select_related("user").filter(lop=lop)

    def search_by_keyword(self, keyword: str) -> QuerySet:
        return MemberProfile.objects.select_related("user").filter(
            Q(ho_ten__icontains=keyword) | Q(user__mssv__icontains=keyword)
        )

    def save(self, member: MemberProfile) -> MemberProfile:
        member.save()
        return member

    # ---------------- Kiểm tra trùng lặp tài khoản ----------------
    def exists_user_by_email(self, email: str, exclude_pk: Optional[int] = None) -> bool:
        """Email đã tồn tại chưa; `exclude_pk` để bỏ qua chính user khi update."""
        queryset = User.objects.filter(email=email)
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)
        return queryset.exists()

    def exists_user_by_mssv(self, mssv: str, exclude_pk: Optional[int] = None) -> bool:
        """MSSV đã tồn tại chưa; `exclude_pk` để bỏ qua chính user khi update."""
        queryset = User.objects.filter(mssv=mssv)
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)
        return queryset.exists()

    # ---------------- Tạo tài khoản + hồ sơ ----------------
    def create_user_with_profile(
        self,
        *,
        email: str,
        password: str,
        ho_ten: str,
        mssv: Optional[str] = None,
        lop: str = "",
        sdt: str = "",
        gioi_tinh: str = "",
        ngay_sinh: Optional[date] = None,
        role: Optional[str] = None,
    ) -> MemberProfile:
        """
        Tạo User + MemberProfile trong MỘT transaction (atomic).

        Hai bảng phải được ghi cùng lúc — nếu tạo profile thất bại thì
        user cũng phải rollback (tránh tài khoản mồ côi không có hồ sơ).

        Returns:
            MemberProfile vừa tạo (đã gắn user, role mặc định MEMBER).
        """
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                password=password,
                mssv=mssv,
                role=role or User.Role.MEMBER,
            )
            profile = MemberProfile.objects.create(
                user=user,
                ho_ten=ho_ten,
                lop=lop,
                sdt=sdt,
                gioi_tinh=gioi_tinh,
                ngay_sinh=ngay_sinh,
            )
        return profile

    # ---------------- Hồ sơ 360° (related queries) ----------------
    def get_profile_registrations(self, profile: MemberProfile) -> QuerySet:
        """Đăng ký sự kiện hợp lệ (bỏ vé CANCELLED) — kèm select_related event."""
        return profile.event_registrations.exclude(
            trang_thai="CANCELLED"
        ).select_related("event")

    def count_profile_registrations(self, profile: MemberProfile) -> int:
        """Số đăng ký sự kiện hợp lệ (đã loại CANCELLED)."""
        return self.get_profile_registrations(profile).count()

    def get_profile_attendance_records(self, profile: MemberProfile) -> QuerySet:
        """Bản ghi điểm danh của thành viên — kèm select_related session."""
        return profile.attendance_records.select_related("session")

    def count_profile_attendance(
        self, profile: MemberProfile, trang_thai_in: Optional[Iterable[str]] = None
    ) -> int:
        """
        Đếm bản ghi điểm danh của thành viên.

        Args:
            trang_thai_in: lọc theo trạng thái (VD: ["CO_MAT", "DI_MUON"]).
        """
        queryset = self.get_profile_attendance_records(profile)
        if trang_thai_in:
            queryset = queryset.filter(trang_thai__in=list(trang_thai_in))
        return queryset.count()

    def get_profile_badges(self, profile: MemberProfile) -> QuerySet:
        """Huy hiệu đã mở khóa của thành viên — kèm select_related badge."""
        return profile.badges.select_related("badge")

    def get_recent_xp_entries(self, profile: MemberProfile, limit: int = 5) -> QuerySet:
        """`limit` dòng XP ledger gần nhất của thành viên."""
        return profile.xp_ledger.all()[:limit]

    def get_profile_board_positions(self, profile: MemberProfile) -> QuerySet:
        """Các chức vụ BCN của thành viên (mọi nhiệm kỳ)."""
        return profile.board_positions.all()

    # ---------------- Trie search (DSA 3) ----------------
    def iter_search_index_profiles(self) -> QuerySet:
        """
        Dòng dữ liệu dựng chỉ mục Trie — chỉ select các trường tối thiểu (.only).

        ⚠ Giữ phương thức này ĐƠN GIẢN và duy nhất: cải tiến tiếp theo sẽ cache
        chỉ mục Trie ở tầng service, toàn bộ truy vấn nguồn vẫn đi qua đây.
        """
        return MemberProfile.objects.select_related("user").only(
            "id", "ho_ten", "user__mssv", "user__email", "lop", "sdt", "gioi_tinh",
            "avatar", "xp_points", "current_level", "streak_count", "trang_thai_hd",
        )

    def get_by_ids_ordered_by_xp(
        self, ids: Iterable[int], only_active: bool = False
    ) -> QuerySet:
        """
        Lấy profile theo danh sách ID (kết quả Trie search), sắp XP giảm dần.

        Args:
            only_active: True → chỉ trả thành viên đang ACTIVE
                (QA-Audit 2a — không lộ danh sách cán bộ ẩn).
        """
        queryset = (
            MemberProfile.objects.select_related("user")
            .filter(pk__in=list(ids))
            .order_by("-xp_points")
        )
        if only_active:
            queryset = queryset.filter(
                trang_thai_hd=MemberProfile.TrangThai.ACTIVE
            )
        return queryset

    # ---------------- Danh sách / xuất Excel ----------------
    def get_all_ordered_by_name(self) -> QuerySet:
        """Toàn bộ thành viên sắp theo họ tên A→Z (phục vụ xuất Excel)."""
        return MemberProfile.objects.select_related("user").order_by("ho_ten")

    def filter_profiles(
        self,
        lop: Optional[str] = None,
        trang_thai: Optional[str] = None,
        q: Optional[str] = None,
        sort: Optional[str] = None,
    ) -> QuerySet:
        """
        Lọc + sắp danh sách thành viên cho API GET /members/.

        Args:
            lop: lọc theo lớp (?lop=).
            trang_thai: lọc theo trạng thái (?trang_thai= ACTIVE/INACTIVE/LEAVE).
            q: từ khóa tìm họ tên / MSSV / email (?search=).
            sort: trường sắp — ngoài ALLOWED_SORT_FIELDS → fallback DEFAULT_SORT
                (chống SQL injection qua order_by — Security §2.1).
        """
        queryset = self.get_all()
        if lop:
            queryset = queryset.filter(lop=lop)
        if trang_thai:
            queryset = queryset.filter(trang_thai_hd=trang_thai)
        if q:
            queryset = queryset.filter(_build_search_q(q))

        sort_param = sort if sort in ALLOWED_SORT_FIELDS else DEFAULT_SORT
        return queryset.order_by(sort_param)

    # ---------------- Bổ trợ cho BoardMember ----------------
    @staticmethod
    def get_board_positions(nhiem_ky: Optional[str] = None) -> QuerySet:
        """Danh sách BCN theo nhiệm kỳ (mặc định tất cả)."""
        qs = BoardMember.objects.select_related("member", "member__user")
        if nhiem_ky:
            qs = qs.filter(nhiem_ky=nhiem_ky)
        return qs
