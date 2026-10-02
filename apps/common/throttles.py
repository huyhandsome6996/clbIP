"""
Throttle Classes chống DoS/DDoS — theo CLBIP_Security_Hardening_Prompt.md §3.1.
"""
from rest_framework.throttling import ScopedRateThrottle, SimpleRateThrottle


class BurstRateThrottle(SimpleRateThrottle):
    """Chặn flood burst ngắn hạn: tối đa 10 request/giây (mọi user)."""

    scope = "burst"

    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class SustainedRateThrottle(SimpleRateThrottle):
    """Giới hạn bền vững theo giờ: 1500 request/hour."""

    scope = "sustained"

    def get_cache_key(self, request, view):
        if request.user.is_authenticated:
            return self.cache_format % {"scope": self.scope, "ident": request.user.pk}
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class AuthLoginRateThrottle(ScopedRateThrottle):
    """Đăng nhập: 5 lần/phút — chống brute-force dò mật khẩu."""

    scope = "auth_login"


class CheckInRateThrottle(ScopedRateThrottle):
    """Điểm danh GPS: 3 lần/phút — chống spam check-in."""

    scope = "checkin"


class FeedbackRateThrottle(ScopedRateThrottle):
    """Góp ý/Poll: 2 lần/phút — chống spam hòm thư."""

    scope = "feedback"


class DocumentUploadRateThrottle(ScopedRateThrottle):
    """Upload tài liệu: 5 lần/phút — chống làm đầy ổ đĩa."""

    scope = "doc_upload"


class PasswordResetThrottle(ScopedRateThrottle):
    """Yêu cầu OTP quên mật khẩu: 3 lần/giờ — chống spam email / dò tài khoản."""

    scope = "pw_reset"
