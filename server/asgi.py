import os

from django.core.asgi import get_asgi_application as get_asgi_django_application
from channels.routing import ProtocolTypeRouter
from server.apps.asgi_socket.asgi import get_asgi_application as get_asgi_websocket_application


# this can because the manage.py file is the entrypoint for debug and asgi for prd
if not os.environ.get("DJANGO_SETTINGS_MODULE", None):
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'server.settings.env.prd')

django_asgi_app = get_asgi_django_application()
websocket_asgi_app = get_asgi_websocket_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": websocket_asgi_app,
})
