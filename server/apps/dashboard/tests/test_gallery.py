from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from server.apps.dashboard.constants import (
    DESTINATION_TYPE_MANDATORY,
    FILE_TYPE_IMAGE,
    ROUTE_TYPE_COORDINATE,
    ROUTE_TYPE_GALLERY,
)
from server.apps.dashboard.models import (
    Destination,
    Edition,
    Event,
    File,
    Organization,
    Route,
    RoutePart,
    RoutePartImage,
    Team,
    TeamRoutePart,
    TeamRoutePartImage,
)
from server.views import _distribute_routes_for_team


@override_settings(SERVER_URI="http://testserver")
class GalleryTestCase(TestCase):
    """Tests for the gallery routepart feature: model wiring, formatter
    payload, per-destination skip_location_check, and distribution."""

    def setUp(self):
        org = Organization.objects.create(
            name="Test Org", contact_person="Test", contact_email="test@test.nl"
        )
        event = Event.objects.create(name="Test Event", organization=org)
        self.edition = Edition.objects.create(
            name="Test Edition",
            date_start=timezone.make_aware(timezone.datetime(2026, 6, 1)),
            date_end=timezone.make_aware(timezone.datetime(2026, 6, 2)),
            event=event,
        )
        self.route = Route.objects.create(name="Route A", edition=self.edition)
        self.team = Team.objects.create(
            name="Team 1",
            code="ABC12",
            contact_name="Tester",
            contact_email="tester@test.nl",
            edition=self.edition,
        )

    # ── helpers ─────────────────────────────────────────────────────

    def _make_image_file(self, name="img.jpg"):
        """A minimal File row with a dummy image upload."""
        f = File(category=FILE_TYPE_IMAGE)
        f.file = SimpleUploadedFile(
            name, b"\xff\xd8\xff\xd9", content_type="image/jpeg"
        )
        f.save()
        return f

    def _create_gallery_routepart(
        self,
        order=1,
        caption="",
        skip_location_check=False,
        with_coordinates=True,
        n_images=2,
    ):
        rp = RoutePart.objects.create(
            name=f"Gallery {order}",
            route=self.route,
            route_type=ROUTE_TYPE_GALLERY,
            order=order,
            gallery_caption=caption,
        )
        if with_coordinates:
            Destination.objects.create(
                lat=52.0 + order * 0.01,
                lng=6.0 + order * 0.01,
                radius=25,
                destination_type=DESTINATION_TYPE_MANDATORY,
                skip_location_check=skip_location_check,
                routepart=rp,
            )
        for i in range(n_images):
            RoutePartImage.objects.create(
                routepart=rp,
                image=self._make_image_file(f"img{order}-{i}.jpg"),
                order=i,
            )
        return rp

    # ── models ──────────────────────────────────────────────────────

    def test_gallery_caption_defaults_to_empty(self):
        rp = RoutePart.objects.create(
            name="G", route=self.route, route_type=ROUTE_TYPE_GALLERY, order=1
        )
        self.assertEqual(rp.gallery_caption, "")

    def test_routepart_images_are_ordered(self):
        rp = self._create_gallery_routepart(n_images=3)
        # Even out-of-order creation should not affect retrieval order
        RoutePartImage.objects.create(
            routepart=rp, image=self._make_image_file(), order=5
        )
        orders = list(rp.gallery_images.values_list("order", flat=True))
        self.assertEqual(orders, sorted(orders))

    # ── formatter (_format_single_part) ─────────────────────────────

    def test_format_gallery_payload(self):
        rp = self._create_gallery_routepart(
            caption="Welkom bij stop 1", skip_location_check=False, n_images=3
        )
        _distribute_routes_for_team(self.team)

        result = self.team.get_next_open_routepart_formatted()

        self.assertEqual(result["type"], "gallery")
        data = result["data"]
        self.assertEqual(data["caption"], "Welkom bij stop 1")
        self.assertFalse(data["coordinates"][0]["skipLocationCheck"])
        self.assertEqual(len(data["images"]), 3)
        # URLs should be absolute (settings.SERVER_URI is overridden in this test)
        for url in data["images"]:
            self.assertTrue(url.startswith("http://testserver"))
        # Coordinates pass through unchanged
        self.assertEqual(len(data["coordinates"]), 1)

    def test_format_destination_skip_location_check_flag(self):
        """A destination flagged skip_location_check surfaces as
        skipLocationCheck=True in its formatted coordinate."""
        self._create_gallery_routepart(skip_location_check=True)
        _distribute_routes_for_team(self.team)
        result = self.team.get_next_open_routepart_formatted()
        coords = result["data"]["coordinates"]
        self.assertEqual(len(coords), 1)
        self.assertTrue(coords[0]["skipLocationCheck"])

    def test_non_gallery_payload_has_no_gallery_fields(self):
        """Existing image/coordinate routeparts should remain unchanged —
        no 'images' / 'caption' keys leak into them. skipLocationCheck is a
        general per-destination field and defaults to False."""
        rp = RoutePart.objects.create(
            name="C", route=self.route, route_type=ROUTE_TYPE_COORDINATE, order=1
        )
        Destination.objects.create(
            lat=52.1,
            lng=6.1,
            radius=25,
            destination_type=DESTINATION_TYPE_MANDATORY,
            routepart=rp,
        )
        _distribute_routes_for_team(self.team)

        data = self.team.get_next_open_routepart_formatted()["data"]
        self.assertNotIn("images", data)
        self.assertNotIn("caption", data)
        self.assertFalse(data["coordinates"][0]["skipLocationCheck"])

    # ── distribution ────────────────────────────────────────────────

    def test_distribution_copies_gallery_images_to_team(self):
        rp = self._create_gallery_routepart(n_images=3)
        _distribute_routes_for_team(self.team)

        trp = TeamRoutePart.objects.get(routepart=rp, team=self.team)
        self.assertEqual(trp.gallery_images.count(), 3)
        # Image File rows are shared (FK to dashboard.File), not duplicated
        rp_image_ids = set(rp.gallery_images.values_list("image_id", flat=True))
        trp_image_ids = set(trp.gallery_images.values_list("image_id", flat=True))
        self.assertEqual(rp_image_ids, trp_image_ids)

    def test_distribution_copies_caption_and_skip_flag(self):
        self._create_gallery_routepart(
            caption="Audio gids hier", skip_location_check=True
        )
        _distribute_routes_for_team(self.team)

        trp = self.team.teamrouteparts.get()
        self.assertEqual(trp.gallery_caption, "Audio gids hier")
        dest = trp.destinations.get()
        self.assertTrue(dest.skip_location_check)

    def test_distribution_is_idempotent_for_gallery(self):
        """Running distribution twice should not duplicate gallery images."""
        self._create_gallery_routepart(n_images=2)
        _distribute_routes_for_team(self.team)
        _distribute_routes_for_team(self.team)

        trp = self.team.teamrouteparts.get()
        self.assertEqual(trp.gallery_images.count(), 2)
        # And only one TeamRoutePart exists per (routepart, team)
        self.assertEqual(self.team.teamrouteparts.count(), 1)

    # ── sync_gallery_from_routepart ─────────────────────────────────

    def test_sync_gallery_no_op_for_non_gallery(self):
        """Calling sync on a non-gallery routepart must do nothing."""
        rp = RoutePart.objects.create(
            name="C", route=self.route, route_type=ROUTE_TYPE_COORDINATE, order=1
        )
        trp = TeamRoutePart.objects.create(
            name=rp.name,
            route=self.route,
            routepart=rp,
            team=self.team,
            route_type=ROUTE_TYPE_COORDINATE,
            order=1,
        )
        trp.sync_gallery_from_routepart(rp)
        self.assertEqual(trp.gallery_images.count(), 0)

    def test_sync_gallery_does_not_create_marker_destination(self):
        """Gallery without coordinates should NOT auto-create a destination.
        A 'tussen-gallery' is instead a normal destination flagged
        skip_location_check, so no marker destination is needed."""
        rp = self._create_gallery_routepart(
            skip_location_check=True, with_coordinates=False
        )
        _distribute_routes_for_team(self.team)
        trp = TeamRoutePart.objects.get(routepart=rp, team=self.team)
        self.assertEqual(trp.destinations.count(), 0)

    def test_team_gallery_image_ordering(self):
        rp = self._create_gallery_routepart(n_images=3)
        _distribute_routes_for_team(self.team)
        trp = TeamRoutePart.objects.get(routepart=rp, team=self.team)
        orders = list(trp.gallery_images.values_list("order", flat=True))
        self.assertEqual(orders, sorted(orders))
        # TeamRoutePartImage ordering meta defaults to (order, id)
        self.assertEqual(
            list(TeamRoutePartImage.objects.filter(teamroutepart=trp)
                 .values_list("order", flat=True)),
            sorted(orders),
        )
