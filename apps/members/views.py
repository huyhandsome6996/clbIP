"""
Views — apps.members
Controller mỏng: nhận request → gọi MemberService → trả envelope.
Phân quyền chống IDOR: thành viên thường CHỈ xem/sửa dữ liệu của chính mình.
"""
from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ForbiddenException
from apps.members.serializers import (
    BoardMemberPublicSerializer,
    BoardMemberSerializer,
    MemberCreateSerializer,
    MemberExcelImportSerializer,
    MemberProfileListSerializer,
    MemberSearchSerializer,
    MemberUpdateSerializer,
)
from apps.members.services import MemberService
from core.pagination import StandardPagination
from core.permissions import IsBCNOrAdmin, IsOwnerOrBCN
from core.response import created, ok

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _paginated_envelope(page, serialized_items: list, message: str) -> dict:
    """Envelope phân trang chuẩn (data.items + data.pagination)."""
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
# Danh sách & tạo thành viên
# ======================================================================
class MemberListCreateView(generics.ListCreateAPIView):
    """GET: BCN xem danh sách thành viên. POST: BCN thêm thành viên mới."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]
    pagination_class = StandardPagination

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MemberCreateSerializer
        return MemberProfileListSerializer

    def get_queryset(self):
        qp = self.request.query_params
        return MemberService.list_profiles(
            lop=qp.get("lop"),
            trang_thai=qp.get("trang_thai"),
            search=qp.get("search"),
            sort=qp.get("sort"),
        )

    @extend_schema(
        tags=["Members"],
        summary="Danh sách thành viên (BCN)",
        parameters=[
            OpenApiParameter("lop", str, OpenApiParameter.QUERY),
            OpenApiParameter("trang_thai", str, OpenApiParameter.QUERY,
                             enum=["ACTIVE", "INACTIVE", "LEAVE"]),
            OpenApiParameter("search", str, OpenApiParameter.QUERY,
                             description="Tìm theo họ tên / MSSV / email"),
            OpenApiParameter("sort", str, OpenApiParameter.QUERY,
                             enum=["created_at", "-created_at", "xp_points", "-xp_points", "ho_ten"]),
        ],
        responses={200: OpenApiResponse(description="Envelope items + pagination")},
    )
    def get(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return Response(_paginated_envelope(self.paginator.page, serializer.data, "Lấy danh sách thành viên thành công"))
        serializer = self.get_serializer(queryset, many=True)
        return ok(data={"items": serializer.data, "pagination": None}, message="Lấy danh sách thành viên thành công")

    @extend_schema(
        tags=["Members"],
        summary="Thêm thành viên mới (BCN)",
        request=MemberCreateSerializer,
        responses={201: MemberProfileListSerializer, 403: None, 409: None},
    )
    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = MemberService.create_member(serializer.validated_data, request.user)
        return created(
            data=MemberProfileListSerializer(profile).data,
            message="Thêm thành viên thành công. Mật khẩu mặc định: CLBIP@2026",
        )


# ======================================================================
# Chi tiết / cập nhật / khóa thành viên
# ======================================================================
class MemberDetailView(APIView):
    """GET: chi tiết (IsOwnerOrBCN). PUT/PATCH: cập nhật. DELETE: khóa tài khoản (BCN)."""

    permission_classes = [IsAuthenticated, IsOwnerOrBCN]

    def _get_object(self, pk: int):
        profile = MemberService._get_or_404(pk)  # noqa: SLF001 — controller dùng service helper
        # Chống IDOR: kiểm tra quyền sở hữu object
        self.check_object_permissions(self.request, profile)
        return profile

    @extend_schema(tags=["Members"], summary="Chi tiết thành viên", responses={200: MemberProfileListSerializer, 403: None, 404: None})
    def get(self, request, pk: int) -> Response:
        profile = self._get_object(pk)
        return ok(data=MemberProfileListSerializer(profile).data, message="Lấy chi tiết thành công")

    @extend_schema(tags=["Members"], summary="Cập nhật hồ sơ thành viên", request=MemberUpdateSerializer)
    def put(self, request, pk: int) -> Response:
        return self._update(request, pk, partial=False)

    @extend_schema(tags=["Members"], summary="Cập nhật một phần hồ sơ", request=MemberUpdateSerializer)
    def patch(self, request, pk: int) -> Response:
        return self._update(request, pk, partial=True)

    def _update(self, request, pk: int, partial: bool) -> Response:
        profile = self._get_object(pk)
        is_self_edit = not request.user.is_bcn
        serializer = MemberUpdateSerializer(
            data=request.data, partial=partial, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        updated = MemberService.update_member(
            pk, serializer.validated_data, request.user, is_self_edit=is_self_edit
        )
        return ok(data=MemberProfileListSerializer(updated).data, message="Cập nhật thành công")

    @extend_schema(tags=["Members"], summary="Khóa tài khoản thành viên (BCN)")
    def delete(self, request, pk: int) -> Response:
        profile = MemberService.lock_member(pk, request.user)
        return ok(data=MemberProfileListSerializer(profile).data, message="Đã khóa tài khoản thành viên")


# ======================================================================
# Hồ sơ 360°
# ======================================================================
class Profile360View(APIView):
    """GET /members/{id}/profile360/ — tổng hợp hồ sơ. Member chỉ xem được của CHÍNH MÌNH."""

    permission_classes = [IsAuthenticated, IsOwnerOrBCN]

    @extend_schema(
        tags=["Members"],
        summary="Hồ sơ 360° tổng hợp",
        description="Thống kê sự kiện, chuyên cần, XP/Level, huy hiệu, vai trò BCN.",
        responses={200: OpenApiResponse(description="Dict tổng hợp"), 403: None, 404: None},
    )
    def get(self, request, pk: int) -> Response:
        if not request.user.is_bcn:
            my_profile = getattr(request.user, "member_profile", None)
            if my_profile is None or my_profile.pk != pk:
                raise ForbiddenException("Bạn chỉ có quyền xem hồ sơ của chính mình.")
        return ok(data=MemberService.get_profile360(pk), message="Lấy hồ sơ 360° thành công")


# ======================================================================
# Trie search
# ======================================================================
class MemberSearchView(APIView):
    """GET /members/search/?q= — tìm kiếm tức thời bằng Prefix Trie (O(L))."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Members"],
        summary="Tìm kiếm thành viên (Trie autocomplete)",
        parameters=[OpenApiParameter("q", str, OpenApiParameter.QUERY, required=True)],
        responses={200: OpenApiResponse(description="items + count")},
    )
    def get(self, request) -> Response:
        q = request.query_params.get("q", "")
        # Phân quyền theo vai trò (QA-Audit 2a — chống PII leak):
        # - BCN/ADMIN: serializer đầy đủ (email/sdt/mssv) phục vụ quản lý.
        # - Thành viên thường: chỉ nhận trường công khai (tên/lớp/cấp độ/XP)
        #   và chỉ thấy thành viên ĐANG HOẠT ĐỘNG.
        is_board = request.user.is_bcn
        profiles = MemberService.search_profiles(q, limit=20, only_active=not is_board)
        serializer_cls = MemberProfileListSerializer if is_board else MemberSearchSerializer
        data = serializer_cls(profiles, many=True).data
        return ok(data={"items": data, "count": len(data)}, message="Kết quả tìm kiếm")


