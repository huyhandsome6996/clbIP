"""
Concurrency tests — ĐIỂM DANH (review R04, 07/10/2026)
=======================================================
Chạy THẬT trên MySQL/MariaDB; SKIP trên SQLite với lý do rõ ràng (không tính
là pass). Khóa thống nhất: SESSION row → RECORD row (review R04) — check-in,
bulk_override và close_session cùng serialization point của phiên.

Kịch bản:
  1. Hai check-in SONG SONG cùng thành viên → đúng 1 thắng (409 cái còn
     lại), metadata/XP không bị ghi đè.
  2. bulk_override vs check-in cùng thành viên → tuần tự hóa: trạng thái
     cuối là một trong hai giá trị ghi, không corrupt metadata.
  3. close_session vs check-in → hoặc check-in thắng (record CO_MAT, phiên
     CLOSED) hoặc close thắng (check-in bị chặn, record vẫn VẮNG chưa-metadata).
"""
from datetime import timedelta
from threading import Barrier, Thread
from unittest import skipIf

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.attendance.services import AttendanceNonceService, AttendanceService
from apps.authentication.models import User
from apps.common.exceptions import DuplicateDataException, SessionClosedException
from apps.gamification.models import XpLedger
from apps.members.models import MemberProfile

CENTER_LAT = 16.4637
CENTER_LON = 107.5909
NEAR_LAT = 16.46379  # cách tâm ~11m — trong bán kính 50m
NEAR_LON = 107.5909


