from django.urls import path
from . import views

app_name = "backoffice"

urlpatterns = [
    #path("", views.dashboard, name="dashboard"),

    # Events → lijst
    path("events/", views.events_list, name="events_list"),

    # Editions gefilterd op een Event
    path("events/<int:event_id>/editions/", views.edition_list, name="edition_list_for_event"),

    #Editions
    path("editions/", views.edition_list, name="edition_list"),
    path("editions/<int:edition_id>/routes-stats/", views.edition_routes_stats, name="edition_routes_stats"),

    # Teams per edition
    path("editions/<int:edition_id>/teams/", views.team_list, name="team_list"),
    path("editions/<int:edition_id>/teams/add/", views.team_add, name="team_add"),
    path("editions/<int:edition_id>/teams/<int:pk>/edit/", views.team_edit, name="team_edit"),
    path("editions/<int:edition_id>/teams/<int:pk>/delete/", views.team_delete, name="team_delete"),

    # Routes
    path("routes/", views.routes_page, name="routes_page"),
    path("routes/list", views.routes_list, name="routes_list"),
    path("routes/new", views.route_form, name="route_new"),
    path("routes/<int:pk>/edit", views.route_form, name="route_edit"),
    path("routes/<int:pk>/delete", views.route_delete, name="route_delete"),

    path('routes/<int:route_id>/live_map', views.route_map, name='route_map'),
    path('routes/<int:route_id>/live_map/state/', views.route_map_state, name='route_map_state'),

    path("routes/<int:route_id>/stats", views.route_stats_page, name="route_stats"),

    # RouteParts builder
    path("routes/<int:route_id>/parts/", views.routeparts_builder, name="routeparts_builder"),
    path("routes/<int:route_id>/parts/new", views.routepart_form, name="routepart_new"),
    path("routes/<int:route_id>/parts/<int:pk>", views.routepart_form, name="routepart_edit"),
    path("routes/<int:route_id>/parts/<int:pk>/delete", views.routepart_delete, name="routepart_delete"),
    path("routes/<int:route_id>/parts/reorder", views.routeparts_reorder, name="routeparts_reorder"),

    path("routeparts/<int:rp_id>/destinations/", views.destinations_editor, name="destinations_editor"),
    path("routeparts/<int:rp_id>/destinations/new", views.destination_form, name="destination_new"),
    path("routeparts/<int:rp_id>/destinations/<int:pk>", views.destination_form, name="destination_edit"),
    path("routeparts/<int:rp_id>/destinations/<int:pk>/delete", views.destination_delete, name="destination_delete"),
    path("routeparts/<int:rp_id>/destinations/<int:pk>/move",views.destination_move, name="destination_move"),
    path("routeparts/<int:rp_id>/destinations/<int:pk>/update", views.destination_update, name="destination_update"),


    path("routes/<int:route_id>/teams/", views.teamrouteparts_builder, name="teamrouteparts_builder"), 
    path("routes/<int:route_id>/distribute", views.distribute_route_to_teams, name="route_distribute"),
    path("teamrouteparts/destinations/bulk_move", views.team_dests_bulk_move, name="team_dests_bulk_move"),
    path("teamrouteparts/destinations/bulk_update", views.team_dests_bulk_update, name="team_dests_bulk_update"),    
    path("teamrouteparts/destinations/bulk_delete", views.team_dests_bulk_delete, name="team_dests_bulk_delete"),
    path("routes/<int:route_id>/teams/clear", views.teamrouteparts_clear, name="teamrouteparts_clear"),
]