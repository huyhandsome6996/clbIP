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

# ------------------------------------------------------------------
# 0.5 .ENV LOADER — nạp file .env ở thư mục gốc (không cần python-dotenv)
# Dự án dùng MySQL làm CSDL chính: biến DB_ENGINE, MYSQL_* đọc từ đây.
# ------------------------------------------------------------------
def _load_env_file() -> None:
    """Đọc cặp KEY=VALUE từ .env (bỏ qua comment #, giữ giá trị có khoảng trắng)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    try:
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:  # biến môi trường thật ưu tiên hơn .env
                os.environ[key] = value
    except OSError:
        pass  # Không thể đọc .env → chạy bằng biến môi trường hệ thống


_load_env_file()

# Cờ nhận diện đang chạy unittest → tắt throttle/axes để test không bị nhiễu
TESTING = "test" in sys.argv

# ------------------------------------------------------------------
# 1. CORE SECURITY SETTINGS — Fail-Fast Config (QA-Audit 2c)
# ------------------------------------------------------------------
# DEBUG mặc định False: quên đặt biến môi trường trên Render sẽ KHÔNG được
# phép rơi về DEBUG=True (rò rỉ settings/stacktrace ra Internet).
DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")
DJANGO_ENV = os.environ.get("DJANGO_ENV", "development")  # 'production' trên Render

# SECRET_KEY: production BẮT BUỘC có khóa thật — chặn deploy khi thiếu hoặc
# đang dùng khóa dev sinh mặc định (tiền tố "django-insecure").
_secret_key_env = os.environ.get("SECRET_KEY", "")
if DJANGO_ENV == "production":
    if not _secret_key_env:
        raise RuntimeError(
            "SECRET_KEY bắt buộc phải có khi DJANGO_ENV=production. "
            "Đặt biến môi trường SECRET_KEY (Render: generateValue=true)."
        )
    if _secret_key_env.startswith("django-insecure"):
        raise RuntimeError(
            'SECRET_KEY đang là khóa dev (tiền tố "django-insecure") — '
            "tuyệt đối không dùng trên production."
        )
    SECRET_KEY = _secret_key_env
else:
    # Chỉ development/test mới được dùng khóa dev mặc định
    SECRET_KEY = _secret_key_env or "django-insecure-local-dev-key-thay-doi-khi-deploy-render"

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
    "core.middleware.ContentSecurityPolicyMiddleware",  # Backstop chống XSS (QA-Audit 2f)
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
# ------------------------------------------------------------------
# 3. DATABASE — MySQL (chính) / PostgreSQL (Render) / SQLite (fallback)
# ------------------------------------------------------------------
# Ưu tiên:
#   1) DB_ENGINE=mysql / MYSQL_DATABASE / USE_MYSQL=1 → MySQL cục bộ
#      (CSDL `clb_ip_db` utf8mb4 — theo CLBIP_Frontend_Integration_Prompt.md)
#   2) DATABASE_URL=mysql://... → MySQL qua URL; postgres://... → Render
#   3) Còn lại → SQLite local (dev nhanh, chạy unit test)
try:
    import pymysql

    pymysql.install_as_MySQLdb()  # Django.db.backends.mysql dùng pymysql
except ImportError:  # Render/PostgreSQL không cần pymysql
    pass

_db_url = os.environ.get("DATABASE_URL", "").strip()
_db_engine = os.environ.get("DB_ENGINE", "").strip().lower()
_mysql_name = os.environ.get("MYSQL_DATABASE", os.environ.get("MYSQL_NAME", "clb_ip_db"))

_use_mysql = (
    _db_engine == "mysql"
    or _db_url.startswith("mysql")
    or bool(os.environ.get("MYSQL_DATABASE"))
    or os.environ.get("USE_MYSQL") == "1"
)

if _use_mysql and _db_url.startswith("mysql"):
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            ssl_require=False,
        )
    }
elif _use_mysql:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": _mysql_name,
            "USER": os.environ.get("MYSQL_USER", "root"),
            "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
            "HOST": os.environ.get("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.environ.get("MYSQL_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",  # Hỗ trợ đầy đủ tiếng Việt + emoji
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }
elif _db_url and not _db_url.startswith("file:"):  # Bỏ qua DATABASE_URL không phải DB thật
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
# 3.5 PROXY & CACHE DÙNG CHUNG (QA-Audit 2b)
# ------------------------------------------------------------------
# Render đặt 1 reverse-proxy phía trước → IP client thật là phần tử CUỐI của
# X-Forwarded-For (client có thể tự thêm phần tử đầu để giả mạo). DRF throttle
# và django-axes dựa vào con số này để nhận diện đúng IP — cấu hình sai thì
# attacker có thể né rate-limit bằng header giả.
_num_proxies_env = os.environ.get("NUM_PROXIES", "").strip()
try:
    NUM_PROXIES: int = int(_num_proxies_env) if _num_proxies_env else (
        1 if DJANGO_ENV == "production" else 0
    )
except ValueError as _exc:
    raise RuntimeError(
        f'NUM_PROXIES phải là số nguyên >= 0 (đang đặt "{_num_proxies_env}"). '
        "Ví dụ: NUM_PROXIES=1 khi chạy sau 1 reverse proxy (Render)."
    ) from _exc

# Cache dùng chung giữa các worker gunicorn cho DRF throttle: bộ đếm
# rate-limit PHẢI dùng chung — LocMemCache mặc định tách rời theo worker →
# attacker né throttle bằng cách trúng nhiều worker khác nhau. (django-axes
# 7 mặc định đã lưu attempt vào DB, không phụ thuộc cache này.)
_redis_url = os.environ.get("REDIS_URL", "").strip()
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "clbip",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache_table",  # tạo bằng createcachetable (build.sh)
            "KEY_PREFIX": "clbip",
            "TIMEOUT": 300,
            "OPTIONS": {"MAX_ENTRIES": 100_000},
        }
    }

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
# Nhận diện IP thật sau reverse proxy Render cho django-axes (django-ipware).
# Ngữ nghĩa KHÁC DRF NUM_PROXIES — đã kiểm chứng thực nghiệm với ipware 7.0.1:
#   proxy_order="right-most" + proxy_count=1 + XFF="giả, IP-thật"
#   → trả về IP-THẬT (trusted) — đúng mô hình Render (proxy ghi phần tử cuối).
#   (right-most + count=None và left-most + count=1 đều trả về IP GIẢ của client!)
AXES_IPWARE_PROXY_ORDER = "right-most"
AXES_IPWARE_PROXY_COUNT = NUM_PROXIES  # số proxy phía trước (Render = 1)
AXES_IPWARE_META_PRECEDENCE_ORDER = ("HTTP_X_FORWARDED_FOR", "REMOTE_ADDR")
# Form đăng nhập gửi trường "email" (không phải "username") — nếu không chỉ
# định, axes đọc rỗng → khóa chỉ theo IP, mất khóa theo cặp (tài khoản, IP)
AXES_USERNAME_FORM_FIELD = "email"

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
    # Nhận diện IP sau reverse proxy (Render) — xem §3.5. Đặt TRONG dict để
    # SimpleRateThrottle.get_ident() đọc đúng địa chỉ client thật, chống giả
    # mạo X-Forwarded-For để né throttle đăng nhập.
    "NUM_PROXIES": NUM_PROXIES,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",        # Khách vãng lai: 60 req/phút
        "user": "300/minute",       # Người dùng: 300 req/phút
        "burst": "10/second",       # Chống flood burst ngắn hạn
        "sustained": "1500/hour",   # Giới hạn bền vững theo giờ
        "auth_login": "5/minute",   # Đăng nhập: 5 lần/phút (chống dò mật khẩu)
        "checkin": "3/minute",      # Điểm danh GPS: 3 lần/phút
        "feedback": "2/minute",     # Góp ý/Poll: 2 lần/phút (chống spam)
        "doc_upload": "5/minute",   # Upload tài liệu: 5 lần/phút (chống lấp kho) — throttle class đã có sẵn trong apps/common/throttles.py
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
        # Mặc định khớp render.yaml + domain backend thật. LƯU Ý: khi deploy
        # Blueprint, env var trong render.yaml sẽ override giá trị mặc định này.
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://clbip-frontend.onrender.com,https://clbip-backend.onrender.com",
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# 8. SECURITY HEADERS (Production Hardening)
# ------------------------------------------------------------------
# (SECURE_BROWSER_XSS_FILTER đã bị Django loại bỏ từ bản 4.0 — không còn tác dụng)
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
