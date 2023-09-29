from ..base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

SERVER_IP = "116.203.112.220"
SERVER_URI = f"http://{SERVER_IP}"

ALLOWED_HOSTS = ['app.tapawingo.nl', SERVER_IP]
CSRF_TRUSTED_ORIGINS = ['https://app.tapawingo.nl']
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
