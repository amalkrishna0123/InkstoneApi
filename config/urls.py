from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from core.admin_views import admin_dashboard

urlpatterns = [
    path("api/", include("core.urls")),
    path("admin/", admin_dashboard, name="admin-dashboard"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
