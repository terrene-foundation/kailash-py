---
id: W6-001
title: Strip hardcoded model strings from kaizen CoreAgent + GovernedSupervisor
priority: P1
estimated_sessions: 1
depends_on: []
blocks: []
status: pending
finding_id: F-D-02, F-D-50
severity: HIGH
spec: specs/kaizen-core.md, specs/kaizen-agents-governance.md
domain: kaizen
specialist: kaizen-specialist
wave: W1
---

## Why

W5-D found `CoreAgent` hardcodes `model="gpt-3.5-turbo"` (F-D-02) and `GovernedSupervisor` hardcodes `model="claude-sonnet-4-6"` (F-D-50). Both are direct violations of `rules/env-models.md` (.env source-of-truth) — model names MUST come from `.env`, not Python literals.

## What changes

- Replace `model="gpt-3.5-turbo"` and `model="claude-sonnet-4-6"` with `os.environ.get("KAIZEN_DEFAULT_MODEL")` (raise `EnvModelMissing` if unset).
- Add Tier-1 unit tests: env-var-present → uses env value; env-var-missing → typed error.
- Update `.env.example` to document `KAIZEN_DEFAULT_MODEL`.

## Capacity check

- LOC: ~50 load-bearing (2 file edits + tests + .env.example)
- Invariants: 3 (env-var precedence, typed-error contract, no Python literal regression)
- Call-graph hops: 2
- Describable: "Replace 2 hardcoded model literals with env-var lookups; add tests; update .env.example."

## Spec reference

- `specs/kaizen-core.md` § CoreAgent default model
- `specs/kaizen-agents-governance.md` § GovernedSupervisor default model
- `rules/env-models.md` § ".env Is Single Source of Truth"

## Acceptance

- [ ] No hardcoded `gpt-*`, `claude-*`, `model="..."` literal in `packages/kailash-kaizen/src/kaizen/core/` or `kaizen/agents/governance/`
- [ ] Env-var-missing raises typed error with actionable message
- [ ] Tier-1 tests at `tests/unit/test_kaizen_default_model_env.py`
- [ ] `.env.example` documents `KAIZEN_DEFAULT_MODEL`
- [ ] CHANGELOG entry in kailash-kaizen

## Dependencies

- None (independent quick win)

## Related

- Finding detail: `04-validate/W5-D-findings.md` F-D-02 + F-D-50
- Rule: `rules/env-models.md`
