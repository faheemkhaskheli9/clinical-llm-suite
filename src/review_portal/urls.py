from django.urls import path

from . import views

urlpatterns = [
    path("", views.queue_list, name="review-queue"),
    path("analytics/", views.analytics_dashboard, name="review-analytics"),
    path("<uuid:item_id>/", views.item_detail, name="review-item-detail"),
    path("<uuid:item_id>/decide/", views.decide, name="review-item-decide"),
]
