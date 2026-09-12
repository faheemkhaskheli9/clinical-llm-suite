# Evaluation Notes: Clinical LLM Suite

## Metrics

- **Chat Intake / DAG Extraction**: structured-extraction field-level
  precision/recall against labeled synthetic conversations, missing-value
  handling correctness, RAG answer relevance (LLM-as-Judge or human-rated)
- **Review Portal**: reviewer-agreement rate, % accepted vs. rejected vs.
  flagged, time-to-review, error-taxonomy distribution

## Reproducing Results

```bash
python -m src.evaluate --config configs/eval.yaml
```

## Result Log

| Date | Config | Metric | Value | Notes |
|------|--------|--------|-------|-------|
|      |        |        |       |       |
