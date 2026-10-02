"""
Views — Events API (prefix /api/v1/events/).
============================================
View mỏng: nhận HTTP request → gọi Service → trả envelope chuẩn.
Lọc/sort theo WHITELIST (chống SQL Injection qua order_by — Security §2.1).
Toàn bộ truy vấn ORM nằm ở apps/events/repositories.py (Repository Pattern)
— view KHÔNG đụng trực tiếp vào `.objects` của model nào.
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import ValidationException
from apps.events.models import ActivityEvent
from apps.events.serializers import (
    ActivityEventCreateUpdateSerializer,
    ActivityEventDetailSerializer,
    ActivityEventListSerializer,
    EventBudgetDetailSerializer,
    EventCommunicationSerializer,
    EventRegistrationSerializer,
    EventTaskSerializer,
    TicketVerifySerializer,
)
from apps.events.services import EventService, EventTaskService
from core.pagination import StandardPagination
from core.permissions import IsBCNOrAdmin

# Whitelist sort — mọi giá trị ngoài danh sách bị chặn (Security Hardening §2.1)
EVENT_SORT_WHITELIST = (
    "thoi_gian_bat_dau",
    "-thoi_gian_bat_dau",
    "created_at",
    "-created_at",
)


def _paginated_envelope(items: list, page, message: str) -> Response:
    """
    Đóng gói kết quả phân trang vào envelope chuẩn {success,data,message,errors}.

    (Bản địa cho app events: `paginated_payload` của core nhận Page thô,
    còn ở đây `items` đã được serialize — cùng shape `data.items/pagination`.)
    """
    return Response(
        {
            "success": True,
            "data": {
                "items": items,
                "pagination": {
                    "page": page.number,
                    "page_size": page.paginator.per_page,
                    "total_pages": page.paginator.num_pages,
                    "total_items": page.paginator.count,
                },
            },
            "message": message,
            "errors": None,
        },
        status=status.HTTP_200_OK,
    )


# ======================================================================
# GET  /api/v1/events/          — danh sách (mọi user đã đăng nhập)
# POST /api/v1/events/          — tạo sự kiện (BCN/ADMIN)
# ======================================================================
class EventListCreateView(APIView):
    """Danh sách & tạo sự kiện. Lọc ?trang_thai= ?loai_hd=; sort whitelist."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Danh sách sự kiện",
        description="Lọc theo `trang_thai`, `loai_hd`; sắp xếp qua `sort` (whitelist).",
        responses=ActivityEventListSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request):
        # Filter whitelist theo choices — giá trị lạ bị bỏ qua (None → repo bỏ filter)
        trang_thai = request.query_params.get("trang_thai")
        if trang_thai and trang_thai not in ActivityEvent.TrangThai.values:
            trang_thai = None
        loai_hd = request.query_params.get("loai_hd")
        if loai_hd and loai_hd not in ActivityEvent.LoaiHoatDong.values:
            loai_hd = None

        sort = request.query_params.get("sort", "-thoi_gian_bat_dau")
        if sort not in EVENT_SORT_WHITELIST:
            sort = "-thoi_gian_bat_dau"

        queryset = EventService.list_events(trang_thai=trang_thai, loai_hd=loai_hd, sort=sort)

        paginator = StandardPagination()
        page_items = paginator.paginate_queryset(queryset, request, view=self)
        items = ActivityEventListSerializer(page_items, many=True).data
        return _paginated_envelope(items, paginator.page, "Lấy danh sách sự kiện thành công")

    @extend_schema(
        summary="Tạo sự kiện (BCN/ADMIN)",
        description="ma_hd tự sinh (EV{năm}{seq}); validate thời gian; hỗ trợ nested budget_details.",
        request=ActivityEventCreateUpdateSerializer,
        responses=ActivityEventDetailSerializer,
        tags=["Events"],
    )
    def post(self, request):
        serializer = ActivityEventCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = EventService.create_event(serializer.validated_data, actor=request.user)
        # context request BẮT BUỘC — serializer lọc PII (created_by_email) theo vai trò
        data = ActivityEventDetailSerializer(event, context={"request": request}).data
        return Response(
            {"success": True, "data": data, "message": "Tạo sự kiện thành công", "errors": None},
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# GET / PUT / PATCH /api/v1/events/<id>/
# ======================================================================
class EventDetailView(APIView):
    """Chi tiết sự kiện (auth) — cập nhật chỉ BCN/ADMIN."""

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(summary="Chi tiết sự kiện", responses=ActivityEventDetailSerializer, tags=["Events"])
    def get(self, request, pk: int):
        event = EventService.get_event_or_404(pk)
        return Response(
            {
                "success": True,
                "data": ActivityEventDetailSerializer(event, context={"request": request}).data,
                "message": "Lấy chi tiết sự kiện thành công",
                "errors": None,
            }
        )

    @extend_schema(
        summary="Cập nhật sự kiện (BCN/ADMIN)",
        description="PUT full / PATCH partial. BCN có thể chuyển `trang_thai` sang OPEN_REGISTRATION.",
        request=ActivityEventCreateUpdateSerializer,
        responses=ActivityEventDetailSerializer,
        tags=["Events"],
    )
    def put(self, request, pk: int):
        return self._update(request, pk, partial=False)

    @extend_schema(
        summary="Cập nhật một phần sự kiện (BCN/ADMIN)",
        request=ActivityEventCreateUpdateSerializer,
        responses=ActivityEventDetailSerializer,
        tags=["Events"],
    )
    def patch(self, request, pk: int):
        return self._update(request, pk, partial=True)

    def _update(self, request, pk: int, partial: bool) -> Response:
        event = EventService.get_event_or_404(pk)
        serializer = ActivityEventCreateUpdateSerializer(event, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        event = EventService.update_event(event, serializer.validated_data)
        return Response(
            {
                "success": True,
                "data": ActivityEventDetailSerializer(event, context={"request": request}).data,
                "message": "Cập nhật sự kiện thành công",
                "errors": None,
            }
        )


# ======================================================================
# GET  /api/v1/events/<id>/tasks/   — kế hoạch DAG (auth)
# POST /api/v1/events/<id>/tasks/   — tạo task (BCN/ADMIN, validate DAG)
# ======================================================================
class EventTaskListCreateView(APIView):
    """Quản lý công việc DAG của sự kiện. GET trả execution plan đầy đủ."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Kế hoạch task DAG của sự kiện",
        description="Trả tasks + topological_order + cycle (nếu deadlock) + executable_now.",
        responses=EventTaskSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request, pk: int):
        # 404 trước, 403 sau (QA-Audit P3: kế hoạch DAG chỉ dành cho BCN hoặc
        # người tham gia sự kiện — được giao task hoặc có vé hiệu lực)
        event = EventService.get_event_or_404(pk)
        EventTaskService.assert_can_view_plan(request.user, event)
        plan = EventTaskService.get_execution_plan(pk)
        return Response(
            {
                "success": True,
                "data": plan,
                "message": "Lấy kế hoạch task (DAG) thành công",
                "errors": None,
            }
        )

    @extend_schema(
        summary="Tạo task mới (BCN/ADMIN)",
        description="Set `depends_on` rồi validate DAG; phụ thuộc vòng tròn → 400 CycleDetected.",
        request=EventTaskSerializer,
        responses=EventTaskSerializer,
        tags=["Events"],
    )
    def post(self, request, pk: int):
        serializer = EventTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        task = EventTaskService.create_task(
            event_id=pk,
            ten_task=vd["ten_task"],
            nguoi_phu_trach_id=vd["nguoi_phu_trach"].id if vd.get("nguoi_phu_trach") else None,
            depends_on_ids=vd.get("depends_on") or [],
            deadline=vd.get("deadline"),
        )
        data = EventTaskSerializer(task).data
        return Response(
            {"success": True, "data": data, "message": "Đã tạo task và kiểm tra DAG thành công", "errors": None},
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# PATCH /api/v1/events/<id>/tasks/<task_id>/ — cập nhật trạng thái task
# (đánh dấu hoàn thành → cộng XP cho người phụ trách qua complete_task)
# ======================================================================
class EventTaskDetailView(APIView):
    """Cập nhật task — CHỈ BCN/ADMIN hoặc người phụ trách (QA-Audit P1-1);
    đủ điều kiện DAG (tiền nhiệm đã xong) mới được tích hoàn thành."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cập nhật task (đánh dấu hoàn thành / mở lại)",
        description=(
            "Body: {is_completed: bool}. is_completed=true cộng XP người phụ "
            "trách. Chỉ BCN/ADMIN hoặc chính người phụ trách được gọi; task "
            "còn tiền nhiệm chưa hoàn thành sẽ bị từ chối (400)."
        ),
        request=None,
        responses=EventTaskSerializer,
        tags=["Events"],
    )
    def patch(self, request, pk: int, task_id: int):
        task = EventTaskService.get_task_or_404(task_id, event_id=pk)
        # Phân quyền object-level: BCN/ADMIN hoặc đúng người phụ trách (403)
        EventTaskService.assert_can_update(request.user, task)

        is_completed = request.data.get("is_completed")
        if not isinstance(is_completed, bool):
            raise ValidationException("Trường 'is_completed' bắt buộc là boolean.")

        if is_completed and not task.is_completed:
            task = EventTaskService.complete_task(task_id)
        elif is_completed is False and task.is_completed:
            task = EventTaskService.reopen_task(task)

        data = EventTaskSerializer(task).data
        return Response(
            {
                "success": True,
                "data": data,
                "message": "Đã cập nhật trạng thái task",
                "errors": None,
            }
        )


# ======================================================================
# GET /api/v1/events/<id>/tasks/topological-order/
# ======================================================================
class TaskOrderView(APIView):
    """Thứ tự thực thi topo (Kahn) — dùng vẽ sơ đồ Gantt/progress BCN."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Thứ tự topological của task (DAG)",
        responses=EventTaskSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request, pk: int):
        # Ràng buộc quyền như EventTaskListCreateView.get (QA-Audit P3)
        event = EventService.get_event_or_404(pk)
        EventTaskService.assert_can_view_plan(request.user, event)
        plan = EventTaskService.get_execution_plan(pk)
        data = {
            "topological_order": plan["topological_order"],
            "is_valid_dag": plan["is_valid_dag"],
            "cycle": plan["cycle"],
        }
        return Response(
            {
                "success": True,
                "data": data,
                "message": "Lấy thứ tự thực thi (topological order) thành công",
                "errors": None,
            }
        )


# ======================================================================
# GET /api/v1/events/my-tickets/ — vé điện tử của CHÍNH TÔI (MEMBER)
# ======================================================================
class MyTicketsView(APIView):
    """Vé điện tử của người gọi — phục vụ trang member/events.html render QR."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Vé sự kiện của tôi",
        description="Danh sách EventRegistration của chính người gọi (mới nhất trước).",
        responses=EventRegistrationSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request):
        member = EventService.get_member_profile_or_forbidden(request.user)
        tickets = EventService.list_tickets_for_member(member)
        data = EventRegistrationSerializer(tickets, many=True).data
        return Response(
            {
                "success": True,
                "data": data,
                "message": "Lấy vé của tôi thành công",
                "errors": None,
            }
        )


