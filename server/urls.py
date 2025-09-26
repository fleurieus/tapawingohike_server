from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

from server.apps.dashboard import views
from server.apps.dashboard import pins
from django.views.generic.base import TemplateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from .views import index

urlpatterns = [
    path('', index, name='index'),
    path("admin/", admin.site.urls),
    path('stats/<int:route_id>/', views.stats_view, name='stats_view_with_route_id'),
    path('map/<int:route_id>/', views.map_view, name='map_view_with_route_id'),
    path('map/', login_required(TemplateView.as_view(template_name='base.html')), name='map'),
    path('stats/', login_required(TemplateView.as_view(template_name='base.html')), name='stats'),
    path('pin', pins.chart_pin, name="chart_pin"),
    path("backoffice/", include("server.apps.backoffice.urls", namespace="backoffice")),
    path("login/", auth_views.LoginView.as_view(template_name="_base.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
