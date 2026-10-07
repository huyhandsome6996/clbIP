"""
Middleware: Content-Security-Policy (CSP) — backstop chống XSS
===============================================================
QA-Audit Nhóm 2f: refresh token đang lưu trong localStorage (kiến trúc SPA
frontend thuần — xem ghi chú rủi ro trong README §Bảo mật). Vì không thể chuyển
ngay sang cookie HttpOnly mà không phá FRONTEND_CONTRACT (api.js đọc token từ
localStorage), rủi ro được giảm thiểu bằng CSP nghiêm ngặt: kể cả khi một đoạn
HTML động lọt XSS, trình duyệt vẫn chặn script ngoại vi, iframe ngoại, object
và form action ngoài domain.

Lưu ý cân bằng: 'unsafe-inline' cho script/style là ĐÁNH ĐỐI CÓ Ý THỨC — toàn
bộ 16 trang frontend nhúng <script> inline (kiến trúc HTML/CSS/JS thuần, không
build step). Khi frontend tách JS ra file ngoài hoàn toàn, nâng cấp lên
nonce-based CSP ('script-src "nonce-..."').
"""
from django.conf import settings


class ContentSecurityPolicyMiddleware:
    """Gắn header Content-Security-Policy vào mọi response của Django."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # setdefault: cho phép view/unit-test override nếu cần
        response.headers.setdefault("Content-Security-Policy", self._build_policy())
        return response

    @staticmethod
    def _build_policy() -> str:
        # frame-ancestors 'none' trùng X-Frame-Options DENY (phòng hờ cho
        # trình duyệt mới); frame-src blob: phục vụ preview PDF qua blob URL
        # vì X_FRAME_OPTIONS=DENY chặn iframe trỏ thẳng /media/.
        directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net",
            # fonts.googleapis.com: trang frontend nạp stylesheet Inter từ Google Fonts
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "img-src 'self' data: blob: https:",
            # fonts.gstatic.com: file woff2 của Inter
            "font-src 'self' data: https://fonts.gstatic.com",
            "connect-src 'self'",
            "frame-src 'self' blob:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        if settings.DJANGO_ENV == "production":
            # Production chỉ chạy HTTPS — nâng cấp mọi request nhạt lên secure
            directives.append("upgrade-insecure-requests")
        return "; ".join(directives)
