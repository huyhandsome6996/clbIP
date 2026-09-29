"""
Tests — apps.members
CRUD phân quyền, IDOR protection, Trie search, Excel import/export, whitelist sort.
"""
import io
from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook, load_workbook
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.members.models import MemberProfile


def make_user(email: str, role: str = "MEMBER", ho_ten: str = "") -> Any:
    """Helper: tạo User (+ MemberProfile nếu là thành viên)."""
    user = User.objects.create_user(email=email, password="TestPass123!", role=role)
    if ho_ten:
        MemberProfile.objects.create(user=user, ho_ten=ho_ten, lop="22A401")
    return user


class MemberCRUDPermissionTests(TestCase):
    """Phân quyền tạo/xem/sửa/khóa thành viên."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.bcn = make_user("bcn@clbip.vn", role="BCN", ho_ten="Chủ Nhiệm")
        self.member = make_user("member@clbip.vn", role="MEMBER", ho_ten="Thành Viên A")

    def test_bcn_create_member_success(self) -> None:
        """BCN tạo member → 201, DB có User + Profile."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.post(
            "/api/v1/members/",
            {"email": "new@clbip.vn", "mssv": "22A401999", "ho_ten": "Người Mới", "lop": "22A402"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["success"])
        self.assertTrue(User.objects.filter(email="new@clbip.vn").exists())
        profile = MemberProfile.objects.get(user__email="new@clbip.vn")
        self.assertEqual(profile.ho_ten, "Người Mới")

    def test_member_create_forbidden(self) -> None:
        """MEMBER tạo member → 403."""
        self.client.force_authenticate(user=self.member)
        res = self.client.post(
            "/api/v1/members/",
            {"email": "x@clbip.vn", "mssv": "22A401888", "ho_ten": "X"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_duplicate_email_rejected(self) -> None:
        """Email trùng → 400/409."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.post(
            "/api/v1/members/",
            {"email": "member@clbip.vn", "mssv": "22A401777", "ho_ten": "Trùng"},
            format="json",
        )
        self.assertIn(res.status_code, (status.HTTP_400_BAD_REQUEST, status.HTTP_409_CONFLICT))

    def test_member_cannot_view_other_profile360_idor(self) -> None:
        """⚠ IDOR: Member A xem profile360 của B → 403. Của chính mình → 200."""
        other = make_user("other@clbip.vn", role="MEMBER", ho_ten="Thành Viên B")
        self.client.force_authenticate(user=self.member)

        res_other = self.client.get(f"/api/v1/members/{other.member_profile.pk}/profile360/")
        self.assertEqual(res_other.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(res_other.data["success"])

        res_self = self.client.get(f"/api/v1/members/{self.member.member_profile.pk}/profile360/")
        self.assertEqual(res_self.status_code, status.HTTP_200_OK)
        self.assertEqual(res_self.data["data"]["ho_ten"], "Thành Viên A")

    def test_bcn_view_any_profile360(self) -> None:
        """BCN xem profile360 của bất kỳ ai → 200."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get(f"/api/v1/members/{self.member.member_profile.pk}/profile360/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["data"]["stats"]["xp_points"], 0)

    def test_member_cannot_edit_sensitive_fields(self) -> None:
        """Member tự sửa email/mssv/trạng thái → 400."""
        self.client.force_authenticate(user=self.member)
        res = self.client.patch(
            f"/api/v1/members/{self.member.member_profile.pk}/",
            {"mssv": "HACKED", "trang_thai_hd": "LEAVE"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_member_can_edit_own_basic_info(self) -> None:
        """Member tự sửa sdt của mình → 200."""
        self.client.force_authenticate(user=self.member)
        res = self.client.patch(
            f"/api/v1/members/{self.member.member_profile.pk}/",
            {"sdt": "0900900900"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.member.member_profile.refresh_from_db()
        self.assertEqual(self.member.member_profile.sdt, "0900900900")

    def test_lock_member(self) -> None:
        """BCN khóa member → is_active=False; member bị khóa không đăng nhập được."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.delete(f"/api/v1/members/{self.member.member_profile.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

        # Đăng nhập bị từ chối
        client = APIClient()
        login = client.post(
            "/api/v1/auth/token/",
            {"email": "member@clbip.vn", "password": "TestPass123!"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_401_UNAUTHORIZED)


class MemberSearchTests(TestCase):
    """Tìm kiếm Trie — hỗ trợ không dấu + MSSV."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.bcn = make_user("bcn2@clbip.vn", role="BCN", ho_ten="Ban Chủ Nhiệm")
        make_user("m1@clbip.vn", ho_ten="Nguyễn Nhật Nam")
        m2 = User.objects.create_user(email="m2@clbip.vn", password="TestPass123!")
        MemberProfile.objects.create(user=m2, ho_ten="Hoàng Bảo Trân", lop="22A402")
        m3 = User.objects.create_user(email="m3@clbip.vn", password="TestPass123!", mssv="22A401123")
        MemberProfile.objects.create(user=m3, ho_ten="Trần Văn Tèo", lop="22A403")

    def test_search_without_accents(self) -> None:
        """q='nguyen nhat' (không dấu) → tìm ra 'Nguyễn Nhật Nam'."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/search/?q=nguyen nhat")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        names = [item["ho_ten"] for item in res.data["data"]["items"]]
        self.assertIn("Nguyễn Nhật Nam", names)

    def test_search_by_mssv_prefix(self) -> None:
        """q='22A4011' → tìm theo MSSV."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/search/?q=22A4011")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["mssv"], "22A401123")

    def test_search_empty_query(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/search/?q=")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["data"]["count"], 0)

    def test_search_requires_auth(self) -> None:
        res = APIClient().get("/api/v1/members/search/?q=nguyen")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class MemberListSortWhitelistTests(TestCase):
    """Whitelist sort — payload độc hại vẫn xử lý an toàn."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.bcn = make_user("bcn3@clbip.vn", role="BCN", ho_ten="BCN")
        make_user("s1@clbip.vn", ho_ten="Sinh Viên 1")
        make_user("s2@clbip.vn", ho_ten="Sinh Viên 2")

    def test_malicious_sort_param_is_sanitized(self) -> None:
        """?sort=email'; -- → không lỗi 500, fallback '-xp_points'."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/", {"sort": "email'; --"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["success"])

    def test_list_pagination_envelope(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("pagination", res.data["data"])
        self.assertGreaterEqual(res.data["data"]["pagination"]["total_items"], 3)

    def test_member_list_requires_bcn(self) -> None:
        member = make_user("mm@clbip.vn", ho_ten="MM")
        self.client.force_authenticate(user=member)
        res = self.client.get("/api/v1/members/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class MemberExcelTests(TestCase):
    """Import / Export Excel."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.bcn = make_user("bcn4@clbip.vn", role="BCN", ho_ten="BCN Excel")

    def _xlsx_bytes(self, rows: list) -> io.BytesIO:
        wb = Workbook()
        ws = wb.active
        ws.append(["ho_ten", "email", "mssv", "lop", "sdt"])
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_import_excel_with_error_preview(self) -> None:
        """2 dòng hợp lệ + 1 dòng trùng mssv → created=2, errors=1."""
        self.client.force_authenticate(user=self.bcn)
        # Tạo trước user trùng MSSV
        make_user("exist@clbip.vn", ho_ten="Đã Tồn Tại")
        existing = User.objects.get(email="exist@clbip.vn")
        existing.mssv = "22A401111"
        existing.save()

        buf = self._xlsx_bytes([
            ["Sinh Viên 1", "sv1@clbip.vn", "22A401001", "22A401", "0901"],
            ["Sinh Viên 2", "sv2@clbip.vn", "22A401002", "22A401", "0902"],
            ["Trùng MSSV", "sv3@clbip.vn", "22A401111", "22A401", "0903"],
        ])
        upload = SimpleUploadedFile("thanh_vien.xlsx", buf.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        res = self.client.post(
            "/api/v1/members/import-excel/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["data"]["created"], 2)
        self.assertEqual(len(res.data["data"]["errors"]), 1)
        self.assertIn("22A401111", res.data["data"]["errors"][0]["error"])

    def test_import_requires_xlsx(self) -> None:
        self.client.force_authenticate(user=self.bcn)
        upload = SimpleUploadedFile("not_excel.txt", b"not excel", content_type="text/plain")
        res = self.client.post(
            "/api/v1/members/import-excel/",
            {"file": upload},
            format="multipart",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_export_excel(self) -> None:
        """BCN xuất file → 200 + đọc lại được nội dung xlsx."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/export-excel/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("spreadsheetml", res["Content-Type"])
        wb = load_workbook(io.BytesIO(res.content))
        ws = wb.active
        self.assertEqual(ws.title, "Thành viên")
        self.assertGreaterEqual(ws.max_row, 2)  # header + ít nhất 1 dòng


class Profile360DataTests(TestCase):
    """Dữ liệu tổng hợp hồ sơ 360°."""

    def setUp(self) -> None:
        self.client = APIClient()
        self.member = make_user("p@clbip.vn", ho_ten="Profile Test")

    def test_profile360_contains_all_sections(self) -> None:
        self.client.force_authenticate(user=self.member)
        res = self.client.get(f"/api/v1/members/{self.member.member_profile.pk}/profile360/")
        data = res.data["data"]
        self.assertIn("stats", data)
        self.assertIn("badges", data)
        self.assertIn("board_positions", data)
        self.assertIn("recent_xp", data)
        self.assertIsNone(data["stats"]["attendance_rate_percent"])  # chưa có record

    def test_board_list_and_create(self) -> None:
        """GET /board/ mọi user; POST /board/ chỉ BCN."""
        from apps.members.models import BoardMember

        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/members/board/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        res_post = self.client.post(
            "/api/v1/members/board/",
            {"member": self.member.member_profile.pk, "nhiem_ky": "2025-2026",
             "chuc_vu": "CHU_NHIEM", "ban_phu_trach": "HOC_THUAT"},
            format="json",
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=make_user("b5@clbip.vn", role="BCN"))
        res_post2 = self.client.post(
            "/api/v1/members/board/",
            {"member": self.member.member_profile.pk, "nhiem_ky": "2025-2026",
             "chuc_vu": "CHU_NHIEM", "ban_phu_trach": "HOC_THUAT"},
            format="json",
        )
        self.assertEqual(res_post2.status_code, status.HTTP_201_CREATED)
        self.assertTrue(BoardMember.objects.filter(member=self.member.member_profile).exists())


class MemberSearchPIITests(TestCase):
    """
    QA-Audit 2a — chống rò rỉ PII qua tìm kiếm thành viên:
    - MEMBER thường: chỉ nhận trường công khai (id/ho_ten/lop/avatar/level/xp),
      KHÔNG có email/sdt/mssv; chỉ thấy thành viên đang HOẠT ĐỘNG.
    - BCN/ADMIN: nhận serializer đầy đủ phục vụ quản lý.
    """

    def setUp(self) -> None:
        self.client = APIClient()
        self.bcn = make_user("piibcn@clbip.vn", role="BCN", ho_ten="Chủ Nhiệm Test")
        self.member = make_user("piimember@clbip.vn", role="MEMBER", ho_ten="Thành Viên PII")
        self.other = make_user("piiother@clbip.vn", role="MEMBER", ho_ten="Nguyễn Bình Yên")

    def test_member_search_khong_chua_pii(self) -> None:
        """MEMBER search → items không có email/sdt/mssv."""
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/members/search/", {"q": "nguyen"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data["data"]["items"]
        self.assertGreaterEqual(len(items), 1)
        for field in ("email", "sdt", "mssv"):
            self.assertNotIn(field, items[0])
        for field in ("id", "ho_ten", "lop", "xp_points", "current_level"):
            self.assertIn(field, items[0])

    def test_member_search_chi_thay_thanh_vien_active(self) -> None:
        """MEMBER không thấy thành viên INACTIVE; BCN vẫn thấy."""
        profile = MemberProfile.objects.get(user__email="piiother@clbip.vn")
        profile.trang_thai_hd = MemberProfile.TrangThai.INACTIVE
        profile.save(update_fields=["trang_thai_hd"])

        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/members/search/", {"q": "nguyen"})
        self.assertEqual(res.data["data"]["items"], [])

        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/search/", {"q": "nguyen"})
        self.assertGreaterEqual(len(res.data["data"]["items"]), 1)

    def test_bcn_search_nhan_serializer_day_du(self) -> None:
        """BCN search → có email (mssv có thể None nếu không đặt)."""
        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/search/", {"q": "nguyen"})
        items = res.data["data"]["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertIn("email", items[0])
        self.assertIn("mssv", items[0])

    def test_board_list_member_khong_nhan_mssv(self) -> None:
        """GET /members/board/ với MEMBER → không lộ member_mssv (PII cán bộ)."""
        from apps.members.models import BoardMember

        BoardMember.objects.create(
            member=MemberProfile.objects.get(user=self.bcn),
            nhiem_ky="2025-2026", chuc_vu="CHU_NHIEM", ban_phu_trach="HOC_THUAT",
        )
        self.client.force_authenticate(user=self.member)
        res = self.client.get("/api/v1/members/board/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.data["data"]["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertNotIn("member_mssv", items[0])

        self.client.force_authenticate(user=self.bcn)
        res = self.client.get("/api/v1/members/board/")
        self.assertIn("member_mssv", res.data["data"]["items"][0])
