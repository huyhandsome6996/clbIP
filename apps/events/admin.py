"""
Admin — Events: ActivityEvent, EventBudgetDetail, EventTask (DAG),
EventRegistration (Vé QR), EventCommunication.
"""
from django.contrib import admin

from apps.events.models import (
    ActivityEvent,
    EventBudgetDetail,
    EventCommunication,
    EventRegistration,
    EventTask,
)


class EventBudgetDetailInline(admin.TabularInline):
    """Nhập nhanh hạng mục dự trù kinh phí ngay trong trang sự kiện."""

    model = EventBudgetDetail
    extra = 1
    fields = ("ten_hang_muc", "so_tien", "ghi_chu")


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    """Quản lý vòng đời sự kiện từ PLANNING → COMPLETED."""

    list_display = (
        "ma_hd",
        "ten_hoat_dong",
        "loai_hd",
        "trang_thai",
        "thoi_gian_bat_dau",
        "dia_diem",
        "so_luong_toi_da",
        "tong_kinh_phi_du_tru",
    )
    list_filter = ("loai_hd", "trang_thai")
    search_fields = ("ma_hd", "ten_hoat_dong", "dia_diem")
    readonly_fields = ("ma_hd", "created_at", "updated_at")
    date_hierarchy = "thoi_gian_bat_dau"
    inlines = [EventBudgetDetailInline]


@admin.register(EventTask)
class EventTaskAdmin(admin.ModelAdmin):
    """Task DAG — hiển thị phụ thuộc để nhận biết nhanh deadlock."""

    list_display = ("ten_task", "event", "nguoi_phu_trach", "is_completed", "deadline")
    list_filter = ("is_completed", "event__trang_thai")
    search_fields = ("ten_task", "event__ma_hd", "event__ten_hoat_dong")
    filter_horizontal = ("depends_on",)


@admin.register(EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    """Danh sách vé điện tử của các sự kiện."""

    list_display = ("ma_ve", "event", "member", "trang_thai", "created_at")
    list_filter = ("trang_thai", "event__loai_hd")
    search_fields = ("ma_ve", "member__ho_ten", "event__ma_hd", "event__ten_hoat_dong")
    readonly_fields = ("ma_ve", "created_at", "updated_at")


@admin.register(EventCommunication)
class EventCommunicationAdmin(admin.ModelAdmin):
    """Kế hoạch truyền thông đa kênh theo sự kiện."""

    list_display = ("tieu_de", "event", "kenh", "trang_thai", "deadline", "nguoi_phu_trach")
    list_filter = ("kenh", "trang_thai")
    search_fields = ("tieu_de", "event__ten_hoat_dong")
