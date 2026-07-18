# DECISION — /codify for the #1779 release cycle (docs + knowledge capture)

Date: 2026-07-18. Repo class: BUILD (`name = "kailash"`). Coordination OFF
(un-enrolled public repo) → no codify lease needed.

## What was codified

1. **`docs/core/trust.rst`** — added a "Governance-Required Posture" section
   documenting the new public API (`is_governance_required` /
   `set_governance_required` / `UngovernedEgressRefused`, `KAILASH_GOVERNANCE_REQUIRED`
   env, `ungoverned=True` opt-out), the resolution order, the enforcement
   chokepoints, and the honest **non-coverage** note (legacy providers /
   multimodal / standalone azure — tracked #1803). Mandatory Step-5 user doc for
   the new public API; every symbol verified live this session.

2. **`CHANGELOG.md`** — moved the shipped `[Unreleased]` block to a dated
   `## [2.54.0] - 2026-07-18` section (release hygiene the tag-publish workflow
   does not do). Both the #1779 Added and the legacy-`from_env` Deprecated entry
   (shipped kaizen 2.32.0, 2026-07-14 — also stale under Unreleased) moved; each
   entry self-attributes its version/issue in-text.

3. **`docs/index.rst` + `docs/getting_started.rst`** — fixed stale SDK version
   badges `0.12.5` → `2.54.0` (pre-existing drift; `documentation.md` requires
   these track pyproject on a version bump).

## Knowledge capture

The three release hazards are captured in `0003-DISCOVERY-release-hazards-1779.md`
(read by the next `codify-backlog` cycle). Hazard #1 (fail-closed guard importing
a same-release symbol → pin floors at that release) and Hazard #3 (interdependent-
minors TestPyPI validation) are flagged as loom-canonicalization candidates for a
future `dependencies.md` / `deployment.md` clause. Not appended to the 96KB
`latest.yaml` this cycle (append risk vs. marginal value; the journal is the
reliable inheritance path).

## Violations triage (16 unaddressed since anchor)

- **15× `repo-scope-discipline/MUST-NOT-1`** — the hook flags every `gh --repo`
  call. On inspection: (a) `--repo terrene-foundation/kailash-py` from within
  kailash-py is the **canonical current repo**, not cross-repo (hook
  over-flags the `--repo` flag); (b) `--repo esperie-enterprise/kailash-rs`
  entries are **authorized cross-SDK filings** with journaled grants (this
  session's rs#1932/#1933 + prior sessions' rs#1881). No rule change warranted;
  these are hook false-positives / grant-backed actions.
- **1× `git/commit-message-claim-accuracy` [advisory]** — a `/sweep`+`/wrapup`
  workspace commit subject flagged for claim language; advisory, workspace-only,
  no action.

## Anchor

`learning-codified.json::last_codified` advanced to 2026-07-18 to bound the next
cycle's delta. The 2211-item backlog is dominated by test_pattern/framework_selection
telemetry (not individually codify-actionable); the actionable delta was the
release-cycle docs + the three hazards above.
