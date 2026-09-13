"""List/detail views for the review queue (issue #5).

Accept/reject/rate/comment controls and the reviewer-role/permission checks
that gate them land in a later issue (roles/permissions + analytics) — the
detail view already renders every field a reviewer needs, with those
controls shown as not-yet-wired so the page isn't a dead end while that
lands.
"""
from __future__ import annotations

import uuid

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import ReviewItem

_VALID_STATUSES = {choice for choice, _ in ReviewItem.Status.choices}


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
    return render(request, "review_portal/item_detail.html", {"item": item})
