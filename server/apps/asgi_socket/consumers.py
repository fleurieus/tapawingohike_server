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

        request_type = _data["type"]
        request_data = _data["data"]

        # if the user is not authenticated: authenticate
        if not self.handler.is_authenticated:
            # close if not authenticated
            if not self.handler.authenticate(request_type, request_data):
                self.close(4003)

            return

        # if authenticated handle the request
        self.handler.handle_request(request_type, request_data)

    def send_dict_json(self, data):
        # before we send the data, parse it to json
        return self.send(json.dumps(data))

    def disconnect(self, close_code):
        if self.handler.is_authenticated:
            self.handler.close()

        return super().disconnect(close_code)


"""
data = {
    "type": "route",
    "data": {
        "type": "audio",
        "data": {
            "fullscreen": False,
            "zoomEnabled": False,
            "image": "https://www.basmeelker.nl/wp-content/uploads/winterlandschap-ijs-op-het-ijsselmeer.jpg",
            "audio": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
            "coordinate": {
                "latitude": 52.258779,
                "longitude": 5.970222,
                "radius": 15,
                "confirmByUser": True
            }
        }
    }
}
self.send_dict_json(data)

"""
