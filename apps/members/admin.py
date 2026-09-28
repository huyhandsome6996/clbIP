from django.contrib import admin

from apps.members.models import BoardMember, MemberProfile


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = ("ho_ten", "mssv_prop", "lop", "xp_points", "current_level", "streak_count", "trang_thai_hd")
    list_filter = ("trang_thai_hd", "lop")
    search_fields = ("ho_ten", "user__mssv", "user__email")
    readonly_fields = ("xp_points", "current_level", "streak_count", "last_attendance_date")

    @admin.display(description="MSSV")
    def mssv_prop(self, obj):
        return obj.user.mssv


@admin.register(BoardMember)
class BoardMemberAdmin(admin.ModelAdmin):
    list_display = ("member", "chuc_vu", "ban_phu_trach", "nhiem_ky")
    list_filter = ("nhiem_ky", "chuc_vu", "ban_phu_trach")
