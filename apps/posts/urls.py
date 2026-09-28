"""
URLs — apps.posts (mounted TRỰC TIẾP tại /api/v1/ — không prefix riêng)
========================================================================
Đảm bảo các path posts/, feedback/, polls/ không xung đột app khác.
"""
from django.urls import path

from apps.posts.views import (
    FeedbackView,
    PollListCreateView,
    PollVoteView,
    PostDetailView,
    PostListCreateView,
    PostPinView,
)

urlpatterns = [
    # ---------- Bảng tin ----------
    path("posts/", PostListCreateView.as_view(), name="post_list"),
    path("posts/<int:pk>/", PostDetailView.as_view(), name="post_detail"),
    path("posts/<int:pk>/pin/", PostPinView.as_view(), name="post_pin"),
    # ---------- Hòm thư góp ý ẩn danh ----------
    path("feedback/", FeedbackView.as_view(), name="feedback"),
    # ---------- Bình chọn cộng đồng ----------
    path("polls/", PollListCreateView.as_view(), name="poll_list"),
    path("polls/<int:pk>/vote/", PollVoteView.as_view(), name="poll_vote"),
]
