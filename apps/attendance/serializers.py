"""
Serializers — Attendance: chỉ chuyển đổi dữ liệu (không chứa logic nghiệp vụ).

LƯU Ý BẢO MẬT: CheckInSerializer là INPUT từ client — TUYỆT ĐỐI không chứa
bất kỳ trường XP nào (server-authoritative — Security Hardening §5.2).
nonce_secret của phiên không bao giờ xuất hiện ở output.
"""
from typing import Optional

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.events.repositories import DjangoEventRepository


class AttendanceSessionSerializer(serializers.ModelSerializer):
    """Phiên điểm danh (read) — EXCLUDED nonce_secret (chỉ dùng nội bộ HMAC)."""

    event_ten = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceSession
        exclude = ["nonce_secret"]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_event_ten(self, obj: AttendanceSession) -> Optional[str]:
        return obj.event.ten_hoat_dong if obj.event_id else None


class SessionCreateSerializer(serializers.ModelSerializer):
    """Mở phiên mới: tọa độ tâm (GPS của BCN tại chỗ) + bán kính + hiệu lực."""

    event = serializers.PrimaryKeyRelatedField(
        queryset=DjangoEventRepository().all_events(),  # ORM chỉ nằm ở repository (P3)
        required=False, allow_null=True
    )

    class Meta:
        model = AttendanceSession
        fields = ["ten_phien", "vi_do", "kinh_do", "ban_kinh_m", "event", "hieu_luc_den"]
        extra_kwargs = {
            "ban_kinh_m": {"required": False, "default": 50},
            "hieu_luc_den": {"required": False, "allow_null": True},
        }


class CheckInSerializer(serializers.Serializer):
    """
    INPUT check-in từ client (không chứa XP nào!):

    - session_id: phiên điểm danh đích.
    - latitude/longitude: tọa độ GPS thiết bị.
    - client_time: thời điểm thiết bị ISO 8601 (chống Replay — skew ≤ 60s).
    - device_id: fingerprint thiết bị (UA + screen + hardware hash).
    - nonce: mã 6 chữ số hiển thị trên máy chiếu (xoay 60s).
    - is_mock/accuracy: thuộc tính cảm biến từ OS.
    """

    session_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    client_time = serializers.CharField(max_length=40)
    device_id = serializers.CharField(max_length=128)
    nonce = serializers.CharField(max_length=10)
    is_mock = serializers.BooleanField(default=False, required=False)
    accuracy = serializers.FloatField(required=False, allow_null=True)


class BulkOverrideSerializer(serializers.Serializer):
    """Cập nhật thủ công hàng loạt: items = [{member_id, trang_thai}]."""

    items = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        help_text="Danh sách {member_id, trang_thai: CO_MAT|VANG|CO_PHEP|DI_MUON}",
    )

    def validate_items(self, value: list) -> list:
        """Kiểm tra cấu trúc từng item (service validate giá trị choices)."""
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise serializers.ValidationError(f"items[{idx}] phải là object.")
            if "member_id" not in item or "trang_thai" not in item:
                raise serializers.ValidationError(
                    f"items[{idx}] phải có đủ 'member_id' và 'trang_thai'."
                )
            try:
                int(item["member_id"])
            except (TypeError, ValueError):
                raise serializers.ValidationError(
                    f"items[{idx}].member_id phải là số nguyên."
                )
        return value


class AttendanceRecordSerializer(serializers.ModelSerializer):
    """Bản ghi điểm danh (read) — dùng cho check-in response và /me/ history."""

    member_ten = serializers.CharField(source="member.ho_ten", read_only=True)
    session_ten = serializers.CharField(source="session.ten_phien", read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            "id",
            "session",
            "session_ten",
            "member",
            "member_ten",
            "trang_thai",
            "khoang_cach_m",
            "vi_do",
            "kinh_do",
            "checked_in_at",
            "device_id",
            "is_suspicious",
            "xp_awarded",
            "overridden_by",
            "created_at",
        ]
