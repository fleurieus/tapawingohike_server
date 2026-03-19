from django.test import TestCase, override_settings
from django.utils import timezone

from server.apps.dashboard.constants import (
    BUNDLE_BROWSE_FREE,
    BUNDLE_BROWSE_LINEAR,
    BUNDLE_LINEAR_UPCOMING_HIDDEN,
    BUNDLE_LINEAR_UPCOMING_LOCKED,
    DESTINATION_TYPE_MANDATORY,
    ROUTE_TYPE_COORDINATE,
    ROUTE_TYPE_IMAGE,
)
from server.apps.dashboard.models import (
    Bundle,
    Destination,
    Edition,
    Event,
    Organization,
    Route,
    RoutePart,
    Team,
    TeamRoutePart,
)
from server.views import _distribute_routes_for_team


@override_settings(SERVER_URI="http://testserver")
class BundleTestCase(TestCase):
    """Tests for the Bundle feature: formatting, status assignment, distribution."""

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

    def _create_bundle(self, browse_mode=BUNDLE_BROWSE_FREE,
                       linear_upcoming_mode=BUNDLE_LINEAR_UPCOMING_LOCKED):
        return Bundle.objects.create(
            name="Bundel 1",
            route=self.route,
            browse_mode=browse_mode,
            linear_upcoming_mode=linear_upcoming_mode,
        )

    def _create_team_routepart(self, order, bundle=None, route_type=ROUTE_TYPE_COORDINATE):
        """Create a RoutePart + matching TeamRoutePart with a mandatory destination."""
        rp = RoutePart.objects.create(
            name=f"Part {order}",
            route=self.route,
            route_type=route_type,
            order=order,
            bundle=bundle,
        )
        trp = TeamRoutePart.objects.create(
            name=rp.name,
            route=self.route,
            routepart=rp,
            team=self.team,
            route_type=route_type,
            order=order,
            bundle=bundle,
        )
        Destination.objects.create(
            lat=52.0 + order * 0.01,
            lng=6.0 + order * 0.01,
            radius=25,
            destination_type=DESTINATION_TYPE_MANDATORY,
            teamroutepart=trp,
        )
        return rp, trp

    # ── Single part (no bundle) ──────────────────────────────────

    def test_single_part_no_bundle_key(self):
        """A part without bundle returns the classic single-part format."""
        _, trp = self._create_team_routepart(order=1)
        result = self.team.get_next_open_routepart_formatted()

        self.assertNotIn("bundle", result)
        self.assertEqual(result["type"], ROUTE_TYPE_COORDINATE)
        self.assertIn("data", result)
        self.assertIn("coordinates", result["data"])
        self.assertIn("hasUndoableCompletions", result["data"])

    # ── Bundle formatting ────────────────────────────────────────

    def test_bundle_returns_bundle_format(self):
        """A part with bundle returns the bundle envelope."""
        bundle = self._create_bundle()
        self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=bundle)
        self._create_team_routepart(order=3, bundle=bundle)

        result = self.team.get_next_open_routepart_formatted()

        self.assertTrue(result["bundle"])
        self.assertEqual(result["browseMode"], BUNDLE_BROWSE_FREE)
        self.assertEqual(result["linearUpcomingMode"], BUNDLE_LINEAR_UPCOMING_LOCKED)
        self.assertEqual(result["currentIndex"], 0)
        self.assertEqual(len(result["parts"]), 3)

    def test_bundle_status_all_open(self):
        """When no parts are completed, first is 'current', rest are 'upcoming'."""
        bundle = self._create_bundle()
        self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=bundle)
        self._create_team_routepart(order=3, bundle=bundle)

        result = self.team.get_next_open_routepart_formatted()
        statuses = [p["status"] for p in result["parts"]]

        self.assertEqual(statuses, ["current", "upcoming", "upcoming"])

    def test_bundle_status_first_completed(self):
        """After completing the first part, second becomes 'current'."""
        bundle = self._create_bundle()
        _, trp1 = self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=bundle)
        self._create_team_routepart(order=3, bundle=bundle)

        # Complete part 1
        now = timezone.now()
        trp1.completed_time = now
        trp1.save()
        trp1.destinations.update(completed_time=now)

        result = self.team.get_next_open_routepart_formatted()
        statuses = [p["status"] for p in result["parts"]]

        self.assertEqual(statuses, ["completed", "current", "upcoming"])
        self.assertEqual(result["currentIndex"], 1)

    def test_bundle_status_two_completed(self):
        """After completing the first two parts, third becomes 'current'."""
        bundle = self._create_bundle()
        _, trp1 = self._create_team_routepart(order=1, bundle=bundle)
        _, trp2 = self._create_team_routepart(order=2, bundle=bundle)
        self._create_team_routepart(order=3, bundle=bundle)

        now = timezone.now()
        for trp in (trp1, trp2):
            trp.completed_time = now
            trp.save()
            trp.destinations.update(completed_time=now)

        result = self.team.get_next_open_routepart_formatted()
        statuses = [p["status"] for p in result["parts"]]

        self.assertEqual(statuses, ["completed", "completed", "current"])
        self.assertEqual(result["currentIndex"], 2)

    # ── Browse modes ─────────────────────────────────────────────

    def test_bundle_linear_mode(self):
        """Linear browse mode is passed through to the response."""
        bundle = self._create_bundle(
            browse_mode=BUNDLE_BROWSE_LINEAR,
            linear_upcoming_mode=BUNDLE_LINEAR_UPCOMING_HIDDEN,
        )
        self._create_team_routepart(order=1, bundle=bundle)

        result = self.team.get_next_open_routepart_formatted()

        self.assertEqual(result["browseMode"], BUNDLE_BROWSE_LINEAR)
        self.assertEqual(result["linearUpcomingMode"], BUNDLE_LINEAR_UPCOMING_HIDDEN)

    # ── hasUndoableCompletions ───────────────────────────────────

    def test_bundle_no_undoable_completions_initially(self):
        """No completions means hasUndoableCompletions is False."""
        bundle = self._create_bundle()
        self._create_team_routepart(order=1, bundle=bundle)

        result = self.team.get_next_open_routepart_formatted()

        self.assertFalse(result["hasUndoableCompletions"])

    def test_bundle_has_undoable_completions_after_complete(self):
        """After completing a destination, hasUndoableCompletions is True."""
        bundle = self._create_bundle()
        _, trp1 = self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=bundle)

        # Complete the destination (not the whole part, just the destination)
        dest = trp1.destinations.first()
        self.team.handle_destination_completion(dest.id)

        result = self.team.get_next_open_routepart_formatted()

        self.assertTrue(result["hasUndoableCompletions"])

    # ── Part data in bundle ──────────────────────────────────────

    def test_bundle_parts_contain_type_and_data(self):
        """Each part in the bundle has type, status, and data with coordinates."""
        bundle = self._create_bundle()
        self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=bundle, route_type=ROUTE_TYPE_IMAGE)

        result = self.team.get_next_open_routepart_formatted()

        self.assertEqual(result["parts"][0]["type"], ROUTE_TYPE_COORDINATE)
        self.assertEqual(result["parts"][1]["type"], ROUTE_TYPE_IMAGE)
        for part in result["parts"]:
            self.assertIn("data", part)
            self.assertIn("coordinates", part["data"])

    # ── Mixed bundle and non-bundle ──────────────────────────────

    def test_mixed_bundle_then_single(self):
        """After completing all bundle parts, next non-bundle part returns single format."""
        bundle = self._create_bundle()
        _, trp1 = self._create_team_routepart(order=1, bundle=bundle)
        self._create_team_routepart(order=2, bundle=None)  # non-bundle part

        # Complete bundle part 1
        now = timezone.now()
        trp1.completed_time = now
        trp1.save()
        trp1.destinations.update(completed_time=now)

        result = self.team.get_next_open_routepart_formatted()

        # Should be the single non-bundle part
        self.assertNotIn("bundle", result)
        self.assertEqual(result["type"], ROUTE_TYPE_COORDINATE)

    # ── Distribution copies bundle FK ────────────────────────────

    def test_distribute_copies_bundle_fk(self):
        """_distribute_routes_for_team copies the bundle FK to TeamRoutePart."""
        bundle = self._create_bundle()
        rp1 = RoutePart.objects.create(
            name="Dist Part 1", route=self.route, route_type=ROUTE_TYPE_COORDINATE,
            order=10, bundle=bundle,
        )
        Destination.objects.create(
            lat=52.1, lng=6.1, radius=25,
            destination_type=DESTINATION_TYPE_MANDATORY,
            routepart=rp1,
        )
        rp2 = RoutePart.objects.create(
            name="Dist Part 2", route=self.route, route_type=ROUTE_TYPE_COORDINATE,
            order=11, bundle=None,
        )
        Destination.objects.create(
            lat=52.2, lng=6.2, radius=25,
            destination_type=DESTINATION_TYPE_MANDATORY,
            routepart=rp2,
        )

        # Create a new team to distribute to (fresh, no existing TRPs)
        team2 = Team.objects.create(
            name="Team 2", code="XYZ99", contact_name="T2",
            contact_email="t2@test.nl", edition=self.edition,
        )
        _distribute_routes_for_team(team2)

        trp_with_bundle = TeamRoutePart.objects.get(team=team2, routepart=rp1)
        trp_without_bundle = TeamRoutePart.objects.get(team=team2, routepart=rp2)

        self.assertEqual(trp_with_bundle.bundle, bundle)
        self.assertIsNone(trp_without_bundle.bundle)

    # ── Single part in bundle ────────────────────────────────────

    def test_bundle_single_part(self):
        """A bundle with only one part still returns bundle format."""
        bundle = self._create_bundle()
        self._create_team_routepart(order=1, bundle=bundle)

        result = self.team.get_next_open_routepart_formatted()

        self.assertTrue(result["bundle"])
        self.assertEqual(len(result["parts"]), 1)
        self.assertEqual(result["parts"][0]["status"], "current")
        self.assertEqual(result["currentIndex"], 0)
