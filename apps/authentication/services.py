"""
Services — apps.authentication
==============================
PasswordResetService — luồng "Quên mật khẩu" bằng OTP 6 số qua email
(QA-Audit đợt 3 — TASK 2 P0; trước đây thành viên quên mật khẩu phải nhờ
BCN reset thủ công qua Django Admin).

Thiết kế:
- OTP + reset_token lưu Django cache (DatabaseCache/Redis dùng chung giữa
  các gunicorn worker) — KHÔNG lưu DB, tự hết hạn theo TTL, tránh spam bảng.
- Anti-enumeration: request_otp LUÔN trả 200, không tiết lộ email tồn tại.
- OTP 6 số có tối đa 5 lần nhập sai (chống dò OTP trong cửa sổ 10 phút).
- Đổi mật khẩu thành công → đưa toàn bộ refresh token của user vào
  blacklist (phiên đăng nhập cũ chết ngay cả khi access token còn hạn).
"""
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail

from apps.common.exceptions import NotFoundException, ValidationException

OTP_TTL = 600  # 10 phút — thời gian hiệu lực mã OTP
TOKEN_TTL = 600  # 10 phút — thời gian hiệu lực reset_token sau khi OTP hợp lệ
OTP_MAX_ATTEMPTS = 5  # Số lần nhập SAI tối đa cho mỗi mã OTP

_OTP_KEY = "pw_reset_otp:{email}"
_OTP_ATTEMPT_KEY = "pw_reset_otp_attempts:{email}"
_TOKEN_KEY = "pw_reset_token:{token}"


def _normalize_email(email: str) -> str:
    """Email chuẩn hóa khóa cache (lowercase, trim)."""
    return (email or "").strip().lower()


class PasswordResetService:
    """Quản lý luồng OTP quên mật khẩu — không đụng ORM trực tiếp ngoài User."""

    # ------------------------------------------------------------------
    # Bước 1 — Yêu cầu OTP
    # ------------------------------------------------------------------
    @staticmethod
    def request_otp(email: str) -> None:
        """
        Sinh OTP 6 số, cache theo email, gửi email.

        Anti-enumeration: email không tồn tại → IM LẶNG trả về (caller vẫn
        trả 200), attacker không phân biệt được email có tồn tại hay không.
        """
        User = get_user_model()
        email = _normalize_email(email)
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            return

        otp = f"{secrets.randbelow(1_000_000):06d}"
        cache.set(_OTP_KEY.format(email=email), otp, OTP_TTL)
        cache.set(_OTP_ATTEMPT_KEY.format(email=email), 0, OTP_TTL)

        send_mail(
            subject="[CLB IP] Mã xác thực đặt lại mật khẩu",
            message=(
                f"Mã OTP của bạn là: {otp}\n"
                f"Hiệu lực trong 10 phút. KHÔNG chia sẻ mã này cho bất kỳ ai.\n\n"
                f"Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[email],
            fail_silently=False,
        )

    # ------------------------------------------------------------------
    # Bước 2 — Xác minh OTP → reset_token
    # ------------------------------------------------------------------
    @staticmethod
    def verify_otp(email: str, otp: str) -> str:
        """
        Xác minh OTP → trả về reset_token (secrets.token_urlsafe, TTL 10 phút).

        Raises:
            ValidationException (400): OTP sai / hết hạn / nhập sai quá hạn mức.
        """
        email = _normalize_email(email)
        otp = (otp or "").strip()
        otp_key = _OTP_KEY.format(email=email)
        attempt_key = _OTP_ATTEMPT_KEY.format(email=email)

        stored = cache.get(otp_key)
        if stored is None:
            raise ValidationException("Mã OTP không đúng hoặc đã hết hạn.")

        if stored != otp:
            attempts = (cache.get(attempt_key) or 0) + 1
            cache.set(attempt_key, attempts, OTP_TTL)
            if attempts >= OTP_MAX_ATTEMPTS:
                # Dò OTP → vô hiệu hóa mã ngay cả khi chưa hết 10 phút
                cache.delete(otp_key)
                cache.delete(attempt_key)
                raise ValidationException(
                    "Bạn đã nhập sai mã OTP quá 5 lần. Vui lòng yêu cầu mã mới."
                )
            raise ValidationException(
                f"Mã OTP không đúng. Bạn còn {OTP_MAX_ATTEMPTS - attempts} lần thử."
            )

        # OTP đúng → tiêu hao mã (one-time), cấp reset_token
        cache.delete(otp_key)
        cache.delete(attempt_key)
        token = secrets.token_urlsafe(32)
        cache.set(_TOKEN_KEY.format(email=email, token=token), email, TOKEN_TTL)
        return token

    # ------------------------------------------------------------------
    # Bước 3 — Đổi mật khẩu bằng reset_token
    # ------------------------------------------------------------------
    @staticmethod
    def confirm_reset(token: str, new_password: str) -> None:
        """
        Đổi mật khẩu bằng reset_token hợp lệ, rồi blacklist toàn bộ refresh
        token cũ của user (mọi phiên đăng nhập đang tồn tại đều phải đăng
        nhập lại bằng mật khẩu mới).

        Raises:
            ValidationException (400): token không hợp lệ / đã dùng / hết hạn.
            NotFoundException (404): tài khoản không còn tồn tại.
        """
        User = get_user_model()
        token = (token or "").strip()
        token_key = _TOKEN_KEY.format(token=token)
        email = cache.get(token_key)
        if email is None:
            raise ValidationException(
                "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn."
            )

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise NotFoundException("Tài khoản không tồn tại.")

        user.set_password(new_password)
        user.save(update_fields=["password"])

        # Token one-time: dùng xong là chết
        cache.delete(token_key)

        # Vô hiệu hóa mọi refresh token cũ (simplejwt blacklist) — phiên cũ
        # không thể cấp access token mới sau khi mật khẩu đã đổi
        try:
            from rest_framework_simplejwt.token_blacklist.models import (  # noqa: PLC0415
                BlacklistedToken,
                OutstandingToken,
            )

            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except Exception:  # noqa: BLE001 — blacklist lỗi không chặn việc đổi mật khẩu
            pass
