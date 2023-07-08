from django.contrib import admin

from server.apps.dashboard.models import Destination


class DestinationInline(admin.TabularInline):
    extra = 1
    model = Destination
    readonly_fields = ("routepart", "teamroutepart")
