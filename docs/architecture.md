# Architecture Notes: Clinical LLM Suite

## Pipeline

```text
Dashboard (pick intake mode) ->
[Patient Chat Intake (assistant) | Structured DAG Extraction (promptflow)] ->
Structured Extraction (vitals/symptoms/history, schema-versioned) ->
Clinical Reasoning (RAG + LLM) -> Draft Summary ->
Review Queue (accept/reject/rate/comment) -> Approved Summary + Analytics
```

## Components

- `clinical_core` — versioned patient-record schema (ported from
  `clinical-ai-assistant`'s `src/schemas/` + `configs/schema.yaml`
  compatibility policy), RAG reference-corpus ingest
  (`scripts/ingest.py`: MedlinePlus, openFDA, MedQuAD), review-item model
  (ported from `clinical-ai-review-platform`)
- `chat_intake` feature app — ported from `clinical-ai-assistant`:
  conversational intake, dynamic follow-ups, extraction, RAG-backed
  recommendations
- `dag_extraction` feature app — ported from `clinical-summary-promptflow`:
  schema-validated field extraction with missing-value handling,
  summarization node. Issue #8 added the actual extraction step (that repo
  only ever had the field shapes — `VitalsSchema`/`SymptomSchema` — and a
  CLI that validated an already-structured JSON blob, never text-in
  extraction): deterministic regex/keyword matching over raw conversation
  text, standing in for an LLM extraction call per the CPU-only/no-paid-API
  rule, that assembles vitals/symptoms/history and validates the result
  through `clinical_core.schemas.validate_patient_record` before handing it
  back; each field group with nothing found is flagged in
  `ExtractionResult.missing_fields` rather than silently left empty.
- `review_portal` feature app — ported from `clinical-ai-review-platform`'s
  already-implemented Django queue (`POST/GET /api/review-items/`). List/detail
  pages landed in issue #5 (`ReviewItem` ORM model extending the archived
  app's shape with `patient_id`/`quality_rating`/`reviewer_comments`/
  `assigned_to` to match `clinical_core.review.ReviewItem`'s contract);
  `POST/GET /api/review-items/` landed in issue #6, validating create
  payloads against `clinical_core.review.ReviewItem` instead of hand-checked
  fields. Issue #7 added a `Reviewers` auth group (seeded by a data
  migration, holding the `change_reviewitem`/`view_reviewitem` permissions
  Django auto-generates for the model), the `decide` view (accept/reject +
  quality rating + comments + a required error-taxonomy category on reject),
  and an analytics dashboard aggregating outcomes by reviewer and by day.
  `clinical-ai-review-platform` never got past planning these three in its
  own README/docs — there was no code to port, only the shape to match.

## Shared validation entry point (issue #4)

`clinical_core.views.validate_patient_record_view` —
`POST /api/patient-records/validate/` — is the one place a candidate patient
record is checked against `clinical_core.schemas.validate_patient_record`
before it is persisted. `chat_intake` and `dag_extraction` (Phase 3/4) must
route through it (over HTTP from client-side JS, or in-process via
`clinical_core.views.validate_patient_record_payload` from server-side code)
rather than reimplementing validation or hand-rolling their own error
response — that keeps a schema violation looking identical no matter which
feature app produced the record. `review_portal` doesn't call it: it only
persists a `ReviewItem` (draft summary + rating), never a full patient
record.

## Design Notes

- Registry pattern for feature apps (mirrors `medical-imaging-suite`'s
  `BaseImagingTask` / `@register_task`).
- Both intake feature apps write into the same `clinical_core` schema so
  either can feed the one review queue — keep the schema-version
  compatibility policy (`current` / `older_supported` / `unknown`) from
  `clinical-ai-assistant`'s `docs/schema-versioning.md` intact.
- `clinical-ai-review-platform` already runs on SQLite with no external
  service required — keep that as the local/dev default; `DATABASE_URL`
  overrides for Postgres in deployment.
- No diagnostic claims: every demo/synthetic path must be explicitly labeled
  as a pipeline demo, not a clinical-decision tool (same disclosure pattern as
  `medical-imaging-suite`).
