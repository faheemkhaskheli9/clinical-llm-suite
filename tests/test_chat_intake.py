"""Tests for issue #11: Port conversational patient intake chat flow."""
import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from chat_intake import conversation, recommendations, summary
from chat_intake.conversation import MAX_TURNS, submit_turn
from chat_intake.models import ChatSession
from clinical_core.rag import ingest
from clinical_core.rag.embeddings import HashingEmbedder
from clinical_core.rag.schema import DocType, SourceDocument
from clinical_core.rag.vector_store import JSONVectorStore

pytestmark = pytest.mark.django_db


def _login(client, django_user_model, username="doc"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    client.force_login(user)
    return user


def _login_as_doctor(client, django_user_model, username="doctor-1"):
    user = django_user_model.objects.create_user(username=username, password="pw12345")
    user.groups.add(Group.objects.get(name="Doctors"))
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


# --- issue #14: RAG-backed recommendations wired into chat intake -------


def test_completing_a_session_persists_a_generic_recommendation_by_default(client, django_user_model):
    """With no RAG store ingested (the default, empty store), completion
    still produces a recommendation, but a clearly-labeled generic one --
    never a fabricated citation."""
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-8"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    resp = client.post(
        url,
        {
            "patient_text": (
                "Temperature is 38.0C, heart rate 90 bpm, BP 120/80, SpO2 97%. "
                "Cough for 2 days, severity 4. History of asthma diagnosed 2018."
            )
        },
    )

    session.refresh_from_db()
    assert session.recommendation_text is not None
    assert session.recommendation_grounded is False
    assert session.recommendation_sources == []
    assert b"General guidance" in resp.content
    assert b"Recommendation" in resp.content


def test_completing_a_session_grounds_the_recommendation_in_a_retrieved_chunk(
    client, django_user_model, tmp_path, monkeypatch
):
    """Core acceptance criterion: when the RAG store has a relevant chunk,
    the recommendation is grounded and references its source."""
    store = JSONVectorStore(tmp_path / "store.json")
    embedder = HashingEmbedder(dimensions=64)
    ingest.ingest_documents(
        [
            SourceDocument(
                id="medlineplus:asthma",
                doc_type=DocType.DISEASE,
                source="medlineplus",
                title="Asthma",
                section="overview",
                text="asthma cough wheezing shortness of breath treatment plan",
                url="https://medlineplus.gov/asthma.html",
            )
        ],
        embedder,
        store,
    )
    monkeypatch.setattr(recommendations, "default_store", lambda: store)
    monkeypatch.setattr(recommendations, "default_embedder", lambda: embedder)
    monkeypatch.setattr(recommendations, "MIN_SIMILARITY", 0.01)

    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-9"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    resp = client.post(
        url,
        {
            "patient_text": (
                "Temperature is 38.0C, heart rate 90 bpm, BP 120/80, SpO2 97%. "
                "Cough for 2 days, severity 4. History of asthma diagnosed 2018."
            )
        },
    )

    session.refresh_from_db()
    assert session.recommendation_grounded is True
    assert session.recommendation_sources
    assert session.recommendation_sources[0]["title"] == "Asthma"
    assert b"Asthma" in resp.content
    assert b"General guidance" not in resp.content


def test_no_recommendation_is_persisted_when_extraction_finds_nothing_valid(client, django_user_model):
    """If extraction never produced a valid record at all (forced
    completion at MAX_TURNS with everything failing validation), there is
    no patient data to recommend on, so no recommendation is generated --
    distinct from the generic-fallback case, which still has query text."""
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-10"})
    session = ChatSession.objects.get()
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    for _ in range(MAX_TURNS):
        client.post(url, {"patient_text": "Temperature is 99.0C."})

    session.refresh_from_db()
    assert session.extraction_record is None
    assert session.recommendation_text is None


# --- issue #15: doctor-facing summary ------------------------------------


def test_migration_seeds_doctors_group_with_view_permission():
    group = Group.objects.get(name="Doctors")
    codenames = sorted(p.codename for p in group.permissions.all())
    assert codenames == ["view_chatsession"]


def _complete_session(client, patient_id):
    client.post(reverse("chat-intake-start"), {"patient_id": patient_id})
    session = ChatSession.objects.get(patient_id=patient_id)
    client.post(
        reverse("chat-intake-session", kwargs={"session_id": session.id}),
        {
            "patient_text": (
                "Temperature is 38.0C, heart rate 90 bpm, BP 120/80, SpO2 97%. "
                "Cough for 2 days, severity 4. History of asthma diagnosed 2018."
            )
        },
    )
    session.refresh_from_db()
    return session


def test_completing_a_session_generates_and_persists_a_summary(client, django_user_model):
    _login(client, django_user_model)

    session = _complete_session(client, "p-11")

    assert session.status == ChatSession.Status.COMPLETE
    assert session.summary_text is not None
    assert "p-11" in session.summary_text


def test_summary_generation_failure_does_not_block_the_record_from_being_saved(
    client, django_user_model, monkeypatch
):
    """Core acceptance criterion: a summary-generation failure must not
    prevent the underlying intake record (status/extraction_record) from
    being saved."""

    def _boom(record, *, turn_count):
        raise summary.SummaryGenerationError("simulated failure")

    monkeypatch.setattr(conversation, "generate_intake_summary", _boom)
    _login(client, django_user_model)

    session = _complete_session(client, "p-12")

    assert session.status == ChatSession.Status.COMPLETE
    assert session.extraction_record is not None
    assert session.summary_text is None


def test_no_summary_is_persisted_when_extraction_finds_nothing_valid(client, django_user_model):
    _login(client, django_user_model)
    client.post(reverse("chat-intake-start"), {"patient_id": "p-13"})
    session = ChatSession.objects.get(patient_id="p-13")
    url = reverse("chat-intake-session", kwargs={"session_id": session.id})

    for _ in range(MAX_TURNS):
        client.post(url, {"patient_text": "Temperature is 99.0C."})

    session.refresh_from_db()
    assert session.extraction_record is None
    assert session.summary_text is None


def test_summary_view_requires_doctor_permission_not_just_login(client, django_user_model):
    _login(client, django_user_model)
    session = _complete_session(client, "p-14")

    resp = client.get(reverse("chat-intake-summary", kwargs={"session_id": session.id}))

    assert resp.status_code == 403


def test_summary_view_unauthenticated_redirects_to_login(client, django_user_model):
    _login(client, django_user_model)
    session = _complete_session(client, "p-15")

    # A fresh, unauthenticated client hitting the doctor view.
    from django.test import Client

    resp = Client().get(reverse("chat-intake-summary", kwargs={"session_id": session.id}))

    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_doctor_can_view_the_persisted_summary(client, django_user_model):
    _login(client, django_user_model)
    session = _complete_session(client, "p-16")

    _login_as_doctor(client, django_user_model)
    resp = client.get(reverse("chat-intake-summary", kwargs={"session_id": session.id}))

    assert resp.status_code == 200
    assert b"p-16" in resp.content
    assert session.summary_text.encode() in resp.content
