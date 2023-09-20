import json
import logging  # Import the logging module

from channels.generic.websocket import WebsocketConsumer

from .handlers import SocketDataHandler

# Configure your logger
logger = logging.getLogger(__name__)

class AppConsumer(WebsocketConsumer):
    handler = None

    def connect(self):
        # set handler with self as consumer
        self.handler = SocketDataHandler(self)
        self.accept()

    def receive(self, text_data=None, bytes_data=None):
        # Log incoming data
        logger.info(f"Incoming data: {text_data}")

        # parse incoming data as dict
        _data = json.loads(text_data)

        request_endpoint = _data["endpoint"]
        request_data = _data.get("data")

        # ... rest of your code ...

    def send_dict_json(self, data):
        # before we send the data, parse it to JSON
        return self.send(json.dumps(data))

    def disconnect(self, close_code):
        if self.handler.is_authenticated:
            self.handler.close()

        return super().disconnect(close_code)
