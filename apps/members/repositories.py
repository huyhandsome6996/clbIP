"""
Repository Layer — apps.members
Repository Pattern (DIP): tách tầng truy vấn CSDL khỏi tầng nghiệp vụ.
Service chỉ phụ thuộc interface, không phụ thuộc ORM trực tiếp.
"""
from abc import ABC, abstractmethod
from typing import Iterable, Optional

from django.db.models import Q, QuerySet

from apps.members.models import BoardMember, MemberProfile


class IMemberRepository(ABC):
    """Interface repository thành viên (Dependency Inversion Principle)."""

    @abstractmethod
    def get_by_id(self, member_id: int) -> Optional[MemberProfile]:
        """Lấy profile theo ID (kèm user)."""

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


class DjangoMemberRepository(IMemberRepository):
    """Repository cài đặt bằng Django ORM (select_related chống N+1)."""

    def get_by_id(self, member_id: int) -> Optional[MemberProfile]:
        return (
            MemberProfile.objects.select_related("user")
            .filter(pk=member_id)
            .first()
        )

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

    # ---------------- Bổ trợ cho BoardMember ----------------
    @staticmethod
    def get_board_positions(nhiem_ky: Optional[str] = None) -> QuerySet:
        """Danh sách BCN theo nhiệm kỳ (mặc định tất cả)."""
        qs = BoardMember.objects.select_related("member", "member__user")
        if nhiem_ky:
            qs = qs.filter(nhiem_ky=nhiem_ky)
        return qs
