"""`POST`/`GET /api/review-items/` (issue #6), ported from
`clinical-ai-review-platform`'s `reviews.views.review_items` — same
list/create shape and "reject unknown fields with no partial write"
behaviour, extended to validate against `clinical_core.review.ReviewItem`
(the review-item schema every feature app is expected to submit against,
per that module's docstring) rather than hand-checking each field, and to
persist into the `review_portal.models.ReviewItem` table issue #5 added
instead of the archived app's narrower model.
"""
from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pydantic import ValidationError

from .models import ReviewItem
from .submission import submit_review_item

# Fields a client may set when creating an item. `status`, `quality_rating`,
# `reviewer_comments` are reviewer-decision fields (issue #7), not settable
# at creation time -- an explicit attempt to set them is a 400, same as the
# archived app's "Unknown fields" rejection for `status`.
_CREATE_FIELDS = {"source", "patient_id", "summary", "assigned_to"}
_VALID_STATUSES = {choice for choice, _ in ReviewItem.Status.choices}


def _serialize(item: ReviewItem) -> dict:
    return {
        "id": str(item.id),
        "source": item.source,
        "patient_id": item.patient_id,
        "summary": item.summary,
        "status": item.status,
        "quality_rating": item.quality_rating,
        "reviewer_comments": item.reviewer_comments,
        "assigned_to": item.assigned_to,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _error(field: str, message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"errors": [{"field": field, "message": message}]}, status=status)


def _list(request: HttpRequest) -> JsonResponse:
    status = request.GET.get("status")
    items = ReviewItem.objects.all()
    if status is not None:
        if status not in _VALID_STATUSES:
            return _error(
                "status",
                f"Unknown status {status!r}. Known statuses: {', '.join(sorted(_VALID_STATUSES))}.",
            )
        items = items.filter(status=status)
    return JsonResponse({"items": [_serialize(item) for item in items]})


def _create(request: HttpRequest) -> JsonResponse:
    if request.content_type != "application/json":
        return _error("(root)", "Content-Type must be application/json.", status=415)

    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error("(root)", "Request body must be valid JSON.")
    if not isinstance(payload, dict):
        return _error("(root)", "Request body must be a JSON object.")

    unknown = sorted(set(payload) - _CREATE_FIELDS)
    if unknown:
        return JsonResponse(
            {"errors": [{"field": f, "message": "Unknown field."} for f in unknown]},
            status=400,
        )

    try:
        with transaction.atomic():
            item = submit_review_item(
                source=payload.get("source", ""),
                patient_id=payload.get("patient_id", ""),
                summary=payload.get("summary", ""),
                assigned_to=payload.get("assigned_to"),
            )
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(p) for p in e["loc"]) or "(root)", "message": e["msg"]}
            for e in exc.errors()
        ]
        return JsonResponse({"errors": errors}, status=400)

    return JsonResponse(_serialize(item), status=201)


@csrf_exempt
@login_required
@require_http_methods(["GET", "POST"])
def review_items(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _list(request)
    return _create(request)
