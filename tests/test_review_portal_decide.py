"""Tests for issue #7: reviewer roles/permissions, decide action, error
taxonomy, and the analytics dashboard."""
import pytest
from django.contrib.auth.models import Group
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


def _make_reviewer(client, django_user_model, username="reviewer-1"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    group = Group.objects.get(name="Reviewers")
    user.groups.add(group)
    client.force_login(user)
    return user


def _make_plain_user(client, django_user_model, username="doc"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    client.force_login(user)
    return user


def test_migration_seeds_reviewers_group_with_expected_permissions():
    group = Group.objects.get(name="Reviewers")
    codenames = sorted(p.codename for p in group.permissions.all())
    assert codenames == ["change_reviewitem", "view_reviewitem"]


def test_decide_unauthenticated_redirects_to_login(client):
    item = _make_item()
    resp = client.post(reverse("review-item-decide", kwargs={"item_id": item.id}), {"status": "accepted"})
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_decide_without_reviewer_permission_is_403(client, django_user_model):
    _make_plain_user(client, django_user_model)
    item = _make_item()

    resp = client.post(reverse("review-item-decide", kwargs={"item_id": item.id}), {"status": "accepted"})

    assert resp.status_code == 403
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.PENDING


def test_reviewer_can_accept_with_quality_rating_and_comments(client, django_user_model):
    reviewer = _make_reviewer(client, django_user_model)
    item = _make_item()

    resp = client.post(
        reverse("review-item-decide", kwargs={"item_id": item.id}),
        {"status": "accepted", "quality_rating": "5", "reviewer_comments": "Looks good."},
    )

    assert resp.status_code == 302
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.ACCEPTED
    assert item.quality_rating == 5
    assert item.reviewer_comments == "Looks good."
    assert item.assigned_to == reviewer.get_username()


def test_reject_requires_error_category(client, django_user_model):
    _make_reviewer(client, django_user_model)
    item = _make_item()

    resp = client.post(reverse("review-item-decide", kwargs={"item_id": item.id}), {"status": "rejected"})

    assert resp.status_code == 400
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.PENDING


def test_reject_with_error_category_is_recorded(client, django_user_model):
    _make_reviewer(client, django_user_model)
    item = _make_item()

    resp = client.post(
        reverse("review-item-decide", kwargs={"item_id": item.id}),
        {"status": "rejected", "error_category": "hallucination", "reviewer_comments": "Not in transcript."},
    )

    assert resp.status_code == 302
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.REJECTED
    assert item.error_category == "hallucination"


def test_error_category_rejected_when_status_is_accepted(client, django_user_model):
    _make_reviewer(client, django_user_model)
    item = _make_item()

    resp = client.post(
        reverse("review-item-decide", kwargs={"item_id": item.id}),
        {"status": "accepted", "error_category": "hallucination"},
    )

    assert resp.status_code == 400
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.PENDING


def test_out_of_range_quality_rating_is_rejected_without_partial_write(client, django_user_model):
    _make_reviewer(client, django_user_model)
    item = _make_item()

    resp = client.post(
        reverse("review-item-decide", kwargs={"item_id": item.id}),
        {"status": "accepted", "quality_rating": "9"},
    )

    assert resp.status_code == 400
    item.refresh_from_db()
    assert item.status == ReviewItem.Status.PENDING
    assert item.quality_rating is None


def test_analytics_requires_login(client):
    resp = client.get(reverse("review-analytics"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_analytics_aggregates_by_reviewer_and_by_day(client, django_user_model):
    reviewer = _make_reviewer(client, django_user_model)
    accepted = _make_item(status=ReviewItem.Status.ACCEPTED, assigned_to=reviewer.get_username())
    _make_item(status=ReviewItem.Status.REJECTED, assigned_to=reviewer.get_username())
    _make_item(status=ReviewItem.Status.PENDING)

    resp = client.get(reverse("review-analytics"))

    assert resp.status_code == 200
    content = resp.content.decode()
    assert reviewer.get_username() in content
    assert str(accepted.created_at.date()) in content
