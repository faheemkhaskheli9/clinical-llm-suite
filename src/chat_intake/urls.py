from django.urls import path

from . import views

urlpatterns = [
    path("start/", views.start, name="chat-intake-start"),
    path("<uuid:session_id>/", views.session_view, name="chat-intake-session"),
]
