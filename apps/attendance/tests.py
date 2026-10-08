"""
Tests — apps.attendance
========================
Phủ: mở phiên + auto VẮNG, RBAC, check-in hợp lệ (CO_MAT/streak/XP/early bonus),
anti-cheat 7 lớp (radius, mock, accuracy, replay skew, nonce, device reuse,
teleportation), duplicate, phiên đóng, bulk_override BCN, lịch sử /me/ chống IDOR.
"""
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.attendance.services import AttendanceNonceService, AttendanceService
from apps.authentication.models import User
from apps.events.models import ActivityEvent, EventRegistration
from apps.members.models import MemberProfile

ATT_URL = "/api/v1/attendance/"

# Tâm phiên chuẩn: somewhere ở Huế — bán kính 50m
CENTER_LAT = 16.4637
CENTER_LON = 107.5909
# Tọa độ lệch ~10m về phía bắc (nằm trong bán kính)
NEAR_LAT = 16.46379
NEAR_LON = 107.5909
# Tọa độ cách ~1.4km (ngoài bán kính)
FAR_LAT = 16.4763
FAR_LON = 107.5909
# Tọa độ Hà Nội (cho test teleportation)
HANOI_LAT = 21.0278
HANOI_LON = 105.8342

import apps.gamification.services  # noqa: F401 — đã triển khai, giữ cờ cho assert phân nhánh

HAS_GAMIFICATION = True


class AttendanceTestBase(TestCase):
    """Base: BCN + 2 member (A, B) kèm MemberProfile + helper tạo phiên/check-in."""

    def setUp(self) -> None:
        cache.clear()  # reset throttle history giữa các test (checkin 3/phút)
        self.client = APIClient()
        self.bcn = User.objects.create_user(
            username="bcn@clb.vn", email="bcn@clb.vn", password="TestPass123!", role="BCN"
        )
        self.member_a = User.objects.create_user(
            username="a@clb.vn", email="a@clb.vn", password="TestPass123!", role="MEMBER"
        )
        self.member_b = User.objects.create_user(
            username="b@clb.vn", email="b@clb.vn", password="TestPass123!", role="MEMBER"
        )
        self.profile_a = MemberProfile.objects.create(user=self.member_a, ho_ten="Thành Viên A")
        self.profile_b = MemberProfile.objects.create(user=self.member_b, ho_ten="Thành Viên B")

    def make_session(self, lat: float = CENTER_LAT, lon: float = CENTER_LON, **extra) -> AttendanceSession:
        """Mở phiên qua AttendanceService (tự tạo record VẮNG cho A, B)."""
        return AttendanceService.open_session(
            ten_phien=extra.pop("ten_phien", f"Phiên {uuid.uuid4().hex[:6]}"),
            vi_do=lat,
            kinh_do=lon,
            ban_kinh_m=extra.pop("ban_kinh_m", 50),
            **extra,
        )

    def shift_session_open_time(self, session: AttendanceSession, minutes: float) -> AttendanceSession:
        """Dời mo_phien_at (auto_now_add) sang tương lai/qua khứ để test early/late."""
        AttendanceSession.objects.filter(pk=session.pk).update(
            mo_phien_at=timezone.now() + timedelta(minutes=minutes)
        )
        session.refresh_from_db()
        return session

    def checkin(
        self,
        user,
        session: AttendanceSession,
        lat: float = NEAR_LAT,
        lon: float = NEAR_LON,
        device_id: str = None,
        client_time: str = None,
        nonce: str = None,
        is_mock: bool = False,
        accuracy: float = 10.0,
    ):
        """POST /check-in/ với nonce + client_time tự sinh hợp lệ (trừ khi override).

        M05 (audit 1114efd): accuracy mặc định 10.0m (tín hiệu tốt) vì backend
        đã BẮT BUỘC accuracy theo Security §5.1 — test mô phỏng client thật
        luôn gửi kèm dữ liệu cảm biến.
        """
        self.client.force_authenticate(user)
        payload = {
            "session_id": session.id,
            "latitude": lat,
            "longitude": lon,
            "client_time": client_time or timezone.now().isoformat(),
            "device_id": device_id or f"DEVICE-{user.pk}",
            "nonce": nonce or AttendanceNonceService.generate(session)["nonce"],
            "is_mock": is_mock,
            "accuracy": accuracy,
        }
        return self.client.post(f"{ATT_URL}check-in/", payload, format="json")


