from ..base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

SERVER_IP = "116.203.112.220"
SERVER_URI = f"http://{SERVER_IP}:8000"

ALLOWED_HOSTS = [SERVER_IP]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'daphne_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': '/var/log/daphne/server.log',
        },
    },
    'loggers': {
        'daphne': {
		    'handlers': ['daphne_file'],
		    'level': 'INFO',
		},
    },
}