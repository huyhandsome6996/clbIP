"""
Regression tests cho routing frontend tĩnh — CLB IP ĐHSP Huế 2.0.

Sinh ra sau Task 12 (landing page công khai tại `/`): chống hồi quy khi ai đó
vô tình trả route "/" về redirect sang login/splash cũ — landing công khai là
yêu cầu sản phẩm (khách truy cập root phải thấy trang giới thiệu CLB).
"""
from django.test import Client, TestCase


def _body(res) -> str:
    """Đọc body từ FileResponse (static_serve trả streaming response)."""
    if hasattr(res, "streaming_content"):
        return b"".join(res.streaming_content).decode("utf-8")
    return res.content.decode("utf-8")


class RootLandingPageTests(TestCase):
    """GET / — landing page công khai (không cần đăng nhập)."""

    def setUp(self):
        self.client = Client()

    def test_root_serves_public_landing(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        body = _body(res)
        # Nội dung đặc trưng của landing công khai
        self.assertIn("Code your Future", body)
        self.assertIn("Đăng nhập", body)
        self.assertIn("frontend/css/landing.css", body)

    def test_root_always_public_no_redirect_to_login(self):
        """Route "/" KHÔNG được 30x về login (hồi quy Task 11 trở về trước)."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("Location", res.headers)

    def test_root_has_no_cache_header(self):
        """Nhất quán với frontend_serve: trình duyệt luôn revalidate."""
        res = self.client.get("/")
        self.assertEqual(res.headers.get("Cache-Control"), "no-cache")

    def test_root_security_headers_present(self):
        """CSP + headers bảo mật phải gắn cả trên landing (SecurityHeadersMiddleware)."""
        res = self.client.get("/")
        csp = res.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")

    def test_landing_html_direct_access_still_works(self):
        """/frontend/landing.html vẫn vào được trực tiếp (cùng file với /)."""
        res = self.client.get("/frontend/landing.html")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Code your Future", _body(res))

    def test_splash_index_still_redirects_anonymous_to_login(self):
        """Splash /frontend/index.html vẫn giữ logic điều hướng cho người đã login."""
        res = self.client.get("/frontend/index.html")
        self.assertEqual(res.status_code, 200)
        body = _body(res)
        self.assertIn("login.html", body)  # JS redirect theo trạng thái đăng nhập
