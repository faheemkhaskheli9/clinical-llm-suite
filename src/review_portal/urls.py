from django.urls import path

from . import views

urlpatterns = [
    path("", views.queue_list, name="review-queue"),
    path("<uuid:item_id>/", views.item_detail, name="review-item-detail"),
]
