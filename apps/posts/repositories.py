"""
Repository Layer — apps.posts
=============================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion).

`PostService` / `FeedbackService` / `PollService` chỉ phụ thuộc vào trừu tượng
`IPostRepository`, không đụng trực tiếp vào ORM của `Post` / `PostAuditLog` /
`FeedbackEntry` / `CommunityPoll`. 100% truy vấn dùng Django ORM parameterized
(TUYỆT ĐỐI không raw SQL — Security Hardening §2.1).
"""
from abc import ABC, abstractmethod
from typing import Optional

from django.db.models import QuerySet

from apps.posts.models import CommunityPoll, FeedbackEntry, Post, PostAuditLog


class IPostRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Bảng tin / Góp ý / Bình chọn (DIP)."""

    # ---------------- Post (Bảng tin) ----------------
    @abstractmethod
    def create_post(self, **fields) -> Post:
        """Ghi một bài đăng mới."""

    @abstractmethod
    def get_feed_queryset(self) -> QuerySet[Post]:
        """Feed bảng tin: bỏ bài đã xóa, ghim lên đầu, mới nhất trước."""

    @abstractmethod
    def get_post(self, pk: int) -> Optional[Post]:
        """Lấy bài đăng theo pk (None nếu không tồn tại)."""

    @abstractmethod
    def all_posts(self) -> QuerySet[Post]:
        """Queryset toàn bộ bài đăng (phục vụ view chi tiết)."""

    @abstractmethod
    def create_audit_log(self, **fields) -> PostAuditLog:
        """Ghi một dòng PostAuditLog (CREATE/UPDATE/PIN/UNPIN/DELETE)."""

    # ---------------- FeedbackEntry (Hòm thư góp ý) ----------------
    @abstractmethod
    def count_feedback_today(self, sender, day_start, day_end) -> int:
        """Đếm góp ý của `sender` trong khoảng [day_start, day_end) (chống spam)."""

    @abstractmethod
    def create_feedback(self, **fields) -> FeedbackEntry:
        """Ghi một góp ý ẩn danh."""

    @abstractmethod
    def all_feedback(self) -> QuerySet[FeedbackEntry]:
        """Queryset toàn bộ góp ý (BCN đọc — serializer ẩn sender)."""

    # ---------------- CommunityPoll (Bình chọn) ----------------
    @abstractmethod
    def create_poll(self, **fields) -> CommunityPoll:
        """Ghi một bình chọn mới."""

    @abstractmethod
    def get_poll(self, pk: int) -> Optional[CommunityPoll]:
        """Lấy bình chọn theo pk (None nếu không tồn tại)."""

    @abstractmethod
    def get_poll_for_update(self, pk: int) -> Optional[CommunityPoll]:
        """Lấy bình chọn kèm KHÓA BI (select_for_update) — bắt buộc trong atomic."""

    @abstractmethod
    def all_polls(self) -> QuerySet[CommunityPoll]:
        """Queryset toàn bộ bình chọn (danh sách poll — Meta ordering -created_at)."""


class DjangoPostRepository(IPostRepository):
    """Triển khai cụ thể bằng Django ORM cho `IPostRepository`."""

    # ---------------- Post (Bảng tin) ----------------
    def create_post(self, **fields) -> Post:
        """Ghi bài đăng mới (INSERT một dòng)."""
        return Post.objects.create(**fields)

    def get_feed_queryset(self) -> QuerySet[Post]:
        """Feed: is_deleted=False, bài ghim lên đầu, mới nhất trước."""
        return Post.objects.filter(is_deleted=False).order_by("-is_pinned", "-created_at")

    def get_post(self, pk: int) -> Optional[Post]:
        """Lấy bài đăng theo pk (None nếu không tồn tại)."""
        return Post.objects.filter(pk=pk).first()

    def all_posts(self) -> QuerySet[Post]:
        """Toàn bộ bài đăng (kể cả soft-deleted — view tự xử lý lookup)."""
        return Post.objects.all()

    def create_audit_log(self, **fields) -> PostAuditLog:
        """Ghi audit trail (INSERT một dòng)."""
        return PostAuditLog.objects.create(**fields)

    # ---------------- FeedbackEntry (Hòm thư góp ý) ----------------
    def count_feedback_today(self, sender, day_start, day_end) -> int:
        """Số góp ý user đã gửi trong ngày địa phương (múi giờ từ tầng service)."""
        return FeedbackEntry.objects.filter(
            sender=sender, created_at__gte=day_start, created_at__lt=day_end
        ).count()

    def create_feedback(self, **fields) -> FeedbackEntry:
        """Ghi góp ý ẩn danh (INSERT một dòng)."""
        return FeedbackEntry.objects.create(**fields)

    def all_feedback(self) -> QuerySet[FeedbackEntry]:
        """Toàn bộ góp ý — FeedbackListSerializer không bao giờ serialize sender."""
        return FeedbackEntry.objects.all()

    # ---------------- CommunityPoll (Bình chọn) ----------------
    def create_poll(self, **fields) -> CommunityPoll:
        """Ghi bình chọn mới (INSERT một dòng)."""
        return CommunityPoll.objects.create(**fields)

    def get_poll(self, pk: int) -> Optional[CommunityPoll]:
        """Lấy bình chọn theo pk (None nếu không tồn tại)."""
        return CommunityPoll.objects.filter(pk=pk).first()

    def get_poll_for_update(self, pk: int) -> Optional[CommunityPoll]:
        """
        Lấy bình chọn VỚI KHÓA BI (pessimistic locking).

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — chống race condition
        double-vote khi 2 thành viên cùng bấm bình chọn đồng thời (Security §5.3).
        """
        return CommunityPoll.objects.select_for_update().filter(pk=pk).first()

    def all_polls(self) -> QuerySet[CommunityPoll]:
        """Toàn bộ bình chọn, mới nhất trước (khớp Meta.ordering)."""
        return CommunityPoll.objects.all()
