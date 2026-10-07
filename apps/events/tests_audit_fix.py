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
from unittest import skipIf

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.models import User
from apps.events.models import ActivityEvent, EventTask
from apps.common.exceptions import ValidationException
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

        with self.assertRaises(ValidationException) as ctx:
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

        with self.assertRaises(ValidationException):
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
        with self.assertRaises(ValidationException):
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


# ======================================================================
# R01 (QA review 69db15d — P1): bất biến DAG phải giữ ở MỌI mutation
# ======================================================================
@override_settings(AXES_ENABLED=False)
class ReviewR01DagSetDependenciesTests(EventTestBase):
    """
    R01 — `set_dependencies` chỉ kiểm tra chu trình, chưa chặn "task COMPLETED
    nhận TIỀN NHIỆM chưa hoàn thành". Bất biến: "task đã hoàn thành thì mọi
    tiền nhiệm của nó cũng đã hoàn thành" phải giữ cả khi THAY PHỤ THUỘC.
    """

    @staticmethod
    def _make(event, ten: str, completed: bool) -> EventTask:
        return EventTask.objects.create(event=event, ten_task=ten, is_completed=completed)

    def test_r01_completed_task_add_incomplete_prereq_blocked(self):
        """Probe của review: B completed nhận tiền nhiệm A incomplete → chặn."""
        event = self.make_event()
        a = self._make(event, "A", completed=False)
        b = self._make(event, "B", completed=True)
        with self.assertRaises(ValidationException):
            EventTaskService.set_dependencies(b.id, [a.id])

    def test_r01_blocked_set_preserves_task_state(self):
        """Chặn xong: B giữ nguyên completed + phụ thuộc cũ KHÔNG bị xóa."""
        event = self.make_event()
        a = self._make(event, "A", completed=False)
        b = self._make(event, "B", completed=True)
        c = self._make(event, "C", completed=True)
        b.depends_on.set([c])

        with self.assertRaises(ValidationException):
            EventTaskService.set_dependencies(b.id, [a.id])

        b.refresh_from_db()
        self.assertTrue(b.is_completed)
        self.assertEqual(
            sorted(b.depends_on.values_list("id", flat=True)), [c.id],
            "Phụ thuộc cũ phải được bảo toàn khi set_dependencies bị chặn.",
        )
        a.refresh_from_db()
        self.assertFalse(a.is_completed)

    def test_r01_completed_task_all_prereqs_completed_ok(self):
        """B completed + toàn bộ tiền nhiệm completed → set hợp lệ."""
        event = self.make_event()
        a = self._make(event, "A", completed=True)
        b = self._make(event, "B", completed=True)
        task = EventTaskService.set_dependencies(b.id, [a.id])
        self.assertEqual(sorted(task.depends_on.values_list("id", flat=True)), [a.id])

    def test_r01_mixed_prereqs_blocked_and_lists_incomplete(self):
        """Danh sách trộn completed + incomplete → chặn, errors nêu đúng id."""
        event = self.make_event()
        done = self._make(event, "DONE", completed=True)
        pending = self._make(event, "PENDING", completed=False)
        b = self._make(event, "B", completed=True)
        with self.assertRaises(ValidationException) as ctx:
            EventTaskService.set_dependencies(b.id, [done.id, pending.id])
        errors = ctx.exception.errors or {}
        self.assertIn(pending.id, [t["id"] for t in errors.get("depends_on", [])])

    def test_r01_incomplete_task_accepts_incomplete_prereq(self):
        """Task chưa hoàn thành nhận tiền nhiệm chưa hoàn thành — hợp lệ."""
        event = self.make_event()
        a = self._make(event, "A", completed=False)
        b = self._make(event, "B", completed=False)
        task = EventTaskService.set_dependencies(b.id, [a.id])
        self.assertEqual(sorted(task.depends_on.values_list("id", flat=True)), [a.id])

    def test_r01_replace_incomplete_prereq_of_completed_task_with_completed_ok(self):
        """B completed đang treo tiền nhiệm incomplete (dữ liệu cũ) → có thể
        tự sửa lại bằng set_dependencies với tiền nhiệm completed."""
        event = self.make_event()
        done = self._make(event, "DONE", completed=True)
        b = self._make(event, "B", completed=True)
        stale = self._make(event, "STALE", completed=False)
        b.depends_on.set([stale])
        task = EventTaskService.set_dependencies(b.id, [done.id])
        self.assertEqual(sorted(task.depends_on.values_list("id", flat=True)), [done.id])


