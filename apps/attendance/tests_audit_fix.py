"""
Regression tests — audit 06/10/2026 (F01, F07, F10)
====================================================
F01: bulk_override phải ATOMIC — validate toàn bộ trước khi ghi, mọi lỗi
     giữa chừng rollback toàn bộ (không lưu một phần dù API báo thất bại).
F07: check-in muộn (DI_MUON) gửi lại phải bị chặn 409 — không sửa metadata/XP.
F10: GET /attendance/sessions/{id}/records/ — BCN xem bảng bản ghi theo phiên
     (RBAC: MEMBER bị chặn; phân trang + lọc trạng thái).
"""
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.attendance.services import AttendanceNonceService, AttendanceService
from apps.attendance.tests import ATT_URL, AttendanceTestBase, CENTER_LAT, CENTER_LON, NEAR_LAT, NEAR_LON


@override_settings(AXES_ENABLED=False)
class BulkOverrideAtomicTests(AttendanceTestBase):
    """F01 — override hàng loạt phải all-or-nothing."""

    def _override(self, session, items, user=None):
        self.client.force_authenticate(user or self.bcn)
        return self.client.put(
            f"{ATT_URL}sessions/{session.id}/bulk-override/", {"items": items}, format="json"
        )

    def test_f01_error_on_last_item_rolls_back_everything(self):
        """Item cuối sai (member không tồn tại) → 400 và item đầu KHÔNG bị đổi."""
        session = self.make_session()
        member_a_id = self.profile_a.pk
        res = self._override(
            session,
            [
                {"member_id": member_a_id, "trang_thai": "CO_PHEP"},
                {"member_id": 999999, "trang_thai": "CO_MAT"},
            ],
        )
        self.assertEqual(res.status_code, 400)
        record = AttendanceRecord.objects.get(session=session, member_id=member_a_id)
        self.assertEqual(record.trang_thai, "VANG")  # vẫn VẮNG như lúc mở phiên
        self.assertIsNone(record.overridden_by)  # không có dấu vết ghi một phần

    def test_f01_invalid_status_rolls_back_nothing(self):
        """Trạng thái sai ở item đầu → 400, không ghi gì cả."""
        session = self.make_session()
        res = self._override(
            session,
            [
                {"member_id": self.profile_a.pk, "trang_thai": "TUYEN_BO"},
                {"member_id": self.profile_b.pk, "trang_thai": "CO_MAT"},
            ],
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            AttendanceRecord.objects.get(session=session, member_id=self.profile_b.pk).trang_thai,
            "VANG",
        )

    def test_f01_duplicate_member_ids_rejected(self):
        """member_id trùng trong danh sách → 400, không ghi."""
        session = self.make_session()
        res = self._override(
            session,
            [
                {"member_id": self.profile_a.pk, "trang_thai": "CO_MAT"},
                {"member_id": self.profile_a.pk, "trang_thai": "CO_PHEP"},
            ],
        )
        self.assertEqual(res.status_code, 400)
        record = AttendanceRecord.objects.get(session=session, member_id=self.profile_a.pk)
        self.assertEqual(record.trang_thai, "VANG")

    def test_f01_bad_member_id_type_rejected(self):
        """member_id sai kiểu (bool/str/<=0) → 400."""
        session = self.make_session()
        for bad in [True, "abc", 0, -5, None]:
            res = self._override(session, [{"member_id": bad, "trang_thai": "CO_MAT"}])
            self.assertEqual(res.status_code, 400, f"member_id={bad!r} phải bị chặn 400")

    def test_f01_empty_items_rejected(self):
        session = self.make_session()
        self.assertEqual(self._override(session, []).status_code, 400)

    def test_f01_all_valid_items_commit_together(self):
        """Danh sách hợp lệ (kể cả member chưa có record) → cập nhật đủ tất cả."""
        session = self.make_session()
        res = self._override(
            session,
            [
                {"member_id": self.profile_a.pk, "trang_thai": "CO_PHEP"},
                {"member_id": self.profile_b.pk, "trang_thai": "CO_MAT"},
            ],
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["updated"], 2)
        self.assertEqual(
            AttendanceRecord.objects.get(session=session, member_id=self.profile_a.pk).trang_thai,
            "CO_PHEP",
        )
        self.assertFalse(
            AttendanceRecord.objects.get(session=session, member_id=self.profile_a.pk).is_suspicious
        )

    def test_f01_mid_loop_save_failure_rolls_back_all(self):
        """Lỗi save giữa chừng → atomic rollback, bản ghi đầu giữ nguyên."""
        from unittest.mock import patch

        session = self.make_session()
        original = AttendanceService._repo()
        profile_b_pk = self.profile_b.pk

        class BoomRepo(type(original)):
            def get_or_create_record(self, *args, **kwargs):
                if kwargs.get("member_id") == profile_b_pk or (
                    len(args) > 1 and args[1] == profile_b_pk
                ):
                    raise RuntimeError("DB explosion giữa chừng")
                return super().get_or_create_record(*args, **kwargs)

        with patch.object(AttendanceService, "_repository_class", BoomRepo):
            with self.assertRaises(RuntimeError):
                AttendanceService.bulk_override(
                    session,
                    [
                        {"member_id": self.profile_a.pk, "trang_thai": "CO_PHEP"},
                        {"member_id": self.profile_b.pk, "trang_thai": "CO_MAT"},
                    ],
                    self.bcn,
                )
        # Rollback: A vẫn VẮNG, không bị override
        record = AttendanceRecord.objects.get(session=session, member_id=self.profile_a.pk)
        self.assertEqual(record.trang_thai, "VANG")
        self.assertIsNone(record.overridden_by)


