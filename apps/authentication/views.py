"""
Views — apps.authentication
Controller mỏng: JWT token (throttle auth_login 5/phút) + /me/.
"""
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.authentication.serializers import (
    CustomTokenObtainPairSerializer,
    MeSerializer,
)
from apps.common.axes_callbacks import lockout_payload
from apps.common.throttles import AuthLoginRateThrottle
from core.response import ok


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/v1/auth/token/ — đăng nhập, trả access + refresh + user info."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthLoginRateThrottle]
    # BẮT BUỘC: ScopedRateThrottle đọc scope từ VIEW — thiếu dòng này thì
    # rate 5/phút bị ÂM THẦM VÔ HIỆU (phát hiện khi test QA-Audit 2b)
    throttle_scope = "auth_login"

    @extend_schema(
        tags=["Authentication"],
        summary="Đăng nhập lấy JWT",
        description=(
            "Đăng nhập bằng email + mật khẩu. Trả về access token (30 phút), "
            "refresh token (7 ngày) và thông tin user/role để điều hướng frontend. "
            "Rate limit: 5 lần/phút. Sai quá 5 lần → tài khoản khóa 15 phút (django-axes)."
        ),
        request=CustomTokenObtainPairSerializer,
        responses={200: None, 401: None, 403: None, 429: None},
    )
    def post(self, request: Any, *args: Any, **kwargs: Any) -> HttpResponse:
        # django-axes + DRF/simplejwt (QA-Audit TASK 1 P0):
        # AxesStandaloneBackend chặn đăng nhập khi bị khóa bằng cách raise
        # PermissionDenied BÊN TRONG django.contrib.auth.authenticate() — lỗi
        # này bị authenticate() nuốt rồi bắn signal user_login_failed, sau đó
        # simplejwt chỉ thấy user=None và trả 401 chung chung. Cờ
        # `axes_locked_out` cũng nằm trên DRF Request wrapper (đối tượng
        # được truyền vào authenticate()), còn AxesMiddleware đọc cờ trên
        # HttpRequest gốc → lockout envelope 403 không bao giờ được trả.
        #
        # Giải pháp: kiểm tra trạng thái khóa TRƯỚC khi authenticate.
        # - Đã bị khóa sẵn (đủ AXES_FAILURE_LIMIT từ các lần thử trước)
        #   → trả ngay lockout envelope 403, không đụng đến JWT.
        # - Chưa khóa → để luồng JWT chạy bình thường. Lần thử THỨ 5 (lần
        #   chạm giới hạn) vẫn là 401 "sai mật khẩu" đúng chuẩn django-axes:
        #   lượt bị khóa chỉ có hiệu lực từ lần thử kế tiếp (thứ 6). Nếu kiểm
        #   tra SAU khi authenticate (is_locked query trực tiếp) thì lần thứ 5
        #   đã thấy 5/5 failure và trả nhầm 403 — lệch chuẩn & lệch test.
        if self._is_locked_out(request):
            # DRF Response (không phải JsonResponse của axes callable) để
            # response đi qua renderer chuẩn của DRF — envelope giữ nguyên.
            return Response(
                lockout_payload(getattr(request, "_request", request)),
                status=403,
            )

        response = super().post(request, *args, **kwargs)
        if response.status_code == 200 and isinstance(response.data, dict):
            return ok(
                data={
                    "access": response.data.get("access"),
                    "refresh": response.data.get("refresh"),
                    "user": response.data.get("user"),
                },
                message="Đăng nhập thành công",
            )
        return response

    @staticmethod
    def _is_locked_out(request: Any) -> bool:
        """Tài khoản/IP đã bị django-axes khóa TRƯỚC lần thử này?

        Chỉ truy vấn khi AXES_ENABLED (mặc định False khi TESTING) — tránh
        thêm query DB vô ích cho toàn bộ test suite khác. Mọi lỗi axes →
        False: axes hỏng không được làm hỏng luồng đăng nhập.
        """
        if not getattr(settings, "AXES_ENABLED", False):
            return False
        try:
            from axes.handlers.proxy import AxesProxyHandler  # noqa: PLC0415

            return AxesProxyHandler.is_locked(
                request, credentials=dict(getattr(request, "data", {}) or {})
            )
        except Exception:  # noqa: BLE001 — axes lỗi không được làm hỏng luồng đăng nhập
            return False


class MeView(APIView):
    """GET /api/v1/auth/me/ — thông tin người dùng hiện tại (+ hồ sơ thành viên)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication"],
        summary="Thông tin user hiện tại",
        responses={200: MeSerializer},
    )
    def get(self, request) -> Response:
        serializer = MeSerializer(request.user)
        return ok(data=serializer.data, message="Lấy thông tin thành công")
