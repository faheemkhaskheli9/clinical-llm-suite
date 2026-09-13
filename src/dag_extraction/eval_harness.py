"""Prompt evaluation harness for the extraction + summarization nodes
(issue #10), ported from `clinical-summary-promptflow`'s planned "prompt
evaluation" step (its README §5 Phase 3 — never actually built there, only
a `VitalsSchema`/CLI validator existed, per that repo's `src/clinical_summary/`).

There is no real prompt here (`extraction.py`/`summarization.py` are
deterministic regex/template nodes standing in for an LLM, per the
CPU-only/no-paid-API project rule) — this harness plays the same role a
prompt-eval harness would: run the extraction+summarization pipeline
against a fixed set of example inputs and score each one, so a change to
either node's logic can be checked against expectations before it ships.
Runs fully offline: no network call, no DB write, no paid API.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .extraction import extract_patient_record
from .summarization import SummarizationError, summarize_record


@dataclass(frozen=True)
class EvalCase:
    """One fixed example input plus what the extraction+summarization
    pipeline is expected to produce for it."""

    name: str
    text: str
    patient_id: str
    expected_symptom_names: frozenset[str] = frozenset()
    expected_vitals: dict = field(default_factory=dict)
    expected_history_conditions: frozenset[str] = frozenset()
    expect_summarization_success: bool = True


@dataclass(frozen=True)
class EvalResult:
    case_name: str
    passed: bool
    errors: tuple[str, ...] = ()


EXAMPLES: tuple[EvalCase, ...] = (
    EvalCase(
        name="cough_with_vitals_and_history",
        text=(
            "Patient reports a cough for 3 days, severity 4/10. Temperature is "
            "38.2C, heart rate 92 bpm, BP 118/76, SpO2 96%. History of asthma "
            "diagnosed 2015."
        ),
        patient_id="eval-1",
        expected_symptom_names=frozenset({"cough"}),
        expected_vitals={
            "temperature_c": 38.2,
            "heart_rate_bpm": 92,
            "systolic_bp_mmhg": 118,
            "diastolic_bp_mmhg": 76,
            "spo2_pct": 96,
        },
        expected_history_conditions=frozenset({"asthma"}),
        expect_summarization_success=True,
    ),
    EvalCase(
        name="severe_headache_only",
        text="Patient reports a severe headache for 2 hours.",
        patient_id="eval-2",
        expected_symptom_names=frozenset({"headache"}),
        expect_summarization_success=True,
    ),
    EvalCase(
        name="nothing_extractable",
        text="Patient seems generally well today.",
        patient_id="eval-3",
        expect_summarization_success=False,
    ),
)


def _check_case(case: EvalCase) -> EvalResult:
    errors: list[str] = []

    result = extract_patient_record(case.text, patient_id=case.patient_id)
    if result.record is None:
        return EvalResult(
            case.name,
            passed=False,
            errors=(f"extraction failed schema validation: {result.validation_errors}",),
        )

    got_symptoms = {s.name for s in result.record.symptoms}
    if case.expected_symptom_names and not case.expected_symptom_names.issubset(got_symptoms):
        errors.append(
            f"expected symptoms {sorted(case.expected_symptom_names)}, got {sorted(got_symptoms)}"
        )

    for field_name, expected_value in case.expected_vitals.items():
        got_value = getattr(result.record.vitals, field_name)
        if got_value != expected_value:
            errors.append(f"vitals.{field_name}: expected {expected_value!r}, got {got_value!r}")

    got_history = {h.condition for h in result.record.history}
    if case.expected_history_conditions and not case.expected_history_conditions.issubset(
        got_history
    ):
        errors.append(
            f"expected history {sorted(case.expected_history_conditions)}, got {sorted(got_history)}"
        )

    try:
        summarize_record(result.record)
        summarization_succeeded = True
    except SummarizationError:
        summarization_succeeded = False

    if summarization_succeeded != case.expect_summarization_success:
        errors.append(
            f"expected summarization success={case.expect_summarization_success}, "
            f"got {summarization_succeeded}"
        )

    return EvalResult(case.name, passed=not errors, errors=tuple(errors))


def run_eval_harness(cases: tuple[EvalCase, ...] = EXAMPLES) -> tuple[EvalResult, ...]:
    return tuple(_check_case(case) for case in cases)


def main() -> int:
    results = run_eval_harness()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.case_name}")
        for error in result.errors:
            print(f"    - {error}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
