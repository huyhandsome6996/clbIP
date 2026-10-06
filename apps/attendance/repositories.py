"""
Repository Layer — apps.attendance
==================================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion) — làm theo mẫu của `apps.funds`.

`AttendanceService` và `GPSAntiCheatEngine` chỉ phụ thuộc vào trừu tượng
`IAttendanceRepository`, không đụng trực tiếp vào ORM. 100% truy vấn dùng
Django ORM parameterized (TUYỆT ĐỐI không raw SQL — Security Hardening §2.1).

⚠️ Cross-app queries: hai phương thức cuối (`member_exists`,
`get_member_profile_for_user`) đọc `MemberProfile` của apps.members và
`mark_event_registrations_checked_in` cập nhật `EventRegistration` của
apps.events. Chúng nằm ở đây (KHÔNG sửa file của apps kia) kèm comment rõ
ràng — apps.events chưa có repository riêng tại thời điểm refactor.
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from django.db import transaction as db_transaction
from django.db.models import Q, QuerySet

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.members.models import MemberProfile


class IAttendanceRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Điểm danh — phụ thuộc trừu tượng (DIP)."""

    # ------------------------------------------------------------------
    # AttendanceSession
    # ------------------------------------------------------------------
    @abstractmethod
    def list_sessions(
        self, trang_thai: Optional[str] = None
    ) -> QuerySet[AttendanceSession]:
        """Danh sách phiên (lọc `trang_thai` nếu nằm trong whitelist choices)."""

    @abstractmethod
    def create_session(self, **fields) -> AttendanceSession:
        """Mở phiên điểm danh mới (INSERT một dòng)."""

    @abstractmethod
    def get_session(self, session_id: int) -> AttendanceSession:
        """Lấy phiên theo pk — raise `AttendanceSession.DoesNotExist` nếu thiếu."""

    # ------------------------------------------------------------------
    # AttendanceRecord
    # ------------------------------------------------------------------
    @abstractmethod
    def bulk_create_vang_records(self, session: AttendanceSession, members, batch_size: int = 500) -> None:
        """Bulk-create bản ghi VẮNG cho danh sách thành viên khi mở phiên."""

    @abstractmethod
    def get_record_for_member(self, session: AttendanceSession, member: MemberProfile) -> AttendanceRecord:
        """Bản ghi điểm danh của một thành viên trong một phiên."""

    @abstractmethod
    def get_record_for_member_locked(
        self, session: AttendanceSession, member: MemberProfile
    ) -> AttendanceRecord:
        """Bản ghi + row lock (select_for_update) — gọi trong transaction.atomic."""

    @abstractmethod
    def get_or_create_record(
        self, session: AttendanceSession, member_id: int, defaults: dict
    ) -> Tuple[AttendanceRecord, bool]:
        """Lấy hoặc tạo bản ghi (BCN override cho member tham gia muộn)."""

    @abstractmethod
    def history_for_member(self, member: MemberProfile, limit: int = 50) -> QuerySet[AttendanceRecord]:
        """Lịch sử điểm danh cá nhân (mới nhất trước, select_related session)."""

    @abstractmethod
    def exists_device_reuse(self, session: AttendanceSession, member: MemberProfile, device_id: str) -> bool:
        """Anti-cheat lớp 5: device_id đã bị dùng cho thành viên khác trong phiên?"""

    @abstractmethod
    def get_last_checkin_for_teleport_check(self, member: MemberProfile) -> Optional[AttendanceRecord]:
        """Anti-cheat lớp 6: lần check-in hợp lệ gần nhất (so vận tốc teleport)."""

    # ------------------------------------------------------------------
    # Truy vấn chéo app (MemberProfile / EventRegistration)
    # ------------------------------------------------------------------
    @abstractmethod
    def member_exists(self, member_id: int) -> bool:
        """Thành viên có tồn tại theo pk? (bulk_override validate)."""

    @abstractmethod
    def filter_existing_member_ids(self, member_ids: set[int]) -> set[int]:
        """Lọc trong tập ID nào thực sự tồn tại (bulk validate — 1 query)."""

    @abstractmethod
    def list_records_for_session(
        self,
        session: AttendanceSession,
        trang_thai: Optional[str] = None,
        search: Optional[str] = None,
    ) -> QuerySet[AttendanceRecord]:
        """Bản ghi điểm danh của một phiên (BCN xem/audit — phân trang ở view)."""

    @abstractmethod
    def get_member_profile_for_user(self, user) -> Optional[MemberProfile]:
        """Hồ sơ thành viên gắn với user (None nếu không có — chặn IDOR/403)."""

    @abstractmethod
    def mark_event_registrations_checked_in(self, event_id: int, member: MemberProfile) -> int:
        """Vé sự kiện của member → CHECKED_IN (trả về số dòng cập nhật)."""

    @abstractmethod
    def aggregate_weekly_attendance(self, since_dt) -> list:
        """
        Tỉ lệ chuyên cần GROUP BY tuần từ `since_dt` — dữ liệu biểu đồ trend
        dashboard BCN (QA-Audit đợt 3 — TASK 4).
        Trả list [{"week": "YYYY-Wnn", "rate": float 0..1}] tăng dần theo tuần.
        """


