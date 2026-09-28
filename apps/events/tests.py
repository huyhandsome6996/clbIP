"""
Tests — apps.events
====================
Phủ: tạo sự kiện + ma_hd tự sinh, RBAC (MEMBER không tạo được),
đăng ký vé (OPEN_REGISTRATION / PLANNING / trùng / hết chỗ / hủy-ređăng ký),
DAG topological order, phát hiện chu trình, complete_task + XP ledger.
"""
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.events.models import ActivityEvent, EventRegistration, EventTask
from apps.events.services import EventTaskService
from apps.members.models import MemberProfile

EVENTS_URL = "/api/v1/events/"


def event_payload(**overrides) -> dict:
    """Payload hợp lệ để POST /api/v1/events/."""
    now = timezone.now()
    data = {
        "ten_hoat_dong": "Workshop Python Backend 2026",
        "mo_ta": "Workshop lập trình backend cho thành viên CLB",
        "loai_hd": "WORKSHOP",
        "thoi_gian_bat_dau": (now + timedelta(days=7)).isoformat(),
        "thoi_gian_ket_thuc": (now + timedelta(days=7, hours=3)).isoformat(),
        "dia_diem": "Phòng 201 — ĐHSP Huế",
        "vi_do": 16.4637,
        "kinh_do": 107.5909,
        "ban_kinh_m": 50,
        "so_luong_toi_da": 100,
    }
    data.update(overrides)
    return data


class EventTestBase(TestCase):
    """Base: BCN + MEMBER + APIClient (axes đã tắt qua settings.TESTING)."""

    def setUp(self) -> None:
        cache.clear()  # reset throttle history giữa các test
        self.client = APIClient()
        self.bcn = User.objects.create_user(
            username="bcn@clb.vn", email="bcn@clb.vn", password="TestPass123!", role="BCN"
        )
        self.member = User.objects.create_user(
            username="thanhvien@clb.vn",
            email="thanhvien@clb.vn",
            password="TestPass123!",
            role="MEMBER",
        )
        self.member_profile = MemberProfile.objects.create(
            user=self.member, ho_ten="Nguyễn Thành Viên"
        )

    @staticmethod
    def make_event(trang_thai: str = "OPEN_REGISTRATION", so_luong_toi_da: int = 100, **extra):
        """Tạo sự kiện trực tiếp qua ORM cho các test đăng ký/DAG."""
        now = timezone.now()
        fields = dict(
            ma_hd=f"EVTEST{uuid.uuid4().hex[:8].upper()}",
            ten_hoat_dong="Sự kiện kiểm thử",
            loai_hd="WORKSHOP",
            thoi_gian_bat_dau=now + timedelta(days=1),
            thoi_gian_ket_thuc=now + timedelta(days=2),
            dia_diem="Huế",
            trang_thai=trang_thai,
            so_luong_toi_da=so_luong_toi_da,
        )
        fields.update(extra)
        return ActivityEvent.objects.create(**fields)

    def _make_member(self, idx: int):
        """Tạo thêm 1 MEMBER kèm hồ sơ (dùng cho test tranh vé)."""
        email = f"member{idx}@clb.vn"
        user = User.objects.create_user(
            username=email, email=email, password="TestPass123!", role="MEMBER"
        )
        return user, MemberProfile.objects.create(user=user, ho_ten=f"Thành Viên {idx}")


# ----------------------------------------------------------------------
# 1-2. Tạo sự kiện + RBAC
# ----------------------------------------------------------------------
class EventCreateTests(EventTestBase):
    def test_bcn_create_event_auto_ma_hd(self) -> None:
        """BCN tạo event → 201, ma_hd tự sinh dạng EV{năm}{seq}."""
        self.client.force_authenticate(self.bcn)
        response = self.client.post(EVENTS_URL, event_payload(), format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertTrue(
            data["ma_hd"].startswith(f"EV{timezone.now().year}"),
            f"ma_hd sai định dạng: {data['ma_hd']}",
        )
        self.assertTrue(ActivityEvent.objects.filter(pk=data["id"]).exists())

    def test_member_create_event_forbidden(self) -> None:
        """MEMBER tạo event → 403 (chỉ BCN/ADMIN)."""
        self.client.force_authenticate(self.member)
        response = self.client.post(EVENTS_URL, event_payload(), format="json")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])

    def test_create_event_invalid_time_range(self) -> None:
        """thoi_gian_bat_dau >= thoi_gian_ket_thuc → 400 ValidationException."""
        self.client.force_authenticate(self.bcn)
        payload = event_payload(
            thoi_gian_bat_dau=(timezone.now() + timedelta(days=7)).isoformat(),
            thoi_gian_ket_thuc=(timezone.now() + timedelta(days=6)).isoformat(),
        )
        response = self.client.post(EVENTS_URL, payload, format="json")
        self.assertEqual(response.status_code, 400)