# ======================================================================
# Excel import / export
# ======================================================================
class MemberImportExcelView(APIView):
    """POST /members/import-excel/ — BCN nhập hàng loạt từ file .xlsx."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]

    @extend_schema(
        tags=["Members"],
        summary="Nhập thành viên từ Excel (BCN)",
        request={"multipart/form-data": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}},
        responses={200: OpenApiResponse(description="created + errors preview")},
    )
    def post(self, request) -> Response:
        serializer = MemberExcelImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = MemberService.import_excel(serializer.validated_data["file"], request.user)
        return ok(
            data=result,
            message=f"Nhập Excel hoàn tất: {result['created']} thành viên mới, {len(result['errors'])} dòng lỗi.",
        )


class MemberExportExcelView(APIView):
    """GET /members/export-excel/ — BCN tải danh sách thành viên .xlsx."""

    permission_classes = [IsAuthenticated, IsBCNOrAdmin]

    @extend_schema(tags=["Members"], summary="Xuất danh sách thành viên Excel (BCN)", responses={200: OpenApiResponse(description="File .xlsx")})
    def get(self, request) -> HttpResponse:
        content = MemberService.export_excel()
        response = HttpResponse(
            content,
            content_type=XLSX_CONTENT_TYPE,
        )
        response["Content-Disposition"] = 'attachment; filename="thanh_vien_clbip.xlsx"'
        return response


# ======================================================================
# Cơ cấu Ban Chủ Nhiệm
# ======================================================================
class BoardMemberListCreateView(generics.ListCreateAPIView):
    """GET: sơ đồ tổ chức BCN theo nhiệm kỳ. POST: bổ nhiệm (BCN)."""

    serializer_class = BoardMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        nhiem_ky = self.request.query_params.get("nhiem_ky")
        from apps.members.repositories import DjangoMemberRepository

        return DjangoMemberRepository.get_board_positions(nhiem_ky)

    @extend_schema(
        tags=["Members"],
        summary="Cơ cấu Ban Chủ Nhiệm (Org Chart)",
        parameters=[OpenApiParameter("nhiem_ky", str, OpenApiParameter.QUERY, required=False)],
        responses={200: BoardMemberSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        # QA-Audit 2a: thành viên thường không nhận MSSV của cán bộ (PII)
        serializer_cls = BoardMemberSerializer if request.user.is_bcn else BoardMemberPublicSerializer
        serializer = serializer_cls(queryset, many=True)
        return ok(data={"items": serializer.data, "pagination": None}, message="Cơ cấu BCN")

    @extend_schema(tags=["Members"], summary="Bổ nhiệm thành viên BCN", request=BoardMemberSerializer)
    def post(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        board_member = serializer.save()
        return created(data=BoardMemberSerializer(board_member).data, message="Bổ nhiệm thành công")
