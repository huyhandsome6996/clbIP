"""
AttendanceService — nghiệp vụ phiên điểm danh GPS (100% logic nằm ở đây).
==========================================================================
Luồng chính:
- open_session:  mở phiên + tự tạo bản ghi VẮNG cho mọi thành viên ACTIVE.
- close_session: đóng phiên, chốt danh sách.
- check_in:      check-in GPS qua GPSAntiCheatEngine (7 lớp anti-cheat),
                 xác định đúng giờ/muộn, tính streak 🔥, cộng XP qua
                 GamificationService (lazy import),
                 cập nhật vé EventRegistration → CHECKED_IN.
- bulk_override: BCN cập nhật thủ công hàng loạt (hết pin, lỗi định vị...).
"""
import logging
from datetime import timedelta
from typing import ClassVar, Optional

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.attendance.repositories import (
    DjangoAttendanceRepository,
    IAttendanceRepository,
)
from apps.attendance.services.anti_cheat import GPSAntiCheatEngine
from apps.common.exceptions import (
    DuplicateDataException,
    ForbiddenException,
    NotFoundException,
    SessionClosedException,
    ValidationException,
)
from apps.members.models import MemberProfile
from apps.members.repositories import DjangoMemberRepository

logger = logging.getLogger(__name__)

# Sau 15 phút kể từ lúc mở phiên → tính ĐI MUỘN
LATE_AFTER_MINUTES = 15


