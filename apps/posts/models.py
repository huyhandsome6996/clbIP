"""
App: posts — Post (Bảng tin), PostAuditLog (Audit ghim/sửa/xóa),
CommunityPoll (Bình chọn), FeedbackEntry (Hòm thư góp ý ẩn danh).
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Post(TimeStampedModel):
    """Bài đăng bảng tin của BCN — hỗ trợ ghim lên đầu trang."""

    tieu_de: models.CharField = models.CharField("Tiêu đề", max_length=200)
    noi_dung: models.TextField = models.TextField("Nội dung (đã sanitize HTML)")
    anh_dinh_kem: models.URLField = models.URLField(
        "Ảnh đính kèm (URL)", max_length=500, blank=True, default=""
    )
    is_pinned: models.BooleanField = models.BooleanField("Được ghim", default=False, db_index=True)
    pinned_at: models.DateTimeField = models.DateTimeField("Thời điểm ghim", null=True, blank=True)
    is_deleted: models.BooleanField = models.BooleanField("Đã xóa (soft)", default=False)

    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="posts_created",
        verbose_name="Người đăng",
    )

    class Meta:
        db_table = "posts"
        verbose_name = "Bài đăng"
        verbose_name_plural = "Bảng tin"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self) -> str:
        return f"{self.tieu_de}{' 📌' if self.is_pinned else ''}"


class PostAuditLog(models.Model):
    """Lịch sử chỉnh sửa / xóa / ghim bài đăng — đảm bảo trách nhiệm giải trình."""

    class Action(models.TextChoices):
        CREATE = "CREATE", "Tạo mới"
        UPDATE = "UPDATE", "Chỉnh sửa"
        DELETE = "DELETE", "Xóa"
        PIN = "PIN", "Ghim"
        UNPIN = "UNPIN", "Bỏ ghim"

    post: models.ForeignKey = models.ForeignKey(
        Post, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action: models.CharField = models.CharField("Hành động", max_length=10, choices=Action.choices)
    performed_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="post_audit_logs",
        verbose_name="Người thực hiện",
    )
    timestamp: models.DateTimeField = models.DateTimeField("Thời điểm", auto_now_add=True, db_index=True)
    chi_tiet: models.TextField = models.TextField("Chi tiết thay đổi", blank=True, default="")

    class Meta:
        db_table = "post_audit_logs"
        verbose_name = "Audit log bài đăng"
        verbose_name_plural = "Audit log bài đăng"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.post_id} · {self.action} · {self.timestamp:%d/%m/%Y %H:%M}"


class CommunityPoll(TimeStampedModel):
    """Bình chọn / Góp ý theo chủ đề — mỗi thành viên vote 1 lần."""

    question: models.CharField = models.CharField("Câu hỏi bình chọn", max_length=255)
    # Danh sách lựa chọn: ["Option A", "Option B", ...]
    options: models.JSONField = models.JSONField("Các lựa chọn", default=list)
    # Đếm票: {"0": 12, "1": 5} — key là index lựa chọn
    votes: models.JSONField = models.JSONField("Kết quả bình chọn", default=dict)
    # user_id đã vote để chặn vote 2 lần
    voted_user_ids: models.JSONField = models.JSONField("User đã vote", default=list)
    is_closed: models.BooleanField = models.BooleanField("Đã đóng bình chọn", default=False)
    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="polls_created",
        verbose_name="Người tạo",
    )

    class Meta:
        db_table = "community_polls"
        verbose_name = "Bình chọn cộng đồng"
        verbose_name_plural = "Bình chọn cộng đồng"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.question


class FeedbackEntry(TimeStampedModel):
    """Ý kiến ẩn danh gửi BCN — BCN chỉ thấy nội dung, KHÔNG thấy người gửi."""

    noi_dung: models.TextField = models.TextField("Nội dung góp ý")
    is_anonymous: models.BooleanField = models.BooleanField("Ẩn danh", default=True)
    # Sender lưu để chống spam theo user nhưng KHÔNG expose qua serializer
    sender: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedbacks_sent",
        verbose_name="Người gửi (ẩn với BCN)",
    )

    class Meta:
        db_table = "feedback_entries"
        verbose_name = "Hòm thư góp ý"
        verbose_name_plural = "Hòm thư góp ý"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Góp ý #{self.pk} — {self.noi_dung[:40]}..."
