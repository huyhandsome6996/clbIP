"""
Tests — apps.common
====================
Phủ bắt buộc (QA-Audit Nhóm 1 — P0):
    1. seed_demo bị CHẶN (CommandError) khi DJANGO_ENV=production — không tạo
       bất kỳ User nào, không đụng dữ liệu.
    2. seed_demo chạy được trên development: tạo đủ ADMIN + BCN + MEMBER,
       mật khẩu lấy từ tham số --password (không hardcode công khai).
    3. seed_demo idempotent: chạy 2 lần không nhân đôi users/sự kiện/giao dịch quỹ.
Lưu ý: DJANGO_ENV mặc định "development" trong settings → toàn bộ test khác
không bị ảnh hưởng bởi lệnh chặn này.
"""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.authentication.models import User
from apps.events.models import ActivityEvent
from apps.funds.models import FundTransaction


class SeedDemoProductionGuardTests(TestCase):
    """P0: tài khoản demo tuyệt đối không được seed lên production."""

    @override_settings(DJANGO_ENV="production")
    def test_seed_demo_bi_chan_tren_production(self):
        """DJANGO_ENV=production → CommandError, không tạo user nào."""
        before = User.objects.count()

        with self.assertRaises(CommandError) as ctx:
            call_command("seed_demo", stdout=self._capture())

        self.assertIn("BỊ CHẶN", str(ctx.exception))
        self.assertIn("production", str(ctx.exception))
        # Không có user nào được tạo ra kể cả khi command lỗi
        self.assertEqual(User.objects.count(), before)

    @override_settings(DJANGO_ENV="production")
    def test_seed_demo_chan_truoc_khi_ghi_db(self):
        """Chặn phải xảy ra ngay ở đầu handle() — trước mọi thao tác ghi."""
        self.assertFalse(User.objects.filter(email="admin@clbip.vn").exists())
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=self._capture())
        self.assertFalse(User.objects.filter(email="admin@clbip.vn").exists())

    def test_seed_demo_van_chay_tren_development(self):
        """DJANGO_ENV mặc định development → seed vẫn hoạt động bình thường."""
        call_command("seed_demo", password="MatKhauTest@123", stdout=self._capture())
        self.assertTrue(User.objects.filter(email="admin@clbip.vn").exists())
        self.assertTrue(User.objects.filter(role="BCN").exists())
        self.assertTrue(User.objects.filter(role="MEMBER").exists())

    def _capture(self):
        import io

        return io.StringIO()


class SeedDemoIdempotencyTests(TestCase):
    """Chạy seed 2 lần → không nhân đôi dữ liệu (đảm bảo build.sh chạy lại an toàn)."""

    def test_chay_hai_lan_khong_nhan_doi(self):
        out = self._capture()
        call_command("seed_demo", password="MatKhauTest@123", stdout=out)
        users_1 = User.objects.count()
        events_1 = ActivityEvent.objects.count()
        funds_1 = FundTransaction.objects.count()

        call_command("seed_demo", password="MatKhauTest@123", stdout=out)
        self.assertEqual(User.objects.count(), users_1)
        self.assertEqual(ActivityEvent.objects.count(), events_1)
        self.assertEqual(FundTransaction.objects.count(), funds_1)

    def _capture(self):
        import io

        return io.StringIO()


class ApiDocsProductionGuardTests(TestCase):
    """QA-Audit 2e — tài liệu API chỉ dành cho ADMIN khi production."""

    def _make_admin(self):
        user = User.objects.create_user(email="docsadmin@clbip.vn", password="DocsPass123!", role="ADMIN")
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
        return user

    @override_settings(DJANGO_ENV="production")
    def test_khach_khong_thay_docs_tren_production(self) -> None:
        """/api/schema/ và /api/docs/ → 404 với khách (ẩn sự tồn tại)."""
        self.assertEqual(self.client.get("/api/schema/").status_code, 404)
        self.assertEqual(self.client.get("/api/docs/").status_code, 404)

    @override_settings(DJANGO_ENV="production")
    def test_member_khong_thay_docs_tren_production(self) -> None:
        from rest_framework.test import APIClient

        member = User.objects.create_user(email="docsmem@clbip.vn", password="DocsPass123!", role="MEMBER")
        client = APIClient()
        client.force_authenticate(user=member)
        self.assertEqual(client.get("/api/schema/").status_code, 404)
        self.assertEqual(client.get("/api/docs/").status_code, 404)

    @override_settings(DJANGO_ENV="production")
    def test_admin_van_xem_duoc_schema(self) -> None:
        from rest_framework.test import APIClient

        admin = self._make_admin()
        client = APIClient()
        client.force_authenticate(user=admin)
        self.assertEqual(client.get("/api/schema/").status_code, 200)

    def test_docs_mo_tren_development(self) -> None:
        """Dev vẫn mở tự do cho tiện ích phát triển."""
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)


class CSPHeaderTests(TestCase):
    """QA-Audit 2f — mọi response phải mang Content-Security-Policy."""

    def test_response_co_header_csp(self) -> None:
        res = self.client.get("/api/health/")
        self.assertIn("Content-Security-Policy", res.headers)
        csp = res.headers["Content-Security-Policy"]
        for directive in ("default-src 'self'", "object-src 'none'", "frame-ancestors 'none'"):
            self.assertIn(directive, csp)
