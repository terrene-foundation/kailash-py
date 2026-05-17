# Round 1 — reviewer redteam report

Scope: commit `31a8e8c2` (#498 Session 1 foundation — four-axis LLM deployment abstraction).
Mode: `/redteam` — mechanical audit against the ten-point protocol.

## Summary

| Bucket | Count |
| ------ | ----- |
| HIGH   | 0     |
| MED    | 3     |
| LOW    | 2     |
| Green  | 8     |

Tests: 628/628 unit tests pass; `pytest --collect-only` over `packages/kailash-kaizen/tests/` exits 0 with 11,287 tests collected; no WARN / ERROR / DeprecationWarning emitted from this commit's test surface (one unrelated `PytestConfigWarning: Unknown config option: env_files` is pre-existing).

The foundation is structurally clean. Findings below are all about widening observability + test-file grep-ability + explicit S3 commitment markers, not correctness.

---

## HIGH — none

---

## MED

### MED-1 — No structured log on SSRF rejection

- **Where**: `packages/kailash-kaizen/src/kaizen/llm/url_safety.py:191 check_url`.
- **Rule**: `rules/observability.md` Mandatory Log Points §2 (integration-boundary intent + result) and §3 (operator-visible rejection).
- **Finding**: `check_url` raises `InvalidEndpoint` on eight different rejection paths (private IPv4, IPv6, IPv4-mapped, metadata IP, metadata host, encoded-IP bypass, scheme violation, resolution failure) but emits exactly one `logger.debug("url_safety.resolution_failed", …)` and nothing on the other seven. Operators running the guard in production will see `InvalidEndpoint` propagate up from the caller with no structured log at the rejection site showing `reason=encoded_ip_bypass` + the URL fingerprint.
- **Disposition**: add `logger.warning("url_safety.rejected", extra={"reason": reason, "url_fingerprint": _fingerprint(url)[:4]})` before each `raise InvalidEndpoint(...)`. WARN-level is correct here — the guard succeeded at blocking an attack, which is operationally visible per `observability.md` §3.

### MED-2 — No structured log on preset registration / lookup / rejection

- **Where**: `packages/kailash-kaizen/src/kaizen/llm/presets.py:88 register_preset`, `105 get_preset`, `59 _validate_preset_name`.
- **Rule**: `rules/observability.md` §4 (state transitions / config loads).
- **Finding**: The preset registry is a config-state transition point. Registering `openai` + attaching `LlmDeployment.openai` classmethod is a silent config load; rejecting a regex-bad name is a silent security event. Neither emits a log line. The `logger = logging.getLogger(__name__)` at the top of `presets.py` is load-bearing — but never called.
- **Disposition**: `logger.info("preset.registered", extra={"name": validated})` in `register_preset`; `logger.warning("preset.rejected", extra={"name_fingerprint": _fingerprint(name)})` in `_validate_preset_name` for non-matching input. The name itself is safe to log (already validated); the rejected fingerprint is the correct artifact for the bad path.

### MED-3 — Pending-orphan window for `LlmClient`, `ApiKey`, `ApiKeyBearer`, `StaticNone`

- **Where**: `packages/kailash-kaizen/src/kaizen/llm/client.py` + `auth/bearer.py`, exposed via `kaizen.llm.__init__`.
- **Rule**: `rules/orphan-detection.md` §1 (5-commit window) + `rules/facade-manager-detection.md` §1 (manager-shape Tier 2).
- **Finding**: These are manager-shape classes exposed on the public surface with **zero production call site** in the `kaizen` framework (confirmed via `rg ApiKey|LlmClient packages/kailash-kaizen/src/kaizen/`, matches appear only in `kaizen/llm/`). That is expected per the S3 commitment, but the orphan rule counts commits, not session names — 5 commits land quickly in an active workspace and the window closes before S3 ships. The wiring test file exists at `tests/integration/llm/test_llmclient_openai_wiring.py` but **skips every real-execution path** with `pytest.skip("S1 client send-path stubbed …")`.
- **Disposition**: two acceptable paths:
  1. Add an explicit orphan-window exemption in the workspace `02-plans/03-redteam-amendments.md` citing the S3 commitment + a deadline commit SHA / date, AND
  2. Rename the wiring test skip message to carry the session marker (`"S3 will enable"`) so `grep -r "S3 will enable"` surfaces all the stubs at audit time.
- There is no canonical `test_apikey_wiring.py` or `test_apikeybearer_wiring.py` — the classes are structural-only in S1 so Tier 2 tests are not yet meaningful. Document that in the amendments file as well so the next redteam round does not re-file this.

---

## LOW

### LOW-1 — `openai_preset` default `model="gpt-4"` violates `rules/env-models.md`

- **Where**: `packages/kailash-kaizen/src/kaizen/llm/presets.py:128` and `:180`.
- **Rule**: `rules/env-models.md` — "NEVER Hardcode Model Names … BLOCKED: `model=\"gpt-4\"`".
- **Finding**: Both `openai_preset(..., model: str = "gpt-4", ...)` and `LlmDeployment.openai(..., model: str = "gpt-4", ...)` hardcode `"gpt-4"` as the default. The rule explicitly lists `model="gpt-4"` as a BLOCKED pattern. Today this is a preset default (power-user escape hatch), not user code — but the same pattern appears in `tests/integration/llm/test_llmclient_openai_wiring.py` as `LlmDeployment.openai(api_key, model="gpt-4o-mini")` (hardcoded in a commented-out test body) and will appear in S3 wire adapters if not caught here.
- **Disposition**: change the preset signature to `model: Optional[str] = None` and raise `ModelGrammarInvalid("missing_model")` when None. Callers supply the model name from `os.environ.get("OPENAI_PROD_MODEL")`. This matches the contract in `rules/env-models.md` and forces the bookkeeping up to the user's `.env`.

### LOW-2 — `_fingerprint` prefix length drifts across SDK surfaces

- **Where**: `packages/kailash-kaizen/src/kaizen/llm/errors.py:41` + `presets.py:54` + `auth/bearer.py:68`.
- **Rule**: `rules/event-payload-classification.md` §2 (cross-SDK fingerprint contract — `sha256:XXXXXXXX` / 8 hex chars / 32 bits).
- **Finding**: The three fingerprint helpers each use 4 hex chars (16 bits). DataFlow's event-payload contract uses 8 hex chars (32 bits) with an explicit `"sha256:"` prefix. Kailash-py has no single cross-SDK fingerprint helper; the 4-char form here will diverge the moment a future code path tries to correlate an LLM auth-reject fingerprint with a DataFlow event fingerprint — same raw value, two different shapes.
- **Disposition**: introduce a shared `kailash.utils.fingerprint.short_fp(raw, *, bits=32, prefix=True)` and route all three call sites through it. Ship as a separate commit before S2 so the decision is isolated. Alternatively, document in workspace journal that the 4-char LLM-local shape is intentional and will not be correlated across systems.

---

## Green flags

1. **Collect-only green** — 11,287 tests collected, exit 0. No `ModuleNotFoundError`, `ImportError`, or orphan test files.
2. **Credential hygiene** — `repr(ApiKeyBearer(kind=…, key=ApiKey('sk-hunter2')))` prints `ApiKeyBearer(kind=Authorization_Bearer, fingerprint=af85)` with no raw bytes. `ApiKey` has no `__eq__`/`__hash__` (structurally enforced via `__slots__` + absence from `__dict__`, test asserts the absence).
3. **`hmac.compare_digest`** is the only equality path, verified by a monkeypatch spy test that asserts the call happens.
4. **SSRF guard depth** — all 8 depth payloads rejected with typed reasons: decimal-encoded (`2130706433` → `encoded_ip_bypass`), octal (`0177.0.0.1` → `encoded_ip_bypass`), IPv4-mapped IPv6 (`::ffff:127.0.0.1` → `ipv4_mapped`), AWS v4/v6 metadata, Google metadata, Azure metadata — each mapped to the exception's `reason` allowlist.
5. **Iterative stub discipline** — `LlmClient.from_env()` raises with `"session 7 (S7)"`; `LlmClient.complete()` raises with `"session 3 (S3)"`; every unimplemented preset on `LlmDeployment` raises with a session marker via `_NOT_YET_IMPLEMENTED` class-var (grep-able at audit time).
6. **Cross-SDK parity (semantic)** — `WireProtocol` members = `OpenAiChat, OpenAiCompletions, AnthropicMessages, GoogleGenerateContent, BedrockInvoke, VertexGenerateContent, AzureOpenAi` (byte-match Rust). `ApiKeyHeaderKind` members = `Authorization_Bearer, X_Api_Key, X_Goog_Api_Key`. `AuthStrategy` Protocol methods = `apply, auth_strategy_kind, refresh`. All match the contract.
7. **Additive contract** — `git diff 31a8e8c2^ 31a8e8c2 --stat -- packages/kailash-kaizen/src/kaizen/providers/ src/kaizen/llm/routing/ src/kaizen/llm/reasoning.py` returns empty. The existing 39-consumer `kaizen.providers.registry` surface is untouched. The option-A decision holds structurally.
8. **Per-session capacity** — production code is ~1,459 LOC but it is boilerplate data-class definitions (frozen Pydantic models, closed enums, exception classes). Load-bearing logic (SSRF guard + preset regex + credential comparison) is ~400 LOC with ~4 invariants (scheme gate, IP range check, encoded-bypass detector, DNS-rebind resolver). Within the `rules/autonomous-execution.md` §Per-session capacity budget for boilerplate-heavy shards.

---

## Disposition gate

- MED-1 / MED-2: ship observability amendments before S3. Both are single-file additions of 3–5 log lines each; not blocking for a PR merge but blocking for "S1 is shippable to downstream workspaces."
- MED-3: either land the orphan-window exemption amendment OR wire the first production call site in S2 (preferred). Recommendation: extend `02-plans/03-redteam-amendments.md` with a MED-6 section explicitly naming the S3 commit as the close-out for the orphan-window, and rename the wiring-test skip message to carry the `"S3 will enable"` marker.
- LOW-1: promote to MED before S3 if the `model="gpt-4"` default escapes into an example, a docstring quickstart, or a wire-adapter default.
- LOW-2: track as a cross-SDK-parity item; not blocking this session but block S4+ (Bedrock) when the AWS audit row needs to cross-correlate with the LLM auth-reject fingerprint.
