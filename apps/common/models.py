"""
Abstract BaseModel — created_at / updated_at dùng chung toàn hệ thống.
"""
from django.db import models


class TimeStampedModel(models.Model):
    """Model trừu tượng cung cấp dấu vết thời gian tạo/cập nhật."""

    created_at = models.DateTimeField("Ngày tạo", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("Ngày cập nhật", auto_now=True)

    class Meta:
        abstract = True
