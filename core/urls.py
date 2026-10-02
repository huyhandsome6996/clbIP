"""
URL Configuration — CLB IP ĐHSP Huế 2.0
Tất cả API có tiền tố /api/v1/ theo CLBIP_Master_Coding_Prompt.md §5.
Swagger UI: /api/docs/ (drf-spectacular, OpenAPI 3.0).
Frontend tĩnh: /frontend/ (landing.html công khai tại `/`, login.html, admin/*, member/*).
"""
from django.conf import settings
from django.contrib import admin
from django.http import Http404
from django.urls import include, path, re_path
from django.views.static import serve as static_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Thư mục giao diện tĩnh (HTML/CSS/JS thuần, nằm cạnh manage.py)
FRONTEND_DIR = settings.BASE_DIR / "frontend"


class _AdminOnlySchemaMixin:
    """
    QA-Audit 2e: ở production, tài liệu API (Swagger/schema) chỉ dành cho ADMIN.
    Sơ đồ API mô tả toàn bộ bề mặt tấn công — không công khai cho Internet.
    Trả 404 (không 403) để không hé lộ sự tồn tại của endpoint; môi trường dev
    vẫn mở tự do cho tiện ích phát triển.

    Ghi đè initial() (chạy SAU khi DRF đã dựng request + xác thực JWT) thay vì
    dispatch() — vì ở dispatch() request.user vẫn là AnonymousUser với JWT.
    """

    def initial(self, request, *args, **kwargs):
        if getattr(settings, "DJANGO_ENV", "") == "production":
            user = request.user
            is_admin = user.is_authenticated and (
                user.is_superuser or getattr(user, "role", "") == "ADMIN"
            )
            if not is_admin:
                raise Http404("Trang không tồn tại.")
        super().initial(request, *args, **kwargs)


class SchemaView(_AdminOnlySchemaMixin, SpectacularAPIView):
    """Raw OpenAPI schema — chỉ ADMIN khi production."""


class SwaggerView(_AdminOnlySchemaMixin, SpectacularSwaggerView):
    """Swagger UI — chỉ ADMIN khi production."""


def frontend_serve(request, path):
    """
    Phục vụ file frontend + luôn bắt trình duyệt revalidate (no-cache).
    Tránh tình trạng sửa CSS/JS mà trình duyệt vẫn dùng bản cũ trong cache.
    """
    response = static_serve(request, path, document_root=FRONTEND_DIR)
    response["Cache-Control"] = "no-cache"
    return response

def frontend_index_serve(request):
    """
    Trang chủ `/` → landing page CÔNG KHAI (frontend/landing.html):
    giới thiệu CLB + CTA Đăng nhập, không cần phiên đăng nhập.
    Khách đã đăng nhập: JS trong trang tự đổi CTA thành "Vào cổng sinh viên"
    (trỏ về /frontend/index.html — splash điều hướng theo vai trò).
    """
    response = static_serve(request, "landing.html", document_root=FRONTEND_DIR)
    response["Cache-Control"] = "no-cache"
    return response


urlpatterns = [
    # ---------- Trang chủ công khai → landing page giới thiệu CLB ----------
    # (Swagger UI vẫn luôn sẵn tại /api/docs/)
    path("", frontend_index_serve),

    # ---------- Frontend tĩnh (login, admin, member, css, js, assets) ----------
    re_path(r"^frontend/(?P<path>.*)$", frontend_serve),

    # ---------- Django Admin ----------
    path("admin/", admin.site.urls),

    # ---------- OpenAPI 3.0 / Swagger UI (chỉ ADMIN khi production) ----------
    path("api/schema/", SchemaView.as_view(), name="schema"),
    path("api/docs/", SwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # ---------- API v1 (module urls do từng app khai báo) ----------
    path("api/v1/auth/", include("apps.authentication.urls")),
    path("api/v1/members/", include("apps.members.urls")),
    path("api/v1/funds/", include("apps.funds.urls")),
    path("api/v1/events/", include("apps.events.urls")),
    path("api/v1/attendance/", include("apps.attendance.urls")),
    path("api/v1/gamification/", include("apps.gamification.urls")),
    path("api/v1/documents/", include("apps.documents.urls")),
    path("api/v1/", include("apps.posts.urls")),  # posts/, feedback/, polls/
    path("api/", include("apps.common.urls")),    # health check
    path("api/v1/common/", include("apps.common.urls_v1")),  # stats trend (TASK 4)
]

# Phục vụ file /media/ CHỈ khi dev (quy ước Django): preview PDF frontend
# cần URL file tồn tại. Production KHÔNG phục vụ media qua Django — tải file
# luôn đi qua /documents/{id}/download/ (có auth + phạm vi BCN_ONLY, QA-Audit
# 2d); file lưu trữ xa sẽ chuyển sang S3/R2 (xem Nhóm 5 — performance/storage).
if settings.DEBUG:
    from django.conf.urls.static import static as static_media

    urlpatterns += static_media(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
