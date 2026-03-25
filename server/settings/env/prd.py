from ..base import *

DEBUG = False

SERVER_IP = os.environ.get("SERVER_IP", "127.0.0.1")
SERVER_URI = f"https://{SERVER_IP}"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "app.tapawingo.nl").split(",")
CSRF_TRUSTED_ORIGINS = [
    f"https://{h}" for h in ALLOWED_HOSTS if h and h != "*"
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "daphne": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
