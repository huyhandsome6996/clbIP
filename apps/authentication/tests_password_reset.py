"""
Tests — Quên mật khẩu + OTP email (QA-Audit đợt 3 — TASK 2 P0).

Che phủ:
- PasswordResetService: request_otp (anti-enumeration), verify_otp (sai/hết
  hạn/dò OTP), confirm_reset (đổi mật khẩu + one-time token + blacklist).
- 3 endpoint: request / verify / confirm (thứ tự 404→400→thành công).
- Throttle pw_reset 3/giờ.
- Frontend luồng chuẩn: đăng nhập được bằng mật khẩu mới, mất quyền bằng mật
  khẩu cũ, refresh token cũ bị blacklist sau khi đổi mật khẩu.
"""
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.services import PasswordResetService


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetServiceTests(TestCase):
    """Unit test PasswordResetService (request_otp / verify_otp / confirm_reset)."""

    def setUp(self) -> None:
        cache.clear()
        self.email = "reset@clbip.vn"
        self.user = User.objects.create_user(
            email=self.email, password="OldPass123!", role="MEMBER"
        )

    def tearDown(self) -> None:
        cache.clear()

    # ------------------------------------------------------------------
    # Bước 1 — request_otp
    # ------------------------------------------------------------------
    def test_request_otp_gui_email_6_so(self) -> None:
        """Email tồn tại → gửi 1 email, OTP 6 số nằm trong cache + outbox."""
        PasswordResetService.request_otp(self.email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.email, mail.outbox[0].to)
        otp = cache.get(f"pw_reset_otp:{self.email}")
        self.assertIsNotNone(otp)
        self.assertRegex(otp, r"^\d{6}$")
        self.assertIn(otp, mail.outbox[0].body)

    def test_request_otp_email_khong_ton_tai_im_lang(self) -> None:
        """Anti-enumeration: email lạ → KHÔNG gửi email, KHÔNG lỗi, KHÔNG cache."""
        PasswordResetService.request_otp("ghost@clbip.vn")
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(cache.get("pw_reset_otp:ghost@clbip.vn"))

    def test_request_otp_email_hoa_thuong_dung_mot_khoa(self) -> None:
        """Email chữ hoa/thường → cùng một khóa cache, OTP vẫn dùng được."""
        PasswordResetService.request_otp(self.email.upper())
        self.assertIsNotNone(cache.get(f"pw_reset_otp:{self.email}"))

    # ------------------------------------------------------------------
    # Bước 2 — verify_otp
    # ------------------------------------------------------------------
    def _request_otp(self) -> str:
        PasswordResetService.request_otp(self.email)
        return cache.get(f"pw_reset_otp:{self.email}")

    def test_verify_otp_dung_tra_reset_token(self) -> None:
        otp = self._request_otp()
        token = PasswordResetService.verify_otp(self.email, otp)
        self.assertIsNotNone(token)
        # OTP one-time: đã bị xóa khỏi cache sau khi dùng
        self.assertIsNone(cache.get(f"pw_reset_otp:{self.email}"))

    def test_verify_otp_sai_400(self) -> None:
        self._request_otp()
        with self.assertRaises(Exception) as ctx:
            PasswordResetService.verify_otp(self.email, "000000")
        self.assertIn("không đúng", str(ctx.exception.message))

    def test_verify_otp_het_han_400(self) -> None:
        """OTP hết hạn (không còn trong cache) → 400."""
        with self.assertRaises(Exception):
            PasswordResetService.verify_otp(self.email, "123456")

    def test_verify_otp_sai_5_lan_bi_vo_hieu_hoa(self) -> None:
        """Dò OTP: 5 lần sai → mã bị xóa, kể cả nhập ĐÚNG ở lần sau cũng hết hiệu lực."""
        otp = self._request_otp()
        for _ in range(5):
            with self.assertRaises(Exception):
                PasswordResetService.verify_otp(self.email, "000000")
        # Lần thứ 6 nhập đúng OTP thật → vẫn bị chặn vì mã đã bị vô hiệu hóa
        with self.assertRaises(Exception) as ctx:
            PasswordResetService.verify_otp(self.email, otp)
        self.assertIn("không đúng", str(ctx.exception.message))

    # ------------------------------------------------------------------
    # Bước 3 — confirm_reset
    # ------------------------------------------------------------------
    def test_confirm_reset_doi_mat_khau_thanh_cong(self) -> None:
        otp = self._request_otp()
        token = PasswordResetService.verify_otp(self.email, otp)
        PasswordResetService.confirm_reset(token, "NewPass456!")

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewPass456!"))
        self.assertFalse(self.user.check_password("OldPass123!"))
        # Token one-time: dùng xong không còn giá trị
        with self.assertRaises(Exception):
            PasswordResetService.confirm_reset(token, "Another789!")

    def test_confirm_reset_token_sai_het_han(self) -> None:
        with self.assertRaises(Exception) as ctx:
            PasswordResetService.confirm_reset("khong-ton-tai", "NewPass456!")
        self.assertIn("hết hạn", str(ctx.exception.message))

    def test_confirm_reset_blacklist_refresh_token_cu(self) -> None:
        """Đổi mật khẩu xong → mọi refresh token cũ của user phải vào blacklist
        (phiên cũ không thể cấp access token mới sau khi mật khẩu đã đổi)."""
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken,
            OutstandingToken,
        )

        client = APIClient()
        login = client.post(
            "/api/v1/auth/token/",
            {"email": self.email, "password": "OldPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        outstanding_count = OutstandingToken.objects.filter(user=self.user).count()
        self.assertGreater(outstanding_count, 0, "Đăng nhập phải tạo outstanding refresh token")

        otp = self._request_otp()
        token = PasswordResetService.verify_otp(self.email, otp)
        PasswordResetService.confirm_reset(token, "NewPass456!")

        self.assertEqual(
            BlacklistedToken.objects.filter(token__user=self.user).count(),
            outstanding_count,
            "Mọi refresh token cũ phải bị blacklist",
        )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetEndpointTests(TestCase):
    """Endpoint /auth/password-reset/{request,verify,confirm}/ — luồng 3 bước."""

    def setUp(self) -> None:
        cache.clear()
        self.client = APIClient()
        self.email = "flow@clbip.vn"
        User.objects.create_user(email=self.email, password="OldPass123!")

    def tearDown(self) -> None:
        cache.clear()

    def _request(self, email=None):
        return self.client.post(
            "/api/v1/auth/password-reset/request/",
            {"email": email or self.email},
            format="json",
        )

    def test_luuong_3_buoc_hoan_chinh(self) -> None:
        # B1: request → 200 + OTP gửi qua email; đọc OTP từ cache (dev/test)
        res = self._request()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        otp = cache.get(f"pw_reset_otp:{self.email}")
        self.assertIsNotNone(otp)

        # B2: verify → 200 + reset_token
        res = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            {"email": self.email, "otp": otp},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        reset_token = res.data["data"]["reset_token"]

        # B3: confirm → 200, đăng nhập bằng mật khẩu mới OK
        res = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {
                "reset_token": reset_token,
                "new_password": "FreshPass789!",
                "confirm_password": "FreshPass789!",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        login = self.client.post(
            "/api/v1/auth/token/",
            {"email": self.email, "password": "FreshPass789!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_request_email_khong_ton_tai_van_200(self) -> None:
        """Anti-enumeration ở tầng endpoint: email lạ → 200 + message chung."""
        res = self._request("lang@clbip.vn")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("Nếu email tồn tại", res.data["message"])
        self.assertEqual(len(mail.outbox), 0)

    def test_verify_otp_sai_400(self) -> None:
        self._request()
        res = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            {"email": self.email, "otp": "999999"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_confirm_mat_khau_khong_khop_400(self) -> None:
        self._request()
        otp = cache.get(f"pw_reset_otp:{self.email}")
        res = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            {"email": self.email, "otp": otp},
            format="json",
        )
        reset_token = res.data["data"]["reset_token"]
        res = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {
                "reset_token": reset_token,
                "new_password": "FreshPass789!",
                "confirm_password": "KhacRoi789!",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(res.data["success"])

    def test_confirm_mat_khau_yeu_400(self) -> None:
        """Mật khẩu yếu (chỉ số) → Django validator chặn 400."""
        self._request()
        otp = cache.get(f"pw_reset_otp:{self.email}")
        res = self.client.post(
            "/api/v1/auth/password-reset/verify/",
            {"email": self.email, "otp": otp},
            format="json",
        )
        reset_token = res.data["data"]["reset_token"]
        res = self.client.post(
            "/api/v1/auth/password-reset/confirm/",
            {
                "reset_token": reset_token,
                "new_password": "12345678",
                "confirm_password": "12345678",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_throttle_request_3_lan_gio(self) -> None:
        """Rate limit pw_reset 3/hour — lần thứ 4 → 429."""
        for _ in range(3):
            res = self._request()
            self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self._request()
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
