"""Shared validation entry point for every feature app that writes a patient
record (issue #4 — Wire schema validation shared across feature apps).

`chat_intake` and `dag_extraction` (Phase 3/4) each turn free text into a
patient record through very different pipelines (a chat loop vs. a
PromptFlow-style DAG), but both must accept/reject that record by the exact
same rule: `clinical_core.schemas.validate_patient_record`. Routing both
through one Django view — instead of each app importing
`validate_patient_record` and formatting its own error response — means a
schema violation looks identical (same JSON shape, same field names) no
matter which feature app produced the record, which is the acceptance
criterion this issue is checking for.

This view has no feature-app caller yet: `review_portal` (Phase 2) only
persists `ReviewItem` (a draft summary + rating), never a full patient
record, and `chat_intake` / `dag_extraction` (the two apps that will) don't
exist until Phase 3/4. It is still real, wired, and tested today — every
future feature app is expected to POST here (or import
`validate_patient_record_payload` directly, server-side) before persisting a
record, rather than reimplementing validation or hand-rolling its own error
format; see `docs/architecture.md`.
"""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .schemas import PatientRecordValidationError, validate_patient_record


def validate_patient_record_payload(data: dict) -> dict:
    """Validate a raw patient-record dict and return one JSON-serializable
    envelope, regardless of which feature app the data came from.

    `{"ok": True, "record": {...}}` on success, or
    `{"ok": False, "errors": [{"field": ..., "message": ...}, ...]}` on a
    schema violation — the one shape every caller (the view below, a future
    feature app calling this in-process, or a test) gets back.
    """
    try:
        record = validate_patient_record(data)
    except PatientRecordValidationError as exc:
        return {
            "ok": False,
            "errors": [{"field": e.field, "message": e.message} for e in exc.errors],
        }
    return {"ok": True, "record": record.model_dump(mode="json")}


@require_POST
@login_required
@csrf_exempt  # internal API surface only, no browser form posts to it yet
def validate_patient_record_view(request: HttpRequest) -> HttpResponse:
    """`POST /api/patient-records/validate/` — the one place any feature app
    (dashboard-embedded JS, or a server-side call from `chat_intake` /
    `dag_extraction`) sends a candidate patient record before persisting it.
    """
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"ok": False, "errors": [{"field": "(root)", "message": "Invalid JSON body."}]},
            status=400,
        )
    if not isinstance(data, dict):
        return JsonResponse(
            {"ok": False, "errors": [{"field": "(root)", "message": "Body must be a JSON object."}]},
            status=400,
        )

    result = validate_patient_record_payload(data)
    return JsonResponse(result, status=200 if result["ok"] else 422)
