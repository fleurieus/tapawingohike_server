from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

from server.apps.dashboard.models import (
    Organization, Event, Edition, Route, Team, UserProfile,
)
from django.utils import timezone


class OrgFilteringTestMixin:
    """Shared setup: two orgs, each with event/edition/route/team."""

    def setUp(self):
        self.org_a = Organization.objects.create(
            name="Org A", contact_person="A", contact_email="a@a.nl"
        )
        self.org_b = Organization.objects.create(
            name="Org B", contact_person="B", contact_email="b@b.nl"
        )
        # Events
        self.event_a = Event.objects.create(name="Event A", organization=self.org_a)
        self.event_b = Event.objects.create(name="Event B", organization=self.org_b)
        # Editions
        now = timezone.now()
        self.edition_a = Edition.objects.create(
            name="Ed A", event=self.event_a, date_start=now, date_end=now
        )
        self.edition_b = Edition.objects.create(
            name="Ed B", event=self.event_b, date_start=now, date_end=now
        )
        # Routes
        self.route_a = Route.objects.create(name="Route A", edition=self.edition_a)
        self.route_b = Route.objects.create(name="Route B", edition=self.edition_b)
        # Teams
        self.team_a = Team.objects.create(
            name="Team A", edition=self.edition_a, code="AAA",
            contact_name="a", contact_email="a@a.nl"
        )
        self.team_b = Team.objects.create(
            name="Team B", edition=self.edition_b, code="BBB",
            contact_name="b", contact_email="b@b.nl"
        )

        # Users
        self.superadmin = User.objects.create_superuser(
            "superadmin", "sa@test.nl", "pass123"
        )
        UserProfile.objects.create(user=self.superadmin, organization=None)

        self.user_a = User.objects.create_user(
            "user_a", "ua@test.nl", "pass123", is_staff=True
        )
        UserProfile.objects.create(user=self.user_a, organization=self.org_a)

        self.user_b = User.objects.create_user(
            "user_b", "ub@test.nl", "pass123", is_staff=True
        )
        UserProfile.objects.create(user=self.user_b, organization=self.org_b)

        self.user_noprofile = User.objects.create_user(
            "user_noprofile", "np@test.nl", "pass123", is_staff=True
        )
        # Intentionally no profile

        self.client = Client()


class EventsListFilterTest(OrgFilteringTestMixin, TestCase):
    """Org-user only sees their own events."""

    def test_superadmin_sees_all_events(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.get(reverse("backoffice:events_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Event A")
        self.assertContains(resp, "Event B")

    def test_org_user_sees_own_events_only(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(reverse("backoffice:events_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Event A")
        self.assertNotContains(resp, "Event B")

    def test_user_without_profile_sees_nothing(self):
        self.client.login(username="user_noprofile", password="pass123")
        resp = self.client.get(reverse("backoffice:events_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Event A")
        self.assertNotContains(resp, "Event B")


class EditionAccessTest(OrgFilteringTestMixin, TestCase):
    """Org-user gets 404 when accessing another org's editions."""

    def test_org_user_can_access_own_edition(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(
            reverse("backoffice:team_list", args=[self.edition_a.id])
        )
        self.assertEqual(resp.status_code, 200)

    def test_org_user_cannot_access_other_edition(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(
            reverse("backoffice:team_list", args=[self.edition_b.id])
        )
        self.assertEqual(resp.status_code, 404)


class RouteAccessTest(OrgFilteringTestMixin, TestCase):
    """Org-user gets 404 when accessing another org's routes."""

    def test_org_user_can_access_own_route(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(
            reverse("backoffice:routeparts_builder", args=[self.route_a.id])
        )
        self.assertEqual(resp.status_code, 200)

    def test_org_user_cannot_access_other_route(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(
            reverse("backoffice:routeparts_builder", args=[self.route_b.id])
        )
        self.assertEqual(resp.status_code, 404)


class RoutesPageFilterTest(OrgFilteringTestMixin, TestCase):
    """Routes page respects org filtering."""

    def test_org_user_sees_own_routes_only(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(reverse("backoffice:routes_page"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Route A")
        self.assertNotContains(resp, "Route B")


class UserManagementAccessTest(OrgFilteringTestMixin, TestCase):
    """Only superadmins can access user management."""

    def test_superadmin_can_access_user_list(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.get(reverse("backoffice:user_list"))
        self.assertEqual(resp.status_code, 200)

    def test_org_user_cannot_access_user_list(self):
        self.client.login(username="user_a", password="pass123")
        resp = self.client.get(reverse("backoffice:user_list"))
        self.assertEqual(resp.status_code, 403)

    def test_superadmin_can_add_user(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.post(reverse("backoffice:user_add"), {
            "username": "newuser",
            "password": "securepass123",
            "organization": self.org_a.id,
            "is_active": True,
        })
        self.assertEqual(resp.status_code, 302)  # redirect on success
        self.assertTrue(User.objects.filter(username="newuser").exists())
        new_user = User.objects.get(username="newuser")
        self.assertTrue(new_user.is_staff)
        self.assertEqual(new_user.profile.organization, self.org_a)

    def test_superadmin_can_create_superadmin(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.post(reverse("backoffice:user_add"), {
            "username": "newsuperadmin",
            "password": "securepass123",
            # organization omitted → None → superadmin
        })
        self.assertEqual(resp.status_code, 302)
        new_user = User.objects.get(username="newsuperadmin")
        self.assertTrue(new_user.is_superuser)

    def test_superadmin_can_edit_user(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.post(
            reverse("backoffice:user_edit", args=[self.user_a.id]),
            {
                "username": "user_a_renamed",
                "organization": self.org_a.id,
                "is_active": True,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.username, "user_a_renamed")

    def test_superadmin_can_deactivate_other_user(self):
        self.client.login(username="superadmin", password="pass123")
        self.assertTrue(self.user_a.is_active)
        resp = self.client.post(
            reverse("backoffice:user_deactivate", args=[self.user_a.id])
        )
        self.assertEqual(resp.status_code, 302)
        self.user_a.refresh_from_db()
        self.assertFalse(self.user_a.is_active)

    def test_superadmin_cannot_deactivate_self(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.post(
            reverse("backoffice:user_deactivate", args=[self.superadmin.id])
        )
        self.assertEqual(resp.status_code, 400)

    def test_superadmin_can_reset_password(self):
        self.client.login(username="superadmin", password="pass123")
        resp = self.client.post(
            reverse("backoffice:user_reset_password", args=[self.user_a.id]),
            {"new_password": "brandnewpass123"},
        )
        self.assertEqual(resp.status_code, 302)
        self.user_a.refresh_from_db()
        self.assertTrue(self.user_a.check_password("brandnewpass123"))
