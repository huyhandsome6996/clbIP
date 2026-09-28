"""
Envelope Response chuẩn cho toàn bộ API — theo CLBIP_Master_Coding_Prompt.md §5.

Mọi JSON response phải có dạng:
    {
        "success": true,
        "data": { ... },
        "message": "Thông báo thân thiện",
        "errors": null
    }
"""
from typing import Any, Optional

from rest_framework import status
from rest_framework.response import Response

ENVELOPE_KEYS = ("success", "data", "message", "errors")


def _envelope(
    success: bool,
    data: Any = None,
    message: str = "",
    errors: Any = None,
) -> dict:
    """Đóng gói payload vào envelope chuẩn 4 trường."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors,
    }


def ok(
    data: Any = None,
    message: str = "Thành công",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """Response thành công chuẩn hóa."""
    return Response(_envelope(True, data, message, None), status=status_code)


def created(data: Any = None, message: str = "Tạo mới thành công") -> Response:
    """Response 201 cho thao tác tạo mới."""
    return Response(_envelope(True, data, message, None), status=status.HTTP_201_CREATED)


def fail(
    message: str = "Yêu cầu không hợp lệ",
    errors: Any = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """Response lỗi chuẩn hóa."""
    return Response(_envelope(False, None, message, errors), status=status_code)


def paginated_payload(page_result, message: str = "Thành công") -> dict:
    """
    Chuyển kết quả paginate của DRF thành envelope có data gồm:
        data = { "items": [...], "pagination": {page, page_size, total_pages, total_items} }
    """
    return _envelope(
        True,
        data={
            "items": list(page_result),
            "pagination": {
                "page": page_result.page.number,
                "page_size": page_result.paginator.page_size,
                "total_pages": page_result.paginator.num_pages,
                "total_items": page_result.paginator.count,
            },
        },
        message=message,
    )
