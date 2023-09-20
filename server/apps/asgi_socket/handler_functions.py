from server.apps.dashboard.models import Team

def send_new_location(handler, data=None):
    handler.consumer.send_dict_json(
        {"type": "route", "data": handler.team.get_next_open_routepart_formatted()}
    )


def receive_destination_confirmed(handler, data=None):
    destination_id = data["id"]
    handler.team.handle_destination_completion(destination_id)


def log_location(handler, data=None):
    handler.team.location_logs.create(
        lat=data["lat"],
        lng=data["lng"],
    )


def undo_completion(handler, data=None):
    if handler.team.check_undoable_completion():
        handler.team.undo_last_completion()

def authenticate(handler, data=None):
    # if there is a authstring, try to authenticate
    if (auth_str := data["authStr"]):
        try:
            handler.team = Team.objects.get(code=auth_str)
        except Team.DoesNotExist:
            handler.send_dict_json({"type": "auth", "data": {"result": 0}})
            return handler.consumer.close(4003)

        # when there is an team set everything right
        handler.team.go_online()
        handler.is_authenticated = True
        handler.send_dict_json({"type": "auth", "data": {"result": 1}})
    elif handler.is_authenticated:
        handler.is_authenticated = False
        return handler.consumer.close(4001)

FUNCTION_MAPPING = {
    "updateLocation": log_location,
    "newLocation": send_new_location,
    "destinationConfirmed": receive_destination_confirmed,
    "undoCompletion": undo_completion,
    "authenticate": authenticate,
}
