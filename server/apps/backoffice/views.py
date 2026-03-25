from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q, Max, Min, Count, F, fields, OuterRef, Subquery, ExpressionWrapper
from django.db.models.functions import Round, TruncTime
from django.views.decorators.http import require_POST, require_http_methods
from django.conf import settings
from django.urls import reverse
from urllib.parse import urlparse, parse_qs
from django import forms
from django.utils import timezone
from django.forms.models import model_to_dict
import json
import googlemaps
from collections import defaultdict
from server.apps.asgi_socket.consumers import push_to_team, push_to_edition, push_to_backoffice
from .forms import RouteForm, RoutePartForm, BundleForm, DestinationForm, EditionRegistrationForm, UserManagementForm
from django.contrib.auth.models import User
from server.apps.dashboard.models import (
    Event, Edition, Route, Bundle, RoutePart, TeamRoutePart, Destination, Team, File, LocationLog,
    Message, UserProfile, DESTINATION_TYPE_MANDATORY, DESTINATION_TYPE_CHOICE,
)
from server.apps.dashboard.constants import FILE_TYPE_IMAGE, FILE_TYPE_AUDIO
from .permissions import org_qs, superuser_required


# ── Sidebar context helper ──────────────────────────────────────────
def edition_ctx(edition, nav_active="", active_route_id=None):
    """Return sidebar context dict for templates that have an edition."""
    routes = list(edition.routes.order_by("name").values("id", "name")) if edition else []
    # Unread messages: sent by teams, not yet read by organisation
    unread_messages = 0
    if edition and edition.messaging_enabled and nav_active != "messages":
        unread_messages = Message.objects.filter(
            edition=edition, sender_team__isnull=False, read_at__isnull=True,
        ).count()
    return {
        "sidebar_edition": edition,
        "sidebar_routes": routes,
        "nav_active": nav_active,
        "active_route_id": active_route_id,
        "sidebar_unread_messages": unread_messages,
    }


@staff_member_required
def events_list(request):
    events = (
        org_qs(request.user, Event.objects, "organization")
        .select_related("organization")
        .annotate(
            editions_count=Count("editions", distinct=True),
            routes_count=Count("editions__routes", distinct=True),
            routeparts_count=Count("editions__routes__routeparts", distinct=True),
            teams_count=Count("editions__teams", distinct=True),
            latest_edition_id=Subquery(
                Edition.objects.filter(event=OuterRef("pk"))
                .order_by("-date_start", "-id")
                .values("id")[:1]
            ),
            latest_edition_name=Subquery(
                Edition.objects.filter(event=OuterRef("pk"))
                .order_by("-date_start", "-id")
                .values("name")[:1]
            ),
        )
        .order_by("organization__name", "name")
    )
    # Group events by organization
    grouped = []
    current_org = None
    current_events = []
    for ev in events:
        if ev.organization_id != (current_org.id if current_org else None):
            if current_org is not None:
                grouped.append((current_org, current_events))
            current_org = ev.organization
            current_events = []
        current_events.append(ev)
    if current_org is not None:
        grouped.append((current_org, current_events))

    return render(request, "backoffice/events_list.html", {
        "grouped_events": grouped,
        "nav_active": "events",
    })


def _dashboard_ctx(edition):
    """Collect all dashboard stats for an edition."""
    # Reset stale online status (last_seen > 1 hour ago)
    stale_cutoff = timezone.now() - timezone.timedelta(hours=1)
    edition.teams.filter(online=True, last_seen__lt=stale_cutoff).update(online=False)

    # Teams stats
    teams = edition.teams.order_by("name")
    teams_total = teams.count()
    teams_active = teams.filter(is_activated=True).count()
    teams_online = teams.filter(online=True).count()

    team_progress = []
    for t in teams:
        total_trp = t.teamrouteparts.count()
        completed_trp = t.teamrouteparts.filter(completed_time__isnull=False).count()
        team_progress.append({
            "team": t,
            "total": total_trp,
            "completed": completed_trp,
            "pct": round(completed_trp / total_trp * 100) if total_trp else 0,
        })

    # Routes stats
    routes = (
        edition.routes.order_by("name")
        .annotate(
            parts_count=Count("routeparts", distinct=True),
            teams_count=Count("routeparts__teamrouteparts__team", distinct=True),
            completed_count=Count(
                "routeparts__teamrouteparts",
                filter=Q(routeparts__teamrouteparts__completed_time__isnull=False),
            ),
            total_trp_count=Count("routeparts__teamrouteparts"),
        )
    )
    for r in routes:
        r.completion_pct = round(r.completed_count / r.total_trp_count * 100) if r.total_trp_count else 0

    # Messages stats
    messages_total = 0
    messages_unread = 0
    recent_messages = []
    if edition.messaging_enabled:
        all_msgs = Message.objects.filter(edition=edition)
        messages_total = all_msgs.count()
        messages_unread = all_msgs.filter(read_at__isnull=True, sender_team__isnull=False).count()
        recent_messages = (
            all_msgs.select_related("sender_team", "recipient_team")
            .order_by("-created_at")[:5]
        )

    routeparts_count = RoutePart.objects.filter(route__edition=edition).count()

    return {
        "edition": edition,
        "teams_total": teams_total,
        "teams_active": teams_active,
        "teams_online": teams_online,
        "team_progress": team_progress,
        "routes": routes,
        "routes_count": routes.count(),
        "routeparts_count": routeparts_count,
        "messages_total": messages_total,
        "messages_unread": messages_unread,
        "recent_messages": recent_messages,
    }


@staff_member_required
def edition_dashboard(request, edition_id: int):
    """Dashboard overview for a single edition."""
    edition = get_object_or_404(
        org_qs(request.user, Edition.objects, "event__organization")
        .select_related("event__organization"),
        pk=edition_id,
    )
    ctx = _dashboard_ctx(edition)
    ctx.update(edition_ctx(edition, "dashboard"))
    return render(request, "backoffice/edition_dashboard.html", ctx)


@staff_member_required
def edition_dashboard_live(request, edition_id: int):
    """HTMX partial: live-refreshable dashboard content."""
    edition = get_object_or_404(
        org_qs(request.user, Edition.objects, "event__organization")
        .select_related("event__organization"),
        pk=edition_id,
    )
    ctx = _dashboard_ctx(edition)
    return render(request, "backoffice/_edition_dashboard_live.html", ctx)


