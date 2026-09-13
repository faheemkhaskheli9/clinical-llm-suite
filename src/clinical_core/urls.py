from django.urls import path

from . import views

urlpatterns = [
    path(
        "patient-records/validate/",
        views.validate_patient_record_view,
        name="validate-patient-record",
    ),
]
