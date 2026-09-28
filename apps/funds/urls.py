"""
URLs — apps.funds (mounted tại /api/v1/funds/)
==============================================
Toàn bộ chức năng quỹ thuộc phân hệ BCN (permission đặt ở tầng View).
"""
from django.urls import path

from apps.funds.views import (
    FundExportExcelView,
    FundPeriodLockListView,
    FundStatsView,
    FundTransactionListCreateView,
    LockPeriodView,
)

urlpatterns = [
    path("", FundTransactionListCreateView.as_view(), name="fund_list"),
    path("stats/", FundStatsView.as_view(), name="fund_stats"),
    path("lock-period/", LockPeriodView.as_view(), name="fund_lock_period"),
    path("locks/", FundPeriodLockListView.as_view(), name="fund_locks"),
    path("export-excel/", FundExportExcelView.as_view(), name="fund_export_excel"),
]
