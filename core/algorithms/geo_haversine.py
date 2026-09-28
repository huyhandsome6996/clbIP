"""
DSA 1: Haversine Geofencing & Bounding Box Spatial Pruning
==========================================================
Nghiệp vụ: Điểm danh GPS — xác minh tọa độ thành viên có nằm trong bán kính
cho phép của BCN hay không.

Tối ưu: Tính Bounding Box [lat ± Δ, lon ± Δ] để prune ~99% trường hợp ngoài
phạm vi trước khi tính hàm lượng giác Haversine (chi phí O(1) cho 1 điểm).

Công thức Haversine:
    d = 2r · arcsin(√( sin²(Δφ/2) + cos(φ1)·cos(φ2)·sin²(Δλ/2) ))
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class BoundingBox:
    """Ô bao chữ nhật tối thiểu chứa hình tròn bán kính `radius_m` tâm `(lat, lon)`."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, lat: float, lon: float) -> bool:
        """Kiểm tra nhanh O(1): điểm có nằm trong ô bao hay không."""
        return self.min_lat <= lat <= self.max_lat and self.min_lon <= lon <= self.max_lon


class GeoSpatialService:
    """Dịch vụ địa lý không gian dùng cho Geofencing điểm danh GPS."""

    EARTH_RADIUS_METERS: float = 6_371_000  # Bán kính Trái Đất trung bình (mét)

    # ------------------------------------------------------------------
    # Công thức Haversine chuẩn
    # ------------------------------------------------------------------
    @classmethod
    def haversine_distance(
        cls, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Tính khoảng cách chính xác (mét) giữa 2 điểm GPS theo công thức Haversine.

        Args:
            lat1, lon1: vĩ độ, kinh độ điểm A (độ thập phân).
            lat2, lon2: vĩ độ, kinh độ điểm B.

        Returns:
            Khoảng cách mặt cầu giữa 2 điểm tính bằng mét.
        """
        phi1: float = math.radians(lat1)
        phi2: float = math.radians(lat2)
        delta_phi: float = math.radians(lat2 - lat1)
        delta_lambda: float = math.radians(lon2 - lon1)

        a: float = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        )
        c: float = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return cls.EARTH_RADIUS_METERS * c

    # ------------------------------------------------------------------
    # Bounding Box Pre-filter (Spatial Pruning)
    # ------------------------------------------------------------------
    @classmethod
    def bounding_box(cls, lat: float, lon: float, radius_m: float) -> BoundingBox:
        """
        Tính ô bao chữ nhật quanh tâm `(lat, lon)` bán kính `radius_m`.

        Dùng để prune nhanh các điểm nằm ngoài vùng trước khi tính Haversine
        đắt tiền — lọc 99% trường hợp chỉ với 4 phép so sánh.
        """
        # Độ vĩ độ tương ứng bán kính: Δlat = r / (R * π/180)
        delta_lat: float = math.degrees(radius_m / cls.EARTH_RADIUS_METERS)
        # Kinh độ co hẹp theo cosine của vĩ độ (gần hai cực thì trộn rộng hơn)
        delta_lon: float = math.degrees(
            radius_m / (cls.EARTH_RADIUS_METERS * max(math.cos(math.radians(lat)), 1e-9))
        )
        return BoundingBox(
            min_lat=lat - delta_lat,
            max_lat=lat + delta_lat,
            min_lon=lon - delta_lon,
            max_lon=lon + delta_lon,
        )

    # ------------------------------------------------------------------
    # Geofencing API tổng hợp (prune + haversine)
    # ------------------------------------------------------------------
    @classmethod
    def is_within_radius(
        cls,
        center_lat: float,
        center_lon: float,
        target_lat: float,
        target_lon: float,
        radius_meters: float,
        use_bounding_box: bool = True,
    ) -> Tuple[bool, float]:
        """
        Xác minh `target` có nằm trong bán kính `radius_meters` quanh tâm hay không.

        Args:
            center_lat/lon: tọa độ tâm (phiên điểm danh).
            target_lat/lon: tọa độ thiết bị thành viên.
            radius_meters: bán kính cho phép (m).
            use_bounding_box: bật/tắt pre-filter bounding box.

        Returns:
            Tuple (is_valid, distance_m) — distance làm tròn 2 chữ số thập phân.
        """
        if use_bounding_box:
            bbox: BoundingBox = cls.bounding_box(center_lat, center_lon, radius_meters)
            if not bbox.contains(target_lat, target_lon):
                # Ngoài ô bao ⇒ chắc chắn ngoài bán kính → trả khoảng cách xấp xỉ
                approx: float = cls._approx_distance_outside_bbox(
                    center_lat, center_lon, target_lat, target_lon
                )
                return False, round(approx, 2)

        distance: float = cls.haversine_distance(
            center_lat, center_lon, target_lat, target_lon
        )
        return distance <= radius_meters, round(distance, 2)

    @staticmethod
    def _approx_distance_outside_bbox(
        center_lat: float, center_lon: float, target_lat: float, target_lon: float
    ) -> float:
        """
        Ước lượng khoảng cách tối thiểu từ điểm ngoài ô bao tới tâm
        (dùng Δ lat/lon trực tiếp — đủ chính xác cho thông báo lỗi).
        """
        dlat_m: float = abs(target_lat - center_lat) * 111_320
        dlon_m: float = (
            abs(target_lon - center_lon)
            * 111_320
            * max(math.cos(math.radians(center_lat)), 1e-9)
        )
        return math.hypot(dlat_m, dlon_m)

    # ------------------------------------------------------------------
    # Tiện ích: tốc độ di chuyển (chống Fake GPS Teleportation)
    # ------------------------------------------------------------------
    @staticmethod
    def travel_speed_kmh(
        lat1: float, lon1: float, lat2: float, lon2: float, seconds: float
    ) -> float:
        """
        Tính vận tốc di chuyển (km/h) giữa 2 lần check-in.
        Nếu > 100 km/h ⇒ chắc chắn Fake GPS (teleportation).
        """
        if seconds <= 0:
            return float("inf")
        distance_m: float = GeoSpatialService.haversine_distance(lat1, lon1, lat2, lon2)
        return (distance_m / 1000.0) / (seconds / 3600.0)
