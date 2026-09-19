"""Tests for issue #16: wire both intake feature apps into the shared
review queue, and show which feature app originated an item on the detail
page."""
import pytest
from django.urls import reverse

from chat_intake.conversation import MAX_TURNS
from chat_intake.models import ChatSession
from dag_extraction.models import ExtractionRecord
from review_portal.models import ReviewItem

pytestmark = pytest.mark.django_db

SAMPLE_TEXT = (
    "Patient reports a cough for 3 days, severity 4/10. Temperature is 38.2C, "
    "heart rate 92 bpm, BP 118/76, SpO2 96%. History of asthma diagnosed 2015."
)


def _login(client, django_user_model, username="doc"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    client.force_login(user)
    return user


# --- dag_extraction submits completed extractions ------------------------


def test_completed_extraction_is_submitted_to_the_review_queue(client, django_user_model):
    _login(client, django_user_model)

    client.post(reverse("dag-extraction"), {"patient_id": "p-1", "text": SAMPLE_TEXT})

    record = ExtractionRecord.objects.get(patient_id="p-1")
    item = ReviewItem.objects.get(patient_id="p-1")
    assert item.source == "dag_extraction"
    assert item.summary == record.summary
    assert item.status == ReviewItem.Status.PENDING


def test_extraction_with_nothing_to_summarize_is_not_submitted(client, django_user_model):
    """A saved extraction whose summarization failed has nothing
    review-worthy yet, so it must not create an empty/junk review item."""
    _login(client, django_user_model)

    client.post(
        reverse("dag-extraction"),
        {"patient_id": "p-2", "text": "Patient seems generally well today."},
    )

    record = ExtractionRecord.objects.get(patient_id="p-2")
    assert record.summarization_failed is True
    assert ReviewItem.objects.filter(patient_id="p-2").count() == 0


def test_failed_extraction_with_no_record_is_not_submitted(client, django_user_model):
    _login(client, django_user_model)

    client.post(reverse("dag-extraction"), {"patient_id": "p-3", "text": "Temperature is 99.0C."})

    assert ExtractionRecord.objects.filter(patient_id="p-3").count() == 0
    assert ReviewItem.objects.filter(patient_id="p-3").count() == 0


# --- chat_intake submits completed intakes -------------------------------


def _complete_session(client, patient_id):
    client.post(reverse("chat-intake-start"), {"patient_id": patient_id})
    session = ChatSession.objects.get(patient_id=patient_id)
    client.post(
        reverse("chat-intake-session", kwargs={"session_id": session.id}),
        {"patient_text": SAMPLE_TEXT},
    )
    session.refresh_from_db()
    return session


def test_completed_intake_is_submitted_to_the_review_queue(client, django_user_model):
    _login(client, django_user_model)

    session = _complete_session(client, "p-4")

    item = ReviewItem.objects.get(patient_id="p-4")
    assert item.source == "chat_intake"
    assert item.summary == session.summary_text
    assert item.status == ReviewItem.Status.PENDING


def test_intake_with_no_summary_is_not_submitted(client, django_user_model):
    """Forced completion at MAX_TURNS with nothing extractable leaves
    `summary_text` None -- there is no draft summary to hand a reviewer."""
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-5"})
    session = ChatSession.objects.get(patient_id="p-5")
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    for _ in range(MAX_TURNS):
        client.post(url, {"patient_text": "Temperature is 99.0C."})

    session.refresh_from_db()
    assert session.summary_text is None
    assert ReviewItem.objects.filter(patient_id="p-5").count() == 0


# --- review-item detail view shows the originating feature app ----------


def test_review_item_detail_shows_the_originating_feature_app(client, django_user_model):
    _login(client, django_user_model)
    session = _complete_session(client, "p-6")
    item = ReviewItem.objects.get(patient_id="p-6")

    resp = client.get(reverse("review-item-detail", kwargs={"item_id": item.id}))

    assert resp.status_code == 200
    assert b"chat_intake" in resp.content


def test_review_queue_lists_items_from_both_feature_apps_together(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("dag-extraction"), {"patient_id": "p-7", "text": SAMPLE_TEXT})
    _complete_session(client, "p-8")

    resp = client.get(reverse("review-queue"))

    assert resp.status_code == 200
    sources = set(ReviewItem.objects.values_list("source", flat=True))
    assert sources == {"dag_extraction", "chat_intake"}
