# Contributing to Kailash Python SDK

Thank you for your interest in contributing to the Kailash Python SDK. This document
covers everything you need to set up, develop, test, and submit contributions.

## Development Setup

See [CLAUDE.md](CLAUDE.md) for the full development environment reference, including
agent orchestration, framework selection, and quality gates.

### Quick start

1. Fork the repository on GitHub and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/kailash-py.git
   cd kailash-py
   ```

2. Install in editable mode with development dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Create a feature branch:

   ```bash
   git checkout -b feat/my-feature
   ```

## Code Style

We enforce consistent style with automated tools. Run these before every commit:

```bash
black src/ tests/
isort src/ tests/ --profile=black
ruff check src/ tests/
```

Or in one pass:

```bash
ruff format . && ruff check .
```

Lint rules are configured in `pyproject.toml` under `[tool.ruff]`.

## Testing

Kailash uses a 3-tier testing strategy.

| Tier            | Scope                                 | Command                     |
| --------------- | ------------------------------------- | --------------------------- |
| 1 — Unit        | Isolated, no external dependencies    | `pytest tests/unit/`        |
| 2 — Integration | Real infrastructure (Docker required) | `pytest tests/integration/` |
| 3 — E2E         | Full workflow scenarios               | `pytest tests/e2e/`         |

For Tier 1 (the default CI gate):

```bash
pytest tests/unit/ tests/parity/ tests/shared/ \
  -m "not (slow or integration or e2e or requires_docker)" \
  -v
```

**No mocking in Tier 2 or Tier 3 tests.** Use real infrastructure.
See [CLAUDE.md](CLAUDE.md) and `.claude/rules/testing.md` for the full testing policy.

### What "CI is green" actually means

Read this before treating a green `gh pr checks` as evidence about your change.
Each row below is a suite in `.github/workflows/unified-ci.yml`; "gates a merge"
means a failure turns the check red.

| Suite                                                        | Runs on                    | Gates a merge?                     |
| ------------------------------------------------------------ | -------------------------- | ---------------------------------- |
| Tier 1 — `tests/unit/`, `tests/trust/plane/unit/`, `tests/security/` | every PR, Python 3.11–3.14 | **Yes**                            |
| Tier 2 — `tests/tier2_integration/`                          | every PR, Python 3.11–3.14 | **Not yet** — non-blocking, but a failure now posts a loud annotation + job summary. Blocked on #2078; see below. |
| Root regression — `tests/regression/`, infra-free            | every PR, Python 3.12      | **Yes** (since #2002)              |
| Root regression — infra-marked                               | every PR (Postgres+Redis)  | **Yes** (since #2002)              |
| DataFlow unit + regression                                   | every PR                   | **Yes**                            |
| PACT                                                         | every PR                   | **Yes**                            |
| Type check (pyright)                                         | every PR                   | No — `continue-on-error`, see #73  |
| CUDA jobs (`test-kailash-ml.yml`)                            | manual dispatch only       | No — `continue-on-error` until the GPU runner is live |
| kailash-ml / kailash-align / trust / CodeQL                  | only when their paths change | Yes, when they run              |

Two consequences worth internalising:

- **A tier that is not listed is not run.** Notably `tests/integration/` and
  `tests/e2e/` are not part of the PR gate; run them locally when your change
  touches those paths.
- **Skipped is not passed.** A suite can be green because every test in it
  skipped for a missing service. When you add a step that depends on external
  infrastructure, pass `-rs` so the skips are visible, and check that the step
  can actually come out the other way.

#### Tier 2 is visible but not yet blocking

Until #2038 the Tier-2 step carried a bare `continue-on-error: true`, so a
Tier-2 failure — and, on Python 3.11/3.12, a 10-minute step **timeout** —
reported green with no signal at all.

It is still non-blocking, but it is no longer silent: a failure now emits a
`::error::` annotation and a job-summary block naming the count. **A green PR
check does not mean Tier 2 passed** — open the step log.

The reason it does not gate yet is #2078. Once `--maxfail=20` was lifted so the
suite could complete on CI for the first time, it reported 174 failed / 58
errors, dominated by 130 `RuntimeError: can't start new thread` and 90
`sqlite3.OperationalError: disk I/O error` — the paired signature of thread and
file-descriptor exhaustion, from one pre-existing leak rather than 232 separate
defects. The same suite is `2604 passed / 0 failed` on macOS, so a local green
is not evidence about the runner.

When #2078 is fixed: delete `continue-on-error` **and** the annotation step from
`unified-ci.yml`, and update this table. If a Tier-2 test fails after that, do
not restore the flag — quarantine that individual test with `xfail(strict=True)`
and a tracking issue, so it clears itself loudly when fixed.

## Commit Style

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description

Optional body explaining the why.

Optional footer (e.g., Fixes #123)
```

Valid types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:

```
feat(workflow): add conditional branching support
fix(nodes): resolve async timeout in HTTPRequestNode
test(dataflow): add integration tests for bulk operations
docs(readme): update installation guide for v1.0
```

## Pull Request Process

1. Ensure all tests pass: `pytest tests/unit/ tests/parity/ tests/shared/`
2. Run linting: `ruff format . && ruff check .`
3. Update `CHANGELOG.md` if your change is user-visible
4. Open a PR against `main` with the following sections:
   - **Summary** — what changed and why (1-3 bullet points)
   - **Test plan** — how to verify the change
   - **Related issues** — links to GitHub issues

PRs require at least one maintainer review before merge.

## Branch Naming

```
feat/add-oauth-support
fix/api-timeout-handling
docs/update-installation-guide
refactor/workflow-builder-simplification
test/dataflow-integration-suite
```

## Licensing and Intellectual Property

Kailash Python SDK is owned by [Terrene Foundation](https://terrene.foundation)
and licensed under the Apache License, Version 2.0.

By submitting a contribution, you agree that your contribution will be licensed
under the same terms. You retain copyright of your contributions.

Under Apache License 2.0, Section 3, each Contributor grants a perpetual,
worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent license
for claims necessarily infringed by their Contribution(s) alone or combined
with the Work. See [PATENTS](PATENTS) for details.

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Be respectful and professional
in all interactions. We maintain a welcoming environment for all contributors.

## Questions

Open an issue on GitHub or email info@terrene.foundation.