# ======================================================================
# POST /api/v1/events/<id>/register/       — member đăng ký vé
# POST /api/v1/events/<id>/cancel-registration/ — member hủy vé
# ======================================================================
class EventRegisterView(APIView):
    """Đăng ký vé sự kiện (chỉ MEMBER có hồ sơ) — chống oversell bằng lock."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Đăng ký vé sự kiện",
        description="Trả về mã vé điện tử (QR) khi sự kiện OPEN_REGISTRATION và còn chỗ.",
        # request=None: POST không nhận body (chỉ cần pk trên path) — tránh
        # drf-spectacular đoán sai serializer cho APIView thuần.
        request=None,
        responses=EventRegistrationSerializer,
        tags=["Events"],
    )
    def post(self, request, pk: int):
        member = EventService.get_member_profile_or_forbidden(request.user)
        registration = EventService.register_member(event_id=pk, member=member)
        return Response(
            {
                "success": True,
                "data": EventRegistrationSerializer(registration).data,
                "message": "Đăng ký thành công! Vé điện tử đã sẵn sàng.",
                "errors": None,
            },
            status=status.HTTP_201_CREATED,
        )


class CancelRegistrationView(APIView):
    """Hủy vé của chính mình — giải phóng chỗ cho thành viên khác."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Hủy vé sự kiện của chính mình",
        # request=None: POST không nhận body (chỉ cần pk trên path) — tránh
        # drf-spectacular đoán sai serializer cho APIView thuần.
        request=None,
        responses=EventRegistrationSerializer,
        tags=["Events"],
    )
    def post(self, request, pk: int):
        member = EventService.get_member_profile_or_forbidden(request.user)
        registration = EventService.cancel_registration(event_id=pk, member=member)
        return Response(
            {
                "success": True,
                "data": EventRegistrationSerializer(registration).data,
                "message": "Đã hủy vé. Chỗ của bạn đã được giải phóng cho người khác.",
                "errors": None,
            }
        )


