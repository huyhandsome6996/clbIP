"""
Serializers — apps.authentication
JWT login bằng email + payload bổ sung thông tin user/role.
"""
from typing import Any, Optional

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.authentication.models import User


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Serializer đăng nhập JWT:
    - Nhận {email, password} (USERNAME_FIELD = email).
    - Thêm claim "role" vào access/refresh token.
    - Response bổ sung data.user {id, email, role, ho_ten, avatar}.
    """

    @classmethod
    def get_token(cls, user: User):
        token = super().get_token(user)
        token["role"] = user.role
        token["email"] = user.email
        return token

    def validate(self, attrs: dict) -> dict:
        data = super().validate(attrs)
        profile = getattr(self.user, "member_profile", None)
        data["user"] = {
            "id": self.user.pk,
            "email": self.user.email,
            "role": self.user.role,
            "is_superuser": self.user.is_superuser,
            "ho_ten": profile.ho_ten if profile else self.user.username,
            "avatar": profile.avatar if profile else "",
            "mssv": self.user.mssv,
        }
        return data


class UserSerializer(serializers.ModelSerializer):
    """Serializer user dùng chung (đọc)."""

    class Meta:
        model = User
        fields = ["id", "email", "mssv", "role", "is_active", "date_joined"]
        read_only_fields = ["id", "email", "mssv", "date_joined"]


class MeSerializer(serializers.ModelSerializer):
    """GET /auth/me/ — user + hồ sơ thành viên (nếu có)."""

    ho_ten = serializers.CharField(source="member_profile.ho_ten", read_only=True, default=None)
    avatar = serializers.CharField(source="member_profile.avatar", read_only=True, default="")
    lop = serializers.CharField(source="member_profile.lop", read_only=True, default="")
    xp_points = serializers.IntegerField(
        source="member_profile.xp_points", read_only=True, default=None
    )
    current_level = serializers.IntegerField(
        source="member_profile.current_level", read_only=True, default=None
    )
    streak_count = serializers.IntegerField(
        source="member_profile.streak_count", read_only=True, default=None
    )
    trang_thai_hd = serializers.CharField(
        source="member_profile.trang_thai_hd", read_only=True, default=None
    )

    class Meta:
        model = User
        fields = [
            "id", "email", "mssv", "role", "is_active",
            "ho_ten", "avatar", "lop",
            "xp_points", "current_level", "streak_count", "trang_thai_hd",
            "date_joined",
        ]