# ----------------------------------------------------------------------
# 3-7. Đăng ký vé
# ----------------------------------------------------------------------
class EventRegistrationTests(EventTestBase):
    def test_register_success_when_open(self) -> None:
        """Đăng ký khi OPEN_REGISTRATION → 201, ma_ve prefix VE-, REGISTERED."""
        event = self.make_event(trang_thai="OPEN_REGISTRATION")
        self.client.force_authenticate(self.member)
        response = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["success"])
        self.assertIn("Vé điện tử", response.data["message"])
        data = response.data["data"]
        self.assertTrue(data["ma_ve"].startswith("VE-"))
        self.assertEqual(data["trang_thai"], "REGISTERED")

    def test_register_rejected_when_planning(self) -> None:
        """Đăng ký khi PLANNING → 409 EventStatusException."""
        event = self.make_event(trang_thai="PLANNING")
        self.client.force_authenticate(self.member)
        response = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertIn("chưa mở đăng ký", response.data["message"])

    def test_duplicate_registration_conflict(self) -> None:
        """Đăng ký trùng → 409 DuplicateRegistrationException."""
        event = self.make_event(trang_thai="OPEN_REGISTRATION")
        self.client.force_authenticate(self.member)
        first = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(first.status_code, 201)

        second = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(second.status_code, 409)
        self.assertIn("đã đăng ký", second.data["message"])

    def test_event_full_third_member_rejected(self) -> None:
        """so_luong_toi_da=2 — member thứ 3 tranh vé → 409 EventFullException."""
        event = self.make_event(trang_thai="OPEN_REGISTRATION", so_luong_toi_da=2)
        _, profile2 = self._make_member(2)
        _, profile3 = self._make_member(3)

        # Đăng ký đúng 2 user đầu, user thứ 3 phải bị chặn (mô phỏng tranh vé)
        self.client.force_authenticate(self.member)
        r1 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r1.status_code, 201)
        self.client.force_authenticate(profile2.user)
        r2 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r2.status_code, 201)
        self.client.force_authenticate(profile3.user)
        r3 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r3.status_code, 409)
        self.assertIn("tối đa", r3.data["message"])
        self.assertEqual(
            event.registrations.exclude(
                trang_thai=EventRegistration.TrangThai.CANCELLED
            ).count(),
            2,
        )

    def test_cancel_and_reregister(self) -> None:
        """Hủy vé → CANCELLED; chủ vé cũ đăng ký lại OK (chỗ được giải phóng)."""
        event = self.make_event(trang_thai="OPEN_REGISTRATION", so_luong_toi_da=1)
        other_user, _ = self._make_member(9)
        self.client.force_authenticate(self.member)

        # Chiếm chỗ duy nhất
        r1 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r1.status_code, 201)
        ma_ve_1 = r1.data["data"]["ma_ve"]

        # Hủy vé → CANCELLED
        r2 = self.client.post(
            f"{EVENTS_URL}{event.id}/cancel-registration/", {}, format="json"
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["data"]["trang_thai"], "CANCELLED")

        # Chủ vé cũ đăng ký lại ngay → OK, nhận vé MỚI (khác mã vé cũ)
        r3 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r3.status_code, 201)
        self.assertEqual(r3.data["data"]["trang_thai"], "REGISTERED")
        self.assertNotEqual(r3.data["data"]["ma_ve"], ma_ve_1)

        # Chỗ đã đầy trở lại → người khác đăng ký bị chặn (409 EventFull)
        self.client.force_authenticate(other_user)
        r4 = self.client.post(f"{EVENTS_URL}{event.id}/register/", {}, format="json")
        self.assertEqual(r4.status_code, 409)


