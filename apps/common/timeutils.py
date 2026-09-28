"""
timeutils — Hàm thời gian di động đa CSDL (MySQL / PostgreSQL / SQLite).
=======================================================================
Vấn đề: lookup ORM dạng `field__date=<date>` trên MySQL sinh CONVERT_TZ(...)
và PHỤ THUỘC bảng timezone của DB (Windows MySQL / MariaDB user-space
thường KHÔNG có sẵn). Khi thiếu → kết quả NULL → lọc ngày âm thầm sai.

Giải pháp: quy ngày địa phương (Asia/Ho_Chi_Minh) thành KHOẢNG datetime
aware rồi so sánh trực tiếp — chạy đúng trên mọi CSDL, không cần bảng tz.
"""
from datetime import date, datetime, time, timedelta
from typing import Tuple

from django.utils import timezone


def local_day_range(day: date) -> Tuple[datetime, datetime]:
    """[00:00 của `day`, 00:00 của ngày kế) theo múi giờ hiện tại của dự án."""
    start = timezone.make_aware(datetime.combine(day, time.min))
    return start, start + timedelta(days=1)


def local_day_start(day: date) -> datetime:
    """00:00 của `day` (aware) — dùng cho lọc 'từ ngày' trở đi."""
    return timezone.make_aware(datetime.combine(day, time.min))


def local_range_inclusive(from_day: date, to_day: date) -> Tuple[datetime, datetime]:
    """Khoảng [00:00 của from_day, 00:00 của to_day+1) — bao trọn to_day."""
    start = local_day_start(from_day)
    _, end = local_day_range(to_day)
    return start, end
