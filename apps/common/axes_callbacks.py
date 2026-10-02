"""
Axes Lockout Callable — phản hồi khi tài khoản bị khóa do brute-force
(django-axes gọi callable này thay vì trả HTML mặc định).
"""
import json
from typing import Any, Optional

from django.http import JsonResponse


def lockout_payload(request: Any = None, credentials: Optional[dict] = None) -> dict:
    """
    Envelope 403 chuẩn khi bị khóa tài khoản.

    Tách riêng payload để tái sử dụng ở 2 nơi:
    - ``axes_lockout_response``: JsonResponse cho django-axes (callable của
      AXES_LOCKOUT_CALLABLE / AxesMiddleware).
    - ``CustomTokenObtainPairView``: DRF Response cho luồng login JWT —
      response đi qua renderer chuẩn của DRF, test client đọc được ``res.data``.
    """
    cooloff = getattr(request, "axes_cooloff_time", None) if request is not None else None
    message = (
        "Tài khoản đã bị khóa tạm thời do đăng nhập sai quá 5 lần. "
        "Vui lòng thử lại sau 15 phút."
    )
    if cooloff:
        message = (
            "Tài khoản đã bị khóa tạm thời do đăng nhập sai quá nhiều lần. "
            f"Vui lòng thử lại sau {cooloff}."
        )
    return {
        "success": False,
        "data": None,
        "message": message,
        "errors": {"detail": "account_locked"},
    }


def axes_lockout_response(request, credentials=None, *args, **kwargs) -> JsonResponse:
    """Trả JSON envelope chuẩn 403 khi bị khóa tài khoản (callable của axes)."""
    return JsonResponse(lockout_payload(request, credentials), status=403)


def parse_lockout_json(response: JsonResponse) -> dict:
    """Đọc lại payload từ một JsonResponse (tiện test/debug)."""
    return json.loads(response.content)
