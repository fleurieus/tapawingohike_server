from channels.generic.websocket import WebsocketConsumer


class MyConsumer(WebsocketConsumer):
    def connect(self):
        print("\nconnect\n")
        self.accept()

    def receive(self, text_data=None, bytes_data=None):
        print("\nreceive\n")
        self.send("test")

    def disconnect(self, close_code):
        print("\ndisconnect\n")
