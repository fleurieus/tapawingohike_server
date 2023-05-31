from django.urls import path

from .consumers import MyConsumer

urls = [
    path(r"ws/", MyConsumer.as_asgi()),
]
