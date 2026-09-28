"""
Serializers — apps.members
Chỉ validate/transform JSON — KHÔNG chứa business logic (Clean Layered).
"""
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.members.models import BoardMember, MemberProfile

User = get_user_model()


class MemberProfileListSerializer(serializers.ModelSerializer):
    """Danh sách thành viên (đọc)."""

    mssv = serializers.CharField(source="user.mssv", read_only=True, default=None)
    email = serializers.CharField(source="user.email", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = MemberProfile
        fields = [
            "id", "mssv", "ho_ten", "email", "lop", "sdt", "gioi_tinh",
            "avatar", "xp_points", "current_level", "streak_count",
            "trang_thai_hd", "is_active", "created_at",
        ]
        read_only_fields = fields


class MemberCreateSerializer(serializers.Serializer):
    """POST /members/ — tạo thành viên (BCN)."""

    email = serializers.EmailField(max_length=254)
    mssv = serializers.CharField(max_length=20)
    ho_ten = serializers.CharField(max_length=150)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        help_text="Để trống sẽ dùng mật khẩu mặc định CLBIP@2026",
    )
    lop = serializers.CharField(max_length=50, required=False, allow_blank=True)
    sdt = serializers.CharField(max_length=15, required=False, allow_blank=True)
    gioi_tinh = serializers.ChoiceField(
        choices=["NAM", "NU", "KHAC"], required=False, allow_blank=True
    )
    ngay_sinh = serializers.DateField(required=False, allow_null=True)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_password(self, value: str) -> str:
        if value:
            validate_password(value)
        return value

    def validate_mssv(self, value: str) -> str:
        if User.objects.filter(mssv=value.strip()).exists():
            raise serializers.ValidationError(f"MSSV {value} đã tồn tại.")
        return value.strip()

    def validate_email_unique(self, value: str) -> str:
        if User.objects.filter(email=value.strip().lower()).exists():
            raise serializers.ValidationError(f"Email {value} đã được sử dụng.")
        return value


class MemberUpdateSerializer(serializers.Serializer):
    """PUT/PATCH /members/{id}/ — cập nhật hồ sơ. Member tự sửa bị chặn các field nhạy cảm."""

    email = serializers.EmailField(required=False)
    mssv = serializers.CharField(max_length=20, required=False)
    ho_ten = serializers.CharField(max_length=150, required=False)
    lop = serializers.CharField(max_length=50, required=False, allow_blank=True)
    sdt = serializers.CharField(max_length=15, required=False, allow_blank=True)
    gioi_tinh = serializers.ChoiceField(
        choices=["NAM", "NU", "KHAC"], required=False, allow_blank=True
    )
    ngay_sinh = serializers.DateField(required=False, allow_null=True)
    trang_thai_hd = serializers.ChoiceField(
        choices=["ACTIVE", "INACTIVE", "LEAVE"], required=False
    )
    role = serializers.ChoiceField(
        choices=["ADMIN", "BCN", "MEMBER"], required=False
    )

    def validate(self, attrs: dict) -> dict:
        request = self.context.get("request")
        if request is not None and not request.user.is_bcn:
            forbidden = {"email", "mssv", "trang_thai_hd", "role"}
            violated = forbidden & set(attrs)
            if violated:
                raise serializers.ValidationError(
                    f"Bạn không có quyền sửa các trường: {', '.join(sorted(violated))}."
                )
        return attrs


class BoardMemberSerializer(serializers.ModelSerializer):
    """Cơ cấu Ban Chủ Nhiệm."""

    member_ho_ten = serializers.CharField(source="member.ho_ten", read_only=True)
    member_mssv = serializers.CharField(source="member.user.mssv", read_only=True, default=None)
    chuc_vu_display = serializers.CharField(source="get_chuc_vu_display", read_only=True)
    ban_phu_trach_display = serializers.CharField(source="get_ban_phu_trach_display", read_only=True)

    class Meta:
        model = BoardMember
        fields = [
            "id", "member", "member_ho_ten", "member_mssv", "nhiem_ky",
            "chuc_vu", "chuc_vu_display", "ban_phu_trach", "ban_phu_trach_display",
        ]

    def validate_member(self, value: MemberProfile) -> MemberProfile:
        nhiem_ky = self.initial_data.get("nhiem_ky", "2025-2026")
        if BoardMember.objects.filter(member=value, nhiem_ky=nhiem_ky).exclude(
            pk=self.instance.pk if self.instance else None
        ).exists():
            raise serializers.ValidationError(
                "Thành viên này đã có chức vụ trong nhiệm kỳ đã chọn."
            )
        return value


class MemberExcelImportSerializer(serializers.Serializer):
    """POST /members/import-excel/ — file .xlsx."""

    file = serializers.FileField()

    def validate_file(self, value) -> Any:
        if not value.name.lower().endswith(".xlsx"):
            raise serializers.ValidationError("Chỉ chấp nhận file .xlsx.")
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("File Excel không được vượt quá 5MB.")
        return value
