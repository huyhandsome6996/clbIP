"""
App: documents — Document (Kho tài liệu học thuật, nhóm chuyên môn, Trie autocomplete).
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Document(TimeStampedModel):
    """Tài liệu trong Kho Báu Tài Liệu Học Thuật — tìm kiếm qua Prefix Trie."""

    class Nhom(models.TextChoices):
        CHUYEN_MON = "CHUYEN_MON", "Chuyên môn"
        NGHIEP_VU = "NGHIEP_VU", "Nghiệp vụ"
        KY_NANG = "KY_NANG", "Kỹ năng"

    tieu_de: models.CharField = models.CharField("Tiêu đề tài liệu", max_length=255)
    nhom: models.CharField = models.CharField(
        "Nhóm tài liệu", max_length=15, choices=Nhom.choices, db_index=True
    )
    # Tag chủ đề phân tách bằng dấu phẩy: "C++, Web, Đề thi"
    tags: models.CharField = models.CharField("Tags chủ đề", max_length=255, blank=True, default="")
    mo_ta: models.TextField = models.TextField("Mô tả", blank=True, default="")

    file: models.FileField = models.FileField(
        "Tệp tài liệu", upload_to="documents/%Y/%m/", max_length=500
    )
    file_type: models.CharField = models.CharField("Loại tệp", max_length=10, blank=True, default="")
    file_size: models.BigIntegerField = models.BigIntegerField("Kích thước (bytes)", default=0)

    luot_tai: models.IntegerField = models.IntegerField("Lượt tải", default=0, db_index=True)
    uploaded_by: models.ForeignKey = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="documents_uploaded",
        verbose_name="Người chia sẻ",
    )

    class Meta:
        db_table = "documents"
        verbose_name = "Tài liệu"
        verbose_name_plural = "Kho tài liệu"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tieu_de} ({self.get_nhom_display()})"

    @property
    def file_ext(self) -> str:
        """Phần mở rộng của tệp (đã lowercase, có dấu chấm)."""
        import os

        return os.path.splitext(self.file.name)[1].lower()
