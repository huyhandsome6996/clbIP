"""
Regression tests — audit 06/10/2026 (F05)
==========================================
F05: GET /documents/{id}/preview/ — stream inline phục vụ iframe xem trước:
     - Cùng phạm vi quyền với download (can_view — BCN_ONLY chặn member).
     - KHÔNG tăng luot_tai (khác download), không cộng XP.
     - Content-Disposition inline; anonymous 401.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.authentication.models import User
from apps.documents.models import Document
from apps.documents.tests import (
    PDF_BYTES,
    TEST_MEDIA_ROOT,
    ThrottleFreeMixin,
)


@TEST_MEDIA_ROOT
class DocumentPreviewTests(ThrottleFreeMixin, APITestCase):
    """F05 — preview qua API có kiểm soát thay vì fetch file trực tiếp."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.member = User.objects.create_user(
            username="member_prev", email="prev-member@clbip.test",
            password="TestPass123!", role=User.Role.MEMBER, mssv="22A4010009",
        )
        cls.bcn = User.objects.create_user(
            username="bcn_prev", email="prev-bcn@clbip.test",
            password="TestPass123!", role=User.Role.BCN,
        )
        cls.doc_public = Document.objects.create(
            tieu_de="Tài liệu preview công khai",
            nhom=Document.Nhom.NGHIEP_VU,
            file=SimpleUploadedFile("preview.pdf", PDF_BYTES, content_type="application/pdf"),
            file_type="pdf",
            file_size=len(PDF_BYTES),
            uploaded_by=cls.bcn,
        )
        cls.doc_bcn_only = Document.objects.create(
            tieu_de="Tài liệu preview BCN_ONLY",
            nhom=Document.Nhom.NGHIEP_VU,
            pham_vi=Document.PhamVi.BCN_ONLY,
            file=SimpleUploadedFile("bcn-only.pdf", PDF_BYTES, content_type="application/pdf"),
            file_type="pdf",
            file_size=len(PDF_BYTES),
            uploaded_by=cls.bcn,
        )

    def test_f05_preview_streams_inline_without_counter(self):
        """200 inline + luot_tai KHÔNG đổi sau preview."""
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("document_preview", kwargs={"pk": self.doc_public.pk}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(b"".join(resp.streaming_content), PDF_BYTES)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("inline", resp["Content-Disposition"])
        self.doc_public.refresh_from_db()
        self.assertEqual(self.doc_public.luot_tai, 0)

    def test_f05_bcn_only_hidden_from_member(self):
        """MEMBER không xem preview được tài liệu BCN_ONLY (404 — như download)."""
        self.client.force_authenticate(user=self.member)
        resp = self.client.get(reverse("document_preview", kwargs={"pk": self.doc_bcn_only.pk}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
        # BCN vẫn xem được
        self.client.force_authenticate(user=self.bcn)
        ok = self.client.get(reverse("document_preview", kwargs={"pk": self.doc_bcn_only.pk}))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)

    def test_f05_anonymous_401(self):
        resp = APIClient()
        res = resp.get(reverse("document_preview", kwargs={"pk": self.doc_public.pk}))
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_f05_preview_missing_file_404(self):
        self.client.force_authenticate(user=self.bcn)
        # Doc tồn tại trong DB nhưng file không còn trên đĩa
        doc = Document.objects.create(
            tieu_de="Mồ côi file",
            nhom=Document.Nhom.NGHIEP_VU,
            file="documents/khong-ton-tai.pdf",
            file_type="pdf",
            file_size=100,
            uploaded_by=self.bcn,
        )
        resp = self.client.get(reverse("document_preview", kwargs={"pk": doc.pk}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
