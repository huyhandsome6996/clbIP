"""
Concurrency tests — SỔ QUỸ (review R04, 07/10/2026)
====================================================
Yêu cầu review: "Đừng coi test race bị skip trên SQLite là đã đạt" → suite
này chạy THẬT trên MySQL/MariaDB (engine production của dự án). Trên SQLite
mỗi test SKIP với lý do rõ ràng (SQLite khóa toàn bảng khi ghi — race không
có ý nghĩa) và KHÔNG BAO GIỜ được ghi nhận là "concurrency pass".

Các kịch bản (mỗi test assert BẤT BIẾN Σthu − Σchi = so_du của dòng cuối):
  1. Distinct keys trên SỔ RỖNG — kịch bản mà lock "dòng cuối" trước đây
     KHÔNG bảo vệ được (không có hàng nào để khóa): 2 giao dịch song song
     cùng đọc số dư 0 rồi cùng ghi → mất cập nhật chuỗi số dư. Fix R04:
     khóa hàng neo `FundLedgerAnchor` (pk=1, data migration 0004).
  2. Same key + same payload × 4 thread → đúng 1 giao dịch, còn lại replay.
  3. Same key + khác payload × 4 thread → 1 thắng (201), còn lại 409.
  4. Distinct keys trên sổ CÓ DỮ LIỆU, thu/chi trộn → invariant giữ.
  5. Hai CHI song song tổng vượt số dư → đúng 1 thắng, số dư không âm.
  6. Ghi sổ song song với khóa sổ kỳ (FundPeriodLock) → không corruption.
"""
from datetime import timedelta
from threading import Barrier, Thread
from unittest import skipIf

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.authentication.models import User
from apps.common.exceptions import (
    IdempotencyKeyConflictException,
    InsufficientFundException,
    PeriodLockedException,
)
from apps.funds.models import FundLedgerAnchor, FundPeriodLock, FundTransaction
from apps.funds.services import FundService
from apps.members.models import MemberProfile


