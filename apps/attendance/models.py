"""
App: attendance — AttendanceSession (phiên điểm danh GPS) & AttendanceRecord.
Anti-Cheat: mock location, timestamp skew, device fingerprint, teleportation,
dynamic nonce xoay 60 giây.
"""
from django.db import models

from apps.common.models import TimeStampedModel


class AttendanceSession(TimeStampedModel):
    """Phiên điểm danh GPS — BCN mở phiên tại địa điểm, thiết lập bán kính & hiệu lực."""

    class TrangThai(models.TextChoices):
        OPEN = "OPEN", "Đang mở"
        CLOSED = "CLOSED", "Đã đóng"

    event: models.ForeignKey = models.ForeignKey(
        "events.ActivityEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_sessions",
        verbose_name="Sự kiện liên quan",
    )
    ten_phien: models.CharField = models.CharField("Tên phiên điểm danh", max_length=200)

    # Tọa độ tâm + bán kính cho phép check-in (Haversine Geofencing)
    vi_do: models.FloatField = models.FloatField("Vĩ độ tâm")
    kinh_do: models.FloatField = models.FloatField("Kinh độ tâm")
    ban_kinh_m: models.FloatField = models.FloatField("Bán kính cho phép (m)", default=50)

    mo_phien_at: models.DateTimeField = models.DateTimeField("Thời điểm mở phiên", auto_now_add=True)
    dong_phien_at: models.DateTimeField = models.DateTimeField(
        "Thời điểm đóng phiên", null=True, blank=True
    )
    hieu_luc_den: models.DateTimeField = models.DateTimeField(
        "Hiệu lực check-in đến", null=True, blank=True
    )
    trang_thai: models.CharField = models.CharField(
        "Trạng thái phiên",
        max_length=10,
        choices=TrangThai.choices,
        default=TrangThai.OPEN,
        db_index=True,
    )

    # Secret dùng để sinh Dynamic Nonce xoay 60s (HMAC) — hiển thị trên máy chiếu
    nonce_secret: models.CharField = models.CharField(
        "Secret sinh nonce", max_length=64, blank=True, default=""
    )

    class Meta:
        db_table = "attendance_sessions"
        verbose_name = "Phiên điểm danh"
        verbose_name_plural = "Phiên điểm danh"
        ordering = ["-mo_phien_at"]

    def __str__(self) -> str:
        return f"{self.ten_phien} ({self.get_trang_thai_display()})"


class AttendanceRecord(TimeStampedModel):
    """Bản ghi điểm danh của từng thành viên trong một phiên."""

    class TrangThaiDiemDanh(models.TextChoices):
        CO_MAT = "CO_MAT", "Có mặt"
        VANG = "VANG", "Vắng"
        CO_PHEP = "CO_PHEP", "Có phép"
        DI_MUON = "DI_MUON", "Đi muộn"

    session: models.ForeignKey = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="records"
    )
    member: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile", on_delete=models.CASCADE, related_name="attendance_records"
    )

    trang_thai: models.CharField = models.CharField(
        "Trạng thái",
        max_length=10,
        choices=TrangThaiDiemDanh.choices,
        default=TrangThaiDiemDanh.VANG,
        db_index=True,
    )

    # Kết quả GPS thực tế
    khoang_cach_m: models.FloatField = models.FloatField(
        "Khoảng cách tới tâm (m)", null=True, blank=True
    )
    vi_do: models.FloatField = models.FloatField("Vĩ độ thiết bị", null=True, blank=True)
    kinh_do: models.FloatField = models.FloatField("Kinh độ thiết bị", null=True, blank=True)
    checked_in_at: models.DateTimeField = models.DateTimeField(
        "Giờ check-in thực tế", null=True, blank=True
    )

    # Anti-Cheat
    device_id: models.CharField = models.CharField(
        "Device fingerprint (hash UA + screen + hw)", max_length=128, blank=True, default=""
    )
    is_suspicious: models.BooleanField = models.BooleanField(
        "Cờ gian lận SUSPICIOUS_FRAUD", default=False
    )
    xp_awarded: models.IntegerField = models.IntegerField("XP được thưởng", default=0)
    overridden_by: models.ForeignKey = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_overrides",
        verbose_name="BCN override thủ công",
    )

    class Meta:
        db_table = "attendance_records"
        verbose_name = "Bản ghi điểm danh"
        verbose_name_plural = "Bản ghi điểm danh"
        ordering = ["session", "member__ho_ten"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "member"], name="unique_record_per_session"
            )
        ]

    def __str__(self) -> str:
        return f"{self.member.ho_ten} — {self.get_trang_thai_display()} @ {self.session.ten_phien}"