# ----------------------------------------------------------------------
# 8-10. DAG task
# ----------------------------------------------------------------------
class EventTaskDagTests(EventTestBase):
    def test_dag_topological_order_valid(self) -> None:
        """Task A, B (B depends A) → topological_order [A, B], DAG hợp lệ."""
        event = self.make_event(trang_thai="PLANNING")
        self.client.force_authenticate(self.bcn)

        r_a = self.client.post(
            f"{EVENTS_URL}{event.id}/tasks/", {"ten_task": "Chuẩn bị địa điểm"}, format="json"
        )
        self.assertEqual(r_a.status_code, 201)
        a_id = r_a.data["data"]["id"]

        r_b = self.client.post(
            f"{EVENTS_URL}{event.id}/tasks/",
            {"ten_task": "Setup âm thanh", "depends_on": [a_id]},
            format="json",
        )
        self.assertEqual(r_b.status_code, 201)
        b_id = r_b.data["data"]["id"]

        response = self.client.get(f"{EVENTS_URL}{event.id}/tasks/topological-order/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertTrue(data["is_valid_dag"])
        self.assertIsNone(data["cycle"])
        self.assertEqual(data["topological_order"], [a_id, b_id])

    def test_dag_cycle_detection(self) -> None:
        """X ← Y và Y ← X → CycleDetectedException (400), dữ liệu không đổi."""
        event = self.make_event(trang_thai="PLANNING")
        self.client.force_authenticate(self.bcn)

        r_x = self.client.post(f"{EVENTS_URL}{event.id}/tasks/", {"ten_task": "Task X"}, format="json")
        x_id = r_x.data["data"]["id"]
        r_y = self.client.post(
            f"{EVENTS_URL}{event.id}/tasks/",
            {"ten_task": "Task Y", "depends_on": [x_id]},
            format="json",
        )
        y_id = r_y.data["data"]["id"]

        # Y đã depends X; giờ ép X depends Y → chu trình → phải raise và ROLLBACK
        from apps.common.exceptions import CycleDetectedException

        with self.assertRaises(CycleDetectedException) as ctx:
            EventTaskService.set_dependencies(x_id, [y_id])
        self.assertIn(x_id, ctx.exception.errors["cycle"])

        # X không bị ghi phụ thuộc (rollback an toàn)
        x_task = EventTask.objects.get(pk=x_id)
        self.assertEqual(x_task.depends_on.count(), 0)

    def test_complete_task_awards_xp(self) -> None:
        """complete_task → XpLedger ghi nhận idempotency_key=task_<id>.
        GamificationService của Agent B viết song song — chưa có thì SKIP."""
        try:
            import apps.gamification.services  # noqa: F401
        except ImportError:
            self.skipTest("GamificationService chưa triển khai (Agent B song song)")

        from apps.gamification.models import XpLedger

        event = self.make_event(trang_thai="IN_PROGRESS")
        task = EventTask.objects.create(event=event, ten_task="Task có thưởng")
        task.nguoi_phu_trach = self.member_profile
        task.save(update_fields=["nguoi_phu_trach"])

        EventTaskService.complete_task(task.id)

        task.refresh_from_db()
        self.assertTrue(task.is_completed)
        self.assertTrue(
            XpLedger.objects.filter(idempotency_key=f"task_{task.id}").exists()
        )


# ----------------------------------------------------------------------
# Budget + Danh sách vé (BCN)
# ----------------------------------------------------------------------
class EventBudgetAndRegistrationListTests(EventTestBase):
    def test_budget_post_auto_total(self) -> None:
        """POST budget → hạng mục tạo mới; tổng kinh phí tự động tính lại."""
        event = self.make_event(trang_thai="PLANNING")
        self.client.force_authenticate(self.bcn)

        r1 = self.client.post(
            f"{EVENTS_URL}{event.id}/budget/",
            {"ten_hang_muc": "Thuê loa", "so_tien": 500000},
            format="json",
        )
        r2 = self.client.post(
            f"{EVENTS_URL}{event.id}/budget/",
            {"ten_hang_muc": "Đồ ăn nhẹ", "so_tien": 300000},
            format="json",
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)

        event.refresh_from_db()
        self.assertEqual(event.tong_kinh_phi_du_tru, 800000)

    def test_registration_list_requires_bcn(self) -> None:
        """Danh sách vé: MEMBER → 403, BCN → 200."""
        event = self.make_event(trang_thai="OPEN_REGISTRATION")
        self.client.force_authenticate(self.member)
        r_member = self.client.get(f"{EVENTS_URL}{event.id}/registrations/")
        self.assertEqual(r_member.status_code, 403)

        self.client.force_authenticate(self.bcn)
        r_bcn = self.client.get(f"{EVENTS_URL}{event.id}/registrations/")
        self.assertEqual(r_bcn.status_code, 200)
        self.assertIn("items", r_bcn.data["data"])