# ======================================================================
# R01 — race reopen(TIỀN NHIỆM) × complete(HẬU NHIỆM): phải tuần tự hóa
# ======================================================================
@override_settings(AXES_ENABLED=False)
class ReviewR01GraphConcurrencyTests(TransactionTestCase):
    """
    Trước fix R01: `reopen_task` đọc descendants rồi save NGOÀI transaction
    chung, `complete_task` chỉ khóa task đích — hai thread (reopen A) ×
    (complete B với B depends_on A) có thể đọc chéo snapshot cũ và CÙNG
    commit → A incomplete nhưng B completed (phá bất biến).

    Sau fix: cả hai mutation khóa hàng SỰ KIỆN trước (thứ tự event → task)
    → tuần tự. Kết quả khả dĩ: (1) complete B thắng → reopen A bị chặn do
    B completed; (2) reopen A thắng → complete B bị chặn do A chưa xong.
    Cả hai nhánh đều giữ bất biến — test assert bất biến sau khi cả hai
    thread kết thúc, KHÔNG assert thread nào thắng (không deterministic).
    """

    databases = {"default"}

    @staticmethod
    def _make_event() -> ActivityEvent:
        now = timezone.now()
        return ActivityEvent.objects.create(
            ma_hd=f"EVR01{uuid.uuid4().hex[:8].upper()}",
            ten_hoat_dong="Race DAG",
            loai_hd="WORKSHOP",
            thoi_gian_bat_dau=now + timedelta(days=1),
            thoi_gian_ket_thuc=now + timedelta(days=2),
            dia_diem="Huế",
        )

    @skipIf(
        connection.vendor == "sqlite",
        "SQLite khóa toàn bảng khi 2 connection cùng ghi — race test chỉ chạy "
        "đúng ý trên MySQL/MariaDB/PostgreSQL (CSDL chính của dự án là MySQL).",
    )
    def test_r01_reopen_prereq_vs_complete_descendant_serialized(self):
        from threading import Barrier, Thread

        from django.db import connections

        event = self._make_event()
        a = EventTask.objects.create(event=event, ten_task="A", is_completed=True)
        b = EventTask.objects.create(event=event, ten_task="B", is_completed=False)
        b.depends_on.set([a])

        barrier = Barrier(2)
        outcomes: list[str] = []

        def do_reopen() -> None:
            try:
                task = EventTaskService.get_task_or_404(a.id)
                barrier.wait(timeout=15)
                EventTaskService.reopen_task(task)
                outcomes.append("reopen-ok")
            except ValidationException:
                outcomes.append("reopen-blocked")
            except Exception as exc:  # pragma: no cover — chỉ để lộ lỗi bất ngờ
                outcomes.append(f"reopen-unexpected:{exc!r}")
            finally:
                connections.close_all()

        def do_complete() -> None:
            try:
                barrier.wait(timeout=15)
                EventTaskService.complete_task(b.id)
                outcomes.append("complete-ok")
            except ValidationException:
                outcomes.append("complete-blocked")
            except Exception as exc:  # pragma: no cover
                outcomes.append(f"complete-unexpected:{exc!r}")
            finally:
                connections.close_all()

        threads = [Thread(target=do_reopen), Thread(target=do_complete)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        a.refresh_from_db()
        b.refresh_from_db()

        # Không thread nào crash ngoài dự kiến
        self.assertFalse(
            [o for o in outcomes if "unexpected" in o],
            f"Có exception bất ngờ: {outcomes}",
        )
        # BẤT BIẾN sau commit: B completed ⇒ A completed
        self.assertFalse(
            b.is_completed and not a.is_completed,
            f"Bất biến DAG bị phá bởi race! a={a.is_completed}, b={b.is_completed}, outcomes={outcomes}",
        )
        # Tuần tự hóa → ĐÚNG MỘT trong hai pattern hợp lệ:
        #   (a) reopen thắng: A incomplete → complete B bị chặn (còn tiền nhiệm)
        #   (b) complete thắng: B completed → reopen A bị chặn (hậu nhiệm done)
        pattern_a = outcomes == ["reopen-ok", "complete-blocked"] or set(outcomes) == {
            "reopen-ok",
            "complete-blocked",
        }
        pattern_b = set(outcomes) == {"complete-ok", "reopen-blocked"}
        self.assertTrue(
            pattern_a or pattern_b,
            f"Outcome không hợp lệ (phá bất biến hoặc lỗi): {outcomes}",
        )
