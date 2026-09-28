"""
URLs — Attendance API (được mount tại /api/v1/attendance/ từ core/urls.py).
"""
from django.urls import path

from apps.attendance.views import (
    BulkOverrideView,
    CheckInView,
    CloseSessionView,
    MyAttendanceHistoryView,
    SessionDetailView,
    SessionListCreateView,
    SessionNonceView,
)

urlpatterns = [
    path("sessions/", SessionListCreateView.as_view(), name="attendance_sessions"),
    path("sessions/<int:pk>/", SessionDetailView.as_view(), name="attendance_session_detail"),
    path("sessions/<int:pk>/close/", CloseSessionView.as_view(), name="attendance_session_close"),
    path("sessions/<int:pk>/nonce/", SessionNonceView.as_view(), name="attendance_session_nonce"),
    path(
        "sessions/<int:pk>/bulk-override/",
        BulkOverrideView.as_view(),
        name="attendance_bulk_override",
    ),
    path("check-in/", CheckInView.as_view(), name="attendance_checkin"),
    path("me/", MyAttendanceHistoryView.as_view(), name="attendance_me"),
]
