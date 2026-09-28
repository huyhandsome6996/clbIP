"""
Service Layer — apps.posts
==========================
Toàn bộ nghiệp vụ Bảng tin / Hòm thư góp ý / Bình chọn nằm tại đây:
    - PostService:     CRUD bài đăng + bleach chống XSS + Audit log + Ghim.
    - FeedbackService: Hòm thư góp ý ẨN DANH + chống spam 5 góp ý/ngày.
    - PollService:     Bình chọn với select_for_update chống race condition.

Chống XSS theo CLBIP_Security_Hardening_Prompt.md §2.2: mọi nội dung do
người dùng nhập PHẢI qua bleach.clean trước khi lưu DB.
"""
import logging
from typing import Optional

import bleach
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    DuplicateDataException,
    EventStatusException,
    NotFoundException,
    ValidationException,
)
from apps.common.timeutils import local_day_range
from apps.posts.models import CommunityPoll, FeedbackEntry, Post, PostAuditLog

logger = logging.getLogger(__name__)


class PostService:
    """
    Nghiệp vụ bảng tin — mọi thay đổi bài đăng đều ghi PostAuditLog
    để đảm bảo trách nhiệm giải trình (màn hình 2: Dashboard BCN).
    """

    # Whitelist tag HTML an toàn cho nội dung bài đăng (Security §2.2)
    ALLOWED_TAGS: list = ["p", "br", "strong", "em", "u", "ul", "ol", "li", "a"]
    ALLOWED_ATTRIBUTES: dict = {"a": ["href"]}

    @classmethod
    def sanitize(cls, html: str) -> str:
        """Làm sạch HTML qua bleach — strip mọi tag không nằm trong whitelist."""
        return bleach.clean(
            html or "",
            tags=cls.ALLOWED_TAGS,
            attributes=cls.ALLOWED_ATTRIBUTES,
            strip=True,
        )

    # ==================================================================
    # CRUD + Audit
    # ==================================================================
    @classmethod
    def create_post(cls, data: dict, actor) -> Post:
        """
        BCN đăng bài mới: sanitize nội dung + ghi audit CREATE.

        Args:
            data: dict gồm tieu_de, noi_dung, anh_dinh_kem (optional).
            actor: User BCN/ADMIN thực hiện.

        Returns:
            Post vừa tạo.
        """
        post = Post.objects.create(
            tieu_de=cls.sanitize_text(data.get("tieu_de", "")),
            noi_dung=cls.sanitize(data.get("noi_dung", "")),
            anh_dinh_kem=data.get("anh_dinh_kem", "") or "",
            created_by=actor,
        )
        cls._log(post, PostAuditLog.Action.CREATE, actor, "Đăng bài mới")
        logger.info("Post #%s '%s' đăng bởi %s", post.pk, post.tieu_de, getattr(actor, "email", "?"))
        return post

    @classmethod
    def update_post(cls, post: Post, data: dict, actor) -> Post:
        """
        BCN sửa bài: sanitize nội dung nếu có + ghi audit UPDATE kèm danh sách field sửa.

        Args:
            post: Post cần sửa.
            data: dict các field hợp lệ (tieu_de, noi_dung, anh_dinh_kem).
            actor: User thực hiện.
        """
        changed_fields: list = []
        if "tieu_de" in data and data["tieu_de"] is not None:
            post.tieu_de = cls.sanitize_text(data["tieu_de"])
            changed_fields.append("tieu_de")
        if "noi_dung" in data and data["noi_dung"] is not None:
            post.noi_dung = cls.sanitize(data["noi_dung"])
            changed_fields.append("noi_dung")
        if "anh_dinh_kem" in data and data["anh_dinh_kem"] is not None:
            post.anh_dinh_kem = data["anh_dinh_kem"] or ""
            changed_fields.append("anh_dinh_kem")
        post.save(update_fields=changed_fields or None)
        cls._log(post, PostAuditLog.Action.UPDATE, actor, f"Sửa các trường: {', '.join(changed_fields) or '-'}")
        return post

    @classmethod
    def toggle_pin(cls, post: Post, actor) -> Post:
        """
        Ghim / bỏ ghim bài (đảo trạng thái) + ghi audit PIN/UNPIN.

        Ghim: pinned_at = now. Bỏ ghim: pinned_at = None.
        """
        post.is_pinned = not post.is_pinned
        post.pinned_at = timezone.now() if post.is_pinned else None
        post.save(update_fields=["is_pinned", "pinned_at", "updated_at"])
        action = PostAuditLog.Action.PIN if post.is_pinned else PostAuditLog.Action.UNPIN
        cls._log(post, action, actor, "Ghim bài lên đầu bảng tin" if post.is_pinned else "Bỏ ghim bài")
        return post

    @classmethod
    def soft_delete_post(cls, post: Post, actor) -> Post:
        """Soft delete: is_deleted=True (giữ dữ liệu + audit), feed không còn hiện."""
        post.is_deleted = True
        post.save(update_fields=["is_deleted", "updated_at"])
        cls._log(post, PostAuditLog.Action.DELETE, actor, "Xóa bài đăng (soft delete)")
        return post

    @staticmethod
    def get_feed(user=None):
        """
        Feed bảng tin cho MEMBER PORTAL: bỏ bài đã xóa, bài ghim lên đầu,
        mới nhất trước. Tham số `user` giữ chỗ cho cá nhân hóa tương lai.
        """
        return Post.objects.filter(is_deleted=False).order_by("-is_pinned", "-created_at")

    @staticmethod
    def get_or_404(pk: int) -> Post:
        """Lấy Post theo pk hoặc raise NotFoundException."""
        try:
            return Post.objects.get(pk=pk)
        except Post.DoesNotExist as exc:
            raise NotFoundException("Không tìm thấy bài đăng yêu cầu.") from exc

    # ==================================================================
    # Nội bộ
    # ==================================================================
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text thuần (tiêu đề) — không cho phép tag nào."""
        return bleach.clean(text or "", tags=[], strip=True)

    @staticmethod
    def _log(post: Post, action: str, actor, chi_tiet: str) -> None:
        """Ghi một dòng PostAuditLog — mọi hành động đều phải truy vết được."""
        PostAuditLog.objects.create(post=post, action=action, performed_by=actor, chi_tiet=chi_tiet)


class FeedbackService:
    """
    Hòm thư góp ý ẨN DANH — BCN chỉ thấy nội dung + thời gian,
    TUYỆT ĐỐI không thấy người gửi (chống sợ trả đũa, khuyến khích góp ý thẳng).

    Chống spam (Security §3): tối đa 5 góp ý / user / ngày (song song với
    FeedbackRateThrottle 2 request/phút ở tầng view).
    """

    DAILY_LIMIT: int = 5

    @classmethod
    def create_feedback(cls, noi_dung: str, user) -> FeedbackEntry:
        """
        Tạo góp ý ẩn danh.

        Args:
            noi_dung: Nội dung góp ý (text thuần — sẽ qua bleach strip tag).
            user: Người gửi (lưu để chống spam, KHÔNG expose ra ngoài).

        Raises:
            ValidationException: Nội dung rỗng hoặc vượt hạn mức 5 góp ý/ngày.
        """
        noi_dung = (noi_dung or "").strip()
        if not noi_dung:
            raise ValidationException("Nội dung góp ý không được để trống.")

        day_start, day_end = local_day_range(timezone.localdate())
        count_today = FeedbackEntry.objects.filter(
            sender=user, created_at__gte=day_start, created_at__lt=day_end
        ).count()
        if count_today >= cls.DAILY_LIMIT:
            raise ValidationException("Bạn đã gửi quá nhiều góp ý hôm nay. Hãy quay lại vào mai!")

        entry = FeedbackEntry.objects.create(
            noi_dung=bleach.clean(noi_dung, tags=[], strip=True),
            is_anonymous=True,
            sender=user,
        )
        logger.info("Feedback #%s (ẩn danh) — user pk=%s", entry.pk, user.pk)
        return entry

    @staticmethod
    def list_feedback():
        """
        Danh sách góp ý cho BCN — QuerySet CHỈ gồm nội dung + thời gian.

        Serializer tương ứng (FeedbackListSerializer) TUYỆT ĐỐI không serialize
        sender — ẩn danh đúng nghĩa ngay cả khi BCN đọc.
        """
        return FeedbackEntry.objects.all()


class PollService:
    """
    Bình chọn cộng đồng — chống race condition bằng select_for_update,
    chống double-vote bằng voted_user_ids (JSON list).
    """

    @classmethod
    def create_poll(cls, question: str, options: list, actor) -> CommunityPoll:
        """
        BCN tạo bình chọn — ít nhất 2 lựa chọn.

        votes khởi tạo {"0": 0, "1": 0, ...} khớp index của options.

        Raises:
            ValidationException: question/options rỗng hoặc < 2 lựa chọn.
        """
        question = (question or "").strip()
        options = [str(o).strip() for o in (options or []) if str(o).strip()]
        if not question:
            raise ValidationException("Câu hỏi bình chọn không được để trống.")
        if len(options) < 2:
            raise ValidationException("Bình chọn cần ít nhất 2 lựa chọn.")

        poll = CommunityPoll.objects.create(
            question=question,
            options=options,
            votes={str(i): 0 for i in range(len(options))},
            voted_user_ids=[],
            created_by=actor,
        )
        logger.info("Poll #%s '%s' tạo bởi %s", poll.pk, poll.question, getattr(actor, "email", "?"))
        return poll

    @classmethod
    def vote(cls, poll_id: int, option_index: int, user) -> CommunityPoll:
        """
        Ghi nhận bình chọn của 1 user (mỗi user 1 lần / poll) — atomic + row lock.

        Thứ tự kiểm tra: tồn tại → is_closed → double-vote → option hợp lệ.

        Raises:
            NotFoundException: Poll không tồn tại.
            EventStatusException: Bình chọn đã đóng.
            DuplicateDataException: User đã bình chọn rồi.
            ValidationException: option_index ngoài phạm vi options.
        """
        with transaction.atomic():
            try:
                poll = CommunityPoll.objects.select_for_update().get(pk=poll_id)
            except CommunityPoll.DoesNotExist as exc:
                raise NotFoundException("Không tìm thấy bình chọn yêu cầu.") from exc

            if poll.is_closed:
                raise EventStatusException("Bình chọn đã đóng. Cảm ơn bạn đã quan tâm!")

            if str(user.pk) in (poll.voted_user_ids or []):
                raise DuplicateDataException("Bạn đã bình chọn rồi!")

            options: list = poll.options or []
            if option_index < 0 or option_index >= len(options):
                raise ValidationException("Lựa chọn không hợp lệ.")

            votes: dict = dict(poll.votes or {})
            votes[str(option_index)] = votes.get(str(option_index), 0) + 1
            poll.votes = votes
            poll.voted_user_ids = [*poll.voted_user_ids, str(user.pk)]
            poll.save()

        logger.info(
            "Poll #%s vote option=%s bởi user pk=%s", poll_id, option_index, user.pk
        )
        return poll

    @staticmethod
    def get_or_404(pk: int) -> Optional[CommunityPoll]:
        """Lấy Poll theo pk hoặc raise NotFoundException."""
        try:
            return CommunityPoll.objects.get(pk=pk)
        except CommunityPoll.DoesNotExist as exc:
            raise NotFoundException("Không tìm thấy bình chọn yêu cầu.") from exc
