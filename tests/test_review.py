import uuid

import pytest
from pydantic import ValidationError

from clinical_core.review import ReviewItem, ReviewItemNotFoundError, ReviewQueue


@pytest.fixture
def queue():
    return ReviewQueue()


def test_submit_creates_pending_item_with_unique_id(queue):
    item = queue.submit(source="chat_intake", patient_id="p-1", summary="Draft summary.")
    assert item.status == "pending"
    assert isinstance(item.id, uuid.UUID)
    assert item.quality_rating is None
    assert item.reviewer_comments is None


def test_submitted_ids_never_collide_across_many_items(queue):
    items = [
        queue.submit(source="dag_extraction", patient_id=f"p-{i}", summary="s")
        for i in range(50)
    ]
    assert len({i.id for i in items}) == 50


def test_model_is_usable_independent_of_source_feature_app():
    """Acceptance: "Model is usable independent of which feature app
    created the review item" — same shape/behavior for any `source` string,
    nothing here special-cases chat_intake vs. dag_extraction."""
    a = ReviewItem(source="chat_intake", patient_id="p-1", summary="s")
    b = ReviewItem(source="dag_extraction", patient_id="p-1", summary="s")
    assert a.status == b.status == "pending"
    assert {a.source, b.source} == {"chat_intake", "dag_extraction"}


def test_list_filters_by_status(queue):
    pending = queue.submit(source="chat_intake", patient_id="p-1", summary="s1")
    accepted = queue.submit(source="chat_intake", patient_id="p-2", summary="s2")
    queue.decide(accepted.id, status="accepted")

    assert [i.id for i in queue.list(status="pending")] == [pending.id]
    assert [i.id for i in queue.list(status="accepted")] == [accepted.id]
    assert queue.list(status="rejected") == []


def test_list_filters_by_assignment(queue):
    mine = queue.submit(source="chat_intake", patient_id="p-1", summary="s", assigned_to="alice")
    other = queue.submit(source="chat_intake", patient_id="p-2", summary="s", assigned_to="bob")
    unassigned = queue.submit(source="chat_intake", patient_id="p-3", summary="s")

    assert [i.id for i in queue.list(assigned_to="alice")] == [mine.id]
    assert unassigned.id not in {i.id for i in queue.list(assigned_to="alice")}
    assert other.id not in {i.id for i in queue.list(assigned_to="alice")}


def test_list_filters_combine_status_and_assignment(queue):
    match = queue.submit(source="chat_intake", patient_id="p-1", summary="s", assigned_to="alice")
    queue.decide(match.id, status="accepted")
    queue.submit(source="chat_intake", patient_id="p-2", summary="s", assigned_to="alice")

    result = queue.list(status="accepted", assigned_to="alice")
    assert [i.id for i in result] == [match.id]


def test_assign_updates_reviewer(queue):
    item = queue.submit(source="chat_intake", patient_id="p-1", summary="s")
    updated = queue.assign(item.id, "alice")
    assert updated.assigned_to == "alice"
    assert queue.get(item.id).assigned_to == "alice"


def test_decide_records_status_rating_and_comments(queue):
    item = queue.submit(source="dag_extraction", patient_id="p-1", summary="s")
    updated = queue.decide(
        item.id, status="accepted", quality_rating=4, reviewer_comments="Looks good."
    )
    assert updated.status == "accepted"
    assert updated.quality_rating == 4
    assert updated.reviewer_comments == "Looks good."
    assert updated.updated_at >= updated.created_at


def test_quality_rating_out_of_range_is_rejected(queue):
    item = queue.submit(source="chat_intake", patient_id="p-1", summary="s")
    with pytest.raises(ValidationError):
        queue.decide(item.id, status="accepted", quality_rating=6)


def test_unknown_item_id_raises_not_found(queue):
    with pytest.raises(ReviewItemNotFoundError):
        queue.get(uuid.uuid4())
    with pytest.raises(ReviewItemNotFoundError):
        queue.assign(uuid.uuid4(), "alice")
    with pytest.raises(ReviewItemNotFoundError):
        queue.decide(uuid.uuid4(), status="accepted")


def test_empty_summary_or_patient_id_is_rejected():
    with pytest.raises(ValidationError):
        ReviewItem(source="chat_intake", patient_id="", summary="s")
    with pytest.raises(ValidationError):
        ReviewItem(source="chat_intake", patient_id="p-1", summary="")
