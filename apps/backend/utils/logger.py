
import logging
from pythonjsonlogger import jsonlogger
import sys
import os
from datetime import datetime

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        if log_record.get('level'):
            log_record['level'] = log_record['level'].upper()
        else:
            log_record['level'] = record.levelname

def get_logger(name):
    logger = logging.getLogger(name)
    
    # Avoid adding handlers multiple times
    if not logger.handlers:
        # File Handler - Always UTF-8
        try:
            fh = logging.FileHandler('backend_error.log', encoding='utf-8')
            fh.setFormatter(CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s'))
            logger.addHandler(fh)
        except Exception as e:
            print(f"Failed to initialize FileHandler: {e}")
        
        # Stream Handler - Robust against encoding errors on Windows
        try:
            # sys.stdout.reconfigure is Python 3.7+
            if sys.platform == "win32" and hasattr(sys.stdout, 'reconfigure'):
                try:
                    sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
                except Exception:
                    pass
            
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s'))
            logger.addHandler(sh)
        except Exception as e:
            print(f"Failed to initialize StreamHandler: {e}")
        
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
    return logger
