"""
Tests — apps.authentication
Login JWT (email), RBAC roles, /me/ endpoint, brute-force lockout (axes).
"""
from typing import Any

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User
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
    def test_account_lockout_after_5_failures(self) -> None:
        """Sai mật khẩu 5 lần → lần 6 đăng nhập ĐÚNG cũng bị chặn 403."""
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
