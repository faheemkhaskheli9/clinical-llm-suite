from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from review_portal.submission import submit_review_item

from .pipeline import run_pipeline


@login_required
def extract(request: HttpRequest) -> HttpResponse:
    result = None
    record = None
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
            record, result = run_pipeline(text, patient_id=patient_id)
            # A completed extraction is one with a usable draft summary --
            # `summarization_failed` means there's nothing yet for a
            # reviewer to review (issue #16 acceptance criterion covers
            # *completed* extractions, not partial ones).
            if record is not None and not record.summarization_failed:
                submit_review_item(
                    source="dag_extraction",
                    patient_id=patient_id,
                    summary=record.summary,
                )

    return render(
        request,
        "dag_extraction/extract.html",
        {"result": result, "record": record, "text": text, "patient_id": patient_id, "error": error},
    )
