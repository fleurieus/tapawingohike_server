from server.apps.dashboard.models import Message


def send_new_location(handler, data=None):
    return {"type": "route", "data": handler.team.get_next_open_routepart_formatted()}


def receive_destination_confirmed(handler, data=None):
    destination_id = data["id"]
    handler.team.handle_destination_completion(destination_id)
    return None


def log_location(handler, data=None):
    handler.team.location_logs.create(
        lat=data["lat"],
        lng=data["lng"],
    )
    return None


def undo_completion(handler, data=None):
    if handler.team.check_undoable_completion():
        handler.team.undo_last_completion()
    return None


def send_message(handler, data=None):
    """Team sends a message to the organisation."""
    if not handler.team.edition.messaging_enabled:
        return None
    msg = Message.objects.create(
        edition=handler.team.edition,
        sender_team=handler.team,
        recipient_team=None,  # to organisation
        text=data["text"],
    )
    return {"type": "message", "data": msg.to_app_format()}


def get_messages(handler, data=None):
    """Return message history for this team."""
    team = handler.team
    if not team.edition.messaging_enabled:
        return {"type": "messageHistory", "data": []}
    messages = Message.objects.filter(
        edition=team.edition,
    ).filter(
        # Broadcasts (recipient=None, sender=None) OR sent to this team OR sent by this team
        models_q_broadcast_or_team(team)
    ).order_by("created_at")[:50]

    return {
        "type": "messageHistory",
        "data": [m.to_app_format() for m in messages],
    }


def models_q_broadcast_or_team(team):
    """Q filter: messages visible to this team."""
    from django.db.models import Q
    return (
        Q(sender_team__isnull=True, recipient_team__isnull=True)  # broadcast
        | Q(sender_team__isnull=True, recipient_team=team)  # org → this team
        | Q(sender_team=team)  # this team → org
    )


FUNCTION_MAPPING = {
    "updateLocation": log_location,
    "newLocation": send_new_location,
    "destinationConfirmed": receive_destination_confirmed,
    "undoCompletion": undo_completion,
    "sendMessage": send_message,
    "getMessages": get_messages,
}
