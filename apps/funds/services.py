"""
Service Layer — apps.funds
==========================
100% business logic của Sổ quỹ nằm ở đây (Clean Layered — Rule 1 & 2):

- **Factory Pattern**: `TransactionFactory` khởi tạo `IncomeTransaction` /
  `ExpenseTransaction` — mỗi loại tự biết cách cập nhật số dư và sinh mã phiếu
  (OCP: thêm loại giao dịch mới không phải sửa code lõi).
- **Toàn vẹn tài chính (ZERO-TOLERANCE)**: mọi biến động quỹ chạy trong
  `transaction.atomic()` + pessimistic locking `select_for_update()` trên bản ghi
  số dư gần nhất (chống double-spending — Security Hardening §5.3), và được kiểm
  chứng bởi `FundInvariantsEngine` TRƯỚC KHI ghi (DSA 5 — bất biến I1→I4).
"""
import logging
from abc import ABC, abstractmethod
from datetime import date
from io import BytesIO
from typing import ClassVar, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.exceptions import (
    DuplicateDataException,
    InsufficientFundException,
    PeriodLockedException,
    ValidationException,
)
from apps.funds.models import FundPeriodLock, FundTransaction
from apps.funds.repositories import IFundRepository, DjangoFundRepository
from apps.common.timeutils import local_range_inclusive
from core.algorithms.fund_invariants import FundInvariantsEngine

logger = logging.getLogger(__name__)

# Whitelist sắp xếp cho API danh sách (chống SQL Injection qua order_by — §2.1)
ALLOWED_SORT_FIELDS: frozenset[str] = frozenset(
    {"ngay_gd", "-ngay_gd", "so_tien", "-so_tien"}
)
DEFAULT_SORT: str = "-ngay_gd"


# ======================================================================
# FACTORY PATTERN — các loại giao dịch thu/chi
# ======================================================================
class BaseFundTransaction(ABC):
    """
    Lớp gốc trừu tượng cho một "chiến lược" giao dịch quỹ.

    Mỗi loại giao dịch tự chịu trách nhiệm:
        1. `apply_to_balance`  — cách cập nhật số dư (I: cộng / E: trừ).
        2. `build_ma_phieu`    — quy tắc sinh mã phiếu (PT/PC + YYYYMMDD + seq 3 chữ số).
    """

    loai_gd: ClassVar[str]
    prefix: ClassVar[str]

    def __init__(self, so_tien: int, ngay_gd: date) -> None:
        self.so_tien: int = int(so_tien)
        self.ngay_gd: date = ngay_gd

    @abstractmethod
    def apply_to_balance(self, balance: int) -> int:
        """Trả về số dư mới sau khi áp dụng giao dịch lên `balance` hiện tại."""

    def build_ma_phieu(self, seq: int) -> str:
        """
        Sinh mã phiếu theo format: <prefix><YYYYMMDD><seq 3 chữ số>.
        Ví dụ: PT20260928001 (phiếu thu số 1 ngày 28/09/2026).
        """
        return f"{self.prefix}{self.ngay_gd:%Y%m%d}{seq:03d}"


class IncomeTransaction(BaseFundTransaction):
    """Phiếu THU — cộng tiền vào quỹ, mã phiếu tiền tố `PT`."""

    loai_gd = "THU"
    prefix = "PT"

    def apply_to_balance(self, balance: int) -> int:
        """Khoản thu làm tăng số dư."""
        return balance + self.so_tien


class ExpenseTransaction(BaseFundTransaction):
    """Phiếu CHI — trừ tiền khỏi quỹ, mã phiếu tiền tố `PC`."""

    loai_gd = "CHI"
    prefix = "PC"

    def apply_to_balance(self, balance: int) -> int:
        """Khoản chi làm giảm số dư (bất biến I3 đã được engine kiểm chứng trước)."""
        return balance - self.so_tien


class TransactionFactory:
    """Factory khởi tạo đối tượng giao dịch theo `loai_gd` (Open/Closed Principle)."""

    _registry: ClassVar[dict[str, type[BaseFundTransaction]]] = {
        "THU": IncomeTransaction,
        "CHI": ExpenseTransaction,
    }

    @classmethod
    def create(
        cls, loai_gd: str, *, so_tien: int, ngay_gd: date
    ) -> BaseFundTransaction:
        """
        Tạo strategy giao dịch tương ứng.

        Raises:
            ValidationException: nếu `loai_gd` không nằm trong {THU, CHI}.
        """
        strategy_cls = cls._registry.get(loai_gd)
        if strategy_cls is None:
            raise ValidationException(
                f"Loại giao dịch không hợp lệ: {loai_gd!r} (chỉ nhận 'THU' hoặc 'CHI')."
            )
        return strategy_cls(so_tien=so_tien, ngay_gd=ngay_gd)


