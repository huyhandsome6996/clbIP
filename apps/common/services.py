"""
Services — apps.common
======================
TrendStatsService — dữ liệu biểu đồ dashboard BCN (QA-Audit đợt 3 — TASK 4).

Tổng hợp từ repository của từng app (mỗi bảng query sống đúng 1 nơi):
- FundTransaction → aggregate_monthly_thu_chi (apps.funds.repository)
- AttendanceRecord → aggregate_weekly_attendance (apps.attendance.repository)
View KHÔNG đụng ORM; service KHÔNG đụng ORM — chỉ gọi repository + định dạng.
"""
from datetime import datetime
from typing import ClassVar

from django.utils import timezone

from apps.attendance.repositories import (
    DjangoAttendanceRepository,
    IAttendanceRepository,
)
from apps.funds.repositories import DjangoFundRepository, IFundRepository


class TrendStatsService:
    """Trend thu/chi theo tháng + tỉ lệ chuyên cần theo tuần cho dashboard."""

    _fund_repository_class: ClassVar[type[IFundRepository]] = DjangoFundRepository
    _attendance_repository_class: ClassVar[type[IAttendanceRepository]] = (
        DjangoAttendanceRepository
    )

    @classmethod
    def _fund_repo(cls) -> IFundRepository:
        return cls._fund_repository_class()

    @classmethod
    def _attendance_repo(cls) -> IAttendanceRepository:
        return cls._attendance_repository_class()

    @staticmethod
    def _since_local_dt(months: int) -> datetime:
        """00:00 ngày 1 của tháng bắt đầu (lùi `months - 1` tháng) theo giờ local."""
        today = timezone.localdate()
        year, month = today.year, today.month - (months - 1)
        while month <= 0:
            month += 12
            year -= 1
        return timezone.make_aware(datetime(year, month, 1))

    @classmethod
    def get_trend(cls, months: int = 6) -> dict:
        """
        Trả shape khớp frontend dashboard:
            {"fund_trend": [{"month": "2026-04", "thu": x, "chi": y}, ...],
             "attendance_trend": [{"week": "2026-W38", "rate": 0.85}, ...]}
        """
        since_dt = cls._since_local_dt(months)
        return {
            "fund_trend": cls._fund_repo().aggregate_monthly_thu_chi(since_dt),
            "attendance_trend": cls._attendance_repo().aggregate_weekly_attendance(since_dt),
        }
