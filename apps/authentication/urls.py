"""URLs — Authentication API (mount tại /api/v1/auth/)."""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.authentication.views import CustomTokenObtainPairView, MeView

urlpatterns = [
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", MeView.as_view(), name="auth_me"),
]
