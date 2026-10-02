"""
Tests — apps.documents
=======================
Phủ bắt buộc:
    1. Upload PDF thật → 201, file_size > 0, file_type="pdf", tên file UUID.
    2. Upload .exe → 400 FileValidationException (whitelist tầng 1).
    3. Đổi đuôi file độc hại (nội dung không khớp magic bytes) → 400 (tầng 3).
    4. Upload PNG thật (magic \\x89PNG\\r\\n) → 201.
    5. Search Trie: q="c++" (qua tag) và q="de thi" (không dấu) trả đúng doc.
    6. Download → luot_tai +1, nội dung stream đúng.
    7. Phân quyền xóa: MEMBER xóa của người khác 403; BCN xóa được; người upload xóa được.
    8. Chưa đăng nhập GET → 401.
Extra:
    9. validate_file: tệp > 15MB → FileValidationException (tầng 2, fake file không tốn đĩa).
"""
import os
import re
import tempfile
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.views import APIView

from apps.authentication.models import User
from apps.common.exceptions import FileValidationException
from apps.documents.models import Document
from apps.documents.services import DocumentService
from apps.members.models import MemberProfile

PDF_BYTES: bytes = b"%PDF-1.4\n% Tai lieu test cho CLB IP DHSP Hue\n" + b"x" * 256
PNG_BYTES: bytes = (
    b"\x89PNG\r\n\x1a\n"  # PNG signature chuẩn
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r"
    b"\n\x2d\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# MEDIA_ROOT test trỏ vào thư mục tạm — không đụng media production
TEST_MEDIA_ROOT = override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="clbip_test_media_doc_"))


class ThrottleFreeMixin:
    """Tắt throttle mặc định khi test — burst 10/s gây 429 nhiễu test suite."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(APIView, "throttle_classes", [])
        patcher.start()
        self.addCleanup(patcher.stop)


def make_pdf_file(name: str = "tai-lieu.pdf") -> SimpleUploadedFile:
    """Tạo tệp PDF thật (magic %PDF-) cho upload."""
    return SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf")


@TEST_MEDIA_ROOT
class DocumentUploadTests(ThrottleFreeMixin, APITestCase):
    """Test 4 tầng File Upload Hardening qua POST /api/v1/documents/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="member_a", email="member@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010001",
        )
        MemberProfile.objects.create(user=cls.member, ho_ten="Nguyễn Văn A")
        cls.upload_url = reverse("document_list")

    def test_01_upload_pdf_that_bien_201(self) -> None:
        """(1) Upload PDF thật → 201, DB lưu đúng size/type, tên file UUID."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": make_pdf_file("huong-dan-git.pdf"),
            "tieu_de": "Hướng dẫn Git cho CLB",
            "nhom": "CHUYEN_MON",
            "tags": "Git, DevOps",
            "mo_ta": "Tài liệu onboarding thành viên mới",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        self.assertIn("+100 XP", resp.data["message"])

        doc = Document.objects.get(tieu_de="Hướng dẫn Git cho CLB")
        self.assertGreater(doc.file_size, 0)
        self.assertEqual(doc.file_type, "pdf")
        self.assertEqual(doc.uploaded_by, self.member)
        # Tầng 4: tên file trên đĩa phải là uuid4().hex + ".pdf" (32 hex)
        basename = os.path.basename(doc.file.name)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}\.pdf", basename), basename)
        self.assertEqual(doc.luot_tai, 0)
        # Serializer: hiển thị họ tên người chia sẻ qua profile
        self.assertEqual(resp.data["data"]["uploaded_by_ho_ten"], "Nguyễn Văn A")

    def test_02_upload_exe_bi_tu_choi(self) -> None:
        """(2) Upload .exe → 400 whitelist đuôi, bất kể nội dung là gì."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile("virus.exe", b"MZ\x90\x00binary", content_type="application/octet-stream"),
            "tieu_de": "Phần mềm hack",
            "nhom": "KY_NANG",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp.data["success"])
        self.assertIn("Định dạng không được phép", resp.data["message"])
        self.assertEqual(Document.objects.count(), 0)

    def test_03_doi_duoi_file_doc_hai_bat_magic_bytes(self) -> None:
        """(3) Nội dung HTML đeo mác .pdf → 400 'Nội dung tệp không khớp định dạng'."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile("malware.pdf", b"<script>hack</script>", content_type="application/pdf"),
            "tieu_de": "Tài liệu giả mạo",
            "nhom": "CHUYEN_MON",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(resp.data["success"])
        self.assertIn("Nội dung tệp không khớp định dạng", resp.data["message"])
        self.assertEqual(Document.objects.count(), 0)

    def test_04_upload_png_that_bien_201(self) -> None:
        """(4) PNG thật (magic \\x89PNG\\r\\n) → 201 với file_type='png'."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile("pic.png", PNG_BYTES, content_type="image/png"),
            "tieu_de": "Ảnh slide workshop",
            "nhom": "KY_NANG",
            "tags": "Slide, Workshop",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data["success"])
        doc = Document.objects.get(tieu_de="Ảnh slide workshop")
        self.assertEqual(doc.file_type, "png")
        self.assertTrue(doc.file.name.endswith(".png"))


