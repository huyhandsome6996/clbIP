"""
Permission Classes — RBAC & chống IDOR/BOLA (Security Hardening §6).

Quy tắc bắt buộc: Mọi ViewSet object-level phải được bảo vệ bởi IsOwnerOrBCN.
"""
from rest_framework import permissions


def _is_board(request) -> bool:
    """Kiểm tra user hiện tại có vai trò BCN hoặc ADMIN hay không."""
    user = request.user
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, "role", None) in ("ADMIN", "BCN") or user.is_superuser)
    )


class IsOwnerOrBCN(permissions.BasePermission):
    """
    BCN/ADMIN: toàn quyền.
    Thành viên thường: CHỈ được thao tác trên bản ghi của chính mình (chống IDOR).
    """

    message = "Bạn chỉ có quyền truy cập dữ liệu của chính mình."

    def has_permission(self, request, view) -> bool:
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj) -> bool:
        if _is_board(request):
            return True
        owner = getattr(obj, "user", None)
        if owner is None:
            # obj là profile / record trung gian → đi qua thuộc tính member → user
            member = getattr(obj, "member", None)
            owner = getattr(member, "user", None) if member is not None else None
        return owner == request.user


class IsBCNOrAdmin(permissions.BasePermission):
    """Chỉ Ban Chủ Nhiệm hoặc Quản trị viên mới được thực hiện."""

    message = "Chức năng này chỉ dành cho Ban Chủ Nhiệm."

    def has_permission(self, request, view) -> bool:
        return _is_board(request)


class IsAdminOnly(permissions.BasePermission):
    """Chỉ ADMIN hệ thống."""

    message = "Chức năng này chỉ dành cho Quản trị viên hệ thống."

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, "role", None) == "ADMIN" or user.is_superuser)
        )


class IsReadOnlyForMembers(permissions.BasePermission):
    """Thành viên thường chỉ được ĐỌC; ghi phải là BCN/ADMIN."""

    message = "Bạn không có quyền thực hiện hành động này."

    def has_permission(self, request, view) -> bool:
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return _is_board(request)
