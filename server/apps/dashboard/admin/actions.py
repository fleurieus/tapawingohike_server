from django.contrib import admin
from django.forms.models import model_to_dict


@admin.action(description="Distribueer naar Teams")
def distribute_to_teams(modeladmin, request, queryset):
    for route in queryset.all():
        teams = route.edition.teams.all()

        for part in route.routeparts.all():
            part_dict = model_to_dict(part)

            del part_dict["id"]

            # foreignkeys
            part_dict["route_id"] = part_dict.pop("route")
            part_dict["routedata_image_id"] = part_dict.pop("routedata_image")
            part_dict["routedata_audio_id"] = part_dict.pop("routedata_audio")

            for team in teams:
                part_dict["team"] = team
                order_dict = {"order": part_dict.pop("order")}

                team_route_part, _ = part.teamrouteparts.get_or_create(**part_dict,defaults=order_dict)

                for dest in part.destinations.all():
                    dest_dict = model_to_dict(dest)

                    del dest_dict["id"]
                    del dest_dict["routepart"]

                    dest_dict["teamroutepart"] = team_route_part.pk

                    team_route_part.destinations.get_or_create(**dest_dict)
