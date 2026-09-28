"""
App: events — ActivityEvent, EventTask (DAG), EventRegistration (Vé QR),
EventBudgetDetail (Dự trù kinh phí), EventCommunication (Truyền thông đa kênh).
"""
from django.conf import settings
from django.db import models
from typing import Optional

from apps.common.models import TimeStampedModel


class ActivityEvent(TimeStampedModel):
    """Hoạt động / sự kiện của CLB — có tọa độ GPS làm tâm điểm danh."""

    class LoaiHoatDong(models.TextChoices):
        WORKSHOP = "WORKSHOP", "Workshop"
        HACKATHON = "HACKATHON", "Hackathon"
        SINH_HOAT_DINH_KY = "SINH_HOAT_DINH_KY", "Sinh hoạt định kỳ"
        TEAMBUILDING = "TEAMBUILDING", "Teambuilding"

    class TrangThai(models.TextChoices):
        PLANNING = "PLANNING", "Đang lên kế hoạch"
        OPEN_REGISTRATION = "OPEN_REGISTRATION", "Mở đăng ký"
        IN_PROGRESS = "IN_PROGRESS", "Đang diễn ra"
        COMPLETED = "COMPLETED", "Đã kết thúc"
        CANCELLED = "CANCELLED", "Đã hủy"

    ma_hd: models.CharField = models.CharField(
        "Mã hoạt động", max_length=20, unique=True, db_index=True
    )
    ten_hoat_dong: models.CharField = models.CharField("Tên hoạt động", max_length=200)
    mo_ta: models.TextField = models.TextField("Mô tả", blank=True, default="")
    loai_hd: models.CharField = models.CharField(
        "Loại hoạt động", max_length=20, choices=LoaiHoatDong.choices
    )

    thoi_gian_bat_dau: models.DateTimeField = models.DateTimeField("Thời gian bắt đầu")
    thoi_gian_ket_thuc: models.DateTimeField = models.DateTimeField("Thời gian kết thúc")

    dia_diem: models.CharField = models.CharField("Địa điểm", max_length=255)

    # Tọa độ GPS tâm điểm danh + bán kính cho phép (Haversine Geofencing)
    vi_do: models.FloatField = models.FloatField("Vĩ độ", null=True, blank=True)
    kinh_do: models.FloatField = models.FloatField("Kinh độ", null=True, blank=True)
    ban_kinh_m: models.FloatField = models.FloatField("Bán kính check-in (m)", default=50)

    tong_kinh_phi_du_tru: models.BigIntegerField = models.BigIntegerField(
        "Tổng kinh phí dự trù (VNĐ)", default=0
    )
    so_luong_toi_da: models.IntegerField = models.IntegerField(
        "Số lượng tham gia tối đa", default=100
    )

    trang_thai: models.CharField = models.CharField(
        "Trạng thái",
        max_length=20,
        choices=TrangThai.choices,
        default=TrangThai.PLANNING,
        db_index=True,
    )
    poster: models.URLField = models.URLField(
        "Poster sự kiện (URL)", max_length=500, blank=True, default=""
    )
    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events_created",
        verbose_name="Người tạo",
    )

    class Meta:
        db_table = "activity_events"
        verbose_name = "Hoạt động sự kiện"
        verbose_name_plural = "Hoạt động sự kiện"
        ordering = ["-thoi_gian_bat_dau"]

    def __str__(self) -> str:
        return f"{self.ma_hd} — {self.ten_hoat_dong}"


class EventBudgetDetail(TimeStampedModel):
    """Hạng mục dự trù kinh phí của sự kiện (Tự động tính tổng tiền)."""

    event: models.ForeignKey = models.ForeignKey(
        ActivityEvent, on_delete=models.CASCADE, related_name="budget_details"
    )
    ten_hang_muc: models.CharField = models.CharField("Hạng mục chi tiêu", max_length=200)
    so_tien: models.BigIntegerField = models.BigIntegerField("Số tiền dự trù (VNĐ)")
    ghi_chu: models.CharField = models.CharField("Ghi chú", max_length=255, blank=True, default="")

    class Meta:
        db_table = "event_budget_details"
        verbose_name = "Hạng mục dự trù kinh phí"
        verbose_name_plural = "Dự trù kinh phí"
        ordering = ["event", "id"]

    def __str__(self) -> str:
        return f"{self.ten_hang_muc} — {self.so_tien:,}₫"


