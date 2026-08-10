# Changelog

All notable changes to the kaizen-agents package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.0] — 2026-08-05 — Documented permission checker is fixed and now fails closed on error; MCP tool discovery and multi-agent routing fixes

**Upgrade note: `pip install -U kailash-kaizen` alone does NOT deliver the fail-open discovery fix below.** `kaizen-agents` 0.12.0 (the currently-published version) declares `kailash-kaizen>=2.36.0` with no upper cap, and this is a `kaizen-agents` fix (`UserFilteredAgentDiscovery` lives in this package, not in `kailash-kaizen`). A `kailash-kaizen` upgrade to 2.46.0 already satisfies that floor, so a resolver has no reason to also touch `kaizen-agents` — an installation can report "kailash-kaizen upgraded" while `kaizen-agents` stays at 0.12.0, keeping the fail-open permission checker described below live with no dependency-resolver signal that anything is still wrong. **`kaizen-agents` MUST be explicitly upgraded to 0.13.0 to receive this fix** — `pip install -U kailash-kaizen kaizen-agents` (or pin `kaizen-agents>=0.13.0` directly).

### Security

- **BREAKING: `UserFilteredAgentDiscovery`'s documented permission checker (`TrustOperations`) never worked — wiring it returned every agent to every user, in every organization, always.** The call site invoked the checker with a keyword shape the documented type's real signature doesn't accept, so the call raised `TypeError` on the first agent of every check; the exception handler caught it and treated the failure as a _grant_. This was the steady-state behavior for any deployment that wired the documented integration path, not an edge case. The call shape, the "malformed result" check, and the constraint-field name (`effective_constraints`, not `constraints`) are all fixed, so the documented checker now actually enforces what it's configured to enforce.
- **BREAKING: a permission checker that raises an exception now DENIES access instead of granting it.** Previously, any error from a caller-supplied permission checker — a database hiccup, a network timeout, a bug in the checker itself — fell through to the same code path as "no restriction found" and granted the requesting agent access. A checker error now denies the request and logs a loud, scrubbed error naming the failure, so an outage in your permission-checking backend shows up as "access denied" (with a clear log line pointing at the cause) instead of silently granting access to everyone. **Operator impact:** if your permission checker occasionally errors — under load, on a flaky connection, during its own maintenance windows — those requests that previously succeeded (incorrectly) will now be denied until the checker is healthy again. This is the intended, safer trade: a transient outage should show up as "temporarily can't confirm access" rather than "everyone has access."
- **BREAKING: a permission checker object that evaluates as `False` (falsy) — e.g. an empty policy set, a health-gated wrapper — was silently skipped, granting access with no checker having run at all.** The code that decides whether a checker is "wired" now checks whether one was configured (not whether it currently evaluates truthy), so a checker your code correctly wired up is always consulted. **Operator impact:** if you have a permission checker that can evaluate falsy in some states (this is unusual, but happens with certain wrapper/proxy patterns), those requests were previously silently granted without your checker's input; they will now correctly go through your checker's actual decision, which may deny requests that were previously (incorrectly) allowed through. If this surfaces unexpected denials, check whether your checker object's `__bool__`/`__len__` can return falsy while still holding real policy — that's the condition this closes.
- A permission checker returning a result object your code cannot interpret (missing the expected `.valid` field, or a genuinely unparseable answer) previously read the _absence_ of an explicit denial as approval; it now requires an explicit `True` to grant.
- A granted-but-constrained access decision could silently drop the constraint information into a shape meaning "no limits at all" — a checker that granted access with a `read_only` restriction, for example, could end up producing an access record with no restriction encoded. The constraint payload is now read completely (all 7 fields, not the 2 that were wired) and a payload the code cannot parse now denies rather than granting unlimited access.

### Fixed

