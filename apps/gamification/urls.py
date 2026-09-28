"""
URLs — apps.gamification (mounted tại /api/v1/gamification/)
============================================================
Mọi user đăng nhập đều được xem (Server-Authoritative: không endpoint nhận XP).
"""
from django.urls import path

from apps.gamification.views import BadgeListView, LeaderboardView, MyGamificationView

urlpatterns = [
    path("leaderboard/", LeaderboardView.as_view(), name="gamification_leaderboard"),
    path("badges/", BadgeListView.as_view(), name="gamification_badges"),
    path("me/", MyGamificationView.as_view(), name="gamification_me"),
]
