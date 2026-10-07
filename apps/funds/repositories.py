"""
Repository Layer — apps.funds
=============================
Tách biệt tầng truy vấn CSDL khỏi tầng nghiệp vụ (Repository Pattern — SKILL.md
Phần 1 §2.A, nguyên tắc Dependency Inversion).

`FundService` chỉ phụ thuộc vào trừu tượng `IFundRepository`, không đụng trực tiếp
vào ORM của `FundTransaction`. 100% truy vấn dùng Django ORM parameterized
(TUYỆT ĐỐI không raw SQL — Security Hardening §2.1).
"""
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from django.db.models import QuerySet

from apps.common.timeutils import local_day_range, local_range_inclusive
from apps.funds.models import FundLedgerAnchor, FundPeriodLock, FundTransaction


class IFundRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Sổ quỹ — phụ thuộc trừu tượng (DIP)."""

    @abstractmethod
    def get_last_transaction_for_update(self) -> Optional[FundTransaction]:
        """Lấy giao dịch MỚI NHẤT kèm pessimistic lock (select_for_update)."""

    @abstractmethod
    def get_ledger_anchor_for_update(self) -> "FundLedgerAnchor":
        """Khóa hàng NEO bi sổ (singleton pk=1) — serialization point chung
        cho mọi writer, kể cả khi SỔ RỖNG (review R04)."""

    @abstractmethod
    def get_last_transaction(self) -> Optional[FundTransaction]:
        """Lấy giao dịch mới nhất (không khóa bi — chỉ đọc)."""

    @abstractmethod
    def create_transaction(self, **fields) -> FundTransaction:
        """Ghi một giao dịch mới vào sổ quỹ."""

    @abstractmethod
    def get_all_ordered(self) -> QuerySet[FundTransaction]:
        """Toàn bộ giao dịch sắp theo thời gian tăng dần (phục vụ bất biến I1/I2)."""

    @abstractmethod
    def exists_locked_period_containing(self, ngay: date) -> bool:
        """Kiểm tra ngày cho trước có nằm trong một kỳ đã khóa sổ hay không."""

    @abstractmethod
    def filter_transactions(
        self,
        *,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        loai_gd: Optional[str] = None,
    ) -> QuerySet[FundTransaction]:
        """Lọc giao dịch theo khoảng ngày và loại giao dịch."""

    @abstractmethod
    def count_transactions_on_date(self, loai_gd: str, ngay: date) -> int:
        """Đếm số giao dịch cùng loại trong một ngày (dùng sinh số thứ tự mã phiếu)."""

    @abstractmethod
    def exists_ma_phieu(self, ma_phieu: str) -> bool:
        """Kiểm tra mã phiếu đã tồn tại trong DB hay chưa (chống trùng lặp)."""

    @abstractmethod
    def get_by_idempotency_key(self, key: str) -> Optional[FundTransaction]:
        """Tra cứu giao dịch theo Idempotency-Key (None nếu chưa tồn tại)."""

    @abstractmethod
    def exists_period_lock_by_name(self, ten_ky: str) -> bool:
        """Kỳ khóa sổ trùng tên đã tồn tại chưa (409 DuplicateData)."""

    @abstractmethod
    def create_period_lock(self, **fields) -> FundPeriodLock:
        """Tạo kỳ khóa sổ mới."""

    @abstractmethod
    def mark_transactions_locked_between(self, start_dt, end_dt) -> int:
        """Đóng băng mọi giao dịch trong khoảng [start_dt, end_dt] (1 UPDATE)."""

    @abstractmethod
    def get_period_locks(self) -> QuerySet[FundPeriodLock]:
        """Danh sách toàn bộ kỳ đã khóa sổ (theo ordering mặc định của model)."""

    @abstractmethod
    def aggregate_monthly_thu_chi(self, since_dt) -> list:
        """
        Tổng thu/chi GROUP BY tháng (TruncMonth ngay_gd) từ `since_dt` —
        dữ liệu biểu đồ trend dashboard BCN (QA-Audit đợt 3 — TASK 4).
        Trả list [{"month": "YYYY-MM", "thu": int, "chi": int}] tăng dần theo tháng.
        """


class DjangoFundRepository(IFundRepository):
    """Triển khai cụ thể bằng Django ORM cho `IFundRepository`."""

    def get_last_transaction_for_update(self) -> Optional[FundTransaction]:
        """
        Lấy bản ghi số dư gần nhất VỚI KHÓA BI (pessimistic locking).

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()` — chống race condition
        / double-spending khi 2 thủ quỹ cùng bấm ghi giao dịch đồng thời
        (Security Hardening §5.3).
        """
        return (
            FundTransaction.objects.select_for_update()
            .order_by("-id")
            .first()
        )

    def get_ledger_anchor_for_update(self) -> FundLedgerAnchor:
        """
        Khóa hàng NEO bi sổ (pk=1) — review R04.

        Trước đây chỉ khóa "dòng cuối" → sổ RỖNG không có hàng để khóa, hai
        giao dịch song song cùng đọc số dư 0 và cùng ghi → mất cập nhật chuỗi
        số dư. Hàng neo tồn tại vĩnh viễn (data migration 0004) nên luôn là
        chốt khóa ổn định đúng 1 hàng cho MỌI writer.

        Tự hồi phục: nếu hàng chưa có (DB cũ chưa chạy data-migration, hàng
        bị mất, hay môi trường test flush) → tạo ngay tại chỗ trong SAVEPOINT
        rồi khóa lại. Hai writer đua nhau tạo → thua IntegrityError ở
        savepoint (không hỏng transaction ngoài) → khóa hàng của bên thắng.

        ⚠️ Bắt buộc gọi bên trong `transaction.atomic()`.
        """
        try:
            return FundLedgerAnchor.objects.select_for_update().get(pk=1)
        except FundLedgerAnchor.DoesNotExist:
            from django.db import IntegrityError, transaction  # noqa: PLC0415

            try:
                with transaction.atomic():  # SAVEPOINT — lỗi cục bộ
                    FundLedgerAnchor.objects.create(
                        pk=1, ghi_chu="Hàng neo khóa bi sổ (tự hồi phục)"
                    )
            except IntegrityError:
                pass  # writer khác đã tạo — đi tiếp để khóa
            return FundLedgerAnchor.objects.select_for_update().get(pk=1)

    def get_last_transaction(self) -> Optional[FundTransaction]:
        """Giao dịch mới nhất — chỉ đọc, không khóa bi."""
        return FundTransaction.objects.order_by("-id").first()

    def create_transaction(self, **fields) -> FundTransaction:
        """Ghi giao dịch mới (INSERT một dòng duy nhất)."""
        return FundTransaction.objects.create(**fields)

    def get_all_ordered(self) -> QuerySet[FundTransaction]:
        """Toàn bộ sổ quỹ theo thứ tự thời gian tăng dần (khớp Meta.ordering)."""
        return FundTransaction.objects.order_by("ngay_gd", "id")

    def exists_locked_period_containing(self, ngay: date) -> bool:
        """True nếu `ngay` ∈ [tu_ngay, den_ngay] của ít nhất một kỳ khóa sổ."""
        return FundPeriodLock.objects.filter(
            tu_ngay__lte=ngay,
            den_ngay__gte=ngay,
        ).exists()

    def filter_transactions(
        self,
        *,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        loai_gd: Optional[str] = None,
    ) -> QuerySet[FundTransaction]:
        """Lọc giao dịch theo khoảng ngày (theo ngày địa phương) và loại giao dịch."""
        queryset = FundTransaction.objects.all()
        if loai_gd:
            queryset = queryset.filter(loai_gd=loai_gd)
        if from_date:
            start_dt, _ = local_range_inclusive(from_date, from_date)
            queryset = queryset.filter(ngay_gd__gte=start_dt)
        if to_date:
            _, end_dt = local_range_inclusive(to_date, to_date)
            queryset = queryset.filter(ngay_gd__lt=end_dt)
        return queryset

    def count_transactions_on_date(self, loai_gd: str, ngay: date) -> int:
        """Số giao dịch cùng loại phát sinh trong ngày `ngay` (múi giờ địa phương)."""
        day_start, day_end = local_day_range(ngay)
        return FundTransaction.objects.filter(
            loai_gd=loai_gd,
            ngay_gd__gte=day_start,
            ngay_gd__lt=day_end,
        ).count()

    def exists_ma_phieu(self, ma_phieu: str) -> bool:
        """Mã phiếu đã tồn tại chưa — vòng lặp sinh mã sẽ tăng seq nếu trùng."""
        return FundTransaction.objects.filter(ma_phieu=ma_phieu).exists()

    def get_by_idempotency_key(self, key: str) -> Optional[FundTransaction]:
        """Tra cứu giao dịch theo Idempotency-Key (None nếu chưa tồn tại)."""
        return FundTransaction.objects.filter(idempotency_key=key).first()

    def exists_period_lock_by_name(self, ten_ky: str) -> bool:
        return FundPeriodLock.objects.filter(ten_ky=ten_ky).exists()

    def create_period_lock(self, **fields) -> FundPeriodLock:
        return FundPeriodLock.objects.create(**fields)

    def mark_transactions_locked_between(self, start_dt, end_dt) -> int:
        # Update hàng loạt 1 query — đóng băng lịch sử trong khoảng kỳ
        # (range datetime di động đa CSDL — thay cho __date, xem timeutils)
        return FundTransaction.objects.filter(
            ngay_gd__gte=start_dt,
            ngay_gd__lt=end_dt,
        ).update(is_locked=True)

    def get_period_locks(self) -> QuerySet[FundPeriodLock]:
        """Toàn bộ kỳ khóa sổ — sắp theo Meta.ordering của model (-tu_ngay)."""
        return FundPeriodLock.objects.all()

    def aggregate_monthly_thu_chi(self, since_dt) -> list:
        """
        Tổng thu/chi GROUP BY tháng — dùng cho biểu đồ "Xu hướng tài chính"
        trên dashboard BCN (TASK 4).

        PORTABLE TIME (apps/common/timeutils): KHÔNG dùng TruncMonth vì
        lookup timezone của MySQL phụ thuộc bảng tz của DB (MariaDB
        user-space thường không có). Lọc bằng khoảng datetime + nhóm theo
        tháng LOCAL trong Python — chạy đúng trên mọi CSDL. Số dòng trong
        cửa sổ vài tháng thuộc cỡ nhỏ (CLB), group Python là đủ.
        """
        from django.utils import timezone  # noqa: PLC0415

        rows = (
            FundTransaction.objects.filter(ngay_gd__gte=since_dt)
            .values_list("ngay_gd", "loai_gd", "so_tien")
            .order_by("ngay_gd")
        )
        buckets: dict = {}
        for ngay_gd, loai_gd, so_tien in rows:
            local_dt = timezone.localtime(ngay_gd)
            key = f"{local_dt:%Y-%m}"
            bucket = buckets.setdefault(key, {"month": key, "thu": 0, "chi": 0})
            if loai_gd == FundTransaction.LoaiGiaoDich.THU:
                bucket["thu"] += so_tien
            elif loai_gd == FundTransaction.LoaiGiaoDich.CHI:
                bucket["chi"] += so_tien
        return [buckets[key] for key in sorted(buckets)]
