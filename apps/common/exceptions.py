"""
Business Exceptions — hệ phân cấp lỗi nghiệp vụ của toàn hệ thống.

Mỗi exception được custom_exception_handler (core/exceptions.py) tự động
chuyển thành envelope {success: false, message, errors} với HTTP status phù hợp.
"""
from typing import Any, Optional


class BusinessException(Exception):
    """Lớp gốc cho mọi lỗi nghiệp vụ."""

    status_code = 400
    default_message = "Yêu cầu không hợp lệ."

    def __init__(
        self,
        message: Optional[str] = None,
        errors: Any = None,
        status_code: Optional[int] = None,
    ) -> None:
        self.message = message or self.default_message
        self.errors = errors
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


# ----------------------------------------------------------------------
# Quỹ (Funds)
# ----------------------------------------------------------------------
class InsufficientFundException(BusinessException):
    status_code = 400
    default_message = "Số dư quỹ không đủ để thực hiện khoản chi này!"


class PeriodLockedException(BusinessException):
    status_code = 409
    default_message = "Kỳ sổ sách đã bị khóa. Không thể thay đổi giao dịch thuộc kỳ này!"


class IdempotencyKeyConflictException(BusinessException):
    """
    Idempotency-Key đã được dùng cho một yêu cầu CÓ NỘI DUNG KHÁC (audit F02).

    Trả 409 — KHÔNG replay giao dịch cũ (sai ý định) và KHÔNG ghi mới
    (mất ý nghĩa chống ghi trùng). Client phải kiểm tra sổ quỹ rồi dùng
    key mới nếu chắc chắn muốn ghi giao dịch mới.
    """

    status_code = 409
    default_message = (
        "Idempotency-Key này đã được dùng cho một giao dịch khác. "
        "Vui lòng kiểm tra sổ quỹ trước khi gửi lại với khóa mới."
    )


class FundInvariantViolationException(BusinessException):
    status_code = 500
    default_message = "Phát hiện bất biến số dư quỹ bị vi phạm. Giao dịch đã bị từ chối!"


# ----------------------------------------------------------------------
# Điểm danh & Anti-Cheat (Attendance)
# ----------------------------------------------------------------------
class AntiCheatException(BusinessException):
    status_code = 403
    default_message = "Phát hiện hành vi gian lận điểm danh!"


class SessionClosedException(BusinessException):
    status_code = 409
    default_message = "Phiên điểm danh đã đóng hoặc chưa mở."


class InvalidNonceException(AntiCheatException):
    default_message = "Mã xác thực phiên không đúng hoặc đã hết hiệu lực!"


# ----------------------------------------------------------------------
# Sự kiện (Events)
# ----------------------------------------------------------------------
class EventFullException(BusinessException):
    status_code = 409
    default_message = "Sự kiện đã đủ số lượng đăng ký tối đa!"


class DuplicateRegistrationException(BusinessException):
    status_code = 409
    default_message = "Bạn đã đăng ký sự kiện này rồi."


class CycleDetectedException(BusinessException):
    status_code = 400
    default_message = "Phát hiện phụ thuộc vòng tròn (deadlock) giữa các task!"


class EventStatusException(BusinessException):
    status_code = 409
    default_message = "Trạng thái sự kiện không cho phép thao tác này."


# ----------------------------------------------------------------------
# Gamification
# ----------------------------------------------------------------------
class XPDailyCapExceededException(BusinessException):
    status_code = 429
    default_message = "Bạn đã đạt trần 300 XP trong ngày hôm nay. Hãy quay lại vào mai!"


# ----------------------------------------------------------------------
# Dữ liệu & Truy cập
# ----------------------------------------------------------------------
class NotFoundException(BusinessException):
    status_code = 404
    default_message = "Không tìm thấy tài nguyên yêu cầu."


class ForbiddenException(BusinessException):
    status_code = 403
    default_message = "Bạn không có quyền thực hiện hành động này."


class DuplicateDataException(BusinessException):
    status_code = 409
    default_message = "Dữ liệu đã tồn tại trong hệ thống."


class FileValidationException(BusinessException):
    status_code = 400
    default_message = "Tệp tải lên không hợp lệ."


class ValidationException(BusinessException):
    status_code = 400
    default_message = "Dữ liệu không hợp lệ."
