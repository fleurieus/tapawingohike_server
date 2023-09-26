from django.contrib import admin
from django.urls import path

from django.conf import settings
from django.conf.urls.static import static

from server.apps.dashboard import views
from django.views.generic.base import TemplateView
from django.contrib.auth.decorators import login_required

urlpatterns = [
    path("admin/", admin.site.urls),
    path('stats/<int:route_id>/', views.stats_view, name='stats_view_with_route_id'),
    path('map/<int:route_id>/', views.map_view, name='map_view_with_route_id'),
    path('map/', login_required(TemplateView.as_view(template_name='base.html')), name='map'),
    path('stats/', login_required(TemplateView.as_view(template_name='base.html')), name='stats'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
