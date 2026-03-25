from django.urls import path

from .consumers import AppConsumer, BackofficeConsumer

urls = [
    path(r"ws/app/", AppConsumer.as_asgi()),
    path(r"ws/backoffice/<int:edition_id>/", BackofficeConsumer.as_asgi()),
]
