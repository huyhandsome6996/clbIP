"""URLs common — mount tại /api/v1/common/ (QA-Audit đợt 3 — TASK 4).

Lưu ý: health check sống tại apps/common/urls.py với mount /api/ (Render
Health Check Path = /api/health/) — KHÔNG đụng. File này chỉ chứa các
endpoint thống kê dùng chung cho dashboard BCN.
"""
from django.urls import path

from apps.common.views import TrendStatsView

urlpatterns = [
    path("stats/trend/", TrendStatsView.as_view(), name="common_stats_trend"),
]
