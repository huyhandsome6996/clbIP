"""
Regression tests — audit 06/10/2026 (F03, F06)
===============================================
F03: POST /members/ với mật khẩu để trống → `data.initial_password` trả về
     ĐÚNG 1 LẦN (login được bằng nó); mọi endpoint đọc khác KHÔNG chứa
     credential; admin tự nhập mật khẩu thì KHÔNG echo.
F06: GET /members/?trang_thai=ACTIVE là tham số canonical — chỉ trả ACTIVE
     (không trả INACTIVE/LEAVE); kết hợp search/lớp/phân trang đúng.
"""
import uuid

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.authentication.models import User
from apps.members.models import MemberProfile

MEMBERS_URL = "/api/v1/members/"


@override_settings(AXES_ENABLED=False)
class MemberPasswordOnboardingTests(APITestCase):
    """F03 — credential khởi tạo một lần, không rò rỉ qua các kênh đọc."""

    def setUp(self) -> None:
        cache.clear()
        self.bcn = User.objects.create_user(
            email="onboard-bcn@clbip.test", password="TestPass123!", role="BCN",
        )
        MemberProfile.objects.create(user=self.bcn, ho_ten="BCN Onboard")
        self.client.force_authenticate(user=self.bcn)

    def _create(self, password="", email=None, mssv=None):
        suffix = uuid.uuid4().hex[:6]
        return self.client.post(
            MEMBERS_URL,
            {
                "ho_ten": f"Thành Viên {suffix}",
                "email": email or f"tv-{suffix}@student.hueuni.edu.vn",
                "mssv": mssv or f"22A{suffix.upper()}",
                "password": password,
            },
            format="json",
        )

    def test_f03_empty_password_returns_initial_password_once(self):
        res = self._create()
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIn("initial_password", res.data["data"])
        self.assertTrue(res.data["data"]["initial_password"])
        # Message KHÔNG chứa mật khẩu (envelope có thể vào log)
        self.assertNotIn(res.data["data"]["initial_password"], res.data["message"])

    def test_f03_login_with_initial_password_works(self):
        res = self._create()
        pwd = res.data["data"]["initial_password"]
        email = res.data["data"]["email"]
        client = APIClient()  # client mới — chưa authenticate
        login = client.post(
            "/api/v1/auth/token/", {"email": email, "password": pwd}, format="json"
        )
        self.assertEqual(login.status_code, 200, login.data)

    def test_f03_initial_password_absent_from_reads_and_export(self):
        res = self._create()
        member_id = res.data["data"]["id"]
        pwd = res.data["data"]["initial_password"]

        for url in [f"{MEMBERS_URL}{member_id}/", f"{MEMBERS_URL}{member_id}/profile360/"]:
            detail = self.client.get(url)
            self.assertEqual(detail.status_code, 200)
            self.assertNotIn("initial_password", detail.data["data"])
            self.assertNotIn(pwd, str(detail.data))

        listing = self.client.get(MEMBERS_URL)
        self.assertNotIn(pwd, str(listing.data))

        export = self.client.get(f"{MEMBERS_URL}export-excel/")
        self.assertEqual(export.status_code, 200)
        self.assertNotIn(pwd.encode(), export.content)

    def test_f03_admin_password_not_echoed(self):
        """BCN tự nhập mật khẩu → response không echo credential."""
        res = self._create(password="TuChon@2026 VN")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertNotIn("initial_password", res.data["data"])


@override_settings(AXES_ENABLED=False)
class MemberStatusFilterTests(APITestCase):
    """F06 — query list dùng `trang_thai=` (canonical), kết hợp filter đúng."""

    def setUp(self) -> None:
        cache.clear()
        self.bcn = User.objects.create_user(
            email="filter-bcn@clbip.test", password="TestPass123!", role="BCN",
        )
        MemberProfile.objects.create(user=self.bcn, ho_ten="BCN Filter")
        self.client.force_authenticate(user=self.bcn)

        specs = [
            ("A", "ACTIVE"), ("B", "ACTIVE"), ("C", "ACTIVE"),
            ("D", "INACTIVE"), ("E", "LEAVE"),
        ]
        for name, status in specs:
            user = User.objects.create_user(
                email=f"mb-{name.lower()}@clbip.test", password="TestPass123!", role="MEMBER",
            )
            MemberProfile.objects.create(
                user=user, ho_ten=f"Thành Viên {name}",
                lop="22A" if name in ("A", "D") else "23C", trang_thai_hd=status,
            )
        # self.bcn cũng có profile ACTIVE (không lop) → ACTIVE tổng = 4

    def test_f06_trang_thai_canonical_param_filters(self):
        res = self.client.get(MEMBERS_URL, {"trang_thai": "ACTIVE"})
        self.assertEqual(res.status_code, 200)
        items = res.data["data"]["items"]
        # 3 member ACTIVE tạo trong setUp + profile BCN (ACTIVE) = 4
        self.assertEqual(res.data["data"]["pagination"]["total_items"], 4)
        self.assertTrue(all(i["trang_thai_hd"] == "ACTIVE" for i in items))
        # INACTIVE/LEAVE không lọt vào kết quả ACTIVE
        statuses = {i["trang_thai_hd"] for i in items}
        self.assertNotIn("INACTIVE", statuses)
        self.assertNotIn("LEAVE", statuses)

    def test_f06_other_statuses(self):
        res_inactive = self.client.get(MEMBERS_URL, {"trang_thai": "INACTIVE"})
        self.assertEqual(res_inactive.data["data"]["pagination"]["total_items"], 1)
        res_leave = self.client.get(MEMBERS_URL, {"trang_thai": "LEAVE"})
        self.assertEqual(res_leave.data["data"]["pagination"]["total_items"], 1)

    def test_f06_filter_combined_with_search_and_lop(self):
        res = self.client.get(MEMBERS_URL, {"trang_thai": "ACTIVE", "lop": "22A", "search": "A"})
        items = res.data["data"]["items"]
        self.assertTrue(
            all(i["trang_thai_hd"] == "ACTIVE" and i.get("lop") == "22A" for i in items)
        )

    def test_f06_pagination_respects_filter(self):
        res = self.client.get(MEMBERS_URL, {"trang_thai": "ACTIVE", "page": 1, "page_size": 2})
        page_data = res.data["data"]["pagination"]
        self.assertEqual(page_data["total_items"], 4)
        self.assertEqual(page_data["total_pages"], 2)
        self.assertEqual(len(res.data["data"]["items"]), 2)
        # Trang 2 — vẫn toàn ACTIVE, đúng tổng
        res2 = self.client.get(MEMBERS_URL, {"trang_thai": "ACTIVE", "page": 2, "page_size": 2})
        self.assertEqual(len(res2.data["data"]["items"]), 2)