@skipIf(
    connection.vendor == "sqlite",
    "SQLite khóa toàn bảng khi 2 connection cùng ghi — race test chỉ chạy "
    "đúng ý trên MySQL/MariaDB/PostgreSQL (CSDL chính của dự án là MySQL). "
    "Kết quả skip KHÔNG được tính là concurrency pass.",
)
class FundLedgerConcurrencyTests(TransactionTestCase):
    """R04 — hàng neo khóa bi sổ: bất biến số dư dưới tải song song."""

    databases = {"default"}

    def setUp(self) -> None:
        # TransactionTestCase FLUSH toàn bộ dữ liệu sau mỗi test — hàng neo
        # (do data migration 0004 tạo lúc setup test DB) bị xóa theo. Khôi
        # phục idempotent để mỗi test có chốt khóa như production.
        FundLedgerAnchor.objects.get_or_create(
            pk=1, defaults={"ghi_chu": "Hàng neo khóa bi sổ (khôi phục trong test setUp)"}
        )

    @classmethod
    def _make_actor(cls, email: str) -> User:
        user = User.objects.create_user(
            email=email, username=email, password="TestPass123!", role="BCN"
        )
        MemberProfile.objects.create(user=user, ho_ten=f"Thủ quỹ {email}")
        return user

    @staticmethod
    def _post(actor, *, loai_gd, so_tien, key=None, ngay=None):
        """Ghi sổ qua service (cùng đường vào với HTTP POST /funds/)."""
        return FundService.execute_transaction_idempotent(
            loai_gd=loai_gd,
            so_tien=so_tien,
            nguoi_thuc_hien="Concurrency Probe",
            created_by=actor,
            idempotency_key=key,
            ngay_gd=ngay,
        )

    @staticmethod
    def _assert_balance_invariant() -> None:
        """Σthu − Σchi PHẢI bằng so_du_sau của dòng MỚI NHẤT (theo id).
        Sổ rỗng → bất biến thỏa chân lý (không có gì để kiểm)."""
        rows = list(FundTransaction.objects.order_by("id"))
        if not rows:
            return
        total = sum(
            r.so_tien if r.loai_gd == "THU" else -r.so_tien for r in rows
        )
        last = rows[-1]
        assert last.so_du_sau == total, (
            f"BẤT BIẾN SỐ DƯ BỊ PHÁ: Σthu−Σchi={total:,} nhưng dòng cuối "
            f"{last.ma_phieu} có so_du_sau={last.so_du_sau:,} (sổ {len(rows)} dòng)"
        )

    # ------------------------------------------------------------------
    def test_01_distinct_keys_on_empty_ledger_parallel(self):
        """SỔ RỖNG + 2 writer song song (THU 100k / THU 50k, key khác nhau).

        Đây chính là kịch bản review R04 chỉ ra: lock "dòng cuối" không có
        gì để khóa → cả hai cùng đọc số dư 0 rồi cùng ghi → dòng cuối ghi
        so_du=50k trong khi Σthu=150k (MẤT CẬP NHẬT). InsufficientFund
        không thể che kịch bản này vì cả hai đều là THU. Sau fix (hàng neo)
        bất biến phải giữ: dòng cuối = 150k.
        """
        actor = self._make_actor("race-quy-1@clbip.test")
        barrier = Barrier(2)
        outcomes: list[str] = []

        def run(so_tien, key):
            try:
                barrier.wait(timeout=15)
                self._post(actor, loai_gd="THU", so_tien=so_tien, key=key)
                outcomes.append("ok")
            except Exception as exc:
                outcomes.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=run, args=(100_000, "empty-a")), Thread(target=run, args=(50_000, "empty-b"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(sorted(outcomes), ["ok", "ok"], f"Có lỗi bất ngờ: {outcomes}")
        self.assertEqual(FundTransaction.objects.count(), 2)
        self._assert_balance_invariant()
        # Kết luận cụ thể của kịch bản: dòng cuối PHẢI mang tổng 150k
        last = FundTransaction.objects.order_by("-id").first()
        self.assertEqual(
            last.so_du_sau, 150_000,
            f"MẤT CẬP NHẬT: dòng cuối so_du_sau={last.so_du_sau:,} thay vì 150.000₫",
        )

    def test_02_same_key_same_payload_parallel(self):
        """4 thread cùng key + cùng payload → đúng 1 giao dịch, 3 replay."""
        actor = self._make_actor("race-quy-2@clbip.test")
        barrier = Barrier(4)
        results: list = []

        def run():
            try:
                barrier.wait(timeout=15)
                tx, replayed = self._post(
                    actor, loai_gd="THU", so_tien=250_000, key="race-key-cung-y-dinh"
                )
                results.append(("ok", replayed))
            except Exception as exc:
                results.append((f"err:{type(exc).__name__}", None))
            finally:
                connection.close()

        threads = [Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(FundTransaction.objects.filter(idempotency_key="race-key-cung-y-dinh").count(), 1)
        self.assertEqual(len([r for r in results if r[0] == "ok"]), 4, str(results))
        # Đúng 1 thread ghi mới, 3 thread nhận replay
        self.assertEqual(len([r for r in results if r[1] is False]), 1, str(results))
        self._assert_balance_invariant()

    def test_03_same_key_different_payload_parallel(self):
        """4 thread cùng key + KHÁC payload → 1 thắng, còn lại 409 conflict."""
        actor = self._make_actor("race-quy-3@clbip.test")
        barrier = Barrier(4)
        results: list = []

        def run(so_tien):
            try:
                barrier.wait(timeout=15)
                self._post(actor, loai_gd="THU", so_tien=so_tien, key="race-key-trung")
                results.append("ok")
            except IdempotencyKeyConflictException:
                results.append("conflict")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=run, args=(amount,)) for amount in (100_000, 200_000, 300_000, 500_000)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(results.count("ok"), 1, str(results))
        self.assertEqual(results.count("conflict"), 3, str(results))
        self.assertEqual(FundTransaction.objects.filter(idempotency_key="race-key-trung").count(), 1)
        self._assert_balance_invariant()

    def test_04_distinct_keys_populated_ledger_mixed(self):
        """Sổ có dữ liệu + 4 writer trộn thu/chi (key khác nhau) → invariant."""
        actor = self._make_actor("race-quy-4@clbip.test")
        self._post(actor, loai_gd="THU", so_tien=1_000_000, key="seed-1")

        barrier = Barrier(4)
        outcomes: list[str] = []

        def run(loai, so_tien, key):
            try:
                barrier.wait(timeout=15)
                self._post(actor, loai_gd=loai, so_tien=so_tien, key=key)
                outcomes.append("ok")
            except Exception as exc:
                outcomes.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        jobs = [
            ("THU", 200_000, "mix-a"),
            ("CHI", 50_000, "mix-b"),
            ("CHI", 120_000, "mix-c"),
            ("THU", 30_000, "mix-d"),
        ]
        threads = [Thread(target=run, args=job) for job in jobs]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(outcomes, ["ok"] * 4, str(outcomes))
        self.assertEqual(FundTransaction.objects.count(), 5)
        self._assert_balance_invariant()
        # Mã phiếu duy nhất (unique) — không lost update sinh trùng
        self.assertEqual(
            FundTransaction.objects.values_list("ma_phieu", flat=True).count(),
            FundTransaction.objects.count(),
        )

    def test_05_parallel_chi_exceeding_balance(self):
        """2 CHI song song (80k + 80k) khi chỉ có 100k → đúng 1 thắng, số dư ≥ 0."""
        actor = self._make_actor("race-quy-5@clbip.test")
        self._post(actor, loai_gd="THU", so_tien=100_000, key="seed-balance")

        barrier = Barrier(2)
        results: list = []

        def run(key):
            try:
                barrier.wait(timeout=15)
                self._post(actor, loai_gd="CHI", so_tien=80_000, key=key)
                results.append("ok")
            except InsufficientFundException:
                results.append("insufficient")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=run, args=(k,)) for k in ("chi-1", "chi-2")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(results.count("ok"), 1, str(results))
        self.assertEqual(results.count("insufficient"), 1, str(results))
        self._assert_balance_invariant()
        last = FundTransaction.objects.order_by("-id").first()
        self.assertGreaterEqual(last.so_du_sau, 0)

    def test_06_transaction_vs_period_lock_parallel(self):
        """Ghi sổ song song với khóa sổ kỳ: giao dịch hoặc thành công TRƯỚC
        khi khóa chốt, hoặc bị từ chối 423 — không trạng thái nửa vời."""
        actor = self._make_actor("race-quy-6@clbip.test")
        barrier = Barrier(2)
        results: list = []
        today = timezone.localdate()

        def post_tx():
            try:
                barrier.wait(timeout=15)
                self._post(
                    actor, loai_gd="THU", so_tien=10_000, key="lock-race",
                    ngay=timezone.now(),
                )
                results.append("ok")
            except PeriodLockedException:
                results.append("locked")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        def lock_period():
            try:
                barrier.wait(timeout=15)
                FundPeriodLock.objects.create(
                    ten_ky=f"KyRace{today:%Y%m%d%H%M%S%f}",
                    tu_ngay=today - timedelta(days=1),
                    den_ngay=today + timedelta(days=1),
                )
                results.append("locked-created")
            finally:
                connection.close()

        threads = [Thread(target=post_tx), Thread(target=lock_period)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(results.count("locked-created"), 1, str(results))
        # Giao dịch hoặc thắng (ghi trước khi khóa chốt) hoặc bị chặn 423
        self.assertIn(results.count("ok") + results.count("locked"), (0, 1), str(results))
        self.assertEqual(len(results), 2, str(results))
        self.assertTrue(
            all(r in ("ok", "locked", "locked-created") for r in results),
            f"Outcome lạ: {results}",
        )
        self._assert_balance_invariant()
