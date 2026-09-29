"""
Views — Attendance API (prefix /api/v1/attendance/).
====================================================
View mỏng: nhận HTTP request → gọi AttendanceService → trả envelope chuẩn.
Check-in áp CheckInRateThrottle (3 lần/phút — chống spam, Security §3.1).
"""
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance.serializers import (
    AttendanceRecordSerializer,
    AttendanceSessionSerializer,
    BulkOverrideSerializer,
    CheckInSerializer,
    SessionCreateSerializer,
)
from apps.attendance.services import AttendanceNonceService, AttendanceService
from apps.common.throttles import CheckInRateThrottle
from apps.attendance.services.attendance_service import LATE_AFTER_MINUTES
from core.pagination import StandardPagination
from core.permissions import IsBCNOrAdmin


def _paginated_envelope(items: list, page, message: str) -> Response:
    """
    Đóng gói kết quả phân trang vào envelope chuẩn {success,data,message,errors}.
    (Bản địa cho app attendance — items đã serialize, cùng shape data.items/pagination.)
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
# GET  /api/v1/attendance/sessions/  — danh sách phiên (auth)
# POST /api/v1/attendance/sessions/  — mở phiên (BCN/ADMIN)
# ======================================================================
class SessionListCreateView(APIView):
    """Quản lý phiên điểm danh GPS."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBCNOrAdmin()]
        return [IsAuthenticated()]

    @extend_schema(
        summary="Danh sách phiên điểm danh",
        description="Lọc `?trang_thai=OPEN|CLOSED` (whitelist choices).",
        responses=AttendanceSessionSerializer(many=True),
        tags=["Attendance"],
    )
    def get(self, request):
        # QuerySet do repository cung cấp (whitelist trang_thai nằm trong repo)
        queryset = AttendanceService.list_sessions(request.query_params.get("trang_thai"))

        paginator = StandardPagination()
        page_items = paginator.paginate_queryset(queryset, request, view=self)
        items = AttendanceSessionSerializer(page_items, many=True).data
        return _paginated_envelope(items, paginator.page, "Lấy danh sách phiên thành công")

    @extend_schema(
        summary="Mở phiên điểm danh mới (BCN/ADMIN)",
        description=(
            "Tọa độ tâm là GPS của BCN tại chỗ; hệ thống tự tạo bản ghi VẮNG "
            "cho toàn bộ thành viên ACTIVE và sinh secret cho nonce 60s."
        ),
        request=SessionCreateSerializer,
        responses=AttendanceSessionSerializer,
        tags=["Attendance"],
    )
    def post(self, request):
        serializer = SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data
        session = AttendanceService.open_session(
            ten_phien=vd["ten_phien"],
            vi_do=vd["vi_do"],
            kinh_do=vd["kinh_do"],
            ban_kinh_m=vd.get("ban_kinh_m", 50),
            event_id=vd["event"].id if vd.get("event") else None,
            hieu_luc_den=vd.get("hieu_luc_den"),
            opened_by=request.user,
        )
        return Response(
            {
                "success": True,
                "data": AttendanceSessionSerializer(session).data,
                "message": "Đã mở phiên điểm danh và tạo bản ghi VẮNG cho toàn bộ thành viên",
                "errors": None,
            },
            status=status.HTTP_201_CREATED,
        )


# ======================================================================
# GET /api/v1/attendance/sessions/<id>/  — chi tiết phiên (auth)
# ======================================================================
class SessionDetailView(APIView):
    """Chi tiết phiên. (Đóng phiên dùng POST /sessions/<id>/close/ riêng.)"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Chi tiết phiên điểm danh",
        responses=AttendanceSessionSerializer,
        tags=["Attendance"],
    )
    def get(self, request, pk: int):
        session = AttendanceService.get_session_or_404(pk)
        return Response(
            {
                "success": True,
                "data": AttendanceSessionSerializer(session).data,
                "message": "Lấy chi tiết phiên thành công",
                "errors": None,
            }
        )


# ======================================================================
# POST /api/v1/attendance/sessions/<id>/close/  — đóng phiên (BCN)
# ======================================================================
class CloseSessionView(APIView):
    """Đóng phiên — chốt danh sách điểm danh."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        summary="Đóng phiên điểm danh (BCN/ADMIN)",
        responses=AttendanceSessionSerializer,
        tags=["Attendance"],
    )
    def post(self, request, pk: int):
        session = AttendanceService.get_session_or_404(pk)
        session = AttendanceService.close_session(session, closed_by=request.user)
        return Response(
            {
                "success": True,
                "data": AttendanceSessionSerializer(session).data,
                "message": "Đã đóng phiên",
                "errors": None,
            }
        )


