"""
Regression tests — audit 06/10/2026 (F08)
==========================================
F08: reopen task tiền nhiệm khi còn hậu nhiệm (trực tiếp hoặc GIÁN TIẾP qua
     chuỗi phụ thuộc) đã hoàn thành phải bị chặn 400 — bảo vệ bất biến DAG
     "task completed thì mọi tiền nhiệm của nó cũng completed".
     Reopen hợp lệ (không hậu nhiệm completed) vẫn hoạt động; XP ledger
     bất biến (không trừ XP đã cộng).
"""
import uuid
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.events.models import ActivityEvent, EventTask
from apps.events.services import EventTaskService
from apps.events.tests import EventTestBase
from apps.gamification.models import XpLedger
from apps.members.models import MemberProfile


@override_settings(AXES_ENABLED=False)
class TaskReopenInvariantTests(EventTestBase):
    """F08 — chặn reopen phá DAG, kể cả phụ thuộc gián tiếp."""

    def setUp(self) -> None:
        super().setUp()
        self.event = self.make_event(trang_thai="IN_PROGRESS")

    def _task(self, name, depends_on=None, completed=False):
        task = EventTask.objects.create(
            event=self.event, ten_task=name, nguoi_phu_trach=self.member_profile
        )
        if depends_on:
            task.depends_on.set(depends_on)
        if completed:
            task.is_completed = True
            task.save(update_fields=["is_completed"])
        return task

    def test_f08_reopen_blocked_when_direct_dependent_completed(self):
        """A hoàn thành; B phụ thuộc A cũng hoàn thành; reopen A → chặn, A vẫn completed."""
        a = self._task("A — in ấn banner", completed=True)
        b = self._task("B — treo banner", depends_on=[a], completed=True)

        with self.assertRaises(Exception) as ctx:
            EventTaskService.reopen_task(a)
        errors = getattr(ctx.exception, "errors", None) or {}
        self.assertIn("blocking_tasks", errors)
        self.assertIn(b.id, [t["id"] for t in errors["blocking_tasks"]])

        a.refresh_from_db()
        b.refresh_from_db()
        self.assertTrue(a.is_completed)  # không bị đổi
        self.assertTrue(b.is_completed)

    def test_f08_reopen_blocked_when_indirect_dependent_completed(self):
        """Chuỗi A ← B ← C: chỉ C completed (B chưa) — reopen A vẫn bị chặn qua C."""
        a = self._task("A — đặt xe", completed=True)
        b = self._task("B — xin phép trường", depends_on=[a], completed=False)
        c = self._task("C — khởi hành", depends_on=[b], completed=True)

        with self.assertRaises(Exception):
            EventTaskService.reopen_task(a)
        a.refresh_from_db()
        self.assertTrue(a.is_completed)
        self.assertFalse(b.is_completed)
        self.assertTrue(c.is_completed)

    def test_f08_reopen_allowed_when_no_completed_descendant(self):
        """Hậu nhiệm tồn tại nhưng CHƯA hoàn thành → reopen OK."""
        a = self._task("A — chuẩn bị tài liệu", completed=True)
        self._task("B — phát tài liệu", depends_on=[a], completed=False)
        reopened = EventTaskService.reopen_task(a)
        self.assertFalse(reopened.is_completed)

    def test_f08_reopen_allowed_when_no_descendant(self):
        """Task lá (không ai phụ thuộc) → reopen tự do."""
        a = self._task("A — task độc lập", completed=True)
        EventTaskService.reopen_task(a)
        a.refresh_from_db()
        self.assertFalse(a.is_completed)

    def test_f08_uncomplete_descendant_then_reopen_ok(self):
        """Mở hậu nhiệm trước → tiền nhiệm reopen được (luồng BCN đúng thứ tự)."""
        a = self._task("A — in banner", completed=True)
        b = self._task("B — treo banner", depends_on=[a], completed=True)
        EventTaskService.reopen_task(b)  # mở B trước
        EventTaskService.reopen_task(a)  # giờ A mở được
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertFalse(a.is_completed)
        self.assertFalse(b.is_completed)

    def test_f08_xp_ledger_untouched_by_blocked_reopen(self):
        """Reopen bị chặn không xóa/thay XP ledger (bất biến theo chính sách)."""
        a = self._task("A — có XP", completed=True)
        self._task("B — phụ thuộc A", depends_on=[a], completed=True)
        XpLedger.objects.create(
            member=self.member_profile, amount=100,
            reason="Hoàn thành task A — có XP",
            source="TASK_COMPLETION", idempotency_key=f"task_{a.id}",
        )
        count_before = XpLedger.objects.count()
        with self.assertRaises(Exception):
            EventTaskService.reopen_task(a)
        self.assertEqual(XpLedger.objects.count(), count_before)

    def test_f08_reopen_via_api_400_with_blocking_list(self):
        """Qua API PATCH is_completed=false → 400 + errors.blocking_tasks cho frontend."""
        a = self._task("A — API reopen", completed=True)
        b = self._task("B — phụ thuộc API", depends_on=[a], completed=True)
        self.client.force_authenticate(self.bcn)
        res = self.client.patch(
            f"/api/v1/events/{self.event.id}/tasks/{a.id}/",
            {"is_completed": False}, format="json",
        )
        self.assertEqual(res.status_code, 400)
        blocking = (res.data.get("errors") or {}).get("blocking_tasks") or []
        self.assertIn(b.id, [t["id"] for t in blocking])


@override_settings(AXES_ENABLED=False)
class EventSearchParamTests(EventTestBase):
    """F09/C6 — GET /events/?search= khớp tên / mã hoạt động (cho selector)."""

    def test_search_by_name_and_ma_hd(self):
        now = timezone.now()
        ActivityEvent.objects.create(
            ma_hd="EVSEARCH1", ten_hoat_dong="Workshop Docker nâng cao",
            loai_hd="WORKSHOP",
            thoi_gian_bat_dau=now + timedelta(days=1),
            thoi_gian_ket_thuc=now + timedelta(days=2),
            dia_diem="Huế",
        )
        ActivityEvent.objects.create(
            ma_hd="EVSEARCH2", ten_hoat_dong="Hoạt động khác",
            loai_hd="WORKSHOP",
            thoi_gian_bat_dau=now + timedelta(days=3),
            thoi_gian_ket_thuc=now + timedelta(days=4),
            dia_diem="Huế",
        )
        self.client.force_authenticate(self.bcn)
        res_name = self.client.get("/api/v1/events/", {"search": "Docker"})
        ids_name = [e["id"] for e in res_name.data["data"]["items"]]
        self.assertEqual(len(ids_name), 1)

        res_code = self.client.get("/api/v1/events/", {"search": "EVSEARCH1"})
        ids_code = [e["id"] for e in res_code.data["data"]["items"]]
        self.assertEqual(len(ids_code), 1)

    def test_search_no_match_returns_empty(self):
        self.client.force_authenticate(self.bcn)
        res = self.client.get("/api/v1/events/", {"search": "zzz-khong-ton-tai"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["pagination"]["total_items"], 0)