@staff_member_required
def edition_list(request, event_id: int | None = None):
    qs = (
        org_qs(request.user, Edition.objects, "event__organization")
        .select_related("event")
        .annotate(
            team_count=Count("teams", distinct=True),
            route_count=Count("routes", distinct=True),
            routeparts_count=Count("routes__routeparts", distinct=True),
        )
    )
    event = None
    if event_id:
        qs = qs.filter(event_id=event_id)
        event = org_qs(request.user, Event.objects, "organization").filter(pk=event_id).first()

    editions = qs.order_by(
        F("date_start").desc(nulls_last=True),
        F("date_end").desc(nulls_last=True),
        "-id",
    )
    return render(request, "backoffice/edition_list.html", {
        "editions": editions,
        "event": event,
        "nav_active": "events",
    })



@staff_member_required
def edition_routes_stats(request, edition_id: int):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    routes = (
        Route.objects.filter(edition=edition)
        .annotate(parts_count=Count("routeparts"))
        .order_by("name")
    )
    return render(request, "backoffice/_edition_routes_stats.html", {"routes": routes})


LOCATION_INTERVAL_CHOICES = [
    (30, "30 seconden"),
    (60, "1 minuut"),
    (120, "2 minuten"),
    (300, "5 minuten (standaard)"),
]

class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        exclude = ["edition"]  # laat alle overige velden toe, edition zetten we in de view
        widgets = {
            # optioneel wat nette widgets
            "name": forms.TextInput(attrs={"class": "w-full rounded-lg border px-3 py-2"}),
            "notes": forms.Textarea(attrs={"class": "w-full rounded-lg border px-3 py-2", "rows": 3}),
            "location_update_interval": forms.Select(
                choices=LOCATION_INTERVAL_CHOICES,
                attrs={"class": "w-full rounded-lg border px-3 py-2"},
            ),
        }

@staff_member_required
def team_list(request, edition_id: int):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)

    # Reset stale online status
    stale_cutoff = timezone.now() - timezone.timedelta(hours=1)
    edition.teams.filter(online=True, last_seen__lt=stale_cutoff).update(online=False)

    teams = edition.teams.annotate(
        trp_total=Count("teamrouteparts"),
        trp_completed=Count("teamrouteparts", filter=Q(teamrouteparts__completed_time__isnull=False)),
    ).order_by("name")

    # Apply filters from query params
    status_filter = request.GET.get("status")
    search = request.GET.get("q", "").strip()
    if status_filter == "online":
        teams = teams.filter(online=True)
    elif status_filter == "active":
        teams = teams.filter(is_activated=True)
    elif status_filter == "registered":
        teams = teams.filter(is_activated=False)
    if search:
        teams = teams.filter(name__icontains=search)

    ctx = {
        "edition": edition,
        "teams": teams,
        "status_filter": status_filter or "",
        "search": search,
    }
    ctx.update(edition_ctx(edition, "teams"))
    return render(request, "backoffice/team_list.html", ctx)

@staff_member_required
def team_add(request, edition_id: int):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    if request.method == "POST":
        form = TeamForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.edition = edition
            obj.save()
            return redirect("backoffice:team_list", edition_id=edition.id)
    else:
        form = TeamForm()
    ctx = {"edition": edition, "form": form, "mode": "add"}
    ctx.update(edition_ctx(edition, "teams"))
    return render(request, "backoffice/team_form.html", ctx)

@staff_member_required
def team_edit(request, edition_id: int, pk: int):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    team = get_object_or_404(Team, pk=pk, edition=edition)
    if request.method == "POST":
        old_interval = team.location_update_interval
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()

            # Push new interval to connected app if it changed
            if team.location_update_interval != old_interval and team.online:
                push_to_team(team.id, {
                    "type": "config",
                    "data": {
                        "locationInterval": team.location_update_interval,
                    },
                })

            return redirect("backoffice:team_list", edition_id=edition.id)
    else:
        form = TeamForm(instance=team)
    ctx = {"edition": edition, "form": form, "mode": "edit", "team": team}
    ctx.update(edition_ctx(edition, "teams"))
    return render(request, "backoffice/team_form.html", ctx)

@staff_member_required
@require_POST
def team_delete(request, edition_id: int, pk: int):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    team = get_object_or_404(Team, pk=pk, edition=edition)
    team.delete()
    return redirect("backoffice:team_list", edition_id=edition.id)


