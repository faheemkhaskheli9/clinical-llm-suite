"""Tests for issue #5: Port review queue list/detail views."""
import pytest
from django.urls import reverse

from review_portal.models import ReviewItem

pytestmark = pytest.mark.django_db


def _make_item(**overrides):
    fields = {
        "source": "dag_extraction",
        "patient_id": "p-1",
        "summary": "Patient reports a 3-day cough, afebrile.",
        "status": ReviewItem.Status.PENDING,
    }
    fields.update(overrides)
    return ReviewItem.objects.create(**fields)


def _login(client, django_user_model, **kwargs):
    user = django_user_model.objects.create_user(username="doc", password="pw12345")
    client.force_login(user)
    return user


def test_unauthenticated_queue_list_redirects_to_login(client):
    resp = client.get(reverse("review-queue"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_unauthenticated_detail_redirects_to_login(client):
    item = _make_item()
    resp = client.get(reverse("review-item-detail", kwargs={"item_id": item.id}))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_queue_list_defaults_to_pending_items(client, django_user_model):
    _login(client, django_user_model)
    pending = _make_item(summary="Pending summary text")
    _make_item(summary="Accepted summary text", status=ReviewItem.Status.ACCEPTED)

    resp = client.get(reverse("review-queue"))

    assert resp.status_code == 200
    assert pending.source.encode() in resp.content
    assert b"Accepted summary text" not in resp.content


def test_queue_list_filters_by_status_query_param(client, django_user_model):
    _login(client, django_user_model)
    _make_item(summary="Pending summary text")
    accepted = _make_item(summary="Accepted summary text", status=ReviewItem.Status.ACCEPTED)

    resp = client.get(reverse("review-queue"), {"status": "accepted"})

    assert resp.status_code == 200
    assert accepted.summary.encode() in resp.content
    assert b"Pending summary text" not in resp.content


def test_queue_list_rejects_unknown_status_filter(client, django_user_model):
    _login(client, django_user_model)
    resp = client.get(reverse("review-queue"), {"status": "not-a-status"})
    assert resp.status_code == 404


def test_item_detail_shows_full_record_and_review_controls(client, django_user_model):
    _login(client, django_user_model)
    item = _make_item(
        quality_rating=4,
        reviewer_comments="Looks accurate.",
        assigned_to="reviewer-1",
    )

    resp = client.get(reverse("review-item-detail", kwargs={"item_id": item.id}))

    assert resp.status_code == 200
    content = resp.content.decode()
    assert item.source in content
    assert item.patient_id in content
    assert item.summary in content
    assert "4" in content
    assert "Looks accurate." in content
    assert "reviewer-1" in content
    assert "Review controls" in content


def test_item_detail_unknown_id_is_404(client, django_user_model):
    import uuid

    _login(client, django_user_model)
    resp = client.get(reverse("review-item-detail", kwargs={"item_id": uuid.uuid4()}))
    assert resp.status_code == 404


def test_dashboard_review_portal_link_redirects_to_real_queue(client, django_user_model):
    _login(client, django_user_model)
    resp = client.get(reverse("feature", kwargs={"slug": "review-portal"}))
    assert resp.status_code == 302
    assert resp.url == reverse("review-queue")
