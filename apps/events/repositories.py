"""
Repository Layer — apps.events
==============================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion).

`EventService` / `EventTaskService` chỉ phụ thuộc vào trừu tượng `IEventRepository`,
không đụng trực tiếp vào ORM của `ActivityEvent` / `EventRegistration` /
`EventTask` / `EventBudgetDetail` / `EventCommunication`. 100% truy vấn dùng
Django ORM parameterized (TUYỆT ĐỐI không raw SQL — Security Hardening §2.1).

Lưu ý hiệu năng — giữ nguyên các tối ưu của bản trước khi refactor:
    - `list_events`           : annotate `active_reg_count` chống N+1.
    - `*_for_update`          : pessimistic lock `select_for_update`, BẮT BUỘC
                                gọi bên trong `transaction.atomic()` của service
                                (chống oversell / race condition — §5.3).
    - `list_registrations_*`  : select_related đúng quan hệ cần serialize.
    - `list_tasks_for_plan`   : select_related + prefetch_related cho DAG plan.
"""
from abc import ABC, abstractmethod
from typing import Iterable, Optional

from django.db.models import Count, Q, QuerySet, Sum

from apps.events.models import (
    ActivityEvent,
    EventBudgetDetail,
    EventCommunication,
    EventRegistration,
    EventTask,
)


class IEventRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Events — phụ thuộc trừu tượng (DIP)."""

    # ------------------------------------------------------------------
    # ActivityEvent (sự kiện)
    # ------------------------------------------------------------------
    @abstractmethod
    def list_events(
        self,
        *,
        trang_thai: Optional[str] = None,
        loai_hd: Optional[str] = None,
        sort: str = "-thoi_gian_bat_dau",
    ) -> QuerySet[ActivityEvent]:
        """Danh sách sự kiện kèm annotation `active_reg_count`; lọc + sắp xếp."""

    @abstractmethod
    def get_event_by_id(self, event_id: int) -> Optional[ActivityEvent]:
        """Lấy sự kiện theo id (None nếu không tồn tại)."""

    @abstractmethod
    def get_event_for_update(self, event_id: int) -> Optional[ActivityEvent]:
        """Lấy sự kiện theo id VỚI KHÓA BI (select_for_update) — chống oversell."""

    @abstractmethod
    def count_events_with_ma_hd_prefix(self, prefix: str) -> int:
        """Đếm sự kiện có mã hoạt động bắt đầu bằng `prefix` (sinh số thứ tự ma_hd)."""

    @abstractmethod
    def exists_ma_hd(self, ma_hd: str) -> bool:
        """Mã hoạt động đã tồn tại chưa (vòng lặp sinh ma_hd tăng seq nếu trùng)."""

    @abstractmethod
    def create_event(self, **fields) -> ActivityEvent:
        """Tạo một sự kiện mới (INSERT một dòng)."""

    # ------------------------------------------------------------------
    # EventRegistration (vé đăng ký)
    # ------------------------------------------------------------------
    @abstractmethod
    def list_registrations_by_member(self, member) -> QuerySet[EventRegistration]:
        """Vé của một thành viên (kèm event, mới nhất trước) — trang MyTickets."""

    @abstractmethod
    def list_registrations_by_event(self, event: ActivityEvent) -> QuerySet[EventRegistration]:
        """Vé của một sự kiện (kèm member+user, mới nhất trước) — BCN xem danh sách."""

    @abstractmethod
    def get_registration(self, event: ActivityEvent, member) -> Optional[EventRegistration]:
        """Vé của `member` tại `event` (None nếu chưa đăng ký — kiểm tra trùng)."""

    @abstractmethod
    def get_registration_for_update(self, event_id: int, member) -> Optional[EventRegistration]:
        """Vé của member VỚI KHÓA BI + kèm event (hủy vé an toàn dưới race)."""

    @abstractmethod
    def get_registration_by_ma_ve(
        self, event_id: int, ma_ve: str, for_update: bool = False
    ) -> Optional[EventRegistration]:
        """Tìm vé theo mã vé (quét QR tại cổng) — tùy chọn khóa BI."""

    @abstractmethod
    def count_active_registrations(self, event: ActivityEvent) -> int:
        """Số vé đang hiệu lực của sự kiện (loại trừ CANCELLED) — chặn oversell."""

    @abstractmethod
    def mark_registrations_checked_in(self, event_id: int, member) -> int:
        """Đổi trạng thái vé của member sang CHECKED_IN khi check-in (gọi từ apps.attendance)."""

    @abstractmethod
    def exists_ma_ve(self, ma_ve: str) -> bool:
        """Mã vé đã tồn tại chưa (vòng lặp sinh ma_ve đảm bảo unique)."""

    @abstractmethod
    def create_registration(self, **fields) -> EventRegistration:
        """Tạo bản ghi đăng ký vé mới."""

    # ------------------------------------------------------------------
    # EventBudgetDetail (dự trù kinh phí)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_budget_details(self, event: ActivityEvent) -> QuerySet[EventBudgetDetail]:
        """Danh sách hạng mục dự trù kinh phí của sự kiện."""

    @abstractmethod
    def create_budget_detail(self, event: ActivityEvent, **fields) -> EventBudgetDetail:
        """Thêm một hạng mục dự trù kinh phí cho sự kiện."""

    @abstractmethod
    def bulk_create_budget_details(
        self, event: ActivityEvent, items: Iterable[dict]
    ) -> list[EventBudgetDetail]:
        """Tạo hàng loạt hạng mục kinh phí (nested write khi tạo/cập nhật sự kiện)."""

    @abstractmethod
    def delete_budget_details(self, event: ActivityEvent) -> None:
        """Xóa TOÀN BỘ hạng mục kinh phí của sự kiện (replace khi update_event)."""

    @abstractmethod
    def sum_budget_total(self, event: ActivityEvent) -> int:
        """Tổng `so_tien` của các hạng mục kinh phí (0 nếu chưa có hạng mục nào)."""

    # ------------------------------------------------------------------
    # EventCommunication (kế hoạch truyền thông)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_communications(self, event: ActivityEvent) -> QuerySet[EventCommunication]:
        """Danh sách kênh truyền thông của sự kiện."""

    @abstractmethod
    def create_communication(self, **fields) -> EventCommunication:
        """Thêm một kênh truyền thông cho sự kiện."""

    # ------------------------------------------------------------------
    # EventTask (DAG)
    # ------------------------------------------------------------------
    @abstractmethod
    def get_task_by_id(self, task_id: int) -> Optional[EventTask]:
        """Lấy task theo id (kèm event để tránh N+1)."""

    @abstractmethod
    def get_task_for_update(self, task_id: int) -> Optional[EventTask]:
        """Lấy task theo id VỚI KHÓA BI + kèm event (đặt phụ thuộc dưới race)."""

    @abstractmethod
    def get_task_ids(self, event: ActivityEvent) -> list[int]:
        """Danh sách id các task của sự kiện (đầu vào của Kahn Topological Sort)."""

    @abstractmethod
    def list_tasks_for_plan(self, event: ActivityEvent) -> QuerySet[EventTask]:
        """Tasks của sự kiện kèm người phụ trách + tiền nhiệm, theo id tăng dần."""

    @abstractmethod
    def get_tasks_by_ids(self, ids: Iterable[int]) -> QuerySet[EventTask]:
        """Tasks theo danh sách id (pk__in — dùng cho M2M `depends_on.set`)."""

    @abstractmethod
    def create_task(self, **fields) -> EventTask:
        """Tạo một task mới cho sự kiện."""

    @abstractmethod
    def get_dependency_edges(self, event: ActivityEvent) -> list[tuple[int, int]]:
        """Cạnh phụ thuộc (task_trước, task_sau) của sự kiện từ bảng through M2M."""

    @abstractmethod
    def has_incomplete_dependencies(self, task: EventTask) -> bool:
        """Task còn TIỀN NHIỆM chưa hoàn thành (DAG — chặn complete khi vắt giáo)."""

    @abstractmethod
    def all_events(self) -> QuerySet[ActivityEvent]:
        """QuerySet toàn bộ sự kiện — dùng cho PrimaryKeyRelatedField của DRF."""

    @abstractmethod
    def member_is_assigned_to_any_task(self, event_id: int, member) -> bool:
        """Thành viên có được giao ÍT NHẤT MỘT task trong sự kiện không (xem DAG plan)."""

    @abstractmethod
    def member_has_active_registration(self, event_id: int, member) -> bool:
        """Thành viên có vé đang hiệu lực (khác CANCELLED) của sự kiện không (xem DAG plan)."""


class DjangoEventRepository(IEventRepository):
    """Triển khai cụ thể bằng Django ORM cho `IEventRepository`."""

    # ------------------------------------------------------------------
    # ActivityEvent (sự kiện)
    # ------------------------------------------------------------------
    def list_events(
        self,
        *,
        trang_thai: Optional[str] = None,
        loai_hd: Optional[str] = None,
        sort: str = "-thoi_gian_bat_dau",
    ) -> QuerySet[ActivityEvent]:
        """
        Danh sách sự kiện — annotate `active_reg_count` (số vé hiệu lực, không
        tính CANCELLED) chống N+1; lọc theo trạng thái/loại (giá trị None/rỗng
        bị bỏ qua); sắp xếp theo `sort` đã được whitelist ở view (Security §2.1).
        """
        queryset = ActivityEvent.objects.annotate(
            active_reg_count=Count(
                "registrations",
                filter=~Q(registrations__trang_thai=EventRegistration.TrangThai.CANCELLED),
            )
        )
        if trang_thai:
            queryset = queryset.filter(trang_thai=trang_thai)
        if loai_hd:
            queryset = queryset.filter(loai_hd=loai_hd)
        return queryset.order_by(sort)

    def get_event_by_id(self, event_id: int) -> Optional[ActivityEvent]:
        """Lấy sự kiện theo id — None nếu không tồn tại (service tự raise 404)."""
        return ActivityEvent.objects.filter(pk=event_id).first()

    def get_event_for_update(self, event_id: int) -> Optional[ActivityEvent]:
        """
        Lấy sự kiện theo id VỚI KHÓA BI (pessimistic locking).

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — chống race condition
        oversell khi 2 thành viên tranh vé cuối cùng đồng thời (Security §5.3).
        """
        return ActivityEvent.objects.select_for_update().filter(pk=event_id).first()

    def count_events_with_ma_hd_prefix(self, prefix: str) -> int:
        """Số sự kiện có mã bắt đầu bằng `prefix` (VD "EV2026") — sinh seq ma_hd."""
        return ActivityEvent.objects.filter(ma_hd__startswith=prefix).count()

    def exists_ma_hd(self, ma_hd: str) -> bool:
        """Mã hoạt động đã tồn tại chưa — vòng lặp sinh mã sẽ tăng seq nếu trùng."""
        return ActivityEvent.objects.filter(ma_hd=ma_hd).exists()

    def create_event(self, **fields) -> ActivityEvent:
        """Tạo sự kiện mới (INSERT một dòng duy nhất)."""
        return ActivityEvent.objects.create(**fields)

    # ------------------------------------------------------------------
    # EventRegistration (vé đăng ký)
    # ------------------------------------------------------------------
    def list_registrations_by_member(self, member) -> QuerySet[EventRegistration]:
        """Vé của thành viên — kèm `event` cho serializer QR, mới nhất trước."""
        return (
            EventRegistration.objects.filter(member=member)
            .select_related("event")
            .order_by("-created_at")
        )

    def list_registrations_by_event(self, event: ActivityEvent) -> QuerySet[EventRegistration]:
        """Vé của sự kiện — kèm `member__user` (chống N+1 PII), mới nhất trước."""
        return (
            EventRegistration.objects.filter(event=event)
            .select_related("member__user", "event")
            .order_by("-created_at")
        )

    def get_registration(self, event: ActivityEvent, member) -> Optional[EventRegistration]:
        """Vé của `member` tại `event` — None nếu chưa từng đăng ký."""
        return EventRegistration.objects.filter(event=event, member=member).first()

    def get_registration_by_ma_ve(
        self, event_id: int, ma_ve: str, for_update: bool = False
    ) -> Optional[EventRegistration]:
        """
        Tìm vé theo (event_id, ma_ve) — dùng khi BCN quét QR tại cổng
        (QA-Audit đợt 3 — TASK 3). Kèm `member` để trả tên ngay không N+1.

        with for_update=True: khóa BI dòng vé — 2 lần quét song song cùng mã
        vé phải tuần tự hóa, chỉ 1 lần được check-in.
        """
        qs = EventRegistration.objects.filter(event_id=event_id, ma_ve=ma_ve).select_related(
            "member", "event"
        )
        if for_update:
            qs = qs.select_for_update()
        return qs.first()

    def get_registration_for_update(self, event_id: int, member) -> Optional[EventRegistration]:
        """
        Vé của member theo event id VỚI KHÓA BI + kèm `event`.

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — 2 request hủy vé
        cùng lúc phải tuần tự hóa (Security §5.3).
        """
        return (
            EventRegistration.objects.select_for_update()
            .select_related("event")
            .filter(event_id=event_id, member=member)
            .first()
        )

    def count_active_registrations(self, event: ActivityEvent) -> int:
        """Số vé hiệu lực (khác CANCELLED) — so với `so_luong_toi_da` chặn oversell."""
        return EventRegistration.objects.filter(event=event).exclude(
            trang_thai=EventRegistration.TrangThai.CANCELLED
        ).count()

    def mark_registrations_checked_in(self, event_id: int, member) -> int:
        """Đổi trạng thái vé của member sang CHECKED_IN khi check-in (gọi từ apps.attendance)."""
        from apps.events.models import EventRegistration  # noqa: PLC0415

        return EventRegistration.objects.filter(
            event_id=event_id, member=member
        ).update(trang_thai=EventRegistration.TrangThai.CHECKED_IN)

    def exists_ma_ve(self, ma_ve: str) -> bool:
        """Mã vé đã tồn tại chưa — vòng lặp sinh mã vé sẽ random lại nếu trùng."""
        return EventRegistration.objects.filter(ma_ve=ma_ve).exists()

    def create_registration(self, **fields) -> EventRegistration:
        """Tạo bản ghi đăng ký vé (mã vé QR do frontend render)."""
        return EventRegistration.objects.create(**fields)

    # ------------------------------------------------------------------
    # EventBudgetDetail (dự trù kinh phí)
    # ------------------------------------------------------------------
    def get_budget_details(self, event: ActivityEvent) -> QuerySet[EventBudgetDetail]:
        """Hạng mục kinh phí của sự kiện (thứ tự theo Meta.ordering: event, id)."""
        return EventBudgetDetail.objects.filter(event=event)

    def create_budget_detail(self, event: ActivityEvent, **fields) -> EventBudgetDetail:
        """Thêm một hạng mục kinh phí cho sự kiện."""
        return EventBudgetDetail.objects.create(event=event, **fields)

    def bulk_create_budget_details(
        self, event: ActivityEvent, items: Iterable[dict]
    ) -> list[EventBudgetDetail]:
        """Tạo hàng loạt hạng mục kinh phí — nested write của tạo/cập nhật sự kiện."""
        return EventBudgetDetail.objects.bulk_create(
            [
                EventBudgetDetail(
                    event=event,
                    ten_hang_muc=item["ten_hang_muc"],
                    so_tien=item["so_tien"],
                    ghi_chu=item.get("ghi_chu", ""),
                )
                for item in items
            ]
        )

    def delete_budget_details(self, event: ActivityEvent) -> None:
        """Xóa toàn bộ hạng mục kinh phí (khi update_event thay thế danh sách mới)."""
        EventBudgetDetail.objects.filter(event=event).delete()

    def sum_budget_total(self, event: ActivityEvent) -> int:
        """Tổng số tiền dự trù — 0 khi sự kiện chưa có hạng mục nào."""
        return EventBudgetDetail.objects.filter(event=event).aggregate(
            total=Sum("so_tien")
        )["total"] or 0

    # ------------------------------------------------------------------
    # EventCommunication (kế hoạch truyền thông)
    # ------------------------------------------------------------------
    def get_communications(self, event: ActivityEvent) -> QuerySet[EventCommunication]:
        """Kênh truyền thông của sự kiện (thứ tự theo Meta.ordering)."""
        return EventCommunication.objects.filter(event=event)

    def create_communication(self, **fields) -> EventCommunication:
        """Thêm một kênh truyền thông (event_id đã được kiểm tra ở view/service)."""
        return EventCommunication.objects.create(**fields)

    # ------------------------------------------------------------------
    # EventTask (DAG)
    # ------------------------------------------------------------------
    def get_task_by_id(self, task_id: int) -> Optional[EventTask]:
        """Lấy task theo id — kèm `event` tránh N+1 khi serialize/validate."""
        return EventTask.objects.select_related("event").filter(pk=task_id).first()

    def get_task_for_update(self, task_id: int) -> Optional[EventTask]:
        """
        Lấy task theo id VỚI KHÓA BI + kèm `event`.

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — đặt phụ thuộc (M2M)
        phải tuần tự hóa để DAG validation không bị race (Security §5.3).
        """
        return (
            EventTask.objects.select_for_update()
            .select_related("event")
            .filter(pk=task_id)
            .first()
        )

    def get_task_ids(self, event: ActivityEvent) -> list[int]:
        """Id các task của sự kiện — tập đỉnh của đồ thị DAG."""
        return list(EventTask.objects.filter(event=event).values_list("id", flat=True))

    def list_tasks_for_plan(self, event: ActivityEvent) -> QuerySet[EventTask]:
        """
        Tasks của sự kiện phục vụ execution plan: kèm người phụ trách
        (select_related) + tiền nhiệm (prefetch_related), thứ tự id tăng dần.
        """
        return (
            EventTask.objects.filter(event=event)
            .select_related("nguoi_phu_trach")
            .prefetch_related("depends_on")
            .order_by("id")
        )

    def get_tasks_by_ids(self, ids: Iterable[int]) -> QuerySet[EventTask]:
        """
        Tasks theo danh sách id (dùng cho `task.depends_on.set(...)`).

        Danh sách rỗng → queryset rỗng (`.set()` sẽ xóa sạch phụ thuộc —
        giữ nguyên ngữ cảnh của bản trước refactor).
        """
        return EventTask.objects.filter(pk__in=list(ids))

    def create_task(self, **fields) -> EventTask:
        """Tạo task mới (INSERT một dòng — M2M depends_on do service `.set()`)."""
        return EventTask.objects.create(**fields)

    def get_dependency_edges(self, event: ActivityEvent) -> list[tuple[int, int]]:
        """
        Danh sách cạnh (task_trước, task_sau) của sự kiện.

        M2M `depends_on`: task A depends_on B nghĩa là B phải xong trước A
        → cạnh (B → A) = (to_eventtask, from_eventtask) trong bảng through.
        """
        return list(
            EventTask.depends_on.through.objects.filter(
                from_eventtask__event_id=event.pk
            ).values_list("to_eventtask_id", "from_eventtask_id")
        )

    def has_incomplete_dependencies(self, task: EventTask) -> bool:
        """
        Kiểm tra task còn TIỀN NHIỆM chưa hoàn thành hay không.

        Ràng buộc DAG khi hoàn thành: một task chỉ được tích "đã xong" khi
        TOÀN BỘ task mà nó depends_on đã hoàn thành trước đó (QA-Audit P1-1
        — trước đây service chỉ validate chu trình khi tạo, không chặn
        complete khi tiền nhiệm còn tồn). Query EXISTS — không đụng hàng loạt
        dòng, chỉ trả True/False.
        """
        return task.depends_on.exclude(is_completed=True).exists()

    def all_events(self) -> QuerySet[ActivityEvent]:
        """QuerySet toàn bộ sự kiện — serializer khai báo PrimaryKeyRelatedField
        cần queryset để validate pk (ORM CHỈ nằm ở repository — QA-Audit P3)."""
        return ActivityEvent.objects.all()

    def member_is_assigned_to_any_task(self, event_id: int, member) -> bool:
        """EXISTS: thành viên được giao task nào đó của sự kiện (EventTask.nguoi_phu_trach)."""
        return EventTask.objects.filter(
            event_id=event_id, nguoi_phu_trach=member
        ).exists()

    def member_has_active_registration(self, event_id: int, member) -> bool:
        """EXISTS: vé đang hiệu lực (khác CANCELLED) của thành viên tại sự kiện."""
        return EventRegistration.objects.filter(
            event_id=event_id, member=member
        ).exclude(
            trang_thai=EventRegistration.TrangThai.CANCELLED
        ).exists()
