"""
Django Admin — apps.posts.
"""
from django.contrib import admin

from apps.posts.models import CommunityPoll, FeedbackEntry, Post, PostAuditLog


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Quản trị bảng tin — theo dõi ghim + soft delete."""

    list_display = ("tieu_de", "is_pinned", "is_deleted", "created_by", "created_at")
    list_filter = ("is_pinned", "is_deleted")
    search_fields = ("tieu_de", "noi_dung")
    readonly_fields = ("created_by", "created_at", "updated_at")


@admin.register(PostAuditLog)
class PostAuditLogAdmin(admin.ModelAdmin):
    """Audit trail — chỉ ĐỌC, không cho sửa/xóa trực tiếp để bảo toàn bằng chứng."""

    list_display = ("post", "action", "performed_by", "timestamp")
    list_filter = ("action",)
    search_fields = ("post__tieu_de", "chi_tiet")
    readonly_fields = ("post", "action", "performed_by", "timestamp", "chi_tiet")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CommunityPoll)
class CommunityPollAdmin(admin.ModelAdmin):
    """Quản trị bình chọn — xem kết quả, đóng/mở bình chọn."""

    list_display = ("question", "is_closed", "total_votes_display", "created_by", "created_at")
    list_filter = ("is_closed",)
    readonly_fields = ("votes", "voted_user_ids", "created_by", "created_at", "updated_at")

    @admin.display(description="Tổng phiếu")
    def total_votes_display(self, obj: CommunityPoll) -> int:
        """Tổng phiếu = sum(votes.values())."""
        return sum((obj.votes or {}).values())


@admin.register(FeedbackEntry)
class FeedbackEntryAdmin(admin.ModelAdmin):
    """
    Hòm thư góp ý — sender KHÔNG hiển thị trong danh sách để giữ đúng
    lời hứa ẩn danh (chỉ tra cứu khi có vi phạm pháp lý qua superuser).
    """

    list_display = ("id", "noi_dung_ngan", "is_anonymous", "created_at")
    list_filter = ("is_anonymous",)
    readonly_fields = ("noi_dung", "is_anonymous", "sender", "created_at", "updated_at")

    @admin.display(description="Nội dung")
    def noi_dung_ngan(self, obj: FeedbackEntry) -> str:
        """Trích 60 ký tự nội dung góp ý."""
        return obj.noi_dung[:60]
