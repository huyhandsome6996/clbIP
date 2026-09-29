"""
GPSAntiCheatEngine — Engine chống gian lận điểm danh GPS (Security Hardening §5.1).
====================================================================================
Trình tự kiểm tra (mỗi bước raise AntiCheatException nếu vi phạm):

    1. Mock Location flag        → từ chối ngay.
    2. GPS accuracy > 100m       → tín hiệu quá kém, từ chối.
    3. Timestamp skew > 60s      → chống Replay Attack.
    4. Dynamic nonce sai/hết hạn → chống chụp màn hình / chỉ-point người ở xa.
    5. Device reuse              → 1 thiết bị không điểm danh hộ 2 thành viên.
    6. Teleportation             → vận tốc giữa 2 lần check-in > 100 km/h.
    7. Haversine radius          → khoảng cách tới tâm > bán kính cho phép.

Toàn bộ PASS → trả (True, distance_m) cho Service ghi vào AttendanceRecord.
"""
import datetime as _dt
import logging
from typing import ClassVar, Optional, Tuple, Union

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.attendance.repositories import (
    DjangoAttendanceRepository,
    IAttendanceRepository,
)
from apps.attendance.services.nonce import AttendanceNonceService
from apps.common.exceptions import AntiCheatException, InvalidNonceException
from core.algorithms.geo_haversine import GeoSpatialService

logger = logging.getLogger(__name__)


class GPSAntiCheatEngine:
    """Engine kiểm tra tính hợp lệ của một request check-in GPS."""

    # DI: repository dữ liệu (anti-cheat KHÔNG đụng ORM trực tiếp)
    _repository_class: ClassVar[type[IAttendanceRepository]] = DjangoAttendanceRepository

    @classmethod
    def _repo(cls) -> IAttendanceRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    @staticmethod
    def _coerce_client_time(client_time: Union[None, str, _dt.datetime]) -> _dt.datetime:
        """
        Chuẩn hóa client_time về datetime timezone-aware.

        - None / rỗng → AntiCheatException (thiếu dữ liệu thiết bị).
        - Chuỗi ISO 8601 → parse; naive → gắn UTC.
        """
        if client_time in (None, ""):
            raise AntiCheatException("Thiếu thông tin thời gian thiết bị (client_time)!")
        if isinstance(client_time, _dt.datetime):
            parsed = client_time
        else:
            parsed = parse_datetime(str(client_time))
            if parsed is None:
                raise AntiCheatException(
                    "Thời gian thiết bị không đúng định dạng ISO 8601!"
                )
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, _dt.timezone.utc)
        return parsed

    @classmethod
    def validate_checkin(
        cls,
        member,
        session,
        client_lat: float,
        client_lon: float,
        client_time: Union[None, str, _dt.datetime],
        device_id: str,
        nonce: str,
        is_mock: bool = False,
        accuracy: Optional[float] = None,
    ) -> Tuple[bool, float]:
        """
        Kiểm tra toàn diện 7 lớp anti-cheat cho request check-in.

        Args:
            member: MemberProfile đang check-in.
            session: AttendanceSession đích.
            client_lat/lon: tọa độ client khai báo.
            client_time: thời điểm thiết bị (ISO 8601 hoặc datetime).
            device_id: fingerprint thiết bị.
            nonce: mã nonce 6 chữ số từ máy chiếu.
            is_mock: cờ mock location từ client OS.
            accuracy: độ chính xác GPS (mét) nếu client gửi.

        Returns:
            (True, khoảng cách tới tâm theo mét) nếu toàn bộ hợp lệ.

        Raises:
            AntiCheatException / InvalidNonceException: khi vi phạm bất kỳ lớp nào.
        """
        now = timezone.now()
        clb = settings.CLB_SETTINGS

        # 1. Mock Location — từ chối ngay lập tức
        if is_mock:
            raise AntiCheatException("Phát hiện vị trí giả lập (Mock Location)!")

        # 2. Accuracy quá kém → nghi ngờ Fake/tín hiệu rác
        max_accuracy = clb["MAX_GPS_ACCURACY_METERS"]
        if accuracy is not None and accuracy > max_accuracy:
            raise AntiCheatException(f"Tín hiệu GPS quá kém (accuracy > {max_accuracy}m)")

        # 3. Timestamp skew — chống Replay Attack (quay lại dùng dữ liệu cũ)
        client_dt = cls._coerce_client_time(client_time)
        if abs((now - client_dt).total_seconds()) > clb["MAX_TIMESTAMP_SKEW_SECONDS"]:
            raise AntiCheatException("Thời gian trên thiết bị không đồng bộ với máy chủ!")

        # 4. Dynamic nonce — chỉ ai nhìn máy chiếu tại hội trường mới có mã
        if not AttendanceNonceService.validate(session, nonce, at=now):
            raise InvalidNonceException("Mã xác thực phiên không đúng hoặc đã hết hiệu lực!")

        # 5. Device reuse — 1 thiết bị không điểm danh cho 2 thành viên
        if device_id:
            reused = cls._repo().exists_device_reuse(session, member, device_id)
            if reused:
                raise AntiCheatException(
                    "Thiết bị này đã được dùng để điểm danh cho sinh viên khác!"
                )

        # 6. Teleportation — vận tốc bất khả thi giữa 2 lần check-in liên tiếp
        last_record = cls._repo().get_last_checkin_for_teleport_check(member)
        if last_record is not None:
            seconds = (client_dt - last_record.checked_in_at).total_seconds()
            speed_kmh = GeoSpatialService.travel_speed_kmh(
                last_record.vi_do, last_record.kinh_do, client_lat, client_lon, seconds
            )
            max_speed = clb["MAX_TRAVEL_SPEED_KMH"]
            if speed_kmh > max_speed:
                logger.warning(
                    "Teleportation: member=%s speed=%.0f km/h", member.id, speed_kmh
                )
                raise AntiCheatException(
                    f"Dịch chuyển bất khả thi {speed_kmh:.0f} km/h — nghi vấn Fake GPS!"
                )

        # 7. Haversine radius — phải nằm trong bán kính cho phép
        is_valid, dist = GeoSpatialService.is_within_radius(
            session.vi_do, session.kinh_do, client_lat, client_lon, session.ban_kinh_m
        )
        if not is_valid:
            raise AntiCheatException(
                f"Bạn đang cách địa điểm {dist:.0f}m (vượt quá bán kính {session.ban_kinh_m}m)!"
            )

        return True, dist