class DjangoAttendanceRepository(IAttendanceRepository):
    """Triển khai cụ thể bằng Django ORM cho `IAttendanceRepository`."""

    # ------------------------------------------------------------------
    # AttendanceSession
    # ------------------------------------------------------------------
    def list_sessions(
        self, trang_thai: Optional[str] = None
    ) -> QuerySet[AttendanceSession]:
        """Danh sách phiên — chỉ lọc khi `trang_thai` hợp lệ (whitelist choices)."""
        queryset = AttendanceSession.objects.all()
        if trang_thai and trang_thai in AttendanceSession.TrangThai.values:
            queryset = queryset.filter(trang_thai=trang_thai)
        return queryset

    def create_session(self, **fields) -> AttendanceSession:
        """Mở phiên điểm danh mới."""
        return AttendanceSession.objects.create(**fields)

    def get_session(self, session_id: int) -> AttendanceSession:
        """Lấy phiên theo pk — caller tự xử lý DoesNotExist → NotFoundException."""
        return AttendanceSession.objects.get(pk=session_id)

    # ------------------------------------------------------------------
    # AttendanceRecord
    # ------------------------------------------------------------------
    def bulk_create_vang_records(
        self, session: AttendanceSession, members, batch_size: int = 500
    ) -> None:
        """Tạo hàng loạt bản ghi VẮNG (vắng mặt là mặc định khi mở phiên)."""
        AttendanceRecord.objects.bulk_create(
            [
                AttendanceRecord(
                    session=session,
                    member=member,
                    trang_thai=AttendanceRecord.TrangThaiDiemDanh.VANG,
                )
                for member in members
            ],
            batch_size=batch_size,
        )

    def get_record_for_member(
        self, session: AttendanceSession, member: MemberProfile
    ) -> AttendanceRecord:
        """Bản ghi của `member` trong `session` — raise DoesNotExist nếu thiếu."""
        return AttendanceRecord.objects.get(session=session, member=member)

    @db_transaction.atomic
    def get_record_for_member_locked(
        self, session: AttendanceSession, member: MemberProfile
    ) -> AttendanceRecord:
        """
        Bản ghi của `member` trong `session` — `select_for_update` (row lock).

        review 13-a P2-4: hai check-in song song cùng member/session tuần tự
        hóa tại đây → chỉ 1 request ghi được, request kia bắt duplicate 409.
        `@atomic` tự bảo đảm có transaction quanh select_for_update (an toàn
        ngay cả khi caller chưa bọc atomic); SQLite lock là no-op toàn bảng,
        MySQL production khóa đúng dòng.
        """
        return AttendanceRecord.objects.select_for_update().get(
            session=session, member=member
        )

    def get_or_create_record(
        self, session: AttendanceSession, member_id: int, defaults: dict
    ) -> Tuple[AttendanceRecord, bool]:
        """Get-or-create phục vụ BCN bulk override (member tham gia muộn)."""
        return AttendanceRecord.objects.get_or_create(
            session=session,
            member_id=member_id,
            defaults=defaults,
        )

    def history_for_member(
        self, member: MemberProfile, limit: int = 50
    ) -> QuerySet[AttendanceRecord]:
        """Lịch sử của CHÍNH member này (chống IDOR ở tầng service/view)."""
        return (
            AttendanceRecord.objects.filter(member=member)
            .select_related("session")
            .order_by("-created_at")[:limit]
        )

    def exists_device_reuse(
        self, session: AttendanceSession, member: MemberProfile, device_id: str
    ) -> bool:
        """True nếu `device_id` đã được dùng cho thành viên khác trong phiên."""
        return (
            AttendanceRecord.objects.filter(session=session, device_id=device_id)
            .exclude(member=member)
            .exclude(device_id="")
            .exists()
        )

    def get_last_checkin_for_teleport_check(
        self, member: MemberProfile
    ) -> Optional[AttendanceRecord]:
        """Check-in có tọa độ gần nhất của member (mốc tính vận tốc di chuyển)."""
        return (
            AttendanceRecord.objects.filter(
                member=member,
                checked_in_at__isnull=False,
                vi_do__isnull=False,
                kinh_do__isnull=False,
            )
            .order_by("-checked_in_at")
            .first()
        )

    # ------------------------------------------------------------------
    # Truy vấn chéo app (MemberProfile / EventRegistration)
    # ------------------------------------------------------------------
    def member_exists(self, member_id: int) -> bool:
        """
        Thành viên tồn tại theo pk?

        ⚠️ Cross-app: đọc thẳng `MemberProfile` (apps.members) — apps.members
        chưa có phương thức `exists()` tương ứng trong repository của nó.
        """
        return MemberProfile.objects.filter(pk=member_id).exists()

    def filter_existing_member_ids(self, member_ids: set[int]) -> set[int]:
        """
        Trả về tập ID thực sự tồn tại trong `MemberProfile` (1 query duy nhất).

        Dùng bởi `AttendanceService.bulk_override` — validate TOÀN BỘ danh sách
        trước khi ghi (audit F01: hết lỗi "API báo thất bại nhưng một phần dữ
        liệu đã đổi").
        """
        if not member_ids:
            return set()
        return set(
            MemberProfile.objects.filter(pk__in=member_ids).values_list("pk", flat=True)
        )

    def list_records_for_session(
        self,
        session: AttendanceSession,
        trang_thai: Optional[str] = None,
        search: Optional[str] = None,
    ) -> QuerySet[AttendanceRecord]:
        """
        Bản ghi điểm danh của một phiên (audit F10 — khoảng trống chức năng:
        BCN cần bảng xem kết quả theo phiên sau override/đóng phiên).

        - `trang_thai`: lọc theo choices (giá trị lạ bị service chặn trước).
        - `search`: khớp họ tên / MSSV / email thành viên (icontains).
        Không trả tọa độ GPS thô — BCN xem `khoang_cach_m` + `is_suspicious`
        là đủ để audit anti-cheat (giảm PII trong payload).
        """
        qs = AttendanceRecord.objects.filter(session=session).select_related(
            "member", "member__user", "overridden_by"
        )
        if trang_thai:
            qs = qs.filter(trang_thai=trang_thai)
        if search:
            qs = qs.filter(
                Q(member__ho_ten__icontains=search)
                # ⚠ `mssv` trên MemberProfile là property (field thật nằm trên
                # User) — ORM chỉ query được qua `member__user__mssv` (fix
                # F-13b-01: trước đây dùng member__mssv → FieldError 500).
                | Q(member__user__mssv__icontains=search)
                | Q(member__user__email__icontains=search)
            )
        return qs.order_by("member__ho_ten", "id")

    def get_member_profile_for_user(self, user) -> Optional[MemberProfile]:
        """
        Hồ sơ thành viên của user (None → service raise ForbiddenException).

        Cross-app: ủy quyền cho members repository — truy vấn user→profile
        sống đúng một nơi (DjangoMemberRepository.get_by_user).
        """
        from apps.members.repositories import DjangoMemberRepository  # noqa: PLC0415

        return DjangoMemberRepository().get_by_user(user)

    def mark_event_registrations_checked_in(
        self, event_id: int, member: MemberProfile
    ) -> int:
        """
        Vé sự kiện của member chuyển sang CHECKED_IN khi check-in phiên gắn event.

        Cross-app: cập nhật `EventRegistration` (apps.events) — ủy quyền qua
        DjangoEventRepository để truy vấn của từng model sống đúng 1 nơi.
        """
        from apps.events.repositories import DjangoEventRepository  # noqa: PLC0415

        return DjangoEventRepository().mark_registrations_checked_in(event_id, member)

    def aggregate_weekly_attendance(self, since_dt) -> list:
        """
        Tỉ lệ chuyên cần GROUP BY tuần (theo thời điểm MỞ PHIỂN) từ `since_dt` —
        dữ liệu biểu đồ "Chuyên cần hàng tuần" trên dashboard BCN (TASK 4).

        Chuyên cần = (CO_MAT + DI_MUON) / tổng bản ghi trong tuần — đi muộn
        vẫn tính là đã đến; CO_PHEP/VANG không tính là chuyên cần.

        PORTABLE TIME (apps/common/timeutils): KHÔNG dùng TruncWeek — lookup
        timezone của MySQL phụ thuộc bảng tz của DB. Lọc bằng khoảng datetime
        + nhóm tuần ISO trong Python — chạy đúng trên mọi CSDL.
        Trả list [{"week": "YYYY-Wnn", "rate": float 0..1}] tăng dần theo tuần.
        """
        from django.utils import timezone  # noqa: PLC0415

        rows = (
            AttendanceRecord.objects.filter(session__mo_phien_at__gte=since_dt)
            .values_list("session__mo_phien_at", "trang_thai")
        )
        buckets: dict = {}
        for mo_phien_at, trang_thai in rows:
            local_dt = timezone.localtime(mo_phien_at)
            iso = local_dt.isocalendar()
            key = f"{iso.year}-W{iso.week:02d}"
            stat = buckets.setdefault(key, {"total": 0, "present": 0})
            stat["total"] += 1
            if trang_thai in (
                AttendanceRecord.TrangThaiDiemDanh.CO_MAT,
                AttendanceRecord.TrangThaiDiemDanh.DI_MUON,
            ):
                stat["present"] += 1
        return [
            {
                "week": key,
                "rate": round(stat["present"] / stat["total"], 4) if stat["total"] else 0.0,
            }
            for key, stat in sorted(buckets.items())
        ]
