"""
Serializers — Events: chỉ chuyển đổi dữ liệu (không chứa logic nghiệp vụ).
"""
from rest_framework import serializers

from apps.events.models import (
    ActivityEvent,
    EventBudgetDetail,
    EventCommunication,
    EventRegistration,
    EventTask,
)
from apps.members.models import MemberProfile


# ----------------------------------------------------------------------
# Budget (định nghĩa trước vì dùng nested trong Event)
# ----------------------------------------------------------------------
class EventBudgetDetailSerializer(serializers.ModelSerializer):
    """Hạng mục dự trù kinh phí của sự kiện."""

    class Meta:
        model = EventBudgetDetail
        fields = ["id", "ten_hang_muc", "so_tien", "ghi_chu"]


class BudgetDetailWriteSerializer(serializers.ModelSerializer):
    """Hạng mục kinh phí — dùng cho nested write (không nhận id)."""

    class Meta:
        model = EventBudgetDetail
        fields = ["ten_hang_muc", "so_tien", "ghi_chu"]
        extra_kwargs = {"ghi_chu": {"required": False, "default": ""}}


# ----------------------------------------------------------------------
# ActivityEvent
# ----------------------------------------------------------------------
class ActivityEventListSerializer(serializers.ModelSerializer):
    """Danh sách sự kiện — kèm số đăng ký đang hiệu lực (không tính CANCELLED)."""

    registered_count = serializers.SerializerMethodField()

    class Meta:
        model = ActivityEvent
        fields = [
            "id",
            "ma_hd",
            "ten_hoat_dong",
            "loai_hd",
            "thoi_gian_bat_dau",
            "thoi_gian_ket_thuc",
            "dia_diem",
            "trang_thai",
            "so_luong_toi_da",
            "tong_kinh_phi_du_tru",
            "poster",
            "registered_count",
        ]

    def get_registered_count(self, obj: ActivityEvent) -> int:
        """Ưu tiên annotation `active_reg_count` (tránh N+1); fallback query."""
        annotated = getattr(obj, "active_reg_count", None)
        if annotated is not None:
            return annotated
        return obj.registrations.exclude(
            trang_thai=EventRegistration.TrangThai.CANCELLED
        ).count()


class ActivityEventDetailSerializer(serializers.ModelSerializer):
    """Chi tiết sự kiện — đủ tọa độ GPS, mô tả và bảng dự trù kinh phí."""

    registered_count = serializers.SerializerMethodField()
    budget_details = EventBudgetDetailSerializer(many=True, read_only=True)
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = ActivityEvent
        fields = [
            "id",
            "ma_hd",
            "ten_hoat_dong",
            "mo_ta",
            "loai_hd",
            "thoi_gian_bat_dau",
            "thoi_gian_ket_thuc",
            "dia_diem",
            "vi_do",
            "kinh_do",
            "ban_kinh_m",
            "trang_thai",
            "so_luong_toi_da",
            "tong_kinh_phi_du_tru",
            "poster",
            "registered_count",
            "budget_details",
            "created_by_email",
            "created_at",
            "updated_at",
        ]

    def get_registered_count(self, obj: ActivityEvent) -> int:
        annotated = getattr(obj, "active_reg_count", None)
        if annotated is not None:
            return annotated
        return obj.registrations.exclude(
            trang_thai=EventRegistration.TrangThai.CANCELLED
        ).count()

    def to_representation(self, instance):
        """QA-Audit 2a: email người tạo là PII — chỉ BCN/ADMIN được xem.
        Thành viên thường nhận chi tiết sự kiện mà không có trường này."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not getattr(request.user, "is_bcn", False):
            data.pop("created_by_email", None)
        return data


class ActivityEventCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Write payload cho tạo/cập nhật sự kiện.

    - `trang_thai` optional: BCN dùng để chuyển OPEN_REGISTRATION khi mở bán vé.
    - `budget_details` optional (nested write): tạo kèm hạng mục kinh phí,
      tổng `tong_kinh_phi_du_tru` tự động = tổng các hạng mục (xử lý ở Service).
    """

    budget_details = BudgetDetailWriteSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = ActivityEvent
        fields = [
            "ten_hoat_dong",
            "mo_ta",
            "loai_hd",
            "thoi_gian_bat_dau",
            "thoi_gian_ket_thuc",
            "dia_diem",
            "vi_do",
            "kinh_do",
            "ban_kinh_m",
            "so_luong_toi_da",
            "tong_kinh_phi_du_tru",
            "poster",
            "trang_thai",
            "budget_details",
        ]
        extra_kwargs = {
            "mo_ta": {"required": False},
            "vi_do": {"required": False, "allow_null": True},
            "kinh_do": {"required": False, "allow_null": True},
            "ban_kinh_m": {"required": False},
            "tong_kinh_phi_du_tru": {"required": False},
            "poster": {"required": False, "allow_blank": True},
            "trang_thai": {"required": False},
            "so_luong_toi_da": {"min_value": 1},
        }

    def validate_trang_thai(self, value: str) -> str:
        """Whitelist choices — chống giá trị lạ (Security §2.1)."""
        valid = {choice for choice, _label in ActivityEvent.TrangThai.choices}
        if value not in valid:
            raise serializers.ValidationError("Trạng thái sự kiện không hợp lệ.")
        return value


