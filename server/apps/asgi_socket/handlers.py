from django.contrib.auth import authenticate

from server.apps.dashboard.models import Team

from .constants import TYPE_AUTHENTICATION
from .handler_functions import FUNCTION_MAPPING


class SocketDataHandler:
    consumer = None
    team = None
    is_authenticated = False

    def __init__(self, consumer) -> None:
        self.consumer = consumer

    def authenticate(self, endpoint, data):
        # if its not an auth request: ignore
        if not endpoint == TYPE_AUTHENTICATION:
            return None

        # if there is not auth_str: ignore
        if not (auth_str := data["authStr"]):
            return None

        # try to get an Team by auth_str
        try:
            self.team = Team.objects.get(code=auth_str)
        except Team.DoesNotExist:
            return None

        # when there is an team set everything right
        self.team.go_online()
        self.is_authenticated = True
        return self.team

    def handle_request(self, endpoint, data=None):
        FUNCTION_MAPPING[endpoint](self, data)

    def close(self):
        self.team.go_offline()


"""
data = {
            "type": "route",
            "data": {
                "type": "coordinate",
                "data": {
                    "fullscreen": False,
                    "zoomEnabled": True,
                    "image": "https://www.basmeelker.nl/wp-content/uploads/winterlandschap-ijs-op-het-ijsselmeer.jpg",
                    "audio": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
                    "coordinates": [
                        {
                            "id": 10,
                            "latitude": 52.258779,
                            "longitude": 5.970222,
                            "type": "bonus",
                            "radius": 15,
                            "confirmByUser": True,
                        },
                        {
                            "id": 11,
                            "latitude": 52.258779,
                            "longitude": 5.670222,
                            "type": "mandatory",
                            "radius": 15,
                            "confirmByUser": True
                        }
                    ]
                }
            }
        }
"""
