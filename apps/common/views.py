"""Health check endpoint — Render Health Check Path (/api/health/)."""
from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.services import TrendStatsService
from core.permissions import IsBCNOrAdmin
from apps.common.exceptions import ValidationException


class HealthCheckView(APIView):
    """Kiểm tra trạng thái sống của service + kết nối database."""

    permission_classes = [AllowAny]
    authentication_classes = []  # Không cần JWT cho health check

    @extend_schema(
        tags=["Health"],
        summary="Health check cho Render",
        responses=OpenApiResponse(
            description="Envelope {success, data:{status, database}} — 200 healthy / 503 degraded",
        ),
    )
    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # noqa: BLE001 — health check phải luôn trả 200/503
            db_ok = False

        payload = {
            "success": db_ok,
            "data": {"status": "healthy" if db_ok else "degraded", "database": db_ok},
            "message": "Service is running" if db_ok else "Database unreachable",
            "errors": None,
        }
        return Response(payload, status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


class TrendStatsView(APIView):
    """GET /api/v1/common/stats/trend/?months=6 — trend biểu đồ dashboard."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        tags=["Common"],
        summary="Xu hướng thu/chi theo tháng + chuyên cần theo tuần (BCN)",
        description=(
            "Dữ liệu vẽ biểu đồ dashboard: fund_trend (tổng thu/chi GROUP BY "
            "tháng) và attendance_trend (tỉ lệ chuyên cần GROUP BY tuần, "
            "0..1). Tham số months: số tháng nhìn lại (1-12, mặc định 6)."
        ),
        responses={200: None, 403: None},
    )
    def get(self, request):
        # Parse + validate input ở view (input parsing), logic ở service
        try:
            months = int(request.query_params.get("months", 6))
        except (TypeError, ValueError):
            raise ValidationException("Tham số months phải là số nguyên (1-12).")
        if not 1 <= months <= 12:
            raise ValidationException("Tham số months phải trong khoảng 1-12.")

        data = TrendStatsService.get_trend(months)
        return Response({"success": True, "data": data, "message": "Lấy dữ liệu trend thành công", "errors": None})
