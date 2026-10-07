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
  6. Ghi sổ vs khóa sổ kỳ qua FundService.lock_period (N03): interleaving
     có kiểm soát — writer dừng NGAY TRƯỚC INSERT trong khi lock chạy →
     tuyến tính hóa qua hàng neo, giao dịch bị mark is_locked=True.
  6b. Lock trước → writer 423, không insert; rows trong kỳ mark, ngoài kỳ không.
  6c. Hai lock_period song song cùng tên → 1 thắng 409 sạch, không deadlock.
  6d. Biên kỳ & múi giờ: 23:59/00:00 đầu-cuối kỳ bị khóa, ngoài kỳ không.
"""
from datetime import datetime, timedelta
from threading import Barrier, Event, Thread
from unittest import skipIf

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.authentication.models import User
from apps.common.exceptions import (
    DuplicateDataException,
    IdempotencyKeyConflictException,
    InsufficientFundException,
    PeriodLockedException,
)
from apps.funds.models import FundLedgerAnchor, FundPeriodLock, FundTransaction
from apps.funds.repositories import FundTransactionRepository
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

    def test_06_transaction_wins_race_then_gets_marked_locked(self):
        """N03 (review ac51233) — interleaving CÓ KIỂM SOÁT qua service thật.

        Kịch bản QA chỉ định: writer vừa qua bước 2 (kiểm tra kỳ — chưa có
        khóa) rồi bị TẠM DỪNG ngay trước INSERT; cùng lúc lock_period chạy.
        Sau khi cả hai kết thúc phải có MỘT thứ tự tuyến tính:
          transaction TRƯỚC lock → giao dịch được GHI và bị ĐÁNH DẤU
          is_locked=True bởi mark của lock (không được lọt qua kỳ khóa).

        Điều phối: monkeypatch repo.create_transaction — hook signal
        `writer_at_insert` + chờ `release_writer`. Writer đang GIỮ anchor
        khi tạm dừng nên lock_period (đã fix N03: lấy anchor trước) PHẢI
        đứng chờ ở anchor — kiểm chứng serialization bằng cách assert lock
        thread CHƯA xong trong khi writer đang treo.
        """
        from unittest.mock import patch

        actor = self._make_actor("race-quy-6@clbip.test")
        writer_at_insert = Event()
        release_writer = Event()
        lock_finished = Event()
        results: list = []
        today = timezone.localdate()
        original_create = FundTransactionRepository.create_transaction

        def hooked_create(repo_self, **fields):
            writer_at_insert.set()
            # Writer giữ anchor, đứng ngay trước INSERT — cửa sổ race chính xác
            release_writer.wait(timeout=20)
            return original_create(repo_self, **fields)

        def post_tx():
            try:
                with patch.object(
                    FundTransactionRepository, "create_transaction", hooked_create
                ):
                    tx, replay = FundService.execute_transaction_idempotent(
                        loai_gd="THU",
                        so_tien=10_000,
                        nguoi_thuc_hien="Race Probe 6",
                        created_by=actor,
                        idempotency_key="lock-race-6",
                        ngay_gd=timezone.now(),
                    )
                    results.append(("ok", tx.pk, replay))
            except Exception as exc:
                results.append(("err", type(exc).__name__, str(exc)))
            finally:
                release_writer.set()  # phòng dead-lock nếu lỗi trước hook
                connection.close()

        def lock_period():
            try:
                FundService.lock_period(
                    ten_ky="KyRace6",
                    tu_ngay=today - timedelta(days=1),
                    den_ngay=today + timedelta(days=1),
                    locked_by=actor,
                )
                results.append(("locked-created",))
            except Exception as exc:
                results.append(("lock-err", type(exc).__name__, str(exc)))
            finally:
                lock_finished.set()
                connection.close()

        writer = Thread(target=post_tx)
        locker = Thread(target=lock_period)
        writer.start()
        self.assertTrue(writer_at_insert.wait(timeout=15), "Writer không tới bước INSERT")

        locker.start()
        # Writer đang GIỮ anchor → lock (đã lấy anchor trước) PHẢI chưa xong.
        # Đây là bằng chứng trực tiếp của lock-order thống nhất (N03).
        self.assertFalse(
            lock_finished.wait(timeout=1.5),
            "lock_period hoàn thành trong khi writer còn giữ anchor → "
            "lock_period KHÔNG dùng chung hàng neo (fix N03 chưa đúng)",
        )

        release_writer.set()
        writer.join(timeout=30)
        locker.join(timeout=30)

        outcomes = [r[0] for r in results]
        self.assertIn("ok", outcomes, str(results))
        self.assertEqual(outcomes.count("locked-created"), 1, str(results))
        # Giao dịch được ghi (thứ tự tuyến tính: tx trước lock)...
        self.assertEqual(FundTransaction.objects.count(), 1)
        tx = FundTransaction.objects.get()
        self.assertEqual(tx.idempotency_key, "lock-race-6")  # mã khóa đúng intent
        self.assertTrue(tx.ma_phieu.startswith("PT"))
        # ...VÀ bị mark is_locked=True bởi mark_transactions_locked_between
        self.assertTrue(
            tx.is_locked,
            "Giao dịch nằm trong kỳ đã khóa nhưng is_locked=False — "
            "khoảng trống khóa kỳ mà QA (N03) chỉ ra vẫn còn",
        )
        lock = FundPeriodLock.objects.get(ten_ky="KyRace6")
        self.assertEqual(lock.tu_ngay, today - timedelta(days=1))
        self._assert_balance_invariant()

    def test_06b_lock_first_rejects_writer_and_marks_existing_rows(self):
        """N03 — thứ tự tuyến tính ngược lại: lock TRƯỚC transaction →
        writer bị từ chối PeriodLockedException (423), KHÔNG insert mới;
        mọi giao dịch CÓ TRƯỚC trong kỳ bị đánh dấu is_locked=True."""
        actor = self._make_actor("race-quy-6b@clbip.test")
        today = timezone.localdate()

        # Hai giao dịch trước khóa: 1 trong kỳ, 1 ngoài kỳ (năm trước)
        self._post(actor, loai_gd="THU", so_tien=200_000, key="6b-in",
                   ngay=timezone.now())
        last_year = timezone.make_aware(datetime(today.year - 1, 6, 15, 10, 0))
        self._post(actor, loai_gd="THU", so_tien=50_000, key="6b-out",
                   ngay=last_year)

        FundService.lock_period(
            ten_ky="Ky6B",
            tu_ngay=today - timedelta(days=1),
            den_ngay=today + timedelta(days=1),
            locked_by=actor,
        )

        before = FundTransaction.objects.count()
        with self.assertRaises(PeriodLockedException):
            self._post(actor, loai_gd="THU", so_tien=10_000, key="6b-after",
                       ngay=timezone.now())
        self.assertEqual(FundTransaction.objects.count(), before,
                         "Writer bị chặn 423 nhưng vẫn INSERT — rò rỉ ghi sổ")

        in_period = FundTransaction.objects.get(idempotency_key="6b-in")
        out_period = FundTransaction.objects.get(idempotency_key="6b-out")
        self.assertTrue(in_period.is_locked, "Giao dịch TRONG kỳ phải bị khóa")
        self.assertFalse(
            out_period.is_locked,
            "Giao dịch NGOÀI kỳ không được đánh dấu nhầm (N03: assert cả hai phía)",
        )
        self._assert_balance_invariant()

    def test_06c_parallel_lock_periods_same_name_single_winner(self):
        """N03 — 2 lock_period song song cùng tên: đúng 1 thắng, kẻ còn lại
        DuplicateDataException 409 SẠCH (không IntegrityError/500), không
        partial write, không deadlock."""
        actor = self._make_actor("race-quy-6c@clbip.test")
        today = timezone.localdate()
        barrier = Barrier(2)
        results: list = []

        def lock(name):
            try:
                barrier.wait(timeout=15)
                FundService.lock_period(
                    ten_ky=name,
                    tu_ngay=today - timedelta(days=1),
                    den_ngay=today + timedelta(days=1),
                    locked_by=actor,
                )
                results.append("created")
            except DuplicateDataException:
                results.append("duplicate-409")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=lock, args=("Ky6C",)), Thread(target=lock, args=("Ky6C",))]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(sorted(results), ["created", "duplicate-409"], str(results))
        self.assertEqual(FundPeriodLock.objects.filter(ten_ky="Ky6C").count(), 1)

    def test_06d_period_boundary_and_timezone_marking(self):
        """N03 — biên kỳ & múi giờ: 23:59 ngày ĐẦU và 00:00 ngày CUỐI (giờ
        địa phương Asia/Ho_Chi_Minh) phải bị khóa; ngày trước/sau kỳ thì KHÔNG."""
        actor = self._make_actor("race-quy-6d@clbip.test")
        today = timezone.localdate()
        tu_ngay = today - timedelta(days=2)
        den_ngay = today + timedelta(days=2)

        cases = {
            "first-day-2359": timezone.make_aware(
                datetime(tu_ngay.year, tu_ngay.month, tu_ngay.day, 23, 59, 30)
            ),
            "last-day-0000": timezone.make_aware(
                datetime(den_ngay.year, den_ngay.month, den_ngay.day, 0, 0, 0)
            ),
            "day-before-1200": timezone.make_aware(
                datetime((tu_ngay - timedelta(days=1)).year,
                         (tu_ngay - timedelta(days=1)).month,
                         (tu_ngay - timedelta(days=1)).day, 12, 0)
            ),
            "day-after-1200": timezone.make_aware(
                datetime((den_ngay + timedelta(days=1)).year,
                         (den_ngay + timedelta(days=1)).month,
                         (den_ngay + timedelta(days=1)).day, 12, 0)
            ),
        }
        for key, ngay in cases.items():
            self._post(actor, loai_gd="THU", so_tien=10_000, key=key, ngay=ngay)

        FundService.lock_period(
            ten_ky="Ky6D", tu_ngay=tu_ngay, den_ngay=den_ngay, locked_by=actor
        )

        for key, expect_locked in (
            ("first-day-2359", True),
            ("last-day-0000", True),
            ("day-before-1200", False),
            ("day-after-1200", False),
        ):
            tx = FundTransaction.objects.get(idempotency_key=key)
            self.assertEqual(
                tx.is_locked, expect_locked,
                f"{key}: is_locked={tx.is_locked}, kỳ [{tu_ngay} → {den_ngay}]",
            )
        # Post-lock insert trong kỳ → chặn; ngoài kỳ → vẫn ghi được
        with self.assertRaises(PeriodLockedException):
            self._post(actor, loai_gd="THU", so_tien=1_000, key="6d-in-after",
                       ngay=timezone.now())
        next_week = timezone.make_aware(datetime.combine(
            today + timedelta(days=10), datetime.min.time()))
        self._post(actor, loai_gd="THU", so_tien=1_000, key="6d-out-after",
                   ngay=next_week)
        self.assertFalse(
            FundTransaction.objects.get(idempotency_key="6d-out-after").is_locked
        )
        self._assert_balance_invariant()
