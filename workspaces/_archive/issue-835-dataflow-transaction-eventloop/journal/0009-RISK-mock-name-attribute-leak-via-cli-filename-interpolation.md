---
type: RISK
date: 2026-05-06
created_at: 2026-05-06T05:09:53Z
author: agent
session_id: 240e50b8-d682-41ee-ae69-438916114a12
session_turn: post-release
project: kailash-py
topic: Mock(name="X") repr leaked through CLI filename interpolation; production lacked trust-boundary validation
phase: redteam
tags:
  [
    dataflow,
    cli,
    filename-validation,
    security,
    mock-anti-pattern,
    path-traversal,
    defense-in-depth,
  ]
---

# `dataflow generate docs` interpolated `workflow.name` into a filesystem path with zero validation; a Mock-leak vector wrote 108 orphan files to disk

## What was discovered

The CLI `dataflow generate docs` subcommand at `packages/kailash-dataflow/src/dataflow/cli/generate.py` interpolated `workflow.name` directly into a filesystem path via `f"{workflow.name}.md"`. No type check, no allowlist, no path-traversal guard. Production code trusted the caller's `workflow.name` to be a benign string.

The originating leak was a Mock-object repr — `<Mock name='test_workflow.name' id='0x...'>` — escaping `tests/unit/cli/test_generate_command.py`. Root cause: `Mock(name="X")` sets the Mock's _repr-name attribute_, NOT the `.name` attribute on the mock object. When test code later accessed `mock.name`, it got back a _child Mock_, which f-strings to its repr. So `f"{workflow.name}.md"` produced filenames like `<Mock name='test_workflow.name' id='0x140f2a8f0'>.md`. Over the period 2026-04-15 → 2026-05-06, 108 such orphan files accumulated:

- 107 in `docs/`
- 1 in `packages/kailash-dataflow/docs/`

## Why this is a RISK, not a DISCOVERY

The `Mock(name="X")` anti-pattern is the _trigger_. The RISK is the production path: any caller passing a non-string, path-traversal substring, or filesystem-unsafe character would have had the same effect — including production callers, not just tests. The Mock leak is the visible symptom of a missing trust-boundary check in CLI code. Adversarial input would have written to `/etc/`, `~/.ssh/`, or similar.

## Two-layered fix shipped in 2.7.8 (commit `a17fa57d`)

Per autonomize directive ("root cause over symptom"), the fix had two layers:

**Layer 1 — production validates regardless of test correctness** (the durable defense):

- New `packages/kailash-dataflow/src/dataflow/utils/filenames.py` exports `safe_workflow_filename(name, ext)` and `WorkflowNameError(ValueError)`.
- Strict allowlist: `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`
- Rejects path-traversal substring `..` even if other chars are allowlisted
- Logs at WARN with sha256[:8] fingerprint per `rules/observability.md` Rule 8 (raw input never echoed)
- Error messages carry actionable Mock-anti-pattern hints ("if your `.name` looks like `<Mock name=...>`, see test/unit/CLAUDE.md Tier-1")

**Layer 2 — test correctness** (closes the proximate vector):

- Test now constructs the Mock via `_make_workflow_mock()` helper that does post-construction `mock.name = "X"` (the form that actually sets the attribute)
- Test uses `tmp_path` for `--output-dir` per `tests/unit/CLAUDE.md` Tier-1 filesystem-isolation contract — `Path.write_text` is NOT caught by `patch("builtins.open", mock_open())`

Plus regression coverage:

- 52 Tier-1 tests for `safe_workflow_filename` — 9 accept, 23 reject (path-traversal, control chars, shell metacharacters, Unicode bidi, Mock-repr, non-string), 9 ext validation, error/log hygiene
- 1 Tier-1 regression in `test_generate_command.py` exercising the historical Mock-leak vector end-to-end through the Click runner; asserts `exit_code == 2` and zero `<Mock` files written

## Why this surfaced inside the #835 release cycle

The 108 orphan files were noticed during the post-release sweep enumeration this session. They had accumulated silently because the Tier-1 test claimed to exercise filename generation, the test passed, and CI never noticed the orphan files because they were committed under `docs/` (and ignored by .gitignore patterns until a manual `ls`). Same-shard fix-immediately disposition per `rules/autonomous-execution.md` Rule 4 (security-reviewer-style finding inside the in-flight release scope).

## Consequences

- kailash-dataflow 2.7.7 → 2.7.8 (patch; pyproject + `__version__` + CHANGELOG bumped atomically per `rules/zero-tolerance.md` Rule 5 + build-repo-release-discipline)
- 108 orphan `<Mock...>.md` files purged from `docs/` and `packages/kailash-dataflow/docs/`
- The `safe_workflow_filename` helper is now the canonical entry point; future CLI subcommands taking user-supplied identifiers must route through it (or analogous helpers in the same module)
- Workspace journal 0005 §F4 disposition recorded
- 2.7.8 shipped before 2.7.9 (#835 fix) — both released same day, 2.7.8 first

## Follow-up

- Audit `gh search code "f\".*workflow.name.*\"" --owner terrene-foundation` for sibling sites that interpolate user identifiers directly into filenames or paths
- Document the `Mock(name="X")` anti-pattern in `tests/unit/CLAUDE.md` so the test-side trap is caught at code-review time
- Consider extending the trust-boundary helper module to other identifier classes (model names, table names, env names) — same pattern, same risk

## For Discussion

- Counterfactual: would 108 orphan files have been noticed without the post-release sweep? CI never failed; tests passed; the leak was silent. The trigger was a manual `ls docs/` during sweep enumeration. What other silent-accumulation failure modes exist behind passing tests?
- Specific data: 108 files over ~3 weeks. The rate (~5/day) suggests every CI run was leaking. Why didn't `git status` after CI runs surface the drift sooner — was `docs/` `.gitignore`d or just always-clean by luck?
- The fix introduces `WorkflowNameError(ValueError)` as a new exception class. Should it instead be `dataflow.errors.IdentifierError` so future helpers (model names, env names) share the type, or is workflow-name-specific the right granularity?
