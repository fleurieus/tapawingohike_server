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
from .actions import distribute_to_teams

admin.site.register(Organization)
admin.site.register(Event)
admin.site.register(Edition)
admin.site.register(File)


@admin.register(Route)
class TeamAdmin(admin.ModelAdmin):
    actions = [distribute_to_teams]


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("__str__", "code", "online")
    readonly_fields = ("online",)


@admin.register(RoutePart)
class RoutePartAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_filter = ("route",)
    inlines = (DestinationInline,)
    fieldsets = [
        (
            "Route Part Info",
            {
                "fields": [
                    "name",
                    "route_type",
                    "route",
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
    ]


@admin.register(TeamRoutePart)
class TeamRoutePartAdmin(SortableAdminMixin, admin.ModelAdmin):
    list_filter = (
        "route",
        "team",
    )
    readonly_fields = ("route", "team", "order")
    inlines = (DestinationInline,)
    fieldsets = [
        (
            "Team Route Part Info",
            {
                "fields": [
                    "name",
                    "route_type",
                    "route",
                    "team",
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
    ]
