"""
Serializer Layer — apps.funds
=============================
Serializer CHỈ validate / transform dữ liệu (SKILL.md — SRP), KHÔNG chứa logic
ghi DB. Mọi nghiệp vụ nằm ở `FundService`.

Lưu ý bảo mật (Server-Authoritative + chống sửa lịch sử):
    - `ma_phieu`, `so_du_sau`, `is_locked` là read_only: client không được tự gán.
    - `so_tien` buộc >= 1: chặn phiếu 0đ / âm ngay tầng vào.
"""
from rest_framework import serializers

from apps.events.models import ActivityEvent
from apps.funds.models import FundPeriodLock, FundTransaction


class FundTransactionSerializer(serializers.ModelSerializer):
    """Serializer ĐỌC sổ quỹ — toàn bộ trường trừ `hoa_don` (file nhạy cảm)."""

    ma_phieu = serializers.CharField(read_only=True)
    so_du_sau = serializers.IntegerField(read_only=True)
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = FundTransaction
        fields = [
            "id",
            "ma_phieu",
            "loai_gd",
            "so_tien",
            "so_du_sau",
            "nguoi_thuc_hien",
            "hinh_thuc",
            "ngay_gd",
            "ghi_chu",
            "is_locked",
            "event",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "ma_phieu", "so_du_sau", "is_locked"]


class FundTransactionCreateSerializer(serializers.ModelSerializer):
    """
    Serializer GHI phiếu thu/chi — payload đầu vào của POST /api/v1/funds/.

    Client KHÔNG được gửi ma_phieu / so_du_sau — chúng do Service sinh và
    kiểm soát tuyệt đối (Server-Authoritative).
    """

    loai_gd = serializers.ChoiceField(
        choices=FundTransaction.LoaiGiaoDich.choices,
        help_text="Loại giao dịch: THU (thu) hoặc CHI (chi).",
    )
    so_tien = serializers.IntegerField(
        min_value=1,
        help_text="Số tiền VNĐ, bắt buộc >= 1.",
    )
    nguoi_thuc_hien = serializers.CharField(max_length=150)
    hinh_thuc = serializers.ChoiceField(
        choices=FundTransaction.HinhThuc.choices,
        default=FundTransaction.HinhThuc.TIEN_MAT,
    )
    ngay_gd = serializers.DateTimeField(required=False, allow_null=True)
    ghi_chu = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        default="",
        style={"base_template": "textarea.html"},
    )
    event = serializers.PrimaryKeyRelatedField(
        queryset=ActivityEvent.objects.all(),
        required=False,
        allow_null=True,
        help_text="ID sự kiện liên quan (tùy chọn).",
    )

    # QA-Audit nhóm 3: chống double-submit — client có thể gửi khóa trong body
    # (ưu tiên header "Idempotency-Key" nếu có cả hai)
    idempotency_key = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        max_length=64,
        help_text="Khóa chống ghi trùng (tùy chọn, tối đa 64 ký tự).",
    )

    class Meta:
        model = FundTransaction
        fields = [
            "loai_gd",
            "so_tien",
            "nguoi_thuc_hien",
            "hinh_thuc",
            "ngay_gd",
            "ghi_chu",
            "event",
            "idempotency_key",
        ]


class FundPeriodLockSerializer(serializers.ModelSerializer):
    """Serializer kỳ khóa sổ — dùng cho POST /lock-period/ và GET /locks/."""

    locked_by = serializers.StringRelatedField(read_only=True)
    locked_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = FundPeriodLock
        fields = ["id", "ten_ky", "tu_ngay", "den_ngay", "locked_by", "locked_at", "ghi_chu"]
        read_only_fields = ["id", "locked_by", "locked_at"]