@TEST_MEDIA_ROOT
class DocumentSearchTests(ThrottleFreeMixin, APITestCase):
    """(5) DSA 3 — Prefix Trie: tìm có dấu/không dấu, qua tag."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="member_s", email="searcher@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010002",
        )
        cls.search_url = reverse("document_search")
        for tieu_de, tags in [
            ("Hướng dẫn C++ cơ bản", "C++, Cơ bản"),
            ("Đề thi Web", "Web, Đề thi"),
            ("Tài liệu Python", "Python"),
        ]:
            Document.objects.create(
                tieu_de=tieu_de,
                nhom=Document.Nhom.CHUYEN_MON,
                tags=tags,
                file=SimpleUploadedFile("seed.pdf", PDF_BYTES, content_type="application/pdf"),
                file_type="pdf",
                file_size=len(PDF_BYTES),
                uploaded_by=cls.member,
            )

    def _search(self, q: str) -> dict:
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(self.search_url, {"q": q})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return resp.data["data"]

    def test_05a_tim_qua_tag_c_plus_plus(self) -> None:
        """q='c++' → trả đúng doc 'Hướng dẫn C++ cơ bản' (khớp qua tag)."""
        data = self._search("c++")
        self.assertGreaterEqual(data["count"], 1)
        titles = [item["tieu_de"] for item in data["items"]]
        self.assertIn("Hướng dẫn C++ cơ bản", titles)
        self.assertNotIn("Đề thi Web", titles)

    def test_05b_tim_khong_dau_de_thi(self) -> None:
        """q='de thi' (không dấu) → trả đúng doc 'Đề thi Web' nhờ normalize Trie."""
        data = self._search("de thi")
        self.assertGreaterEqual(data["count"], 1)
        titles = [item["tieu_de"] for item in data["items"]]
        self.assertIn("Đề thi Web", titles)
        self.assertNotIn("Tài liệu Python", titles)

    def test_05c_q_rong_tra_rong(self) -> None:
        """q rỗng → items rỗng, count = 0 (theo hợp đồng service)."""
        data = self._search("")
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["items"], [])


@TEST_MEDIA_ROOT
class DocumentDownloadTests(ThrottleFreeMixin, APITestCase):
    """(6) Download: đếm lượt tải atomic + stream nội dung đúng."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="member_d", email="downloader@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010003",
        )
        cls.doc = Document.objects.create(
            tieu_de="Slide Sinh hoạt định kỳ",
            nhom=Document.Nhom.NGHIEP_VU,
            tags="Slide",
            file=SimpleUploadedFile("slide.pdf", PDF_BYTES, content_type="application/pdf"),
            file_type="pdf",
            file_size=len(PDF_BYTES),
            uploaded_by=cls.member,
        )

    def test_06_download_tang_luot_tai_va_stream_dung(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("document_download", kwargs={"pk": self.doc.pk}))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Nội dung stream đúng PDF
        self.assertEqual(b"".join(resp.streaming_content), PDF_BYTES)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])
        # luot_tai tăng 1 sau khi tải
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.luot_tai, 1)

    def test_06b_download_doc_khong_ton_tai_404(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("document_download", kwargs={"pk": 99999}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


@TEST_MEDIA_ROOT
class DocumentDeletePermissionTests(ThrottleFreeMixin, APITestCase):
    """(7) Chống IDOR: chỉ BCN/ADMIN hoặc người upload được xóa."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.uploader = User.objects.create_user(
            username="uploader", email="uploader@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010004",
        )
        cls.other_member = User.objects.create_user(
            username="member_b", email="memberb@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010005",
        )
        cls.bcn = User.objects.create_user(
            username="bcn", email="bcn@clbip.test", password="TestPass123!",
            role=User.Role.BCN, mssv="22A4010006",
        )

    def _create_doc(self, tieu_de: str) -> Document:
        return Document.objects.create(
            tieu_de=tieu_de,
            nhom=Document.Nhom.CHUYEN_MON,
            file=SimpleUploadedFile("x.pdf", PDF_BYTES, content_type="application/pdf"),
            file_type="pdf",
            file_size=len(PDF_BYTES),
            uploaded_by=self.uploader,
        )

    def test_07a_member_xoa_cua_nguoi_khac_403(self) -> None:
        doc = self._create_doc("Tài liệu của uploader")
        self.client.force_authenticate(user=self.other_member)
        resp = self.client.delete(reverse("document_detail", kwargs={"pk": doc.pk}))

        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(resp.data["success"])
        self.assertTrue(Document.objects.filter(pk=doc.pk).exists())

    def test_07b_bcn_xoa_duoc(self) -> None:
        doc = self._create_doc("Tài liệu BCN xóa")
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.delete(reverse("document_detail", kwargs={"pk": doc.pk}))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["success"])
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())

    def test_07c_nguoi_upload_xoa_duoc(self) -> None:
        doc = self._create_doc("Tài liệu tự xóa")
        self.client.force_authenticate(user=self.uploader)
        resp = self.client.delete(reverse("document_detail", kwargs={"pk": doc.pk}))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(Document.objects.filter(pk=doc.pk).exists())


class DocumentAuthTests(ThrottleFreeMixin, APITestCase):
    """(8) Chưa đăng nhập → 401 envelope chuẩn."""

    def test_08_chua_auth_get_401(self) -> None:
        resp = self.client.get(reverse("document_list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(resp.data["success"])
        self.assertIn("đăng nhập", resp.data["message"])


class DocumentServiceUnitTests(APITestCase):
    """Extra: unit test tầng 2 (size 15MB) với fake file — không tốn đĩa."""

    def test_09_file_vuot_15mb_bat_exception(self) -> None:
        class FakeBigFile:
            """Stub mô phỏng tệp > 15MB, magic đúng PDF."""

            name = "big.pdf"
            size = 16 * 1024 * 1024

            def read(self, n: int = -1) -> bytes:
                return b"%PDF-1.4"

            def seek(self, pos: int, whence: int = 0) -> None:
                return None

        with self.assertRaises(FileValidationException) as ctx:
            DocumentService.validate_file(FakeBigFile())
        self.assertIn("15MB", str(ctx.exception.message))


@TEST_MEDIA_ROOT
class DocumentPhamViScopeTests(ThrottleFreeMixin, APITestCase):
    """
    QA-Audit 2d — phạm vi truy cập tài liệu (pham_vi):
    - MEMBER không thấy/tải/search được tài liệu BCN_ONLY (404 — không hé lộ).
    - BCN thấy đầy đủ.
    - MEMBER upload kèm pham_vi=BCN_ONLY bị ép về PUBLIC_MEMBER.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            email="pv-member@clbip.test", password="TestPass123!", role=User.Role.MEMBER,
        )
        MemberProfile.objects.create(user=cls.member, ho_ten="Thành Viên Phạm Vi")
        cls.bcn = User.objects.create_user(
            email="pv-bcn@clbip.test", password="TestPass123!", role=User.Role.BCN,
        )
        MemberProfile.objects.create(user=cls.bcn, ho_ten="BCN Phạm Vi")

    def _upload(self, as_user, pham_vi=None) -> Document:
        """Helper: upload 1 tài liệu PDF và trả về instance."""
        self.client.force_authenticate(user=as_user)
        payload = {
            "file": make_pdf_file("tai-lieu-pham-vi.pdf"),
            "tieu_de": f"TaiLieuPV-{pham_vi or 'pub'}-{Document.objects.count()}",
            "nhom": "CHUYEN_MON",
        }
        if pham_vi:
            payload["pham_vi"] = pham_vi
        resp = self.client.post(reverse("document_list"), payload, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        return Document.objects.get(pk=resp.data["data"]["id"])

    def _make_bcn_only(self, owner) -> Document:
        """Tạo trực tiếp tài liệu BCN_ONLY trong DB (không qua API)."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        doc = Document(
            tieu_de="Noi-Bo-BCN-Quan-Tri", nhom="NGHIEP_VU",
            pham_vi=Document.PhamVi.BCN_ONLY, tags="noibo", file=SimpleUploadedFile("x.pdf", PDF_BYTES),
        )
        doc.uploaded_by = owner
        doc.save()
        return doc

    def test_01_member_khong_thay_bcn_only_trong_danh_sach(self) -> None:
        secret = self._make_bcn_only(self.bcn)
        self._upload(self.bcn)  # 1 tài liệu công khai
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("document_list"))
        items = resp.data["data"]["items"]
        self.assertTrue(all(d["pham_vi"] != "BCN_ONLY" for d in items))
        self.assertFalse(any(d["id"] == secret.pk for d in items))

    def test_02_bcn_thay_bcn_only(self) -> None:
        secret = self._make_bcn_only(self.bcn)
        self.client.force_authenticate(user=self.bcn)
        resp = self.client.get(reverse("document_list"))
        self.assertTrue(any(d["id"] == secret.pk for d in resp.data["data"]["items"]))

    def test_03_member_chi_tiet_bcn_only_404(self) -> None:
        secret = self._make_bcn_only(self.bcn)
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(f"/api/v1/documents/{secret.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # BCN xem được
        self.client.force_authenticate(user=self.bcn)
        resp2 = self.client.get(f"/api/v1/documents/{secret.pk}/")
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_04_member_khong_tai_duoc_bcn_only(self) -> None:
        """Test bắt buộc của audit: MEMBER tải BCN_ONLY → bị chặn, luot_tai không đổi."""
        secret = self._make_bcn_only(self.bcn)
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(f"/api/v1/documents/{secret.pk}/download/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        secret.refresh_from_db()
        self.assertEqual(secret.luot_tai, 0)

    def test_05_member_khong_search_thay_bcn_only(self) -> None:
        secret = self._make_bcn_only(self.bcn)
        self.client.force_authenticate(user=self.member)
        resp = self.client.get("/api/v1/documents/search/", {"q": "Noi-Bo"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["data"]["items"], [])
        # BCN tìm thấy
        self.client.force_authenticate(user=self.bcn)
        resp2 = self.client.get("/api/v1/documents/search/", {"q": "Noi-Bo"})
        self.assertGreaterEqual(len(resp2.data["data"]["items"]), 1)

    def test_06_member_upload_khong_dat_duoc_bcn_only(self) -> None:
        doc = self._upload(self.member, pham_vi="BCN_ONLY")
        doc.refresh_from_db()
        self.assertEqual(doc.pham_vi, Document.PhamVi.PUBLIC_MEMBER)

    def test_07_bcn_upload_dat_duoc_bcn_only(self) -> None:
        doc = self._upload(self.bcn, pham_vi="BCN_ONLY")
        doc.refresh_from_db()
        self.assertEqual(doc.pham_vi, Document.PhamVi.BCN_ONLY)

    def test_08_member_khong_nhan_email_nguoi_upload(self) -> None:
        """QA-Audit 2a: uploaded_by với MEMBER là tên hiển thị, không phải email."""
        doc = self._upload(self.bcn)
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(f"/api/v1/documents/{doc.pk}/")
        self.assertEqual(resp.data["data"]["uploaded_by"], "BCN Phạm Vi")
        # BCN vẫn xem được email
        self.client.force_authenticate(user=self.bcn)
        resp2 = self.client.get(f"/api/v1/documents/{doc.pk}/")
        self.assertEqual(resp2.data["data"]["uploaded_by"], self.bcn.email)


@TEST_MEDIA_ROOT
class SearchIndexTrieCacheTests(TestCase):
    """
    QA-Audit đợt 2 (P2-1 + P2-2) — Cache Trie tài liệu:
        1. `_built_at` phải theo TỪNG scope: PUBLIC dựng lại không được gán
           version mới cho FULL (regression của bug đã tái hiện trong audit).
        2. Invalidation phải hiệu lực QUA CÁC WORKER qua cache dùng chung:
           bump counter ở "worker khác" → process này phải dựng lại Trie.
        3. Cache hỏng → fallback counter trong process, không lỗi request.
    """

    def setUp(self) -> None:
        from django.core.cache import cache

        cache.clear()
        self.uploader = User.objects.create_user(
            username="trie-uploader", email="trie@clbip.test",
            password="TestPass123!", role=User.Role.MEMBER,
        )

    def _create_doc(self, tieu_de: str, pham_vi: str = Document.PhamVi.PUBLIC_MEMBER) -> Document:
        return Document.objects.create(
            tieu_de=tieu_de,
            nhom=Document.Nhom.CHUYEN_MON,
            pham_vi=pham_vi,
            file=SimpleUploadedFile("x.pdf", PDF_BYTES, content_type="application/pdf"),
            file_type="pdf",
            file_size=len(PDF_BYTES),
            uploaded_by=self.uploader,
        )

    def test_public_rebuild_khong_gan_version_cho_full(self) -> None:
        """Regression P2-1: đổi doc → search PUBLIC → search FULL phải thấy thay đổi."""
        from apps.documents import search_index

        doc = self._create_doc("Tai lieu goc CLB")

        # BCN dựng FULL trước (version v1)
        trie_full_v1 = search_index.get_trie(search_index.SCOPE_FULL)
        self.assertIn(doc.pk, trie_full_v1.search_prefix("tai lieu"))

        # Đổi tiêu đề → post_save invalidate (version v2)
        doc.tieu_de = "De thi OOP 2026"
        doc.save(update_fields=["tieu_de", "updated_at"])

        # Member tìm PUBLIC trước → PUBLIC dựng lại tại v2
        trie_public = search_index.get_trie(search_index.SCOPE_PUBLIC)
        self.assertIn(doc.pk, trie_public.search_prefix("de thi"))

        # BCN tìm FULL sau → PHẢI dựng lại (bug cũ: coi FULL còn mới tại v1)
        trie_full_v2 = search_index.get_trie(search_index.SCOPE_FULL)
        self.assertIsNot(trie_full_v2, trie_full_v1, "FULL phải được dựng lại sau khi PUBLIC dựng lại")
        self.assertIn(doc.pk, trie_full_v2.search_prefix("de thi"))
        self.assertNotIn(doc.pk, trie_full_v2.search_prefix("tai lieu"))

    def test_invalidate_da_worker_qua_cache_dung_chung(self) -> None:
        """P2-2: bump counter ở 'worker khác' (chỉ cache) → process này rebuild."""
        from django.core.cache import cache

        from apps.documents import search_index

        self._create_doc("Tai lieu worker 1")
        trie_1 = search_index.get_trie(search_index.SCOPE_PUBLIC)
        self.assertIn(
            Document.objects.get(tieu_de="Tai lieu worker 1").pk,
            trie_1.search_prefix("tai lieu"),
        )

        # Tạo doc KHÔNG bắn signal cục bộ (mô phỏng: worker khác nhận ghi)
        # ⚠️ disconnect phải truyền đúng sender — lookup key = (dispatch_uid, _make_id(sender))
        from django.db.models.signals import post_delete, post_save

        post_save.disconnect(sender=Document, dispatch_uid="trie_doc_save")
        post_delete.disconnect(sender=Document, dispatch_uid="trie_doc_del")
        try:
            self._create_doc("Tai lieu worker 2")
        finally:
            post_save.connect(search_index.invalidate, sender=Document, dispatch_uid="trie_doc_save")
            post_delete.connect(search_index.invalidate, sender=Document, dispatch_uid="trie_doc_del")

        # Process này chưa biết gì → Trie cũ không có doc mới
        trie_stale = search_index.get_trie(search_index.SCOPE_PUBLIC)
        self.assertEqual(trie_stale, trie_1)

        # "Worker khác" đã tăng counter dùng chung → process này phải thấy
        try:
            cache.incr(search_index._VERSION_CACHE_KEY)
        except ValueError:
            cache.add(search_index._VERSION_CACHE_KEY, 99, timeout=None)

        trie_2 = search_index.get_trie(search_index.SCOPE_PUBLIC)
        self.assertIsNot(trie_2, trie_stale, "Counter dùng chung đổi → phải dựng lại Trie")
        # Doc của worker khác giờ phải xuất hiện trong kết quả tìm
        pks = trie_2.search_prefix("tai lieu")
        doc2 = Document.objects.get(tieu_de="Tai lieu worker 2")
        self.assertIn(doc2.pk, pks)

    def test_cache_hong_fallback_counter_local(self) -> None:
        """Cache hỏng (DummyCache — get luôn None) → invalidation local vẫn chạy."""
        from apps.documents import search_index

        with override_settings(
            CACHES={"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
        ):
            doc = self._create_doc("Tai lieu khi cache hong")
            trie = search_index.get_trie(search_index.SCOPE_PUBLIC)
            self.assertIn(doc.pk, trie.search_prefix("tai lieu"))

    def test_incr_khong_mat_ttl_never_expire(self) -> None:
        """Regression MAJOR-1: DatabaseCache.incr của Django = get+set không
        truyền timeout → TTL về default 300s. invalidate() phải `touch(None)`
        khôi phục never-expire, nếu không counter chết sau 5 phút → mất
        invalidation đa worker (backend production mặc định là DatabaseCache)."""
        from django.core.cache import cache
        from django.db import connection

        from apps.documents import search_index

        search_index.invalidate()  # lần đầu: add với timeout=None
        search_index.invalidate()  # lần sau: incr (+touch None)
        search_index.invalidate()

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT expires FROM django_cache_table WHERE cache_key LIKE %s",
                ["%trie_version:documents%"],
            )
            row = cursor.fetchone()

        self.assertIsNotNone(row, "Counter dùng chung phải tồn tại trong cache DB")
        # datetime.max (9999-12-31) = never-expire; nếu incr làm mất TTL thì
        # expires sẽ là now + 300s (năm hiện tại)
        self.assertEqual(getattr(row[0], "year", None), 9999)


class PersistentStorageGuardTests(ThrottleFreeMixin, APITestCase):
    """
    QA-Audit đợt 2 (P2-3) — FAIL LOUD khi production lưu upload vào đĩa tạm:
        - production + FileSystemStorage → 400 kèm hướng dẫn S3.
        - production + ALLOW_EPHEMERAL_UPLOADS=1 → 201 (demo/pilot chấp nhận rủi ro).
        - production + MEDIA_STORAGE_PERSISTENT=True (S3) → 201.
        - development → không bao giờ chặn.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="storage-guard", email="guard@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010201",
        )
        MemberProfile.objects.create(user=cls.member, ho_ten="Guard Lưu Trữ")
        cls.upload_url = reverse("document_list")

    def _upload(self):
        self.client.force_authenticate(user=self.member)
        return self.client.post(
            self.upload_url,
            {"file": make_pdf_file("tai-lieu.pdf"), "tieu_de": "Tài liệu lưu trữ", "nhom": "CHUYEN_MON"},
            format="multipart",
        )

    def test_production_ephemeral_bi_chan_400(self) -> None:
        with override_settings(
            DJANGO_ENV="production", MEDIA_STORAGE_PERSISTENT=False, ALLOW_EPHEMERAL_UPLOADS=False
        ):
            resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("lưu trữ bền vững", resp.data["message"])
        self.assertFalse(Document.objects.filter(tieu_de="Tài liệu lưu trữ").exists())

    def test_production_allow_ephemeral_thi_201(self) -> None:
        with override_settings(
            DJANGO_ENV="production", MEDIA_STORAGE_PERSISTENT=False, ALLOW_EPHEMERAL_UPLOADS=True
        ):
            resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_production_co_s3_thi_201(self) -> None:
        with override_settings(
            DJANGO_ENV="production", MEDIA_STORAGE_PERSISTENT=True, ALLOW_EPHEMERAL_UPLOADS=False
        ):
            resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_development_khong_bao_gio_chan(self) -> None:
        with override_settings(
            DJANGO_ENV="development", MEDIA_STORAGE_PERSISTENT=False, ALLOW_EPHEMERAL_UPLOADS=False
        ):
            resp = self._upload()
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)


