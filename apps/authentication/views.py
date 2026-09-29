"""
Views — apps.authentication
Controller mỏng: JWT token (throttle auth_login 5/phút) + /me/.
"""
from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.authentication.serializers import (
    CustomTokenObtainPairSerializer,
    MeSerializer,
)
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
    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
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
