# Red-Team Convergence Verdict — Session PRs #502–#508

Date: 2026-04-19. Protocol: `rules/autonomous-execution.md` + `/redteam` against PRs #502–#508.

## Verdict: NOT CONVERGED — 2 HIGH findings, 1 MED finding.

All collection gates pass (20,900 tests collected across four packages, 0 errors). All promised public symbols exist at their cited paths and import cleanly. Main bundle imports `nexus`, `kailash_ml`, `kaizen.llm` with no ImportError. However two regressions surface on execution.

---

## HIGH-1 — Nexus HTTP clients are orphans by `orphan-detection.md` MUST Rule 1

**Scope:** PR #505 `HttpClient` + `ServiceClient`, PR #507 `TypedServiceClient`.

**Evidence:** Grep of `packages/kailash-nexus/src/` for any production call site that constructs or references `HttpClient(`, `ServiceClient(`, `TypedServiceClient(` returns **zero** results outside the defining modules themselves. The classes are exported on `nexus.__all__` (lines 170–188) and re-import inside each other (TypedServiceClient extends ServiceClient), but no Nexus hot-path code — handler, middleware, engine, transport — ever instantiates them.

**Rule citation:** `rules/orphan-detection.md` MUST Rule 1: "Any attribute exposed on a public surface that returns a `*Client` / `*Service` MUST have at least one call site inside the framework's production hot path within 5 commits of the facade landing. The call site MUST live in the same package as the framework, not just in tests or downstream consumers."

**PR #505 body acknowledges:** "Downstream aegis migration (11 httpx sites in `src/aegis/services/`) happens after merge." This is exactly the Phase-5.11 pattern the rule exists to prevent — public symbol shipped, consumers expected to adopt later, framework itself never calls the class.

**Remediation:** Either (a) wire one Nexus-internal caller (e.g. OpenAPI generator's fetch path, webhooks outbound delivery, SSE upstream proxy) to `HttpClient` in a follow-up PR within 5 commits, or (b) move the three clients to a `nexus.outbound` / `kailash.http` sibling namespace not advertised as a Nexus facade until a consumer lands.

**Severity rationale:** HIGH, not CRITICAL. The classes are hand-crafted primitives with no security promise that bypassing them defeats; the risk is semantic drift (downstream aegis migration happens against a class never exercised by Nexus's own test matrix against its own server).

---

## HIGH-2 — `register_estimator` LogRecord collision breaks the unit suite under cross-module test load

**Scope:** PR #506 — `packages/kailash-ml/src/kailash_ml/estimators/registry.py:63–66, 79–82`.

**Evidence:** Running `pytest packages/kailash-kaizen/tests/unit/llm/test_embed_shapers.py packages/kailash-ml/tests/unit/test_register_estimator.py` (the two test files merged in this session) yields:

```
FAILED test_register_as_decorator           KeyError: "Attempt to overwrite 'module' in LogRecord"
FAILED test_register_as_function_then_compose
FAILED test_unregister_round_trip
FAILED test_register_idempotent
FAILED test_pipeline_with_registered_final_step_fits_and_predicts
FAILED test_feature_union_with_registered_transformer
FAILED test_column_transformer_with_registered_transformer
FAILED test_registered_class_missing_protocol_still_rejected
8 failed, 29 passed in 0.96s
```

Root cause: `registry.py` calls `logger.debug("...", extra={"module": key[0], "qualname": key[1]})`. `"module"` is a reserved LogRecord attribute. Python's stdlib logging (3.13) raises `KeyError` the moment a second test in the same process installs a caplog handler that materializes the extra dict — which the kaizen tests do via their conftest logging setup. In isolation the test file is green (propagate chain short-circuits before extra-expansion), which is why PR #506 CI passed.

**Rule citation:** `rules/observability.md` MUST Rule 1 + stdlib contract. `logger.debug` with reserved-name extras is effectively a stub (`rules/zero-tolerance.md` Rule 2 "fake encryption / fake observability" pattern) — the debug line silently works on PR CI, silently breaks the moment another test file in the same process triggers record materialization.

**Remediation:** Rename the `extra` keys in both `register_estimator` and `unregister_estimator` to non-reserved names: `{"registry_module": ..., "registry_qualname": ...}`. Or use a non-`extra` form: `logger.debug("register module=%s qualname=%s", key[0], key[1])`. Add a regression test that runs `register_estimator` under `caplog` to prove the extras don't collide.

**Severity rationale:** HIGH. The symptom is non-deterministic across test orderings, a CI shard schedule change can flip the suite red overnight, and the same `extra={"module": ...}` pattern would silently misfire in production any time an aggregator handler materializes the record.

---

## MED-1 — PR #505 + #507 tests do not prove the production wiring contract

**Scope:** PRs #505 / #507 claim "Tier 2 integration tests" against `pytest_httpserver`. That proves the client hits a real HTTP server. It does NOT prove the Nexus framework ever calls the client, which is the exact distinction `facade-manager-detection.md` MUST Rule 1 draws.

**Remediation:** Either (a) accept the "primitive, not facade" framing and delete the clients from `nexus.__all__` until a Nexus internal consumer wires them (the Phase-5.11 deletion pattern), or (b) add one Tier 2 wiring test that exercises a Nexus handler whose implementation calls `HttpClient`. Option (b) is forward-compatible with the aegis adoption plan.

---

## Disposition of other scan paths

- **pip check** — blocked locally by missing `pip` in venv (`python -m pip` returns "No module named pip"). Not a finding against these PRs; separate venv hygiene task. Note: this also means "Declared=Imported" verification (dependencies.md) cannot be re-run in this session; trusted PR bodies.
- **Collection gate** — 20,900 tests collected across 4 packages, 0 errors. Satisfies `orphan-detection.md` MUST Rule 5.
- **Spec-compliance assertion tables** — PRs #502, #503, #504, #508 fully compliant. PRs #505, #506, #507 have the findings above.
- **SSRF / injection surface** — `HttpClient` SSRF + header validation code reviewed at class level (correct intent, correct order per PR body "NN1" clause), not exercised end-to-end against a simulated IMDS attacker. Rule 1 MUST-rules met at author level; Tier 2 integration against pytest-httpserver covers what it can. No new finding.
- **Log hygiene** — no new PII/secret fields introduced by the session PRs (spot-checked `http_client.py` + `service_client.py` for `logger.` calls; bearer tokens scrubbed, URLs fingerprinted per PR body).

## Convergence requirement

Two more clean rounds after HIGH-1 and HIGH-2 are resolved. The `register_estimator` LogRecord collision is a one-line fix; the Nexus-clients orphan question needs a human decision between "wire an internal caller now" and "move to a non-facade namespace."

Do NOT fix in this session — report-only per task instructions. File as follow-up issues against PR #505/#506/#507 before closing the round.