# ----------------------------------------------------------------------
# 1. Mở phiên + RBAC
# ----------------------------------------------------------------------
class OpenSessionTests(AttendanceTestBase):
    def test_open_session_creates_vang_records(self) -> None:
        """BCN mở phiên → bản ghi VẮNG tự tạo cho mọi member ACTIVE."""
        # Member C ở trạng thái INACTIVE → KHÔNG được tạo record
        member_c = User.objects.create_user(
            username="c@clb.vn", email="c@clb.vn", password="TestPass123!", role="MEMBER"
        )
        MemberProfile.objects.create(
            user=member_c, ho_ten="Thành Viên C", trang_thai_hd=MemberProfile.TrangThai.INACTIVE
        )

        self.client.force_authenticate(self.bcn)
        response = self.client.post(
            f"{ATT_URL}sessions/",
            {
                "ten_phien": "Sinh hoạt định kỳ tuần 5",
                "vi_do": CENTER_LAT,
                "kinh_do": CENTER_LON,
                "ban_kinh_m": 50,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        session_id = response.data["data"]["id"]
        self.assertNotIn("nonce_secret", response.data["data"])  # secret không bao giờ lộ

        records = AttendanceRecord.objects.filter(session_id=session_id)
        self.assertEqual(records.count(), 2)  # A + B (không tính C INACTIVE)
        self.assertTrue(
            all(r.trang_thai == AttendanceRecord.TrangThaiDiemDanh.VANG for r in records)
        )
        self.assertTrue(AttendanceSession.objects.get(pk=session_id).nonce_secret)

    def test_member_cannot_open_session(self) -> None:
        """MEMBER mở phiên → 403."""
        self.client.force_authenticate(self.member_a)
        response = self.client.post(
            f"{ATT_URL}sessions/",
            {"ten_phien": "Phiên trái phép", "vi_do": CENTER_LAT, "kinh_do": CENTER_LON},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


# ----------------------------------------------------------------------
# 2. Check-in hợp lệ + XP + Streak
# ----------------------------------------------------------------------
class CheckInSuccessTests(AttendanceTestBase):
    def test_checkin_success_on_time(self) -> None:
        """Check-in đúng giờ (mới mở phiên) → CO_MAT, dist<50, streak=1, XP=50."""
        session = self.make_session()
        response = self.checkin(self.member_a, session)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["trang_thai"], "CO_MAT")
        self.assertLess(data["khoang_cach_m"], 50)
        self.assertEqual(data["streak_count"], 1)
        if not HAS_GAMIFICATION:
            self.assertEqual(data["xp_gained"], 50)  # XP_ATTENDANCE mặc định
        else:
            self.assertGreater(data["xp_gained"], 0)

        self.profile_a.refresh_from_db()
        self.assertEqual(self.profile_a.streak_count, 1)
        self.assertEqual(self.profile_a.last_attendance_date, timezone.localdate())

        record = AttendanceRecord.objects.get(session=session, member=self.profile_a)
        self.assertEqual(record.device_id, f"DEVICE-{self.member_a.pk}")

    def test_checkin_early_bonus(self) -> None:
        """mo_phien_at lùi sau 30 phút → điểm danh sớm ≥15 phút → bonus XP (70)."""
        session = self.make_session()
        self.shift_session_open_time(session, minutes=30)  # phiên "sẽ mở" sau 30 phút

        response = self.checkin(self.member_a, session)
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["trang_thai"], "CO_MAT")
        if not HAS_GAMIFICATION:
            self.assertEqual(data["xp_gained"], 70)  # 50 + 20 early bonus
        self.assertGreater(data["xp_gained"], 0)

    def test_checkin_late_after_15_minutes(self) -> None:
        """mo_phien_at lùi về 20 phút trước → quá 15 phút → DI_MUON (XP 25)."""
        session = self.make_session()
        self.shift_session_open_time(session, minutes=-20)

        response = self.checkin(self.member_a, session)
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["trang_thai"], "DI_MUON")
        if not HAS_GAMIFICATION:
            self.assertEqual(data["xp_gained"], 25)  # XP_ATTENDANCE_LATE

    def test_checkin_marks_event_registration_checked_in(self) -> None:
        """Check-in tại phiên gắn sự kiện → vé EventRegistration chuyển CHECKED_IN."""
        now = timezone.now()
        event = ActivityEvent.objects.create(
            ma_hd=f"EVTEST{uuid.uuid4().hex[:8].upper()}",
            ten_hoat_dong="Sự kiện có điểm danh",
            loai_hd="WORKSHOP",
            thoi_gian_bat_dau=now,
            thoi_gian_ket_thuc=now + timedelta(hours=2),
            dia_diem="Huế",
            trang_thai="IN_PROGRESS",
        )
        EventRegistration.objects.create(
            event=event,
            member=self.profile_a,
            ma_ve=f"VE-{uuid.uuid4().hex[:10].upper()}",
            trang_thai=EventRegistration.TrangThai.REGISTERED,
        )
        session = self.make_session(event_id=event.id)

        response = self.checkin(self.member_a, session)
        self.assertEqual(response.status_code, 200)

        registration = EventRegistration.objects.get(event=event, member=self.profile_a)
        self.assertEqual(registration.trang_thai, EventRegistration.TrangThai.CHECKED_IN)


