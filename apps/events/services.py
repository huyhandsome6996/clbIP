"""
Services — 100% nghiệp vụ Events (Clean Layered Architecture).
==============================================================
Views CHỈ là Controller; toàn bộ logic nằm ở đây:

- EventService:    CRUD sự kiện + đăng ký vé (transaction + select_for_update
                   chống Race Condition / oversell — Security Hardening §5.3).
- EventTaskService: Quản lý task sự kiện theo đồ thị DAG (DSA 4 — Kahn
                   Topological Sort), chặn phụ thuộc vòng tròn (deadlock).

Cả hai service KHÔNG đụng trực tiếp vào ORM — toàn bộ truy vấn đi qua
`IEventRepository` (Repository Pattern — Dependency Inversion, xem
apps/events/repositories.py; pattern DI giống `FundService`).
"""
import logging
from typing import Any, ClassVar, Optional

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.common.exceptions import (
    CycleDetectedException,
    DuplicateRegistrationException,
    EventFullException,
    EventStatusException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from apps.authentication.models import User
from apps.events.models import ActivityEvent, EventBudgetDetail, EventCommunication, EventRegistration, EventTask
from apps.events.repositories import DjangoEventRepository, IEventRepository
from apps.members.models import MemberProfile
from apps.members.repositories import DjangoMemberRepository, IMemberRepository
from core.algorithms.dag_workflow import TaskDependencyEngine

logger = logging.getLogger(__name__)

# Bảng chữ sinh mã vé — loại bỏ I/1, O/0 dễ gây nhầm lẫn khi đọc/scan QR
TICKET_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class EventService:
    """Nghiệp vụ sự kiện: tạo/cập nhật + đăng ký vé chống oversell."""

    # DI repository (funds-style) — cho phép swap khi unit test
    _repository_class: ClassVar[type[IEventRepository]] = DjangoEventRepository
    _member_repository_class: ClassVar[type[IMemberRepository]] = DjangoMemberRepository

    @classmethod
    def _repo(cls) -> IEventRepository:
        """Factory method cho repository sự kiện — cho phép DI khi unit test."""
        return cls._repository_class()

    @classmethod
    def _member_repo(cls) -> IMemberRepository:
        """Factory method cho repository thành viên (tra cứu chéo apps.members)."""
        return cls._member_repository_class()

    # ------------------------------------------------------------------
    # Sinh mã tự động
    # ------------------------------------------------------------------
    @classmethod
    def _generate_ma_hd(cls) -> str:
        """
        Sinh mã hoạt động tự động: "EV" + năm + số thứ tự 3 chữ số.
        VD: EV2026001. Vòng while đảm bảo unique khi nhiều sự kiện cùng năm.
        """
        prefix = f"EV{timezone.now().year}"
        seq = cls._repo().count_events_with_ma_hd_prefix(prefix)
        candidate = f"{prefix}{seq + 1:03d}"
        while cls._repo().exists_ma_hd(candidate):
            seq += 1
            candidate = f"{prefix}{seq + 1:03d}"
        return candidate

    @classmethod
    def _generate_ma_ve(cls) -> str:
        """Sinh mã vé điện tử "VE-" + 12 ký tự ngẫu nhiên (không chứa I/1, O/0)."""
        ma_ve = f"VE-{get_random_string(length=12, allowed_chars=TICKET_CODE_CHARS)}"
        while cls._repo().exists_ma_ve(ma_ve):
            ma_ve = f"VE-{get_random_string(length=12, allowed_chars=TICKET_CODE_CHARS)}"
        return ma_ve

    # ------------------------------------------------------------------
    # Validate thời gian
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_time_range(start: Any, end: Any) -> None:
        """Thời gian bắt đầu BẮT BUỘC trước thời gian kết thúc."""
        if start and end and start >= end:
            raise ValidationException(
                "Thời gian bắt đầu phải sớm hơn thời gian kết thúc.",
                errors={"thoi_gian": "thoi_gian_bat_dau >= thoi_gian_ket_thuc"},
            )

    # ------------------------------------------------------------------
    # Tạo / Cập nhật sự kiện
    # ------------------------------------------------------------------
    @classmethod
    def create_event(cls, data: dict, actor: User) -> ActivityEvent:
        """
        Tạo sự kiện mới.

        Args:
            data: validated_data từ ActivityEventCreateUpdateSerializer.
                  Có thể chứa "budget_details" (nested) — tổng kinh phí
                  dự trù sẽ tự động = tổng các hạng mục.
            actor: User BCN/ADMIN thực hiện tạo.

        Returns:
            ActivityEvent vừa tạo (đã có ma_hd tự sinh).
        """
        data = dict(data)
        budget_items: Optional[list] = data.pop("budget_details", None)

        cls._validate_time_range(data.get("thoi_gian_bat_dau"), data.get("thoi_gian_ket_thuc"))

        with transaction.atomic():
            event = cls._repo().create_event(
                ma_hd=cls._generate_ma_hd(),
                created_by=actor,
                **data,
            )
            if budget_items:
                cls._repo().bulk_create_budget_details(event, budget_items)
                event.tong_kinh_phi_du_tru = sum(item["so_tien"] for item in budget_items)
                event.save(update_fields=["tong_kinh_phi_du_tru", "updated_at"])

        logger.info("Event %s (%s) tạo bởi %s", event.ma_hd, event.id, actor)
        return event

    @classmethod
    def update_event(cls, event: ActivityEvent, data: dict) -> ActivityEvent:
        """
        Cập nhật sự kiện (partial hoặc full).

        Nếu data chứa "budget_details" → thay thế toàn bộ hạng mục cũ
        và tính lại tổng kinh phí dự trù.
        """
        data = dict(data)
        budget_items: Optional[list] = data.pop("budget_details", None)

        cls._validate_time_range(
            data.get("thoi_gian_bat_dau", event.thoi_gian_bat_dau),
            data.get("thoi_gian_ket_thuc", event.thoi_gian_ket_thuc),
        )

        with transaction.atomic():
            for field, value in data.items():
                setattr(event, field, value)
            if budget_items is not None:
                cls._repo().delete_budget_details(event)
                cls._repo().bulk_create_budget_details(event, budget_items)
                event.tong_kinh_phi_du_tru = sum(item["so_tien"] for item in budget_items)
            event.save()

        logger.info("Event %s cập nhật: %s", event.ma_hd, list(data.keys()))
        return event

    # ------------------------------------------------------------------
    # Đăng ký vé — chống Race Condition (Security Hardening §5.3)
    # ------------------------------------------------------------------
    @classmethod
    def register_member(cls, event_id: int, member: MemberProfile) -> EventRegistration:
        """
        Đăng ký vé sự kiện cho thành viên — PESSIMISTIC LOCK chặn oversell
        khi 2 người tranh vé cuối cùng (select_for_update trên ActivityEvent).

        Quy trình:
            1. atomic + khóa bi sự kiện.
            2. Sự kiện phải ở trạng thái OPEN_REGISTRATION.
            3. Đăng ký trùng (đang REGISTERED/APPROVED/...) → 409.
            4. active_count >= so_luong_toi_da → EventFullException.
            5. Sinh ma_ve "VE-XXXXXXXXXXXX" (không chứa I/1, O/0).
            6. Tạo bản ghi REGISTERED. Hủy vé cũ (CANCELLED) → đăng ký lại
               dùng lại dòng cũ (ràng buộc unique event+member).

        Returns:
            EventRegistration với mã vé điện tử.
        """
        with transaction.atomic():
            event = cls._repo().get_event_for_update(event_id)
            if event is None:
                raise NotFoundException("Không tìm thấy sự kiện.")

            if event.trang_thai != ActivityEvent.TrangThai.OPEN_REGISTRATION:
                raise EventStatusException("Sự kiện chưa mở đăng ký.")

            existing = cls._repo().get_registration(event, member)
            # Vé đã hủy (CANCELLED) không tính là trùng — cho phép đăng ký lại
            if existing is not None and existing.trang_thai != EventRegistration.TrangThai.CANCELLED:
                raise DuplicateRegistrationException()

            active_count = cls._repo().count_active_registrations(event)
            if active_count >= event.so_luong_toi_da:
                raise EventFullException()

            if existing is not None:
                # Đăng ký lại sau khi hủy — tái sử dụng dòng (unique event+member)
                existing.ma_ve = cls._generate_ma_ve()
                existing.trang_thai = EventRegistration.TrangThai.REGISTERED
                existing.save(update_fields=["ma_ve", "trang_thai", "updated_at"])
                registration = existing
            else:
                registration = cls._repo().create_registration(
                    event=event,
                    member=member,
                    ma_ve=cls._generate_ma_ve(),
                    trang_thai=EventRegistration.TrangThai.REGISTERED,
                )

        logger.info(
            "Member %s đăng ký event %s — vé %s", member.id, event.ma_hd, registration.ma_ve
        )
        return registration

    @classmethod
    def cancel_registration(cls, event_id: int, member: MemberProfile) -> EventRegistration:
        """
        Hủy vé của chính thành viên → trạng thái CANCELLED, giải phóng chỗ
        cho người khác đăng ký.
        """
        with transaction.atomic():
            registration = cls._repo().get_registration_for_update(event_id, member)
            if registration is None:
                raise NotFoundException("Bạn chưa đăng ký sự kiện này.")

            if registration.trang_thai == EventRegistration.TrangThai.CANCELLED:
                raise ValidationException("Vé này đã bị hủy trước đó.")

            registration.trang_thai = EventRegistration.TrangThai.CANCELLED
            registration.save(update_fields=["trang_thai", "updated_at"])

        logger.info(
            "Member %s hủy vé %s — chỗ được giải phóng", member.id, registration.ma_ve
        )
        return registration

    # ------------------------------------------------------------------
    # Tra cứu
    # ------------------------------------------------------------------
    @classmethod
    def get_event_or_404(cls, event_id: int) -> ActivityEvent:
        """Lấy sự kiện theo id, không thấy → NotFoundException (404 envelope)."""
        event = cls._repo().get_event_by_id(event_id)
        if event is None:
            raise NotFoundException("Không tìm thấy sự kiện.")
        return event

    @classmethod
    def get_member_profile_or_forbidden(cls, user: User) -> MemberProfile:
        """User phải gắn với hồ sơ thành viên mới được đăng ký vé (repo apps.members)."""
        profile = cls._member_repo().get_by_user(user)
        if profile is None:
            raise ForbiddenException("Chỉ thành viên CLB mới đăng ký được.")
        return profile

    # ------------------------------------------------------------------
    # Danh sách (view mỏng gọi — trả QuerySet cho serializer paginate)
    # ------------------------------------------------------------------
    @classmethod
    def list_events(
        cls,
        trang_thai: Optional[str] = None,
        loai_hd: Optional[str] = None,
        sort: str = "-thoi_gian_bat_dau",
    ) -> QuerySet[ActivityEvent]:
        """
        Danh sách sự kiện kèm annotation `active_reg_count` (chống N+1).

        `trang_thai` / `loai_hd` đã được view validate theo choices, `sort`
        đã được view ràng buộc whitelist EVENT_SORT_WHITELIST (Security §2.1).
        """
        return cls._repo().list_events(trang_thai=trang_thai, loai_hd=loai_hd, sort=sort)

    @classmethod
    def list_tickets_for_member(cls, member: MemberProfile) -> QuerySet[EventRegistration]:
        """Vé điện tử của một thành viên (mới nhất trước) — MyTicketsView."""
        return cls._repo().list_registrations_by_member(member)

    @classmethod
    def list_registrations(cls, event: ActivityEvent) -> QuerySet[EventRegistration]:
        """Danh sách vé của sự kiện (mới nhất trước) — BCN/ADMIN xem."""
        return cls._repo().list_registrations_by_event(event)

    @classmethod
    def list_budget_details(cls, event: ActivityEvent) -> QuerySet[EventBudgetDetail]:
        """Hạng mục dự trù kinh phí của sự kiện."""
        return cls._repo().get_budget_details(event)

    @classmethod
    def list_communications(cls, event: ActivityEvent) -> QuerySet[EventCommunication]:
        """Kế hoạch truyền thông đa kênh của sự kiện."""
        return cls._repo().get_communications(event)

    # ------------------------------------------------------------------
    # Ghi nhanh từ view (business op đã được tách khỏi controller)
    # ------------------------------------------------------------------
    @classmethod
    def add_budget_item(
        cls, event: ActivityEvent, data: dict
    ) -> tuple[EventBudgetDetail, ActivityEvent]:
        """
        Thêm hạng mục dự trù kinh phí rồi TỰ ĐỘNG tính lại
        `tong_kinh_phi_du_tru` = tổng các hạng mục.

        Ghi chú: `event` phải đã được kiểm tra tồn tại (404) ở view TRƯỚC khi
        validate payload — giữ nguyên thứ tự lỗi 404 → 400 như bản cũ.
        """
        with transaction.atomic():
            item = cls._repo().create_budget_detail(event, **data)
            # Tự động tính lại tổng kinh phí dự trù
            event.tong_kinh_phi_du_tru = cls._repo().sum_budget_total(event)
            event.save(update_fields=["tong_kinh_phi_du_tru", "updated_at"])
        return item, event

    @classmethod
    def add_communication(cls, event_id: int, data: dict) -> EventCommunication:
        """
        Thêm kế hoạch truyền thông cho sự kiện.

        Ghi chú: sự kiện đã được kiểm tra tồn tại (404) ở view trước khi
        validate payload — giữ nguyên thứ tự lỗi 404 → 400 như bản cũ.
        """
        with transaction.atomic():
            return cls._repo().create_communication(event_id=event_id, **data)


class EventTaskService:
    """
    Nghiệp vụ task sự kiện theo đồ thị DAG (DSA 4 — TaskDependencyEngine).

    Mọi thao tác thay đổi phụ thuộc đều validate DAG TRƯỚC KHI COMMIT:
    nếu phát hiện chu trình → raise CycleDetectedException → rollback toàn bộ
    (kỹ thuật "tạo trong transaction, validate, cycle → raise để rollback").
    """

    # DI repository (funds-style) — cho phép swap khi unit test
    _repository_class: ClassVar[type[IEventRepository]] = DjangoEventRepository

    @classmethod
    def _repo(cls) -> IEventRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # ------------------------------------------------------------------
    # Đọc đồ thị phụ thuộc
    # ------------------------------------------------------------------
    @classmethod
    def _dependency_edges(cls, event: ActivityEvent) -> list[tuple[int, int]]:
        """
        Trả về danh sách cạnh (task_trước, task_sau) của sự kiện.

        M2M `depends_on`: task A depends_on B nghĩa là B phải xong trước A
        → cạnh (B → A) = (to_eventtask, from_eventtask) trong bảng through.
        """
        return cls._repo().get_dependency_edges(event)

    @classmethod
    def _get_event_or_404(cls, event_id: int) -> ActivityEvent:
        event = cls._repo().get_event_by_id(event_id)
        if event is None:
            raise NotFoundException("Không tìm thấy sự kiện.")
        return event

    @classmethod
    def get_task_or_404(cls, task_id: int, event_id: Optional[int] = None) -> EventTask:
        """Lấy task theo id (tuỳ chọn kiểm tra thuộc đúng sự kiện)."""
        task = cls._get_task_or_404(task_id)
        if event_id is not None and task.event_id != event_id:
            raise NotFoundException("Task không thuộc sự kiện này.")
        return task

    @classmethod
    def _get_task_or_404(cls, task_id: int) -> EventTask:
        task = cls._repo().get_task_by_id(task_id)
        if task is None:
            raise NotFoundException("Không tìm thấy task.")
        return task

    @classmethod
    def _validate_depends_ids(cls, event: ActivityEvent, depends_on_ids: list[int]) -> None:
        """Mọi task phụ thuộc phải thuộc CÙNG sự kiện."""
        if not depends_on_ids:
            return
        valid_ids = set(cls._repo().get_task_ids(event))
        invalid = [tid for tid in depends_on_ids if tid not in valid_ids]
        if invalid:
            raise ValidationException(
                "Task phụ thuộc không hợp lệ (không thuộc sự kiện này hoặc không tồn tại).",
                errors={"depends_on": invalid},
            )

    # ------------------------------------------------------------------
    # Tạo task — validate DAG trước khi commit
    # ------------------------------------------------------------------
    @classmethod
    def create_task(
        cls,
        event_id: int,
        ten_task: str,
        nguoi_phu_trach_id: Optional[int] = None,
        depends_on_ids: Optional[list[int]] = None,
        deadline=None,
    ) -> EventTask:
        """
        Tạo task mới cho sự kiện rồi set M2M depends_on; sau đó validate DAG
        toàn sự kiện. Nếu phát hiện chu trình → raise trong atomic → ROLLBACK
        toàn bộ (task vừa tạo không còn tồn tại).
        """
        depends_on_ids = list(depends_on_ids or [])
        with transaction.atomic():
            event = cls._get_event_or_404(event_id)
            cls._validate_depends_ids(event, depends_on_ids)

            task = cls._repo().create_task(
                event=event,
                ten_task=ten_task,
                nguoi_phu_trach_id=nguoi_phu_trach_id,
                deadline=deadline,
            )
            if depends_on_ids:
                task.depends_on.set(cls._repo().get_tasks_by_ids(depends_on_ids))

            # Validate DAG trên dữ liệu đã ghi (chưa commit)
            task_ids = cls._repo().get_task_ids(event)
            edges = cls._dependency_edges(event)
            is_valid, _order = TaskDependencyEngine.resolve_task_order(task_ids, edges)
            if not is_valid:
                cycle = TaskDependencyEngine.find_cycle(task_ids, edges)
                logger.warning("Tạo task %s gây chu trình: %s → rollback", ten_task, cycle)
                raise CycleDetectedException(errors={"cycle": cycle})

        return task

    # ------------------------------------------------------------------
    # Đặt phụ thuộc — validate trên dữ liệu GIẢ LẬP trước khi commit
    # ------------------------------------------------------------------
    @classmethod
    def set_dependencies(cls, task_id: int, depends_on_ids: list[int]) -> EventTask:
        """
        Thay toàn bộ phụ thuộc của task bằng danh sách mới.

        Validate trên dữ liệu GIẢ LẬP (edges hiện tại − edges cũ của task
        + edges mới) trước khi ghi — chặn deadlock proactive.
        """
        depends_on_ids = list(depends_on_ids or [])
        with transaction.atomic():
            task = cls._repo().get_task_for_update(task_id)
            if task is None:
                raise NotFoundException("Không tìm thấy task.")
            event = task.event
            cls._validate_depends_ids(event, depends_on_ids)

            task_ids = cls._repo().get_task_ids(event)
            # Giả lập: bỏ các cạnh cũ trỏ VÀO task, thêm cạnh mới (dep → task)
            simulated_edges = [
                (u, v) for (u, v) in cls._dependency_edges(event) if v != task.pk
            ] + [(dep_id, task.pk) for dep_id in depends_on_ids]

            is_valid, _order = TaskDependencyEngine.resolve_task_order(task_ids, simulated_edges)
            if not is_valid:
                cycle = TaskDependencyEngine.find_cycle(task_ids, simulated_edges)
                logger.warning(
                    "set_dependencies task %s gây chu trình: %s → từ chối", task_id, cycle
                )
                raise CycleDetectedException(errors={"cycle": cycle})

            task.depends_on.set(cls._repo().get_tasks_by_ids(depends_on_ids))

        return task

    # ------------------------------------------------------------------
    # Kế hoạch thực thi (DAG overview)
    # ------------------------------------------------------------------
    @classmethod
    def get_execution_plan(cls, event_id: int) -> dict:
        """
        Trả về kế hoạch thực thi task của sự kiện:
            - tasks: danh sách task (đã serialize).
            - is_valid_dag / topological_order / cycle.
            - executable_now: task có thể bắt đầu NGAY (tiền nhiệm đã xong).
        """
        from apps.events.serializers import EventTaskSerializer  # import cục bộ tránh vòng

        event = cls._get_event_or_404(event_id)
        tasks = list(cls._repo().list_tasks_for_plan(event))
        task_ids = [t.id for t in tasks]
        edges = cls._dependency_edges(event)

        is_valid, order = TaskDependencyEngine.resolve_task_order(task_ids, edges)
        cycle = None if is_valid else TaskDependencyEngine.find_cycle(task_ids, edges)
        completed = {t.id for t in tasks if t.is_completed}
        executable_now = TaskDependencyEngine.find_executable_now(task_ids, edges, completed)

        return {
            "tasks": EventTaskSerializer(tasks, many=True).data,
            "is_valid_dag": is_valid,
            "topological_order": order,
            "cycle": cycle,
            "executable_now": executable_now,
        }

    # ------------------------------------------------------------------
    # Hoàn thành task (+ XP qua GamificationService — lazy import)
    # ------------------------------------------------------------------
    @classmethod
    def complete_task(cls, task_id: int, actor_member: Optional[MemberProfile] = None) -> EventTask:
        """
        Đánh dấu task hoàn thành. Nếu task có người phụ trách → cộng XP
        qua GamificationService (lazy import — tích hợp song song an toàn
        với Agent B; chưa có module thì chỉ ghi log, không lỗi).
        """
        task = cls._get_task_or_404(task_id)
        task.is_completed = True
        task.save(update_fields=["is_completed", "updated_at"])

        if task.nguoi_phu_trach_id:
            cls._award_xp_for_completion(task)

        logger.info("Task %s (%s) hoàn thành", task.id, task.ten_task)
        return task

    @classmethod
    def reopen_task(cls, task: EventTask) -> EventTask:
        """
        Mở lại task đã hoàn thành (is_completed=False).

        KHÔNG hoàn lại XP đã cộng (XP ledger là bất biến — xem
        GamificationService với idempotency_key "task_<id>").
        """
        task.is_completed = False
        task.save(update_fields=["is_completed", "updated_at"])
        return task

    @staticmethod
    def _award_xp_for_completion(task: EventTask) -> None:
        """Cộng XP hoàn thành task — KHÔNG bao giờ chặn luồng nghiệp vụ."""
        from django.conf import settings

        try:
            # Lazy import BÊN TRONG hàm — Agent B (gamification) viết song song
            from apps.gamification.services import GamificationService

            GamificationService.award_xp(
                member=task.nguoi_phu_trach,
                amount=settings.CLB_SETTINGS["XP_TASK_COMPLETION"],
                reason=f"Hoàn thành task {task.ten_task}",
                source="TASK_COMPLETION",
                idempotency_key=f"task_{task.id}",
            )
        except ImportError:
            logger.info(
                "GamificationService chưa sẵn sàng — bỏ qua cộng XP cho task %s.", task.id
            )
        except Exception:  # noqa: BLE001 — lỗi gamification không được hỏng nghiệp vụ
            logger.warning(
                "Cộng XP cho task %s thất bại — giữ nguyên kết quả hoàn thành.",
                task.id,
                exc_info=True,
            )
