"""
App: funds — FundTransaction (Sổ quỹ thu/chi) & FundPeriodLock (Khóa sổ định kỳ).
Bất biến số dư được bảo vệ bởi FundInvariantsEngine + select_for_update.
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class FundTransaction(TimeStampedModel):
    """Một giao dịch thu/chi của quỹ CLB — số dư lũ kế được kiểm soát qua Transaction."""

    class LoaiGiaoDich(models.TextChoices):
        THU = "THU", "Khoản thu"
        CHI = "CHI", "Khoản chi"

    class HinhThuc(models.TextChoices):
        TIEN_MAT = "TIEN_MAT", "Tiền mặt"
        CHUYEN_KHOAN = "CHUYEN_KHOAN", "Chuyển khoản"

    ma_phieu: models.CharField = models.CharField(
        "Mã phiếu (PT/PC...)", max_length=20, unique=True, db_index=True
    )
    loai_gd: models.CharField = models.CharField(
        "Loại giao dịch", max_length=5, choices=LoaiGiaoDich.choices, db_index=True
    )
    so_tien: models.BigIntegerField = models.BigIntegerField("Số tiền (VNĐ)")
    so_du_sau: models.BigIntegerField = models.BigIntegerField(
        "Số dư sau giao dịch", default=0
    )
    nguoi_thuc_hien: models.CharField = models.CharField(
        "Người thực hiện", max_length=150
    )
    hinh_thuc: models.CharField = models.CharField(
        "Hình thức", max_length=15, choices=HinhThuc.choices, default=HinhThuc.TIEN_MAT
    )
    ngay_gd: models.DateTimeField = models.DateTimeField(
        "Thời gian giao dịch", db_index=True
    )
    ghi_chu: models.TextField = models.TextField("Ghi chú", blank=True, default="")
    is_locked: models.BooleanField = models.BooleanField(
        "Thuộc kỳ đã khóa sổ", default=False
    )
    # Idempotency (QA-Audit nhóm 3): client gửi "Idempotency-Key" khi ghi sổ —
    # trùng khóa → trả lại giao dịch cũ, KHÔNG ghi thêm (chống double-submit
    # khi mạng chập chờn/nhấn nút 2 lần). Unique ở tầng DB làm backstop.
    idempotency_key: models.CharField = models.CharField(
        "Khóa chống ghi trùng",
        max_length=64,
        unique=True,  # unique index — không cần db_index riêng
        null=True,    # nhiều NULL hợp lệ (giao dịch không dùng khóa)
        blank=True,
    )
    # Vân tay nội dung yêu cầu (audit F02): SHA-256 của các trường nghiệp vụ
    # (actor, loại, số tiền, người thực hiện, hình thức, ngày GD client gửi,
    # ghi chú, event). Cùng key + cùng vân tay → replay an toàn; cùng key +
    # vân tay KHÁC → 409 IdempotencyKeyConflictException. NULL = bản ghi legacy
    # trước khi có field (đối chiếu bằng các trường lưu trong DB — xem service).
    request_fingerprint: models.CharField = models.CharField(
        "Vân tay nội dung yêu cầu (idempotency)",
        max_length=64,
        null=True,
        blank=True,
        db_index=True,
        editable=False,
    )

    # Liên kết tùy chọn
    created_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fund_transactions",
        verbose_name="Người tạo phiếu",
    )
    event: models.ForeignKey = models.ForeignKey(
        "events.ActivityEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fund_transactions",
        verbose_name="Sự kiện liên quan",
    )
    hoa_don: models.FileField = models.FileField(
        "Hóa đơn đính kèm",
        upload_to="funds/invoices/%Y/%m/",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "fund_transactions"
        verbose_name = "Giao dịch quỹ"
        verbose_name_plural = "Sổ quỹ"
        ordering = ["ngay_gd", "id"]

    def __str__(self) -> str:
        return f"{self.ma_phieu} — {self.get_loai_gd_display()} {self.so_tien:,}₫"


class FundPeriodLock(TimeStampedModel):
    """Khóa sổ định kỳ — đóng băng mọi giao dịch trong khoảng thời gian."""

    ten_ky: models.CharField = models.CharField("Tên kỳ khóa sổ", max_length=50, unique=True)
    tu_ngay: models.DateField = models.DateField("Từ ngày")
    den_ngay: models.DateField = models.DateField("Đến ngày")
    locked_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="fund_period_locks",
        verbose_name="Người khóa sổ",
    )
    locked_at: models.DateTimeField = models.DateTimeField("Thời điểm khóa", auto_now_add=True)
    ghi_chu: models.TextField = models.TextField("Ghi chú", blank=True, default="")

    class Meta:
        db_table = "fund_period_locks"
        verbose_name = "Khóa sổ quỹ"
        verbose_name_plural = "Khóa sổ quỹ"
        ordering = ["-tu_ngay"]

    def __str__(self) -> str:
        return f"Kỳ {self.ten_ky} ({self.tu_ngay} → {self.den_ngay})"


class FundLedgerAnchor(TimeStampedModel):
    """
    Hàng NEO khóa bi sổ (review R04 — 07/10/2026).

    Vấn đề: trước đây mọi writer chỉ khóa "bản ghi MỚI NHẤT" của sổ
    (`get_last_transaction_for_update`). Sổ RỖNG thì không có hàng nào để
    khóa → 2 giao dịch song song cùng đọc số dư 0 và cùng ghi → mất cập nhật
    chuỗi số dư (Σthu − Σchi ≠ so_du của dòng cuối).

    Giải pháp: MỌI writer của sổ quỹ `select_for_update()` đúng hàng neo
    singleton này TRƯỚC KHI đọc/ghi — sổ rỗng hay có dữ liệu đều được tuần
    tự hóa như nhau. Hàng được tạo bằng data migration (pk=1) và KHÔNG BAO
    GIỜ bị xóa/ghi đổi nội dung (chỉ là chốt khóa, không mang nghiệp vụ).
    """

    ghi_chu: models.CharField = models.CharField(
        "Ghi chú kỹ thuật", max_length=200, blank=True, default="Hàng neo khóa bi sổ"
    )

    class Meta:
        db_table = "fund_ledger_anchor"
        verbose_name = "Hàng neo khóa bi sổ quỹ"
        verbose_name_plural = "Hàng neo khóa bi sổ quỹ"

    def __str__(self) -> str:
        return f"FundLedgerAnchor(pk={self.pk})"