# ----------------------------------------------------------------------
# 3-8. Anti-Cheat Engine
# ----------------------------------------------------------------------
class AntiCheatTests(AttendanceTestBase):
    def test_checkin_out_of_radius(self) -> None:
        """Cách 1.4km → 403 AntiCheat (vượt bán kính 50m)."""
        session = self.make_session()
        response = self.checkin(self.member_a, session, lat=FAR_LAT, lon=FAR_LON)

        self.assertEqual(response.status_code, 403)
        self.assertIn("cách địa điểm", response.data["message"])
        # Record không bị đổi trạng thái
        record = AttendanceRecord.objects.get(session=session, member=self.profile_a)
        self.assertEqual(record.trang_thai, AttendanceRecord.TrangThaiDiemDanh.VANG)

    def test_checkin_mock_location_rejected(self) -> None:
        """is_mock=True → 403 'vị trí giả lập'."""
        session = self.make_session()
        response = self.checkin(self.member_a, session, is_mock=True)
        self.assertEqual(response.status_code, 403)
        self.assertIn("giả lập", response.data["message"])

    def test_checkin_poor_accuracy_rejected(self) -> None:
        """accuracy=150m (>100m) → 400 bị chặn ở serializer (M05 — §5.1)."""
        session = self.make_session()
        response = self.checkin(self.member_a, session, accuracy=150)
        self.assertEqual(response.status_code, 400)
        self.assertIn("quá kém", str(response.data))

    def test_checkin_timestamp_skew_rejected(self) -> None:
        """client_time lệch 120 giây (>60s) → 403 chống Replay Attack."""
        session = self.make_session()
        replay_time = (timezone.now() - timedelta(seconds=120)).isoformat()
        response = self.checkin(self.member_a, session, client_time=replay_time)
        self.assertEqual(response.status_code, 403)
        self.assertIn("không đồng bộ", response.data["message"])

    def test_checkin_invalid_nonce_rejected(self) -> None:
        """nonce sai → 403 InvalidNonce."""
        session = self.make_session()
        response = self.checkin(self.member_a, session, nonce="000000")
        self.assertEqual(response.status_code, 403)
        self.assertIn("không đúng hoặc đã hết hiệu lực", response.data["message"])

    def test_device_reuse_rejected(self) -> None:
        """1 thiết bị điểm danh cho A rồi B → B bị 403 (device reuse)."""
        session = self.make_session()

        r_a = self.checkin(self.member_a, session, device_id="DEVICE-X")
        self.assertEqual(r_a.status_code, 200)

        r_b = self.checkin(self.member_b, session, device_id="DEVICE-X")
        self.assertEqual(r_b.status_code, 403)
        self.assertIn("Thiết bị này đã được dùng", r_b.data["message"])

        record_b = AttendanceRecord.objects.get(session=session, member=self.profile_b)
        self.assertEqual(record_b.trang_thai, AttendanceRecord.TrangThaiDiemDanh.VANG)

    def test_teleportation_rejected(self) -> None:
        """Check-in Huế rồi ngay lập tức Hà Nội → 403 'Dịch chuyển bất khả thi'."""
        session_hue = self.make_session()  # tâm 16.4637/107.5909
        r1 = self.checkin(self.member_a, session_hue)
        self.assertEqual(r1.status_code, 200)

        session_hanoi = self.make_session(lat=HANOI_LAT, lon=HANOI_LON, ten_phien="Phiên Hà Nội")
        r2 = self.checkin(self.member_a, session_hanoi, lat=HANOI_LAT, lon=HANOI_LON)
        self.assertEqual(r2.status_code, 403)
        self.assertIn("Dịch chuyển bất khả thi", r2.data["message"])


