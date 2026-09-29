"""
View Layer (Controller) — apps.funds
====================================
View MỎNG: nhận HTTP request → gọi `FundService` → trả envelope chuẩn
{success, data, message, errors} qua `core.response.ok/created`.

Phân quyền: TOÀN BỘ quỹ là chức năng BCN (`IsBCNOrAdmin` — Security RBAC).

Lưu ý kiến trúc: hàm `_paginated_envelope` tự dựng envelope phân trang cùng shape
với `core.response.paginated_payload` (data.items + data.pagination) — do helper
trong core hiện kỳ vọng object có `.page.*` không khớp với Django `Page`
(latent bug, ngoài phạm vi được phép sửa của app này). Không đụng core/.
"""
from typing import Any, Optional

from django.core.paginator import Page
from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import ValidationException
from apps.funds.repositories import DjangoFundRepository
from apps.funds.services import FundService
from apps.funds.serializers import (
    FundPeriodLockSerializer,
    FundTransactionCreateSerializer,
    FundTransactionSerializer,
)
from core.pagination import StandardPagination
from core.permissions import IsBCNOrAdmin
from core.response import created, ok

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _paginated_envelope(
    page: Page, serialized_items: list, message: str
) -> dict[str, Any]:
    """
    Dựng envelope phân trang chuẩn: data.items + data.pagination.
    (Shape tương thích 100% với hợp đồng của core.response.paginated_payload.)
    """
    return {
        "success": True,
        "data": {
            "items": serialized_items,
            "pagination": {
                "page": page.number,
                "page_size": page.paginator.per_page,
                "total_pages": page.paginator.num_pages,
                "total_items": page.paginator.count,
            },
        },
        "message": message,
        "errors": None,
    }


