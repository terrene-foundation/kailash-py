---
type: DECISION
status: final
created: 2026-04-20
session_id: clean-release-2026-04-20
---

# /codify — 2 rule additions from clean-release cycle 2026-04-20

## Context

Session resolved all 5 outstanding GH issues surfaced by the earlier `/redteam` sweep (2026-04-20 morning) in a single autonomous cycle:

- **#546** — ONNX bridge matrix completion (torch/lightning/catboost) → kailash-ml 0.13.0
- **#547** — `km.doctor()` + `km-doctor` console script → kailash-ml 0.13.0
- **#548** — `km.track()` Phase 6 (NotImplementedError → async context manager) → kailash-ml 0.13.0
- **#549** — `kailash-trust` package delete + PyPI yank
- **#550** — `quote_identifier` port from DataFlow into core → kailash 2.8.10

Four merged PRs (#551, #552, #553), two published tags (v2.8.10, ml-v0.13.0), one PyPI yank.

## Decision

Append two rule additions to `.claude/.proposals/latest.yaml` for loom Gate-1 review:

1. **`rules/orphan-detection.md` §4a** — Stub Implementation MUST Sweep Deferral Tests In Same Commit. Mirror of existing §4 (API removal sweeps tests). The implementation-author grep (`grep -rln 'NotImplementedError.*<symbol>' tests/`) costs ~1s and catches the orphan before CI starts.

2. **`rules/agents.md` §: MUST Parallel-Worktree Package Ownership Coordination** — when N parallel worktree agents touch the same sub-package, ONE is designated version-owner; sibling prompts include a verbatim exclusion clause for `pyproject.toml` / `__init__.py::__version__` / `CHANGELOG.md`. Prevents merge-time version-race with silent CHANGELOG drop.

Also updated the proposal's existing 5 implementation followups (km.track Phase 6, ONNX matrix, km.doctor, kailash-trust orphan, dialect quote_identifier) to `COMPLETE` via a `release_completion_update` block. loom Gate-1 reviewer can mark them done.

## Evidence

### Rule 1 (orphan-detection §4a) — recovered failure

kailash-ml 0.13.0 release PR #552 bundled #546+#547+#548. Agent 2 implemented `km.track()` replacing the `NotImplementedError` stub. CI surfaced the paired deferral test `test_km_track_deferral_names_phase` as failing across Base (Python 3.10/3.11/3.12/3.13/3.14) — 5 matrix jobs red simultaneously. Fix: delete the deferral test (`release/kailash-ml-0.13.0` commit `ef8751c5`). Cost: one extra CI cycle + one follow-up commit at release gate.

### Rule 2 (agents parallel-worktree ownership) — positive evidence

Three parallel agents launched with worktree isolation. Agent 1 designated version-owner for kailash-ml pyproject.toml + CHANGELOG. Agent 2's prompt included the verbatim exclusion: _"COORDINATION NOTE: A parallel agent is resolving #546 (ONNX bridge matrix) in another worktree and will ALSO bump version to 0.13.0 + write CHANGELOG. To avoid merge conflicts, you (this agent) MUST NOT edit packages/kailash-ml/pyproject.toml, packages/kailash-ml/src/kailash_ml/**init**.py::**version**, or packages/kailash-ml/CHANGELOG.md."_ Agent 3 worked on a different package (core kailash/ 2.8.10). Integration step: one trivial CHANGELOG.md root-file conflict, zero conflicts on package pyproject.toml. Without the exclusion clause, Agents 1 and 2 would have independently written `## [0.13.0]` headers and racey `version = "0.13.0"` fields.

## Cross-SDK applicability

Both rules apply to Rust (kailash-rs) with minor mechanism differences:

- **Rule 1 (§4a mirror)**: Rust `todo!()` / `unimplemented!()` macros are the scaffold-equivalent of `NotImplementedError`. Scaffold tests may `should_panic` on the un-implemented path; implementation-author must sweep them in the same commit.
- **Rule 2 (parallel ownership)**: Rust `Cargo.toml [package] version` and per-crate CHANGELOG files exhibit the same race. The ownership contract is build-system-independent.

Classification_suggestion: `global` for both.

## Also logged

- Pre-existing rule-file size overflow: `rules/orphan-detection.md` (240 lines) and `rules/agents.md` (288 lines) both exceed the 200-line cap in `rules/rule-authoring.md` MUST Rule. Session 2026-04-20 morning notes already flagged this for future extraction into guides/skills. Not blocking this proposal.
- `/wrapup` deferred to end of session.

## Artifacts

- Commits applied: none yet (rule files modified locally; commit pending).
- Proposal: `.claude/.proposals/latest.yaml` — appended 2 new `changes:` entries + `release_completion_update` block + updated `summary_note`.
- Next session handoff: loom Gate-1 reviews the 5 rule additions (3 from morning + 2 from this session) and the `release_completion_update` marker.
