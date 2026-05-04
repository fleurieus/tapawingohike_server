from django.contrib import admin
from django.urls import path, include, re_path

from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve

from server.apps.dashboard import views
from server.apps.dashboard import pins
from django.views.generic.base import TemplateView
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from .views import index, register

urlpatterns = [
    path('', index, name='index'),
    path('register/<int:edition_id>/', register, name='register'),
    path("admin/", admin.site.urls),
    path('stats/<int:route_id>/', views.stats_view, name='stats_view_with_route_id'),
    path('map/<int:route_id>/', views.map_view, name='map_view_with_route_id'),
    path('map/', login_required(TemplateView.as_view(template_name='base.html')), name='map'),
    path('stats/', login_required(TemplateView.as_view(template_name='base.html')), name='stats'),
    path('pin', pins.chart_pin, name="chart_pin"),
    path("backoffice/", include("server.apps.backoffice.urls", namespace="backoffice")),
    path("api/", include("server.apps.api.urls", namespace="api")),
    path("login/", auth_views.LoginView.as_view(template_name="_base.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
]

# Serve user-uploaded media files. django.conf.urls.static.static() is a
# no-op when DEBUG=False, so register the serve view directly to make
# /media/ available in production as well.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % settings.MEDIA_URL.lstrip("/"),
        static_serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
