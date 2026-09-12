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
  summarization node
- `review_portal` feature app — ported from `clinical-ai-review-platform`'s
  already-implemented Django queue (`POST/GET /api/review-items/`)

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
