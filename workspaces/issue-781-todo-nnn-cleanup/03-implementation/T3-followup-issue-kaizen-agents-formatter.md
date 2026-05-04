# GH issue — kaizen-agents auto-formatter modernization (follow-up to T3)

**FILED 2026-05-04 as terrene-foundation/kailash-py#815** (per `rules/upstream-issue-hygiene.md` MUST Rule 1, with explicit user approval). Body promoted to file-ready state at `/tmp/issue-T3-kaizen-agents-formatter.md` before submission — workspace identifiers stripped, counts re-verified against current main (89 black + 1804 ruff / 1608 fixable).

This file retained as institutional history of the discovery context (T3 of issue #781 cleanup).

## Title

`chore(kaizen-agents): apply Black + Ruff modernization sweep across packages/kaizen-agents/src/`

## Body

### Affected API

`kaizen_agents.*` — entire `packages/kaizen-agents/src/` source tree (no public API change).

### Symptoms

`black` and `ruff` report large pre-existing modernization drift across the package source:

- `uv run black --check src/` — 89 files would be reformatted (pre-existing line-length / trailing-comma drift).
- `uv run ruff check src/` — 1804 errors, of which 1608 are auto-fixable. Dominant categories: `Optional[X] → X | None` (PEP 604), `List[X] → list[X]` (PEP 585), unused imports, deprecated `typing` re-exports.

T3 of the issue #781 cleanup landed comment-only edits and deliberately rejected formatter changes from that PR's scope to keep the diff reviewable. The drift is pre-existing — no T1–T5 PR introduced it.

### Reproduction

```bash
cd packages/kaizen-agents
uv run black --check src/
uv run ruff check src/
# Both report the diagnostic counts above against the current main.
```

### Expected vs actual

- **Expected:** `uv run black --check src/ && uv run ruff check src/` returns clean against main.
- **Actual:** 89 Black-reformat candidates + 1804 Ruff diagnostics on main; pre-dates the issue #781 cleanup commits per `git log --oneline packages/kaizen-agents/src/ | head` (style-baseline commit was `b511f186` 2026-03-19, before the modernization drift accumulated).

### Severity

**LOW** — formatter / linter drift only; no runtime behavior change. Modernization improves grep / refactor ergonomics (PEP 604 union types render cleaner across files) and lets pre-commit hooks run cleanly without per-file ignore rules.

### Acceptance criteria

- [ ] `uv run black src/` applied and committed.
- [ ] `uv run ruff check --fix src/` applied (auto-fixable 1608/1804); remaining 196 manually triaged.
- [ ] `uv run black --check src/ && uv run ruff check src/` exits 0.
- [ ] Pre-commit hook configuration (`.pre-commit-config.yaml`) explicitly runs Black + Ruff on `packages/kaizen-agents/src/` so future drift is caught at commit time.
- [ ] No public API change (signatures, behavior, imports unchanged); commit body documents the no-functional-change guarantee.

### Discovery context (FOR HUMAN — strip before filing per upstream-issue-hygiene if filing publicly)

Surfaced during T3 of issue #781 TODO-NNN cleanup workstream. Black + Ruff would have reformatted the touched files; rejected from T3 PR to keep diffs comment-only. Filed as standalone follow-up.
