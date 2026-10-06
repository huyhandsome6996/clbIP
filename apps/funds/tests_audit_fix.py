"""
Regression tests — audit 06/10/2026 (F02)
==========================================
F02: Idempotency-Key dùng lại với payload KHÁC phải bị chặn 409 conflict —
     tuyệt đối không replay thành công giao dịch ngoài ý định, không ghi thêm.
     Cùng key + cùng nội dung (kể cả bản ghi legacy không có vân tay) → replay
     200 đúng bản ghi cũ.
"""
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.authentication.models import User
from apps.funds.models import FundTransaction
from apps.members.models import MemberProfile


@override_settings(AXES_ENABLED=False)
class FundIdempotencyConflictTests(APITestCase):
    """F02 — cùng key khác nội dung → 409; cùng key cùng nội dung → replay."""

    def setUp(self) -> None:
        cache.clear()
        self.bcn = User.objects.create_user(
            email="idem-audit@clbip.test", password="TestPass123!", role="BCN",
        )
        MemberProfile.objects.create(user=self.bcn, ho_ten="Thủ Quỹ Audit")
        self.bcn2 = User.objects.create_user(
            email="idem-audit2@clbip.test", password="TestPass123!", role="BCN",
        )
        MemberProfile.objects.create(user=self.bcn2, ho_ten="Thủ Quỹ Audit Hai")
        self.client.force_authenticate(user=self.bcn)
        self.url = reverse("fund_list")
        self.payload = {
            "loai_gd": "THU",
            "so_tien": 500_000,
            "nguoi_thuc_hien": "Nhà tài trợ XYZ",
            "hinh_thuc": "CHUYEN_KHOAN",
        }

    def test_f02_same_key_different_payload_conflict_409(self):
        """THU 500k key K → 201; THU 900k key K → 409, DB vẫn chỉ 500k."""
        res1 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-K",
        )
        self.assertEqual(res1.status_code, 201, res1.data)

        res2 = self.client.post(
            self.url,
            {**self.payload, "so_tien": 900_000},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-K",
        )
        self.assertEqual(res2.status_code, 409, res2.data)
        self.assertEqual(res2.data["success"], False)
        # DB chỉ còn đúng 1 giao dịch 500.000
        self.assertEqual(FundTransaction.objects.count(), 1)
        self.assertEqual(FundTransaction.objects.first().so_tien, 500_000)

    def test_f02_same_key_same_payload_replay_200(self):
        """Retry NGUYÊN yêu cầu (không có ngay_gd) → 200 đúng phiếu cũ."""
        res1 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-R",
        )
        self.assertEqual(res1.status_code, 201)
        res2 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-R",
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res1.data["data"]["ma_phieu"], res2.data["data"]["ma_phieu"])
        self.assertEqual(FundTransaction.objects.count(), 1)

    def test_f02_same_key_different_actor_conflict(self):
        """Key do BCN A dùng — BCN B gửi payload giống hệt với key đó → 409."""
        res1 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-actor",
        )
        self.assertEqual(res1.status_code, 201)
        self.client.force_authenticate(user=self.bcn2)
        res2 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-actor",
        )
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(FundTransaction.objects.count(), 1)

    def test_f02_client_ngay_gd_same_replay_different_conflict(self):
        """ngay_gd client gửi: giống → replay; khác (ý định khác) → 409."""
        p = {**self.payload, "ngay_gd": "2026-10-01T09:00:00Z"}
        res1 = self.client.post(self.url, p, format="json", HTTP_IDEMPOTENCY_KEY="key-date")
        self.assertEqual(res1.status_code, 201)

        res_same = self.client.post(self.url, p, format="json", HTTP_IDEMPOTENCY_KEY="key-date")
        self.assertEqual(res_same.status_code, 200)

        res_diff = self.client.post(
            self.url,
            {**self.payload, "ngay_gd": "2026-10-02T09:00:00Z"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-date",
        )
        self.assertEqual(res_diff.status_code, 409)
        self.assertEqual(FundTransaction.objects.count(), 1)

    def test_f02_ghi_chu_khac_conflict(self):
        """Cùng key, chỉ khác ghi chú → 409 (ý định khác)."""
        res1 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-note",
        )
        self.assertEqual(res1.status_code, 201)
        res2 = self.client.post(
            self.url,
            {**self.payload, "ghi_chu": "Hội phí đợt 2"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-note",
        )
        self.assertEqual(res2.status_code, 409)

    def test_f02_legacy_row_same_fields_replay_different_fields_conflict(self):
        """
        Bản ghi LEGACY (fingerprint NULL — ghi trước khi có field):
        - Cùng trường nghiệp vụ lưu trong DB → replay an toàn.
        - Khác trường nghiệp vụ → 409.
        """
        res1 = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-legacy",
        )
        self.assertEqual(res1.status_code, 201)
        # Mô phỏng bản ghi cũ: xóa vân tay
        FundTransaction.objects.update(request_fingerprint=None)
        ma_phieu_legacy = res1.data["data"]["ma_phieu"]

        # Retry nguyên payload → vẫn replay (đối chiếu theo trường lưu trong DB)
        res_same = self.client.post(
            self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-legacy",
        )
        self.assertEqual(res_same.status_code, 200)
        self.assertEqual(res_same.data["data"]["ma_phieu"], ma_phieu_legacy)

        # Payload khác → 409 (legacy không có vân tay nhưng trường DB không khớp)
        res_diff = self.client.post(
            self.url,
            {**self.payload, "so_tien": 1_000_000},
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-legacy",
        )
        self.assertEqual(res_diff.status_code, 409)
        self.assertEqual(FundTransaction.objects.count(), 1)

    def test_f02_new_transactions_store_fingerprint(self):
        """Giao dịch (có hoặc không có key) đều lưu vân tay — phục vụ truy vết."""
        self.client.post(self.url, self.payload, format="json", HTTP_IDEMPOTENCY_KEY="key-fp")
        with_fp = FundTransaction.objects.get(idempotency_key="key-fp")
        self.assertTrue(with_fp.request_fingerprint)
        self.assertEqual(len(with_fp.request_fingerprint), 64)  # sha256 hex

        self.client.post(self.url, self.payload, format="json")
        without_key = FundTransaction.objects.get(idempotency_key__isnull=True)
        self.assertTrue(without_key.request_fingerprint)
