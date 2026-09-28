"""
View Layer (Controller) — apps.gamification
===========================================
View MỎNG: nhận request → gọi Service → trả envelope `core.response.ok`.

Phân quyền: MỌI user đăng nhập đều được XEM (leaderboard/badge/me) —
`IsAuthenticated` khai báo tường minh.
Server-Authoritative: KHÔNG có endpoint nào nhận `xp` từ client.
"""
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import NotFoundException
from apps.gamification.models import Badge, MemberBadge
from apps.gamification.serializers import BadgeSerializer, MemberBadgeSerializer
from apps.gamification.services import (
    GamificationService,
    LeaderboardService,
)
from apps.members.models import MemberProfile
from core.response import ok


class LeaderboardView(APIView):
    """GET /api/v1/gamification/leaderboard/ — Bảng vàng Top 10 (Min-Heap) + rank cá nhân."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gamification"],
        summary="Bảng vàng Top 10 XP",
        description=(
            "Top 10 thành viên tích cực nhất tính bằng Min-Heap O(N log K) "
            "(DSA 2) kèm vị trí hiện tại của người gọi và khoảng cách XP tới Top 10."
        ),
        responses={
            200: OpenApiResponse(
                description="Envelope top_10 + my_position + total_members"
            )
        },
    )
    def get(self, request, *args, **kwargs) -> Response:
        """Trả bảng vàng; my_position=None nếu user chưa có hồ sơ thành viên."""
        profile = MemberProfile.objects.filter(user=request.user).first()
        data = LeaderboardService.get_leaderboard(profile)
        return ok(data=data, message="Lấy bảng vàng thành công")


class BadgeListView(APIView):
    """GET /api/v1/gamification/badges/ — toàn bộ huy hiệu + flag unlocked cho user hiện tại."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gamification"],
        summary="Danh sách huy hiệu + trạng thái mở khóa",
        description=(
            "Trả {items: [...badge + unlocked], unlocked: [ma_badge đã mở]} — "
            "một query MemberBadge cho user hiện tại (tránh N+1)."
        ),
        responses={200: OpenApiResponse(description="Envelope items + unlocked")},
    )
    def get(self, request, *args, **kwargs) -> Response:
        """Gom badge toàn hệ thống + trạng thái mở khóa của user (2 query)."""
        profile = MemberProfile.objects.filter(user=request.user).first()
        unlocked_ids: set[int] = set()
        if profile is not None:
            # Một query duy nhất cho MemberBadge của user
            unlocked_ids = set(
                MemberBadge.objects.filter(member=profile).values_list(
                    "badge_id", flat=True
                )
            )

        items: list[dict] = []
        unlocked: list[str] = []
        for badge in Badge.objects.all():
            is_unlocked = badge.pk in unlocked_ids
            item = BadgeSerializer(badge).data
            item["unlocked"] = is_unlocked
            items.append(item)
            if is_unlocked:
                unlocked.append(badge.ma_badge)

        return ok(
            data={"items": items, "unlocked": unlocked},
            message="Lấy danh sách huy hiệu thành công",
        )


class MyGamificationView(APIView):
    """GET /api/v1/gamification/me/ — tổng quan XP / Level / Streak / Badge / Nhiệm vụ tuần."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Gamification"],
        summary="Tổng quan gamification của tôi",
        description=(
            "{xp, level, streak_count, badges (đã mở), weekly_quests} — dùng cho "
            "thanh tiến độ Level và widget Nhiệm vụ tuần kiếm XP."
        ),
        responses={
            200: OpenApiResponse(description="Envelope tổng quan"),
            404: OpenApiResponse(description="User chưa có hồ sơ thành viên"),
        },
    )
    def get(self, request, *args, **kwargs) -> Response:
        """Ghép dữ liệu hồ sơ + badge + nhiệm vụ tuần từ Service."""
        profile = MemberProfile.objects.filter(user=request.user).first()
        if profile is None:
            raise NotFoundException("Bạn chưa có hồ sơ thành viên trong hệ thống.")

        unlocked_badges = profile.badges.select_related("badge").all()
        data = {
            "xp": profile.xp_points,
            "level": profile.current_level,
            "streak_count": profile.streak_count,
            "badges": [MemberBadgeSerializer(mb).data for mb in unlocked_badges],
            "weekly_quests": GamificationService.get_weekly_quests(profile),
        }
        return ok(data=data, message="Lấy thông tin gamification thành công")
