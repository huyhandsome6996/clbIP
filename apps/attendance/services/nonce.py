"""
Services — Attendance: Dynamic Nonce xoay 60 giây (HMAC-SHA256).
================================================================
Theo Security Hardening §5.1: mỗi phiên điểm danh có secret riêng, mã nonce
6 chữ số thay đổi mỗi NONCE_ROTATION_SECONDS (60s) — chỉ ai có mặt tại phòng
sinh hoạt và nhìn lên máy chiếu mới có mã để gửi kèm request GPS.

Tolerance: validate chấp nhận window hiện tại HOẶC window liền trước để
không làm khó member đứng đúng ranh giới chuyển cửa sổ.
"""
import hashlib
import hmac
from typing import Optional, Union

from django.conf import settings
from django.utils import timezone


class AttendanceNonceService:
    """Sinh / xác minh mã nonce động của phiên điểm danh."""

    # ------------------------------------------------------------------
    # Cửa sổ thời gian
    # ------------------------------------------------------------------
    @staticmethod
    def _rotation_seconds() -> int:
        """Độ dài cửa sổ xoay nonce (giây) — cấu hình tại CLB_SETTINGS."""
        return int(settings.CLB_SETTINGS["NONCE_ROTATION_SECONDS"])

    @classmethod
    def _window_index(cls, timestamp: float) -> int:
        """Chỉ số cửa sổ hiện tại: floor(timestamp / rotation)."""
        return int(timestamp // cls._rotation_seconds())

    # ------------------------------------------------------------------
    # Sinh mã cho một cửa sổ
    # ------------------------------------------------------------------
    @classmethod
    def _code_for_window(cls, session, window: int) -> str:
        """
        Mã nonce của 1 window: HMAC-SHA256(key=nonce_secret, msg=str(window))
        → lấy 8 hex đầu → % 1_000_000 → 6 chữ số zero-pad (VD: "004213").
        """
        secret = (session.nonce_secret or "").encode("utf-8")
        digest = hmac.new(
            secret, msg=str(window).encode("utf-8"), digestmod=hashlib.sha256
        ).hexdigest()
        return f"{int(digest[:8], 16) % 1_000_000:06d}"

    # ------------------------------------------------------------------
    # API public
    # ------------------------------------------------------------------
    @classmethod
    def generate(cls, session, at: Union[object, None] = None) -> dict:
        """
        Sinh nonce hiện tại để BCN hiển thị lên máy chiếu.

        Returns:
            {"nonce": "123456", "window": <int>, "expires_in": <giây còn lại>}
        """
        now = at or timezone.now()
        timestamp = now.timestamp()
        rotation = cls._rotation_seconds()
        window = cls._window_index(timestamp)
        return {
            "nonce": cls._code_for_window(session, window),
            "window": window,
            "expires_in": max(0, rotation - int(timestamp % rotation)),
        }

    @classmethod
    def validate(cls, session, nonce, at: Union[object, None] = None) -> bool:
        """
        Xác minh nonce — khớp window hiện tại HOẶC window liền trước
        (constant-time compare bằng hmac.compare_digest).
        """
        if not nonce or not getattr(session, "nonce_secret", ""):
            return False
        now = at or timezone.now()
        window = cls._window_index(now.timestamp())
        candidate = str(nonce).strip()
        for w in (window, window - 1):  # tolerance: tránh lệch ranh giới 60s
            if hmac.compare_digest(cls._code_for_window(session, w), candidate):
                return True
        return False