class AttendanceService:
    """
    Điều phối phiên điểm danh + check-in GPS + override của BCN.

    Toàn bộ truy vấn ORM tách vào `IAttendanceRepository` (Repository Pattern
    — Dependency Inversion, mẫu của apps.funds); service chỉ giữ nghiệp vụ.
    """

    # DI: repository dữ liệu attendance (cho phép mock khi unit test)
    _repository_class: ClassVar[type[IAttendanceRepository]] = DjangoAttendanceRepository
    # DI: tái dùng repository của apps.members (KHÔNG nhân bản truy vấn ACTIVE)
    _member_repository_class: ClassVar[type] = DjangoMemberRepository

    @classmethod
    def _repo(cls) -> IAttendanceRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    @classmethod
    def _member_repo(cls):
        """Repository thành viên (apps.members) — chỉ đọc dữ liệu chéo app."""
        return cls._member_repository_class()

    # ------------------------------------------------------------------
    # Mở / đóng phiên
    # ------------------------------------------------------------------
    @classmethod
    def open_session(
        cls,
        ten_phien: str,
        vi_do: float,
        kinh_do: float,
        ban_kinh_m: float = 50,
        event_id: Optional[int] = None,
        hieu_luc_den=None,
        opened_by: Optional[object] = None,  # giữ cho audit mở rộng (model chưa có FK)
    ) -> AttendanceSession:
        """
        Mở phiên điểm danh:
        - Sinh nonce_secret 48 ký tự (chìa khóa HMAC cho Dynamic Nonce 60s).
        - TỰ ĐỘNG bulk_create bản ghi VẮNG cho MỌI MemberProfile trang_thai=ACTIVE
          (BCN không cần tick từng người — vắng mặt là mặc định).

        Returns:
            AttendanceSession vừa mở.
        """
        session = cls._repo().create_session(
            ten_phien=ten_phien,
            vi_do=vi_do,
            kinh_do=kinh_do,
            ban_kinh_m=ban_kinh_m,
            event_id=event_id,
            hieu_luc_den=hieu_luc_den,
            nonce_secret=get_random_string(length=48),
            trang_thai=AttendanceSession.TrangThai.OPEN,
        )
        # Route qua repository của apps.members (get_active_members) — không trùng lặp
        active_members = cls._member_repo().get_active_members()
        cls._repo().bulk_create_vang_records(session, active_members, batch_size=500)
        logger.info(
            "Mở phiên %s (id=%s) bởi %s — %s bản ghi VẮNG",
            ten_phien,
            session.id,
            getattr(opened_by, "email", None),
            len(active_members),
        )
        return session

    @classmethod
    def close_session(cls, session: AttendanceSession, closed_by: Optional[object] = None) -> AttendanceSession:
        """Đóng phiên — chốt danh sách điểm danh."""
        session.trang_thai = AttendanceSession.TrangThai.CLOSED
        session.dong_phien_at = timezone.now()
        session.save(update_fields=["trang_thai", "dong_phien_at", "updated_at"])
        logger.info(
            "Đóng phiên %s bởi %s", session.id, getattr(closed_by, "email", None)
        )
        return session

    # ------------------------------------------------------------------
    # Check-in GPS (7 lớp anti-cheat)
    # ------------------------------------------------------------------
    @classmethod
    def check_in(
        cls,
        member: MemberProfile,
        session_id: int,
        client_lat: float,
        client_lon: float,
        client_time,
        device_id: str,
        nonce: str,
        is_mock: bool = False,
        accuracy: Optional[float] = None,
    ) -> AttendanceRecord:
        """
        Check-in GPS của thành viên:

            1. Phiên phải OPEN và còn hiệu lực (hieu_luc_den).
            2. Thành viên phải có bản ghi trong phiên (được tạo khi mở phiên).
            3. Không check-in trùng (CO_MAT).
            4. GPSAntiCheatEngine.validate_checkin — 7 lớp: mock → accuracy →
               skew → nonce → device reuse → teleportation → radius.
            5. Đúng giờ (≤15 phút sau mo_phien_at): CO_MAT; muộn hơn: DI_MUON.
               Điểm danh sớm ≥15 phút: thưởng XP_ATTENDANCE_EARLY_BONUS.
            6. Cập nhật streak 🔥 + cộng XP (GamificationService lazy import).
            7. Nếu phiên gắn sự kiện có vé → vé chuyển CHECKED_IN.
        """
        clb = settings.CLB_SETTINGS
        now = timezone.now()

        # 1. Phiên hợp lệ?
        try:
            session = cls._repo().get_session(session_id)
        except AttendanceSession.DoesNotExist:
            raise NotFoundException("Không tìm thấy phiên điểm danh.")
        if session.trang_thai != AttendanceSession.TrangThai.OPEN:
            raise SessionClosedException("Phiên điểm danh đã đóng hoặc chưa mở.")
        if session.hieu_luc_den and now > session.hieu_luc_den:
            raise SessionClosedException("Phiên điểm danh đã hết hiệu lực.")

        # 2. Bản ghi trong phiên (được tạo VẮNG khi mở phiên)
        try:
            record = cls._repo().get_record_for_member(session, member)
        except AttendanceRecord.DoesNotExist:
            raise NotFoundException("Bạn không có bản ghi điểm danh trong phiên này.")

        # 3. Chặn check-in trùng
        if record.trang_thai == AttendanceRecord.TrangThaiDiemDanh.CO_MAT:
            raise DuplicateDataException("Bạn đã điểm danh phiên này rồi!")

        # 4. Anti-Cheat Engine — raise nếu vi phạm bất kỳ lớp nào
        is_valid, dist = GPSAntiCheatEngine.validate_checkin(
            member=member,
            session=session,
            client_lat=client_lat,
            client_lon=client_lon,
            client_time=client_time,
            device_id=device_id,
            nonce=nonce,
            is_mock=is_mock,
            accuracy=accuracy,
        )

        # 5. Xác định đúng giờ / muộn + XP tương ứng (server-authoritative)
        late_deadline = session.mo_phien_at + timedelta(minutes=LATE_AFTER_MINUTES)
        if now > late_deadline:
            trang_thai = AttendanceRecord.TrangThaiDiemDanh.DI_MUON
            xp_total = clb["XP_ATTENDANCE_LATE"]
        else:
            trang_thai = AttendanceRecord.TrangThaiDiemDanh.CO_MAT
            minutes_early = (session.mo_phien_at - now).total_seconds() / 60.0
            xp_total = clb["XP_ATTENDANCE"]
            if minutes_early >= 15:
                xp_total += clb["XP_ATTENDANCE_EARLY_BONUS"]

        record.trang_thai = trang_thai
        record.khoang_cach_m = dist
        record.vi_do = client_lat
        record.kinh_do = client_lon
        record.checked_in_at = now
        record.device_id = device_id or ""
        record.xp_awarded = xp_total
        record.save(
            update_fields=[
                "trang_thai",
                "khoang_cach_m",
                "vi_do",
                "kinh_do",
                "checked_in_at",
                "device_id",
                "xp_awarded",
                "updated_at",
            ]
        )

        # 6a. Streak chuyên cần 🔥
        cls._update_streak(member, now)

        # 6b. XP qua GamificationService (lazy import — an toàn tích hợp song song)
        cls._award_xp_safe(member=member, amount=xp_total, session=session, record=record)

        # 7. Vé sự kiện (nếu có) → CHECKED_IN (query chéo app nằm trong repo)
        if session.event_id:
            cls._repo().mark_event_registrations_checked_in(session.event_id, member)

        logger.info(
            "Check-in OK: member=%s session=%s dist=%.1fm status=%s xp=%s",
            member.id,
            session.id,
            dist,
            trang_thai,
            record.xp_awarded,
        )
        return record

    # ------------------------------------------------------------------
    # Tiện ích nội bộ
    # ------------------------------------------------------------------
    @staticmethod
    def _update_streak(member: MemberProfile, now) -> None:
        """
        Chuỗi chuyên cần: điểm danh hôm nay đã tính rồi thì giữ nguyên;
        hôm qua có điểm danh → +1; gián đoạn → reset về 1.
        """
        today = timezone.localdate(now)
        last = member.last_attendance_date
        if last == today:
            streak = member.streak_count  # tránh đếm đúp trong cùng ngày
        elif last == today - timedelta(days=1):
            streak = member.streak_count + 1
        else:
            streak = 1
        member.streak_count = streak
        member.last_attendance_date = today
        member.save(update_fields=["streak_count", "last_attendance_date", "updated_at"])

    @staticmethod
    def _award_xp_safe(member: MemberProfile, amount: int, session: AttendanceSession, record: AttendanceRecord) -> None:
        """
        Gọi GamificationService.award_xp với idempotency_key chống cộng lặp.

        - Lazy import BÊN TRONG hàm (lỗi gamification không chặn check-in).
        - Mọi lỗi gamification KHÔNG được làm hỏng kết quả check-in.
        """
        try:
            from apps.gamification.services import GamificationService  # noqa: PLC0415
        except ImportError:
            logger.info(
                "GamificationService chưa sẵn sàng — bỏ qua cộng XP (member=%s session=%s).",
                member.id,
                session.id,
            )
            return

        try:
            result = GamificationService.award_xp(
                member=member,
                amount=amount,
                reason=f"Điểm danh {session.ten_phien}",
                source="ATTENDANCE",
                idempotency_key=f"attendance_{session.id}_{member.id}",
            )
            # Đồng bộ XP thực nhận (GamificationService có thể áp Daily Cap 300)
            if isinstance(result, dict) and result.get("xp_gained") is not None:
                record.xp_awarded = result["xp_gained"]
                record.save(update_fields=["xp_awarded", "updated_at"])
        except Exception:  # noqa: BLE001 — lỗi XP không chặn nghiệp vụ điểm danh
            logger.warning(
                "Cộng XP thất bại (member=%s session=%s) — check-in vẫn hợp lệ.",
                member.id,
                session.id,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # BCN override thủ công hàng loạt
    # ------------------------------------------------------------------
    @classmethod
    def bulk_override(cls, session: AttendanceSession, items: list[dict], actor) -> int:
        """
        Cập nhật trạng thái điểm danh thủ công cho danh sách thành viên.

        Args:
            session: phiên điểm danh đích.
            items: [{"member_id": int, "trang_thai": "CO_MAT|VANG|CO_PHEP|DI_MUON"}].
            actor: User BCN thực hiện (ghi vào overridden_by để audit).

        Returns:
            Số bản ghi đã cập nhật. Member chưa có record trong phiên
            (tham gia muộn) → tạo mới bản ghi với trạng thái chỉ định.
        """
        valid_statuses = set(AttendanceRecord.TrangThaiDiemDanh.values)
        updated = 0
        for item in items:
            member_id = item.get("member_id")
            trang_thai = item.get("trang_thai")

            if trang_thai not in valid_statuses:
                raise ValidationException(
                    f"Trạng thái điểm danh không hợp lệ: {trang_thai}",
                    errors={"trang_thai": trang_thai},
                )
            if not cls._repo().member_exists(member_id):
                raise ValidationException(
                    f"Không tồn tại thành viên với member_id={member_id}",
                    errors={"member_id": member_id},
                )

            record, created = cls._repo().get_or_create_record(
                session=session,
                member_id=member_id,
                defaults={"trang_thai": trang_thai},
            )
            if not created:
                record.trang_thai = trang_thai
            record.overridden_by = actor
            if trang_thai == AttendanceRecord.TrangThaiDiemDanh.CO_PHEP:
                record.is_suspicious = False  # có phép → xóa cờ nghi vấn
            record.save()

            updated += 1

        logger.info("BCN %s override %s bản ghi của phiên %s", actor, updated, session.id)
        return updated

    # ------------------------------------------------------------------
    # Tra cứu
    # ------------------------------------------------------------------
    @classmethod
    def get_session_or_404(cls, session_id: int) -> AttendanceSession:
        """Lấy phiên theo id — không thấy → NotFoundException (404 envelope)."""
        try:
            return cls._repo().get_session(session_id)
        except AttendanceSession.DoesNotExist:
            raise NotFoundException("Không tìm thấy phiên điểm danh.")

    @classmethod
    def get_member_profile_or_forbidden(cls, user) -> MemberProfile:
        """Chỉ user gắn với hồ sơ thành viên mới được check-in."""
        profile = cls._repo().get_member_profile_for_user(user)
        if profile is None:
            raise ForbiddenException("Tài khoản này không gắn với hồ sơ thành viên CLB.")
        return profile

    # ------------------------------------------------------------------
    # Tra cứu cho view (view mỏng — không đụng ORM)
    # ------------------------------------------------------------------
    @classmethod
    def list_sessions(cls, trang_thai: Optional[str] = None):
        """QuerySet phiên điểm danh (view tự phân trang + serialize)."""
        return cls._repo().list_sessions(trang_thai)

    @classmethod
    def history_for_member(cls, member: MemberProfile, limit: int = 50):
        """Lịch sử điểm danh cá nhân (mới nhất trước, tối đa `limit` bản ghi)."""
        return cls._repo().history_for_member(member, limit=limit)
