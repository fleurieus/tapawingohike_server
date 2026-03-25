from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    path(
        "messages/upload-image/",
        views.upload_message_image,
        name="upload_message_image",
    ),
]
