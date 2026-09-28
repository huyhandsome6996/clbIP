"""
Django Admin — apps.documents.
"""
from django.contrib import admin

from apps.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Quản trị Kho tài liệu — hiển thị gọn, lọc nhanh theo nhóm/định dạng."""

    list_display = ("tieu_de", "nhom", "file_type", "file_size_mb", "luot_tai", "uploaded_by", "created_at")
    list_filter = ("nhom", "file_type")
    search_fields = ("tieu_de", "tags", "mo_ta")
    readonly_fields = ("file_type", "file_size", "luot_tai", "uploaded_by", "created_at", "updated_at")
    ordering = ("-created_at",)

    @admin.display(description="Kích thước (MB)")
    def file_size_mb(self, obj: Document) -> str:
        """Hiển thị kích thước tệp theo MB cho dễ đọc."""
        return f"{obj.file_size / (1024 * 1024):.2f}" if obj.file_size else "0.00"
