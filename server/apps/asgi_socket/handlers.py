from django.contrib.auth import authenticate

from server.apps.dashboard.models import Team

from .constants import TYPE_AUTHENTICATION


class SocketDataHandler:
    consumer = None
    team = None
    is_authenticated = False

    def __init__(self, consumer) -> None:
        self.consumer = consumer

    def authenticate(self, request_type, data):
        # if its not an auth request: ignore
        if not request_type == TYPE_AUTHENTICATION:
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

    def handle_request(self, request_type, data):
        print(request_type)

    def close(self):
        self.team.go_offline()
