from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="dashboard/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="login"),
        name="logout",
    ),
    path("api/", include("clinical_core.urls")),
    path("api/", include("review_portal.api_urls")),
    path("review/", include("review_portal.urls")),
    path("dag-extraction/", include("dag_extraction.urls")),
    path("", include("dashboard.urls")),
]
