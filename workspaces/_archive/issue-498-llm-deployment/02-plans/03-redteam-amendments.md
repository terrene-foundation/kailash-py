# Plan Amendments — Red Team Round 1 (2026-04-18)

Source: kaizen-specialist red-team pass against `01-shard-breakdown.md`
(/todos gate, session round 4, 2026-04-18).

**Verdict:** 0 HIGH, 5 MED, 3 LOW. The 5 MEDs below MUST be folded
into the originating session's /implement work. The 3 LOWs are
tracked here for disposition but do not block the gate.

Every amendment cites the affected todo file so the implementer finds
it without re-reading the red-team output.

## MED-1 — Azure wiring test file by convention

**Gap:** S6-i/S6-ii introduce `AzureEntra` auth but no
`test_azureentra_wiring.py` is named anywhere. Per
`rules/facade-manager-detection.md` §2, manager-shape classes (auth
strategies qualify) MUST have a Tier 2 wiring file whose absence is
grep-able by the predictable name.

**Amendment:** Add `tests/integration/llm/test_azureentra_wiring.py` to
S6-i's T2 test list. Gated on `AZURE_OPENAI_API_KEY` or an Azure
service principal; cassette fallback via `pytest-recording`.

**Affected todo:** `todos/active/006-session-6-s6-azure-entra.md` — add
the file under **Tests (T2)**.

## MED-2 — Tier 2 wiring files for `LlmHttpClient` and `AwsSigV4`

**Gap:** S4c lists only a T1 test for `LlmHttpClient`
(`test_llm_http_client_uses_safe_dns_resolver.py`). S4b-i says "real
Bedrock SigV4 call, cassette-recorded" but no file named per
convention.

**Amendment:**

- Add `tests/integration/llm/test_llmhttpclient_wiring.py` to S4c's T2
  list — asserts the `LlmHttpClient` singleton actually routes through
  `SafeDnsResolver` on a live Bedrock or OpenAI endpoint (cassette-
  recorded).
- Add `tests/integration/llm/test_awssigv4_wiring.py` to S4b-i's T2
  list — the "real Bedrock SigV4 call" that the plan already mandates,
  now named by convention.

**Affected todos:**

- `todos/active/003-session-3-s4a-bedrock-claude-plus-s4b-i-sigv4-core.md`
  — add `test_awssigv4_wiring.py` under **Tests (T2)**.
- `todos/active/004-session-4-s4b-ii-bedrock-families-plus-s4c-security-suite.md`
  — add `test_llmhttpclient_wiring.py` under **Tests (T2)**.

## MED-3 — Rust §6 threat coverage gaps

**Gap:** Four Rust `specs/llm-deployments.md` §6 threats have no named
test in any shard.

| Threat                                                                      | Resolution                                                                                                                                        | Shard |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| 6.4 Timing side-channel (credential validation)                             | `tests/unit/llm/security/test_credential_comparison_uses_constant_time.py` — assert `hmac.compare_digest` usage                                   | S4c   |
| 6.5 Classification-aware prompt redaction                                   | `tests/unit/llm/security/test_llmclient_redacts_classified_prompt_fields.py` — integrate with `apply_read_classification` on request.messages     | S4c   |
| 6.M2 Observability log-injection via `deployment_preset` label              | `tests/unit/llm/security/test_deployment_preset_regex_rejects_injection.py` — CRLF, spaces, unicode in preset name                                | S1+S2 |
| 6.M5 Legacy shim rejects new-preset names via 1-key API                     | `tests/unit/llm/from_env/test_legacy_shim_rejects_new_preset_names.py` — `KAILASH_LLM_PROVIDER=bedrock_claude` via legacy tier raises typed error | S7    |
| 6.8 Credential zeroization (complement to rotation — S4b-i covers rotation) | `tests/unit/llm/auth/test_aws_credentials_zeroize_on_rotate.py` — assert old `SecretStr` values are cleared/overwritten                           | S4b-i |

**Affected todos:**

- `todos/active/001-session-1-s1-s2-foundation-openai.md` — add
  `test_deployment_preset_regex_rejects_injection.py` under **Tests
  (T1)**.
