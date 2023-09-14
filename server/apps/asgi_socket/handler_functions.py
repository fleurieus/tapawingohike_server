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


FUNCTION_MAPPING = {
    "updateLocation": log_location,
    "newLocation": send_new_location,
    "destinationConfirmed": receive_destination_confirmed,
    "undoCompletion": undo_completion,
}
