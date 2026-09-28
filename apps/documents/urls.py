"""
URLs — apps.documents (mounted tại /api/v1/documents/)
=======================================================
LƯU Ý: `search/` PHẢI đứng trước `<int:pk>/` để không bị nuốt bởi converter.
"""
from django.urls import path

from apps.documents.views import (
    DocumentDetailView,
    DocumentDownloadView,
    DocumentListCreateView,
    DocumentSearchView,
)

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document_list"),
    # ĐẶT TRƯỚC <int:pk>/ !
    path("search/", DocumentSearchView.as_view(), name="document_search"),
    path("<int:pk>/", DocumentDetailView.as_view(), name="document_detail"),
    path("<int:pk>/download/", DocumentDownloadView.as_view(), name="document_download"),
]
