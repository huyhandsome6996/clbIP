"""
App: members — MemberProfile (Hồ sơ thành viên + XP + Level + Streak)
và BoardMember (Cơ cấu Ban Chủ Nhiệm theo nhiệm kỳ). Theo ERD.
"""
from django.conf import settings
from django.db import models
from typing import Optional

from apps.common.models import TimeStampedModel


class MemberProfile(TimeStampedModel):
    """Hồ sơ 360° của thành viên CLB — gắn 1-1 với User."""

    class GioiTinh(models.TextChoices):
        NAM = "NAM", "Nam"
        NU = "NU", "Nữ"
        KHAC = "KHAC", "Khác"

    class TrangThai(models.TextChoices):
        ACTIVE = "ACTIVE", "Đang hoạt động"
        INACTIVE = "INACTIVE", "Ngừng hoạt động"
        LEAVE = "LEAVE", "Bảo lưu"

    user: models.OneToOneField = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        verbose_name="Tài khoản",
    )

    # ---- Thông tin cá nhân ----
    ho_ten: models.CharField = models.CharField("Họ và tên", max_length=150)
    ngay_sinh: models.DateField = models.DateField("Ngày sinh", null=True, blank=True)
    gioi_tinh: models.CharField = models.CharField(
        "Giới tính", max_length=5, choices=GioiTinh.choices, blank=True, default=""
    )
    lop: models.CharField = models.CharField("Lớp", max_length=50, blank=True, default="")
    sdt: models.CharField = models.CharField(
        "Số điện thoại", max_length=15, blank=True, default=""
    )
    avatar: models.URLField = models.URLField(
        "Ảnh đại diện (URL)", max_length=500, blank=True, default=""
    )

    # ---- Gamification (Server-Authoritative — client TUYỆT ĐỐI không gửi XP) ----
    xp_points: models.IntegerField = models.IntegerField("Điểm XP", default=0, db_index=True)
    current_level: models.IntegerField = models.IntegerField("Cấp độ hiện tại (1-10)", default=1)
    streak_count: models.IntegerField = models.IntegerField(
        "Chuỗi chuyên cần 🔥", default=0
    )
    last_attendance_date: models.DateField = models.DateField(
        "Lần điểm danh gần nhất", null=True, blank=True
    )

    # ---- Trạng thái thành viên ----
    trang_thai_hd: models.CharField = models.CharField(
        "Trạng thái hoạt động",
        max_length=10,
        choices=TrangThai.choices,
        default=TrangThai.ACTIVE,
        db_index=True,
    )

    class Meta:
        db_table = "member_profiles"
        verbose_name = "Hồ sơ thành viên"
        verbose_name_plural = "Hồ sơ thành viên"
        ordering = ["-xp_points", "ho_ten"]

    def __str__(self) -> str:
        return f"{self.ho_ten} ({self.user.mssv or self.user.email})"

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def mssv(self) -> Optional[str]:
        return self.user.mssv


class BoardMember(TimeStampedModel):
    """Thành viên Ban Chủ Nhiệm theo nhiệm kỳ (dùng cho sơ đồ tổ chức Org Chart)."""

    class ChucVu(models.TextChoices):
        CHU_NHIEM = "CHU_NHIEM", "Chủ nhiệm"
        PHO_CHU_NHIEM = "PHO_CHU_NHIEM", "Phó chủ nhiệm"
        TRUONG_BAN = "TRUONG_BAN", "Trưởng ban"
        PHO_BAN = "PHO_BAN", "Phó ban"

    class BanPhuTrach(models.TextChoices):
        HOC_THUAT = "HOC_THUAT", "Ban Học thuật"
        TRUYEN_THONG = "TRUYEN_THONG", "Ban Truyền thông"
        SU_KIEN = "SU_KIEN", "Ban Sự kiện"
        TAI_CHINH = "TAI_CHINH", "Ban Tài chính"

    member: models.ForeignKey = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name="board_positions",
        verbose_name="Thành viên",
    )
    nhiem_ky: models.CharField = models.CharField(
        "Nhiệm kỳ", max_length=20, default="2025-2026"
    )
    chuc_vu: models.CharField = models.CharField(
        "Chức vụ", max_length=20, choices=ChucVu.choices
    )
    ban_phu_trach: models.CharField = models.CharField(
        "Ban phụ trách", max_length=20, choices=BanPhuTrach.choices
    )

    class Meta:
        db_table = "board_members"
        verbose_name = "Ban Chủ Nhiệm"
        verbose_name_plural = "Ban Chủ Nhiệm"
        ordering = ["nhiem_ky", "chuc_vu"]
        constraints = [
            models.UniqueConstraint(
                fields=["member", "nhiem_ky"],
                name="unique_member_per_nhiem_ky",
            )
        ]

    def __str__(self) -> str:
        return f"{self.member.ho_ten} — {self.get_chuc_vu_display()} ({self.nhiem_ky})"
