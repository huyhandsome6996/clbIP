"""
Views — apps.posts (Controller MỎNG, logic 100% ở Service Layer)
================================================================
Prefix mount: /api/v1/ (không có prefix "posts/" riêng):
    GET    /api/v1/posts/          — feed (auth): bỏ bài xóa, ghim lên đầu
    POST   /api/v1/posts/          — BCN đăng bài (bleach chống XSS + audit)
    GET    /api/v1/posts/<id>/     — chi tiết + 10 audit log gần nhất
    PUT    /api/v1/posts/<id>/     — BCN sửa bài (audit UPDATE)
    PATCH  /api/v1/posts/<id>/     — BCN sửa bài (partial)
    DELETE /api/v1/posts/<id>/     — BCN xóa mềm (audit DELETE)
    PATCH  /api/v1/posts/<id>/pin/ — BCN ghim / bỏ ghim
    GET    /api/v1/feedback/       — BCN đọc hòm thư góp ý (ẨN DANH)
    POST   /api/v1/feedback/       — thành viên gửi góp ý ẩn danh (throttle 2/phút)
    GET    /api/v1/polls/          — danh sách bình chọn
    POST   /api/v1/polls/          — BCN tạo bình chọn
    POST   /api/v1/polls/<id>/vote/ — thành viên bình chọn (throttle, chống double-vote)
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.throttles import FeedbackRateThrottle
from apps.posts.serializers import (
    FeedbackCreateSerializer,
    FeedbackListSerializer,
    PollCreateSerializer,
    PollSerializer,
    PollVoteSerializer,
    PostCreateUpdateSerializer,
    PostDetailSerializer,
    PostListSerializer,
)
from apps.posts.services import FeedbackService, PollService, PostService
from core.permissions import IsBCNOrAdmin
from core.response import created, ok


class EnvelopeListMixin:
    """
    List mixin trả envelope chuẩn {success, data:{items, pagination}, ...}.

    ⚠ ĐI VÒNG LỖI FOUNDATION: core.response.paginated_payload truy cập
    `page_result.page.number` / `page_result.paginator.page_size` — Django `Page`
    không có `.page` (phải là `.number`) và DjangoPaginator không có `.page_size`
    (phải là `.per_page`). Đã flag worklog để main agent sửa core sau này.
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


