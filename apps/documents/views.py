"""
Views — apps.documents (Controller MỎNG, logic 100% ở Service Layer)
====================================================================
Prefix mount: /api/v1/documents/
    GET  /api/v1/documents/           — danh sách (filter nhom/search, sort whitelist)
    POST /api/v1/documents/           — upload tài liệu (multipart, +100 XP)
    GET  /api/v1/documents/search/    — tìm kiếm prefix qua Trie (DSA 3)
    GET  /api/v1/documents/<id>/      — chi tiết
    GET  /api/v1/documents/<id>/download/ — tải về (đếm lượt tải atomic)
    DELETE /api/v1/documents/<id>/    — xóa (BCN/ADMIN hoặc người upload)
"""
from django.db.models import QuerySet
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.exceptions import NotFoundException
from apps.documents.serializers import DocumentCreateSerializer, DocumentSerializer
from apps.documents.services import DocumentService
from core.pagination import StandardPagination
from core.response import created, ok


class EnvelopeListMixin:
    """
    List mixin trả envelope chuẩn {success, data:{items, pagination}, ...}.

    ⚠ ĐI VÒNG LỖI FOUNDATION: core.response.paginated_payload truy cập
    `page_result.page.number` / `page_result.paginator.page_size` — Django `Page`
    không có `.page` (phải là `.number`) và DjangoPaginator không có `.page_size`
    (phải là `.per_page`). Lỗi đã được flag lên worklog để main agent sửa core;
    mixin này đảm bảo API danh sách hoạt động đúng hợp đồng envelope ngay bây giờ.
    """

    def list(self, request: Request, *args, **kwargs) -> Response:
        """GET danh sách — bắt buộc phân trang (Security §3.3), trả envelope."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            # paginate_queryset trả LIST item; Django Page nằm ở self.paginator.page
            django_page = self.paginator.page
            serializer = self.get_serializer(page, many=True)
            return Response(
                {
                    "success": True,
                    "data": {
                        "items": serializer.data,
                        "pagination": {
                            "page": django_page.number,
                            "page_size": django_page.paginator.per_page,
                            "total_pages": django_page.paginator.num_pages,
                            "total_items": django_page.paginator.count,
                        },
                    },
                    "message": "Lấy danh sách thành công",
                    "errors": None,
                },
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(queryset, many=True)
        return ok(
            {"items": serializer.data, "pagination": None},
            message="Lấy danh sách thành công",
        )


class DocumentListCreateView(EnvelopeListMixin, generics.ListCreateAPIView):
    """
    Danh sách + Upload tài liệu.

    GET  (auth): filter ?nhom= (whitelist choices), ?search= (icontains, ORM
         parameterized), sort whitelist chống SQLi qua order_by động (§2.1).
    POST (auth): MỌI thành viên chia sẻ được — multipart/form-data, tệp qua
         File Upload Hardening 4 tầng trong DocumentService.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = StandardPagination

    def get_queryset(self) -> QuerySet:
        """Queryset qua Repository (scope pham_vi + filter/sort whitelist) — controller mỏng."""
        return DocumentService.list_documents(
            self.request.user,
            nhom=self.request.query_params.get("nhom"),
            search=self.request.query_params.get("search") or "",
            sort=self.request.query_params.get("sort", "-created_at"),
        )

    def get_serializer_class(self) -> type:
        """GET dùng DocumentSerializer, POST dùng DocumentCreateSerializer."""
        if self.request.method == "POST":
            return DocumentCreateSerializer
        return DocumentSerializer

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Danh sách tài liệu",
        description=(
            "Lấy danh sách Kho Tài liệu (phân trang chuẩn). Filter: `nhom` "
            "(CHUYEN_MON/NGHIEP_VU/KY_NANG), `search` (icontains tiêu đề/tags/mô tả), "
            "`sort` whitelist (-created_at, luot_tai, -luot_tai, tieu_de)."
        ),
        parameters=[
            OpenApiParameter("nhom", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("sort", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: DocumentSerializer(many=True)},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """Danh sách phân trang — envelope qua StandardPagination."""
        return self.list(request, *args, **kwargs)

    @extend_schema(
        summary="Chia sẻ tài liệu mới (+100 XP)",
        description=(
            "Upload tài liệu (multipart/form-data). Tệp phải qua 4 tầng "
            "hardening: whitelist đuôi (.pdf/.docx/.pptx/.xlsx/.png/.jpg/.jpeg), "
            "size ≤ 15MB, kiểm tra magic bytes nội dung thật, đổi tên UUID. "
            "Thành viên có MemberProfile được thưởng +100 XP (idempotency)."
        ),
        request=DocumentCreateSerializer,
        responses={
            201: DocumentSerializer,
            400: OpenApiResponse(description="FileValidationException — tệp vi phạm hardening"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        """Validate serializer → Service tạo tài liệu (hardening + XP) → envelope 201."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = DocumentService.create_document(
            request.user,
            serializer.validated_data["file"],
            serializer.validated_data,
        )
        return created(
            DocumentSerializer(doc, context=self.get_serializer_context()).data,
            message="Chia sẻ tài liệu thành công (+100 XP!)",
        )


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    """
    Chi tiết + Xóa tài liệu.

    GET    (auth): xem thông tin tài liệu.
    DELETE (auth): BCN/ADMIN hoặc chính người upload — logic trong
           DocumentService.delete_document (IsOwnerOrBCN, chống IDOR).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DocumentSerializer

    def get_queryset(self) -> QuerySet:
        """Queryset qua Repository — thay class attr giữ ORM queryset (Repository Pattern)."""
        return DocumentService.detail_queryset()

    @extend_schema(
        summary="Chi tiết tài liệu",
        description="Xem đầy đủ thông tin một tài liệu trong kho.",
        responses={200: DocumentSerializer, 404: OpenApiResponse(description="Không tìm thấy")},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """Chi tiết tài liệu — envelope (kiểm tra phạm vi theo vai trò)."""
        doc = self.get_object()
        # QA-Audit 2d: BCN_ONLY không tồn tại với thành viên thường (404 —
        # không hé lộ sự tồn tại của tài liệu nội bộ)
        if not DocumentService.can_view(doc, request.user):
            raise NotFoundException("Không tìm thấy tài liệu yêu cầu.")
        return ok(
            self.get_serializer(doc).data,
            message="Lấy chi tiết tài liệu thành công",
        )

    @extend_schema(
        summary="Xóa tài liệu",
        description="Chỉ BCN/ADMIN hoặc người upload mới được xóa. File vật lý cũng bị dọn.",
        responses={
            200: OpenApiResponse(description="Đã xóa"),
            403: OpenApiResponse(description="ForbiddenException — không đúng quyền"),
            404: OpenApiResponse(description="Không tìm thấy"),
        },
    )
    def delete(self, request: Request, *args, **kwargs) -> Response:
        """Xóa qua Service (kiểm quyền actor + dọn file vật lý) → envelope."""
        doc = self.get_object()
        # QA-Audit 2d: nhất quán với GET — BCN_ONLY với thành viên thường trả
        # 404 thay vì 403 (không hé lộ sự tồn tại của tài liệu nội bộ)
        if not DocumentService.can_view(doc, request.user):
            raise NotFoundException("Không tìm thấy tài liệu yêu cầu.")
        DocumentService.delete_document(doc, request.user)
        return ok(None, message="Đã xóa tài liệu")


class DocumentSearchView(generics.GenericAPIView):
    """
    Tìm kiếm nhanh qua Prefix Trie (DSA 3) — O(L).

    GET /api/v1/documents/search/?q=<tiền tố> — normalize bỏ dấu tiếng Việt,
    khớp cả tiêu đề lẫn từng tag ("de thi" → "Đề thi Web").
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DocumentSerializer
    pagination_class = None  # Tìm kiếm tức thời, trả tối đa `limit` kết quả

    @extend_schema(
        summary="Tìm kiếm tài liệu (Prefix Trie — O(L))",
        description=(
            "Autocomplete tức thời theo tiền tố tiêu đề/tags, tự bỏ dấu "
            "tiếng Việt. Trả `items` + `count` (tối đa 20 kết quả)."
        ),
        parameters=[
            OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY, required=False),
        ],
        responses={200: DocumentSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        """Gọi DocumentService.search (chỉ index tài liệu trong phạm vi) → envelope data={items, count}."""
        q = request.query_params.get("q", "")
        docs = DocumentService.search(q, limit=20, user=request.user)
        return ok(
            {
                "items": self.get_serializer(docs, many=True).data,
                "count": len(docs),
            },
            message="Kết quả tìm kiếm tài liệu",
        )


class DocumentDownloadView(generics.GenericAPIView):
    """
    Tải tài liệu về — đếm lượt tải atomic rồi stream file đính kèm.

    GET /api/v1/documents/<id>/download/ — FileResponse as_attachment,
    Content-Type khớp định dạng (chống MIME sniffing — Security §8).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = DocumentSerializer

    @extend_schema(
        summary="Tải xuống tài liệu",
        description=(
            "Stream nội dung tệp (attachment) và tăng lượt tải lên 1 một cách "
            "atomic (F expression, chống race condition)."
        ),
        responses={
            200: OpenApiResponse(description="Nội dung nhị phân của tệp"),
            404: OpenApiResponse(description="Không tìm thấy tài liệu/tệp"),
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        """Tăng luot_tai → mở file → FileResponse attachment (kiểm phạm vi trước)."""
        doc = DocumentService.get_or_404(pk)
        # QA-Audit 2d: chặn tải tài liệu BCN_ONLY bởi thành viên thường —
        # kiểm tra ở đây chứ không chỉ ở list (download là lỗ hổng bị bỏ sót phổ biến)
        if not DocumentService.can_view(doc, request.user):
            raise NotFoundException("Không tìm thấy tài liệu yêu cầu.")
        DocumentService.increment_download(doc)

        ext = doc.file_ext or f".{doc.file_type}"
        try:
            file_handle = doc.file.open("rb")
        except (FileNotFoundError, ValueError) as exc:
            raise NotFoundException("Tệp không còn tồn tại trên máy chủ.") from exc

        return FileResponse(
            file_handle,
            as_attachment=True,
            filename=f"{doc.tieu_de}{ext}",
            content_type=DocumentService.CONTENT_TYPES.get(ext, "application/octet-stream"),
            status=status.HTTP_200_OK,
        )
