import logging

from PIL import Image

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from server.apps.dashboard.models import Team, Message
from server.apps.asgi_socket.consumers import (
    push_to_team,
    push_to_backoffice,
)

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_FORMATS = {"JPEG", "PNG"}


@csrf_exempt
@require_POST
def upload_message_image(request):
    """
    HTTP endpoint for teams to upload an image message.

    Auth: X-Team-Code header containing the team code.
    Body: multipart/form-data with an 'image' file field.
    """
    team_code = request.headers.get("X-Team-Code", "").strip()
    if not team_code:
        return JsonResponse({"error": "Missing X-Team-Code header"}, status=401)

    try:
        team = Team.objects.select_related("edition").get(code=team_code)
    except Team.DoesNotExist:
        return JsonResponse({"error": "Invalid team code"}, status=401)

    if not team.edition.messaging_enabled:
        return JsonResponse({"error": "Messaging is disabled"}, status=403)

    image = request.FILES.get("image")
    if not image:
        return JsonResponse({"error": "No image file provided"}, status=400)

    if image.size > MAX_IMAGE_SIZE:
        return JsonResponse(
            {"error": "Image exceeds maximum size of 5 MB"}, status=400
        )

    # Validate actual image content with Pillow (ignores unreliable content_type)
    try:
        img = Image.open(image)
        img.verify()
        if img.format not in ALLOWED_FORMATS:
            return JsonResponse(
                {"error": "Only JPEG and PNG images are allowed"}, status=400
            )
    except Exception:
        return JsonResponse(
            {"error": "Only JPEG and PNG images are allowed"}, status=400
        )

    # Reset file pointer after verify() consumed it
    image.seek(0)

    text = request.POST.get("text", "").strip()

    msg = Message.objects.create(
        edition=team.edition,
        sender_team=team,
        recipient_team=None,  # to organisation
        text=text,
        image=image,
    )

    # Push to the team that sent it (confirmation) + backoffice
    msg_payload = {"type": "message", "data": msg.to_app_format()}
    push_to_team(team.id, msg_payload)
    push_to_backoffice(team.edition_id, msg_payload)

    return JsonResponse({"ok": True, "message": msg.to_app_format()}, status=201)
