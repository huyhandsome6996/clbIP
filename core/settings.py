"""
============================================================
CLB IP ĐHSP Huế 2.0 — Django Settings (Render Ready)
Tuân thủ: CLBIP_Security_Hardening_Prompt.md (Defense-in-Depth)
Kiến trúc: Clean Layered Architecture (Models → Repos → Services → Serializers → ViewSets)
============================================================
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url

# ------------------------------------------------------------------
# 0. BASE PATHS & RUNTIME FLAGS
# ------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# Cờ nhận diện đang chạy unittest → tắt throttle/axes để test không bị nhiễu
TESTING = "test" in sys.argv

# ------------------------------------------------------------------
# 1. CORE SECURITY SETTINGS
# ------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-local-dev-key-thay-doi-khi-deploy-render",
)

DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")  # 'production' trên Render

ALLOWED_HOSTS: list[str] = [
    h.strip()
    for h in os.environ.get(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1,.onrender.com",
    ).split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "https://*.onrender.com,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]

# ------------------------------------------------------------------
# 2. APPLICATIONS
# ------------------------------------------------------------------
INSTALLED_APPS = [
    # Django defaults
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # Blacklist JWT khi logout / rotation
    "corsheaders",
    "drf_spectacular",       # OpenAPI 3.0 / Swagger UI
    "axes",                  # Chống brute-force đăng nhập (lockout 5 lần/15 phút)
    # Local apps (Clean Layered Architecture)
    "apps.common",
    "apps.authentication",
    "apps.members",
    "apps.funds",
    "apps.events",
    "apps.attendance",
    "apps.gamification",
    "apps.documents",
    "apps.posts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Phục vụ staticfiles trên Render
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",  # Chặn brute-force ở tầng middleware
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ------------------------------------------------------------------
# 3. DATABASE — PostgreSQL (Render) hoặc SQLite (local dev)
# ------------------------------------------------------------------
_db_url = os.environ.get("DATABASE_URL", "").strip()
if _db_url and not _db_url.startswith("file:"):  # Bỏ qua DATABASE_URL không phải DB thật
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            ssl_require=False,  # Render quản lý SSL qua sslmode trong URL
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 30},  # Tránh 'database is locked' khi test concurrency
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------
# 4. AUTHENTICATION — Custom User (đăng nhập bằng Email) + Argon2
# ------------------------------------------------------------------
AUTH_USER_MODEL = "authentication.User"

# Thuật toán băm mật khẩu kháng GPU (Argon2id) theo Security Hardening §4.2
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    # Axes backend PHẢI đứng đầu để chặn đăng nhập khi bị khóa
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Cấu hình django-axes: khóa tài khoản sau 5 lần sai liên tiếp, mở khóa sau 15 phút
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]  # Khóa theo cặp username+IP
AXES_RESET_ON_SUCCESS = True
AXES_ENABLED = not TESTING  # Tắt khi chạy unittest để không phá vỡ test suite
AXES_VERBOSE = True
AXES_LOCKOUT_CALLABLE = "apps.common.axes_callbacks.axes_lockout_response"

# ------------------------------------------------------------------
# 5. DJANGO REST FRAMEWORK + THROTTLING ĐA TẦNG (Chống DoS/DDoS)
# ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "apps.common.throttles.BurstRateThrottle",
        "apps.common.throttles.SustainedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",        # Khách vãng lai: 60 req/phút
        "user": "300/minute",       # Người dùng: 300 req/phút
        "burst": "10/second",       # Chống flood burst ngắn hạn
        "sustained": "1500/hour",   # Giới hạn bền vững theo giờ
        "auth_login": "5/minute",   # Đăng nhập: 5 lần/phút (chống dò mật khẩu)
        "checkin": "3/minute",      # Điểm danh GPS: 3 lần/phút
        "feedback": "2/minute",     # Góp ý/Poll: 2 lần/phút (chống spam)
    },
}

# ------------------------------------------------------------------
# 6. JWT (SimpleJWT) — Token Hardening theo Security Hardening §4.3
# ------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),   # Access token ngắn hạn
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),      # Refresh token 7 ngày
    "ROTATE_REFRESH_TOKENS": True,                    # Token rotation
    "BLACKLIST_AFTER_ROTATION": True,                 # Vô hiệu hóa refresh cũ
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ------------------------------------------------------------------
# 7. CORS — Whitelist nghiêm ngặt, TUYỆT ĐỐI KHÔNG allow-all trên production
# ------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://clbip-hue.onrender.com",
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# 8. SECURITY HEADERS (Production Hardening)
# ------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"  # Chống Clickjacking
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SECURE_HSTS_SECONDS = 31536000 if DJANGO_ENV == "production" else 0  # 1 năm HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = DJANGO_ENV == "production"
SESSION_COOKIE_SECURE = DJANGO_ENV == "production"
CSRF_COOKIE_SECURE = DJANGO_ENV == "production"
SESSION_COOKIE_HTTPONLY = True

# Giới hạn kích thước payload — chống Slowloris / upload rác cạn RAM (§3.2)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024          # 5 MB cho JSON/form body
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024          # >5MB ghi ra temp file đĩa

# ------------------------------------------------------------------
# 9. I18N & TIMEZONE
# ------------------------------------------------------------------
LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------
# 10. STATIC & MEDIA (WhiteNoise + Render ephemeral disk)
# ------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ------------------------------------------------------------------
# 11. SPECTACULAR — OpenAPI 3.0 / Swagger UI tại /api/docs/
# ------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "CLB IP ĐHSP Huế 2.0 — Backend API",
    "DESCRIPTION": (
        "Hệ thống quản lý toàn diện CLB IP ĐHSP Huế: thành viên, quỹ, sự kiện, "
        "điểm danh GPS chống gian lận, gamification XP/Leaderboard, kho tài liệu "
        "và bảng tin. Xây dựng theo Clean Layered Architecture + DSA."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "TAGS": [
        {"name": "Authentication", "description": "JWT: đăng nhập, refresh, thông tin user"},
        {"name": "Members", "description": "Quản lý thành viên, hồ sơ 360°, Excel"},
        {"name": "Funds", "description": "Quỹ CLB: thu/chi, khóa sổ, bất biến số dư"},
        {"name": "Events", "description": "Sự kiện, vé QR, DAG công việc, dự trù kinh phí"},
        {"name": "Attendance", "description": "Phiên điểm danh GPS + Anti-Cheat Engine"},
        {"name": "Gamification", "description": "XP, huy hiệu, bảng vàng Min-Heap"},
        {"name": "Documents", "description": "Kho tài liệu + Trie autocomplete"},
        {"name": "Posts", "description": "Bảng tin, ghim bài, hòm thư góp ý ẩn danh"},
    ],
}

# ------------------------------------------------------------------
# 12. NGHIỆP VỤ ĐẶC THÙ (Business Constants)
# ------------------------------------------------------------------
CLB_SETTINGS = {
    # Cảnh báo quỹ thấp: số dư < 200.000 VNĐ → cảnh báo vàng trên Dashboard BCN
    "FUND_LOW_BALANCE_THRESHOLD": 200_000,
    # Trần XP tối đa 1 thành viên có thể nhận trong 1 ngày (chống spam/cày ảo)
    "DAILY_XP_CAP": 300,
    # Ngưỡng phát hiện dịch chuyển bất khả thi (km/h) — Fake GPS teleportation
    "MAX_TRAVEL_SPEED_KMH": 100,
    # Độ chính xác GPS tối đa cho phép (mét) — bỏ qua tín hiệu quá kém
    "MAX_GPS_ACCURACY_METERS": 100,
    # Cửa sổ xoay nonce điểm danh (giây) — mã hiển thị máy chiếu đổi mỗi 60s
    "NONCE_ROTATION_SECONDS": 60,
    # Cho phép lệch giờ thiết bị - máy chủ tối đa (giây) — chống Replay Attack
    "MAX_TIMESTAMP_SKEW_SECONDS": 60,
    # Điểm XP mặc định theo từng loại sự kiện
    "XP_ATTENDANCE": 50,
    "XP_ATTENDANCE_EARLY_BONUS": 20,
    "XP_ATTENDANCE_LATE": 25,
    "XP_DOCUMENT_SHARE": 100,
    "XP_TASK_COMPLETION": 30,
    "XP_EVENT_ORGANIZER": 150,
}

# ------------------------------------------------------------------
# 13. LOGGING
# ------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name} — {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