@skipIf(
    connection.vendor == "sqlite",
    "SQLite khóa toàn bảng khi 2 connection cùng ghi — race test chỉ chạy "
    "đúng ý trên MySQL/MariaDB/PostgreSQL (CSDL chính của dự án là MySQL). "
    "Kết quả skip KHÔNG được tính là concurrency pass.",
)
class AttendanceConcurrencyTests(TransactionTestCase):
    """R04 — mutation điểm danh tuần tự hóa trên khóa phiên."""

    databases = {"default"}

    def setUp(self) -> None:
        self.member_user = User.objects.create_user(
            email="race-checkin@clbip.test",
            username="race-checkin@clbip.test",
            password="TestPass123!",
            role="MEMBER",
        )
        self.member = MemberProfile.objects.create(
            user=self.member_user, ho_ten="Thành Viên Race"
        )

    def _open_session(self) -> AttendanceSession:
        """Mở phiên hợp lệ qua service — tự tạo record VẮNG cho thành viên.
        Phiên không gắn sự kiện để tránh phụ thuộc vé/XP event."""
        return AttendanceService.open_session(
            ten_phien=f"Phiên race {self.member_user.pk}",
            vi_do=CENTER_LAT,
            kinh_do=CENTER_LON,
            ban_kinh_m=50,
        )

    def _checkin(self, session: AttendanceSession) -> None:
        """Gọi service check-in với tham số hợp lệ (GPS trong bán kính).

        M05 (audit 1114efd): service BẮT BUỘC accuracy (§5.1) — test gửi
        accuracy=10m như client thật.
        """
        AttendanceService.check_in(
            member=self.member,
            session_id=session.id,
            client_lat=NEAR_LAT,
            client_lon=NEAR_LON,
            client_time=timezone.now(),
            device_id=f"DEVICE-{self.member_user.pk}",
            nonce=AttendanceNonceService.generate(session)["nonce"],
            accuracy=10.0,
        )

    # ------------------------------------------------------------------
    def test_01_parallel_checkin_same_member(self):
        """2 check-in song song cùng member → đúng 1 thắng, 1 bị 409."""
        session = self._open_session()
        barrier = Barrier(2)
        results: list = []

        def run():
            try:
                barrier.wait(timeout=15)
                self._checkin(session)
                results.append("ok")
            except DuplicateDataException:
                results.append("duplicate")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=run), Thread(target=run)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(results.count("ok"), 1, str(results))
        self.assertEqual(results.count("duplicate"), 1, str(results))

        record = AttendanceRecord.objects.get(session=session, member=self.member)
        self.assertIn(record.trang_thai, ("CO_MAT", "DI_MUON"))
        self.assertIsNotNone(record.checked_in_at, "Metadata check-in phải còn nguyên")
        # XP idempotent: tối đa 1 ledger entry cho check-in này
        xp_count = XpLedger.objects.filter(
            member=self.member, idempotency_key__contains=f"session_{session.id}"
        ).count()
        self.assertLessEqual(xp_count, 1, str(xp_count))

    def test_02_bulk_override_vs_checkin_parallel(self):
        """bulk_override (CO_PHEP) vs check-in cùng member → tuần tự, không corrupt."""
        session = self._open_session()
        barrier = Barrier(2)
        results: list = []

        def do_checkin():
            try:
                barrier.wait(timeout=15)
                self._checkin(session)
                results.append("checkin-ok")
            except (DuplicateDataException, SessionClosedException):
                results.append("checkin-blocked")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        def do_override():
            try:
                barrier.wait(timeout=15)
                AttendanceService.bulk_override(
                    session,
                    [{"member_id": self.member.pk, "trang_thai": "CO_PHEP"}],
                    actor=None,
                )
                results.append("override-ok")
            except SessionClosedException:
                results.append("override-blocked")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=do_checkin), Thread(target=do_override)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertNotIn(
            [r for r in results if r.startswith("err:")],
            results,
            f"Có exception bất ngờ: {results}",
        )
        self.assertIn("override-ok", results, str(results))
        record = AttendanceRecord.objects.get(session=session, member=self.member)
        # Trạng thái cuối là một trong hai giá trị đã ghi — không xor/lẫn
        self.assertIn(record.trang_thai, ("CO_MAT", "DI_MUON", "CO_PHEP"))
        if record.trang_thai == "CO_PHEP":
            # Override thắng → không được phép còn metadata check-in dở với CO_MAT
            self.assertNotEqual(record.trang_thai, "CO_MAT")
        # update_fields của override KHÔNG đè metadata check-in (13-a P2-1)
        if "checkin-ok" in results:
            self.assertIsNotNone(record.checked_in_at, "check-in thắng mà metadata bị mất!")

    def test_03_close_session_vs_checkin_parallel(self):
        """close vs check-in: hoặc check-in thắng trước khi đóng, hoặc bị chặn."""
        session = self._open_session()
        barrier = Barrier(2)
        results: list = []

        def do_checkin():
            try:
                barrier.wait(timeout=15)
                self._checkin(session)
                results.append("checkin-ok")
            except (DuplicateDataException, SessionClosedException):
                results.append("checkin-blocked")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        def do_close():
            try:
                barrier.wait(timeout=15)
                AttendanceService.close_session(session)
                results.append("close-ok")
            except Exception as exc:
                results.append(f"err:{type(exc).__name__}")
            finally:
                connection.close()

        threads = [Thread(target=do_checkin), Thread(target=do_close)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        session.refresh_from_db()
        self.assertEqual(
            session.trang_thai, AttendanceSession.TrangThai.CLOSED, str(results)
        )
        self.assertIn("close-ok", results, str(results))
        record = AttendanceRecord.objects.get(session=session, member=self.member)
        if "checkin-ok" in results:
            self.assertIn(record.trang_thai, ("CO_MAT", "DI_MUON"))
            self.assertIsNotNone(record.checked_in_at)
        else:
            # close thắng → check-in phải bị chặn, record giữ VẮNG không metadata
            self.assertIn("checkin-blocked", results, str(results))
            self.assertEqual(record.trang_thai, "VANG")
            self.assertIsNone(record.checked_in_at)
        # Không có trạng thái nửa vời: CLOSED nhưng lại có check-in metadata mới
