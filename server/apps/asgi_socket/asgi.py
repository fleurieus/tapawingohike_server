from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

from .router import urls


def get_asgi_application():
    """
    Wrap it in a function, lazy import you know
    """
    return AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(urls)
        )
    )
