"""
check_deploy.py — Script tự verify cấu hình deploy Render
==========================================================
Kiểm tra toàn bộ biến môi trường + cấu hình Django + staticfiles
TRƯỚC KHI deploy. Chạy: python check_deploy.py

Exit codes:
    0 — Sẵn sàng deploy
    1 — Có lỗi cấu hình cần sửa
"""
import os
import sys
from typing import Any

# Đảm bảo settings load được
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

CHECKS_PASSED = 0
CHECKS_FAILED = 0
WARNINGS = 0


def check(name: str, condition: bool, hint: str = "", warn_only: bool = False) -> bool:
    """In kết quả 1 mục kiểm tra và đếm pass/fail."""
    global CHECKS_PASSED, CHECKS_FAILED, WARNINGS
    if condition:
        print(f"  ✅ {name}")
        CHECKS_PASSED += 1
        return True
    if warn_only:
        print(f"  ⚠️  {name} — {hint}")
        WARNINGS += 1
    else:
        print(f"  ❌ {name} — {hint}")
        CHECKS_FAILED += 1
    return False


def main() -> int:
    print("=" * 70)
    print("CLB IP ĐHSP Huế 2.0 — PRE-DEPLOY CHECK (Render)")
    print("=" * 70)

    # ------------------------------------------------------------------
    print("\n[1/6] Biến môi trường bắt buộc")
    check("PYTHON_VERSION >= 3.11", sys.version_info >= (3, 11),
          f"Đang chạy Python {sys.version_info.major}.{sys.version_info.minor}")
    check("DJANGO_SETTINGS_MODULE", bool(os.environ.get("DJANGO_SETTINGS_MODULE")),
          "chưa set (Render tự set qua render.yaml)")
    check("SECRET_KEY", bool(os.environ.get("SECRET_KEY")),
          "Render generateValue sẽ tự sinh khi deploy qua Blueprint")
    check("DATABASE_URL", bool(os.environ.get("DATABASE_URL")),
          "Render sẽ inject tự động qua fromDatabase khi dùng Blueprint", warn_only=True)
    check("DEBUG", os.environ.get("DEBUG", "False").lower() in ("false", "0", ""),
          "Production phải DEBUG=False")

    # ------------------------------------------------------------------
    print("\n[2/6] Django core")
    import django
    django.setup()
    from django.conf import settings

    check(f"Django {django.get_version()}", True)
    check("AUTH_USER_MODEL=authentication.User", settings.AUTH_USER_MODEL == "authentication.User")
    check("ALLOWED_HOSTS không rỗng", len(settings.ALLOWED_HOSTS) > 0,
          "set ALLOWED_HOSTS=.onrender.com cho production")

    # ------------------------------------------------------------------
    print("\n[3/6] Bảo mật production (Security Hardening)")
    check("DEBUG=False", not settings.DEBUG)
    check("Password hasher Argon2", "Argon2PasswordHasher" in settings.PASSWORD_HASHERS[0])
    check("JWT rotation + blacklist",
          settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS") and settings.SIMPLE_JWT.get("BLACKLIST_AFTER_ROTATION"))
    check("Throttling bật (chống DoS)", len(settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES", [])) >= 2)
    check("CORS không allow-all", not getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False))
    check("django-axes bật (chống brute-force)", getattr(settings, "AXES_ENABLED", False) or settings.TESTING)
    check("HSTS >= 1 năm", settings.SECURE_HSTS_SECONDS >= 31536000, warn_only=True)
    check("X-Frame-Options DENY", settings.X_FRAME_OPTIONS == "DENY")
    check("Payload limit 5MB", settings.DATA_UPLOAD_MAX_MEMORY_SIZE == 5 * 1024 * 1024)

    # ------------------------------------------------------------------
    print("\n[4/6] Apps & Database migration state")
    from django.core.management import call_command
    from django.db import connections

    db_conn = connections["default"]
    with db_conn.cursor() as cursor:
        cursor.execute("SELECT 1")
    check(f"Database kết nối OK ({db_conn.settings_dict['ENGINE'].split('.')[-1]})", True)

    try:
        call_command("migrate", "--check", verbosity=0)
        check("Migrations đồng bộ (không thiếu)", True)
    except SystemExit:
        check("Migrations đồng bộ", False, "chạy: python manage.py migrate")

    # ------------------------------------------------------------------
    print("\n[5/6] Danh sách API modules")
    expected_apps = ["authentication", "members", "funds", "events",
                     "attendance", "gamification", "documents", "posts"]
    for app in expected_apps:
        check(f"apps.{app}", f"apps.{app}" in settings.INSTALLED_APPS)

    # ------------------------------------------------------------------
    print("\n[6/6] Staticfiles & Deployment files")
    check("build.sh tồn tại", os.path.exists("build.sh"))
    check("build.sh có quyền execute", os.access("build.sh", os.X_OK))
    check("render.yaml tồn tại", os.path.exists("render.yaml"))
    check("Procfile tồn tại", os.path.exists("Procfile"))
    check("requirements.txt tồn tại", os.path.exists("requirements.txt"))

    static_root = getattr(settings, "STATIC_ROOT", None)
    check("STATIC_ROOT đã cấu hình", bool(static_root), "thiếu STATIC_ROOT trong settings")

    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"KẾT QUẢ: {CHECKS_PASSED} PASS | {CHECKS_FAILED} FAIL | {WARNINGS} WARNING")
    if CHECKS_FAILED == 0:
        print("🚀 SẴN SÀNG DEPLOY LÊN RENDER!")
        print("   Cách 1 (khuyên dùng): Render Dashboard → New + → Blueprint → chọn repo → Apply")
        print("   Cách 2: New + → Web Service → connect repo → Render sẽ đọc render.yaml")
        print("=" * 70)
        return 0
    print("❌ CÓ LỖI CẤU HÌNH — sửa các mục ❌ phía trên rồi chạy lại.")
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
