---
id: W6-020
title: Numbered migration for _kml_automl_trials table
priority: P0
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: W6.5-followup-3
severity: HIGH
spec: specs/ml-automl.md, specs/infra-stores.md
domain: ml + infra
specialist: ml-specialist
wave: W7
---

## Why

W6.5 review § AutoML MED-3 + commit `f21e9844` follow-up #3: `_kml_automl_trials` table is created via first-use DDL ("table-create-failed → WARN → fall back to in-memory"). That's degraded-mode for development; production should land via numbered migration per `rules/schema-migration.md` Rule 1.

## What changes

- Create numbered migration `packages/kailash-ml/migrations/NNN_create_kml_automl_trials.py` per `rules/schema-migration.md`.
- Migration creates table + indexes per the DDL currently inline in `automl/engine.py:296-348`.
- Update engine to detect "table missing" and raise `MigrationRequiredError` instead of silently creating + WARN.
- Add Tier-2 test: fresh DB without migration → typed error; after migration → engine works.
- Strip the inline DDL from engine module.

## Capacity check

- LOC: ~250 (migration + engine refactor + Tier-2 test)
- Invariants: 4 (migration idempotent, engine errors typed, Tier-2 green, DDL not inline)
- Call-graph hops: 3
- Describable: "Move _kml_automl_trials DDL into a numbered migration; engine errors typed if missing."

## Spec reference

- `specs/ml-automl.md` § 8A.2
- `specs/infra-stores.md` § Migration system
- `rules/schema-migration.md` Rule 1

## Acceptance

- [ ] Migration file exists with version + up/down
- [ ] Engine raises `MigrationRequiredError` if table absent
- [ ] No inline `CREATE TABLE` in `automl/engine.py`
- [ ] Tier-2 test exercises both states (pre/post migration)
- [ ] CHANGELOG entry

## Dependencies

- None

## Related

- Source: commit `f21e9844` § Wave 6 follow-ups
- Review: `04-validate/W6.5-v2-draft-review.md` AutoML MED-3
