import io
from PIL import Image

from django.test import TestCase, Client, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from server.apps.dashboard.models import (
    Edition,
    Event,
    Message,
    Organization,
    Team,
)


def _make_image(fmt="PNG", size=(100, 100)):
    """Create a minimal in-memory image file."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color="red")
    img.save(buf, format=fmt)
    buf.seek(0)
    content_type = "image/png" if fmt == "PNG" else "image/jpeg"
    ext = "png" if fmt == "PNG" else "jpg"
    return SimpleUploadedFile(f"test.{ext}", buf.read(), content_type=content_type)


@override_settings(MEDIA_ROOT="/tmp/tapawingohike_test_media")
class UploadMessageImageTest(TestCase):
    """Tests for POST /api/messages/upload-image/"""

    URL = "/api/messages/upload-image/"

    def setUp(self):
        org = Organization.objects.create(
            name="Org", contact_person="X", contact_email="x@x.nl"
        )
        event = Event.objects.create(name="Event", organization=org)
        self.edition = Edition.objects.create(
            name="Edition",
            date_start=timezone.make_aware(timezone.datetime(2026, 6, 1)),
            date_end=timezone.make_aware(timezone.datetime(2026, 6, 2)),
            event=event,
            messaging_enabled=True,
        )
        self.team = Team.objects.create(
            name="Team A",
            code="TEAM123",
            contact_name="Tester",
            contact_email="t@t.nl",
            edition=self.edition,
        )
        self.client = Client()

    def test_upload_png_success(self):
        image = _make_image("PNG")
        resp = self.client.post(
            self.URL,
            {"image": image},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIn("imageUrl", data["message"])
        self.assertEqual(Message.objects.count(), 1)
        msg = Message.objects.first()
        self.assertTrue(msg.image)
        self.assertEqual(msg.sender_team, self.team)

    def test_upload_jpeg_success(self):
        image = _make_image("JPEG")
        resp = self.client.post(
            self.URL,
            {"image": image},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 201)

    def test_upload_with_text(self):
        image = _make_image("PNG")
        resp = self.client.post(
            self.URL,
            {"image": image, "text": "Kijk dit!"},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 201)
        msg = Message.objects.first()
        self.assertEqual(msg.text, "Kijk dit!")

    def test_missing_team_code(self):
        image = _make_image("PNG")
        resp = self.client.post(self.URL, {"image": image})
        self.assertEqual(resp.status_code, 401)

    def test_invalid_team_code(self):
        image = _make_image("PNG")
        resp = self.client.post(
            self.URL,
            {"image": image},
            HTTP_X_TEAM_CODE="INVALID",
        )
        self.assertEqual(resp.status_code, 401)

    def test_messaging_disabled(self):
        self.edition.messaging_enabled = False
        self.edition.save()
        image = _make_image("PNG")
        resp = self.client.post(
            self.URL,
            {"image": image},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 403)

    def test_no_image_provided(self):
        resp = self.client.post(
            self.URL,
            {},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_content_type(self):
        bad_file = SimpleUploadedFile("test.gif", b"GIF89a", content_type="image/gif")
        resp = self.client.post(
            self.URL,
            {"image": bad_file},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("JPEG", resp.json()["error"])

    def test_file_too_large(self):
        # Create a file just over 5 MB
        large_data = b"\x00" * (5 * 1024 * 1024 + 1)
        large_file = SimpleUploadedFile(
            "big.png", large_data, content_type="image/png"
        )
        resp = self.client.post(
            self.URL,
            {"image": large_file},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("5 MB", resp.json()["error"])

    def test_get_not_allowed(self):
        resp = self.client.get(self.URL, HTTP_X_TEAM_CODE="TEAM123")
        self.assertEqual(resp.status_code, 405)

    def test_to_app_format_includes_image_url(self):
        image = _make_image("PNG")
        self.client.post(
            self.URL,
            {"image": image},
            HTTP_X_TEAM_CODE="TEAM123",
        )
        msg = Message.objects.first()
        fmt = msg.to_app_format()
        self.assertIn("imageUrl", fmt)
        self.assertIn("/media/messages/", fmt["imageUrl"])

    def test_to_app_format_no_image(self):
        """Text-only messages should not have imageUrl."""
        msg = Message.objects.create(
            edition=self.edition,
            sender_team=self.team,
            text="Hello",
        )
        fmt = msg.to_app_format()
        self.assertNotIn("imageUrl", fmt)
