"""
Tests — apps.authentication
Login JWT (email), RBAC roles, /me/ endpoint, brute-force lockout (axes).
"""
from typing import Any

from unittest import mock

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.authentication.views import CustomTokenObtainPairView
from apps.members.models import MemberProfile


class LoginTests(TestCase):
    """Test JWT login bằng email + envelope chuẩn."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="nam@clbip.vn", password="TestPass123!", role="MEMBER"
        )

    def test_login_success_envelope(self) -> None:
        """Đăng nhập đúng → 200 envelope {success, data.access, data.refresh, data.user}."""
        res = self.client.post(
            "/api/v1/auth/token/",
            {"email": "nam@clbip.vn", "password": "TestPass123!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])
        self.assertIn("access", res.data["data"])
        self.assertIn("refresh", res.data["data"])
        self.assertEqual(res.data["data"]["user"]["email"], "nam@clbip.vn")
        self.assertEqual(res.data["data"]["user"]["role"], "MEMBER")

    def test_login_wrong_password_401(self) -> None:
        """Sai mật khẩu → 401 envelope success=false."""
        res = self.client.post(
            "/api/v1/auth/token/",
            {"email": "nam@clbip.vn", "password": "SaiRoi123!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(res.data["success"])

    def test_login_unknown_email_401(self) -> None:
        """Email không tồn tại → 401."""
        res = self.client.post(
            "/api/v1/auth/token/",
            {"email": "ghost@clbip.vn", "password": "Whatever123!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_flow(self) -> None:
        """Refresh token hợp lệ → nhận access token mới."""
        login = self.client.post(
            "/api/v1/auth/token/",
            {"email": "nam@clbip.vn", "password": "TestPass123!"},
            format="json",
        )
        refresh = login.data["data"]["refresh"]
        res = self.client.post(
            "/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("access", res.data)


class MeViewTests(TestCase):
    """Test GET /auth/me/."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.member = User.objects.create_user(
            email="me@clbip.vn", password="TestPass123!", role="MEMBER"
        )
        MemberProfile.objects.create(user=self.member, ho_ten="Nguyễn Văn Me", lop="22A401")

    def test_me_requires_auth(self) -> None:
        """Chưa đăng nhập → 401."""
        res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_with_profile(self) -> None:
        """Có profile → trả kèm ho_ten/lop/xp."""
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["data"]["email"], "me@clbip.vn")
        self.assertEqual(res.data["data"]["ho_ten"], "Nguyễn Văn Me")
        self.assertEqual(res.data["data"]["lop"], "22A401")
        self.assertEqual(res.data["data"]["xp_points"], 0)


class RBACTests(TestCase):
    """Test vai trò ADMIN/BCN/MEMBER."""

    def test_role_defaults_to_member(self) -> None:
        user = User.objects.create_user(email="r1@clbip.vn", password="TestPass123!")
        self.assertEqual(user.role, User.Role.MEMBER)

    def test_is_bcn_property(self) -> None:
        bcn = User.objects.create_user(email="r2@clbip.vn", password="TestPass123!", role="BCN")
        member = User.objects.create_user(email="r3@clbip.vn", password="TestPass123!")
        admin = User.objects.create_user(email="r4@clbip.vn", password="TestPass123!", role="ADMIN")
        self.assertTrue(bcn.is_bcn)
        self.assertFalse(member.is_bcn)
        self.assertTrue(admin.is_bcn)
        self.assertTrue(admin.is_admin)

    def test_duplicate_email_rejected(self) -> None:
        """Email phải unique — tạo trùng bị IntegrityError."""
        User.objects.create_user(email="r2@clbip.vn", password="TestPass123!")
        with self.assertRaises(Exception):
            User.objects.create_user(email="r2@clbip.vn", password="TestPass123!")


class BruteForceLockoutTests(TestCase):
    """Test khóa tài khoản brute-force (django-axes) — enable cho class này."""

    @override_settings(AXES_ENABLED=True)
    @mock.patch.object(CustomTokenObtainPairView, "throttle_classes", [])
    def test_account_lockout_after_5_failures(self) -> None:
        """Sai mật khẩu 5 lần → lần 6 đăng nhập ĐÚNG cũng bị chặn (axes lockout).
        Tắt DRF throttle để cô lập hành vi axes (throttle 5/phút chặn trước axes)."""
        User.objects.create_user(email="lock@clbip.vn", password="CorrectPass123!")
        client = APIClient()
        for _ in range(5):
            res = client.post(
                "/api/v1/auth/token/",
                {"email": "lock@clbip.vn", "password": "WrongPass123!"},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        # Lần 6: mật khẩu ĐÚNG nhưng tài khoản đã bị khóa
        res = client.post(
            "/api/v1/auth/token/",
            {"email": "lock@clbip.vn", "password": "CorrectPass123!"},
            format="json",
        )
        self.assertIn(
            res.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED)
        )
        self.assertFalse(res.data["success"])