- **`kailash-kaizen` version floor raised to `>=2.46.0` (from `>=2.36.0`) — required, not optional.** This package imports symbols from `kailash-kaizen` at module load time that do not exist before 2.46.0 (the shared credential-scrubbing module, `ReasoningDegradedError`, and the tool-input-schema normalizer). Upgrading `kaizen-agents` without also upgrading `kailash-kaizen` to at least 2.46.0 causes `import kaizen_agents` to fail immediately with `ImportError`.
- **A permission-gated MCP tool advertised an invalid, empty parameter schema to every LLM provider.** A tool your access-control policy restricts is intentionally advertised with `inputSchema: {}` — but every converter (Anthropic, OpenAI, and this package's own MCP path) read that as "no schema provided" rather than "empty schema provided," and passed it through unchanged. Anthropic's API rejects a genuinely-empty/typeless schema outright; providers that do accept it then have no argument names for that tool, so the model can't call it correctly. All three converters now normalize this consistently through one shared helper.
- **Agents whose permission checker returned an "advisory" restriction label it couldn't otherwise express were being silently denied and vanished from discovery entirely** — with no error, indistinguishable from an outage, and the only workaround being to disable the permission checker altogether. That restriction category is enforced independently, one layer down (at capability-signature verification), so denying it here added no additional safety and only cost availability. These agents are now correctly discoverable again; the advisory label is preserved on the access record rather than silently dropped.
- **A silently-unconfigured permission checker (the `permission_checker=None` default) now emits one loud warning at construction time** naming that access checks are running with no restriction in effect, instead of granting every user access to every agent with zero signal that anything is unguarded. The default behavior (grant when unconfigured) is unchanged — this only adds visibility. (Corrected from an earlier draft of this entry, which mischaracterized this as "once per distinct label set" — that de-duplication describes a different, unrelated warning about advisory constraint labels.)
- **Two different implementations of the same routing logic had drifted, each holding a bug the other one had already fixed.** One implementation's "route by matching capability" path silently never ran for any real agent card shape (it checked an attribute name the real card type doesn't have), so every semantic-routing call fell back to picking whichever agent happened to be first — while _appearing_ to route intelligently. The other implementation's round-robin path lacked a bounds check and crashed with `IndexError` the moment the agent pool shrank mid-run. The duplicate implementation is removed; there is now one routing implementation, carrying both fixes.
- **Multi-agent workflows silently executed with no actual task content.** The workflow builder configured each generated node with parameters the underlying LLM node doesn't accept, so the intended task was silently dropped (visible only as a low-level "unknown parameter" warning) and each agent ran with an empty instruction — yet the workflow still reported 100% success, because an LLM call with no input still returns a response. Multi-agent workflows built through this path now actually convey the task to each agent.
- A degraded reasoning judgment (see kailash-kaizen 2.46.0, #1981) could previously abort an entire workflow rather than being handled per-candidate; the semantic routing path and the agent-discovery path now handle a degraded judgment as an exclusion for that one candidate rather than a hard failure, consistent with how the rest of the #1981 fix works elsewhere in this package.

## [0.12.0] — 2026-07-23 — Default autonomous-agent checkpoints to a per-user state dir (off cwd) + owner-only permissions

### Changed

- **BREAKING (default location): `BaseAutonomousAgent` now checkpoints to a per-user state directory by default, not `./checkpoints` in the current working directory.** With no explicit `checkpoint_dir`, the default resolves via `platformdirs.user_state_dir("kaizen")` (`$XDG_STATE_HOME`/`~/.local/state/kaizen/checkpoints` on Linux, `~/Library/Application Support/kaizen/checkpoints` on macOS, `%LOCALAPPDATA%\kaizen\checkpoints` on Windows) — so the SDK no longer writes checkpoint files into whatever directory the process was launched from. **Migration:** to keep the old behavior, pass `checkpoint_dir=Path("./checkpoints")` explicitly; existing checkpoint files under a project-local `./checkpoints/` are not auto-migrated and will not be found by the new default (recovery from them requires passing the explicit path). This completes the cwd-litter fix started in 0.11.8 (which stopped the _construct-time_ directory creation); 0.12.0 additionally relocates the _run-time_ checkpoint writes off the cwd.

### Security

- **Checkpoint directory and files are now created with owner-only permissions on POSIX** (`0o700` dir / `0o600` files), matching the delegate `SessionManager` secure-write pattern. Checkpoint payloads can contain conversation and plan state; they were previously created world-readable under the default umask. On Windows, POSIX modes do not apply and a plain append is used.

## [0.11.8] — 2026-07-23 — Stop `BaseAutonomousAgent` from creating `./checkpoints/` in the caller's cwd on construction

### Fixed

- **`BaseAutonomousAgent` no longer litters the caller's working directory with an empty `checkpoints/` directory on construction.** `__init__` unconditionally called `self.checkpoint_dir.mkdir(parents=True, exist_ok=True)` (default `checkpoint_dir=Path("./checkpoints")`), so merely _constructing_ an autonomous agent — or any subclass, including the Codex and Claude-Code adapters — created a `./checkpoints/` folder in whatever directory the process was launched from, even for agents that never checkpoint (the base run loop persists via `state_manager`/DataFlow, not this directory). Directory creation is now **lazy**: it happens on the first actual checkpoint write inside `_save_checkpoint`. This is non-breaking — agents that do checkpoint get the identical directory at the identical location, created on demand; agents that don't get no stray folder. Reads were already `.exists()`-guarded, so resume/load paths are unaffected. Behavioral regression tests pin all three cases (construction creates no dir; first write creates dir+file; an explicit `checkpoint_dir` is likewise lazy).

## [0.11.7] — 2026-07-23 — Remove documented-but-unwired Delegate `signature`/`inner_agent` params (#1927)

### Removed

- **Removed the unwired `Delegate(signature=…)` and `Delegate(inner_agent=…)` constructor params and the `Delegate.signature` property (#1927).** Both were accepted and documented but never wired — silent no-ops (the same documented-kwarg-drop class as the #1899 `base_url`/`api_key` and #1926 `temperature`/`max_tokens` fixes, but here the resolution is removal, not wiring):
  - `signature` was documented as "enables structured outputs on the inner BaseAgent" but was only stored and returned by the `.signature` getter — never threaded to the loop/adapter, so structured outputs never took effect. The `Delegate` is a streaming autonomous-execution facade with no structured-output path by design; callers who need structured outputs should use the `BaseAgent` + `Signature` API (`kaizen.core`), which fully supports schema-constrained / response-format generation. Duplicating that into the streaming facade would have meant a second structured-output implementation across every provider adapter.
  - `inner_agent` was documented as a "pre-built `BaseAgent` escape hatch" but was stored and never read — the `Delegate` always builds its own streaming loop. It is architecturally incompatible with the streaming `run()` (a generic `BaseAgent` exposes only batch `run`/`run_async`, no streaming interface). The `adapter=` and `config=` params remain the supported "bring your own engine" seams.
  - The `core_agent` property docstring, which incorrectly claimed to return a "user-provided inner_agent", was corrected.
  - Passing either keyword now raises `TypeError` — a loud, actionable failure — instead of silently doing nothing. Since neither param ever functioned, no caller could depend on the documented behavior; the only migration is to drop the now-rejected keyword.
  - A structural completeness-guard test now asserts every `Delegate.__init__` param reaches a real consumer, so this documented-kwarg-drop class cannot silently regress.

## [0.11.6] — 2026-07-22 — Thread temperature/max_tokens overrides into the Delegate config build

### Fixed

- **`Delegate(temperature=…, max_tokens=…)` now actually applies the override.** Both params were accepted and documented on `Delegate.__init__` as LLM overrides, but the zero-config `KzConfig` build omitted them — so an explicit caller override was silently dropped and the `KzConfig` defaults (`temperature=0.4`, `max_tokens=16384`) always won. A caller pinning `temperature=0` for determinism silently got `0.4`. Same documented-kwarg-drop class as the #1899 `base_url`/`api_key` fix, one field over. Both are now forwarded onto `KzConfig`, and only when set (an unspecified override still inherits the `KzConfig` default, since the fields are non-Optional). A completeness sweep of `Delegate.__init__` confirmed `temperature`/`max_tokens` were the only two params silently dropped in the config path. (Two further documented-but-unwired params, `signature` and `inner_agent`, are tracked separately in #1927 — they need a wire-vs-remove design decision, not a mechanical thread.)

## [0.11.5] — 2026-07-22 — Infer provider from model prefix in zero-config Delegate (#1918)

### Fixed

- **Zero-config `Delegate(model="claude-*")` no longer routes to the OpenAI wire (#1918).** `KzConfig.provider` defaulted to the non-empty string `"openai"`, which `AgentLoop._build_adapter` forwarded as an _explicit_ provider to `get_adapter_for_model`, short-circuiting the model-name-prefix fallback (`claude-`→anthropic, `gemini-`→google). A zero-config `claude-*`/`gemini-*` model therefore built an OpenAI adapter pointed at `api.openai.com` (sending the wrong provider's key to the wrong endpoint). The default is now the empty-string sentinel `""`, aligning with `get_adapter_for_model`'s own unset sentinel so the prefix fallback runs on the no-client path; explicit `provider=` / `KZ_PROVIDER` / `.kz` config still win, and zero-config `gpt-*`/unknown-prefix models still default to OpenAI (unchanged). The prior regression test called the registry directly (bypassing `Delegate`), masking the bug — new tests exercise the full `Delegate` → adapter path end-to-end.
- **Print-mode `max_turns` override no longer drops the deployment client (#1918).** `PrintRunner`'s `max_turns`-override branch rebuilt `KzConfig` field-by-field and omitted `base_url`/`api_key`, silently dropping a #1899 deployment client; combined with the provider-default fix, a `claude-*` model pinned to a custom endpoint would then re-infer to the prefix provider's real wire instead of the caller's deployment. The reconstruction now preserves every field.

## [0.11.4] — 2026-07-22 — Route agent completion by the passed client, not the model prefix (#1899)

### Fixed

- **`Delegate(base_url=…, api_key=…)` now routes to the passed deployment client's endpoint (#1899).** An explicitly-passed OpenAI-compatible / Azure / custom-endpoint deployment client was silently ignored: `Delegate` accepted `base_url`/`api_key` but dropped them (no `KzConfig` fields), and model-name-prefix detection overrode an explicit endpoint. The passed client's endpoint is now authoritative; prefix detection is demoted to a fallback used only when no explicit client is set (zero-config `gpt-*`/`claude-*` unchanged). `KzConfig.api_key`/`base_url` carry `repr=False` so the credential cannot leak into a config log.

## [0.11.3] — 2026-07-19 — RAGResearchAgent lazy-loads so bare install imports without numpy (#1849)

### Fixed

- **A bare install no longer fails to import `kaizen_agents.agents` (or any
  `specialized.*` agent) when `numpy` is absent (#1849).** An unguarded
  module-scope import chain eagerly loaded `RAGResearchAgent`, which pulls
  `kaizen.retrieval.vector_store` → `import numpy`. `numpy` is declared by
  no `kaizen-agents` manifest — it ships only under `kailash-kaizen[rag]` —
  so its absence collateral-damaged every non-RAG agent (`chain_of_thought`,
  etc.) even though they have nothing to do with RAG. `RAGResearchAgent` now
  resolves via a PEP 562 `__getattr__` (static analysis / `__all__`
  preserved via a `TYPE_CHECKING` block) instead of an eager module-scope
  import; the registration path (`register_builtin.py` / `nodes.py`) guards
  the import with `try/except ImportError`, emitting an actionable WARN
  ("install kailash-kaizen[rag]") instead of a silent swallow. A **direct**
  submodule import
  (`from kaizen_agents.agents.specialized.rag_research import
RAGResearchAgent`) without numpy now raises an actionable `ImportError`
  naming `kailash-kaizen[rag]` (chained via `from exc`, not swallowed)
  instead of a bare `ModuleNotFoundError: No module named 'numpy'`.
  `RAGResearchAgent` remains fully functional when numpy IS present — no new
  hard dependency, no behavior change on the RAG path.

## [0.11.2] — 2026-07-19 — Cost fix: KAIZEN_MODEL fallbacks now resolve via the shared env helper (#1844, #1845)

### Fixed

- **Specialized agents, pattern factories, and workflow templates now resolve their
  `KAIZEN_MODEL`-unset fallback through the shared `kaizen_agents._model_env.resolve_default_model()`
  helper instead of a hardcoded `gpt-4` / `gpt-3.5-turbo` literal (#1844).** 0.11.1 introduced
  `resolve_default_model()` (`OPENAI_PROD_MODEL` → `DEFAULT_LLM_MODEL` → the provider-intrinsic
  `gpt-4o` fallback) for the `api` config layer only; every other consumer still had its own
  `os.getenv("KAIZEN_MODEL", "gpt-4")` (or `"gpt-3.5-turbo"`) pattern, so an unconfigured agent
  silently spent against a deprecated, billed model whenever `KAIZEN_MODEL` was unset (root
  cause of a ~$208 obsolete-model spend across the shared dev environment — the specialized
  agents, pattern factories, and coordination examples were the primary source, run on their
  obsolete defaults). `KAIZEN_MODEL`, when explicitly set, still wins at every call site — only
  the _unset_ fallback changed. Touched: the 14 specialized agents (`batch_processing`,
  `chain_of_thought`, `code_generation`, `human_approval`, `memory_agent`, `pev`, `planning`,
  `rag_research`, `react`, `resilient`, `self_reflection`, `simple_qa`, `streaming_chat`,
  `tree_of_thoughts`), the 4 pattern factories (`consensus`, `debate`, `handoff`,
  `supervisor_worker`), and `workflows/enterprise_templates.py` +
  `workflows/supervisor_worker.py`. No public signature changes — every fix is a default-_value_
  change; explicit `model=` / `KAIZEN_MODEL=` are unaffected.

Companion release: `kailash-kaizen` `2.37.1` (released alongside) closes the equivalent gap at
the Core-SDK-agent layer (`core/agents.py`, `core/framework.py`,
`nodes/ai/{llm_agent,iterative_llm_agent}.py`, `providers/multi_modal_adapter.py`). Dependency
floor stays `kailash-kaizen>=2.36.0` — this release does not depend on any new kaizen surface.

## [0.11.1] — 2026-07-19 — env-models: model defaults resolve from .env (#1825)

### Fixed

- **Hardcoded LLM model defaults now resolve from `.env` (#1825, env-models
  rule).** Executable `model="gpt-4"` / `model: str = "gpt-4"` /
  `.get("model", "gpt-3.5-turbo")` defaults across the package (the `api`
  config layer — `AgentConfig.model`, the `CapabilityPresets`, `from_preset`,
  `get_recommended_configuration` — plus the specialized-agent convenience
  functions, `patterns`/`workflows` config fallbacks) now resolve the default
  model from the environment via a shared helper
  (`kaizen_agents._model_env.resolve_default_model`:
  `OPENAI_PROD_MODEL` → `DEFAULT_LLM_MODEL` → `gpt-4o`), so a deployment's
  configured model is honored instead of a pinned literal. Provider-intrinsic
  defaults (the runtime adapters) and task-intrinsic defaults (the vision
  model, the intent-detection model, the code-review preset's Claude
  recommendation) are preserved as documented module-level constants
  overridable via provider/task-scoped env vars (`KAIZEN_OPENAI_MODEL`,
  `KAIZEN_GEMINI_MODEL`, `KAIZEN_CLAUDE_MODEL`, `KAIZEN_VISION_MODEL`,
  `KAIZEN_INTENT_MODEL`, `KAIZEN_CODE_REVIEW_MODEL`) — the env-models
  "Provider-Intrinsic Named-Constant Defaults" carve-out. No public API
  signatures changed (defaults moved from a literal to `None`-resolves-from-env);
  explicit `model=` arguments are unaffected. Regression test pins the
  resolution order and asserts no executable hardcoded default remains.

## [0.11.0] — 2026-07-19 — StreamingAgent token-streaming cutover to the four-axis LlmClient (#1720 Wave-2b)

### Changed

- **`StreamingAgent.run_stream()` now streams tokens through the four-axis
  `kaizen.llm.LlmClient` (#1720 Wave-2b).** Wave-2a retired
  `kaizen.providers.registry.get_provider_for_model` (it now raises for every
  input), which silently broke `StreamingAgent`'s legacy provider resolution:
  `_resolve_streaming_provider` caught the raise, returned `None`, and every
  stream fell back to BATCH execution — losing incremental token streaming for
  anyone on `kailash-kaizen>=2.36.0`. Streaming now resolves the innermost
  agent's config (`model` / `llm_provider` / `api_key` / `base_url` /
  `ungoverned`) to an `LlmDeployment` via `resolve_deployment_for` — the SAME
  chokepoint `BaseAgent._simple_execute_async` uses for `complete()` — and
  streams via `LlmClient.stream(...)`, mapping each parsed chunk
  (`{text, usage, stop_reason, model, tool_calls?}`) onto the typed
  `TextDelta` / `ToolCallStart` / `ToolCallEnd` / `TurnComplete` events. The
  `#1779` governance posture is honored unchanged (the agent's own `ungoverned`
  flag is passed through; a `governance_required` refusal propagates, never
  silently downgrades to batch). The batch fallback now fires ONLY in the
  genuine "no model / no four-axis deployment for the inner provider" case and
  logs at WARN.
- `StreamingAgent.__init__` gains an optional `http_client=` parameter
  (mirroring `LlmClient`'s own transport seam) for advanced callers / offline
  deterministic tests (`kaizen.llm.testing.MockLlmHttpClient`).

### Fixed

- **Circular import that downgraded `kaizen.Agent` to the sync `CoreAgent`.**
  `kaizen/__init__.py` eagerly ran `from kaizen_agents import Agent`; when
  `kaizen` was first imported THROUGH `kaizen_agents`
  (`kaizen_agents/__init__` → `Delegate` → `kaizen.core.base_agent` →
  `kaizen`), `kaizen_agents` was only partially initialized, the import raised
  `ImportError: cannot import name 'Agent' from partially initialized module
'kaizen_agents'`, and it silently fell through to `CoreAgent`. `kaizen.Agent`
  is now resolved lazily via PEP 562 `__getattr__`, so the canonical async
  `Agent` resolves correctly regardless of import order. Paired with making
  `kaizen.core.agent_loop`'s `error_sanitizer` import lazy so the base import
  surface no longer drags in the `kaizen.nodes.ai.a2a` subtree — restoring
  graceful degradation when a2a (or a `[rag]` extra it needs) is unavailable
  (`kailash-kaizen` change, released together).

### Dependencies

- **Requires `kailash-kaizen>=2.36.0`** (was `>=2.35.0`). This release depends
  on the Wave-2a retired registry + the four-axis `LlmClient.stream` surface,
  both of which land in kaizen 2.36.0.

## [0.10.0] — 2026-07-18 — governance_required posture on the orchestration egress chokepoint (#1779)

### Added

- **`governance_required` posture enforcement across the ENTIRE kaizen-agents
  direct-LLM-egress surface (#1779, EATP D6 parity).** kaizen-agents constructs
  provider clients directly (not through the four-axis `kaizen.llm.LlmClient`) in
  several places; all are now gated on the core `kailash.is_governance_required()`
  posture. When the posture is ACTIVE, a bare un-governed construction is refused
  fail-closed with `kailash.trust.pact.UngovernedEgressRefused` unless
  `ungoverned=True` is passed; OFF by default (byte-identical to prior behavior).
  Gated surfaces:
  - `kaizen_agents.llm.LLMClient` (the orchestration DI chokepoint — planner /
    recovery / protocols / monitor / context inject it);
  - the flagship `Delegate` primitive's execution path: `AgentLoop`'s client
    factory + every streaming adapter (`OpenAIStreamAdapter`,
    `AnthropicStreamAdapter`, `GoogleStreamAdapter`, `OllamaStreamAdapter`,
    `OllamaEmbeddingAdapter`);
  - the orchestration structured adapters (`OpenAIStructuredAdapter`,
    `AnthropicStructuredAdapter`);
  - the runtime adapters (`OpenAICodexAdapter`, `GeminiCLIAdapter`).

  The `ungoverned` opt-out is threaded top-down through `Delegate` → `AgentLoop`
  → the adapter registry (`get_adapter` / `get_adapter_for_model` /
  `get_embedding_adapter`) → each adapter, so `Delegate(..., ungoverned=True)`
  disables the gate for its whole egress chain.

## [0.9.11] — 2026-06-17 — Gemini adapters on supported google-genai SDK; provider SDKs are runtime deps

### Changed

- **Gemini adapters migrated from the deprecated `google.generativeai` SDK to
  the supported `google.genai` SDK** (#1351). `delegate/adapters/google_adapter.py`
  and `runtime_adapters/gemini_cli.py` now use `genai.Client` +
  `client.aio.models.generate_content_stream` + `types.GenerateContentConfig` /
  `types.Tool` / `types.ToolCodeExecution` (generation knobs moved from the model
  object into the per-request config). No `FutureWarning` from the end-of-life
  package on the Gemini path.

### Fixed

- **Provider SDKs declared as runtime dependencies** (#1351). `google-genai` and
  the sibling `anthropic` (which had the identical defect) were declared only in
  `[dev]` extras yet imported at runtime by their adapters — so a normal
  `pip install kaizen-agents` raised `ImportError` on the Gemini / Anthropic path.
  Both are now `[project.dependencies]`; the deprecated `google-generativeai` pin
  is removed. Regression coverage:
  `tests/regression/test_issue_1351_google_genai_migration.py`.

## [0.9.10] — 2026-06-11 — enforce the slim-core import fix via the kailash-kaizen floor

### Changed

- **`kailash-kaizen` floor raised to `>=2.25.1`.** The slim-core
  `import kaizen_agents.patterns` contract claimed in 0.9.9 is only actually
  satisfied by kailash-kaizen 2.25.1, which lazy-loads the optional-extra autonomy
  hooks (`structlog` / `prometheus-client` / `opentelemetry`). Pinning the floor
  guarantees a fresh `pip install kaizen-agents` receives the fixed kaizen. No
  kaizen-agents source change.

## [0.9.9] — 2026-06-11 — slim-core import contract + ruff-clean test dirs + deprecation fixes

### Fixed

- **`import kaizen_agents.patterns` no longer requires optional heavy
  dependencies** (F31-FU5 sibling): `patterns/runtime.py` and
  `patterns/state_manager.py` moved runtime-optional type references behind
  `from __future__ import annotations`, completing the slim-core import contract
  (pinned by the kailash-kaizen FU5 subprocess regression suite).
- `datetime.utcnow()` → `datetime.now(UTC)` in `api/result.py`, `api/agent.py`,
  and `runtime_adapters/types.py` (DeprecationWarning class).
- Pre-existing integration fixture drift: the `orchestration_runtime` teardown
  called `shutdown(mode="immediate")` — a kwarg `OrchestrationRuntime.shutdown`
  never had (drift from the #75 structural split); now `shutdown(graceful=False)`.

### Changed

- All test directories (`tests/{unit,integration,e2e}`) are ruff-clean
  (394 findings → 0), enabling lint-gating kaizen-agents tests in CI. Adapter
  unit-test dependencies (`anthropic`, `google-generativeai`) declared in `[dev]`.

## [0.9.8] — 2026-06-01 — persistent/learning memory shortcut repair + pyright drift (#855)

### Fixed

- **`Agent(memory="persistent")` and `Agent(memory="learning")` no longer crash (#855)** — the shortcut factories passed `storage_path=`/`enable_*=` kwargs that `HierarchicalMemory.__init__` (`hot_size, warm_backend, cold_backend, ...`) never accepted, so both shortcuts raised `TypeError: unexpected keyword argument 'storage_path'` on every call and were unusable. Both factories now build a real warm-tier-backed `HierarchicalMemory`: a `_safe_sqlite_dsn()` helper emits DataFlow's required 4-slash absolute SQLite DSN (the 3-slash form fails `unable to open database file`) and rejects `?`/`#`/null bytes; a `_build_dataflow_warm_backend()` helper registers `MemoryEntryModel` with the `tag_list` column (not the reserved `NodeMetadata.tags`) and returns a `DataFlowMemoryBackend`, degrading to hot-tier-only with a logged warning when DataFlow is unavailable (never a silent drop). Verified end-to-end: `store()`→`get()` round-trips content AND tags.
- **pyright type-drift in `patterns/state_manager.py` and `journey/core.py` (#855)** — bound `DataFlow`/`AsyncLocalRuntime`/`WorkflowBuilder` in a `TYPE_CHECKING` block (previously "possibly unbound" from the lazy `try/except ImportError`); guaranteed an async-capable `self.runtime` via a graceful fallback to an owned `AsyncLocalRuntime` when a sync runtime is supplied; imported `Pipeline` unconditionally for type-checking (the prior `Pipeline = None` on ImportError broke every `Pipeline` annotation); switched to the canonical `Signature.with_guidelines()`. Reduces the three files from 19 errors / 14 warnings to 0/0.

## [0.9.7] — 2026-05-09 — slim core: orphan deletes + httpx/openai consolidation (#890)

Patch release shipping kaizen-agents' slice of the kailash 2.18.0 / #890 slim-core decoupling. **No public-API behavior change** — three deps audited as orphans (zero imports across `src/kaizen_agents/`) are deleted, and the dep ordering is cleaned up. Users see no difference in installed packages from the `kailash-kaizen` + `openai` transitive set.

### Changed

- **Removed orphan dependencies** — verified via grep across `src/kaizen_agents/`:
  - **`kailash-pact>=0.8.1`** — zero imports. PACT semantics are reached via `kailash.trust.pact.*` (in `kailash` core), not the separate `kailash-pact` package. DELETED.
  - **`python-dotenv>=1.0.0`** — zero imports. DELETED.
  - **`structlog>=23.1.0`** — zero imports. DELETED.
- **Re-ordered remaining deps** — `kailash`, `kailash-kaizen`, `openai`, `httpx`. `httpx` is function-local but small enough to keep in core for ergonomics (no extras gating).
- **`kailash` floor: 2.14.0** (unchanged) — kaizen-agents does not require the 2.16+ slim-core surface; kailash-kaizen floor handles the chain.

### Notes

- This is a **dependency-cleanup release** — no `__init__.py` exports change, no `__all__` change, no behavior change. Test suite verifies all symbols still resolve.

## [0.9.6] — 2026-05-06 — black + ruff modernization sweep (#815, PR #850)

1222 unit tests pass (PR #850 CI). No public API change: `__init__.py` exports + `__all__`
lists are byte-for-byte identical between main and HEAD on every package init module.
Wheel content unchanged for any consumer-visible surface.
Pre-existing pyright drift (not introduced by this release) tracked in issue #855.

### Changed (issue #815 — chore-only modernization sweep, packages/kaizen-agents/src/)

- Applied Black + Ruff modernization sweep across `src/` clearing pre-existing drift the T3 hygiene release (`0.9.5`) flagged as out-of-scope. **No public API change**: `__init__.py` exports + `__all__` lists are byte-for-byte identical between main and HEAD on every package init module. Wheel content unchanged for any consumer-visible surface.
- Black: 88 files reformatted at line-length=88 (aligned with repo-level pre-commit hook). Project `pyproject.toml::[tool.black]::line-length` updated 100 → 88 for single-source-of-truth.
- Ruff: 376 of 433 diagnostics auto-fixed (PEP 604 `Optional[X] → X | None`, PEP 585 `List[X] → list[X]`, unused imports, deprecated `typing` re-exports). Manual triage: F821 (undefined `ExecutionMode` annotation in `api/shortcuts.py` — fixed via `TYPE_CHECKING` import), F841 unused locals (3 dead assignments removed in `validation.py`, `journey/nexus.py`, `patterns/parallel.py`), B904 raise-from-clause (17 sites — every `except X as e: raise Y(...)` now chains via `from e` or `from None` for `ImportError` lazy-load probes), B007 unused loop vars (2 renamed to `_node_id` / `_subtask`), E402 (4 intentional late imports kept with `# noqa: E402` + rationale comments — circular avoidance + optional-dep probe ordering). Style-preference rules SIM102/103/105/108/116 disabled at project level (`pyproject.toml::[tool.ruff.lint]::ignore`) — the nested-if / try-except / ternary forms read clearer in the agent / pattern code than the SIM-suggested rewrites.
- Pre-commit hook coverage: repo-level `.pre-commit-config.yaml` already runs Black + Ruff against `packages/kaizen-agents/src/`; no per-package config added.

## [0.9.5] — 2026-05-03 — issue #781 hygiene release (T3)

Patch release cutting PyPI for T3 (kaizen-agents TODO-NNN comment-strip) of the issue #781 cleanup workstream.

### Changed (T3 of #781 — comment-only, packages/kaizen-agents/src/)

- Stripped 69 `TODO-NNN` markers across 17 files. Heavy concentration in `agents/autonomous/base.py` (28 hits — state persistence + interrupt handling banners), `runtime_adapters/docs/` (23 hits across architecture-diagram cells + table column headers in 5 files), `patterns/` (15 hits across 11 files), `api/shortcuts.py` (3 hits — verified `ClaudeCodeAdapter` / `OpenAICodexAdapter` / `GeminiCLIAdapter` exist at `runtime_adapters/{claude_code,openai_codex,gemini_cli}.py`; rewrote stale "may not exist yet" notes). Disposition: 27 Class 1a banner / group label / inline-shipped, 33 Class 1b docstring / doc-body provenance, 9 Class 3 mid-comment cross-reference, 0 Class 2.

### Notes

- Comment-only diff: zero changes to imports, signatures, control flow, or types. Three commits (`b9605dde`, `35eebba1`, `37bab09f`) bypassed pre-commit hooks per the documented `git -c core.hooksPath=/dev/null` exception in `rules/git.md` § Pre-Commit Hook Workarounds — Black + Ruff auto-formatters proposed `Optional[X] → X | None` and `Dict → dict` rewrites that exceed T3's comment-only mandate; the type-modernization sweep is flagged as a follow-up workstream (out of T3 scope).

## [0.9.4] - 2026-04-21 — ToolRegistry pre-hydrate eliminates discovery tax (#579)

### Added

- **`ToolHydrator.pre_hydrate_from_query(query, top_k=5)`** — BM25 retrieval over the deferred tool index, seeded with the user's own input. When the hydrator is active (tool count above threshold), the top-K matches are merged into the active set so the LLM sees candidate tools on turn 1. Prior behaviour required a dedicated `search_tools` meta-call on turn 1 before the LLM could emit the real data-tool call on turn 2 — a 25% overhead on an 8-turn budget (issue #579, documented in ImpactVerse/Iris live staging).
- **`AgentLoop.run_turn`** now invokes `pre_hydrate_from_query(user_message, top_k=5)` once per turn before the first LLM completion. `search_tools` remains available as the escape hatch when the BM25 pre-hydrate misses.
- **System prompt addendum** — the default system prompt now tells the LLM it can batch a `search_tools + real_tool` pair in a single tool-call batch when the target name is known, saving the round-trip on models that support parallel tool calls (GPT-4-class).

### Why this is LLM-first compatible

Pre-hydration is **retrieval, not routing or classification**. The framework runs a BM25 scoring pass (documented data operation) and merges results into the visible tool set. The LLM still decides whether to invoke any hydrated tool, which one, and how. `search_tools` is preserved for queries where the pre-hydrate misses — the multi-hop discovery path is unchanged. See `rules/agent-reasoning.md` Permitted Exception 6 (tool-result parsing / retrieval as data operation).

### Behavior change

Tool-call latency drops by ~600ms and turn-budget consumption drops by 25% on the common case where the user's natural-language query contains tokens that BM25 resolves to the correct candidates. Token cost per turn increases slightly (~600 tokens of hydrated tool schemas) — amortized over session length.

### Tests

- 9 new Tier 1 unit tests at `packages/kaizen-agents/tests/unit/delegate/test_tool_hydration.py::TestPreHydrateFromQuery` + `TestAgentLoopCallsPreHydrate` covering: top-K BM25 hits, `top_k` cap, inactive-hydrator no-op, empty-query no-op, no-match no-op, active-set idempotence across repeated queries, `search_tools` escape-hatch preservation, `AgentLoop.run_turn` invocation on active hydrator, and skip on inactive hydrator.

### Cross-SDK

Filed as follow-up for kailash-rs if `DefaultToolHydrator::search` + hot-path wiring shows the same pattern. Rust semantic parity MUST use the same method name and same behavior per `rules/cross-sdk-inspection.md` EATP D6.

Closes #579.

## [0.9.3] - 2026-04-15 — Python 3.14 compatibility

### Fixed

- **`DataFlowConnection.get_table_schema`** previously called `model.__annotations__` directly, which raises `NameError` instead of returning the annotation dict on Python 3.14 when a model uses any string forward reference. Replaced with `kailash.utils.annotations.get_resolved_type_hints(model)`, which evaluates the lazy 3.14 `__annotate__` callable safely and surfaces a clear per-field error if any forward reference is unresolvable.

## [0.7.0] - 2026-04-07

### Added

- **Top-level pattern exports** — All 5 multi-agent pattern classes (`BaseMultiAgentPattern`, `SupervisorWorkerPattern`, `ConsensusPattern`, `DebatePattern`, `HandoffPattern`, `SequentialPipelinePattern`) and 5 factory functions now exported from `kaizen_agents` top-level
- Deprecated `coordination/` module removed; 33 files migrated to `patterns/`

## [0.5.0] - 2026-03-30

### Added

- **ToolCallStart/ToolCallEnd event wiring** — Delegate streaming now emits all 6 defined event types. Applications can pattern-match on `ToolCallStart(name=...)` and `ToolCallEnd(name=..., result=...)` for tool execution visibility (spinners, SSE, progress bars). Closes #159.
- 8 new unit tests for tool call event emission, ordering, error handling, multi-turn, and consumer compatibility.

### Fixed

- **Error message sanitization** — `str(exc)` replaced with `type(exc).__name__` in 5 error paths (`Delegate.run()`, `PrintRunner.run()`, `AgentLoop._run_single()`, `run_interactive()`, `HookManager._run_hook()`). Prevents internal detail leakage (file paths, connection strings) via events and API responses.

### Changed

- `AgentLoop.run_turn()` return type widened to `AsyncGenerator[str | DelegateEvent, None]` (internal API — only consumed by `Delegate.run()`).
- `AgentLoop._execute_tool_calls()` now returns `list[DelegateEvent]` instead of `None`.
- `run_interactive()`, `run_print()`, and `PrintRunner.run()` filter non-string chunks from `run_turn()`.

## [0.4.0] - 2026-03-27

### Added

- **Delegate facade** — `Delegate` class as the primary user-facing API for autonomous AI execution with typed event system, progressive disclosure (Layer 1/2/3), and budget tracking. Closes #114.
- **Incremental streaming** — `AgentLoop.run_turn()` yields text tokens incrementally as they arrive from the model. Closes #115.
- **Multi-provider LLM adapter** — `StreamingChatAdapter` protocol with 4 provider adapters (OpenAI, Anthropic, Google, Ollama). Closes #113.
- **Tool hydration** — `ToolHydrator` with BM25 search for large tool sets (100+ tools). Closes #76.
- **Hook system** — `HookManager` with lifecycle events (PRE/POST tool use, model, session).

## [0.3.0] - 2026-03-25

### Added

- **Structural split**: Absorbed ~44K lines of Layer 2 engine code from kailash-kaizen
- `kaizen_agents.agents/` — 29 specialized agents (ReAct, RAG, ToT, CoT, vision, audio, etc.)
- `kaizen_agents.patterns/` — Multi-agent patterns (debate, supervisor-worker, pipeline, consensus, ensemble)
- `kaizen_agents.journey/` — Journey orchestration with LLM intent detection
- `kaizen_agents.api/` — Canonical async-first Agent API
- `kaizen_agents.workflows/` — Enterprise workflow templates
- `kaizen_agents.coordination/` — Backward-compatibility coordination shims
- `kaizen_agents.integrations/dataflow/` — AI-enhanced database operations
- `kaizen_agents.runtime_adapters/` — Concrete LLM provider adapters
- `kaizen_agents.research_patterns/` — Advanced ML patterns
- Re-exports: `Agent`, `ReActAgent`, `Pipeline` from top-level `kaizen_agents`

### Changed

- Version bump: 0.2.0 → 0.3.0
- Dependency: `kailash-kaizen>=2.3.0` (requires version after structural split)

## [0.2.0] - 2026-03-21

### Added

- Initial release with GovernedSupervisor, Delegate engine, orchestration (planner, protocols, recovery), PACT governance integration
