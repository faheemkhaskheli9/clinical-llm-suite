import pytest
from pydantic import ValidationError

from clinical_core.rag.schema import DocType, SourceDocument


def _valid_payload() -> dict:
    return {
        "id": "medlineplus:diabetes",
        "doc_type": "disease",
        "source": "medlineplus",
        "title": "Diabetes",
        "section": "overview",
        "text": "Diabetes is a disease in which blood glucose levels are too high.",
        "url": "https://medlineplus.gov/diabetes.html",
        "metadata": {"query_term": "diabetes"},
    }


def test_valid_document_parses():
    doc = SourceDocument.model_validate(_valid_payload())

    assert doc.doc_type == DocType.DISEASE
    assert doc.source == "medlineplus"
    assert doc.section == "overview"


def test_section_defaults_to_overview_when_omitted():
    payload = _valid_payload()
    payload.pop("section")

    doc = SourceDocument.model_validate(payload)

    assert doc.section == "overview"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.pop("id"),
        lambda payload: payload.update(text=""),
        lambda payload: payload.update(source="not-a-real-source"),
        lambda payload: payload.update(doc_type="not-a-real-type"),
        lambda payload: payload.update(unexpected_field="not allowed"),
    ],
)
def test_malformed_document_fails_validation(mutate):
    payload = _valid_payload()
    mutate(payload)

    with pytest.raises(ValidationError):
        SourceDocument.model_validate(payload)
