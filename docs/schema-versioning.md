# Patient-record schema versioning policy

Every patient record (whichever intake app produced it) carries its own
`schema_version`. `clinical_core.schemas` classifies any version it sees into
one of three tiers:

- **current** — matches `LATEST_SCHEMA_VERSION`; validated as-is.
- **older_supported** — a version this suite no longer *writes* but still
  accepts on read; `validate_patient_record` runs `upgrade_to_latest` on it
  before validating, so an old record keeps loading even after the schema
  gains fields.
- **unknown** — anything else; rejected with a field-level error on
  `schema_version` rather than silently coerced or dropped.

## Adding a field (bumping the version)

1. Add a new `PatientRecordVX` class in `schemas.py` (don't edit the old
   version's class in place — records already validated under it must keep
   validating the same way).
2. Register it in `SCHEMA_REGISTRY["X.Y"]`, bump `LATEST_SCHEMA_VERSION`, and
   move the previous latest version into `OLDER_SUPPORTED_VERSIONS`.
3. Extend `upgrade_to_latest` with a branch that fills the new field's
   default when migrating an older-version record forward.
4. Update `configs/schema.yaml` to match (`tests/test_schemas.py` asserts the
   registry and the config file agree on which versions exist).

## Scope note

This schema and validator are a pipeline-demo data contract over
synthetic/public data — not a clinical-decision system. See README.md's
Disclosure section.
