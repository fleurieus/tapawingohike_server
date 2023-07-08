from django.db import models

from .constants import (
    DESTINATION_TYPE_MANDATORY,
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

    def routeparts(self):
        """
        current_post = Post.objects.get(slug="c")
        next_post = Post.objects.filter(order__gt=current).order_by('order').first()
        """
        self.teamrouteparts.all()


class Route(models.Model):
    name = models.CharField(max_length=255)

    edition = models.ForeignKey(
        "dashboard.Edition",
        on_delete=models.CASCADE,
        related_name="routes",
    )

    def __str__(self):
        return self.name


class RoutePart(models.Model):
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


class TeamRoutePart(models.Model):
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
