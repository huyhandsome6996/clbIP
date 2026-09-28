"""
App: authentication — Custom User (RBAC 3 vai trò, đăng nhập bằng Email).
Theo ERD: User (Auth, Role, JWT).
"""
from django.contrib.auth.models import AbstractUser
from django.db import models
from typing import Any, Optional


class User(AbstractUser):
    """
    Tài khoản hệ thống — kế thừa AbstractUser, đăng nhập bằng EMAIL.

    RBAC (Role-Based Access Control):
        - ADMIN:  Quản trị viên hệ thống (toàn quyền).
        - BCN:    Ban Chủ Nhiệm (quản lý nghiệp vụ CLB).
        - MEMBER: Thành viên thường (chỉ dữ liệu của mình).
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Quản trị viên"
        BCN = "BCN", "Ban Chủ Nhiệm"
        MEMBER = "MEMBER", "Thành viên"

    # Đăng nhập bằng email (USERNAME_FIELD)
    email: models.EmailField = models.EmailField("Địa chỉ email", unique=True)

    # Mã số sinh viên — unique, nullable cho giảng viên cố vấn / tài khoản admin
    mssv: models.CharField = models.CharField(
        "Mã số sinh viên", max_length=20, unique=True, null=True, blank=True
    )

    role: models.CharField = models.CharField(
        "Vai trò", max_length=10, choices=Role.choices, default=Role.MEMBER, db_index=True
    )

    is_active: models.BooleanField = models.BooleanField("Đang hoạt động", default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list = []  # tạo superuser chỉ cần email + password

    class Meta:
        db_table = "auth_user"
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    def __str__(self) -> str:
        return f"{self.email} ({self.get_role_display()})"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Tự sinh username từ email nếu chưa có (username vẫn giữ để tương thích admin)."""
        if not self.username and self.email:
            base = self.email.split("@")[0][:140]
            candidate = base
            suffix = 1
            # Tránh trùng username — thêm số thứ tự
            User_ = User  # noqa: N806 (alias local để tránh trùng tên class)
            while User_.objects.filter(username=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}{suffix}"
                suffix += 1
            self.username = candidate
        super().save(*args, **kwargs)

    # ----------------------- Tiện ích RBAC -----------------------
    @property
    def is_bcn(self) -> bool:
        """Là Ban Chủ Nhiệm hay ADMIN."""
        return self.role in (self.Role.ADMIN, self.Role.BCN) or self.is_superuser

    @property
    def is_admin(self) -> bool:
        return self.role == self.Role.ADMIN or self.is_superuser
