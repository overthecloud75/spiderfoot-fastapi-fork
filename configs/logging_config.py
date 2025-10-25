import os
import logging
from logging.config import dictConfig

# Log
LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.mkdir(LOG_DIR)

dictConfig({
    'version': 1,
    'formatters': {
        'default': {
            'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        }
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR + '/web.log',
            'maxBytes': 1024 * 1024 * 5,  # 5 MB
            'backupCount': 5,
            'formatter': 'default',
        },
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
            'stream': 'ext://sys.stdout',  # 표준 출력 (stdout)
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file']
    }
})

logger = logging.getLogger(__name__)