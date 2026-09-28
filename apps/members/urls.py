"""URLs — Members API (mount tại /api/v1/members/)."""
from django.urls import path

from apps.members.views import (
    BoardMemberListCreateView,
    MemberDetailView,
    MemberExportExcelView,
    MemberImportExcelView,
    MemberListCreateView,
    MemberSearchView,
    Profile360View,
)

urlpatterns = [
    path("", MemberListCreateView.as_view(), name="member_list"),
    path("import-excel/", MemberImportExcelView.as_view(), name="member_import_excel"),
    path("export-excel/", MemberExportExcelView.as_view(), name="member_export_excel"),
    path("search/", MemberSearchView.as_view(), name="member_search"),
    path("board/", BoardMemberListCreateView.as_view(), name="board_list"),
    path("<int:pk>/", MemberDetailView.as_view(), name="member_detail"),
    path("<int:pk>/profile360/", Profile360View.as_view(), name="member_profile360"),
]
