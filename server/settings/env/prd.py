from ..base import *

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ["*"]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'daphne_file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/var/log/daphne/server.log',
        },
    },
    'loggers': {
        'daphne': {
		    'handlers': ['daphne_file'],
		    'level': 'DEBUG',
		},
    },
}