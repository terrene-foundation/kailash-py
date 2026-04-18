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