# ----------------------------------------------------------------------
# EventTask (DAG)
# ----------------------------------------------------------------------
class EventTaskSerializer(serializers.ModelSerializer):
    """
    Task sự kiện.

    - `depends_on`: write_only list id task tiền nhiệm (cùng sự kiện).
    - `depends_on_detail`: read_only chi tiết task tiền nhiệm.
    """

    nguoi_phu_trach = serializers.PrimaryKeyRelatedField(
        queryset=MemberProfile.objects.all(),
        required=False,
        allow_null=True,
    )
    nguoi_phu_trach_ten = serializers.SerializerMethodField()
    depends_on = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    depends_on_detail = serializers.SerializerMethodField()

    class Meta:
        model = EventTask
        fields = [
            "id",
            "event",
            "ten_task",
            "nguoi_phu_trach",
            "nguoi_phu_trach_ten",
            "depends_on",
            "depends_on_detail",
            "is_completed",
            "deadline",
        ]
        read_only_fields = ["event"]

    def get_nguoi_phu_trach_ten(self, obj: EventTask):
        return obj.nguoi_phu_trach.ho_ten if obj.nguoi_phu_trach_id else None

    def get_depends_on_detail(self, obj: EventTask) -> list[dict]:
        return [
            {"id": dep.id, "ten_task": dep.ten_task} for dep in obj.depends_on.all()
        ]


# ----------------------------------------------------------------------
# EventRegistration (Vé điện tử)
# ----------------------------------------------------------------------
class EventRegistrationSerializer(serializers.ModelSerializer):
    """Vé đăng ký sự kiện — mã vé dùng render QR ở frontend."""

    member = serializers.PrimaryKeyRelatedField(read_only=True)
    member_ten = serializers.CharField(source="member.ho_ten", read_only=True)
    event = serializers.PrimaryKeyRelatedField(read_only=True)
    event_ten = serializers.CharField(source="event.ten_hoat_dong", read_only=True)

    class Meta:
        model = EventRegistration
        fields = [
            "id",
            "ma_ve",
            "trang_thai",
            "member",
            "member_ten",
            "event",
            "event_ten",
            "created_at",
        ]


# ----------------------------------------------------------------------
# EventCommunication (Truyền thông đa kênh)
# ----------------------------------------------------------------------
class EventCommunicationSerializer(serializers.ModelSerializer):
    """Kế hoạch truyền thông (Facebook/TikTok/Email/Website) theo sự kiện."""

    event = serializers.PrimaryKeyRelatedField(read_only=True)
    nguoi_phu_trach_ten = serializers.SerializerMethodField()

    class Meta:
        model = EventCommunication
        fields = [
            "id",
            "event",
            "kenh",
            "tieu_de",
            "deadline",
            "link_bai_viet",
            "trang_thai",
            "nguoi_phu_trach",
            "nguoi_phu_trach_ten",
            "created_at",
        ]
        read_only_fields = ["event"]

    def get_nguoi_phu_trach_ten(self, obj: EventCommunication):
        return obj.nguoi_phu_trach.ho_ten if obj.nguoi_phu_trach_id else None
