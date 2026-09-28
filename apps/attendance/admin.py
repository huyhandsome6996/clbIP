"""
Admin — Attendance: AttendanceSession & AttendanceRecord.
"""
from django.contrib import admin

from apps.attendance.models import AttendanceRecord, AttendanceSession


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    """Quản lý phiên điểm danh GPS (nonce_secret ẩn — chỉ dùng nội bộ HMAC)."""

    list_display = (
        "ten_phien",
        "event",
        "trang_thai",
        "mo_phien_at",
        "dong_phien_at",
        "hieu_luc_den",
        "ban_kinh_m",
    )
    list_filter = ("trang_thai",)
    search_fields = ("ten_phien", "event__ten_hoat_dong")
    readonly_fields = ("mo_phien_at", "created_at", "updated_at")
    exclude = ("nonce_secret",)  # không hiển thị secret trong admin


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    """Bản ghi điểm danh — kèm cờ anti-cheat và BCN override."""

    list_display = (
        "member",
        "session",
        "trang_thai",
        "checked_in_at",
        "khoang_cach_m",
        "xp_awarded",
        "is_suspicious",
        "overridden_by",
    )
    list_filter = ("trang_thai", "is_suspicious", "session__trang_thai")
    search_fields = ("member__ho_ten", "session__ten_phien", "device_id")
    readonly_fields = ("created_at", "updated_at")
