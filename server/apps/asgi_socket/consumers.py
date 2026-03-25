import json
import asyncio
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .handlers import SocketDataHandler

logger = logging.getLogger(__name__)

# ── Global registry for pushing messages from sync code (backoffice views) ──
_connected_consumers: dict[int, "AppConsumer"] = {}
_backoffice_consumers: dict[int, set["BackofficeConsumer"]] = {}  # edition_id → set of consumers
_event_loop: asyncio.AbstractEventLoop | None = None


def _ensure_loop():
    global _event_loop
    if _event_loop is None:
        return False
    return True


def push_to_team(team_id: int, payload: dict):
    """Send a message to a connected team from sync code (e.g. a Django view)."""
    if not _ensure_loop():
        return
    consumer = _connected_consumers.get(team_id)
    if consumer is not None:
        asyncio.run_coroutine_threadsafe(
            consumer.send_dict_json(payload), _event_loop
        )


def push_to_edition(edition_id: int, payload: dict):
    """Broadcast a message to all connected teams of an edition."""
    for consumer in list(_connected_consumers.values()):
        if consumer._edition_id == edition_id:
            push_to_team(consumer._team_id, payload)


def push_to_backoffice(edition_id: int, payload: dict):
    """Push a message to all connected backoffice clients for an edition."""
    if not _ensure_loop():
        return
    consumers = _backoffice_consumers.get(edition_id, set())
    for consumer in list(consumers):
        asyncio.run_coroutine_threadsafe(
            consumer.send_dict_json(payload), _event_loop
        )


# ─── App Consumer (teams) ───────────────────────────────────────────

class AppConsumer(AsyncWebsocketConsumer):
    handler = None
    _team_id: int | None = None
    _edition_id: int | None = None

    async def connect(self):
        global _event_loop
        _event_loop = asyncio.get_running_loop()

        self.handler = SocketDataHandler(self)
        await self.accept()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            _data = json.loads(text_data)
        except (json.JSONDecodeError, TypeError):
            logger.warning("AppConsumer: invalid JSON received")
            return

        request_endpoint = _data.get("endpoint")
        request_data = _data.get("data")

        if not request_endpoint:
            logger.warning("AppConsumer: missing endpoint in message")
            return

        if not self.handler.is_authenticated:
            team = await database_sync_to_async(self.handler.authenticate)(
                request_endpoint, request_data
            )
            if not team:
                await self.send_dict_json({"type": "auth", "data": {"result": 0}})
                await self.close(4003)
                return

            self._team_id = team.id
            self._edition_id = await database_sync_to_async(
                lambda: team.edition_id
            )()
            _connected_consumers[team.id] = self

            auth_data = await database_sync_to_async(
                lambda: {
                    "locationInterval": team.location_update_interval,
                    "messagingEnabled": team.edition.messaging_enabled,
                }
            )()
            await self.send_dict_json({
                "type": "auth",
                "data": {
                    "result": 1,
                    **auth_data,
                },
            })
            return

        try:
            response = await database_sync_to_async(self.handler.handle_request)(
                request_endpoint, request_data
            )
        except KeyError:
            logger.warning("AppConsumer: unknown endpoint '%s'", request_endpoint)
            return
        except Exception:
            logger.exception("AppConsumer: error handling '%s'", request_endpoint)
            return

        if response is not None:
            await self.send_dict_json(response)

            # If a team sent a message, also notify connected backoffice clients
            if request_endpoint == "sendMessage" and self._edition_id:
                bo_consumers = _backoffice_consumers.get(self._edition_id, set())
                for bo in list(bo_consumers):
                    try:
                        await bo.send_dict_json(response)
                    except Exception:
                        logger.warning("AppConsumer: failed to forward to backoffice consumer")

    async def send_dict_json(self, data):
        data_json = json.dumps(data)
        return await self.send(data_json)

    async def disconnect(self, close_code):
        if self.handler.is_authenticated and close_code != 4005:
            await database_sync_to_async(self.handler.close)()

        if self._team_id is not None:
            _connected_consumers.pop(self._team_id, None)


# ─── Backoffice Consumer (admin dashboard) ──────────────────────────

class BackofficeConsumer(AsyncWebsocketConsumer):
    _edition_id: int | None = None

    async def connect(self):
        global _event_loop
        _event_loop = asyncio.get_running_loop()

        self._edition_id = int(self.scope["url_route"]["kwargs"]["edition_id"])
        await self.accept()

        # Register in backoffice consumer set
        if self._edition_id not in _backoffice_consumers:
            _backoffice_consumers[self._edition_id] = set()
        _backoffice_consumers[self._edition_id].add(self)

    async def send_dict_json(self, data):
        data_json = json.dumps(data)
        return await self.send(data_json)

    async def receive(self, text_data=None, bytes_data=None):
        # Backoffice doesn't send messages via WebSocket (uses HTTP forms)
        pass

    async def disconnect(self, close_code):
        if self._edition_id is not None:
            consumers = _backoffice_consumers.get(self._edition_id, set())
            consumers.discard(self)
            if not consumers:
                _backoffice_consumers.pop(self._edition_id, None)
