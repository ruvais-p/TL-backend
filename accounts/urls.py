from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    Auth0ExchangeView,
    LoginView,
    LogoutView,
    ManagedUserViewSet,
    MeView,
    MoodleExchangeView,
    PermissionCatalogView,
    RoleViewSet,
    StaffSummaryView,
)

app_name = "accounts"

router = SimpleRouter()
router.register("users", ManagedUserViewSet, basename="managed-user")
router.register("groups", RoleViewSet, basename="role")

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("auth0/exchange/", Auth0ExchangeView.as_view(), name="auth0-exchange"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("moodle/exchange/", MoodleExchangeView.as_view(), name="moodle-exchange"),
    path("permissions/", PermissionCatalogView.as_view(), name="permission-catalog"),
    path("staff-summary/", StaffSummaryView.as_view(), name="staff-summary"),
    path("", include(router.urls)),
]
