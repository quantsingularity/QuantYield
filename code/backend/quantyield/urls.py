"""
QuantYield -- Root URL Configuration
"""

from apps.core.auth_views import MeView, RegisterView, TokenObtainView
from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # ── Auth endpoints ─────────────────────────────────────────────────────────
    # POST  /api/v1/auth/token/         obtain access + refresh tokens
    # POST  /api/v1/auth/token/refresh/ exchange a refresh token for a new access token
    # POST  /api/v1/auth/register/      create a new user account
    # GET   /api/v1/auth/me/            return the authenticated user's profile
    path("api/v1/auth/token/", TokenObtainView.as_view(), name="token_obtain"),
    path(
        "api/v1/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"
    ),
    path("api/v1/auth/register/", RegisterView.as_view(), name="auth_register"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth_me"),
    # ── API v1 ────────────────────────────────────────────────────────────────
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/bonds/", include("apps.bonds.urls")),
    path("api/v1/portfolios/", include("apps.portfolios.urls")),
    path("api/v1/curves/", include("apps.curves.urls")),
    path("api/v1/analytics/", include("apps.analytics.urls")),
    # ── OpenAPI schema + docs ─────────────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass
