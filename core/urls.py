"""
URL Configuration — CLB IP ĐHSP Huế 2.0
Tất cả API có tiền tố /api/v1/ theo CLBIP_Master_Coding_Prompt.md §5.
Swagger UI: /api/docs/ (drf-spectacular, OpenAPI 3.0).
Frontend tĩnh: /frontend/ (login.html, admin/*, member/*).
"""
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import include, path, re_path
from django.views.static import serve as static_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# Thư mục giao diện tĩnh (HTML/CSS/JS thuần, nằm cạnh manage.py)
FRONTEND_DIR = settings.BASE_DIR / "frontend"


def frontend_serve(request, path):
    """
    Phục vụ file frontend + luôn bắt trình duyệt revalidate (no-cache).
    Tránh tình trạng sửa CSS/JS mà trình duyệt vẫn dùng bản cũ trong cache.
    """
    response = static_serve(request, path, document_root=FRONTEND_DIR)
    response["Cache-Control"] = "no-cache"
    return response

urlpatterns = [
    # ---------- Trang chủ → điều hướng thông minh theo đăng nhập ----------
    # (Swagger UI vẫn luôn sẵn tại /api/docs/)
    path("", lambda request: HttpResponseRedirect("/frontend/index.html")),

    # ---------- Frontend tĩnh (login, admin, member, css, js, assets) ----------
    re_path(r"^frontend/(?P<path>.*)$", frontend_serve),

    # ---------- Django Admin ----------
    path("admin/", admin.site.urls),

    # ---------- OpenAPI 3.0 / Swagger UI ----------
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),

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
]
