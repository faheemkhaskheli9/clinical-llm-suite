"""Tests for issue #6: Port review-item API endpoints."""
import json

import pytest
from django.urls import reverse

from review_portal.models import ReviewItem

pytestmark = pytest.mark.django_db


def _post(client, payload):
    return client.post(
        reverse("review-items"), data=json.dumps(payload), content_type="application/json"
    )


def test_unauthenticated_post_redirects_to_login(client):
    resp = _post(client, {"source": "s", "patient_id": "p-1", "summary": "sum"})
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_unauthenticated_get_redirects_to_login(client):
    resp = client.get(reverse("review-items"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_post_persists_item_and_returns_stable_identifier(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc", password="pw12345")
    client.force_login(user)

    resp = _post(
        client, {"source": "dag_extraction", "patient_id": "p-1", "summary": "Follow-up advised."}
    )

    assert resp.status_code == 201
    item = ReviewItem.objects.get()
    assert resp.json()["id"] == str(item.id)
    assert item.status == ReviewItem.Status.PENDING
    assert item.source == "dag_extraction"
    assert item.patient_id == "p-1"


def test_post_missing_required_field_is_a_field_level_error_not_a_partial_write(
    client, django_user_model
):
    user = django_user_model.objects.create_user(username="doc2", password="pw12345")
    client.force_login(user)

    resp = _post(client, {"source": "dag_extraction", "summary": "Missing patient id."})

    assert resp.status_code == 400
    fields = [e["field"] for e in resp.json()["errors"]]
    assert "patient_id" in fields
    assert ReviewItem.objects.count() == 0


def test_post_unknown_field_is_rejected_without_partial_write(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc3", password="pw12345")
    client.force_login(user)

    resp = _post(
        client,
        {
            "source": "dag_extraction",
            "patient_id": "p-1",
            "summary": "sum",
            "status": "accepted",
        },
    )

    assert resp.status_code == 400
    assert resp.json()["errors"][0]["field"] == "status"
    assert ReviewItem.objects.count() == 0


def test_get_lists_all_items_with_no_filter(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc4", password="pw12345")
    client.force_login(user)
    ReviewItem.objects.create(source="s", patient_id="p-1", summary="a")
    ReviewItem.objects.create(
        source="s", patient_id="p-2", summary="b", status=ReviewItem.Status.ACCEPTED
    )

    resp = client.get(reverse("review-items"))

    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_get_filters_by_status(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc5", password="pw12345")
    client.force_login(user)
    ReviewItem.objects.create(source="s", patient_id="p-1", summary="pending one")
    ReviewItem.objects.create(
        source="s", patient_id="p-2", summary="accepted one", status=ReviewItem.Status.ACCEPTED
    )

    resp = client.get(reverse("review-items"), {"status": "accepted"})

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["summary"] == "accepted one"


def test_get_with_unknown_status_filter_is_a_400(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc6", password="pw12345")
    client.force_login(user)

    resp = client.get(reverse("review-items"), {"status": "not-a-status"})

    assert resp.status_code == 400
