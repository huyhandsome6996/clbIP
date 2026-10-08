"""
Regression tests — audit luồng thành viên 1114efd (M05)
=======================================================
Policy Security Hardening §5.1: `accuracy` BẮT BUỘC, hữu hạn, > 0,
≤ MAX_GPS_ACCURACY_METERS (100). Không còn đường "thiếu cảm biến vẫn +XP".
"""
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.exceptions import AntiCheatException
from apps.attendance.services.nonce import AttendanceNonceService
from apps.attendance.services.attendance_service import AttendanceService
from apps.attendance.tests import CENTER_LAT, CENTER_LON, AttendanceTestBase


class CheckInAccuracyPolicyTests(AttendanceTestBase):
    """M05 — ma trận accuracy: missing/null/negative/zero/NaN/inf/poor."""

    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.session = self.make_session()

    def _post(self, accuracy, *, omit=False):
        import json as _json

        self.client.force_authenticate(self.member_a)
        payload = {
            "session_id": self.session.id,
            "latitude": CENTER_LAT + 0.0001,
            "longitude": CENTER_LON,
            "client_time": timezone.now().isoformat(),
            "device_id": "DEVICE-ACC-TEST",
            "nonce": AttendanceNonceService.generate(self.session)["nonce"],
            "accuracy": accuracy,
        }
        if omit:
            payload.pop("accuracy", None)
        # Gửi JSON thô (allow_nan) để mô phỏng client gửi NaN/Infinity thật —
        # DRF test client `format="json"` sẽ tự chặn trước khi tới server.
        return self.client.post(
            "/api/v1/attendance/check-in/",
            data=_json.dumps(payload),
            content_type="application/json",
        )

    def test_missing_accuracy_rejected_400(self) -> None:
        res = self._post(None, omit=True)
        self.assertEqual(res.status_code, 400)
        self.assertIn("accuracy", str(res.data).lower())

    def test_null_accuracy_rejected_400(self) -> None:
        res = self._post(None)
        self.assertEqual(res.status_code, 400)

    def test_negative_accuracy_rejected_400(self) -> None:
        res = self._post(-12.5)
        self.assertEqual(res.status_code, 400)
        self.assertIn("dương", str(res.data))

    def test_zero_accuracy_rejected_400(self) -> None:
        res = self._post(0)
        self.assertEqual(res.status_code, 400)

    def test_nan_accuracy_rejected_400(self) -> None:
        # NaN/Infinity literal bị chặn 400: hoặc ở tầng parse JSON của DRF
        # ("JSON parse error") hoặc ở validate_accuracy ("hữu hạn") — cả hai
        # đều là từ chối an toàn theo policy §5.1.
        res = self._post(float("nan"))
        self.assertEqual(res.status_code, 400)

    def test_infinite_accuracy_rejected_400(self) -> None:
        res = self._post(float("inf"))
        self.assertEqual(res.status_code, 400)

    def test_poor_accuracy_over_limit_rejected_400(self) -> None:
        res = self._post(150.0)
        self.assertEqual(res.status_code, 400)
        self.assertIn("quá kém", str(res.data))

    def test_valid_accuracy_checkin_ok(self) -> None:
        """Control: accuracy hợp lệ (10m) + trong bán kính → check-in thành công."""
        res = self._post(10.0)
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["data"]["trang_thai"], "CO_MAT")


class AntiCheatEngineAccuracyLayerTests(AttendanceTestBase):
    """M05 — defense in depth: engine tự chặn accuracy lỗi khi gọi service thẳng."""

    def _service_checkin(self, accuracy):
        return AttendanceService.check_in(
            member=self.profile_a,
            session_id=self.session.id,
            client_lat=CENTER_LAT + 0.0001,
            client_lon=CENTER_LON,
            client_time=timezone.now(),
            device_id="DEVICE-ENGINE-TEST",
            nonce=AttendanceNonceService.generate(self.session)["nonce"],
            accuracy=accuracy,
        )

    def setUp(self) -> None:
        super().setUp()
        self.session = self.make_session()

    def test_engine_rejects_none_accuracy(self) -> None:
        with self.assertRaises(AntiCheatException):
            self._service_checkin(None)

    def test_engine_rejects_nonfinite_accuracy(self) -> None:
        with self.assertRaises(AntiCheatException):
            self._service_checkin(float("nan"))
        with self.assertRaises(AntiCheatException):
            self._service_checkin(float("inf"))

    def test_engine_rejects_nonpositive_accuracy(self) -> None:
        with self.assertRaises(AntiCheatException):
            self._service_checkin(0)
        with self.assertRaises(AntiCheatException):
            self._service_checkin(-3.0)
