"""Tests for issue #4: wire schema validation shared across feature apps.

`chat_intake` and `dag_extraction` don't exist yet (Phase 3/4), so these
tests stand in for both by posting two differently-shaped payloads (one
"from" a chat-style intake, one "from" a DAG-extraction pass) at the one
shared validation endpoint and asserting they get back the exact same error
shape for the same underlying violation.
"""
import json

import pytest
from django.urls import reverse

from clinical_core.views import validate_patient_record_payload

pytestmark = pytest.mark.django_db


def _valid_record(**overrides):
    record = {
        "patient_id": "p-1",
        "vitals": {"temperature_c": 37.0, "heart_rate_bpm": 72, "spo2_pct": 98.0},
        "symptoms": [{"name": "cough", "duration_days": 3, "severity": 4}],
        "history": [{"condition": "asthma", "diagnosed_year": 2015}],
    }
    record.update(overrides)
    return record


def _post(client, payload):
    return client.post(
        reverse("validate-patient-record"),
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_unauthenticated_request_redirects_to_login(client):
    resp = _post(client, _valid_record())
    assert resp.status_code == 302
    assert resp.url.startswith(reverse("login"))


def test_valid_record_from_either_caller_is_accepted(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc", password="pw12345")
    client.force_login(user)

    chat_intake_shaped = _valid_record(patient_id="chat-p-1")
    dag_extraction_shaped = _valid_record(patient_id="dag-p-1")

    for payload in (chat_intake_shaped, dag_extraction_shaped):
        resp = _post(client, payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["record"]["patient_id"] == payload["patient_id"]


@pytest.mark.parametrize(
    "overrides,bad_field",
    [
        ({"patient_id": ""}, "patient_id"),
        ({"vitals": {"temperature_c": 200}}, "vitals.temperature_c"),
        ({"symptoms": [{"name": "", "severity": 5}]}, "symptoms.0.name"),
        ({"history": [{"condition": "x", "diagnosed_year": 1800}]}, "history.0.diagnosed_year"),
    ],
)
def test_same_violation_is_the_same_error_shape_from_either_caller(
    client, django_user_model, overrides, bad_field
):
    user = django_user_model.objects.create_user(username="doc2", password="pw12345")
    client.force_login(user)

    chat_intake_shaped = _valid_record(**{"patient_id": "chat-p-2", **overrides})
    dag_extraction_shaped = _valid_record(**{"patient_id": "dag-p-2", **overrides})

    responses = [_post(client, chat_intake_shaped), _post(client, dag_extraction_shaped)]

    for resp in responses:
        assert resp.status_code == 422
        body = resp.json()
        assert body["ok"] is False
        fields = [e["field"] for e in body["errors"]]
        assert bad_field in fields

    # Same violation, different "caller" -> byte-identical error payload
    # aside from the field that differs (patient_id), proving one shared
    # validation entry point rather than two reimplementations drifting.
    errors_a = [e for e in responses[0].json()["errors"] if e["field"] == bad_field]
    errors_b = [e for e in responses[1].json()["errors"] if e["field"] == bad_field]
    assert errors_a == errors_b


def test_malformed_json_body_is_a_field_level_error_not_a_500(client, django_user_model):
    user = django_user_model.objects.create_user(username="doc3", password="pw12345")
    client.force_login(user)

    resp = client.post(
        reverse("validate-patient-record"), data="{not json", content_type="application/json"
    )

    assert resp.status_code == 400
    assert resp.json()["ok"] is False


def test_payload_helper_is_the_same_function_the_view_calls():
    """`validate_patient_record_payload` is importable and callable directly,
    so `chat_intake`/`dag_extraction` can validate server-side (not only over
    HTTP) without duplicating the envelope logic."""
    ok_result = validate_patient_record_payload(_valid_record())
    assert ok_result == {"ok": True, "record": ok_result["record"]}
    assert ok_result["record"]["patient_id"] == "p-1"

    bad_result = validate_patient_record_payload(_valid_record(patient_id=""))
    assert bad_result["ok"] is False
    assert bad_result["errors"][0]["field"] == "patient_id"