- `todos/active/003-session-3-s4a-bedrock-claude-plus-s4b-i-sigv4-core.md`
  — add `test_aws_credentials_zeroize_on_rotate.py` under **Tests
  (T1)**.
- `todos/active/004-session-4-s4b-ii-bedrock-families-plus-s4c-security-suite.md`
  — add `test_credential_comparison_uses_constant_time.py` and
  `test_llmclient_redacts_classified_prompt_fields.py` under **Tests
  (T1)**.
- `todos/active/007-session-7-s7-from-env-plus-s8-plugins-sync.md` —
  add `test_legacy_shim_rejects_new_preset_names.py` under **Tests
  (T1)**.

## MED-4 — Back-compat empirical verification

**Gap:** S3 invariant 3 claims "39 registry consumers compile and test
unchanged" but no dedicated Tier 2 test imports
`kaizen.providers.registry.get_provider(...)` and runs a completion
through it. Passive reliance on existing provider tests staying green
is not a guard against a future refactor that re-routes the registry
path.

**Amendment:** Add
`tests/regression/test_provider_registry_backcompat.py` — imports
`kaizen.providers.registry.get_provider("openai")` (and anthropic,
google as gated tests), runs a one-token completion, asserts success.
This file is NEVER deleted per `rules/testing.md` § "Regression tests
are never deleted."

**Affected todo:** `todos/active/002-session-2-s3-anthropic-google-direct-providers.md`
— add under **Tests (regression)**. Alternatively, fold into
`todos/active/100-global-wiring-audit.md` as a session-gate check.

## MED-5 — Retry-After cross-provider parity test

**Gap:** `03-gaps-and-risks.md §9` flags OpenAI / Anthropic `Retry-After`
header semantics differ (seconds vs HTTP-date). No shard names a
parity test.

**Amendment:** Add `tests/cross_sdk_parity/test_retry_after_matches_rust.py`
to S9's parity suite — snapshot-compare Python retry-semantics output
against the Rust retry-semantics output for each provider's
`Retry-After` response variant.

**Affected todo:** `todos/active/008-session-8-s9-parity-docs-release.md`
— add to **Tests (T2)** cross-SDK parity list.

## LOW Findings (tracked, non-blocking)

| ID    | Finding                                                                                    | Disposition                                                                                                         |
| ----- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| LOW-1 | `test_from_env_legacy_bedrock_only.py` missing — Rust §5.4 STP unblock path via legacy env | Add to S7's T1 test list during /implement — document in session-7 todo as "optional expansion"                     |
| LOW-2 | Region-allowlist parity test not in S9                                                     | Fold into `test_preset_names_match_rust.py` as a shared-fixture assertion (region list is a shared constant)        |
| LOW-3 | `error_class` closed-set enumeration in parity snapshot                                    | Extend `test_error_taxonomy_matches_rust.py` to pin the closed set of `error_class` enum values, not just the field |

## Summary

All 5 MED findings are resolvable in-shard without re-scoping. No
shard grows past the capacity budget after these additions
(largest impact: S4c gains ~3 test files, already in the capacity
headroom).

**Gate status:** plan is ready for human approval pending the human's
nod. The MEDs become /implement tasks within their shard, not a
separate approval cycle.

---

# Round 2 / Round 3 Amendments (2026-04-18, post-Session 1 convergence)

Session 1 landed and converged through 2 parallel /redteam rounds + a
round-3 cleanup commit (`c00f21c4`). The items below were carried over
from rounds 1–3 as deferred LOW/MED follow-ups. This round-5 session
resolves each one in the pristine-first sweep before the next
implementation shard starts.

## Round 5 Resolutions (pre-Session 2 cleanup sweep, 2026-04-18)

### R5-1 — Nexus M-N2 cancel-cleanup contract

**Was:** round-2 security MED, downgraded to LOW by reviewer. Plugin
`on_startup` hooks cancelled by `asyncio.wait_for` left partially
initialized state (DB connections acquired, tasks spawned) with no
framework-enforced cleanup path.