class ThrottleProxyIPTests(TestCase):
    """
    QA-Audit 2b — throttle phải khóa theo IP client thật sau reverse proxy:
    - NUM_PROXIES=0 (dev): X-Forwarded-For bị bỏ qua hoàn toàn → giả mạo vô ích.
    - NUM_PROXIES=1 (production): chỉ phần tử CUỐI của XFF (do proxy Render ghi)
      được dùng — phần tử đầu do client gửi là rác giả mạo, không tạo bucket riêng.
    """

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 1})
    def test_xff_gia_khong_ne_duoc_throttle_dang_nhap(self) -> None:
        """Mô phỏng Render: XFF='giả, IP-thật' — đổi phần tử giả vẫn bị khóa theo IP thật."""
        User.objects.create_user(email="xff@clbip.vn", password="XffPass123!")
        client = APIClient()
        for i in range(5):
            res = client.post(
                "/api/v1/auth/token/",
                {"email": "xff@clbip.vn", "password": "SaiRoi123!"},
                format="json",
                REMOTE_ADDR="10.0.0.1",  # IP của reverse proxy
                HTTP_X_FORWARDED_FOR=f"10.9.9.{i}, 203.0.113.77",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        # Lần 6: throttle chặn (429) dù đổi tiếp phần tử giả mạo phía trước
        res = client.post(
            "/api/v1/auth/token/",
            {"email": "xff@clbip.vn", "password": "SaiRoi123!"},
            format="json",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="10.9.9.99, 203.0.113.77",
        )
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 0})
    def test_xff_bi_bo_qua_khi_num_proxies_bang_0(self) -> None:
        """Dev không qua proxy (NUM_PROXIES=0): ident = REMOTE_ADDR — XFF giả vô nghĩa."""
        User.objects.create_user(email="xff0@clbip.vn", password="XffPass123!")
        client = APIClient()
        for i in range(5):
            res = client.post(
                "/api/v1/auth/token/",
                {"email": "xff0@clbip.vn", "password": "SaiRoi123!"},
                format="json",
                REMOTE_ADDR="203.0.113.88",
                HTTP_X_FORWARDED_FOR=f"10.6.6.{i}",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        res = client.post(
            "/api/v1/auth/token/",
            {"email": "xff0@clbip.vn", "password": "SaiRoi123!"},
            format="json",
            REMOTE_ADDR="203.0.113.88",
            HTTP_X_FORWARDED_FOR="10.6.6.200",
        )
        self.assertEqual(res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class AxesProxyLockoutTests(TestCase):
    """QA-Audit 2b — axes khóa đúng theo IP thật khi đứng sau 1 proxy."""

    @override_settings(AXES_ENABLED=True, AXES_IPWARE_PROXY_COUNT=1)
    @mock.patch.object(CustomTokenObtainPairView, "throttle_classes", [])
    def test_axes_khoa_theo_ip_that_du_xff_gia(self) -> None:
        """5 sai với XFF giả → khóa theo cặp (username, IP thật cuối XFF)."""
        User.objects.create_user(email="axespx@clbip.vn", password="AxesPass123!")
        client = APIClient()
        for i in range(5):
            res = client.post(
                "/api/v1/auth/token/",
                {"email": "axespx@clbip.vn", "password": "SaiQua123!"},
                format="json",
                REMOTE_ADDR="10.0.0.1",
                HTTP_X_FORWARDED_FOR=f"66.66.66.{i}, 198.51.100.10",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        # Lần 6: mật khẩu ĐÚNG nhưng đã bị khóa theo (username, 198.51.100.10)
        res = client.post(
            "/api/v1/auth/token/",
            {"email": "axespx@clbip.vn", "password": "AxesPass123!"},
            format="json",
            REMOTE_ADDR="10.0.0.1",
            HTTP_X_FORWARDED_FOR="66.66.66.123, 198.51.100.10",
        )
        self.assertIn(res.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_401_UNAUTHORIZED))
        self.assertFalse(res.data["success"])
        # Chứng minh axes nhận diện đúng IP THẬT (phần tử cuối XFF do proxy ghi),
        # không phải phần tử giả đầu tiên hay IP proxy — cốt lõi của QA-Audit 2b
        from axes.models import AccessAttempt

        attempt = AccessAttempt.objects.filter(username="axespx@clbip.vn").first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.ip_address, "198.51.100.10")


class AxesLockoutTests(TestCase):
    """
    QA-Audit đợt 2 (P3): django-axes đang AXES_ENABLED = not TESTING → chính
    sách khóa đăng nhập không có test. Test này override AXES_ENABLED=True
    để chạy thật: 5 lần sai → khóa, lần thứ 6 ĐÚNG mật khẩu cũng bị chặn 403.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.user = User.objects.create_user(
            email="lockout@clbip.vn", password="CorrectPass123!", role="MEMBER"
        )

    def _login(self, password: str):
        return self.client.post(
            "/api/v1/auth/token/",
            {"email": "lockout@clbip.vn", "password": password},
            format="json",
        )

    def test_sai_5_lan_bi_khoa_ke_ca_dung_mat_khau(self) -> None:
        # Tắt throttle DRF của view login (429 sẽ chặn trước axes trong test)
        with mock.patch.object(CustomTokenObtainPairView, "throttle_classes", []):
            with override_settings(AXES_ENABLED=True):
                # 5 lần sai mật khẩu → chạm AXES_FAILURE_LIMIT
                for i in range(5):
                    res = self._login("WrongPass123!")
                    self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED, f"Lần {i+1}")

                # Lần thứ 6 — ĐÚNG mật khẩu vẫn bị chặn 403 (account_locked);
                # AccessAttempt ghi trong transaction test → rollback tự động
                res = self._login("CorrectPass123!")
                self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
                payload = res.json() if hasattr(res, "json") else res.data
                self.assertIn("khóa", payload["message"])
                self.assertEqual(payload["errors"]["detail"], "account_locked")
