import json
import logging
from datetime import datetime,timezone

class JsonFormatter(logging.Formatter):
    def format(self,record):
        message=record.getMessage()
        try:
            payload=json.loads(message)
            if not isinstance(payload,dict):
                payload={'message':message}
        except (ValueError,TypeError):
            payload={'message':message}
        payload.update(time=datetime.now(timezone.utc).isoformat(),level=record.levelname,logger=record.name)
        if record.exc_info:
            payload['exception']=self.formatException(record.exc_info)
        return json.dumps(payload,ensure_ascii=False)

def configure_logging():
    handler=logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root=logging.getLogger()
    root.handlers=[handler]
    root.setLevel(logging.INFO)