# ----------------------------------------------------------------------
# 9-10. Duplicate & Closed session
# ----------------------------------------------------------------------
class CheckInStateTests(AttendanceTestBase):
    def test_duplicate_checkin_rejected(self) -> None:
        """Check-in 2 lần → 409 DuplicateDataException."""
        session = self.make_session()
        first = self.checkin(self.member_a, session)
        self.assertEqual(first.status_code, 200)

        second = self.checkin(self.member_a, session)
        self.assertEqual(second.status_code, 409)
        self.assertIn("đã điểm danh", second.data["message"])

    def test_closed_session_rejected(self) -> None:
        """Phiên CLOSED → check-in bị 409 SessionClosedException."""
        session = self.make_session()
        self.client.force_authenticate(self.bcn)
        close_response = self.client.post(f"{ATT_URL}sessions/{session.id}/close/")
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.data["data"]["trang_thai"], "CLOSED")

        response = self.checkin(self.member_a, session)
        self.assertEqual(response.status_code, 409)
        self.assertIn("đóng", response.data["message"])


# ----------------------------------------------------------------------
# 11-12. BCN bulk override + lịch sử cá nhân
# ----------------------------------------------------------------------
class OverrideAndHistoryTests(AttendanceTestBase):
    def test_bulk_override_co_phep(self) -> None:
        """BCN bulk_override member A → CO_PHEP, overridden_by đúng người."""
        session = self.make_session()
        self.client.force_authenticate(self.bcn)
        response = self.client.put(
            f"{ATT_URL}sessions/{session.id}/bulk-override/",
            {"items": [{"member_id": self.profile_a.id, "trang_thai": "CO_PHEP"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["updated"], 1)

        record = AttendanceRecord.objects.get(session=session, member=self.profile_a)
        self.assertEqual(record.trang_thai, AttendanceRecord.TrangThaiDiemDanh.CO_PHEP)
        self.assertEqual(record.overridden_by, self.bcn)
        self.assertFalse(record.is_suspicious)

    def test_bulk_override_invalid_status(self) -> None:
        """trang_thai lạ → 400 ValidationException."""
        session = self.make_session()
        self.client.force_authenticate(self.bcn)
        response = self.client.put(
            f"{ATT_URL}sessions/{session.id}/bulk-override/",
            {"items": [{"member_id": self.profile_a.id, "trang_thai": "DI_HOC"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_my_history_idor_protection(self) -> None:
        """/attendance/me/ CHỈ trả record của chính mình (chống IDOR)."""
        session = self.make_session()
        self.checkin(self.member_a, session)  # A check-in; B giữ VẮNG

        self.client.force_authenticate(self.member_a)
        r_a = self.client.get(f"{ATT_URL}me/")
        self.assertEqual(r_a.status_code, 200)
        items_a = r_a.data["data"]["items"]
        self.assertEqual(len(items_a), 1)
        self.assertEqual(items_a[0]["member"], self.profile_a.id)
        self.assertEqual(items_a[0]["trang_thai"], "CO_MAT")

        self.client.force_authenticate(self.member_b)
        r_b = self.client.get(f"{ATT_URL}me/")
        items_b = r_b.data["data"]["items"]
        self.assertEqual(len(items_b), 1)  # chỉ record VẮNG của B, KHÔNG thấy của A
        self.assertEqual(items_b[0]["member"], self.profile_b.id)
        self.assertEqual(items_b[0]["trang_thai"], "VANG")


# ----------------------------------------------------------------------
# Nonce service (unit)
# ----------------------------------------------------------------------
class NonceServiceTests(AttendanceTestBase):
    def test_nonce_rotation_and_tolerance(self) -> None:
        """Nonce đổi theo window; window liền trước vẫn được chấp nhận."""
        session = self.make_session()
        now = timezone.now()
        n1 = AttendanceNonceService.generate(session, at=now)
        # Thời điểm chắc chắn ở trong window kế tiếp (+1s sau ranh giới)
        next_window_at = now + timedelta(seconds=n1["expires_in"] + 1)
        n2 = AttendanceNonceService.generate(session, at=next_window_at)

        self.assertNotEqual(n1["nonce"], n2["nonce"])  # xoay cửa sổ 60s
        self.assertTrue(AttendanceNonceService.validate(session, n1["nonce"], at=now))
        # Window liền trước (tolerance) vẫn hợp lệ tại thời điểm window mới
        self.assertTrue(
            AttendanceNonceService.validate(session, n1["nonce"], at=next_window_at)
        )
        # Nonce của session KHÁC phải bị từ chối
        other = self.make_session()
        self.assertFalse(AttendanceNonceService.validate(other, n1["nonce"], at=now))
