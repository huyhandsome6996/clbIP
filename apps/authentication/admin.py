from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.authentication.models import User


@admin.register(User)
class ClbIpUserAdmin(UserAdmin):
    """Admin User — tìm kiếm theo email/mssv, lọc theo role."""

    list_display = ("email", "mssv", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active")
    search_fields = ("email", "mssv", "username")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Thông tin CLB", {"fields": ("mssv", "role")}),
        ("Quyền", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Thời gian", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "mssv", "role", "password1", "password2")}),
    )
