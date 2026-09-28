"""
Django Admin — apps.gamification
================================
Quản trị huy hiệu, bộ sưu tập và sổ XP (kiểm tra idempotency key khi điều tra gian lận).
"""
from django.contrib import admin

from apps.gamification.models import Badge, MemberBadge, XpLedger


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    """Quản trị định nghĩa huy hiệu."""

    list_display = ("ma_badge", "ten_badge", "icon", "mo_ta")
    search_fields = ("ma_badge", "ten_badge")


@admin.register(MemberBadge)
class MemberBadgeAdmin(admin.ModelAdmin):
    """Bộ sưu tập huy hiệu của thành viên."""

    list_display = ("member", "badge", "awarded_at")
    list_filter = ("badge",)
    search_fields = ("member__ho_ten", "badge__ten_badge")
    list_select_related = ("member", "badge")


@admin.register(XpLedger)
class XpLedgerAdmin(admin.ModelAdmin):
    """Sổ cái XP — tra cứu idempotency key phục vụ điều tra gian lận XP."""

    list_display = ("member", "amount", "reason", "source", "idempotency_key", "created_at")
    list_filter = ("source",)
    search_fields = ("member__ho_ten", "reason", "idempotency_key")
    list_select_related = ("member",)
    date_hierarchy = "created_at"
    list_per_page = 50