# ======================================================================
# GET /api/v1/attendance/sessions/<id>/nonce/  — mã nonce máy chiếu (BCN)
# ======================================================================
class SessionNonceView(APIView):
    """Nonce 6 chữ số xoay 60 giây — BCN hiển thị lên máy chiếu."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        summary="Mã nonce động của phiên (BCN/ADMIN)",
        description="Đổi mỗi 60 giây; member phải nhập để check-in (chống đi vắng vẫn điểm danh).",
        responses=AttendanceSessionSerializer,
        tags=["Attendance"],
    )
    def get(self, request, pk: int):
        session = AttendanceService.get_session_or_404(pk)
        nonce_data = AttendanceNonceService.generate(session)
        data = {
            "session_id": session.id,
            "ten_phien": session.ten_phien,
            "trang_thai": session.trang_thai,
            "thoi_han_muon_phut": LATE_AFTER_MINUTES,
            **nonce_data,
        }
        return Response(
            {
                "success": True,
                "data": data,
                "message": "Mã nonce hiện tại — hiển thị lên máy chiếu",
                "errors": None,
            }
        )


# ======================================================================
# POST /api/v1/attendance/check-in/  — member tự check-in GPS
# ======================================================================
class CheckInView(APIView):
    """Check-in GPS qua 7 lớp anti-cheat (mock/accuracy/skew/nonce/device/teleport/radius)."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [CheckInRateThrottle]
    # ScopedRateThrottle đọc scope từ VIEW — thiếu thì rate 3/phút vô hiệu
    throttle_scope = "checkin"

    @extend_schema(
        summary="Check-in điểm danh GPS",
        description=(
            "Nhận tọa độ + client_time + device_id + nonce từ client. "
            "Server tự tính XP (client không gửi XP) và streak 🔥."
        ),
        request=CheckInSerializer,
        responses=AttendanceRecordSerializer,
        tags=["Attendance"],
    )
    def post(self, request):
        serializer = CheckInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = AttendanceService.get_member_profile_or_forbidden(request.user)
        vd = serializer.validated_data

        record = AttendanceService.check_in(
            member=member,
            session_id=vd["session_id"],
            client_lat=vd["latitude"],
            client_lon=vd["longitude"],
            client_time=vd["client_time"],
            device_id=vd["device_id"],
            nonce=vd["nonce"],
            is_mock=vd.get("is_mock", False),
            accuracy=vd.get("accuracy"),
        )

        data = AttendanceRecordSerializer(record).data
        data["xp_gained"] = record.xp_awarded
        data["streak_count"] = member.streak_count
        return Response(
            {
                "success": True,
                "data": data,
                "message": "Điểm danh thành công!",
                "errors": None,
            }
        )


# ======================================================================
# PUT /api/v1/attendance/sessions/<id>/bulk-override/  — BCN override
# ======================================================================
class BulkOverrideView(APIView):
    """Cập nhật thủ công hàng loạt (điện thoại hết pin, lỗi định vị...)."""

    permission_classes = [IsBCNOrAdmin]

    @extend_schema(
        summary="Cập nhật thủ công hàng loạt trạng thái (BCN/ADMIN)",
        request=BulkOverrideSerializer,
        responses=AttendanceRecordSerializer(many=True),
        tags=["Attendance"],
    )
    def put(self, request, pk: int):
        session = AttendanceService.get_session_or_404(pk)
        serializer = BulkOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = AttendanceService.bulk_override(
            session=session, items=serializer.validated_data["items"], actor=request.user
        )
        return Response(
            {
                "success": True,
                "data": {"updated": updated},
                "message": f"Đã cập nhật thủ công {updated} bản ghi điểm danh.",
                "errors": None,
            }
        )


# ======================================================================
# GET /api/v1/attendance/me/  — lịch sử điểm danh của CHÍNH MÌNH
# ======================================================================
class MyAttendanceHistoryView(APIView):
    """Lịch sử điểm danh cá nhân — chống IDOR: CHỈ trả record của chính mình."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Lịch sử điểm danh của tôi (tối đa 50 bản ghi mới nhất)",
        responses=AttendanceRecordSerializer(many=True),
        tags=["Attendance"],
    )
    def get(self, request):
        member = AttendanceService.get_member_profile_or_forbidden(request.user)
        # Chống IDOR: repository chỉ trả record của CHÍNH member này (limit 50)
        records = AttendanceService.history_for_member(member)
        items = AttendanceRecordSerializer(records, many=True).data
        return Response(
            {
                "success": True,
                "data": {"items": items},
                "message": "Lấy lịch sử điểm danh thành công",
                "errors": None,
            }
        )