class EventTask(TimeStampedModel):
    """
    Task chuẩn bị sự kiện — hỗ trợ đồ thị DAG (phụ thuộc task trước).
    Chu trình được kiểm tra bằng TaskDependencyEngine (Kahn Topological Sort).
    """

    event: models.ForeignKey = models.ForeignKey(
        ActivityEvent, on_delete=models.CASCADE, related_name="tasks"
    )
    ten_task: models.CharField = models.CharField("Tên công việc", max_length=200)
    nguoi_phu_trach: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks",
        verbose_name="Người phụ trách",
    )
    depends_on: models.ManyToManyField = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="blocks"
    )
    is_completed: models.BooleanField = models.BooleanField("Đã hoàn thành", default=False)
    deadline: models.DateTimeField = models.DateTimeField("Deadline", null=True, blank=True)

    class Meta:
        db_table = "event_tasks"
        verbose_name = "Công việc sự kiện"
        verbose_name_plural = "Công việc sự kiện (DAG)"
        ordering = ["event", "id"]

    def __str__(self) -> str:
        return f"[{self.event.ma_hd}] {self.ten_task}"


class EventRegistration(TimeStampedModel):
    """Đăng ký tham gia sự kiện — sinh mã vé điện tử (QR code do frontend render)."""

    class TrangThai(models.TextChoices):
        REGISTERED = "REGISTERED", "Đã đăng ký"
        APPROVED = "APPROVED", "Đã duyệt"
        CHECKED_IN = "CHECKED_IN", "Đã check-in"
        CANCELLED = "CANCELLED", "Đã hủy"

    event: models.ForeignKey = models.ForeignKey(
        ActivityEvent, on_delete=models.CASCADE, related_name="registrations"
    )
    member: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile", on_delete=models.CASCADE, related_name="event_registrations"
    )
    ma_ve: models.CharField = models.CharField(
        "Mã vé (QR)", max_length=30, unique=True, db_index=True
    )
    trang_thai: models.CharField = models.CharField(
        "Trạng thái vé", max_length=15, choices=TrangThai.choices, default=TrangThai.REGISTERED
    )

    class Meta:
        db_table = "event_registrations"
        verbose_name = "Đăng ký sự kiện"
        verbose_name_plural = "Đăng ký sự kiện"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "member"], name="unique_registration_per_event"
            )
        ]

    def __str__(self) -> str:
        return f"{self.ma_ve} — {self.member.ho_ten} @ {self.event.ten_hoat_dong}"

    @property
    def member_user(self):
        """User sở hữu vé — phục vụ permission chống IDOR."""
        return self.member.user


class EventCommunication(TimeStampedModel):
    """Kế hoạch truyền thông đa kênh (Facebook, TikTok...) theo từng sự kiện."""

    class Kenh(models.TextChoices):
        FACEBOOK = "FACEBOOK", "Facebook"
        TIKTOK = "TIKTOK", "TikTok"
        EMAIL = "EMAIL", "Email"
        WEBSITE = "WEBSITE", "Website"
        OTHER = "OTHER", "Khác"

    class TrangThai(models.TextChoices):
        PENDING = "PENDING", "Chưa đăng"
        PUBLISHED = "PUBLISHED", "Đã đăng"

    event: models.ForeignKey = models.ForeignKey(
        ActivityEvent, on_delete=models.CASCADE, related_name="communications"
    )
    kenh: models.CharField = models.CharField("Kênh truyền thông", max_length=15, choices=Kenh.choices)
    tieu_de: models.CharField = models.CharField("Tiêu đề bài đăng", max_length=200)
    deadline: models.DateTimeField = models.DateTimeField("Deadline đăng bài", null=True, blank=True)
    link_bai_viet: models.URLField = models.URLField("Link bài viết", max_length=500, blank=True, default="")
    trang_thai: models.CharField = models.CharField(
        "Trạng thái", max_length=10, choices=TrangThai.choices, default=TrangThai.PENDING
    )
    nguoi_phu_trach: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="communications",
        verbose_name="Người phụ trách",
    )

    class Meta:
        db_table = "event_communications"
        verbose_name = "Kế hoạch truyền thông"
        verbose_name_plural = "Kế hoạch truyền thông"
        ordering = ["event", "deadline"]
