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

Kailash uses a 3-tier testing strategy. **All 5708+ tests must pass before a PR
can be merged.**

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
