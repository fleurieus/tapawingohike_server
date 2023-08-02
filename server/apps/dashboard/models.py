from urllib.parse import urljoin

from django.db import models
from django.conf import settings

from .validators import FinalDestinationValidationMixin
from .constants import (
    DESTINATION_TYPE_MANDATORY,
    DESTINATION_TYPE_CHOICE,
    DESTINATION_TYPES,
    ROUTE_TYPE_COORDINATE,
    ROUTE_TYPES,
    FILE_TYPE_IMAGE,
    FILE_TYPE_AUDIO,
    FILE_TYPES,
)


class Organization(models.Model):
    name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255)
    contact_email = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Event(models.Model):
    name = models.CharField(max_length=255)

    organization = models.ForeignKey(
        "dashboard.Organization",
        on_delete=models.CASCADE,
        related_name="events",
    )

    def __str__(self):
        return f"{self.name} | {self.organization}"


class Edition(models.Model):
    name = models.CharField(max_length=255)
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()

    event = models.ForeignKey(
        "dashboard.Event",
        on_delete=models.CASCADE,
        related_name="editions",
    )

    def __str__(self):
        return f"{self.name} | {self.event}"


class Team(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=100)
    contact_email = models.CharField(max_length=100)
    contact_phone = models.CharField(max_length=100)
    online = models.BooleanField(default=False)

    edition = models.ForeignKey(
        "dashboard.Edition",
        on_delete=models.CASCADE,
        related_name="teams",
    )

    def __str__(self):
        return f"{self.name}"

    def go_online(self):
        self.online = True
        self.save()

    def go_offline(self):
        self.online = False
        self.save()

    def get_next_open_routepart(self):
        return self.teamrouteparts.filter(completed=False).order_by("order").first()

    def get_next_open_routepart_formatted(self):
        part = self.get_next_open_routepart()

        image_url = (
            urljoin(settings.SERVER_URI, part.routedata_image.file.url)
            if part.routedata_image
            else None
        )
        audio_url = (
            urljoin(settings.SERVER_URI, part.routedata_audio.file.url)
            if part.routedata_audio
            else None
        )

        formatted_data = {
            "type": part.route_type,
            "data": {
                "fullscreen": part.routepart_fullscreen,
                "zoomEnabled": part.routepart_zoom,
                "image": image_url,
                "audio": audio_url,
                "coordinates": self.destinations_formatted(part.destinations.all()),
            },
        }
        return formatted_data

    def get_teamroutepart(self, destination_id):
        return self.teamrouteparts.get(destinations__id=destination_id)

    @staticmethod
    def destinations_formatted(destinations):
        # TODO: beslissen of we de `completed` destintions ook willen tonen
        return [
            dict(
                id=d.id,
                latitude=d.lat,
                longitude=d.lng,
                type=d.destination_type,
                radius=d.radius,
                confirmByUser=d.confirm_by_user,
            )
            for d in destinations
        ]

    def handle_destination_completion(self, destination_id):
        part = self.get_teamroutepart(destination_id)
        part.complete_destination(destination_id)
        part.check_completion()


class Route(models.Model):
    name = models.CharField(max_length=255)

    edition = models.ForeignKey(
        "dashboard.Edition",
        on_delete=models.CASCADE,
        related_name="routes",
    )

    def __str__(self):
        return self.name


class RoutePart(FinalDestinationValidationMixin, models.Model):
    # info
    name = models.CharField(max_length=255)
    route_type = models.CharField(
        max_length=255, default=ROUTE_TYPE_COORDINATE, choices=ROUTE_TYPES
    )

    # data
    routepart_zoom = models.BooleanField(default=True)
    routepart_fullscreen = models.BooleanField(default=True)
    routedata_image = models.ForeignKey(
        "dashboard.File",
        on_delete=models.CASCADE,
        related_name="routepart_images",
        limit_choices_to={"category": FILE_TYPE_IMAGE},
        blank=True,
        null=True,
    )
    routedata_audio = models.ForeignKey(
        "dashboard.File",
        on_delete=models.CASCADE,
        related_name="routepart_audio",
        limit_choices_to={"category": FILE_TYPE_AUDIO},
        blank=True,
        null=True,
    )

    # extra
    final = models.BooleanField(default=False)
    order = models.PositiveIntegerField()

    route = models.ForeignKey(
        "dashboard.Route",
        on_delete=models.CASCADE,
        related_name="routeparts",
    )

    def __str__(self):
        return f"{self.name} | {self.route}"

    class Meta:
        ordering = ("order",)


