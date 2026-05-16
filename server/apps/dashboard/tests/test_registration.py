from smtplib import SMTPException
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from server.apps.dashboard.models import Edition, Event, Organization, Team


class RegistrationTestCase(TestCase):
    def setUp(self):
        org = Organization.objects.create(
            name="Org", contact_person="T", contact_email="t@t.nl"
        )
        event = Event.objects.create(name="Event", organization=org)
        self.edition = Edition.objects.create(
            name="Aanmeldtocht",
            event=event,
            date_start=timezone.make_aware(timezone.datetime(2026, 6, 1)),
            date_end=timezone.make_aware(timezone.datetime(2026, 6, 2)),
            registration_mode=Edition.REGISTRATION_QUICK,
        )
        self.url = reverse("register", args=[self.edition.slug])

    # ── happy path ──────────────────────────────────────────────────

    def test_quick_registration_succeeds(self):
        resp = Client().post(
            self.url, {"contact_name": "Jan", "contact_email": "jan@example.com"}
        )
        self.assertEqual(resp.status_code, 200)
        team = Team.objects.get(edition=self.edition)
        self.assertTrue(team.is_activated)
        self.assertTrue(team.code)

    # ── already-registered e-mail ───────────────────────────────────

    def test_duplicate_email_is_rejected_with_message(self):
        Team.objects.create(
            edition=self.edition, name="A", contact_name="A",
            contact_email="dup@example.com", code="ABC12",
        )
        resp = Client().post(
            self.url,
            {"contact_name": "Bob", "contact_email": "DUP@example.com"},
        )
        self.assertEqual(resp.status_code, 200)  # not 500
        self.assertContains(resp, "al aangemeld voor deze editie")
        # No second team created
        self.assertEqual(self.edition.teams.count(), 1)

    # ── undeliverable address / mail-server error ───────────────────

    def test_mail_failure_shows_error_not_500(self):
        with patch(
            "server.views.send_mail", side_effect=SMTPException("nope")
        ):
            resp = Client().post(
                self.url,
                {"contact_name": "Eve", "contact_email": "eve@example.com"},
            )
        self.assertEqual(resp.status_code, 200)  # not 500
        self.assertContains(resp, "konden geen e-mail sturen")
        # Rolled back — no half-registration
        self.assertEqual(Team.objects.count(), 0)

    def test_extended_duplicate_email_rejected(self):
        self.edition.registration_mode = Edition.REGISTRATION_EXTENDED
        self.edition.save()
        Team.objects.create(
            edition=self.edition, name="T", contact_name="C",
            contact_email="x@example.com", code="",
        )
        resp = Client().post(
            self.url,
            {
                "contact_name": "C2",
                "contact_address": "Straat 1",
                "contact_phone": "06",
                "contact_email": "x@example.com",
                "team_name": "Team 2",
                "member_names": "A, B",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "al aangemeld voor deze editie")
        self.assertEqual(self.edition.teams.count(), 1)
