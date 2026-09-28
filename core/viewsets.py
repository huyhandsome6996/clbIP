"""
Base ViewSet chuẩn hóa envelope + hooks Service Layer.

Views chỉ là Controller: nhận HTTP request → gọi Service → trả envelope.
Mọi list endpoint tự động có phân trang bắt buộc (chống DoS §3.3).
"""
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.response import paginated_payload


class EnvelopeModelViewSet(viewsets.ModelViewSet):
    """
    ModelViewSet trả về envelope chuẩn {success, data, message, errors}.

    Subclass chỉ cần override perform_create / perform_update / perform_destroy
    để điều hướng qua Service Layer, hoặc override nguyên method khi cần logic riêng.
    """

    # Thông báo mặc định (subclass có thể ghi đè)
    create_message: str = "Tạo mới thành công"
    update_message: str = "Cập nhật thành công"
    destroy_message: str = "Xóa thành công"

    # ------------------------------------------------------------------
    def list(self, request, *args, **kwargs) -> Response:
        """GET danh sách — bắt buộc phân trang, trả envelope."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(
                paginated_payload(self.page, items=serializer.data, message="Lấy danh sách thành công")
            )
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "success": True,
                "data": {"items": serializer.data, "pagination": None},
                "message": "Lấy danh sách thành công",
                "errors": None,
            }
        )

    def create(self, request, *args, **kwargs) -> Response:
        """POST — tạo mới qua Service (perform_create), trả envelope 201."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {
                "success": True,
                "data": serializer.data,
                "message": self.create_message,
                "errors": None,
            },
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, *args, **kwargs) -> Response:
        """GET chi tiết — envelope."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(
            {
                "success": True,
                "data": serializer.data,
                "message": "Lấy chi tiết thành công",
                "errors": None,
            }
        )

    def update(self, request, *args, **kwargs) -> Response:
        """PUT/PATCH — cập nhật qua Service (perform_update)."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(
            {
                "success": True,
                "data": serializer.data,
                "message": self.update_message,
                "errors": None,
            }
        )

    def destroy(self, request, *args, **kwargs) -> Response:
        """DELETE — xóa (hoặc soft-delete) qua Service (perform_destroy)."""
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {
                "success": True,
                "data": None,
                "message": self.destroy_message,
                "errors": None,
            }
        )


class EnvelopeGenericViewSet(viewsets.GenericViewSet):
    """GenericViewSet với envelope — cho các view action tùy biến (không CRUD chuẩn)."""
