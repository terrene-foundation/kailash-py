# #1056 — Architecture Plan (post-/analyze, nexus-specialist authoritative)

## Verdict

Python Nexus exposes **no query-string API-key decode surface**. The Rust bug class (kailash-rs#998: hand-rolled `?api_key=` percent-decode with invalid-UTF-8 raw-fallback + no NUL guard) **structurally cannot exist** here:

- `src/kailash/trust/auth/jwt.py:99-101` — `JWTConfig` has only `api_key_header`/`api_key_enabled`/`api_key_validator`. No `api_key_query_param` field.
- `packages/kailash-nexus/src/nexus/auth/jwt.py:275-279` — API-key extraction is header-only (`request.headers.get(api_key_header)`).
- `specs/security-auth.md §2.2` — contract is `X-API-Key` header.
- Only server-side query-param auth path is JWT _token_ (WebSocket) at `jwt.py:294-298`, using Starlette stdlib decode (no hand-rolled `unquote()` raw-fallback). NUL on that path is inert (JWT verify is a crypto check, no credential-truncation surface).

**Severity: MEDIUM → NOT-AFFECTED** (regression-pinning value only, not vuln remediation). Matches the #525/PR#528 precedent in `cross-sdk-inspection.md §3a`.

## Disposition (cross-sdk-inspection.md §3a + verify-resource-existence.md MUST-3)

Tests-only. **No production code.** Inventing a `?api_key=` path is BLOCKED (spec doesn't call for it; query-string credentials are an inferior pattern — leak into logs).

### Shard 1 (combined — ~120 LOC test code, 0 load-bearing logic, ≤3 invariants, pytest feedback loop)

| Item | File                                                                                            | Content                                                                                                                                                                                                                                                                                                                         | Value-anchor                                                                                                                     |
| ---- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1a   | `packages/kailash-nexus/tests/integration/test_jwt_query_param_decode_cross_sdk.py` (new)       | Tier-2, real Nexus app + real ASGI flow, NO mocking. 3 scenarios on the `token_query_param` path (the only query-string credential decode surface): (1) `?access_token=%00x` → 401 reject; (2) invalid-UTF-8 `%FF%FE` → 401 reject, decoded value ≠ literal still-encoded string; (3) valid percent-encoded JWT → auth succeeds | issue #1056 AC bullets 2–4 (verbatim); cross-sdk §3a item 1                                                                      |
| 1b   | `packages/kailash-nexus/tests/regression/test_issue_1056_apikey_header_only_invariant.py` (new) | Structural invariant: (i) `dataclasses.fields(JWTConfig)` api-key field set == `{api_key_header, api_key_enabled, api_key_validator}` exactly; (ii) `inspect.getsource(JWTMiddleware._extract_token)` api-key branch reads only headers, never `request.query_params` for the key                                               | cross-sdk §3a item 2 — pins bug-class absence; fails loudly if a future port adds `?api_key=`                                    |
| 1c   | `gh issue close 1056`                                                                           | Comment cites both test paths + commit SHA + cross-ref kailash-rs#998. States: no query-string API-key path (config-level exclusion); AC#1 recorded not-literally-applicable (no decode call site to route through helper); bug class pinned by 1b invariant                                                                    | `git.md` issue-closure discipline; §3a no-hand-waving close; **USER GATE** (value-bearing close per value-prioritization MUST-4) |

### Out of scope (do NOT fold in — nexus-specialist explicit)

- NUL guard on `token_query_param` branch — no truncation/comparison surface (JWT verify is crypto, not credential lookup). No value-anchor. Separate issue if user later wants defense-in-depth.

### Cross-SDK divergence note (EATP D6 — surface only, do NOT act)

kailash-rs exposes a `?api_key=` query-string path; kailash-py deliberately does not (header-only = strictly smaller attack surface). Recommend the **user** file a kailash-rs issue to align Rust _down_ to Python's header-only posture (deprecate the query-string API-key path). Per `repo-scope-discipline.md` this is surfaced as a recommendation only — NOT filed from this kailash-py session.

## Human gates

1. Plan scope (this doc) — tests-only, non-destructive → proceeding under `/autonomize`.
2. **Issue #1056 closure (1c)** — explicit user gate before `gh issue close`.
3. kailash-rs cross-ref filing — user's action, surfaced not executed.