class TeamRoutePart(FinalDestinationValidationMixin, models.Model):
    # info
    name = models.CharField(max_length=255)
    route_type = models.CharField(
        max_length=255, default=ROUTE_TYPE_COORDINATE, choices=ROUTE_TYPES
    )

    # data
    routepart_zoom = models.BooleanField(default=True)
    routepart_fullscreen = models.BooleanField(default=True)
    routedata_image = models.ForeignKey(
        "dashboard.File",
        on_delete=models.CASCADE,
        related_name="teamroutepart_images",
        limit_choices_to={"category": FILE_TYPE_IMAGE},
        blank=True,
        null=True,
    )
    routedata_audio = models.ForeignKey(
        "dashboard.File",
        on_delete=models.CASCADE,
        related_name="teamroutepart_audio",
        limit_choices_to={"category": FILE_TYPE_AUDIO},
        blank=True,
        null=True,
    )

    # extra
    final = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)
    order = models.PositiveIntegerField()

    route = models.ForeignKey(
        "dashboard.Route",
        on_delete=models.CASCADE,
        related_name="teamrouteparts",
    )

    routepart = models.ForeignKey(
        "dashboard.RoutePart",
        on_delete=models.CASCADE,
        related_name="teamrouteparts",
    )
    team = models.ForeignKey(
        "dashboard.Team",
        on_delete=models.CASCADE,
        related_name="teamrouteparts",
    )

    def __str__(self):
        return f"{self.team.name} | {self.routepart}"

    def complete_destination(self, destination_id):
        return self.destinations.filter(id=destination_id).update(completed=True)

    def check_completion(self):
        destinations = self.destinations.all()

        # mandatory not completed
        if destinations.filter(
            destination_type=DESTINATION_TYPE_MANDATORY, completed=False
        ).exists():
            return

        # choice is not completed
        if (
            not destinations.filter(destination_type=DESTINATION_TYPE_CHOICE).exists()
            and destinations.filter(
                destination_type=DESTINATION_TYPE_CHOICE, completed=True
            ).exists()
        ):
            return

        self.complete()

    def complete(self):
        self.completed = True
        self.save()

    class Meta:
        ordering = ("order",)


class Destination(models.Model):
    lat = models.FloatField(max_length=64)
    lng = models.FloatField(max_length=64)
    radius = models.IntegerField()
    destination_type = models.CharField(
        max_length=255, default=DESTINATION_TYPE_MANDATORY, choices=DESTINATION_TYPES
    )
    confirm_by_user = models.BooleanField(default=False)
    hide_for_user = models.BooleanField(default=False)

    completed = models.BooleanField(default=False)

    routepart = models.ForeignKey(
        "dashboard.Routepart",
        on_delete=models.CASCADE,
        related_name="destinations",
        blank=True,
        null=True,
    )

    teamroutepart = models.ForeignKey(
        "dashboard.TeamRoutepart",
        on_delete=models.CASCADE,
        related_name="destinations",
        blank=True,
        null=True,
    )


class File(models.Model):
    file = models.FileField()
    category = models.CharField(
        max_length=64,
        default=FILE_TYPE_IMAGE,
        choices=FILE_TYPES,
    )

    def __str__(self) -> str:
        return self.file.name


class LocationLog(models.Model):
    team = models.ForeignKey(
        "dashboard.Team",
        on_delete=models.CASCADE,
        related_name="location_logs",
    )

    lat = models.FloatField(max_length=64)
    lng = models.FloatField(max_length=64)
    time = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.team} | {self.time.strftime('%d-%m-%Y %H:%M')}"
