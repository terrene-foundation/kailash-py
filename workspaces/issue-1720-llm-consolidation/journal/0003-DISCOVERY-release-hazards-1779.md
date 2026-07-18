# DISCOVERY — three release hazards from the #1779 governance_required cycle

Surfaced 2026-07-18 while releasing kailash 2.54.0 / kailash-kaizen 2.35.0 /
kaizen-agents 0.10.0. All three are reusable release-engineering lessons; #1 is
general (loom-canonicalization candidate), #2/#3 are monorepo-CI/PyPI-specific.

## Hazard 1 — a fail-closed gate that imports a same-release symbol needs a pin floor at that release (GENERAL)

`kaizen.llm.governance_gate` does `from kailash import is_governance_required`
(new in kailash **2.54.0**) on **every** LlmClient/Agent construction, and it is
**fail-closed**: if the import raises, `active = True` → refuse. kaizen 2.35.0
pinned `kailash>=2.50.0`. That combination means an **old-kailash (<2.54.0) +
new-kaizen** install resolves the import to `ImportError` → the gate refuses
**every** egress **even under the default OFF posture** — a silent hard break
for a partial upgrade.

- **Rule:** when a guard imports a symbol added in the SAME coordinated release
  AND fails closed on import error, the manifest pin MUST floor at that release
  (`kailash>=2.54.0`, not `>=2.50.0`). This is stricter than the usual
  "declared = imported" (`dependencies.md`) because the fail-closed behavior
  turns a loose floor into a runtime refusal, not just an `ImportError` at the
  call site.
- **Fix landed:** PR #1804 — bumped kaizen `kailash>=2.50.0`→`>=2.54.0` and
  kaizen-agents `kailash-kaizen>=2.25.1`→`>=2.35.0`.
- **Loom candidate:** a `dependencies.md` clause — "a fail-closed guard importing
  a same-release symbol floors its pin at that release."

## Hazard 2 — local editable sibling MUST be installed before any package that pins it (monorepo CI)

`test-kailash-kaizen.yml` installed editable `kaizen-agents` **before** editable
`kailash-kaizen`. When uv installed kaizen-agents and saw `kailash-kaizen>=2.35.0`,
it resolved that pin against **PyPI** (latest 2.34.2) — "no solution found" —
because the local editable 2.35.0 was not yet installed. Latent before the pin
bump (the old `>=2.25.1` was satisfiable from PyPI, so it silently pulled a PyPI
kaizen that the later editable install overwrote).

- **Rule:** in monorepo CI, install a local editable package **before** any
  sibling that pins it, so the pin resolves against the in-repo version.
- **Fix landed:** PR #1804 — reordered the install step; added a NOTE comment.
  `example-validation.yml` already had the correct order.

## Hazard 3 — TestPyPI validation of interdependent minors needs dependency-order dispatch + `--index-strategy unsafe-best-match`

Validating three interdependent minors on TestPyPI (the deployment.md MUST for
minors) required two non-obvious things:

1. **Dependency-order dispatch** — publish kailash 2.54.0 to TestPyPI first so
   kaizen 2.35.0's `kailash>=2.54.0` pin resolves there (not against prod PyPI,
   which lagged at 2.53.0), then kaizen, then kaizen-agents.
2. **`--index-strategy unsafe-best-match`** — the package under test lives on
   TestPyPI but its third-party deps live on prod PyPI; uv's default first-index
   strategy fails to resolve across the two indexes. `unsafe-best-match` makes
   uv consider all indexes for all packages.

Verify command shape:

```
uv pip install --refresh --index-strategy unsafe-best-match \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "<pkg>==<ver>"
```

Also: a verify loop must capture uv's real exit code — `uv pip install ... | tail`
masks it (pipe exit = tail's), so a failed install can print a false "OK".

- **Rule:** TestPyPI validation of interdependent packages = dependency-order
  dispatch + `unsafe-best-match` + real-exit-code capture.
- **Loom candidate:** a `deployment.md` TestPyPI-validation clause for
  interdependent multi-package releases.

## Also confirmed this cycle

- PyPI `info.version` cache lag: kaizen showed 2.34.2 for minutes after 2.35.0
  published; the version-specific `/pypi/<pkg>/<ver>/json` endpoint + a clean
  install both confirmed 2.35.0 live (matches `build-repo-release-discipline.md`).
