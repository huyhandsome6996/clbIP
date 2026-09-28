"""
Serializer Layer — apps.gamification
====================================
Serializer CHỈ validate / transform (SRP). XP / Leaderboard trả dict trực tiếp
từ Service (không cần serializer trung gian).
"""
from rest_framework import serializers

from apps.gamification.models import Badge, MemberBadge


class BadgeSerializer(serializers.ModelSerializer):
    """Serializer huy hiệu (định nghĩa badge)."""

    class Meta:
        model = Badge
        fields = ["id", "ma_badge", "ten_badge", "mo_ta", "icon"]


class MemberBadgeSerializer(serializers.ModelSerializer):
    """Huy hiệu thành viên — badge lồng nhau (read-only)."""

    badge = BadgeSerializer(read_only=True)

    class Meta:
        model = MemberBadge
        fields = ["id", "badge", "awarded_at"]
