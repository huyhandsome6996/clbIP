"""
Django Admin — apps.funds
=========================
Sổ quỹ là dữ liệu tài chính nhạy cảm: chỉ ĐỌC các trường do hệ thống sinh
(ma_phieu, so_du_sau, is_locked), tìm kiếm nhanh theo mã phiếu/người thực hiện.
"""
from django.contrib import admin

from apps.funds.models import FundPeriodLock, FundTransaction


@admin.register(FundTransaction)
class FundTransactionAdmin(admin.ModelAdmin):
    """Quản trị Sổ quỹ — theo dõi thu/chi và trạng thái khóa kỳ."""

    list_display = (
        "ma_phieu",
        "loai_gd",
        "so_tien",
        "so_du_sau",
        "nguoi_thuc_hien",
        "hinh_thuc",
        "ngay_gd",
        "is_locked",
        "created_by",
    )
    list_filter = ("loai_gd", "hinh_thuc", "is_locked")
    search_fields = ("ma_phieu", "nguoi_thuc_hien", "ghi_chu")
    date_hierarchy = "ngay_gd"
    ordering = ("-ngay_gd", "-id")
    readonly_fields = ("ma_phieu", "so_du_sau", "is_locked", "created_at", "updated_at")
    list_per_page = 50


@admin.register(FundPeriodLock)
class FundPeriodLockAdmin(admin.ModelAdmin):
    """Quản trị khóa sổ kỳ."""

    list_display = ("ten_ky", "tu_ngay", "den_ngay", "locked_by", "locked_at")
    search_fields = ("ten_ky", "ghi_chu")
    list_filter = ("tu_ngay",)
    ordering = ("-tu_ngay",)
