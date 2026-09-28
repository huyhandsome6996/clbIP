"""
Package services — apps.attendance.
Re-export các service chính cho import gọn bên ngoài:

    from apps.attendance.services import (
        AttendanceService, GPSAntiCheatEngine, AttendanceNonceService
    )
"""
from apps.attendance.services.anti_cheat import GPSAntiCheatEngine
from apps.attendance.services.attendance_service import AttendanceService
from apps.attendance.services.nonce import AttendanceNonceService

__all__ = [
    "AttendanceService",
    "GPSAntiCheatEngine",
    "AttendanceNonceService",
]
