"""
App: gamification — Badge (Huy hiệu), MemberBadge (Bộ sưu tập),
XpLedger (Sổ XP với idempotency key + trần 300 XP/ngày).
Client TUYỆT ĐỐI KHÔNG được gửi XP — mọi điểm chỉ sinh từ sự kiện đã xác minh.
"""
from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel


class Badge(TimeStampedModel):
    """Định nghĩa huy hiệu thành tích (Code Ninja, 100% chuyên cần...)."""

    ma_badge: models.CharField = models.CharField(
        "Mã huy hiệu", max_length=50, unique=True, db_index=True
    )
    ten_badge: models.CharField = models.CharField("Tên huy hiệu", max_length=100)
    mo_ta: models.CharField = models.CharField("Mô tả điều kiện mở khóa", max_length=255)
    icon: models.CharField = models.CharField(
        "Icon (emoji/tên icon)", max_length=20, blank=True, default="🏅"
    )

    class Meta:
        db_table = "badges"
        verbose_name = "Huy hiệu"
        verbose_name_plural = "Huy hiệu"
        ordering = ["ma_badge"]

    def __str__(self) -> str:
        return f"{self.icon} {self.ten_badge}"


class MemberBadge(TimeStampedModel):
    """Huy hiệu mà thành viên đã mở khóa."""

    member: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile", on_delete=models.CASCADE, related_name="badges"
    )
    badge: models.ForeignKey = models.ForeignKey(
        Badge, on_delete=models.CASCADE, related_name="holders"
    )
    awarded_at: models.DateTimeField = models.DateTimeField("Thời điểm nhận", auto_now_add=True)

    class Meta:
        db_table = "member_badges"
        verbose_name = "Huy hiệu thành viên"
        verbose_name_plural = "Huy hiệu thành viên"
        ordering = ["-awarded_at"]
        constraints = [
            models.UniqueConstraint(fields=["member", "badge"], name="unique_badge_per_member")
        ]

    def __str__(self) -> str:
        return f"{self.member.ho_ten} — {self.badge.ten_badge}"


class XpLedger(TimeStampedModel):
    """
    Sổ cái XP — mỗi biến động XP được ghi 1 dòng:
    - idempotency_key: khóa chống cộng điểm lặp (chống spam request).
    - source: nguồn phát sinh (điểm danh / chia sẻ tài liệu / task...).
    Trần 300 XP/ngày được kiểm soát bởi GamificationService qua bảng này.
    """

    class Source(models.TextChoices):
        ATTENDANCE = "ATTENDANCE", "Điểm danh"
        DOCUMENT_SHARE = "DOCUMENT_SHARE", "Chia sẻ tài liệu"
        TASK_COMPLETION = "TASK_COMPLETION", "Hoàn thành task"
        EVENT_ORGANIZER = "EVENT_ORGANIZER", "Tổ chức sự kiện"
        BONUS = "BONUS", "Thưởng khác"

    member: models.ForeignKey = models.ForeignKey(
        "members.MemberProfile", on_delete=models.CASCADE, related_name="xp_ledger"
    )
    amount: models.IntegerField = models.IntegerField("Số XP thay đổi")
    reason: models.CharField = models.CharField("Lý do", max_length=255)
    source: models.CharField = models.CharField(
        "Nguồn", max_length=20, choices=Source.choices, default=Source.BONUS
    )
    idempotency_key: models.CharField = models.CharField(
        "Khóa chống lặp", max_length=255, unique=True, null=True, blank=True, db_index=True
    )

    class Meta:
        db_table = "xp_ledger"
        verbose_name = "Sổ XP"
        verbose_name_plural = "Sổ XP"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.member.ho_ten} {'+' if self.amount >= 0 else ''}{self.amount} XP ({self.source})"