@staff_member_required
def destinations_editor(request, rp_id:int):
    rp = get_object_or_404(org_qs(request.user, RoutePart.objects, "route__edition__event__organization"), pk=rp_id)
    dests = rp.destinations.all().order_by("id")

    dest_items = list(dests.values(
        "id", "lat", "lng", "destination_type", "radius",
        "confirm_by_user", "hide_for_user"
    ))

    ctx = {
        "rp": rp,
        "destinations": dests,
        "dest_items": dest_items,
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    ctx.update(edition_ctx(rp.route.edition, "routes", active_route_id=rp.route_id))
    return render(request, "backoffice/destinations.html", ctx)



@staff_member_required
def destination_form(request, rp_id:int, pk:int=None):
    rp = get_object_or_404(org_qs(request.user, RoutePart.objects, "route__edition__event__organization"), pk=rp_id)
    inst = get_object_or_404(Destination, pk=pk, routepart=rp) if pk else None

    if request.method == "POST":
        form = DestinationForm(request.POST, instance=inst)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.routepart = rp               # expliciet
            obj.teamroutepart = None
            obj.save()

            # payload voor de kaart
            from django.db.models import Count
            rp_order = rp.order
            # eenvoudige index binnen dit part (1-based)
            idx = Destination.objects.filter(routepart=rp).count()

            item = {
                "id": obj.id,
                "lat": obj.lat,
                "lng": obj.lng,
                "radius": obj.radius,
                "confirm_by_user": obj.confirm_by_user,
                "hide_for_user": obj.hide_for_user,
                "rp_id": rp.id,
                "rp_order": rp_order,
                "idx": idx,
            }

            # Leeg geen DOM hier; laat de client dat doen via event
            resp = HttpResponse("")
            # Stuur een custom event met payload
            resp["HX-Trigger"] = json.dumps({"destination:saved": {"item": item}})
            
            return resp

        # INVALID → formulier terug in het sidepanel (200)
        html = render_to_string("backoffice/_destination_form.html",
                                {"form": form, "rp": rp, "pk": pk}, request=request)
        resp = HttpResponse(html)
        resp["HX-Retarget"] = "#sidepanel"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    # GET: formulier tonen; initial lat/lng bij klik op map
    initial = {}
    if not inst:
        qlat, qlng = request.GET.get("lat"), request.GET.get("lng")
        if qlat and qlng:
            initial["lat"] = qlat
            initial["lng"] = qlng
    form = DestinationForm(instance=inst, initial=initial)
    html = render_to_string("backoffice/_destination_form.html",
                            {"form": form, "rp": rp, "pk": pk}, request=request)
    return HttpResponse(html)


@staff_member_required
def destination_delete(request, rp_id:int, pk:int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    rp = get_object_or_404(org_qs(request.user, RoutePart.objects, "route__edition__event__organization"), pk=rp_id)
    inst = get_object_or_404(Destination, pk=pk, routepart=rp)
    inst.delete()
    return HttpResponse("OK")


@staff_member_required
@require_POST
def destination_move(request, rp_id: int, pk: int):
    rp = get_object_or_404(org_qs(request.user, RoutePart.objects, "route__edition__event__organization"), pk=rp_id)
    inst = get_object_or_404(Destination, pk=pk, routepart=rp)

    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return HttpResponseBadRequest("Invalid JSON")
        lat = payload.get("lat")
        lng = payload.get("lng")
    else:
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")

    try:
        lat = float(str(lat).replace(",", "."))
        lng = float(str(lng).replace(",", "."))
    except Exception:
        return HttpResponseBadRequest("Invalid lat/lng")

    inst.lat = lat
    inst.lng = lng
    inst.save(update_fields=["lat", "lng"])
    return JsonResponse({"ok": True, "id": inst.id, "lat": inst.lat, "lng": inst.lng})

@staff_member_required
@require_POST
def destination_update(request, rp_id: int, pk: int):
    """
    JSON body: { "radius": int, "confirm_by_user": bool, "hide_for_user": bool }
    """
    rp = get_object_or_404(org_qs(request.user, RoutePart.objects, "route__edition__event__organization"), pk=rp_id)
    inst = get_object_or_404(Destination, pk=pk, routepart=rp)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    changed = []
    if "radius" in payload:
        try:
            radius = int(payload["radius"])
            inst.radius = radius
            changed.append("radius")
        except Exception:
            return HttpResponseBadRequest("Invalid radius")
    if "confirm_by_user" in payload:
        inst.confirm_by_user = bool(payload["confirm_by_user"])
        changed.append("confirm_by_user")
    if "hide_for_user" in payload:
        inst.hide_for_user = bool(payload["hide_for_user"])
        changed.append("hide_for_user")

    if changed:
        inst.save(update_fields=changed)

    return JsonResponse({
        "ok": True,
        "id": inst.id,
        "radius": inst.radius,
        "confirm_by_user": inst.confirm_by_user,
        "hide_for_user": inst.hide_for_user,
    })


# -------- Team Destinations (TeamRoutePart-level) --------

@staff_member_required
def team_destinations_editor(request, trp_id: int):
    trp = get_object_or_404(
        org_qs(request.user, TeamRoutePart.objects, "route__edition__event__organization"),
        pk=trp_id,
    )
    dests = trp.destinations.all().order_by("id")
    dest_items = list(dests.values(
        "id", "lat", "lng", "destination_type", "radius",
        "confirm_by_user", "hide_for_user"
    ))
    ctx = {
        "rp": trp,  # reuse 'rp' context key so the template works for both
        "destinations": dests,
        "dest_items": dest_items,
        "is_team_mode": True,
        "team": trp.team,
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    ctx.update(edition_ctx(trp.route.edition, "distribution", active_route_id=trp.route_id))
    return render(request, "backoffice/destinations.html", ctx)


@staff_member_required
def team_destination_form(request, trp_id: int, pk: int = None):
    trp = get_object_or_404(
        org_qs(request.user, TeamRoutePart.objects, "route__edition__event__organization"),
        pk=trp_id,
    )
    inst = get_object_or_404(Destination, pk=pk, teamroutepart=trp) if pk else None

    if request.method == "POST":
        form = DestinationForm(request.POST, instance=inst)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.teamroutepart = trp
            obj.routepart = None
            obj.save()

            idx = Destination.objects.filter(teamroutepart=trp).count()
            item = {
                "id": obj.id,
                "lat": obj.lat,
                "lng": obj.lng,
                "radius": obj.radius,
                "confirm_by_user": obj.confirm_by_user,
                "hide_for_user": obj.hide_for_user,
                "rp_id": trp.id,
                "rp_order": trp.order,
                "idx": idx,
            }
            resp = HttpResponse("")
            resp["HX-Trigger"] = json.dumps({"destination:saved": {"item": item}})
            return resp

        html = render_to_string("backoffice/_destination_form.html",
                                {"form": form, "rp": trp, "pk": pk, "is_team_mode": True}, request=request)
        resp = HttpResponse(html)
        resp["HX-Retarget"] = "#sidepanel"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    initial = {}
    if not inst:
        qlat, qlng = request.GET.get("lat"), request.GET.get("lng")
        if qlat and qlng:
            initial["lat"] = qlat
            initial["lng"] = qlng
    form = DestinationForm(instance=inst, initial=initial)
    html = render_to_string("backoffice/_destination_form.html",
                            {"form": form, "rp": trp, "pk": pk, "is_team_mode": True}, request=request)
    return HttpResponse(html)


@staff_member_required
def team_destination_delete(request, trp_id: int, pk: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")
    trp = get_object_or_404(
        org_qs(request.user, TeamRoutePart.objects, "route__edition__event__organization"),
        pk=trp_id,
    )
    inst = get_object_or_404(Destination, pk=pk, teamroutepart=trp)
    inst.delete()
    return HttpResponse("OK")


@staff_member_required
@require_POST
def team_destination_move(request, trp_id: int, pk: int):
    trp = get_object_or_404(
        org_qs(request.user, TeamRoutePart.objects, "route__edition__event__organization"),
        pk=trp_id,
    )
    inst = get_object_or_404(Destination, pk=pk, teamroutepart=trp)

    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body.decode("utf-8"))
        except Exception:
            return HttpResponseBadRequest("Invalid JSON")
        lat = payload.get("lat")
        lng = payload.get("lng")
    else:
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")

    try:
        lat = float(str(lat).replace(",", "."))
        lng = float(str(lng).replace(",", "."))
    except Exception:
        return HttpResponseBadRequest("Invalid lat/lng")

    inst.lat = lat
    inst.lng = lng
    inst.save(update_fields=["lat", "lng"])
    return JsonResponse({"ok": True, "id": inst.id, "lat": inst.lat, "lng": inst.lng})


@staff_member_required
@require_POST
def team_destination_update(request, trp_id: int, pk: int):
    trp = get_object_or_404(
        org_qs(request.user, TeamRoutePart.objects, "route__edition__event__organization"),
        pk=trp_id,
    )
    inst = get_object_or_404(Destination, pk=pk, teamroutepart=trp)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    changed = []
    if "radius" in payload:
        try:
            radius = int(payload["radius"])
            inst.radius = radius
            changed.append("radius")
        except Exception:
            return HttpResponseBadRequest("Invalid radius")
    if "confirm_by_user" in payload:
        inst.confirm_by_user = bool(payload["confirm_by_user"])
        changed.append("confirm_by_user")
    if "hide_for_user" in payload:
        inst.hide_for_user = bool(payload["hide_for_user"])
        changed.append("hide_for_user")

    if changed:
        inst.save(update_fields=changed)

    return JsonResponse({
        "ok": True,
        "id": inst.id,
        "radius": inst.radius,
        "confirm_by_user": inst.confirm_by_user,
        "hide_for_user": inst.hide_for_user,
    })


# -------- Routes --------
@staff_member_required
def routes_page(request):
    editions = org_qs(request.user, Edition.objects, "event__organization").order_by('name')
    routes = _filtered_routes(request)
    selected_edition = None
    ed_id = request.GET.get('edition')
    if ed_id:
        selected_edition = (
            org_qs(request.user, Edition.objects, "event__organization")
            .select_related("event").filter(pk=ed_id).first()
        )
    ctx = {
        "editions": editions,
        "routes": routes,
        "selected_edition": selected_edition,
    }
    if selected_edition:
        ctx.update(edition_ctx(selected_edition, "routes"))
    return render(request, "backoffice/routes.html", ctx)

def _filtered_routes(request):
    qs = org_qs(request.user, Route.objects, "edition__event__organization") \
         .select_related('edition') \
         .annotate(parts_count=Count('routeparts'))
    if (ed := request.GET.get('edition')):
        qs = qs.filter(edition_id=ed)
    if (q := request.GET.get('q')):
        qs = qs.filter(Q(name__icontains=q) | Q(edition__name__icontains=q))
    return qs.order_by('edition__name', 'name')

@staff_member_required
def routes_list(request):
    routes = _filtered_routes(request)
    return render(request, "backoffice/_routes_list.html", {"routes": routes})

@staff_member_required
def route_form(request, pk=None):
    instance = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=pk) if pk else None

    if request.method == "GET":
        form = RouteForm(instance=instance)
        form.fields["edition"].queryset = org_qs(request.user, Edition.objects, "event__organization")
        return render(request, "backoffice/_route_form.html", {"form": form})

    # POST
    form = RouteForm(request.POST, instance=instance)
    form.fields["edition"].queryset = org_qs(request.user, Edition.objects, "event__organization")
    if form.is_valid():
        obj = form.save()
        new_form = RouteForm(instance=obj)
        new_form.fields["edition"].queryset = org_qs(request.user, Edition.objects, "event__organization")
        return render(request, "backoffice/_route_form.html", {"form": new_form, "saved_ok": True})
    else:
        return render(request, "backoffice/_route_form.html", {"form": form})

@staff_member_required
@require_http_methods(["DELETE"])
def route_delete(request, pk):
    obj = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=pk)
    obj.delete()
    # Row wordt vervangen door niets dankzij hx-swap="outerHTML"
    return HttpResponse(status=204)

# -------- RouteParts builder --------
@staff_member_required
def routeparts_builder(request, route_id:int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization").select_related("edition"), pk=route_id)
    parts = list(
    route.routeparts
         .select_related("routedata_image","routedata_audio","bundle")
         .annotate(dest_count=Count("destinations"))
         .order_by("order")
    )

    # parts = list(route.routeparts.select_related("routedata_image","routedata_audio").all().order_by("order"))

    # Alle destinations van deze route + volgnummer binnen part
    dest_qs = (
        Destination.objects
        .filter(routepart__route=route, routepart__isnull=False)
        .select_related("routepart")
        .order_by("routepart__order", "id")
    )
    counters = defaultdict(int)
    dest_items = []
    for d in dest_qs:
        rp = d.routepart
        counters[rp.id] += 1
        dest_items.append({
            "id": d.id,
            "lat": d.lat,
            "lng": d.lng,
            "radius": d.radius,
            "confirm_by_user": d.confirm_by_user,
            "hide_for_user": d.hide_for_user,
            "rp_id": rp.id,
            "rp_order": rp.order,
            "rp_name": rp.name,
            "idx": counters[rp.id],
        })

    bundles = list(route.bundles.all())

    ctx = {
        "route": route,
        "parts": parts,
        "bundles": bundles,
        "dest_items": dest_items,
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    ctx.update(edition_ctx(route.edition, "routes", active_route_id=route.id))
    return render(request, "backoffice/routeparts.html", ctx)



@staff_member_required
def routepart_form(request, route_id:int, pk:int=None):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    inst = get_object_or_404(RoutePart, pk=pk, route=route) if pk else None

    if request.method == "POST":
        form = RoutePartForm(request.POST, request.FILES, instance=inst, route=route)

        if form.is_valid():
            # Altijd commit=False zodat we verplichte velden kunnen zetten
            obj = form.save(commit=False)

            # Nieuw? Vul verplichte velden in
            if inst is None:
                obj.route = route
                # order = max(order)+1 binnen deze route
                max_order = route.routeparts.aggregate(Max("order")).get("order__max") or 0
                # Alleen zetten als het formulier geen 'order' bevat
                if not getattr(obj, "order", None):
                    obj.order = max_order + 1

            # Geüpload bestand heeft voorrang boven dropdown-keuze
            if form.cleaned_data.get("new_image_upload"):
                new_file = File(category=FILE_TYPE_IMAGE)
                new_file.file = form.cleaned_data["new_image_upload"]
                new_file.save()
                obj.routedata_image = new_file

            if form.cleaned_data.get("new_audio_upload"):
                new_file = File(category=FILE_TYPE_AUDIO)
                new_file.file = form.cleaned_data["new_audio_upload"]
                new_file.save()
                obj.routedata_audio = new_file

            obj.save()  # nu veilig saven

            # Render het list item (met dest_count)
            p = (
                RoutePart.objects.filter(pk=obj.pk)
                .annotate(dest_count=Count("destinations"))
                .select_related("route")
                .first()
            )
            html = render_to_string(
                "backoffice/_routepart_item.html",
                {"p": p, "route": p.route, "request": request},
            )
            resp = HttpResponse(html)
            resp["HX-Trigger"] = "routepart:saved"  # → laat sidepanel leeglopen
            return resp

        # INVALID: formulier terug in sidepanel (200), geen htmx:error
        html = render_to_string(
            "backoffice/_routepart_form.html",
            {"form": form, "route": route, "pk": pk, "request": request},
        )
        resp = HttpResponse(html)
        resp["HX-Retarget"] = "#sidepanel"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    # GET: formulier tonen
    form = RoutePartForm(instance=inst, route=route)
    html = render_to_string(
        "backoffice/_routepart_form.html",
        {"form": form, "route": route, "pk": pk, "request": request},
    )
    return HttpResponse(html)


@staff_member_required
@require_POST
def routepart_delete(request, route_id:int, pk:int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    inst = get_object_or_404(RoutePart, pk=pk, route=route)
    inst.delete()

    # Lege body is ok; stuur een trigger zodat de client markers kan opruimen
    resp = HttpResponse("")
    resp["HX-Trigger"] = json.dumps({"routepart:deleted": {"rp_id": pk}})
    return resp


@staff_member_required
@require_POST
def routeparts_reorder(request, route_id:int):
    """
    Body: {"order":[partId1, partId2, ...]}  in gewenste volgorde (top->bottom)
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        new_order = payload.get("order", [])
        if not isinstance(new_order, list):
            return HttpResponseBadRequest("order must be list")
    except Exception:
        return HttpResponseBadRequest("invalid json")

    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    parts = {p.id: p for p in route.routeparts.all()}
    i = 1
    for pid in new_order:
        p = parts.get(int(pid))
        if p:
            p.order = i
            p.save(update_fields=["order"])
            i += 1
    return JsonResponse({"ok": True})


# ---------- Bundles ----------
@staff_member_required
def bundle_form(request, route_id: int, pk: int = None):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    inst = get_object_or_404(Bundle, pk=pk, route=route) if pk else None

    if request.method == "POST":
        form = BundleForm(request.POST, instance=inst)
        if form.is_valid():
            obj = form.save(commit=False)
            if inst is None:
                obj.route = route
            obj.save()

            html = render_to_string(
                "backoffice/_bundle_item.html",
                {"bundle": obj, "route": route, "request": request},
            )
            resp = HttpResponse(html)
            resp["HX-Trigger"] = "bundle:saved"
            return resp

        html = render_to_string(
            "backoffice/_bundle_form.html",
            {"form": form, "route": route, "pk": pk, "request": request},
        )
        resp = HttpResponse(html)
        resp["HX-Retarget"] = "#sidepanel"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    form = BundleForm(instance=inst)
    html = render_to_string(
        "backoffice/_bundle_form.html",
        {"form": form, "route": route, "pk": pk, "request": request},
    )
    return HttpResponse(html)


@staff_member_required
@require_POST
def bundle_delete(request, route_id: int, pk: int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    inst = get_object_or_404(Bundle, pk=pk, route=route)
    inst.delete()  # RouteParts get bundle=NULL via SET_NULL
    resp = HttpResponse("")
    resp["HX-Trigger"] = "bundle:deleted"
    return resp


# ---------- Distribute (oude admin action, nu per route) ----------
@staff_member_required
@require_POST
def distribute_route_to_teams(request, route_id: int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    teams = list(route.edition.teams.all())

    trp_created = 0
    dest_created = 0

    with transaction.atomic():
        # Alle RouteParts van deze route
        for part in route.routeparts.select_related(
            "route", "routedata_image", "routedata_audio"
        ).all():

            for team in teams:
                # Maak (of vind) TeamRoutePart voor (routepart, team)
                trp, created = TeamRoutePart.objects.get_or_create(
                    routepart=part,      # ← belangrijk
                    team=team,           # ← instance, geen id
                    defaults={
                        "route": route,  # ← instance, geen id
                        "name": part.name,
                        "route_type": part.route_type,
                        "routepart_zoom": part.routepart_zoom,
                        "routepart_fullscreen": part.routepart_fullscreen,
                        "routedata_image": part.routedata_image,
                        "routedata_audio": part.routedata_audio,
                        "final": part.final,
                        "order": part.order,
                        "bundle": part.bundle,
                    },
                )
                if created:
                    trp_created += 1
                else:
                    # (optioneel) sync velden als part gewijzigd is
                    dirty = False
                    for field, value in {
                        "route": route,
                        "name": part.name,
                        "route_type": part.route_type,
                        "routepart_zoom": part.routepart_zoom,
                        "routepart_fullscreen": part.routepart_fullscreen,
                        "routedata_image": part.routedata_image,
                        "routedata_audio": part.routedata_audio,
                        "final": part.final,
                        "order": part.order,
                        "bundle": part.bundle,
                    }.items():
                        if getattr(trp, field) != value:
                            setattr(trp, field, value)
                            dirty = True
                    if dirty:
                        trp.save()

                # Clone destinations van RoutePart naar TeamRoutePart (idempotent)
                for d in part.destinations.all().order_by("id"):
                    _, d_created = Destination.objects.get_or_create(
                        teamroutepart=trp,                 # TRP-koppeling
                        lat=d.lat,
                        lng=d.lng,
                        radius=d.radius,
                        destination_type=d.destination_type,
                        confirm_by_user=d.confirm_by_user,
                        hide_for_user=d.hide_for_user,
                        defaults={
                            # completed_time, routepart niet overnemen
                        },
                    )
                    if d_created:
                        dest_created += 1

    target = reverse("backoffice:teamrouteparts_builder", args=[route.id])

    # HTMX → stuur redirect via header
    if request.headers.get("HX-Request") or request.headers.get("Hx-Request"):
        resp = HttpResponse(f"TRP: {trp_created}, DEST: {dest_created}")
        resp["HX-Redirect"] = target
        return resp

    # Gewone POST → normale redirect
    return redirect(target)


# ---------- TeamRouteParts builder (map + team-selectie) ----------
@staff_member_required
def teamrouteparts_builder(request, route_id:int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization").select_related("edition"), pk=route_id)

    teams = list(route.edition.teams.order_by("name"))
    selected = request.GET.getlist("team")  # ?team=1&team=2
    selected_ids = {int(t) for t in selected} if selected else {t.id for t in teams}

    # Alle TRP’s + destinations
    trps = (
        TeamRoutePart.objects
        .filter(route=route)
        .select_related("team", "routepart")
        .order_by("order", "id")
    )

    # Maak dest_items met ‘group key’: (base_rp_id, idx binnen base_rp)
    # idx bepalen per TRP volgt originele volgorde van de gekloonde RoutePart
    dest_items = []
    # eerst: alle TeamRoutePart -> zijn RoutePart id en order ophalen
    trp_meta = {}
    for trp in trps:
        trp_meta[trp.id] = {
            "team_id": trp.team_id,
            "team_name": trp.team.name,
            "base_rp_id": trp.routepart_id,
            "rp_order": trp.order,          # we tonen volgorde van TRP
            "rp_name": trp.name,
        }
        # enumerate destinations binnen TRP
        for idx, d in enumerate(trp.destinations.all().order_by("id"), start=1):
            # group key = base routepart + idx
            dest_items.append({
                "id": d.id,
                "lat": d.lat,
                "lng": d.lng,
                "radius": d.radius,
                "confirm_by_user": d.confirm_by_user,
                "hide_for_user": d.hide_for_user,
                "trp_id": trp.id,
                "team_id": trp.team_id,
                "team_name": trp.team.name,
                "base_rp_id": trp.routepart_id,
                "rp_order": trp.order,
                "rp_name": trp.name,
                "idx": idx,
                "group_key": f"{trp.routepart_id}:{idx}",
            })

    ctx = {
        "route": route,
        "teams": teams,
        "selected_ids": selected_ids,
        "dest_items": dest_items,
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    ctx.update(edition_ctx(route.edition, "distribution", active_route_id=route.id))
    return render(request, "backoffice/teamrouteparts.html", ctx)


@staff_member_required
def teamrouteparts_table(request, route_id: int):
    """Table view of all TeamRouteParts for a route, filterable by team."""
    route = get_object_or_404(
        org_qs(request.user, Route.objects, "edition__event__organization").select_related("edition"),
        pk=route_id,
    )
    teams = list(route.edition.teams.order_by("name"))
    selected = request.GET.getlist("team")
    selected_ids = {int(t) for t in selected} if selected else {t.id for t in teams}
    search = request.GET.get("q", "").strip()

    table_trps = (
        TeamRoutePart.objects
        .filter(route=route, team_id__in=selected_ids)
        .select_related("team", "routepart", "bundle")
        .annotate(
            dest_total=Count(
                "destinations",
                filter=Q(destinations__destination_type__in=[DESTINATION_TYPE_MANDATORY, DESTINATION_TYPE_CHOICE]),
            ),
            dest_completed=Count(
                "destinations",
                filter=Q(
                    destinations__destination_type__in=[DESTINATION_TYPE_MANDATORY, DESTINATION_TYPE_CHOICE],
                    destinations__completed_time__isnull=False,
                ),
            ),
        )
        .order_by("team__name", "order")
    )

    if search:
        table_trps = table_trps.filter(
            Q(name__icontains=search) | Q(team__name__icontains=search)
        )

    ctx = {
        "route": route,
        "teams": teams,
        "selected_ids": selected_ids,
        "search": search,
        "table_trps": table_trps,
    }
    ctx.update(edition_ctx(route.edition, "distribution", active_route_id=route.id))
    return render(request, "backoffice/teamrouteparts_table.html", ctx)


# ---------- Bulk APIs voor verplaatsen / updaten ----------
@staff_member_required
@require_POST
def team_dests_bulk_move(request):
    """
    JSON:
      { "ids": [destId1,...], "lat": <float>, "lng": <float> }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        ids = payload.get("ids") or []
        lat = float(str(payload.get("lat")).replace(",", "."))
        lng = float(str(payload.get("lng")).replace(",", "."))
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    qs = org_qs(request.user, Destination.objects, "teamroutepart__route__edition__event__organization").filter(id__in=ids, teamroutepart__isnull=False)
    updated = qs.update(lat=lat, lng=lng)
    return JsonResponse({"ok": True, "updated": updated, "lat": lat, "lng": lng})


@staff_member_required
@require_POST
def team_dests_bulk_update(request):
    """
    JSON:
      { "ids":[...], "radius": int?, "confirm_by_user": bool?, "hide_for_user": bool? }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        ids = payload.get("ids") or []
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    qs = org_qs(request.user, Destination.objects, "teamroutepart__route__edition__event__organization").filter(id__in=ids, teamroutepart__isnull=False)

    changed = {}
    if "radius" in payload:
        try:
            changed["radius"] = int(payload["radius"])
        except Exception:
            return HttpResponseBadRequest("Invalid radius")
    if "confirm_by_user" in payload:
        changed["confirm_by_user"] = bool(payload["confirm_by_user"])
    if "hide_for_user" in payload:
        changed["hide_for_user"] = bool(payload["hide_for_user"])

    if not changed:
        return HttpResponseBadRequest("Nothing to update")

    qs.update(**changed)
    return JsonResponse({"ok": True, "updated": qs.count(), **changed})


@staff_member_required
@require_POST
def team_dests_bulk_delete(request):
    """
    JSON: { "ids": [destId1, destId2, ...] }
    Verwijdert alléén destinations die aan een TeamRoutePart hangen.
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return HttpResponseBadRequest("ids required")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    qs = org_qs(request.user, Destination.objects, "teamroutepart__route__edition__event__organization").filter(id__in=ids, teamroutepart__isnull=False)
    existing_ids = list(qs.values_list("id", flat=True))
    deleted_count = qs.delete()[0]

    return JsonResponse({"ok": True, "deleted": existing_ids, "count": deleted_count})



@staff_member_required
@require_POST
def teamrouteparts_clear(request, route_id:int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    # Verwijder alle TeamRouteParts voor deze route (Destinations hangen aan TRP en verdwijnen mee)
    TeamRoutePart.objects.filter(route=route).delete()

    target = reverse("backoffice:teamrouteparts_builder", args=[route.id])

    # HTMX → redirect header, anders normale redirect
    if request.headers.get("HX-Request") or request.headers.get("Hx-Request"):
        resp = HttpResponse("OK")
        resp["HX-Redirect"] = target
        return resp
    return redirect(target)


@staff_member_required
def route_map(request, route_id: int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)

    teams_qs = (
        Team.objects
        .filter(teamrouteparts__routepart__route=route)
        .distinct()
        .order_by("id")
    )
    teams_json = list(teams_qs.values("id", "name"))  # alleen wat JS nodig heeft

    dest_qs = (
        Destination.objects
        .filter(routepart__route=route)
        .annotate(lat_r=Round('lat', 6), lng_r=Round('lng', 6))
        .values('lat_r', 'lng_r')
        .annotate(
            count=Count('id'),
            order=Min('routepart__order'),  # representatief label (laagste order)
        )
        .order_by('order')
    )

    destinations = [
        {
            'lat': float(d['lat_r']),
            'lng': float(d['lng_r']),
            'routepart__order': int(d['order']),
            'count': int(d['count']),
        }
        for d in dest_qs
    ]

    # completed minimal: geen teamnaam dupliceren
    completed_destinations = list(
        Destination.objects
        .filter(
            teamroutepart__team__in=teams_qs,
            teamroutepart__routepart__route=route,
            completed_time__isnull=False,
        )
        .values("lat", "lng", "teamroutepart__team_id", "completed_time")
        .order_by("-completed_time")
    )

    filter_date = route.date or timezone.localdate()
    team_locations = list(
        LocationLog.objects
        .filter(team__in=teams_qs, time__date=filter_date)
        .values("team__id", "lat", "lng", "time")
        .order_by("-time")
    )

    ctx = {
        "route": route,
        "filter_date": filter_date,
        "teams": teams_qs,
        "teams_json": teams_json,
        "destinations": destinations,
        "completed_destinations": completed_destinations,
        "team_locations": team_locations,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    ctx.update(edition_ctx(route.edition, "live_map", active_route_id=route.id))
    return render(request, "backoffice/route_map.html", ctx)

@staff_member_required
def route_map_state(request, route_id: int):
    # Minimal JSON voor live updates
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    teams_qs = Team.objects.filter(teamrouteparts__routepart__route=route).distinct()

    now = timezone.now()
    filter_date = route.date or timezone.localdate()

    team_positions = list(
        LocationLog.objects
        .filter(team__in=teams_qs, time__date=filter_date)
        .order_by('team_id','-time')
        .values('team__id','lat','lng','time')
    )

    completed = list(
        Destination.objects
        .filter(teamroutepart__team__in=teams_qs,
                teamroutepart__routepart__route=route,
                completed_time__isnull=False)
        .values('lat','lng','teamroutepart__team_id','completed_time')
    )

    return JsonResponse({
        "server_time": now.isoformat(),
        "teams": team_positions,
        "completed_destinations": completed,
    })



def calculate_walking_distance(destinations):
    
    # Initialize Google Maps client
    gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

    total_distance = 0.0

    # Split destinations into chunks of 10
    chunk_size = 10
    for i in range(0, len(destinations), chunk_size):
        chunk = destinations[i:i + chunk_size]

        # Create a list of waypoints, excluding the first and last points
        waypoints = chunk[1:-1]


        # Calculate the walking distance for the chunk
        if waypoints:
            directions_result = gmaps.directions(
                chunk[0],  # Starting point
                chunk[-1],  # Ending point
                mode="walking",  # Walking mode
                waypoints=waypoints,
            )
            #print(directions_result)

            # Extract distance from the result
            distance = directions_result[0]["legs"][0]["distance"]["value"]  # in meters
            total_distance += distance

    # Convert total distance to kilometers or miles, depending on your preference
    total_distance_km = total_distance / 1000.0
    return round(total_distance_km,2)


@staff_member_required
def route_stats_page(request, route_id: int):
    route = get_object_or_404(org_qs(request.user, Route.objects, "edition__event__organization"), pk=route_id)
    edition = route.edition

    # Mandatory destinations for this route (+ optioneel annotatie voor eerste choice)
    mandatory_qs = Destination.objects.filter(
        routepart__route=route,
        destination_type=DESTINATION_TYPE_MANDATORY
    )

    first_choice_subq = Destination.objects.filter(
        routepart__route=route,
        destination_type=DESTINATION_TYPE_CHOICE,
        routepart=OuterRef('routepart')
    ).order_by('id').values('id')[:1]

    mandatory_qs = mandatory_qs.annotate(first_choice_destination=Subquery(first_choice_subq))

    destinations_count = mandatory_qs.count()

    # Distance (km) op basis van mandatory dests
    coords = [(d.lat, d.lng) for d in mandatory_qs]
    distance = calculate_walking_distance(coords) if coords else 0

    # Teams die aan deze route hangen
    teams = Team.objects.filter(teamrouteparts__route=route).distinct()

    # Per team: first/last completed (alleen tijd), totale duur, totaal aantal completed destinations
    team_stats = (
        teams
        .annotate(
            first_completed=TruncTime(Min('teamrouteparts__completed_time')),
            last_completed=TruncTime(Max('teamrouteparts__completed_time')),
        )
        .annotate(
            time_difference=ExpressionWrapper(
                F('last_completed') - F('first_completed'),
                output_field=fields.DurationField(),
            ),
        )
        .annotate(
            completed_destinations_count=Count(
                'teamrouteparts__destinations',
                filter=Q(teamrouteparts__destinations__completed_time__isnull=False)
            ),
        )
        .order_by('name')
    )

    ctx = {
        'route': route,
        'edition': edition,
        'destinations_count': destinations_count,
        'distance': distance,
        'team_stats': team_stats,
    }
    ctx.update(edition_ctx(edition, "routes", active_route_id=route.id))
    return render(request, 'backoffice/route_stats.html', ctx)


@staff_member_required
def edition_registration(request, edition_id: int):
    """Edit registration settings for an edition."""
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    if request.method == "POST":
        form = EditionRegistrationForm(request.POST, instance=edition)
        if form.is_valid():
            form.save()
            return redirect("backoffice:edition_dashboard", edition_id=edition.id)
    else:
        form = EditionRegistrationForm(instance=edition)
    ctx = {"edition": edition, "form": form}
    ctx.update(edition_ctx(edition, "settings"))
    return render(request, "backoffice/edition_registration.html", ctx)


@staff_member_required
@require_POST
def team_activate(request, edition_id: int, pk: int):
    """Activate a team: generate code, distribute routes, send email."""
    from server.views import _unique_team_code, _distribute_routes_for_team, _send_team_code_email

    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    team = get_object_or_404(Team, pk=pk, edition=edition)

    if not team.is_activated:
        with transaction.atomic():
            team.code = _unique_team_code(edition)
            team.is_activated = True
            team.save()
            _distribute_routes_for_team(team)
        _send_team_code_email(team)

    return redirect("backoffice:team_list", edition_id=edition_id)


# ─── Messages ──────────────────────────────────────────────────────


class MessageForm(forms.Form):
    """Form for sending a message from the backoffice."""
    recipient_team = forms.ModelChoiceField(
        queryset=Team.objects.none(),
        required=False,
        empty_label="Alle teams (broadcast)",
        widget=forms.Select(attrs={"class": "w-full rounded-lg border px-3 py-2"}),
        label="Ontvanger",
    )
    text = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "w-full rounded-lg border px-3 py-2",
            "rows": 3,
            "placeholder": "Typ een bericht…",
        }),
        label="Bericht",
    )

    def __init__(self, *args, edition=None, **kwargs):
        super().__init__(*args, **kwargs)
        if edition:
            self.fields["recipient_team"].queryset = edition.teams.all().order_by("name")


@staff_member_required
def messages_page(request, edition_id: int, team_id: int = None):
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    if not edition.messaging_enabled:
        return redirect("backoffice:team_list", edition_id=edition.id)
    teams = edition.teams.all().order_by("name")

    # Selected team thread (None = broadcast / all)
    selected_team = None
    if team_id:
        selected_team = get_object_or_404(Team, pk=team_id, edition=edition)

    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        image = request.FILES.get("image")
        if text or image:
            msg = Message.objects.create(
                edition=edition,
                sender_team=None,  # from organisation
                recipient_team=selected_team,
                text=text,
                image=image,
            )

            # Push to connected teams and backoffice clients
            msg_payload = {"type": "message", "data": msg.to_app_format()}
            if selected_team:
                push_to_team(selected_team.id, msg_payload)
            else:
                push_to_edition(edition.id, msg_payload)
            push_to_backoffice(edition.id, msg_payload)

        # Redirect back to the same thread
        if selected_team:
            return redirect("backoffice:messages_team", edition_id=edition.id, team_id=selected_team.id)
        return redirect("backoffice:messages", edition_id=edition.id)

    # Build thread messages
    if selected_team:
        # Show conversation between organisation and this specific team
        thread_messages = Message.objects.filter(
            edition=edition,
        ).filter(
            Q(sender_team=selected_team)  # team → org
            | Q(sender_team__isnull=True, recipient_team=selected_team)  # org → team
            | Q(sender_team__isnull=True, recipient_team__isnull=True)  # broadcast
        ).select_related("sender_team", "recipient_team").order_by("created_at")
    else:
        # Show all broadcasts
        thread_messages = Message.objects.filter(
            edition=edition,
            sender_team__isnull=True,
            recipient_team__isnull=True,
        ).order_by("created_at")

    # Annotate unread count per team
    unread_counts = dict(
        Message.objects.filter(
            edition=edition,
            sender_team__isnull=False,
            read_at__isnull=True,
        ).values_list("sender_team").annotate(count=Count("id")).values_list("sender_team", "count")
    )
    teams_with_unread = []
    for t in teams:
        t.unread_count = unread_counts.get(t.id, 0)
        teams_with_unread.append(t)

    # Ensure selected_team also has the unread_count
    if selected_team:
        selected_team.unread_count = unread_counts.get(selected_team.id, 0)

    ctx = {
        "edition": edition,
        "teams": teams_with_unread,
        "selected_team": selected_team,
        "thread_messages": thread_messages,
    }
    ctx.update(edition_ctx(edition, "messages"))
    return render(request, "backoffice/messages.html", ctx)


@staff_member_required
@require_POST
def messages_mark_read(request, edition_id: int, team_id: int):
    """AJAX: mark all unread messages from a team as read."""
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)
    team = get_object_or_404(Team, pk=team_id, edition=edition)
    updated = Message.objects.filter(
        edition=edition, sender_team=team, read_at__isnull=True
    ).update(read_at=timezone.now())
    return JsonResponse({"marked": updated})


@staff_member_required
@require_POST
def messages_clear(request, edition_id: int, team_id: int = None):
    """Delete all messages in a thread."""
    edition = get_object_or_404(org_qs(request.user, Edition.objects, "event__organization"), pk=edition_id)

    if team_id:
        team = get_object_or_404(Team, pk=team_id, edition=edition)
        # Delete conversation between org and this team
        Message.objects.filter(
            edition=edition,
        ).filter(
            Q(sender_team=team)
            | Q(sender_team__isnull=True, recipient_team=team)
        ).delete()
        return redirect("backoffice:messages_team", edition_id=edition.id, team_id=team.id)
    else:
        # Delete all broadcasts
        Message.objects.filter(
            edition=edition,
            sender_team__isnull=True,
            recipient_team__isnull=True,
        ).delete()
        return redirect("backoffice:messages", edition_id=edition.id)


# ─── User Management (superadmin only) ──────────────────────────


@superuser_required
def user_list(request):
    users = (
        User.objects
        .select_related("profile__organization")
        .order_by("username")
    )
    return render(request, "backoffice/user_list.html", {"users": users, "nav_active": "users"})


@superuser_required
def user_add(request):
    if request.method == "POST":
        form = UserManagementForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password"],
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                email=form.cleaned_data.get("email", ""),
                is_staff=True,
                is_active=form.cleaned_data.get("is_active", True),
            )
            org = form.cleaned_data.get("organization")
            UserProfile.objects.create(user=user, organization=org)
            if not org:
                user.is_superuser = True
                user.save(update_fields=["is_superuser"])
            return redirect("backoffice:user_list")
    else:
        form = UserManagementForm()
    return render(request, "backoffice/user_form.html", {"form": form, "mode": "add", "nav_active": "users"})


@superuser_required
def user_edit(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    profile, _ = UserProfile.objects.get_or_create(user=target)

    if request.method == "POST":
        form = UserManagementForm(request.POST, editing_user=target)
        if form.is_valid():
            target.username = form.cleaned_data["username"]
            target.first_name = form.cleaned_data.get("first_name", "")
            target.last_name = form.cleaned_data.get("last_name", "")
            target.email = form.cleaned_data.get("email", "")
            target.is_active = form.cleaned_data.get("is_active", True)
            if form.cleaned_data.get("password"):
                target.set_password(form.cleaned_data["password"])
            org = form.cleaned_data.get("organization")
            target.is_superuser = not org
            target.save()
            profile.organization = org
            profile.save(update_fields=["organization"])
            return redirect("backoffice:user_list")
    else:
        form = UserManagementForm(
            initial={
                "username": target.username,
                "first_name": target.first_name,
                "last_name": target.last_name,
                "email": target.email,
                "organization": profile.organization,
                "is_active": target.is_active,
            },
            editing_user=target,
        )
    return render(request, "backoffice/user_form.html", {"form": form, "mode": "edit", "target_user": target, "nav_active": "users"})


@superuser_required
@require_POST
def user_deactivate(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        return HttpResponseBadRequest("Je kunt jezelf niet deactiveren.")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    return redirect("backoffice:user_list")


@superuser_required
@require_POST
def user_reset_password(request, pk: int):
    target = get_object_or_404(User, pk=pk)
    new_password = request.POST.get("new_password", "").strip()
    if new_password:
        target.set_password(new_password)
        target.save()
    return redirect("backoffice:user_list")