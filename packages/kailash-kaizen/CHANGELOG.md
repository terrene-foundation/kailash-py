# Changelog

All notable changes to the Kaizen AI Agent Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.10.0] — 2026-04-21 — AgentDiagnostics + TraceExporter → kaizen.observability (#567 PR#6 of 7)

### Added

- **`kaizen.observability.AgentDiagnostics`** — concrete Kaizen-side adapter satisfying the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol. Context-managed agent-run session that captures `TraceEvent` records and produces a `report()` rollup (counts by `event_type`, total cost in integer microdollars, p50/p95 duration, error rate, errored-export count). Signature-free — pure data aggregator; outside `rules/agent-reasoning.md` scope.
- **`kaizen.observability.TraceExporter`** — single-filter-point sink adapter for `TraceEvent` records. Every event stamped with the cross-SDK-locked SHA-256 fingerprint from `kailash.diagnostics.protocols.compute_trace_event_fingerprint` (byte-identical with kailash-rs#468 / v3.17.1+, commit `e29d0bad`). Sinks: `NoOpSink`, `JsonlSink` (append-only JSONL with thread-safe writes), `CallableSink` (sync or async user-supplied callable). No third-party commercial-SDK imports anywhere in the surface per `rules/independence.md`.
- **`BaseAgent.attach_trace_exporter(exporter)` + `BaseAgent.trace_exporter` property** — production hot-path wiring of the exporter. `AgentLoop.run_sync` and `run_async` emit `agent.run.start` and `agent.run.end` TraceEvents through the attached exporter, threading `parent_event_id` from start → end and stamping `duration_ms` + `status`. Fire-and-forget: exporter failures WARN-log and continue so the agent hot path never breaks because a trace sink failed. Closes `rules/orphan-detection.md` §1 for `kaizen.observability`.
- **`kaizen.observability.AgentDiagnosticsReport`** — frozen dataclass shape returned by `AgentDiagnostics.report_dataclass()`; `.to_dict()` matches the `Diagnostic` Protocol's dict-shape contract.
- **`specs/kaizen-observability.md`** — authoritative spec documenting the cross-SDK fingerprint canonicalization contract, BaseAgent wiring surface, tenant-isolation and classification discipline (payload_hash `"sha256:<8-hex>"` per `rules/event-payload-classification.md` §2), security threats subsection, Tier 1 + Tier 2 testing contract, and MLFP attribution history.
- **`specs/diagnostics-catalog.md`** — catalog indexing every `Diagnostic` adapter (`DLDiagnostics`, `RAGDiagnostics`, `AlignmentDiagnostics`, `InterpretabilityDiagnostics`, `LLMJudge` / `LLMDiagnostics`, `AgentDiagnostics`, `GovernanceEngine` extensions) with its Tier 2 wiring-test file name (grep-able per `rules/facade-manager-detection.md` §2), medical-metaphor regression gate, and the additive extension flow for an 8th diagnostic.

### Tests

- **`packages/kailash-kaizen/tests/integration/observability/test_agent_diagnostics_wiring.py`** — 4 Tier 2 tests exercising a real `BaseAgent` + attached `TraceExporter`; asserts start + end events fire via `AgentLoop`, `run_id` stability, `parent_event_id` threading, fingerprint parity with the canonical helper, cost rollup as int microdollars, and short-circuit behaviour when `attach_trace_exporter(None)`.
- **`packages/kailash-kaizen/tests/unit/observability/test_trace_exporter_fingerprint.py`** — 15 Tier 1 tests covering determinism, hex shape, per-field sensitivity of the 6 mandatory fields, canonicalization form (sort-keys, compact separators, `+00:00`, no `Z`), Enum string serialization, `cost_microdollars` MUST-be-int invariant (rejects float, negative, bool), re-export parity, and bounded-counter contract (no unbounded `_events` buffer).

### Cross-SDK Parity

- **kailash-rs#468** (v3.17.1+, commit `e29d0bad`) — the Rust-side `TraceEvent` + `compute_trace_event_fingerprint` pair; 4 round-trip tests green. The Python-side fingerprint contract in this release is byte-identical with the Rust side.
- **kailash-rs#497** — Rust TraceExporter Kaizen-rs wiring tracker; this Python PR integrates against the byte-identical parity locked in kailash-rs#468.

## [2.9.0] — 2026-04-20 — LLMDiagnostics + JudgeCallable → kaizen.judges + kaizen.evaluation split (#567 PR#5 of 7)

### Added

- **`kaizen.judges.LLMJudge`** — concrete Kaizen-side implementation of the cross-SDK `kailash.diagnostics.protocols.JudgeCallable` Protocol (async `__call__(JudgeInput) -> JudgeResult`). Wraps `kaizen_agents.Delegate` so every LLM call routes through the framework's cost tracker + env-sourced model resolution per `rules/framework-first.md` + `rules/env-models.md`. Raw `openai.chat.completions.create` / `litellm.completion` are BLOCKED (`rules/zero-tolerance.md` Rule 4). Structured `Signature(InputField/OutputField)` drives scoring — no regex on LLM output per `rules/agent-reasoning.md` MUST Rule 3.
- **`kaizen.judges.LLMDiagnostics`** — context-managed Diagnostic session satisfying `kailash.diagnostics.protocols.Diagnostic`. Aggregates `llm_as_judge()` / `faithfulness()` / `self_consistency()` / `refusal_calibrator()` into a single `report()` dict with severity banding, polars DataFrame accessors (`judge_df` / `faithfulness_df`), and plotly dashboard (`plot_output_dashboard()`).
- **`kaizen.judges.FaithfulnessJudge`**, **`kaizen.judges.SelfConsistencyJudge`**, **`kaizen.judges.RefusalCalibrator`** — rubric-bound judge wrappers. `SelfConsistencyJudge` shares one `CostTracker` across N independent scorings and surfaces variance statistics (`SelfConsistencyReport`).
- **`kaizen.judges.JudgeBudgetExhaustedError`** — typed error when the judge's integer-microdollar `budget_cap` is hit mid-evaluation. Position-swap bias mitigation plus budget enforcement are routed through a shared `CostTracker` per `rules/tenant-isolation.md` when a `tenant_id` is present.
- **`kaizen.evaluation.ROUGE`**, **`kaizen.evaluation.BLEU`**, **`kaizen.evaluation.BERTScore`** — pure-algorithmic NLP metrics as a **separate namespace** from `kaizen.judges`. Split intentional: judges carry LLM / cost / budget surface; evaluation is lightweight string math. Each metric raises a loud, actionable `ImportError` naming the `[evaluation]` extra if the underlying library is absent per `rules/dependencies.md` "Optional Extras with Loud Failure".
- **New `[judges]` extra**: `bert-score>=0.3.13` + `rouge-score>=0.1.2` + `sacrebleu>=2.4`. Covers the judge runtime's algorithmic fallbacks.
- **New `[evaluation]` extra**: same deps, narrower scope — for users who only want reference-comparison metrics without the judge / cost / budget surface.
- **`specs/kaizen-judges.md`** and **`specs/kaizen-evaluation.md`** — new spec files documenting Protocol conformance contract, public API, cost-budget discipline, position-swap bias mitigation mechanics, security threats, Tier 1 + Tier 2 testing contract, MLFP attribution history. Both referenced from `specs/_index.md`.

### Security

- **No raw openai / litellm imports in `kaizen.judges` / `kaizen.evaluation`** — every LLM call routes through `kaizen_agents.Delegate`.
- **No regex on LLM output for winner selection** — judge verdicts come from structured `OutputField` parsing via Signature. `_parse_score` regex heuristics from the MLFP donor source were replaced with Signature-based extraction.
- **Budget tracking in integer microdollars** — `CostTracker` is the single source of truth; raw USD floats are not accumulated. Cross-SDK parity with `pact.costs.CostTracker`.
- **Typed error on budget exhaustion** — `JudgeBudgetExhaustedError` is raised loud per `rules/zero-tolerance.md` Rule 3 rather than silently returning partial-result dicts that look successful.

### Attribution

- Portions of `LLMJudge` / `LLMDiagnostics` / `FaithfulnessJudge` / `SelfConsistencyJudge` / `RefusalCalibrator` originated in the MLFP diagnostics helpers (`shared/mlfp06/diagnostics/output.py` + `_judges.py`, Apache 2.0) and were re-authored for the Kailash ecosystem with medical-metaphor cleanup, framework-first routing through Delegate, structured Signature scoring, and `run_id` correlation. MLFP donation history recorded in the root `NOTICE` file per Apache-2.0 §4(d) (blocker B4 shipped in #569).

## [2.8.0] — 2026-04-20 — InterpretabilityDiagnostics adapter for open-weight LLM analysis (#567 PR#4 of 7)

### Added

- **`kaizen.interpretability.InterpretabilityDiagnostics` adapter (#567 PR#4 of 7)**: post-hoc interpretability session for local open-weight language models (Llama / Gemma / Phi / Mistral). Satisfies the cross-SDK `kailash.diagnostics.protocols.Diagnostic` Protocol (`run_id` + `__enter__` + `__exit__` + `report()`), so `isinstance(diag, Diagnostic)` holds at runtime for downstream telemetry pipelines. Four analyses expose attention heatmaps (plotly), logit-lens top-`k` predictions per layer (polars DataFrame), scikit-learn linear probes on last-token hidden states, and optional Gemma-Scope SAE feature activations via `sae-lens`. Every per-analysis buffer uses `deque(maxlen=window)` for bounded-memory discipline; `close()` on context exit releases the model and clears CUDA / MPS caches.
- **New `[interpretability]` extra**: `transformers>=4.40,<5.0` + `sae-lens>=3.0`. Plotting methods raise a loud `ImportError` naming the extra if plotly / matplotlib is absent per `rules/dependencies.md` "Optional Extras with Loud Failure". Base-install construction + API-only refusal paths run without the extra installed.
- **`kaizen.interpretability` facade module**: public surface `from kaizen.interpretability import InterpretabilityDiagnostics`. Tier 2 wiring test asserts facade import per `rules/orphan-detection.md` §1.
- **`specs/kaizen-interpretability.md`** — new spec file documenting Protocol conformance contract, public API, VRAM / memory budget guidance, 6 security threats with mitigations, Tier 1 + Tier 2 testing contract, MLFP attribution history. Referenced from `specs/_index.md`.

### Security

- **Local-files-only default** — `from_pretrained(local_files_only=True)` is the default so a diagnostic call NEVER silently downloads multi-GB weights over the network. Operators pass `allow_download=True` explicitly to opt in.
- **No hardcoded HF token** — auth token read from `HF_TOKEN` / `HUGGINGFACE_TOKEN` env vars via `os.environ.get` only.
- **API-only refusal** — `gpt-*` / `o1-*` / `o3-*` / `o4-*` / `claude-*` / `gemini-*` / `deepseek-*` model prefixes are refused with a canonical `{"mode": "not_applicable"}` payload rather than fabricating interpretability readings. Honest failure per `rules/zero-tolerance.md` Rule 2.
- **No raw prompt text in logs** — structured logs carry `interp_run_id` correlation IDs only; `interp_*`-prefixed fields avoid the LogRecord attribute-collision hazard documented in `rules/observability.md` MUST Rule 9.

## [2.7.5] - 2026-04-19 — LlmClient.embed() + trust migration fix + Python 3.14 compatibility (#462 #499 #477)

### Added

- **`LlmClient.embed()` for OpenAI + Ollama (#462, PR #502)**: `LlmClient.embed(texts, *, model)` exposes a first-class embedding API on the existing `LlmClient` surface. Supports OpenAI (`text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`) and Ollama (`nomic-embed-text` and any Ollama-hosted embedding model). Returns a `List[List[float]]` consistent with OpenAI's embedding response shape.

### Fixed

- **LLM endpoint trust migration identifier validation (#499, PR #504)**: `kaizen.llm.migration` used f-string interpolation for identifier names in log and error message paths. All identifier-containing paths now route through `_validate_identifier()` before use.
- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.**

- **Python 3.14 (PEP 649 / PEP 749) silently broke every class-based `Signature`.** `SignatureMeta.__new__` read `namespace.get("__annotations__", {})` to discover `InputField` / `OutputField` declarations. On 3.14 the compiler emits `namespace["__annotate__"]` (a lazy callable) instead of populating `__annotations__` directly, so the metaclass saw `{}`, produced signatures with zero fields, and every dependent `BaseAgent` refused to construct. The fix routes the read through the new shared helper `kailash.utils.annotations.get_namespace_annotations`, which evaluates `__annotate__` (preferring `Format.VALUE`, falling back to `Format.FORWARDREF` on unresolved names) on 3.14 and reads the eager dict on 3.13 and earlier.
- **`kaizen.deploy.introspect.build_card_for`** previously called `getattr(signature_cls, "__annotations__", {})`, which can raise `NameError` instead of returning a default on 3.14 if the signature has any string forward reference. Replaced with `kailash.utils.annotations.get_class_annotations(signature_cls)` so every annotation read in the SDK flows through the one-place handler for 3.13/3.14 differences.
- **`type_introspector`, `core/autonomy/state/types`, `memory/enterprise`, `strategies/single_shot`, `strategies/multi_cycle`** all updated to read class annotations through `kailash.utils.annotations.get_class_annotations`, so PEP 649 forward references are surfaced safely instead of crashing the introspection path.

### Pyright

- `signatures/core.py` cleanup (touched while applying the 3.14 fix): `description: str = None` → `Optional[str] = None`; dropped `ClassVar[…]` on the `_signature_*` attributes that get per-instance overrides; declared `_outputs_list: List[Union[str, List[str]]]` at class scope so the multi-output return type holds; added a `TYPE_CHECKING` import for `SignatureComposition` (defined in `signatures.enterprise`); added narrowing casts at dispatchers where `hasattr` already proves the discriminator.

## [2.7.3] - 2026-04-12 — Post-Convergence Security Hardening

### Security

- **SQL injection fix in `security/audit.py` `query_events()`**: the prior implementation built a raw f-string `WHERE` clause from caller-supplied `event_type` and `agent_id` parameters. These arguments could contain SQL metacharacters, enabling injection via crafted event type strings. Fixed to use parameterized queries; identifier segments validated with `re.match` before interpolation.
- **Audit forwarding with `exc_info=True`**: `logger.error()` calls in `core/autonomy/observability/audit.py` and `security/audit.py` now include `exc_info=True`, ensuring stack traces appear in the log pipeline rather than just the message string. Previously, exceptions were swallowed silently on the audit forwarding path.

### Changed

- **Strategy deprecation warnings**: `async_single_shot.py` and `single_shot.py` now emit `DeprecationWarning` when invoked, directing users to `DelegateEngine` as the canonical async strategy. The single-shot strategies remain functional but are officially deprecated.

## [2.3.0] - 2026-03-25

### Changed

- **Structural split**: Moved ~44K lines of Layer 2 (LLM-dependent) engine code to kaizen-agents package
- Moved modules: agents/, orchestration/ (→patterns/), journey/, api/, workflows/, coordination/, integrations/dataflow/, runtime/adapters/, research patterns
- `from kaizen import Agent` now conditionally resolves to async Agent from kaizen-agents (fallback: CoreAgent)
- kaizen-agents added to root `[kaizen]` optional dependency group

### Deprecated

- `kaizen.agent.Agent` (sync wrapper) — use `kaizen_agents.api.agent.Agent` (async) instead

### Removed

- `kaizen/agents/` — moved to kaizen-agents package
- `kaizen/orchestration/` — moved to kaizen-agents as `patterns/`
- `kaizen/journey/` — moved to kaizen-agents
- `kaizen/api/` — moved to kaizen-agents (canonical async Agent API)
- `kaizen/workflows/` — moved to kaizen-agents
- `kaizen/coordination/` — moved to kaizen-agents
- `kaizen/integrations/dataflow/` — moved to kaizen-agents
- `kaizen/runtime/adapters/` — moved to kaizen-agents as `runtime_adapters/`

## [2.2.0] - 2026-03-24

### LLM-First Autonomous Agents

All autonomous agents now default to MCP tool discovery enabled, and the framework enforces LLM-first reasoning as an absolute directive.

### Changed

- **ReActAgent**: `mcp_discovery_enabled` default changed from `False` to `True`
- **CodeGenerationAgent**: Added `mcp_enabled: bool = True` to config
- **RAGResearchAgent**: Added `mcp_enabled: bool = True` to config
- **SelfReflectionAgent**: Added `mcp_enabled: bool = True` to config (now classified as autonomous)
- Agent Classification updated: 4 autonomous agents (was 3), SelfReflectionAgent promoted

### Removed

- **ReActAgent.\_discover_mcp_tools()**: Removed no-op stub method. MCP discovery flows through `BaseAgent.discover_mcp_tools()` (the real async implementation)

### Fixed

- `test_memory_agent`: Fixed mock provider detection in execution test
- `test_http_transport`: Fixed `base_url` fixture scope conflict with pytest-base-url plugin
- `test_agent_execution_patterns_e2e`: Relaxed content assertions for mock provider compatibility

## [2.1.0] - 2026-03-22

### L3 Autonomy Primitives

Five deterministic SDK primitives enabling agents that spawn child agents, allocate constrained budgets, communicate through typed channels, and execute dynamic task graphs under PACT governance.

### Added

- **`kaizen.l3.envelope`** — EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer (continuous budget tracking, ratio-based division, non-bypassable enforcement)
- **`kaizen.l3.context`** — ScopedContext, ScopeProjection, DataClassification (hierarchical context with projection-based access control and 5-level clearance)
- **`kaizen.l3.messaging`** — MessageChannel, MessageRouter, DeadLetterStore, 6 typed payloads (bounded async channels with priority ordering and 8-step routing validation)
- **`kaizen.l3.factory`** — AgentFactory, AgentInstanceRegistry, AgentSpec, AgentInstance (runtime agent spawning with 6-state lifecycle machine and cascade termination)
- **`kaizen.l3.plan`** — Plan DAG, PlanValidator, PlanExecutor, PlanModification (DAG task graphs with gradient-driven scheduling and 7 typed mutations)
- **`kaizen.agent_config`** — Optional `envelope` field for PACT constraint governance
- **`kaizen.composition.graph_utils`** — Generic cycle detection and topological ordering
- 868 new tests (581 unit + 240 security + 47 integration/E2E)

## [1.2.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **FallbackRouter Error Truncation**: `get_error_summary()` now truncates error messages to 200 characters, matching `execute()` behavior
- **Hardcoded Model Removal**: `BaseAgent._execute_signature` model fallback uses `os.environ` only, no hardcoded `"gpt-4o"`
- **Timestamping Silent Swallows**: 3 bare `except: pass` blocks in RFC 3161 fallback chain replaced with `logger.debug()` calls
- **Stale Tests**: Updated timestamping tests that expected `NotImplementedError` from now-implemented RFC 3161 authority

### Test Results

- Kaizen: 128 fallback-related tests passed, 60 timestamping tests passed

## [1.2.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all Kaizen-specific gaps remediated.

### Added

- **FallbackRouter Safety**: `on_fallback` callback fires before each fallback (raise `FallbackRejectedError` to block), WARNING-level logging on every fallback, model capability validation
- **MCP Session Methods**: `discover_mcp_resources()`, `read_mcp_resource()`, `discover_mcp_prompts()`, `get_mcp_prompt()` wired and functional
- **RFC 3161 Timestamping**: Ed25519 local timestamp authority with clock drift detection and production warnings
- **AgentTeam Deprecation**: Proper `DeprecationWarning` with migration guidance to `OrchestrationRuntime`

### Changed

- **Model Fallback**: `BaseAgent._execute_signature` now reads model from `os.environ` instead of hardcoded `"gpt-4"` fallback
- **Error Truncation**: FallbackRouter truncates error messages to 200 chars to prevent log flooding

### Security

- No hardcoded model names in runtime code (all from environment variables)
- Cryptographically secure nonce generation via `secrets.token_hex(16)`
- V4 audit: 0 CRITICAL findings

### Test Results

- 385 unit tests passed (+1 pre-existing)

## [1.0.0] - 2026-01-25

### Added

#### Phase 7: Production Deployment & GA Release

**TODO-199: Performance Optimization**

- Performance benchmarks suite with 15 comprehensive tests
- Schema caching: ~4.6μs per operation
- Embedding caching: ~17.9μs per operation
- Parallel tool execution: 4.6x speedup over sequential
- Hook parallelization: 8.4x speedup over sequential

**TODO-200: Production Deployment Guides**

- Complete Docker deployment guide with multi-stage builds
- Kubernetes orchestration with health checks and auto-scaling
- Monitoring setup with Prometheus, Grafana, and Loki
- Security hardening documentation

**TODO-201: v1.0 GA Release Validation**

- Comprehensive test suite: 7,400+ unit tests, 226+ integration tests
- Docker image builds and runs successfully
- Fresh pip install verified (kailash-kaizen-1.0.0 installs cleanly)
- Security scan completed (4 documented unfixable vulnerabilities in dependencies)

### Changed

- Version bumped to 1.0.0 (GA release)
- `setup.py` version synchronized with `pyproject.toml` and `__init__.py`
- Semver validation regex updated to accept PEP 440 pre-release format
- HTTP transport tests updated for local development (`allow_insecure=True`)
- Rate limiter fixture converted to `@pytest_asyncio.fixture`

### Fixed

- **OrchestrationRuntime**: Removed incompatible `execution_timeout` parameter from AsyncLocalRuntime initialization
- **Governance datetime comparison**: Fixed offset-naive/aware datetime comparison in `timeout_pending_approvals()`
- **Planning agent response extraction**: Enhanced nested response parsing for Ollama models
- **Rate limiter async fixture**: Corrected decorator for pytest-asyncio compatibility
- **Missing dependencies**: Added motor (MongoDB async driver) and trio (async library)

### Security

- Security scan performed with pip-audit
- 4 remaining unfixable vulnerabilities documented:
  - ecdsa: No fix available (low severity)
  - mcp: Version pinned by kailash (acceptable risk)
  - protobuf: No fix version available (low severity)
  - py: Legacy package (acceptable risk)

---

## [1.0.0b1] - 2026-01-24

### Added

#### Phase 6: Autonomous Execution Layer (922+ tests)

Complete implementation of autonomous agent capabilities enabling Claude Code-level functionality.

**TODO-190: Native Tool System**

- `BaseTool`: Abstract base for all native tools with schema generation
- `NativeToolResult`: Standardized result format with success/error handling
- `KaizenToolRegistry`: Central registry with category-based registration
- `DangerLevel`: 5-level danger classification (SAFE, LOW, MEDIUM, HIGH, CRITICAL)
- 7 file tools: ReadFileTool, WriteFileTool, EditFileTool, GlobTool, GrepTool, ListDirectoryTool, FileExistsTool
- 2 search tools: WebSearchTool, WebFetchTool
- 1 bash tool: BashTool with sandboxing support

**TODO-191: Runtime Abstraction Layer**

- `RuntimeAdapter`: Abstract base class for runtime adapters
- `LocalKaizenAdapter`: Native Kaizen runtime for autonomous execution
- `RuntimeSelector`: Automatic adapter selection based on context
- Plugin system for custom runtime adapters

**TODO-192: LocalKaizenAdapter - TAOD Loop (371 tests)**

- Think → Act → Observe → Decide autonomous execution loop
- Tool call management with approval workflows
- Cycle detection and prevention
- Error recovery with automatic retry
- Execution metrics and performance tracking

**TODO-193: Memory Provider Interface (112 tests)**

- `MemoryProvider`: Abstract interface for memory backends
- `InMemoryProvider`: Default in-memory storage
- `HierarchicalMemory`: Hot/Warm/Cold tier system
- Memory search and retrieval with relevance scoring
- Configurable retention policies

**TODO-194: Multi-LLM Routing (145 tests)**

- `LLMRouter`: Intelligent routing across LLM providers
- `TaskAnalyzer`: Task complexity analysis for routing decisions
- `FallbackRouter`: Automatic failover on provider errors
- `RoutingRule`: Configurable routing policies
- Provider capability detection and matching

**TODO-195: Unified Agent API (217 tests)**

- `Agent`: Single class supporting all capability combinations
- `ExecutionMode`: SINGLE, MULTI, AUTONOMOUS modes
- `MemoryDepth`: STATELESS, SESSION, PERSISTENT, HIERARCHICAL
- `ToolAccess`: NONE, READ_ONLY, READ_WRITE, FULL
- `AgentResult`: Standardized execution results with tool call records
- `CapabilityPresets`: 9 pre-configured capability sets
- Progressive configuration from 2-line quickstart to expert mode

**TODO-196: External Runtime Adapters**

- Claude SDK adapter for Claude Code integration
- OpenAI adapter for GPT-based agents
- Extensible adapter architecture

#### Phase 6.5: Enterprise-App Enablement (530+ tests)

**TODO-202: Specialist System - ADR-013 (107 tests)**

- `SpecialistDefinition`: Type-safe specialist definitions
- `SkillDefinition`: Skill specifications with triggers
- `SpecialistRegistry`: Central registry with discovery
- Built-in specialists: sdk-navigator, pattern-expert, testing-specialist
- Plugin architecture for custom specialists

**TODO-203: Task/Skill Tools (132 tests)**

- `TaskTool`: Spawn subagent specialists
- `SkillTool`: Invoke reusable skills
- Background execution with TaskOutput retrieval
- Shared state management between tools

**TODO-204: Enterprise-App Streaming (291 tests)**

- 10 streaming event types for real-time progress
- `StreamingExecutor`: Async streaming execution
- Event buffering and batching
- WebSocket and SSE transport support

#### Phase 6.6: Claude Code Tool Parity (214 tests)

**TODO-207: Full Tool Parity with Claude Code**

- `TodoWriteTool`: Structured task list management
- `NotebookEditTool`: Jupyter notebook cell editing
- `AskUserQuestionTool`: Bidirectional user communication
- `EnterPlanModeTool`: Plan mode workflow entry
- `ExitPlanModeTool`: Plan mode with approval workflow
- `KillShellTool`: Background process termination
- `TaskOutputTool`: Background task output retrieval
- **19 total native tools** via KaizenToolRegistry
- `PlanModeManager`: Coordinated planning tool state
- `ProcessManager`: Background task tracking

**Documentation**

- Unified Agent API Guide: `docs/developers/05-unified-agent-api-guide.md`
- Claude Code Parity Tools Guide: `docs/developers/08-claude-code-parity-tools-guide.md`

### Changed

- Default version updated to 1.0.0b1 (beta release)
- `Agent` class now primary entry point (replaces `BaseAgent` for new code)
- Tool registry now supports 7 categories: file, bash, search, agent, interaction, planning, process

### Fixed

- Timeout error message format in AskUserQuestionTool (includes "timeout" keyword)
- Metadata passthrough in AskUserQuestionTool when no callback configured

---

## [0.8.0] - 2025-12-16

### Added

#### Enterprise Agent Trust Protocol (EATP)

Complete implementation of cryptographically verifiable trust chains for AI agents.

**Phase 1: Foundation & Single Agent Trust (Weeks 1-4)**

- `TrustLineageChain`: Complete trust chain data structure
- `GenesisRecord`: Cryptographic proof of agent authorization
- `CapabilityAttestation`: What agents are authorized to do
- `DelegationRecord`: Trust transfer between agents
- `ConstraintEnvelope`: Limits on agent behavior
- `AuditAnchor`: Tamper-proof action records
- `TrustOperations`: ESTABLISH, DELEGATE, VERIFY, AUDIT operations
- `PostgresTrustStore`: Persistent trust chain storage
- `OrganizationalAuthorityRegistry`: Authority lifecycle management
- `TrustKeyManager`: Ed25519 key management
- `TrustedAgent`: BaseAgent with automatic trust verification
- `TrustedSupervisorAgent`: Delegation to worker agents

**Phase 2: Multi-Agent Trust (Weeks 5-8)**

- `AgentRegistry`: Central registry for agent discovery
- `AgentHealthMonitor`: Background health monitoring
- `SecureChannel`: End-to-end encrypted messaging
- `MessageVerifier`: Multi-step message verification
- `InMemoryReplayProtection`: Replay attack prevention
- `TrustExecutionContext`: Trust state propagation
- `TrustPolicyEngine`: Policy-based trust evaluation
- `TrustAwareOrchestrationRuntime`: Trust-aware workflow execution

**Phase 3: Enterprise Features (Weeks 9-12)**

- `A2AService`: FastAPI A2A protocol service
- `AgentCardGenerator`: A2A Agent Card with trust extensions
- `JsonRpcHandler`: JSON-RPC 2.0 handler
- `A2AAuthenticator`: JWT-based authentication
- `EnterpriseSystemAgent` (ESA): Proxy for legacy systems
- `DatabaseESA`: SQL database ESA (PostgreSQL, MySQL, SQLite)
- `APIESA`: REST API ESA with OpenAPI support (see details below)
- `ESARegistry`: ESA discovery and management
- `TrustChainCache`: LRU cache with TTL (100x+ speedup)
- `CredentialRotationManager`: Periodic key rotation
- `TrustSecurityValidator`: Input validation and sanitization
- `SecureKeyStorage`: Encrypted key storage (Fernet)
- `TrustRateLimiter`: Per-authority rate limiting
- `SecurityAuditLogger`: Security event logging

**APIESA - REST API Enterprise System Agent (2025-12-15)**

Production-ready ESA for trust-aware REST API integration:

_Core Features:_

- OpenAPI/Swagger spec parsing with automatic capability generation
- HTTP operations: GET, POST, PUT, DELETE, PATCH with full async support
- Rate limiting: per-second, per-minute, per-hour with sliding window
- Request/response audit logging with circular buffer (last 1000 requests)
- Flexible authentication: Bearer tokens, API keys, custom headers

_Trust Integration:_

- Full `EnterpriseSystemAgent` inheritance
- `discover_capabilities()`, `execute_operation()`, `validate_connection()`
- Trust establishment and capability delegation support

_Error Handling:_

- Timeout, request, and connection error handling
- Missing parameter validation
- Rate limit exceeded errors with detailed context

_Documentation:_

- API Reference: `docs/trust/esa/APIESA.md`
- Quick Reference: `docs/trust/esa/APIESA_QUICK_REFERENCE.md`
- Example: `examples/trust/esa_api_example.py`
- 33 unit tests in `tests/unit/trust/esa/test_apiesa.py`

**Performance Targets Met**

- VERIFY QUICK: <1ms (target <5ms)
- VERIFY STANDARD: <5ms (target <50ms)
- VERIFY FULL: <50ms (target <100ms)
- Cache hit: <0.5ms (100x+ speedup)

**Testing**

- 691 total tests (548 unit + 143 integration)
- NO MOCKING policy for Tier 2-3 tests
- Real PostgreSQL infrastructure testing

**Documentation**

- API Reference: `docs/api/trust.md`
- Migration Guide: `docs/guides/eatp-migration-guide.md`
- Security Best Practices: `docs/guides/eatp-security-best-practices.md`
- 10 usage examples in `examples/trust/`

### Changed

- `BaseAgent` now supports optional trust verification via `TrustedAgent` subclass
- Orchestration runtime can be trust-aware via `TrustAwareOrchestrationRuntime`

### Fixed

- SecurityEventType enum now includes rotation events
- APIESA capability name generation fixed for path parameters
- Integration tests now use real implementations (NO MOCKING)

---

## [0.1.x] - Previous Releases

See individual release notes for earlier versions.

---

## Migration

To upgrade from 0.7.x to 0.8.0, see the [EATP Migration Guide](docs/guides/eatp-migration-guide.md).

Key changes:

- New `kaizen.trust` module with all EATP components
- Optional trust verification for existing agents
- Backward compatible - existing `BaseAgent` code works unchanged

## Links

- [Documentation](https://docs.kailash.dev/kaizen)
- [GitHub](https://github.com/terrene-foundation/kailash-py)
- [Issues](https://github.com/terrene-foundation/kailash-py/issues)