@override_settings(AXES_ENABLED=False)
class LateCheckInDuplicateTests(AttendanceTestBase):
    """F07 — check-in muộn gửi lại phải 409, không sửa record/XP."""

    def _make_late_session(self):
        session = self.make_session()
        # Dời mo_phien_at về 20 phút trước → mọi check-in bây giờ là DI_MUON
        AttendanceSession.objects.filter(pk=session.pk).update(
            mo_phien_at=timezone.now() - timedelta(minutes=20)
        )
        session.refresh_from_db()
        return session

    def test_f07_second_late_checkin_rejected_409(self):
        session = self._make_late_session()
        first = self.checkin(self.member_a, session)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["data"]["trang_thai"], "DI_MUON")

        second = self.checkin(self.member_a, session)
        self.assertEqual(second.status_code, 409)

    def test_f07_record_untouched_after_duplicate(self):
        """Bản ghi giữ nguyên checked_in_at/device/GPS/XP sau lần gửi trùng."""
        session = self._make_late_session()
        first = self.checkin(self.member_a, session)
        record = AttendanceRecord.objects.get(session=session, member=self.profile_a)
        snapshot = {
            "checked_in_at": record.checked_in_at,
            "device_id": record.device_id,
            "vi_do": record.vi_do,
            "kinh_do": record.kinh_do,
            "xp_awarded": record.xp_awarded,
            "khoang_cach_m": record.khoang_cach_m,
        }
        self.checkin(self.member_a, session)  # 409
        record.refresh_from_db()
        self.assertEqual(record.checked_in_at, snapshot["checked_in_at"])
        self.assertEqual(record.device_id, snapshot["device_id"])
        self.assertEqual(record.vi_do, snapshot["vi_do"])
        self.assertEqual(record.kinh_do, snapshot["kinh_do"])
        self.assertEqual(record.xp_awarded, snapshot["xp_awarded"])
        self.assertEqual(record.khoang_cach_m, snapshot["khoang_cach_m"])

    def test_f07_duplicate_from_other_device_still_blocked(self):
        """Thiết bị khác gửi lại cùng member vẫn bị chặn (không trick qua device)."""
        session = self._make_late_session()
        self.checkin(self.member_a, session, device_id="DEVICE-A")
        second = self.checkin(self.member_a, session, device_id="DEVICE-A-2")
        self.assertEqual(second.status_code, 409)


@override_settings(AXES_ENABLED=False)
class SessionRecordsEndpointTests(AttendanceTestBase):
    """F10 — GET /attendance/sessions/{id}/records/ (BCN audit bảng theo phiên)."""

    def _seed_records(self, session):
        AttendanceRecord.objects.filter(session=session, member=self.profile_a).update(
            trang_thai="CO_MAT",
            checked_in_at=timezone.now(),
            device_id="DEV-A",
            xp_awarded=50,
        )
        AttendanceRecord.objects.filter(session=session, member=self.profile_b).update(
            trang_thai="DI_MUON", xp_awarded=25
        )

    def test_bcn_sees_records_of_a_session(self):
        session = self.make_session()
        self._seed_records(session)
        self.client.force_authenticate(self.bcn)
        res = self.client.get(f"{ATT_URL}sessions/{session.id}/records/")
        self.assertEqual(res.status_code, 200)
        items = res.data["data"]["items"]
        self.assertEqual(len(items), 2)
        by_member = {i["member"]: i for i in items}
        self.assertEqual(by_member[self.profile_a.pk]["trang_thai"], "CO_MAT")
        self.assertEqual(by_member[self.profile_b.pk]["trang_thai"], "DI_MUON")
        # Không lộ GPS thô trong payload admin
        self.assertNotIn("vi_do", items[0])
        self.assertNotIn("kinh_do", items[0])

    def test_filter_by_status(self):
        session = self.make_session()
        self._seed_records(session)
        self.client.force_authenticate(self.bcn)
        res = self.client.get(f"{ATT_URL}sessions/{session.id}/records/?trang_thai=CO_MAT")
        items = res.data["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["trang_thai"], "CO_MAT")

    def test_invalid_status_filter_400(self):
        session = self.make_session()
        self.client.force_authenticate(self.bcn)
        res = self.client.get(f"{ATT_URL}sessions/{session.id}/records/?trang_thai=ABC")
        self.assertEqual(res.status_code, 400)

    def test_member_forbidden(self):
        """MEMBER không được xem bảng quản trị theo phiên (RBAC)."""
        session = self.make_session()
        self.client.force_authenticate(self.member_a)
        res = self.client.get(f"{ATT_URL}sessions/{session.id}/records/")
        self.assertEqual(res.status_code, 403)

    def test_anonymous_401(self):
        session = self.make_session()
        res = APIClient().get(f"{ATT_URL}sessions/{session.id}/records/")
        self.assertEqual(res.status_code, 401)

    def test_404_for_missing_session(self):
        self.client.force_authenticate(self.bcn)
        res = self.client.get(f"{ATT_URL}sessions/999999/records/")
        self.assertEqual(res.status_code, 404)

    def test_closed_session_records_still_viewable(self):
        """Sau khi đóng phiên, BCN vẫn xem được bản ghi (đúng mục đích audit)."""
        session = self.make_session()
        self._seed_records(session)
        AttendanceService.close_session(session, closed_by=self.bcn)
        self.client.force_authenticate(self.bcn)
        res = self.client.get(f"{ATT_URL}sessions/{session.id}/records/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["data"]["items"]), 2)
