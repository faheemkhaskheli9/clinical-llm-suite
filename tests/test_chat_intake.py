"""Tests for issue #11: Port conversational patient intake chat flow."""
import pytest
from django.urls import reverse

from chat_intake import conversation
from chat_intake.conversation import MAX_TURNS, submit_turn
from chat_intake.models import ChatSession

pytestmark = pytest.mark.django_db


def _login(client, django_user_model, username="doc"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    client.force_login(user)
    return user


def test_unauthenticated_start_page_redirects_to_login(client):
    resp = client.get(reverse("chat-intake-start"))
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_starting_a_session_creates_an_active_session_and_redirects(client, django_user_model):
    _login(client, django_user_model)

    resp = client.post(reverse("chat-intake-start"), {"patient_id": "p-1"})

    session = ChatSession.objects.get()
    assert session.patient_id == "p-1"
    assert session.status == ChatSession.Status.ACTIVE
    assert resp.status_code == 302
    assert resp.url == reverse("chat-intake-session", kwargs={"session_id": session.id})


def test_missing_patient_id_reprompts_without_starting_a_session(client, django_user_model):
    _login(client, django_user_model)

    resp = client.post(reverse("chat-intake-start"), {"patient_id": ""})

    assert resp.status_code == 200
    assert b"Patient ID is required." in resp.content
    assert ChatSession.objects.count() == 0


def test_session_completes_early_once_every_field_group_is_extracted(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-2"})
    session = ChatSession.objects.get()

    text = (
        "Temperature is 38.0C, heart rate 90 bpm, BP 120/80, SpO2 97%. "
        "Cough for 2 days, severity 4. History of asthma diagnosed 2018."
    )
    resp = client.post(
        reverse("chat-intake-session", kwargs={"session_id": session.id}),
        {"patient_text": text},
    )

    session.refresh_from_db()
    assert session.status == ChatSession.Status.COMPLETE
    assert session.extraction_record is not None
    assert session.turns.count() == 1
    assert resp.status_code == 200
    assert b"Intake complete." in resp.content


def test_session_asks_followup_questions_in_field_order_when_incomplete(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-3"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    resp = client.post(url, {"patient_text": "Temperature is 37.5C."})
    assert b"symptoms" in resp.content.lower() or b"What symptoms" in resp.content

    session.refresh_from_db()
    assert session.status == ChatSession.Status.ACTIVE


def test_session_force_completes_at_max_turns_even_if_fields_still_missing(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-4"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    # An out-of-range vitals value fails clinical_core validation every
    # turn, so the session never reaches "no missing fields" and instead
    # runs out the clock at MAX_TURNS with no valid record to save.
    for _ in range(MAX_TURNS):
        resp = client.post(url, {"patient_text": "Temperature is 99.0C."})

    session.refresh_from_db()
    assert session.status == ChatSession.Status.COMPLETE
    assert session.turns.count() == MAX_TURNS
    assert b"Reached the turn limit" in resp.content


def test_posting_to_an_already_complete_session_is_rejected_not_a_crash(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-5"})
    session = ChatSession.objects.get()
    submit_turn(
        session,
        "Temperature is 38.0C, heart rate 90 bpm, BP 120/80, SpO2 97%. "
        "Cough for 2 days. History of asthma diagnosed 2018.",
    )
    session.refresh_from_db()
    assert session.status == ChatSession.Status.COMPLETE

    resp = client.post(
        reverse("chat-intake-session", kwargs={"session_id": session.id}),
        {"patient_text": "one more thing"},
    )

    assert resp.status_code == 200
    assert b"already complete" in resp.content
    assert session.turns.count() == 1


def test_unknown_session_id_is_a_404(client, django_user_model):
    _login(client, django_user_model)
    resp = client.get(reverse("chat-intake-session", kwargs={"session_id": "00000000-0000-0000-0000-000000000000"}))
    assert resp.status_code == 404


def test_followup_question_targets_the_named_symptom_missing_detail(client, django_user_model):
    """Issue #12: once a symptom is named but its duration/severity is
    still missing, the next question targets that symptom instead of the
    generic "what symptoms" question -- depends on the prior answer."""
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-6"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    resp = client.post(url, {"patient_text": "Temperature is 37.5C. I have a cough."})

    assert b"How long have you had that cough" in resp.content
    session.refresh_from_db()
    assert session.status == ChatSession.Status.ACTIVE


def test_followup_question_moves_on_once_symptom_detail_is_given(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-7"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    client.post(url, {"patient_text": "Temperature is 37.5C. I have a cough."})
    resp = client.post(url, {"patient_text": "The cough has lasted 3 days."})

    # duration_days is now present for the cough, so the adaptive follow-up
    # no longer applies and the flow moves on to the next missing field.
    assert b"medical history" in resp.content.lower()


def test_adaptive_symptom_followup_falls_back_to_none_with_no_matching_rule(monkeypatch):
    """A named symptom with no entry in `_SYMPTOM_FOLLOWUPS` returns `None`
    (falls back to the fixed FIELD_ORDER question) rather than raising."""
    monkeypatch.setattr(conversation, "_SYMPTOM_FOLLOWUPS", {})
    assert conversation._adaptive_symptom_followup("I have a cough.") is None


def test_adaptive_symptom_followup_none_when_no_symptom_named():
    assert conversation._adaptive_symptom_followup("Temperature is 37.5C.") is None


def test_dashboard_chat_intake_link_redirects_to_real_feature(client, django_user_model):
    _login(client, django_user_model)

    resp = client.get(reverse("feature", kwargs={"slug": "chat-intake"}))

    assert resp.status_code == 302
    assert resp.url == reverse("chat-intake-start")
