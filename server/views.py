import secrets
import string

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.forms.models import model_to_dict
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from server.apps.dashboard.models import (
    Destination,
    Edition,
    Team,
    TeamRoutePart,
)
from server.forms import ExtendedRegistrationForm, QuickRegistrationForm


def index(request):
    return render(request, "index.html")


def _generate_team_code(length=5):
    """Generate a short, easy-to-remember team code.

    Uses uppercase letters + digits, excluding ambiguous characters
    (O/0, I/1, L) to avoid confusion when typing.
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _unique_team_code(edition):
    """Generate a team code that doesn't exist yet in this edition."""
    existing = set(edition.teams.values_list("code", flat=True))
    for _ in range(100):
        code = _generate_team_code()
        if code not in existing:
            return code
    raise RuntimeError("Could not generate unique team code")


def _distribute_routes_for_team(team):
    """Distribute all route parts to a single team (mirrors admin action logic)."""
    edition = team.edition
    for route in edition.routes.all():
        for part in route.routeparts.select_related(
            "routedata_image", "routedata_audio"
        ).all():
            trp, _ = TeamRoutePart.objects.get_or_create(
                routepart=part,
                team=team,
                defaults={
                    "route": route,
                    "name": part.name,
                    "route_type": part.route_type,
                    "routepart_zoom": part.routepart_zoom,
                    "routepart_fullscreen": part.routepart_fullscreen,
                    "routedata_image": part.routedata_image,
                    "routedata_audio": part.routedata_audio,
                    "final": part.final,
                    "order": part.order,
                },
            )

            for d in part.destinations.all().order_by("id"):
                Destination.objects.get_or_create(
                    teamroutepart=trp,
                    lat=d.lat,
                    lng=d.lng,
                    radius=d.radius,
                    destination_type=d.destination_type,
                    defaults={
                        "confirm_by_user": d.confirm_by_user,
                        "hide_for_user": d.hide_for_user,
                    },
                )


def _send_team_code_email(team):
    """Send the team code to the contact email."""
    send_mail(
        subject=f"Je teamcode voor {team.edition.name}",
        message=(
            f"Hallo {team.contact_name},\n\n"
            f"Je bent aangemeld voor {team.edition.name}.\n"
            f"Je teamcode is: {team.code}\n\n"
            f"Veel plezier!\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[team.contact_email],
        fail_silently=False,
    )


def _send_confirmation_email(team, confirmation_text):
    """Send a confirmation email for extended registration."""
    body = confirmation_text or (
        f"Hallo {team.contact_name},\n\n"
        f"Bedankt voor je aanmelding voor {team.edition.name}.\n"
        f"We nemen zo snel mogelijk contact met je op.\n"
    )
    send_mail(
        subject=f"Bevestiging aanmelding {team.edition.name}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[team.contact_email],
        fail_silently=False,
    )


def register(request, edition_id):
    """Public registration view — shows quick or extended form based on edition settings."""
    edition = get_object_or_404(Edition, pk=edition_id)

    if edition.registration_mode == Edition.REGISTRATION_NONE:
        raise Http404

    is_quick = edition.registration_mode == Edition.REGISTRATION_QUICK
    FormClass = QuickRegistrationForm if is_quick else ExtendedRegistrationForm

    if request.method == "POST":
        form = FormClass(request.POST)
        if form.is_valid():
            with transaction.atomic():
                if is_quick:
                    code = _unique_team_code(edition)
                    team = Team.objects.create(
                        edition=edition,
                        name=form.cleaned_data["contact_name"],
                        contact_name=form.cleaned_data["contact_name"],
                        contact_email=form.cleaned_data["contact_email"],
                        code=code,
                        is_activated=True,
                    )
                    _distribute_routes_for_team(team)
                    _send_team_code_email(team)
                else:
                    team = Team.objects.create(
                        edition=edition,
                        name=form.cleaned_data["team_name"],
                        contact_name=form.cleaned_data["contact_name"],
                        contact_email=form.cleaned_data["contact_email"],
                        contact_phone=form.cleaned_data.get("contact_phone", ""),
                        contact_address=form.cleaned_data.get("contact_address", ""),
                        member_names=form.cleaned_data.get("member_names", ""),
                        remarks=form.cleaned_data.get("remarks", ""),
                        code="",
                        is_activated=False,
                    )
                    _send_confirmation_email(
                        team, edition.registration_confirmation_text
                    )

            return render(
                request,
                "registration/success.html",
                {"edition": edition, "is_quick": is_quick, "team": team},
            )
    else:
        form = FormClass()

    return render(
        request,
        "registration/form.html",
        {"edition": edition, "form": form, "is_quick": is_quick},
    )