# ======================================================================
# Sổ quỹ: GET danh sách (lọc/sắp) + POST lập phiếu thu/chi
# ======================================================================
class FundTransactionListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/funds/  — danh sách giao dịch (phân trang bắt buộc).
    POST /api/v1/funds/ — lập phiếu thu/chi (BCN) qua FundService (atomic + lock).
    """

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]
    pagination_class = StandardPagination

    def get_serializer_class(self):
        """POST dùng serializer ghi; GET dùng serializer đọc."""
        if self.request.method == "POST":
            return FundTransactionCreateSerializer
        return FundTransactionSerializer

    def get_queryset(self):
        """Ủy quyền 100% lọc/sắp cho Service (sort whitelist chống SQLi)."""
        qp = self.request.query_params
        return FundService.list_transactions(
            loai_gd=qp.get("loai_gd"),
            from_date=qp.get("from_date"),
            to_date=qp.get("to_date"),
            sort=qp.get("sort"),
        )

    @extend_schema(
        tags=["Funds"],
        summary="Danh sách giao dịch quỹ",
        description="Sổ quỹ thu/chi có phân trang, lọc theo loại/khoảng ngày, sort whitelist.",
        parameters=[
            OpenApiParameter("loai_gd", str, OpenApiParameter.QUERY, enum=["THU", "CHI"]),
            OpenApiParameter("from_date", str, OpenApiParameter.QUERY, description="YYYY-MM-DD"),
            OpenApiParameter("to_date", str, OpenApiParameter.QUERY, description="YYYY-MM-DD"),
            OpenApiParameter(
                "sort", str, OpenApiParameter.QUERY,
                enum=["ngay_gd", "-ngay_gd", "so_tien", "-so_tien"],
            ),
        ],
        responses={200: OpenApiResponse(description="Envelope items + pagination")},
    )
    def get(self, request, *args, **kwargs) -> Response:
        """GET danh sách — envelope phân trang chuẩn."""
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs) -> Response:
        """Ghi đè list để trả envelope {success, data:{items,pagination}}."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(_paginated_envelope(self.paginator.page, serializer.data, "Lấy sổ quỹ thành công"))
        serializer = self.get_serializer(queryset, many=True)
        return ok(
            data={"items": serializer.data, "pagination": None},
            message="Lấy sổ quỹ thành công",
        )

    @extend_schema(
        tags=["Funds"],
        summary="Lập phiếu thu/chi",
        description=(
            "Ghi giao dịch mới vào sổ quỹ. Chạy atomic transaction với "
            "pessimistic locking (select_for_update) + kiểm chứng bất biến số dư. "
            "Client KHÔNG được gửi ma_phieu/so_du_sau."
        ),
        request=FundTransactionCreateSerializer,
        responses={
            201: FundTransactionSerializer,
            400: OpenApiResponse(description="Số dư không đủ / dữ liệu không hợp lệ"),
            403: OpenApiResponse(description="Chỉ BCN/ADMIN được lập phiếu"),
            409: OpenApiResponse(description="Ngày giao dịch thuộc kỳ đã khóa sổ"),
        },
    )
    def post(self, request, *args, **kwargs) -> Response:
        """POST lập phiếu — 201 envelope, message 'Lập phiếu thành công'."""
        return self.create(request, *args, **kwargs)

    def create(self, request, *args, **kwargs) -> Response:
        """Validate payload → Service → envelope 201 (mới) / 200 (idempotent replay).

        QA-Audit nhóm 3: nhận Idempotency-Key từ header (ưu tiên) hoặc trường
        body — client retry/submit 2 lần vẫn chỉ tạo MỘT giao dịch.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated: dict = serializer.validated_data

        # Header "Idempotency-Key" ưu tiên hơn trường body (chuẩn phổ biến)
        idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if len(idem_key) > 64:
            raise ValidationException(
                "Header Idempotency-Key không được vượt quá 64 ký tự.",
                errors={"idempotency_key": "Tối đa 64 ký tự."},
            )
        if not idem_key:
            idem_key = (validated.get("idempotency_key") or "").strip() or None

        instance, replayed = self.perform_create(serializer, idem_key)
        output = FundTransactionSerializer(instance, context=self.get_serializer_context())
        if replayed:
            # HTTP 200 — trả lại giao dịch cũ, KHÔNG ghi thêm (theo audit)
            return ok(
                data=output.data,
                message=f"Giao dịch đã tồn tại (Idempotency-Key) — trả lại phiếu {instance.ma_phieu}.",
            )
        return created(data=output.data, message="Lập phiếu thành công")

    def perform_create(self, serializer, idempotency_key: Optional[str] = None) -> Any:
        """Ủy quyền ghi sổ cho Service — view không chứa business logic."""
        validated: dict = serializer.validated_data
        return FundService.execute_transaction_idempotent(
            loai_gd=validated["loai_gd"],
            so_tien=validated["so_tien"],
            nguoi_thuc_hien=validated["nguoi_thuc_hien"],
            hinh_thuc=validated.get("hinh_thuc", "TIEN_MAT"),
            ngay_gd=validated.get("ngay_gd"),
            ghi_chu=validated.get("ghi_chu", ""),
            created_by=self.request.user,
            event=validated.get("event"),
            idempotency_key=idempotency_key,
        )


# ======================================================================
# Thống kê quỹ
# ======================================================================
class FundStatsView(generics.RetrieveAPIView):
    """GET /api/v1/funds/stats/ — tổng thu, tổng chi, số dư, cờ quỹ thấp."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]

    @extend_schema(
        tags=["Funds"],
        summary="Thống kê quỹ CLB",
        description=(
            "Trả về total_income / total_expense / balance (đảm bảo bất biến "
            "Σ thu − Σ chi = số dư) và low_balance=True khi số dư < 200.000đ."
        ),
        responses={200: OpenApiResponse(description="Stats dict trong envelope")},
    )
    def get(self, request, *args, **kwargs) -> Response:
        """Gọi Service.get_stats() — không logic gì thêm ở view."""
        return ok(data=FundService.get_stats(), message="Lấy thống kê quỹ thành công")


