from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.operations.views import overview

urlpatterns = [
    path("", overview, name="overview"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("operations/", include("apps.operations.urls")),
    path("health/", include("apps.core.urls")),
    path("admin/", admin.site.urls),
]