**Resolution:** Added three-clause cancel-cleanup contract to
`src/kailash/servers/workflow_server.py`'s `startup_hook_timeout`
docstring. Two Tier 2 integration tests at
`tests/integration/nexus/test_startup_hook_cancel_cleanup.py` exercise
the contract (partial-init cleanup via shutdown_hook + spawned-task
cancellation). Real asyncio, real FastAPI lifespan, no mocking.

**Commit:** R5 cleanup (see session commit).

### R5-2 — `_run_async_hook:1977` third residual `asyncio.iscoroutinefunction` site

**Was:** third residual `asyncio.iscoroutinefunction` call (Python 3.14
deprecated) out of round-1 scope. Surface audit found the actual
remaining site at
`packages/kailash-nexus/src/nexus/auth/audit/backends/custom.py:32`,
not the line in session notes.

**Resolution:** Replaced `asyncio.iscoroutinefunction` with
`inspect.iscoroutinefunction` (forward-compatible). 64/64 auth/custom
tests green.

### R5-3 — #498 LOW-1 hardcoded `model="gpt-4"` default

**Was:** round-2 reviewer LOW-1. `openai_preset` / `LlmDeployment.openai`
defaulted `model` to the literal `"gpt-4"`, violating
`rules/env-models.md` ("BLOCKED: model='gpt-4'"). Kept in round-3 for
ergonomic quickstart despite the rule.

**Resolution:** Made `model` a REQUIRED parameter (no default) on both
`openai_preset` and the classmethod. The docstring points callers to
`os.environ["OPENAI_PROD_MODEL"]`. Added two new unit tests covering
the required-model contract. Migration path is clean for Session 2+
(every new preset takes `model` as a required parameter).

### R5-4 — ApiKey pickle/deepcopy hygiene

**Was:** round-2 defer followup. `ApiKey.__slots__` values were
exposed via `copy.deepcopy` and `pickle.dumps` default protocols —
the SecretStr payload shipped across pickling boundaries (multi-process
queues, test cassettes, exception reprs).

**Resolution:** Added `__reduce__`, `__deepcopy__`, and `__copy__`
overrides that route reconstruction through `__init__`. 5 new unit
tests in `test_apikey.py` cover the round-trip contract. The override
does NOT eliminate cross-process secret-bearing pickle payloads
(that's a caller discipline issue documented in the class docstring),
but it DOES prevent accidental **slots**-level repr leakage via
in-process copying.

## MED-3 (deferred to Session 3 close-out) — `LlmClient` orphan-window amendment

**Was:** #498 round-2 reviewer MED-3. `LlmClient` is a facade class
per `rules/facade-manager-detection.md` §2 (name matches `*Client`
pattern — adjacent to the manager-shape regex). Session 1 ships
`LlmClient.from_deployment(LlmDeployment)` with a structural wiring
test but no live-network hot-path consumer in the framework's own
code (wire-send lands in Session 3's S4 via `LlmHttpClient`).

**Amendment:** At Session 3 close-out, the Tier 2 integration test
`tests/integration/llm/test_llmclient_send_wiring.py` MUST land in
the same commit as the wire-send path. The test MUST:

1. Import `LlmClient` through the framework facade (not the class
   directly from a submodule).
2. Construct via `LlmClient.from_deployment(LlmDeployment.openai(...))`.
3. Invoke `client.send(prompt="...", max_tokens=1)` against a
   cassette-recorded OpenAI endpoint.
4. Assert the externally-observable effect: one HTTP call was made
   with `Authorization: Bearer ...` header matching the API key's
   fingerprint.

This closes the orphan-window per `rules/facade-manager-detection.md`
§1 ("every `db.X` / `app.X` facade has a production call site") within
5 commits of the facade landing. Session 1's LlmClient is at commit 1
of the 5-commit window; Session 3's wire-send will be commit 2-3,
well within the allowance.

**Affected todo:** `todos/active/003-session-3-s4a-bedrock-claude-plus-s4b-i-sigv4-core.md`
— add `test_llmclient_send_wiring.py` under **Tests (T2)**.

**Failure mode if NOT addressed by Session 3:** LlmClient joins the
Phase 5.11 orphan class (documented facade with no production call
site). Session 3 gate MUST fail on /redteam if the wiring test file
is absent.
