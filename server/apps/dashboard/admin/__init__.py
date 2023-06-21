from copy import deepcopy

from django.contrib import admin

from django.contrib import admin
from server.apps.dashboard.models import (
    Organization,
    Event,
    Edition,
    Team,
    Route,
    RoutePart,
    TeamRoutePart,
    File,
)

from adminsortable2.admin import SortableAdminMixin

from .inlines import DestinationInline

admin.site.register(Organization)
admin.site.register(Event)
admin.site.register(Edition)
admin.site.register(Route)
admin.site.register(File)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("__str__", "code", "online")
    readonly_fields = ("online",)


@admin.register(RoutePart)
class RoutePartAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_filter = [
        "route",
    ]
    inlines = (DestinationInline,)
    fieldsets = [
        (
            "Route Part Info",
            {
                "fields": [
                    "name",
                    "route_type",
                ],
            },
        ),
        (
            "Route Part Data",
            {
                "fields": [
                    "routepart_zoom",
                    "routepart_fullscreen",
                    "routedata_image",
                    "routedata_audio",
                ],
            },
        ),
        (
            "Extra",
            {
                "fields": ["route"],
            },
        ),
    ]


@admin.register(TeamRoutePart)
class TeamRoutePartAdmin(RoutePartAdmin):
    readonly_fields = ("route", "team", "order")
    fieldsets = [
        (
            "Route Part Info",
            {
                "fields": [
                    "name",
                    "route_type",
                ],
            },
        ),
        (
            "Route Part Data",
            {
                "fields": [
                    "routepart_zoom",
                    "routepart_fullscreen",
                    "routedata_image",
                    "routedata_audio",
                ],
            },
        ),
        (
            "Extra",
            {
                "fields": ["route", "team"],
            },
        ),
    ]
