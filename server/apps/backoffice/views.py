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
from .forms import RouteForm, RoutePartForm, DestinationForm
from server.apps.dashboard.models import (
    Event, Edition, Route, RoutePart, TeamRoutePart, Destination, Team, File, LocationLog, DESTINATION_TYPE_MANDATORY, DESTINATION_TYPE_CHOICE
)

@staff_member_required
def events_list(request):
    events = (
        Event.objects
        .annotate(
            editions_count=Count("editions", distinct=True),
            routes_count=Count("editions__routes", distinct=True),
            routeparts_count=Count("editions__routes__routeparts", distinct=True),
            teams_count=Count("editions__teams", distinct=True),
        )
        .order_by("name")
    )
    return render(request, "backoffice/events_list.html", {"events": events})


@staff_member_required
def edition_list(request, event_id: int | None = None):
    qs = (
        Edition.objects
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
        event = Event.objects.filter(pk=event_id).first()

    editions = qs.order_by(
        F("date_start").desc(nulls_last=True),
        F("date_end").desc(nulls_last=True),
        "-id",
    )
    return render(request, "backoffice/edition_list.html", {"editions": editions, "event": event})



@staff_member_required
def edition_routes_stats(request, edition_id: int):
    routes = (
        Route.objects.filter(edition_id=edition_id)
        .annotate(parts_count=Count("routeparts"))
        .order_by("name")
    )
    return render(request, "backoffice/_edition_routes_stats.html", {"routes": routes})


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        exclude = ["edition"]  # laat alle overige velden toe, edition zetten we in de view
        widgets = {
            # optioneel wat nette widgets
            "name": forms.TextInput(attrs={"class": "w-full rounded-lg border px-3 py-2"}),
            "notes": forms.Textarea(attrs={"class": "w-full rounded-lg border px-3 py-2", "rows": 3}),
        }

@staff_member_required
def team_list(request, edition_id: int):
    edition = get_object_or_404(Edition, pk=edition_id)
    teams = edition.teams.all().order_by("name")
    return render(request, "backoffice/team_list.html", {"edition": edition, "teams": teams})

@staff_member_required
def team_add(request, edition_id: int):
    edition = get_object_or_404(Edition, pk=edition_id)
    if request.method == "POST":
        form = TeamForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.edition = edition
            obj.save()
            return redirect("backoffice:team_list", edition_id=edition.id)
    else:
        form = TeamForm()
    return render(request, "backoffice/team_form.html", {"edition": edition, "form": form, "mode": "add"})

@staff_member_required
def team_edit(request, edition_id: int, pk: int):
    edition = get_object_or_404(Edition, pk=edition_id)
    team = get_object_or_404(Team, pk=pk, edition=edition)
    if request.method == "POST":
        form = TeamForm(request.POST, instance=team)
        if form.is_valid():
            form.save()
            return redirect("backoffice:team_list", edition_id=edition.id)
    else:
        form = TeamForm(instance=team)
    return render(request, "backoffice/team_form.html", {"edition": edition, "form": form, "mode": "edit", "team": team})

@staff_member_required
@require_POST
def team_delete(request, edition_id: int, pk: int):
    edition = get_object_or_404(Edition, pk=edition_id)
    team = get_object_or_404(Team, pk=pk, edition=edition)
    team.delete()
    return redirect("backoffice:team_list", edition_id=edition.id)


@staff_member_required
def destinations_editor(request, rp_id:int):
    rp = get_object_or_404(RoutePart, pk=rp_id)
    dests = rp.destinations.all().order_by("id")

    dest_items = list(dests.values(
        "id", "lat", "lng", "destination_type", "radius",
        "confirm_by_user", "hide_for_user"
    ))

    ctx = {
        "rp": rp,
        "destinations": dests,
        "dest_items": dest_items,  # ← hieraan toegevoegd
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    return render(request, "backoffice/destinations.html", ctx)



@staff_member_required
def destination_form(request, rp_id:int, pk:int=None):
    rp = get_object_or_404(RoutePart, pk=rp_id)
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
    rp = get_object_or_404(RoutePart, pk=rp_id)
    inst = get_object_or_404(Destination, pk=pk, routepart=rp)
    inst.delete()
    return HttpResponse("OK")


@staff_member_required
@require_POST
def destination_move(request, rp_id: int, pk: int):
    rp = get_object_or_404(RoutePart, pk=rp_id)
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
    rp = get_object_or_404(RoutePart, pk=rp_id)
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

# -------- Routes --------
@staff_member_required
def routes_page(request):
    editions = Edition.objects.order_by('name')
    routes = _filtered_routes(request)
    selected_edition = None
    ed_id = request.GET.get('edition')
    if ed_id:
        selected_edition = (
            Edition.objects.select_related("event").filter(pk=ed_id).first()
        )
    return render(request, "backoffice/routes.html", {
        "editions": editions,
        "routes": routes,
        "selected_edition": selected_edition,
    })

def _filtered_routes(request):
    qs = Route.objects.select_related('edition') \
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
    instance = get_object_or_404(Route, pk=pk) if pk else None

    if request.method == "GET":
        form = RouteForm(instance=instance)
        return render(request, "backoffice/_route_form.html", {"form": form})

    # POST
    form = RouteForm(request.POST, instance=instance)
    if form.is_valid():
        obj = form.save()
        # Render dezelfde partial met flag zodat client een event kan dispatchen
        return render(request, "backoffice/_route_form.html", {"form": RouteForm(instance=obj), "saved_ok": True})
    else:
        # Invalid — render terug in sidepanel
        return render(request, "backoffice/_route_form.html", {"form": form})

@staff_member_required
@require_http_methods(["DELETE"])
def route_delete(request, pk):
    obj = get_object_or_404(Route, pk=pk)
    obj.delete()
    # Row wordt vervangen door niets dankzij hx-swap="outerHTML"
    return HttpResponse(status=204)

# -------- RouteParts builder --------
@staff_member_required
def routeparts_builder(request, route_id:int):
    route = get_object_or_404(Route.objects.select_related("edition"), pk=route_id)
    parts = list(
    route.routeparts
         .select_related("routedata_image","routedata_audio")
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

    ctx = {
        "route": route,
        "parts": parts,
        "dest_items": dest_items,
        "GOOGLE_MAPS_API_KEY": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    return render(request, "backoffice/routeparts.html", ctx)



@staff_member_required
def routepart_form(request, route_id:int, pk:int=None):
    route = get_object_or_404(Route, pk=route_id)
    inst = get_object_or_404(RoutePart, pk=pk, route=route) if pk else None

    if request.method == "POST":
        form = RoutePartForm(request.POST, instance=inst)

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
    form = RoutePartForm(instance=inst)
    html = render_to_string(
        "backoffice/_routepart_form.html",
        {"form": form, "route": route, "pk": pk, "request": request},
    )
    return HttpResponse(html)


@staff_member_required
@require_POST
def routepart_delete(request, route_id:int, pk:int):
    route = get_object_or_404(Route, pk=route_id)
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

    route = get_object_or_404(Route, pk=route_id)
    parts = {p.id: p for p in route.routeparts.all()}
    i = 1
    for pid in new_order:
        p = parts.get(int(pid))
        if p:
            p.order = i
            p.save(update_fields=["order"])
            i += 1
    return JsonResponse({"ok": True})


# ---------- Distribute (oude admin action, nu per route) ----------
@staff_member_required
@require_POST
def distribute_route_to_teams(request, route_id: int):
    route = get_object_or_404(Route, pk=route_id)
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
    route = get_object_or_404(Route.objects.select_related("edition"), pk=route_id)

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
    return render(request, "backoffice/teamrouteparts.html", ctx)


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

    qs = Destination.objects.filter(id__in=ids, teamroutepart__isnull=False)
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

    qs = Destination.objects.filter(id__in=ids, teamroutepart__isnull=False)

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

    qs = Destination.objects.filter(id__in=ids, teamroutepart__isnull=False)
    existing_ids = list(qs.values_list("id", flat=True))
    deleted_count = qs.delete()[0]

    return JsonResponse({"ok": True, "deleted": existing_ids, "count": deleted_count})



@staff_member_required
@require_POST
def teamrouteparts_clear(request, route_id:int):
    route = get_object_or_404(Route, pk=route_id)
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
    route = get_object_or_404(Route, pk=route_id)

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

    current_date = timezone.now().date()
    team_locations = list(
        LocationLog.objects
        .filter(team__in=teams_qs, time__date=current_date)
        .values("team__id", "lat", "lng", "time")
        .order_by("-time")
    )

    ctx = {
        "route": route,
        "teams": teams_qs,                     # voor de filterlijst render
        "teams_json": teams_json,              # voor JS-kleur/label
        "destinations": destinations,
        "completed_destinations": completed_destinations,
        "team_locations": team_locations,
        "GOOGLE_MAPS_API_KEY": settings.GOOGLE_MAPS_API_KEY,
        "GOOGLE_MAPS_MAP_ID": getattr(settings, "GOOGLE_MAPS_MAP_ID", ""),
    }
    return render(request, "backoffice/route_map.html", ctx)

@staff_member_required
def route_map_state(request, route_id: int):
    # Minimal JSON voor live updates
    route = get_object_or_404(Route, pk=route_id)
    teams_qs = Team.objects.filter(teamrouteparts__routepart__route=route).distinct()

    now = timezone.now()
    today = timezone.localdate()

    team_positions = list(
        LocationLog.objects
        .filter(team__in=teams_qs, time__date=today)
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
    route = get_object_or_404(Route, pk=route_id)
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
    return render(request, 'backoffice/route_stats.html', ctx)