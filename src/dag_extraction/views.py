from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .extraction import extract_patient_record


@login_required
def extract(request: HttpRequest) -> HttpResponse:
    result = None
    text = ""
    patient_id = ""
    error = None

    if request.method == "POST":
        text = request.POST.get("text", "")
        patient_id = request.POST.get("patient_id", "").strip()
        if not patient_id:
            # A missing patient_id is explicit user input, not a default to
            # paper over with a placeholder id that could collide across
            # submissions -- re-show the form with the problem instead.
            error = "Patient ID is required."
        elif not text.strip():
            error = "Paste some conversation text to extract from."
        else:
            result = extract_patient_record(text, patient_id=patient_id)

    return render(
        request,
        "dag_extraction/extract.html",
        {"result": result, "text": text, "patient_id": patient_id, "error": error},
    )
