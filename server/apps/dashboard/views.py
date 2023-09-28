# views.py
import googlemaps
from django.core.serializers.json import DjangoJSONEncoder

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from .models import Destination, Team, TeamRoutePart, LocationLog, Route
from django.db.models import OuterRef, Subquery, Case, When, Value, CharField

from django.db.models import Count, Max, Min, F, Q, ExpressionWrapper, fields
from django.db.models.functions import Now, TruncTime
from django.conf import settings
from .constants import (
    DESTINATION_TYPE_MANDATORY,
)

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

# def calculate_distance_between_destinations(destination1, destination2):
#     # Initialize Google Maps client
#     gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)

#     # Define destination coordinates
#     origin = (destination1.lat, destination1.lng)
#     destination = (destination2.lat, destination2.lng)

#     # Calculate distance between two coordinates using Directions API
#     directions_result = gmaps.directions(
#         origin,
#         destination,
#         mode="walking",  # You can specify other travel modes like "walking" or "bicycling"
#     )

#     # Extract distance from the result
#     distance = directions_result[0]["legs"][0]["distance"]["text"]

#     return distance

# def calculate_total_distance(distances):
#     total_distance = 0.0
#     for distance in distances.values():
#         # Parse the distance text (e.g., "5.2 mi" or "2.3 km") to extract the numeric value
#         numeric_distance = float(distance.split()[0])
#         total_distance += numeric_distance
#     return total_distance

@staff_member_required
def stats_view(request, route_id):
    # Fetch the route
    route = Route.objects.get(pk=route_id)

    # Fetch the edition related to the route
    edition = route.edition

    # Calculate the number of destinations of type mandatory for the chosen route
    mandatory_destinations = Destination.objects.filter(
        routepart__route=route,
        destination_type=DESTINATION_TYPE_MANDATORY
    )
    mandatory_destinations_count = mandatory_destinations.count()

    # Calculate distance between mandatory destinations
    my_dests = [(dest.lat, dest.lng) for dest in mandatory_destinations]    
    distance = calculate_walking_distance(my_dests)


    # Fetch all teams associated with the route
    teams = Team.objects.filter(teamrouteparts__route=route).distinct()

    # Calculate the first completed teamroutepart and last completed teamroutepart for each team
    team_stats = teams.annotate(
        first_completed=TruncTime(Min('teamrouteparts__completed_time')),
        last_completed=TruncTime(Max('teamrouteparts__completed_time')),
    )

    # Calculate the time difference in hours
    team_stats = team_stats.annotate(
        time_difference=ExpressionWrapper(
            F('last_completed') - F('first_completed'),
            output_field=fields.DurationField(),
        ),
    )

    # Calculate the number of completed destinations for each teamroutepart
    team_stats = team_stats.annotate(
        completed_destinations_count=Count(
            'teamrouteparts__destinations',
            filter=Q(teamrouteparts__destinations__completed_time__isnull=False),
        ),
    )

    context = {
        'route': route,
        'edition': edition,
        'mandatory_destinations_count': mandatory_destinations_count,
        'distance': distance,
        'team_stats': team_stats,
        'selected_route_id': route_id,
    }

    return render(request, 'stats.html', context)





@staff_member_required
def map_view(request, route_id=None):
    destinations = Destination.objects.none()
    teams = Team.objects.none()
    
    if route_id is not None:
        destinations = Destination.objects.filter(routepart__route__id=route_id).values('id', 'lat', 'lng', 'radius', 'destination_type', 'confirm_by_user', 'hide_for_user', 'routepart__name', 'routepart__order').order_by('routepart__order')
        teams = Team.objects.filter(teamrouteparts__routepart__route__id=route_id).distinct()
    
    # Retrieve team locations
    team_locations = LocationLog.objects.filter(
        team__in=teams
    ).values('team__name', 'team__id', 'lat', 'lng', 'time')

    # Fetch the list of routes
    routes = Route.objects.all()

    # Create a dictionary to map team IDs to marker icons based on a unique attribute
    team_marker_icons = {}
    for index, team in enumerate(teams, start=1):
        team_marker_icons[team.id] = get_marker_icon(index)

    # Subquery to retrieve the last completed destination for each team
    last_completed_destinations = Destination.objects.filter(
        teamroutepart__team=OuterRef('team_id'),
        completed_time__isnull=False
    ).order_by('-completed_time').values('lat', 'lng', 'teamroutepart__team_id', 'completed_time')[:1]

    # Annotate team_locations with latitude, longitude, and completed time of the last completed destination
    team_locations = team_locations.annotate(
        last_completed_lat=Subquery(last_completed_destinations.values('lat')),
        last_completed_lng=Subquery(last_completed_destinations.values('lng')),
        last_completed_time=Subquery(last_completed_destinations.values('completed_time'))
    )

    last_completed_destinations = {}
    for location in team_locations:
        team_id = location['team__id']
        last_completed_destinations[team_id] = {
            'team_id': team_id,
            'lat': location['last_completed_lat'],
            'lng': location['last_completed_lng'],
            'time': location['last_completed_time'],
        }
    
    google_maps_api_key = settings.GOOGLE_MAPS_API_KEY

    
    
    
    context = {
        'google_maps_api_key': google_maps_api_key,
        'destinations': destinations,
        'teams': teams,
        'team_locations': team_locations,
        'last_completed_destinations': last_completed_destinations,
        'team_marker_icons': team_marker_icons,
        'selected_route_id': route_id,
        'funnel_toggle': True
    }
    
    
    return render(request, 'map.html', context)



def get_marker_icon(team_property):
    # Define a mapping of team property values to marker icon URLs
    marker_icon_mappings = {
        1: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=A|00008B|FFFFFF',
        2: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=B|FF00FF|000000',
        3: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=C|FFFF00|000000',
        4: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=D|0000FF|FFFFFF',
        5: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=E|008000|FFFFFF',
        6: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=F|FF0000|FFFFFF',
        7: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=G|FFA500|FFFFFF',
        8: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=H|800080|FFFFFF',
        9: 'http://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=I|FFFF00|000000'
    }


    # Use the team property value to look up the marker icon URL
    # If a match is found, return the corresponding marker icon URL; otherwise, use a default.
    return marker_icon_mappings.get(team_property, 'http://maps.google.com/mapfiles/ms/icons/grey-dot.png')