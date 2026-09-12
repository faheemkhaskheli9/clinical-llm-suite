# Clinical LLM Suite

> LLM, RAG & Agentic AI portfolio project — independent open-source implementation.
> This is an original, from-scratch build. It is not affiliated with, and does not
> contain any code, prompts, data, or business logic from, any employer or client.

![status](https://img.shields.io/badge/status-planned-lightgrey)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

## Combines

This is a flagship suite that will combine 3 related clinical-LLM repos into
one Django web app with all 3 features selectable from a single dashboard
UI — the same combined-suite pattern already used in this portfolio for
`video-analytics-suite`, `medical-imaging-suite`, and `trading-ai-suite`:

- [`clinical-ai-assistant`](../clinical-ai-assistant/) — patient conversational intake, structured extraction, RAG-backed clinical reasoning, doctor-facing summary
- [`clinical-summary-promptflow`](../clinical-summary-promptflow/) — schema-validated field extraction (vitals, symptoms, history) from a raw conversation, summarization node, PromptFlow-style DAG
- [`clinical-ai-review-platform`](../clinical-ai-review-platform/) — human-in-the-loop review queue for AI-generated clinical summaries (accept/reject/rate/comment, reviewer assignment, analytics)

These 3 already form a pipeline in spirit — intake/extract (`clinical-ai-assistant`
or `clinical-summary-promptflow`) feeds a summary into the review queue
(`clinical-ai-review-platform`) — but exist as 3 separate apps today. The 3
originals will get an archived banner + `status-archived` badge and move to
`E:\Projects\portfolio-archived-repos\` once this suite reaches feature
parity with each of them — no code or git history is deleted, only relocated.

## 1. Problem

A clinical-summary pipeline needs three things to be trustworthy end to end:
a way to turn a conversation into structured data (2 competing approaches
exist here — an LLM-chat-driven assistant, and a PromptFlow-style DAG), and a
human review layer that gates what gets trusted. Built as 3 unconnected
scaffolds, none of them can actually demonstrate "conversation in, reviewed
clinical summary out."

## 2. Architecture

```text
Dashboard (pick intake mode) ->
[Patient Chat Intake (assistant) | Structured DAG Extraction (promptflow)] ->
Structured Extraction (vitals/symptoms/history, schema-versioned) ->
Clinical Reasoning (RAG + LLM) -> Draft Summary ->
Review Queue (accept/reject/rate/comment) -> Approved Summary + Analytics
```

A shared `clinical_core` layer (the versioned patient-record schema from
`clinical-ai-assistant`'s `configs/schema.yaml` contract, the RAG reference
corpus ingest from `scripts/ingest.py`, and a summary/job model) sits
underneath 3 feature apps — chat intake, DAG extraction, and the review
portal — registered the same registry pattern used by this portfolio's other
suites. Both intake modes write to the same schema so either can feed the one
review queue.

## 3. Technology Stack

- Python, Django 5.x (feature-picker web app + review-queue models, matching
  `clinical-ai-review-platform`'s existing Django app)
- OpenAI / Azure OpenAI API (chat intake, summarization, RAG)
- Pydantic (schema validation — vitals/symptoms contracts already exist in
  `clinical-summary-promptflow` and `clinical-ai-assistant`)
- PostgreSQL in production, SQLite for local/dev (`DATABASE_URL` override) —
  `clinical-ai-review-platform` already defaults to SQLite with no external
  service required
- Redis/Celery if background summarization/RAG jobs are needed at scale

## 4. Feature List

- **Chat Intake** (from `clinical-ai-assistant`): conversational patient
  intake, dynamic follow-up questions, structured extraction, RAG-backed
  recommendations, doctor-facing summary
- **DAG Extraction** (from `clinical-summary-promptflow`): schema-validated
  field extraction (vitals, symptoms, history) with missing-value handling,
  summarization node, prompt evaluation
- **Review Portal** (from `clinical-ai-review-platform`): review queue,
  accept/reject actions, quality rating, reviewer comments, error taxonomy,
  reviewer assignment, role/permission groups, analytics dashboard
- Shared: one patient-record schema (versioned), one review queue fed by
  either intake mode

## 5. Implementation Plan

1. Phase 1: `clinical_core` shared app — port the versioned schema contract
   from `clinical-ai-assistant`'s `src/schemas/` + `configs/schema.yaml`, and
   the review-item model already implemented in `clinical-ai-review-platform`
2. Phase 2: Port `clinical-ai-review-platform`'s existing Django app (queue,
   `POST /api/review-items/`, `GET /api/review-items/`) as the review-portal
   feature app — it already runs on SQLite with no external service
3. Phase 3: Port `clinical-summary-promptflow`'s schema-validation CLI and DAG
   extraction into a feature app writing into `clinical_core`'s schema
4. Phase 4: Port `clinical-ai-assistant`'s chat intake + RAG layer (reusing its
   MedlinePlus/openFDA/MedQuAD ingest pipeline) into a third feature app
5. Phase 5: Wire both intake feature apps to submit into the shared review
   queue; archive the 3 original repos (banner + badge, move to
   `portfolio-archived-repos`) once parity is confirmed

## Task Tracking

Work will be broken into phase-tagged user stories tracked as GitHub Issues,
not in this file. Implement Phase 1 issues first (later phases depend on it).
When you start one, add label `status:in-progress`. When you finish, close it
referencing the commit (e.g. `git commit -m "... Closes #4"`) and push.

## 6. Repository Structure

```text
clinical-llm-suite/
├── README.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── .env.example
├── docker/
├── docs/
│   ├── architecture.md
│   └── evaluation.md
├── src/
├── tests/
├── configs/
├── scripts/
├── notebooks/
├── examples/
├── assets/
└── .github/
    └── workflows/
```

## 7. Setup

```bash
git clone <this-repo-url>
cd clinical-llm-suite
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt   # or: pip install -e .
cp .env.example .env              # fill in API keys / config
```

## 8. Dataset

The RAG reference corpus (ported from `clinical-ai-assistant`) is pulled live
from public sources — MedlinePlus Health Topics, openFDA Drug Label API, and
MedQuAD (CC BY 4.0) — nothing vendored, only fetched and cached locally. No
proprietary, employer-owned, or client-identifiable data is used in this
project.

## 9. Training / Execution

```bash
# Once Phase 1 lands:
python manage.py migrate
python manage.py runserver   # open http://127.0.0.1:8000/ and pick a feature
```

## 10. Evaluation

Document evaluation metrics and how to reproduce them here (see
`docs/evaluation.md`).

## 11. Results

_To be filled in as the implementation progresses — screenshots, metrics
tables, and sample outputs go here._

## 12. API

_If this project exposes an API, document the main endpoints here (or link to
auto-generated OpenAPI docs, e.g. `/docs` for FastAPI)._ `clinical-ai-review-platform`'s
existing `POST /api/review-items/` / `GET /api/review-items/` endpoints are
the starting point for Phase 2.

## 13. Docker

```bash
docker build -t clinical-llm-suite .
docker run -p 8000:8000 clinical-llm-suite
```

## 14. Tests

```bash
pytest tests/
```

## 15. Limitations

- This is a from-scratch, independent recreation built for portfolio purposes.
- Performance numbers, once added, are based on public datasets and are not
  representative of any production system's real-world results.
- Scaffold stage: no code has been ported from the 3 source repos yet — see
  §5 Implementation Plan. This is not a diagnostic or clinical-decision tool.

## 16. Future Work

- Port each source repo's existing Phase-1 code (all 3 have some already —
  see §5) rather than rewriting from scratch.
- Expand evaluation coverage and add CI-based regression checks.
- Track open items as GitHub Issues.

## 17. Disclosure

This repository is an **independent open-source recreation inspired by the
kind of production systems I have worked on professionally**. It contains no
employer or client source code, prompts, datasets, credentials, architecture
diagrams, or business logic. All code, data, and documentation here are
original or built on publicly available datasets and open-source tools.

---
_Last updated: 2026-09-12_
