"""List/detail/decide/analytics views for the review queue.

List/detail landed in issue #5. `decide` (accept/reject with quality
rating, comments, and error taxonomy) plus the analytics dashboard land in
issue #7, gated by the `review_portal.change_reviewitem` /
`review_portal.view_reviewitem` permissions Django auto-generates for
`ReviewItem` — the `Reviewers` group (seeded by migration
`0003_seed_reviewers_group`) holds both.
"""
from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ReviewItem

_VALID_STATUSES = {choice for choice, _ in ReviewItem.Status.choices}
_DECIDABLE_STATUSES = {ReviewItem.Status.ACCEPTED, ReviewItem.Status.REJECTED}
_VALID_ERROR_CATEGORIES = {choice for choice, _ in ReviewItem.ErrorCategory.choices}


@login_required
def queue_list(request: HttpRequest) -> HttpResponse:
    """`?status=` filters the queue; defaults to pending (the common case for
    a reviewer working through the backlog). An explicit-but-unknown status
    is a 404, not a silent fall-back to pending — it's user-supplied input,
    not a missing default."""
    status = request.GET.get("status") or ReviewItem.Status.PENDING
    if status not in _VALID_STATUSES:
        raise Http404(f"Unknown status filter: {status!r}")

    items = ReviewItem.objects.filter(status=status)
    return render(
        request,
        "review_portal/queue_list.html",
        {"items": items, "status": status, "statuses": ReviewItem.Status.choices},
    )


@login_required
def item_detail(request: HttpRequest, item_id: uuid.UUID) -> HttpResponse:
    item = get_object_or_404(ReviewItem, id=item_id)
    can_decide = request.user.has_perm("review_portal.change_reviewitem")
    return render(
        request,
        "review_portal/item_detail.html",
        {"item": item, "can_decide": can_decide, "error_categories": ReviewItem.ErrorCategory.choices},
    )


def _bad_request(message: str) -> HttpResponseBadRequest:
    return HttpResponseBadRequest(message)


@require_POST
@login_required
@permission_required("review_portal.change_reviewitem", raise_exception=True)
def decide(request: HttpRequest, item_id: uuid.UUID) -> HttpResponse:
    """Record a reviewer's accept/reject decision plus optional quality
    rating and comments, and -- only when rejecting -- a required error
    taxonomy category (acceptance criterion: "error taxonomy are recorded
    per review item")."""
    item = get_object_or_404(ReviewItem, id=item_id)

    status = request.POST.get("status")
    if status not in _DECIDABLE_STATUSES:
        return _bad_request(
            f"status must be one of {sorted(_DECIDABLE_STATUSES)!r}, got {status!r}."
        )

    quality_rating_raw = (request.POST.get("quality_rating") or "").strip()
    quality_rating = None
    if quality_rating_raw:
        try:
            quality_rating = int(quality_rating_raw)
        except ValueError:
            return _bad_request("quality_rating must be an integer between 1 and 5.")
        if not 1 <= quality_rating <= 5:
            return _bad_request("quality_rating must be between 1 and 5.")

    error_category = (request.POST.get("error_category") or "").strip() or None
    if status == ReviewItem.Status.REJECTED:
        if not error_category:
            return _bad_request("error_category is required when rejecting an item.")
        if error_category not in _VALID_ERROR_CATEGORIES:
            return _bad_request(f"Unknown error_category {error_category!r}.")
    elif error_category:
        return _bad_request("error_category is only valid when rejecting an item.")

    reviewer_comments = (request.POST.get("reviewer_comments") or "").strip() or None

    item.status = status
    item.quality_rating = quality_rating
    item.error_category = error_category
    item.reviewer_comments = reviewer_comments
    item.assigned_to = request.user.get_username()
    item.save()

    return redirect("review-item-detail", item_id=item.id)


@login_required
@permission_required("review_portal.view_reviewitem", raise_exception=True)
def analytics_dashboard(request: HttpRequest) -> HttpResponse:
    """Aggregate review outcomes by reviewer and by day (acceptance
    criterion: "Analytics dashboard aggregates review outcomes by reviewer
    and by time window")."""
    by_reviewer = (
        ReviewItem.objects.exclude(assigned_to__isnull=True)
        .values("assigned_to", "status")
        .annotate(count=Count("id"))
        .order_by("assigned_to", "status")
    )
    by_day = (
        ReviewItem.objects.annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
        .order_by("day", "status")
    )
    return render(
        request,
        "review_portal/analytics.html",
        {"by_reviewer": by_reviewer, "by_day": by_day},
    )