class PostListCreateView(EnvelopeListMixin, generics.ListCreateAPIView):
    """Feed bảng tin (GET — mọi thành viên) + Đăng bài (POST — chỉ BCN)."""

    # Phân trang bắt buộc cho MỌI API danh sách (Security §3.3) — dùng default.

    def get_queryset(self):
        """Feed: is_deleted=False, ghim lên đầu, mới nhất trước (PostService)."""
        return PostService.get_feed(self.request.user)

    def get_serializer_class(self) -> type:
        """GET → PostListSerializer; POST → PostCreateUpdateSerializer."""
        if self.request.method == "POST":
            return PostCreateUpdateSerializer
        return PostListSerializer

    def get_permissions(self) -> list:
        """GET auth; POST chỉ BCN/ADMIN (RBAC — màn hình 2)."""
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    # ------------------------------------------------------------------
    @extend_schema(
        summary="Feed bảng tin",
        description="Danh sách bài đăng còn hiệu lực: bài ghim lên đầu, mới nhất trước.",
        responses={200: PostListSerializer(many=True)},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """Feed cho MEMBER PORTAL (màn hình 11)."""
        return self.list(request, *args, **kwargs)

    @extend_schema(
        summary="Đăng thông báo mới (BCN)",
        description=(
            "BCN đăng bài: nội dung được bleach.clean whitelist "
            "p/br/strong/em/u/ul/ol/li/a — chống XSS (Security §2.2). "
            "Ghi PostAuditLog CREATE."
        ),
        request=PostCreateUpdateSerializer,
        responses={
            201: PostDetailSerializer,
            403: OpenApiResponse(description="Chỉ BCN/ADMIN được đăng bài"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        """Validate → PostService.create_post (sanitize + audit) → envelope 201."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = PostService.create_post(serializer.validated_data, request.user)
        return created(
            PostDetailSerializer(post).data,
            message="Đăng thông báo thành công",
        )


class PostDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Chi tiết bài đăng + Sửa (BCN) + Xóa mềm (BCN) — mọi thay đổi ghi audit."""

    def get_queryset(self):
        """Queryset qua Repository (PostService.all_posts) — thay class attr ORM."""
        return PostService.all_posts()

    def get_serializer_class(self) -> type:
        """GET/PATCH/PUT → PostDetailSerializer (có audit); DELETE không cần."""
        return PostDetailSerializer

    def get_permissions(self) -> list:
        """GET auth; PUT/PATCH/DELETE chỉ BCN/ADMIN."""
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Chi tiết bài đăng",
        description="Bao gồm 10 dòng PostAuditLog gần nhất (CREATE/UPDATE/PIN/DELETE).",
        responses={200: PostDetailSerializer, 404: OpenApiResponse(description="Không tìm thấy")},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """Chi tiết + audit trail."""
        post = self.get_object()
        return ok(self.get_serializer(post).data, message="Lấy chi tiết bài đăng thành công")

    @extend_schema(
        summary="Sửa bài đăng (BCN)",
        description="Nội dung mới được bleach.clean trước khi lưu; ghi audit UPDATE kèm field sửa.",
        request=PostCreateUpdateSerializer,
        responses={200: PostDetailSerializer, 403: OpenApiResponse(description="Chỉ BCN/ADMIN")},
    )
    def put(self, request: Request, *args, **kwargs) -> Response:
        """Sửa toàn phần qua PostService.update_post."""
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Sửa một phần bài đăng (BCN)",
        description="PATCH partial — chỉ các field gửi lên mới được cập nhật.",
        request=PostCreateUpdateSerializer,
        responses={200: PostDetailSerializer, 403: OpenApiResponse(description="Chỉ BCN/ADMIN")},
    )
    def patch(self, request: Request, *args, **kwargs) -> Response:
        """Sửa một phần qua PostService.update_post."""
        return self.update(request, *args, partial=True, **kwargs)

    @extend_schema(
        summary="Xóa bài đăng (BCN — soft delete)",
        description="is_deleted=True + audit DELETE; feed không còn hiển thị bài.",
        responses={200: OpenApiResponse(description="Đã xóa"), 403: OpenApiResponse(description="Chỉ BCN/ADMIN")},
    )
    def delete(self, request: Request, *args, **kwargs) -> Response:
        """Soft delete qua PostService → envelope."""
        post = self.get_object()
        PostService.soft_delete_post(post, request.user)
        return ok(None, message="Đã xóa bài đăng")

    # ------------------------------------------------------------------
    def update(self, request: Request, *args, partial: bool = False, **kwargs) -> Response:
        """PUT/PATCH chung: validate qua PostCreateUpdateSerializer → Service → envelope."""
        post = self.get_object()
        input_serializer = PostCreateUpdateSerializer(post, data=request.data, partial=partial)
        input_serializer.is_valid(raise_exception=True)
        updated = PostService.update_post(post, input_serializer.validated_data, request.user)
        return ok(self.get_serializer(updated).data, message="Cập nhật bài đăng thành công")


class PostPinView(generics.GenericAPIView):
    """Ghim / Bỏ ghim bài đăng — PATCH /posts/<id>/pin/ (chỉ BCN)."""

    permission_classes = [IsBCNOrAdmin]
    serializer_class = PostListSerializer

    @extend_schema(
        summary="Ghim / Bỏ ghim bài đăng (BCN)",
        description=(
            "Đảo trạng thái is_pinned. Ghim: pinned_at=now, bài lên đầu feed. "
            "Ghi audit PIN/UNPIN."
        ),
        request=None,
        responses={200: PostListSerializer, 403: OpenApiResponse(description="Chỉ BCN/ADMIN")},
    )
    def patch(self, request: Request, pk: int) -> Response:
        """Toggle pin qua PostService → thông báo theo trạng thái mới."""
        post = PostService.get_or_404(pk)
        PostService.toggle_pin(post, request.user)
        message = "Đã ghim bài" if post.is_pinned else "Đã bỏ ghim"
        return ok(PostListSerializer(post).data, message=message)


class FeedbackView(EnvelopeListMixin, generics.ListCreateAPIView):
    """
    Hòm thư góp ý ẨN DANH.

    GET  (BCN): chỉ thấy nội dung + thời gian — KHÔNG bao giờ lộ sender.
    POST (auth): thành viên gửi góp ý — throttle 2 request/phút chống spam,
         cộng thêm hạn mức 5 góp ý/ngày ở FeedbackService.
    """

    # Phân trang bắt buộc cho MỌI API danh sách (Security §3.3) — dùng default.

    # Throttle scoped (cần throttle_scope để ScopedRateThrottle hoạt động)
    throttle_classes = [FeedbackRateThrottle]
    throttle_scope = "feedback"

    def get_queryset(self):
        """Danh sách góp ý (ẩn danh) — serializer cũng không serialize sender."""
        return FeedbackService.list_feedback()

    def get_serializer_class(self) -> type:
        """GET → FeedbackListSerializer; POST → FeedbackCreateSerializer."""
        if self.request.method == "POST":
            return FeedbackCreateSerializer
        return FeedbackListSerializer

    def get_permissions(self) -> list:
        """GET chỉ BCN/ADMIN; POST mọi thành viên đã đăng nhập."""
        if self.request.method == "GET":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Đọc hòm thư góp ý (BCN)",
        description=(
            "Danh sách góp ý ẨN DANH: chỉ (noi_dung, created_at). "
            "Tuyệt đối không trả sender."
        ),
        responses={200: FeedbackListSerializer(many=True), 403: OpenApiResponse(description="Chỉ BCN/ADMIN")},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """BCN đọc góp ý — ẩn danh đúng nghĩa."""
        return self.list(request, *args, **kwargs)

    @extend_schema(
        summary="Gửi góp ý ẩn danh",
        description="Tối đa 5 góp ý/ngày/người + throttle 2 request/phút. Nội dung text thuần.",
        request=FeedbackCreateSerializer,
        responses={
            201: OpenApiResponse(description="Đã ghi nhận góp ý"),
            400: OpenApiResponse(description="Nội dung rỗng hoặc vượt hạn mức chống spam"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        """FeedbackService.create_feedback (anti-spam + bleach) → envelope 201."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        FeedbackService.create_feedback(serializer.validated_data["noi_dung"], request.user)
        return created(None, message="Cảm ơn góp ý của bạn! (Ẩn danh)")


class PollListCreateView(EnvelopeListMixin, generics.ListCreateAPIView):
    """Danh sách bình chọn (GET — auth) + Tạo bình chọn (POST — BCN)."""

    # Phân trang bắt buộc cho MỌI API danh sách (Security §3.3) — dùng default.

    def get_queryset(self):
        """Toàn bộ poll, mới nhất trước (Meta ordering) — qua Repository."""
        return PollService.all_polls()

    def get_serializer_class(self) -> type:
        """GET → PollSerializer; POST → PollCreateSerializer."""
        if self.request.method == "POST":
            return PollCreateSerializer
        return PollSerializer

    def get_permissions(self) -> list:
        """GET auth; POST chỉ BCN/ADMIN."""
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Danh sách bình chọn",
        description="Các poll cộng đồng kèm số phiếu hiện tại và tổng phiếu.",
        responses={200: PollSerializer(many=True)},
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        """Danh sách poll."""
        return self.list(request, *args, **kwargs)

    @extend_schema(
        summary="Tạo bình chọn mới (BCN)",
        description="Cần ít nhất 2 lựa chọn; votes khởi tạo đếm 0 theo từng option.",
        request=PollCreateSerializer,
        responses={201: PollSerializer, 400: OpenApiResponse(description="Thiếu lựa chọn")},
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        """PollService.create_poll → envelope 201."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        poll = PollService.create_poll(
            serializer.validated_data["question"],
            serializer.validated_data["options"],
            request.user,
        )
        return created(PollSerializer(poll).data, message="Tạo bình chọn thành công")


class PollVoteView(generics.GenericAPIView):
    """Bình chọn: POST /polls/<id>/vote/ — mỗi user 1 lần, atomic row lock."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [FeedbackRateThrottle]
    throttle_scope = "feedback"
    serializer_class = PollVoteSerializer

    @extend_schema(
        summary="Ghi nhận bình chọn",
        description=(
            "Body: {option_index}. Chống race condition bằng select_for_update; "
            "chặn vote lại (409), poll đóng (409), index sai (400)."
        ),
        request=PollVoteSerializer,
        responses={
            200: PollSerializer,
            400: OpenApiResponse(description="option_index ngoài phạm vi"),
            409: OpenApiResponse(description="Đã bình chọn rồi / Bình chọn đã đóng"),
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """PollService.vote (atomic + double-vote guard) → envelope."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        poll = PollService.vote(pk, serializer.validated_data["option_index"], request.user)
        return ok(PollSerializer(poll).data, message="Đã ghi nhận bình chọn")


class PollCloseView(generics.GenericAPIView):
    """Đóng bình chọn: PATCH /polls/<id>/close/ — chỉ BCN/ADMIN (TASK 6A)."""

    permission_classes = [IsBCNOrAdmin]
    serializer_class = PollSerializer

    @extend_schema(
        summary="Đóng bình chọn (BCN)",
        description=(
            "Đặt is_closed=True — thành viên không thể vote thêm (vote trên "
            "poll đã đóng trả 409). Đóng lần 2 → 400."
        ),
        request=None,
        responses={
            200: PollSerializer,
            400: OpenApiResponse(description="Bình chọn đã đóng rồi"),
            403: OpenApiResponse(description="Chỉ BCN/ADMIN"),
            404: OpenApiResponse(description="Poll không tồn tại"),
        },
    )
    def patch(self, request: Request, pk: int) -> Response:
        """PollService.close_poll (atomic + row lock) → envelope."""
        poll = PollService.close_poll(pk, request.user)
        return ok(PollSerializer(poll).data, message="Đã đóng bình chọn")
