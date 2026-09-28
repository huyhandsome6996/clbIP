"""
App: authentication — Custom User (RBAC 3 vai trò, đăng nhập bằng Email).
Theo ERD: User (Auth, Role, JWT).
"""
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from typing import Any, Optional


class UserManager(BaseUserManager):
    """
    Custom User Manager — đăng nhập bằng EMAIL.
    `create_user(email=..., password=...)` không cần username (tự sinh từ email).
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str, **extra_fields: Any) -> "User":
        """Tạo user với email bắt buộc; username tự sinh nếu thiếu."""
        if not email:
            raise ValueError("Email là bắt buộc.")
        email = self.normalize_email(email)
        username = extra_fields.pop("username", None)
        if not username:
            username = email.split("@")[0][:140]
            # Đảm bảo username unique — thêm số thứ tự nếu trùng
            suffix = 1
            while User.objects.filter(username=username).exists():
                username = f"{email.split('@')[0][:130]}{suffix}"
                suffix += 1
            extra_fields["username"] = username
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: Optional[str] = None, **extra_fields: Any) -> "User":
        """Tạo user thường (member)."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields: Any) -> "User":
        """Tạo superuser (ADMIN)."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser phải có is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser phải có is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


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

    objects = UserManager()

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
