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

from apps.funds.models import FundTransaction


class IFundRepository(ABC):
    """Hợp đồng (interface) truy cập dữ liệu Sổ quỹ — phụ thuộc trừu tượng (DIP)."""

    @abstractmethod
    def get_last_transaction_for_update(self) -> Optional[FundTransaction]:
        """Lấy giao dịch MỚI NHẤT kèm pessimistic lock (select_for_update)."""

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
        from apps.funds.models import FundPeriodLock

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
            queryset = queryset.filter(ngay_gd__date__gte=from_date)
        if to_date:
            queryset = queryset.filter(ngay_gd__date__lte=to_date)
        return queryset

    def count_transactions_on_date(self, loai_gd: str, ngay: date) -> int:
        """Số giao dịch cùng loại phát sinh trong ngày `ngay` (múi giờ địa phương)."""
        return FundTransaction.objects.filter(
            loai_gd=loai_gd,
            ngay_gd__date=ngay,
        ).count()

    def exists_ma_phieu(self, ma_phieu: str) -> bool:
        """Mã phiếu đã tồn tại chưa — vòng lặp sinh mã sẽ tăng seq nếu trùng."""
        return FundTransaction.objects.filter(ma_phieu=ma_phieu).exists()
