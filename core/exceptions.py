"""
Custom Exception Handler — chuẩn hóa MỌI lỗi về envelope 4 trường.

Bao phủ:
- BusinessException (hệ nghiệp vụ tự định nghĩa ở apps/common/exceptions.py)
- DRF ValidationError / NotAuthenticated / PermissionDenied / Http404 / Throttled
"""
import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.common.exceptions import BusinessException

logger = logging.getLogger(__name__)


def _flatten_detail(detail) -> any:
    """Gom chi tiết lỗi DRF (dict/list of ErrorDetail) thành cấu trúc JSON thuần."""
    if isinstance(detail, dict):
        return {k: _flatten_detail(v) for k, v in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_flatten_detail(v) for v in detail]
    return str(detail)


def custom_exception_handler(exc, context) -> Response:
    """Chuyển mọi exception thành envelope {success, data, message, errors}."""
    # 1) Lỗi nghiệp vụ tự định nghĩa (BusinessException & con của nó)
    if isinstance(exc, BusinessException):
        return Response(
            {
                "success": False,
                "data": None,
                "message": str(exc.message),
                "errors": exc.errors,
            },
            status=exc.status_code,
        )

    # 2) Ủy quyền cho DRF handler mặc định trước
    response = drf_exception_handler(exc, context)
    if response is not None:
        # Throttle: thêm Retry-After message thân thiện
        if isinstance(exc, drf_exceptions.Throttled):
            response.data = {
                "success": False,
                "data": None,
                "message": (
                    f"Bạn gửi yêu cầu quá nhanh. Vui lòng thử lại sau "
                    f"{int(getattr(exc, 'wait', 60))} giây."
                ),
                "errors": {"detail": "throttled"},
            }
            response["Retry-After"] = str(int(getattr(exc, "wait", 60)))
            return response

        message_map = {
            drf_exceptions.NotAuthenticated: "Bạn chưa đăng nhập. Vui lòng cung cấp JWT token.",
            drf_exceptions.AuthenticationFailed: "Xác thực thất bại. Token không hợp lệ hoặc đã hết hạn.",
            drf_exceptions.PermissionDenied: "Bạn không có quyền thực hiện hành động này.",
            drf_exceptions.NotFound: "Không tìm thấy tài nguyên yêu cầu.",
            drf_exceptions.MethodNotAllowed: "Phương thức HTTP không được hỗ trợ cho endpoint này.",
            drf_exceptions.ParseError: "Dữ liệu gửi lên không đúng định dạng JSON.",
        }
        default_message = "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại các trường thông tin."
        if isinstance(exc, Http404):
            message = "Không tìm thấy tài nguyên yêu cầu."
        elif isinstance(exc, PermissionDenied):
            message = "Bạn không có quyền thực hiện hành động này."
        else:
            message = message_map.get(type(exc), default_message)

        response.data = {
            "success": False,
            "data": None,
            "message": message,
            "errors": _flatten_detail(response.data) if response.data else None,
        }
        return response

    # 3) Lỗi không lường trước → 500 + log đầy đủ stack
    logger.exception("Unhandled exception: %s", exc)
    return Response(
        {
            "success": False,
            "data": None,
            "message": "Lỗi hệ thống. Vui lòng thử lại sau hoặc liên hệ BCN.",
            "errors": None,
        },
        status=500,
    )