# ======================================================================
# Khóa sổ kỳ
# ======================================================================
class LockPeriodView(generics.GenericAPIView):
    """POST /api/v1/funds/lock-period/ — khóa sổ một kỳ (đóng băng lịch sử)."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]
    serializer_class = FundPeriodLockSerializer

    @extend_schema(
        tags=["Funds"],
        summary="Khóa sổ kỳ",
        description=(
            "Tạo kỳ khóa sổ [tu_ngay, den_ngay] và đóng băng (is_locked=True) "
            "mọi giao dịch trong khoảng. Sau khi khóa, không thể phát sinh "
            "giao dịch mới trong kỳ (409 PeriodLockedException)."
        ),
        request=FundPeriodLockSerializer,
        responses={
            200: FundPeriodLockSerializer,
            400: OpenApiResponse(description="tu_ngay > den_ngay"),
            409: OpenApiResponse(description="Tên kỳ đã tồn tại"),
        },
    )
    def post(self, request, *args, **kwargs) -> Response:
        """Validate → FundService.lock_period → envelope 200."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated: dict = serializer.validated_data
        lock = FundService.lock_period(
            ten_ky=validated["ten_ky"],
            tu_ngay=validated["tu_ngay"],
            den_ngay=validated["den_ngay"],
            locked_by=request.user,
            ghi_chu=validated.get("ghi_chu", ""),
        )
        return ok(
            data=FundPeriodLockSerializer(lock).data,
            message="Khóa sổ kỳ thành công",
        )


# ======================================================================
# Danh sách kỳ đã khóa
# ======================================================================
class FundPeriodLockListView(generics.ListAPIView):
    """GET /api/v1/funds/locks/ — danh sách các kỳ đã khóa sổ (phân trang)."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]
    serializer_class = FundPeriodLockSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        """Ủy quyền truy vấn cho Repository (Repository Pattern — DIP)."""
        return DjangoFundRepository().get_period_locks()

    @extend_schema(
        tags=["Funds"],
        summary="Danh sách kỳ khóa sổ",
        responses={200: OpenApiResponse(description="Envelope items + pagination")},
    )
    def get(self, request, *args, **kwargs) -> Response:
        """GET danh sách kỳ đã khóa — envelope phân trang."""
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs) -> Response:
        """Ghi đè list để trả envelope {success, data:{items,pagination}}."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(_paginated_envelope(self.paginator.page, serializer.data, "Lấy danh sách kỳ khóa sổ thành công"))
        serializer = self.get_serializer(queryset, many=True)
        return ok(
            data={"items": serializer.data, "pagination": None},
            message="Lấy danh sách kỳ khóa sổ thành công",
        )


# ======================================================================
# Xuất sổ quỹ Excel
# ======================================================================
class FundExportExcelView(generics.GenericAPIView):
    """GET /api/v1/funds/export-excel/ — tải file .xlsx toàn bộ sổ quỹ."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]

    @extend_schema(
        tags=["Funds"],
        summary="Xuất sổ quỹ Excel",
        description="File so_quy_clbip.xlsx: sheet 'Sổ quỹ' gồm mọi giao dịch kèm số dư lũ kế.",
        responses={
            200: OpenApiResponse(
                description=(
                    "File so_quy_clbip.xlsx nhị phân "
                    f"(Content-Type: {XLSX_CONTENT_TYPE}, Content-Disposition: attachment)"
                ),
            ),
        },
    )
    def get(self, request, *args, **kwargs) -> HttpResponse:
        """Sinh bytes xlsx từ Service và trả về như file đính kèm."""
        content, _filename = FundService.export_excel()
        response = HttpResponse(
            content,
            content_type=XLSX_CONTENT_TYPE,
            status=status.HTTP_200_OK,
        )
        response["Content-Disposition"] = 'attachment; filename="so_quy_clbip.xlsx"'
        return response
