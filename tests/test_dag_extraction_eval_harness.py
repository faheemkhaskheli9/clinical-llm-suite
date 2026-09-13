"""Tests for issue #10: Port prompt evaluation harness."""
from dag_extraction.eval_harness import EXAMPLES, EvalCase, main, run_eval_harness


def test_harness_runs_extraction_and_summarization_against_fixed_examples():
    results = run_eval_harness()
    assert len(results) == len(EXAMPLES)
    assert {r.case_name for r in results} == {c.name for c in EXAMPLES}


def test_harness_reports_pass_per_example_for_the_shipped_fixtures():
    results = run_eval_harness()
    failed = [r for r in results if not r.passed]
    assert not failed, f"unexpected failures: {failed}"


def test_harness_catches_a_regression_in_expected_symptoms():
    bad_case = EvalCase(
        name="regression_check",
        text="Patient reports a cough for 3 days.",
        patient_id="eval-x",
        expected_symptom_names=frozenset({"fever"}),  # wrong on purpose
    )
    results = run_eval_harness((bad_case,))
    assert len(results) == 1
    assert results[0].passed is False
    assert "expected symptoms" in results[0].errors[0]


def test_harness_catches_a_regression_in_expected_vitals():
    bad_case = EvalCase(
        name="regression_check_vitals",
        text="Temperature is 37.0C.",
        patient_id="eval-y",
        expected_vitals={"temperature_c": 38.0},
    )
    results = run_eval_harness((bad_case,))
    assert results[0].passed is False
    assert "vitals.temperature_c" in results[0].errors[0]


def test_harness_catches_a_regression_in_expected_summarization_outcome():
    bad_case = EvalCase(
        name="regression_check_summarization",
        text="Patient seems generally well today.",
        patient_id="eval-z",
        expect_summarization_success=True,  # wrong: nothing extractable
    )
    results = run_eval_harness((bad_case,))
    assert results[0].passed is False
    assert "summarization success" in results[0].errors[0]


def test_harness_is_runnable_offline_with_no_network_or_db(monkeypatch, capsys):
    """No DB access: run_eval_harness must work without pytest-django's
    database fixture (no @pytest.mark.django_db on this test)."""
    exit_code = main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "PASS" in captured.out
