---
type: DECISION
slug: codify-env-models-carveout-to-proposal
created: 2026-06-11T13:39:31Z
---

# /codify — env-models provider-intrinsic carve-out appended to proposal pipeline

## Decision

Appended the FNEW-5 / env-models provider-intrinsic default-constant carve-out
learning to `.claude/.proposals/latest.yaml` as the final `changes:` entry
(BUILD→loom proposal, `origin: build`, `classification_suggestion: global`) and
RESET the proposal `status: reviewed → pending_review` per `artifact-flow.md`
§ "Reset Status on Append".

## Why this, and why now

Prompted by the user catching that the earlier "no /codify needed" call was made
without reading the last-codification artifact. On reading
`.claude/.proposals/latest.yaml` (2026-05-18, #1086, then-status `reviewed`,
18 changes entries + `deferred` + `append_session`), confirmed the env-models
carve-out was **not** already captured — so this is a genuine new entry, not a
duplicate. The user then asked to /codify it so it rides the Gate-1 pipeline
rather than living only as loom#485.

## Scope (deliberately narrow)

- **No new rule/skill/agent authored in this repo.** The carve-out itself is a
  loom-owned `env-models.md` edit, already landed in loom canonical via
  loom#485. This session only records the proposal-pipeline provenance.
- **No Trust Posture Wiring authored** — the carve-out is a narrowing of an
  existing grandfathered rule (no new MUST clause, no enforcement surface, no
  new violation class). Noted in the proposal entry for the loom-side processor.
- **Codify lease:** exempt — no `.claude/operators.roster.json`, so the
  multi-operator substrate is a no-op by construction. Edits land on branch
  `codify/esperie-2026-06-11-env-models` per the codify branch convention.
- **No `learning-codified.json` digest cycle** — this is a targeted append, not
  a full session-knowledge extraction; the digest is unchanged.

## Mechanics note (for the next session)

The proposal YAML has top-level keys `changes`, `deferred`, `append_session`
(in that order), so a new `changes` entry MUST be inserted before the
`deferred:` key — NOT appended at EOF (EOF belongs to the `append_session`
scalar). A prettier PostToolUse formatter reflows the file on every Edit-tool
write (col-0 → col-2 sequence reindent), so the edit was applied via a Python
text pass (validated with `yaml.safe_load`) to keep the diff minimal: 45
insertions, 1 deletion; 19 changes entries; `deferred`/`append_session` intact.

## Receipts

- Proposal: `.claude/.proposals/latest.yaml` (entry `artifact: env-models`)
- loom#485 (esperie-enterprise/loom) — the carve-out request
- Cross-repo filing receipt: journal/0012
- kailash-py PRs #1292 (FNEW-5 fix), #1294 (kaizen 2.26.0 release)
- Deploy record: `deploy/deployments/2026-06-11-kaizen-v2.26.0-fnew5.md`
