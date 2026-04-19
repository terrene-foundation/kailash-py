# kailash-mcp Changelog

All notable changes to the Kailash MCP package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.5] - 2026-04-19 — oauth.py optional-extras gating (#514)

### Fixed

- **`oauth.py` module-level imports of optional extras (#514, PR #518)**: `kailash_mcp/auth/oauth.py` imported `aiohttp`, `PyJWT`, and `cryptography` at module scope. All three are declared optional under `[project.optional-dependencies] auth-oauth`. On a bare `pip install kailash-mcp` (no oauth extra), any `import kailash_mcp` transitioned to an `ImportError` through the auth sub-package. Fix: wrap the three imports in `try/except ImportError` with `None` fallbacks; add `_require_oauth_extras()` helper that raises a descriptive `ImportError` naming `pip install 'kailash-mcp[auth-oauth]'` when OAuth classes are instantiated without the extra. Module now imports cleanly without the oauth extra; OAuth classes fail loudly with an actionable error instead of silently. Aligns with `rules/dependencies.md` § "Declared = Gated Consistently" and cross-SDK parity with kailash-rs#417.

## [0.2.4] - 2026-04-14

### Fixed

- All 63 unit test warnings resolved (combined with kailash 2.8.6 release).

## [0.2.3] - 2026-04-08

### Added

- Initial platform server, auth JWT/OAuth, and MCP client/server implementations.
