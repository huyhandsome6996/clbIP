"""
URL Configuration — CLB IP ĐHSP Huế 2.0
Tất cả API có tiền tố /api/v1/ theo CLBIP_Master_Coding_Prompt.md §5.
Swagger UI: /api/docs/ (drf-spectacular, OpenAPI 3.0).
"""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # ---------- Root Redirect to Swagger UI ----------
    path("", RedirectView.as_view(url="/api/docs/", permanent=False), name="root"),

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
