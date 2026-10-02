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


class StorageResolverTests(TestCase):
    """QA-Audit nhóm 5 — chọn storage theo biến môi trường (pure function)."""

    def test_mac_dinh_filesystem(self):
        from core.storage_resolver import resolve_default_storage

        cfg = resolve_default_storage({})
        self.assertEqual(cfg["BACKEND"], "django.core.files.storage.FileSystemStorage")

    def test_use_s3_tao_cau_hinh_s3(self):
        from core.storage_resolver import resolve_default_storage

        cfg = resolve_default_storage({
            "USE_S3": "1",
            "AWS_ACCESS_KEY_ID": "k",
            "AWS_SECRET_ACCESS_KEY": "s",
            "AWS_STORAGE_BUCKET_NAME": "clbip-media",
            "AWS_S3_ENDPOINT_URL": "https://abc.r2.cloudflarestorage.com",
        })
        self.assertEqual(cfg["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(cfg["OPTIONS"]["bucket_name"], "clbip-media")
        self.assertFalse(cfg["OPTIONS"]["file_overwrite"])

    def test_use_s3_thieu_gia_tri_khong_crash(self):
        from core.storage_resolver import resolve_default_storage

        cfg = resolve_default_storage({"USE_S3": "1"})
        self.assertEqual(cfg["BACKEND"], "storages.backends.s3.S3Storage")
        self.assertEqual(cfg["OPTIONS"]["bucket_name"], "")


# --- imports bổ sung cho TrendStatsTests (TASK 4) ---
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.members.models import MemberProfile
from rest_framework.test import APIClient


class TrendStatsTests(TestCase):
    """QA-Audit đợt 3 — TASK 4 (P1): GET /api/v1/common/stats/trend/."""

    def setUp(self) -> None:
        from rest_framework.test import APIClient

        cache.clear()
        self.client = APIClient()
        self.bcn = User.objects.create_user(
            email="trend-bcn@clb.vn", password="TestPass123!", role="BCN"
        )
        self.member = User.objects.create_user(
            email="trend-member@clb.vn", password="TestPass123!", role="MEMBER"
        )
        self.member_profile = MemberProfile.objects.create(
            user=self.member, ho_ten="Thành Viên Trend"
        )
        self.client.force_authenticate(user=self.bcn)

    def _make_fund_transaction(self, loai_gd: str, so_tien: int, ngay_gd) -> None:
        FundTransaction.objects.create(
            ma_phieu=f"PT{so_tien}{abs(hash((loai_gd, ngay_gd.isoformat()))) % 10**6:06d}",
            loai_gd=loai_gd,
            so_tien=so_tien,
            ngay_gd=ngay_gd,
            nguoi_thuc_hien="Tester",
        )

    def _make_attendance(self, mo_phien_at, trang_thai: str) -> None:
        # mo_phien_at là auto_now_add → phải update sau khi tạo để đặt giá trị
        session = AttendanceSession.objects.create(
            ten_phien=f"Phiên {trang_thai} {mo_phien_at:%Y%m%d%H%M%S}",
            vi_do=16.4637,
            kinh_do=107.5909,
        )
        AttendanceSession.objects.filter(pk=session.pk).update(mo_phien_at=mo_phien_at)
        AttendanceRecord.objects.create(
            session=session, member=self.member_profile, trang_thai=trang_thai
        )

    def test_member_ban_quyen_403(self) -> None:
        """MEMBER thường → 403 (endpoint chỉ BCN/ADMIN)."""
        client = APIClient()
        client.force_authenticate(user=self.member)
        res = client.get("/api/v1/common/stats/trend/")
        self.assertEqual(res.status_code, 403)

    def test_chua_auth_401(self) -> None:
        client = APIClient()
        res = client.get("/api/v1/common/stats/trend/")
        self.assertEqual(res.status_code, 401)

    def test_rong_tra_mang_rong(self) -> None:
        """Chưa có dữ liệu → 200 với 2 mảng rỗng (frontend vẽ empty state)."""
        res = self.client.get("/api/v1/common/stats/trend/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["fund_trend"], [])
        self.assertEqual(res.data["data"]["attendance_trend"], [])

    def test_fund_trend_group_by_thang(self) -> None:
        """2 tháng giao dịch thu/chi → đúng tổng theo từng tháng, tháng tăng dần."""
        tz = timezone.get_current_timezone()
        # months=12 để bao trọn dữ liệu cố định ở dưới (tránh phụ thuộc ngày chạy test)
        self._make_fund_transaction("THU", 1_500_000, datetime(2026, 4, 10, 9, 0, tzinfo=tz))
        self._make_fund_transaction("CHI", 800_000, datetime(2026, 4, 20, 10, 0, tzinfo=tz))
        self._make_fund_transaction("THU", 2_000_000, datetime(2026, 5, 5, 9, 0, tzinfo=tz))

        res = self.client.get("/api/v1/common/stats/trend/?months=12")
        self.assertEqual(res.status_code, 200)
        fund = res.data["data"]["fund_trend"]
        by_month = {row["month"]: row for row in fund}
        self.assertEqual(by_month["2026-04"]["thu"], 1_500_000)
        self.assertEqual(by_month["2026-04"]["chi"], 800_000)
        self.assertEqual(by_month["2026-05"]["thu"], 2_000_000)
        self.assertEqual(by_month["2026-05"]["chi"], 0)
        months = [row["month"] for row in fund]
        self.assertEqual(months, sorted(months))

    def test_attendance_trend_rate_theo_tuan(self) -> None:
        """2 phiên trong cùng tuần (3 có mặt + 1 vắng) → rate = 0.75."""
        tz = timezone.get_current_timezone()
        # Thứ 2 và thứ 5 cùng một tuần ISO
        monday = datetime(2026, 9, 14, 8, 0, tzinfo=tz)   # 2026-W38
        thursday = datetime(2026, 9, 17, 8, 0, tzinfo=tz)  # 2026-W38
        self._make_attendance(monday, "CO_MAT")
        self._make_attendance(monday + timedelta(hours=1), "CO_MAT")
        self._make_attendance(thursday, "CO_MAT")
        self._make_attendance(thursday + timedelta(hours=1), "VANG")

        res = self.client.get("/api/v1/common/stats/trend/?months=12")
        att = res.data["data"]["attendance_trend"]
        self.assertEqual(len(att), 1)
        iso = monday.isocalendar()  # tuần mong đợi tính ĐỘNG từ dữ liệu test
        self.assertEqual(att[0]["week"], f"{iso.year}-W{iso.week:02d}")
        self.assertAlmostEqual(att[0]["rate"], 0.75, places=3)

    def test_months_khong_hop_le_400(self) -> None:
        res = self.client.get("/api/v1/common/stats/trend/?months=abc")
        self.assertEqual(res.status_code, 400)
        res = self.client.get("/api/v1/common/stats/trend/?months=0")
        self.assertEqual(res.status_code, 400)
        res = self.client.get("/api/v1/common/stats/trend/?months=13")
        self.assertEqual(res.status_code, 400)

    def test_months_mac_dinh_6(self) -> None:
        """Không truyền months → mặc định 6 (vẫn 200)."""
        res = self.client.get("/api/v1/common/stats/trend/")
        self.assertEqual(res.status_code, 200)
