from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator


def get_asgi_application():
    """
    Wrap it in a function, lazy import you know
    """
    from .router import urls

    return AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(urls)))
