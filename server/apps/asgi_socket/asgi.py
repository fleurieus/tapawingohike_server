from channels.routing import URLRouter
from channels.auth import AuthMiddlewareStack


def get_asgi_application():
    """
    Wrap it in a function, lazy import you know
    """
    from .router import urls

    return AuthMiddlewareStack(URLRouter(urls))