class DocumentSanitizationTests(ThrottleFreeMixin, APITestCase):
    """QA-Audit đợt 2 (P3): tieu_de/mo_ta tài liệu phải sạch tag HTML ở backend."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="sanitizer", email="sani@clbip.test", password="TestPass123!",
            role=User.Role.MEMBER, mssv="22A4010301",
        )
        MemberProfile.objects.create(user=cls.member, ho_ten="San Itizer")
        cls.upload_url = reverse("document_list")

    def test_tieu_de_mo_ta_bi_strip_script(self) -> None:
        self.client.force_authenticate(user=self.member)
        resp = self.client.post(
            self.upload_url,
            {
                "file": make_pdf_file("sach.pdf"),
                "tieu_de": "<script>hack()</script>Giao Trinh Python",
                "mo_ta": "<p>Giáo trình<script>bad()</script> cơ bản</p>",
                "nhom": "CHUYEN_MON",
            },
            format="multipart",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(pk=resp.data["data"]["id"])
        self.assertNotIn("<script>", doc.tieu_de)
        self.assertNotIn("<script>", doc.mo_ta)
        self.assertIn("Giao Trinh Python", doc.tieu_de)


class DocumentLegacyOfficeUploadTests(ThrottleFreeMixin, APITestCase):
    """QA-Audit đợt 3 — TASK 5 (P2): nhận .doc/.xls cho form chia sẻ tài liệu."""

    def setUp(self) -> None:
        self.member = User.objects.create_user(email="doc2@clb.vn", password="TestPass123!")
        MemberProfile.objects.create(user=self.member, ho_ten="Nguyễn Văn A")
        self.upload_url = "/api/v1/documents/"

    OLE_BYTES = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32

    def test_01_upload_doc_that_bien_201(self) -> None:
        """.doc thật (OLE2 magic) → 201, file_type='doc'."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile(
                "de-cuong.doc", self.OLE_BYTES, content_type="application/msword"
            ),
            "tieu_de": "Đề cương ôn tập (Word cổ)",
            "nhom": "CHUYEN_MON",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(tieu_de="Đề cương ôn tập (Word cổ)")
        self.assertEqual(doc.file_type, "doc")
        self.assertTrue(doc.file.name.endswith(".doc"))

    def test_02_upload_xls_that_bien_201(self) -> None:
        """.xls thật (OLE2 magic) → 201, file_type='xls'."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile(
                "bang-diem.xls", self.OLE_BYTES, content_type="application/vnd.ms-excel"
            ),
            "tieu_de": "Bảng điểm kỳ 2025-2026",
            "nhom": "NGHIEP_VU",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(tieu_de="Bảng điểm kỳ 2025-2026")
        self.assertEqual(doc.file_type, "xls")

    def test_03_exe_doi_duoi_doc_bi_tu_magic_bytes(self) -> None:
        """.exe đổi đuôi .doc → 400 (magic MZ không khớp OLE2)."""
        self.client.force_authenticate(user=self.member)
        payload = {
            "file": SimpleUploadedFile(
                "virus.doc", b"MZ\x90\x00binary-pe-payload", content_type="application/msword"
            ),
            "tieu_de": "Tệp giả mạo",
            "nhom": "CHUYEN_MON",
        }
        resp = self.client.post(self.upload_url, payload, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Nội dung tệp không khớp định dạng", resp.data["message"])
        self.assertEqual(Document.objects.count(), 0)
