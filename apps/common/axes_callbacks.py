"""
Axes Lockout Callable — phản hồi khi tài khoản bị khóa do brute-force
(django-axes gọi callable này thay vì trả HTML mặc định).
"""
from django.http import JsonResponse


def axes_lockout_response(request, credentials=None, *args, **kwargs) -> JsonResponse:
    """Trả JSON envelope chuẩn 403 khi bị khóa tài khoản."""
    cooloff = getattr(request, "axes_cooloff_time", None)
    message = (
        "Tài khoản đã bị khóa tạm thời do đăng nhập sai quá 5 lần. "
        "Vui lòng thử lại sau 15 phút."
    )
    if cooloff:
        message = (
            "Tài khoản đã bị khóa tạm thời do đăng nhập sai quá nhiều lần. "
            f"Vui lòng thử lại sau {cooloff}."
        )
    return JsonResponse(
        {
            "success": False,
            "data": None,
            "message": message,
            "errors": {"detail": "account_locked"},
        },
        status=403,
    )