# ======================================================================
# FUND SERVICE — nghiệp vụ sổ quỹ
# ======================================================================
class FundService:
    """
    Facade nghiệp vụ Sổ quỹ (toàn bộ classmethod, phụ thuộc `IFundRepository`).

    Điểm bất biến bắt buộc:
        - Mọi ghi sổ chạy trong `transaction.atomic()`.
        - Số dư luôn đọc từ bản ghi gần nhất SAU KHI `select_for_update()`.
        - `FundInvariantsEngine.validate_new_transaction` phải pass trước khi INSERT.
    """

    _repository_class: ClassVar[type[IFundRepository]] = DjangoFundRepository

    @classmethod
    def _repo(cls) -> IFundRepository:
        """Factory method cho repository — cho phép DI khi unit test."""
        return cls._repository_class()

    # ------------------------------------------------------------------
    # GHI SỔ GIAO DỊCH
    # ------------------------------------------------------------------
    @classmethod
    def execute_transaction(
        cls,
        loai_gd: str,
        so_tien: int,
        nguoi_thuc_hien: str,
        hinh_thuc: str = FundTransaction.HinhThuc.TIEN_MAT,
        ngay_gd: Optional[object] = None,
        ghi_chu: str = "",
        created_by: Optional[object] = None,
        event: Optional[object] = None,
        idempotency_key: Optional[str] = None,
    ) -> FundTransaction:
        """
        Ghi một phiếu thu/chi vào sổ quỹ — nguyên tố (atomic) & chống double-spending.

        Quy trình 7 bước (tất cả trong 1 DB transaction):
            1. Khóa bi bản ghi số dư gần nhất (`select_for_update`) → số dư hiện tại.
            1.5. Idempotency: nếu `idempotency_key` đã tồn tại (kiểm tra SAU khi
               giữ khóa bi — hai request song song cùng key tuần tự hóa ở bước 1)
               → trả lại giao dịch cũ, KHÔNG ghi thêm (QA-Audit nhóm 3).
            2. Kiểm tra khóa sổ kỳ: ngày giao dịch rơi vào kỳ đã khóa → chặn (409).
            3. `FundInvariantsEngine.validate_new_transaction` kiểm chứng bất biến:
               so_tien > 0, loại hợp lệ, CHI không làm số dư âm (I3).
            4. Tính số dư mới qua Factory strategy (THU: +, CHI: −).
            5. Sinh `ma_phieu` duy nhất (PT/PC + YYYYMMDD + seq, while-loop chống trùng).
            6. INSERT `FundTransaction` với `so_du_sau` = số dư mới.

        Args:
            loai_gd: 'THU' hoặc 'CHI'.
            so_tien: số tiền VNĐ (> 0).
            nguoi_thuc_hien: tên người thực hiện giao dịch.
            hinh_thuc: 'TIEN_MAT' hoặc 'CHUYEN_KHOAN'.
            ngay_gd: thời điểm giao dịch (mặc định `timezone.now()`).
            ghi_chu: nội dung ghi chú.
            created_by: User tạo phiếu (BCN đang đăng nhập).
            event: ActivityEvent liên quan (tùy chọn).
            idempotency_key: khóa chống ghi trùng (tùy chọn — dùng khi client
                gửi header `Idempotency-Key`).

        Returns:
            FundTransaction vừa tạo, hoặc bản ghi CŨ khi idempotency replay
            (có ma_phieu + so_du_sau).

        Raises:
            ValidationException: loai_gd/so_tien không hợp lệ (400).
            PeriodLockedException: ngày giao dịch thuộc kỳ đã khóa sổ (409).
            InsufficientFundException: khoản chi vượt số dư (400).
        """
        tx, _replayed = cls._execute_locked(
            loai_gd=loai_gd,
            so_tien=so_tien,
            nguoi_thuc_hien=nguoi_thuc_hien,
            hinh_thuc=hinh_thuc,
            ngay_gd=ngay_gd,
            ghi_chu=ghi_chu,
            created_by=created_by,
            event=event,
            idempotency_key=idempotency_key,
        )
        return tx

    @classmethod
    def execute_transaction_idempotent(
        cls,
        loai_gd: str,
        so_tien: int,
        nguoi_thuc_hien: str,
        hinh_thuc: str = FundTransaction.HinhThuc.TIEN_MAT,
        ngay_gd: Optional[object] = None,
        ghi_chu: str = "",
        created_by: Optional[object] = None,
        event: Optional[object] = None,
        idempotency_key: Optional[str] = None,
    ) -> "tuple[FundTransaction, bool]":
        """
        Ghi sổ có kiểm tra Idempotency-Key — trả về (giao dịch, có_phải_replay).

        View dùng cờ `replayed` để quyết định HTTP: 201 (ghi mới) hay 200
        (trả lại kết quả cũ — KHÔNG ghi thêm). Không có key → luôn ghi mới.

        Phòng hờ empty-ledger (QA-Audit nhóm 3): khi sổ quỹ TRỐNG, khóa bi ở
        bước 1 không khóa được dòng nào → 2 request song song cùng key có thể
        cùng qua bước kiểm tra và request sau đụng UNIQUE constraint. Trường
        hợp hiếm này được chuyển thành replay graceful (200) thay vì 500.
        """
        from django.db import IntegrityError  # noqa: PLC0415 — import cục bộ phòng hờ

        try:
            return cls._execute_locked(
                loai_gd=loai_gd,
                so_tien=so_tien,
                nguoi_thuc_hien=nguoi_thuc_hien,
                hinh_thuc=hinh_thuc,
                ngay_gd=ngay_gd,
                ghi_chu=ghi_chu,
                created_by=created_by,
                event=event,
                idempotency_key=idempotency_key,
            )
        except IntegrityError:
            if not idempotency_key:
                raise
            # Atomic đã rollback → tra cứu lại bản ghi request kia đã commit
            existing = cls._repo().get_by_idempotency_key(idempotency_key)
            if existing is not None:
                logger.info(
                    "Idempotency replay (UNIQUE backstop): key=%s → %s.",
                    idempotency_key, existing.ma_phieu,
                )
                return existing, True
            raise

    @classmethod
    def _execute_locked(
        cls,
        *,
        loai_gd: str,
        so_tien: int,
        nguoi_thuc_hien: str,
        hinh_thuc: str = FundTransaction.HinhThuc.TIEN_MAT,
        ngay_gd: Optional[object] = None,
        ghi_chu: str = "",
        created_by: Optional[object] = None,
        event: Optional[object] = None,
        idempotency_key: Optional[str] = None,
    ) -> "tuple[FundTransaction, bool]":
        """Lõi ghi sổ dùng chung cho execute_transaction / execute_transaction_idempotent."""
        if ngay_gd is None:
            ngay_gd = timezone.now()
        if timezone.is_naive(ngay_gd):
            # Phòng thủ: chuẩn hóa datetime naive sang múi giờ dự án
            ngay_gd = timezone.make_aware(ngay_gd)
        if hinh_thuc not in FundTransaction.HinhThuc.values:
            raise ValidationException(f"Hình thức không hợp lệ: {hinh_thuc!r}.")

        repo = cls._repo()
        # Ngày địa phương (Asia/Ho_Chi_Minh) — thống nhất với lookup `ngay_gd__date`
        ngay_dia_phuong: date = timezone.localdate(ngay_gd)
        strategy = TransactionFactory.create(loai_gd, so_tien=so_tien, ngay_gd=ngay_dia_phuong)

        with transaction.atomic():
            # Bước 1 — PESSIMISTIC LOCK: mọi writer cùng chờ nhau ở đây
            last = repo.get_last_transaction_for_update()
            current_balance: int = last.so_du_sau if last else 0

            # Bước 1.5 — IDEMPOTENCY (QA-Audit nhóm 3): kiểm tra SAU KHI giữ
            # khóa bi sổ. Hai request song song cùng key tuần tự hóa ở bước 1:
            # request sau thấy bản ghi request trước → trả lại kết quả cũ.
            # (Chỉ kiểm ở đây mới chống được race — kiểm trước atomic là vô ích.)
            if idempotency_key:
                existing = repo.get_by_idempotency_key(idempotency_key)
                if existing is not None:
                    logger.info(
                        "Idempotency replay: key=%s → trả lại %s, không ghi thêm.",
                        idempotency_key, existing.ma_phieu,
                    )
                    return existing, True

            # Bước 2 — khóa sổ kỳ: chặn mọi giao dịch phát sinh trong kỳ đã đóng
            if repo.exists_locked_period_containing(ngay_dia_phuong):
                raise PeriodLockedException()

            # Bước 3 — kiểm chứng bất biến số dư trước khi ghi
            try:
                FundInvariantsEngine.validate_new_transaction(current_balance, loai_gd, so_tien)
            except ValueError as exc:
                raise ValidationException(str(exc)) from exc
            except AssertionError as exc:
                raise InsufficientFundException(str(exc)) from exc

            # Bước 4 — số dư mới do strategy tự tính
            new_balance: int = strategy.apply_to_balance(current_balance)

            # Bước 5 — sinh mã phiếu duy nhất (while-loop tăng seq nếu trùng)
            ma_phieu = cls._generate_ma_phieu(repo, strategy, loai_gd, ngay_dia_phuong)

            # Bước 6 — ghi sổ
            tx = repo.create_transaction(
                ma_phieu=ma_phieu,
                loai_gd=loai_gd,
                so_tien=int(so_tien),
                so_du_sau=new_balance,
                nguoi_thuc_hien=nguoi_thuc_hien,
                hinh_thuc=hinh_thuc,
                ngay_gd=ngay_gd,
                ghi_chu=ghi_chu,
                created_by=created_by,
                event=event,
                idempotency_key=idempotency_key,
            )
            logger.info(
                "Ghi sổ quỹ %s (%s %sđ) — số dư mới: %sđ",
                ma_phieu, loai_gd, f"{so_tien:,}", f"{new_balance:,}",
            )
            return tx, False

    @classmethod
    def _generate_ma_phieu(
        cls,
        repo: IFundRepository,
        strategy: BaseFundTransaction,
        loai_gd: str,
        ngay: date,
    ) -> str:
        """
        Sinh mã phiếu duy nhất: seq = (số GD cùng loại trong ngày) + 1,
        while-loop kiểm tra DB và tăng seq nếu trùng (an toàn khi có nhiễu).
        """
        seq: int = repo.count_transactions_on_date(loai_gd, ngay) + 1
        ma_phieu: str = strategy.build_ma_phieu(seq)
        while repo.exists_ma_phieu(ma_phieu):
            seq += 1
            ma_phieu = strategy.build_ma_phieu(seq)
        return ma_phieu

    # ------------------------------------------------------------------
    # KHÓA SỔ KỲ
    # ------------------------------------------------------------------
    @classmethod
    def lock_period(
        cls,
        ten_ky: str,
        tu_ngay: date,
        den_ngay: date,
        locked_by: Optional[object],
        ghi_chu: str = "",
    ) -> FundPeriodLock:
        """
        Khóa sổ một kỳ — đóng băng mọi giao dịch trong khoảng [tu_ngay, den_ngay].

        - Tạo bản ghi `FundPeriodLock`.
        - Cập nhật `is_locked=True` cho toàn bộ giao dịch trong khoảng
          (MỘT câu UPDATE duy nhất — tránh N+1).

        Raises:
            ValidationException: tu_ngay > den_ngay (400).
            DuplicateDataException: ten_ky đã tồn tại (409).
        """
        if tu_ngay > den_ngay:
            raise ValidationException("'Từ ngày' phải nhỏ hơn hoặc bằng 'Đến ngày'.")

        with transaction.atomic():
            if FundPeriodLock.objects.filter(ten_ky=ten_ky).exists():
                raise DuplicateDataException(f"Kỳ khóa sổ '{ten_ky}' đã tồn tại.")

            lock = FundPeriodLock.objects.create(
                ten_ky=ten_ky,
                tu_ngay=tu_ngay,
                den_ngay=den_ngay,
                locked_by=locked_by,
                ghi_chu=ghi_chu,
            )
            # Update hàng loạt 1 query — đóng băng lịch sử trong khoảng kỳ
            # (range datetime di động đa CSDL — thay cho __date, xem timeutils)
            start_dt, end_dt = local_range_inclusive(tu_ngay, den_ngay)
            FundTransaction.objects.filter(
                ngay_gd__gte=start_dt,
                ngay_gd__lt=end_dt,
            ).update(is_locked=True)

        logger.info("Khóa sổ kỳ '%s' (%s → %s)", ten_ky, tu_ngay, den_ngay)
        return lock

    # ------------------------------------------------------------------
    # THỐNG KÊ & DANH SÁCH
    # ------------------------------------------------------------------
    @classmethod
    def get_stats(cls) -> dict:
        """
        Thống kê tổng thu / tổng chi / số dư + cờ cảnh báo quỹ thấp.

        Returns:
            {"total_income": int, "total_expense": int, "balance": int,
             "low_balance": bool}  — low_balance khi balance < ngưỡng 200.000đ.
        """
        totals = FundInvariantsEngine.compute_totals(
            cls._repo().get_all_ordered().values("loai_gd", "so_tien")
        )
        threshold: int = settings.CLB_SETTINGS["FUND_LOW_BALANCE_THRESHOLD"]
        return {
            "total_income": totals["total_income"],
            "total_expense": totals["total_expense"],
            "balance": totals["balance"],
            "low_balance": totals["balance"] < threshold,
        }

    @classmethod
    def list_transactions(
        cls,
        *,
        loai_gd: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        sort: Optional[str] = None,
    ):
        """
        Truy vấn danh sách giao dịch cho API GET /funds/ (có lọc + sắp whitelist).

        Args:
            loai_gd: 'THU'/'CHI' (query param ?loai_gd=).
            from_date: 'YYYY-MM-DD' (?from_date=).
            to_date: 'YYYY-MM-DD' (?to_date=).
            sort: một trong whitelist {'ngay_gd','-ngay_gd','so_tien','-so_tien'};
                  ngoài whitelist → fallback '-ngay_gd' (chống SQLi qua order_by).

        Returns:
            QuerySet đã lọc + sắp xếp (phân trang do tầng View đảm nhiệm).
        """
        loai_gd = cls._validate_loai_gd_param(loai_gd)
        from_d = cls._parse_date_param("from_date", from_date)
        to_d = cls._parse_date_param("to_date", to_date)

        sort_value = sort or DEFAULT_SORT
        if sort_value not in ALLOWED_SORT_FIELDS:
            sort_value = DEFAULT_SORT

        queryset = cls._repo().filter_transactions(
            from_date=from_d, to_date=to_d, loai_gd=loai_gd
        )
        # Thêm 'id' làm khóa phụ để thứ tự ổn định (deterministic paging)
        return queryset.order_by(sort_value, "id")

    # ------------------------------------------------------------------
    # XUẤT EXCEL
    # ------------------------------------------------------------------
    @classmethod
    def export_excel(cls) -> tuple[bytes, str]:
        """
        Xuất toàn bộ sổ quỹ ra file Excel (sheet 'Sổ quỹ').

        Returns:
            (bytes nội dung xlsx, tên file 'so_quy_clbip.xlsx').
        """
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Sổ quỹ"
        ws.append(
            [
                "Mã phiếu", "Loại", "Số tiền", "Số dư sau", "Người thực hiện",
                "Hình thức", "Thời gian", "Ghi chú", "Khóa",
            ]
        )
        for tx in cls._repo().get_all_ordered():
            ws.append(
                [
                    tx.ma_phieu,
                    tx.get_loai_gd_display(),
                    f"{tx.so_tien:,}",
                    f"{tx.so_du_sau:,}",
                    tx.nguoi_thuc_hien,
                    tx.get_hinh_thuc_display(),
                    timezone.localtime(tx.ngay_gd).strftime("%d/%m/%Y %H:%M"),
                    tx.ghi_chu,
                    "Đã khóa" if tx.is_locked else "",
                ]
            )

        buffer = BytesIO()
        wb.save(buffer)
        filename = "so_quy_clbip.xlsx"
        logger.info("Xuất sổ quỹ Excel: %s (%d giao dịch)", filename, ws.max_row - 1)
        return buffer.getvalue(), filename

    # ------------------------------------------------------------------
    # TIỆN ÍCH VALIDATE THAM SỐ QUERY
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_loai_gd_param(loai_gd: Optional[str]) -> Optional[str]:
        """Chỉ chấp nhận 'THU'/'CHI' — giá trị khác → 400 (whitelist filter)."""
        if loai_gd in (None, ""):
            return None
        if loai_gd not in FundTransaction.LoaiGiaoDich.values:
            raise ValidationException(
                f"Tham số loai_gd không hợp lệ: {loai_gd!r} (chỉ nhận 'THU' hoặc 'CHI')."
            )
        return loai_gd

    @staticmethod
    def _parse_date_param(param_name: str, raw: Optional[str]) -> Optional[date]:
        """Parse chuỗi 'YYYY-MM-DD' từ query param; sai định dạng → 400."""
        from django.utils.dateparse import parse_date

        if raw in (None, ""):
            return None
        parsed = parse_date(str(raw))
        if parsed is None:
            raise ValidationException(
                f"Tham số {param_name} không hợp lệ: {raw!r} (định dạng yêu cầu YYYY-MM-DD)."
            )
        return parsed
