from django.urls import path

from . import api_views

urlpatterns = [
    path("review-items/", api_views.review_items, name="review-items"),
]