# ======================================================================
# GET /api/v1/events/<id>/registrations/  — BCN xem danh sách vé
# ======================================================================
class EventRegistrationListView(APIView):
    """Danh sách vé của sự kiện — chỉ BCN/ADMIN (chống lộ dữ liệu member)."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        summary="Danh sách vé sự kiện (BCN/ADMIN)",
        responses=EventRegistrationSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request, pk: int):
        event = EventService.get_event_or_404(pk)
        queryset = EventService.list_registrations(event)
        paginator = StandardPagination()
        page_items = paginator.paginate_queryset(queryset, request, view=self)
        items = EventRegistrationSerializer(page_items, many=True).data
        return _paginated_envelope(items, paginator.page, "Lấy danh sách vé thành công")


# ======================================================================
# GET / POST /api/v1/events/<id>/budget/
# ======================================================================
class BudgetView(APIView):
    """Dự trù kinh phí: xem (auth) / thêm hạng mục (BCN) — tổng tự động."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Danh sách hạng mục dự trù kinh phí",
        responses=EventBudgetDetailSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request, pk: int):
        event = EventService.get_event_or_404(pk)
        items = EventBudgetDetailSerializer(EventService.list_budget_details(event), many=True).data
        return Response(
            {
                "success": True,
                "data": {"items": items, "tong_kinh_phi_du_tru": event.tong_kinh_phi_du_tru},
                "message": "Lấy dự trù kinh phí thành công",
                "errors": None,
            }
        )

    @extend_schema(
        summary="Thêm hạng mục dự trù kinh phí (BCN/ADMIN)",
        description="Tổng `tong_kinh_phi_du_tru` của sự kiện được tính lại tự động.",
        request=EventBudgetDetailSerializer,
        responses=EventBudgetDetailSerializer,
        tags=["Events"],
    )
    def post(self, request, pk: int):
        event = EventService.get_event_or_404(pk)  # 404 phải trước 400 (validate payload)
        serializer = EventBudgetDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item, event = EventService.add_budget_item(event, serializer.validated_data)
        data = EventBudgetDetailSerializer(item).data
        data["tong_kinh_phi_du_tru"] = event.tong_kinh_phi_du_tru
        return Response(
            {"success": True, "data": data, "message": "Đã thêm hạng mục dự trù kinh phí", "errors": None},
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# GET / POST /api/v1/events/<id>/communications/
# ======================================================================
class CommunicationView(APIView):
    """Kế hoạch truyền thông đa kênh: xem (auth) / thêm (BCN)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Kế hoạch truyền thông của sự kiện",
        responses=EventCommunicationSerializer(many=True),
        tags=["Events"],
    )
    def get(self, request, pk: int):
        event = EventService.get_event_or_404(pk)
        items = EventCommunicationSerializer(EventService.list_communications(event), many=True).data
        return Response(
            {
                "success": True,
                "data": {"items": items},
                "message": "Lấy kế hoạch truyền thông thành công",
                "errors": None,
            }
        )

    @extend_schema(
        summary="Thêm kế hoạch truyền thông (BCN/ADMIN)",
        request=EventCommunicationSerializer,
        responses=EventCommunicationSerializer,
        tags=["Events"],
    )
    def post(self, request, pk: int):
        EventService.get_event_or_404(pk)  # đảm bảo sự kiện tồn tại → 404 nếu không
        serializer = EventCommunicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comm = EventService.add_communication(event_id=pk, data=serializer.validated_data)
        return Response(
            {
                "success": True,
                "data": EventCommunicationSerializer(comm).data,
                "message": "Đã thêm kế hoạch truyền thông",
                "errors": None,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyTicketView(APIView):
    """POST /api/v1/events/{pk}/verify-ticket/ — quét/kiểm tra vé tại cổng."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        tags=["Events"],
        summary="Xác minh vé tại cổng sự kiện (BCN)",
        description=(
            "BCN quét QR hoặc nhập tay mã vé → check-in thành viên. "
            "404 = vé không tồn tại/không thuộc sự kiện; 400 = vé đã hủy; "
            "409 = vé đã quét trước đó. Kèm mã vé trong body."
        ),
        request=TicketVerifySerializer,
        responses={200: None, 400: None, 404: None, 409: None},
    )
    def post(self, request, pk: int) -> Response:
        serializer = TicketVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = EventService.verify_ticket(pk, serializer.validated_data["ma_ve"])
        return Response(
            {
                "success": True,
                "data": result,
                "message": f"Đã xác nhận — {result['member_name']} vào cổng.",
                "errors": None,
            }
        )
