"""Health check endpoint — Render Health Check Path (/api/health/)."""
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Kiểm tra trạng thái sống của service + kết nối database."""

    permission_classes = [AllowAny]
    authentication_classes = []  # Không cần JWT cho health check

    @extend_schema(tags=["Health"], summary="Health check cho Render")
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
