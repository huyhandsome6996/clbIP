"""
Pagination bắt buộc cho MỌI API danh sách — chống DoS lấy 1 triệu bản ghi (Security §3.3).
"""
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.response import paginated_payload


class StandardPagination(PageNumberPagination):
    """Phân trang chuẩn với page_size tối đa 100 bản ghi."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data) -> Response:
        """Trả về envelope chuẩn có data.items + data.pagination."""
        return Response(paginated_payload(self.page, items=data))
