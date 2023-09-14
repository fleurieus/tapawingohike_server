import json

from channels.generic.websocket import WebsocketConsumer

from .handlers import SocketDataHandler


class AppConsumer(WebsocketConsumer):
    handler = None

    def connect(self):
        # set handler with self as consumer
        self.handler = SocketDataHandler(self)
        self.accept()

    def receive(self, text_data=None, bytes_data=None):
        # parse incomming data as dict
        _data = json.loads(text_data)

        request_endpoint = _data["endpoint"]
        request_data = _data.get("data")

        # if the user is not authenticated: authenticate
        if not self.handler.is_authenticated:
            # close if not authenticated
            if not self.handler.authenticate(request_endpoint, request_data):
                self.send_dict_json({"type": "auth", "data": {"result": 0}})
                self.close(4003)

            # send loginresult success
            self.send_dict_json({"type": "auth", "data": {"result": 1}})

            return
        

        # if authenticated handle the request
        self.handler.handle_request(request_endpoint, request_data)

    def send_dict_json(self, data):
        # before we send the data, parse it to json
        return self.send(json.dumps(data))

    def disconnect(self, close_code):
        if self.handler.is_authenticated:
            self.handler.close()

        return super().disconnect(close_code)
