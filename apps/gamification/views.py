"""
View Layer (Controller) — apps.gamification
===========================================
View MỎNG: nhận request → gọi Service → trả envelope `core.response.ok`.
100% truy vấn CSDL nằm ở `apps.gamification.repositories` (Repository Pattern,
mẫu apps.funds) — View chỉ truy cập dữ liệu qua module-level `_repo()` (DI bằng
cách gán `_repository_class`).

Phân quyền: MỌI user đăng nhập đều được XEM (leaderboard/badge/me) —
`IsAuthenticated` khai báo tường minh.
Server-Authoritative: KHÔNG có endpoint nào nhận `xp` từ client.
"""
from typing import ClassVar

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.exceptions import NotFoundException
from apps.gamification.repositories import (
    DjangoGamificationRepository,
    IGamificationRepository,
)
from apps.gamification.serializers import MemberBadgeSerializer
from apps.gamification.services import (
    BadgeService,
    GamificationService,
    LeaderboardService,
)
from core.response import ok

_repository_class: ClassVar[type[IGamificationRepository]] = (
    DjangoGamificationRepository
)


def _repo() -> IGamificationRepository:
    """Repository accessor cho tầng View — cho phép DI khi unit test."""
    return _repository_class()


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
        profile = _repo().find_member_profile_by_user(request.user)
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
        """Service gom badge toàn hệ thống + trạng thái mở khóa của user."""
        profile = _repo().find_member_profile_by_user(request.user)
        data = BadgeService.list_badges_with_status(profile)
        return ok(
            data=data,
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
        profile = _repo().find_member_profile_by_user(request.user)
        if profile is None:
            raise NotFoundException("Bạn chưa có hồ sơ thành viên trong hệ thống.")

        unlocked_badges = _repo().list_member_badges(profile)
        data = {
            "xp": profile.xp_points,
            "level": profile.current_level,
            "streak_count": profile.streak_count,
            "badges": [MemberBadgeSerializer(mb).data for mb in unlocked_badges],
            "weekly_quests": GamificationService.get_weekly_quests(profile),
        }
        return ok(data=data, message="Lấy thông tin gamification thành công")
