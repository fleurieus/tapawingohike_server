from django.urls import path

from .consumers import AppConsumer

urls = [
    path(r"ws/app/", AppConsumer.as_asgi()),
]
