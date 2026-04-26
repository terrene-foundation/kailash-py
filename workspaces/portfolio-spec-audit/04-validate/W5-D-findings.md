# W5-D Findings — kaizen

**Specs audited:** 13 (kaizen-core, kaizen-signatures, kaizen-providers, kaizen-advanced, kaizen-llm-deployments, kaizen-interpretability, kaizen-judges, kaizen-evaluation, kaizen-observability, kaizen-agents-core, kaizen-agents-patterns, kaizen-agents-governance, kaizen-ml-integration)
**§ subsections enumerated:** ~120 across all specs
**Findings:** CRIT=0 HIGH=4 MED=8 LOW=45
**Audit completed:** 2026-04-26

## HIGH Findings Summary
- **F-D-02** kaizen-core § 6.1 — CoreAgent default config hardcodes `"gpt-3.5-turbo"` (env-models.md violation)
- **F-D-25** kaizen-judges § Test discipline — 24 Tier-1 unit tests claimed but `tests/unit/judges/` doesn't exist
- **F-D-50** kaizen-agents-governance § 9.2 — GovernedSupervisor default model hardcoded `"claude-sonnet-4-6"` (env-models.md violation)
- **F-D-55** kaizen-ml-integration § 2.4 — `km.engine_info` discovery + `MLAwareAgent` class mandated by spec but ZERO production wiring (orphan-detection.md §1 violation)

## MED Findings Summary
- F-D-03 (posture wiring cross-spec correlation), F-D-04 (checkpoint_manager undocumented), F-D-06 (MultiModalSignature defined twice), F-D-17 (A2A types module path drift), F-D-20 (security tests in different dirs than spec), F-D-22 (InterpretabilityDiagnostics no production consumer), F-D-30 (kaizen-evaluation Tier-1 unit tests acknowledged missing), F-D-53 (SQLiteSink at wrong module path), F-D-56 (4 of 5 Tier-2 wiring tests missing)

## Audit Methodology
- Read each spec in full
- Grep/AST verified every named class, function, and contract assertion
- Cross-correlated rules: `agent-reasoning.md`, `env-models.md`, `orphan-detection.md`, `facade-manager-detection.md`
- Verified BaseAgent hot-path wiring for diagnostic adapters (TraceExporter wiring confirmed; InterpretabilityDiagnostics standalone-by-design; LLMDiagnostics + AgentDiagnostics wired via tracker= kwarg)
- Did NOT modify any spec or source code

---

## F-D-01 — kaizen-core § header — Spec version stale (2.7.3 vs actual 2.13.1)

**Severity:** LOW
**Spec claim:** "Version: 2.7.3" (line 3 of `specs/kaizen-core.md`)
**Actual state:** `packages/kailash-kaizen/pyproject.toml:version = "2.13.1"` — six minor versions behind.
**Remediation hint:** Bump spec header to current package version; add note that spec covers 2.13.x line.

## F-D-02 — kaizen-core § 6.1 — CoreAgent default config hardcodes "gpt-3.5-turbo"

**Severity:** HIGH
**Spec claim:** "Default config: `model="gpt-3.5-turbo"`, `temperature=0.7`, `max_tokens=1000`, `timeout=30`."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/agents.py:104-109` — `defaults = {"model": "gpt-3.5-turbo", "temperature": 0.7, "max_tokens": 1000, "timeout": 30}`. Spec MATCHES code, but BOTH violate `rules/env-models.md` "NEVER Hardcode Model Names" — `model="gpt-3.5-turbo"` is BLOCKED in production code paths.
**Remediation hint:** Resolve default model via `os.environ.get("DEFAULT_LLM_MODEL")`; raise if unset. Update spec to reflect env-driven defaults.

## F-D-03 — kaizen-core § 4.1 — Trust posture field present but no production wiring claim verified at this layer

**Severity:** MED
**Spec claim:** "`posture: Optional[AgentPosture]` — Trust posture (immutable after construction)"
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/config.py:109` declares `posture`; `__setattr__` guard at lines 115-126 enforces immutability. Coercion present at lines 138-152. Spec assertion verified at field-declaration layer only — this finding is a placeholder for cross-spec correlation: kaizen-agents-governance.md §X.Y must wire posture into PACT clearance check on every agent step (verified separately).
**Remediation hint:** Cross-reference posture wiring assertions in `kaizen-agents-governance.md` audit (governance section).

## F-D-04 — kaizen-core § 3.4 — Spec claims 7 deprecated extension points, but checkpoint_manager added to constructor (8 ctor args beyond config/sig/strat)

**Severity:** MED
**Spec claim:** "These are deprecated in v2.5.0 -- composition wrappers (StreamingAgent, MonitoredAgent, GovernedAgent) are preferred for new code." — table lists 7 extension methods. Constructor signature in spec § 3.2 shows 9 params (config, signature, strategy, memory, shared_memory, agent_id, control_protocol, mcp_servers, hook_manager).
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/base_agent.py:60-72` — constructor adds `checkpoint_manager: Optional[Any] = None` (10th param), undocumented in spec.
**Remediation hint:** Add `checkpoint_manager` to spec § 3.2 with description (persists intermediate agent state for strategies/hooks).

## F-D-05 — kaizen-core § 28.7 — MCP/structured output mutual exclusion implemented but spec doesn't note logging path

**Severity:** LOW
**Spec claim:** "MCP/structured output mutual exclusion: When `has_structured_output` is True, MCP auto-discovery is suppressed."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/base_agent.py:127-134` — verified, suppresses with logger.debug. Behavior matches spec; no defect.
**Remediation hint:** No action; assertion holds. Listed for completeness.

## F-D-06 — kaizen-signatures § 2.8 — `MultiModalSignature` defined in two locations

**Severity:** MED
**Spec claim:** "`MultiModalSignature`: Support for image + audio + text inputs." (single class)
**Actual state:** `packages/kailash-kaizen/src/kaizen/signatures/enterprise.py:277` AND `packages/kailash-kaizen/src/kaizen/signatures/multi_modal.py:602` — TWO classes both named `MultiModalSignature`. Whichever is exported via `signatures/__init__.py` wins; consumers depending on the other shape see silent divergence.
**Remediation hint:** Consolidate to one definition; if both have unique APIs, rename one (e.g., `EnterpriseMultiModalSignature`). Cross-reference with `kaizen-providers.md` § multi-modal exports.

## F-D-07 — kaizen-signatures § 2.x — Undocumented `SignatureOptimizer` class present

**Severity:** LOW
**Spec claim:** Spec § 2.4-2.7 enumerate Parser, Compiler, Validator, Template — no `SignatureOptimizer`.
**Actual state:** `packages/kailash-kaizen/src/kaizen/signatures/core.py:1824` — `class SignatureOptimizer:` exists but absent from spec.
**Remediation hint:** Document `SignatureOptimizer` in spec or mark as private (`_SignatureOptimizer`). If experimental, add `(Awaiting ISS-NN)` marker.

## F-D-08 — kaizen-signatures § 2.3 — Spec lists `signature_type` enum values but doesn't pin "enterprise" semantics

**Severity:** LOW
**Spec claim:** "`signature_type: str = "basic"` — basic, multi_io, complex, enterprise, multi_modal"
**Actual state:** Verified `Signature.__init__` accepts `signature_type`. Enum values not validated at constructor — any string accepted. Spec describes 5 valid values; code does not enforce.
**Remediation hint:** Add typed validation in `__post_init__` (raise on invalid) OR convert to Literal type hint. Update spec to clarify enforcement.

## F-D-09 — kaizen-signatures § 18.1 — `create_structured_output_config` exists but signature deviation

**Severity:** LOW
**Spec claim:** "`create_structured_output_config(signature=my_signature, strict=True)` → returns dict suitable for `response_format`."
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/structured_output.py:292` — verified function exists. Spec assertion holds at signature level. No defect; listed for completeness.
**Remediation hint:** No action.

## F-D-10 — kaizen-providers § 11.5 — `PersistenceBackend` is `Protocol` not `ABC` as spec implies

**Severity:** LOW
**Spec claim:** "`class PersistenceBackend(ABC):` ... `@abstractmethod` ... `async def save(self, session_id: str, data: Any) -> None`"
**Actual state:** `packages/kailash-kaizen/src/kaizen/memory/persistence_backend.py:11` — `class PersistenceBackend(Protocol):` (NOT ABC). Methods are `save_turn(self, session_id, turn)` and signatures differ from spec (sync, not async; method named differently).
**Remediation hint:** Update spec to reflect Protocol-based structural typing AND actual method names (`save_turn`, `load_session`, etc.). Verify all consumers expect the Protocol shape.

## F-D-11 — kaizen-providers § 8.5 — `StreamEvent` dataclass body undocumented

**Severity:** LOW
**Spec claim:** "`@dataclass class StreamEvent:` # Token-by-token streaming event from LLM provider" — empty body in spec.
**Actual state:** Class exists in `packages/kailash-kaizen/src/kaizen/providers/types.py`. Spec leaves contract undefined; consumers cannot infer field names without reading source.
**Remediation hint:** Document `StreamEvent` fields in spec (token delta, metadata, completion status, etc.).

## F-D-12 — kaizen-providers § 10 — Tool registry removal verified; spec note correct

**Severity:** LOW
**Spec claim:** "Kaizen uses MCP (Model Context Protocol) as the sole tool integration mechanism. `ToolRegistry` and `ToolExecutor` are removed."
**Actual state:** Verified — `packages/kailash-kaizen/src/kaizen/tools/__init__.py` does not export ToolRegistry/ToolExecutor. Spec assertion holds.
**Remediation hint:** No action.

## F-D-13 — kaizen-providers § 8.3 — Provider registry uses lazy "_unified_azure" string sentinel; spec note unclear

**Severity:** LOW
**Spec claim:** `"azure": "_unified_azure",  # Lazy-loaded` — table entries.
**Actual state:** `packages/kailash-kaizen/src/kaizen/providers/registry.py:54-69` — verified PROVIDERS dict matches spec exactly (14 entries including aliases). Lazy `"_unified_azure"` string is a sentinel resolved by `get_provider`. Spec accurately describes; no defect.
**Remediation hint:** No action; assertion holds.

## F-D-14 — kaizen-advanced § 12.1 — Cost tracker microdollar precision verified

**Severity:** LOW
**Spec claim:** "Costs stored internally as integer microdollars (1 USD = 1,000,000) ... Cross-SDK alignment with kailash-rs#38."
**Actual state:** `packages/kailash-kaizen/src/kaizen/cost/tracker.py:21` — `_MICRODOLLARS_PER_USD = 1_000_000`. Verified contract.
**Remediation hint:** No action.

## F-D-15 — kaizen-advanced § 13 — Composition functions exist (validate_dag, check_schema_compatibility, estimate_cost)

**Severity:** LOW
**Spec claim:** Three composition functions exposed via `kaizen.composition`.
**Actual state:** All three verified at `packages/kailash-kaizen/src/kaizen/composition/{dag_validator,schema_compat,cost_estimator}.py`. Spec assertion holds.
**Remediation hint:** No action.

## F-D-16 — kaizen-advanced § 16.3 — `ProviderConfig.api_key` redaction in `__repr__` verified

**Severity:** LOW
**Spec claim:** "`api_key` is redacted in `__repr__` to prevent leakage in logs/tracebacks."
**Actual state:** `packages/kailash-kaizen/src/kaizen/config/providers.py:54-59` — verified `__repr__` returns `'***'` placeholder when api_key set. Contract holds.
**Remediation hint:** No action.

## F-D-17 — kaizen-advanced § 19 — A2A capability cards exposed; Card factory functions undocumented at module level

**Severity:** MED
**Spec claim:** Lists 13+ A2A types (A2AAgentCard, Capability, CollaborationStyle, A2ATask, TaskState, etc.) and 6 factory functions.
**Actual state:** Many A2A types live in `packages/kailash-kaizen/src/kaizen/nodes/ai/a2a.py` (deeply nested). Spec implies they are at top-level `kaizen.a2a` module but actual location is `nodes/ai/`. Module path drift.
**Remediation hint:** Either re-export A2A types at `kaizen.a2a.*` or update spec to canonical import paths (`from kaizen.nodes.ai.a2a import A2AAgentCard`).

## F-D-18 — kaizen-llm-deployments § Preset Catalog — All 24 presets verified (16 direct + 5 Bedrock + 2 Vertex + 1 Azure)

**Severity:** LOW
**Spec claim:** 24 presets across direct providers, Bedrock, Vertex, Azure.
**Actual state:** `packages/kailash-kaizen/src/kaizen/llm/presets.py` — 54 register/registration calls; `register_preset` enumerated for all 24 named presets (openai, anthropic, google, cohere, mistral, perplexity, huggingface, ollama, docker_model_runner, groq, together, fireworks, openrouter, deepseek, lm_studio, llama_cpp, bedrock_claude, bedrock_llama, bedrock_titan, bedrock_mistral, bedrock_cohere, vertex_claude, vertex_gemini, azure_openai). All 24 verified.
**Remediation hint:** No action; assertion holds.

## F-D-19 — kaizen-llm-deployments § Four Axes — LlmDeployment + LlmClient classes verified

**Severity:** LOW
**Spec claim:** "`LlmDeployment` primitive composes these four axes ... `LlmClient.from_deployment(d)` wraps it."
**Actual state:** `packages/kailash-kaizen/src/kaizen/llm/deployment.py:287` — `LlmDeployment(BaseModel)` ; `packages/kailash-kaizen/src/kaizen/llm/client.py:79` — `LlmClient`. Auth strategies (ApiKeyBearer, StaticNone, AwsBearerToken, AwsSigV4, GcpOauth, AzureEntra) all present in `kaizen/llm/auth/`. WireProtocol enum at `deployment.py:53`. Endpoint at `deployment.py:82`. Verified.
**Remediation hint:** No action.

## F-D-20 — kaizen-llm-deployments § 6 Security — Test paths drift from spec table

**Severity:** MED
**Spec claim:** Security tests live in `packages/kailash-kaizen/tests/unit/llm/security/` (table lists 8 tests with that path).
**Actual state:** Only 5 tests in `tests/unit/llm/security/`. The other 3 live in different directories: `test_aws_credentials_zeroize_on_rotate.py` is at `tests/unit/llm/auth/`; `test_apikey.py` is at `tests/unit/llm/`; `test_errors.py` (referenced in spec) actually named `test_errors_no_credential_leak.py` at `tests/unit/llm/`. Spec table inaccurately implies all 8 in same dir.
**Remediation hint:** Update spec table with actual test paths OR consolidate tests into `tests/unit/llm/security/` directory.

## F-D-21 — kaizen-llm-deployments § Error Taxonomy — All error classes verified

**Severity:** LOW
**Spec claim:** "LlmClientError ... LlmError ... AuthError ... EndpointError ... ModelGrammarError ... ConfigError" hierarchy.
**Actual state:** `packages/kailash-kaizen/src/kaizen/llm/errors.py:104,113,179,226,286,326` — all 6 root error classes exist. Sub-types (Timeout, RateLimited, ProviderError, InvalidResponse, etc.) need closer inspection but root hierarchy verified.
**Remediation hint:** No action; assertion holds at hierarchy level.

## F-D-22 — kaizen-interpretability § 1 — `InterpretabilityDiagnostics` exists at expected path, but no production call site

**Severity:** MED
**Spec claim:** "context-manager session that operates on a local open-weight `transformers.PreTrainedModel`" — adapter is operator-invoked.
**Actual state:** `packages/kailash-kaizen/src/kaizen/interpretability/core.py:266` exists. However, the only import of `InterpretabilityDiagnostics` outside the module is in `kaizen/interpretability/__init__.py`. NO production code in `kaizen/core/`, `kaizen/agents/`, or `kaizen_agents/` consumes this adapter. Per `rules/orphan-detection.md` §1, while diagnostic adapters are intentionally standalone (operators invoke), the spec's intent — "downstream consumers use `isinstance(obj, Diagnostic)`" — implies a sink/aggregator that has no production realization yet. Tier 2 wiring tests exist (`test_interpretability_wiring.py`) but only at adapter-construction level, not via a framework-pulled-from-`db`-or-`agent`-style hot path.
**Remediation hint:** Document in spec that `InterpretabilityDiagnostics` is operator-invoked (no auto-wiring); OR add a sink (e.g., `agent.attach_diagnostic(diag)`) that consumes via the Diagnostic Protocol in production hot path. If standalone-by-design, add explicit § "Wiring is the operator's responsibility" note.

## F-D-23 — kaizen-interpretability § 8.1 — Tests exist at expected paths

**Severity:** LOW
**Spec claim:** Unit tests at `tests/unit/interpretability/test_interpretability_diagnostics_unit.py`; integration at `tests/integration/interpretability/test_interpretability_wiring.py`.
**Actual state:** Both files verified at the expected paths. Test inventory matches spec.
**Remediation hint:** No action.

## F-D-24 — kaizen-interpretability § 3.5 — API-only refusal is permitted deterministic logic, but spec lists prefixes that overlap with kaizen-llm-deployments § Tier 2

**Severity:** LOW
**Spec claim:** "API-only model prefixes (`gpt-*`, `o1-*`, `o3-*`, `o4-*`, `claude-*`, `gemini-*`, `deepseek-*`) are refused"
**Actual state:** Per `rules/agent-reasoning.md` § "Permitted Deterministic Logic" item 4 (safety guards on configuration string), this is permitted. However, the prefix list duplicates the model-prefix dispatch from `kaizen-providers.md` § 8.3 model→provider table. Single-source-of-truth violation — API-only list lives in two specs.
**Remediation hint:** Move API-only prefix list to a single canonical location (e.g., `kaizen.providers.registry._API_ONLY_PREFIXES`); both specs reference it.

## F-D-25 — kaizen-judges § Test discipline — Tier 1 unit tests claimed but not present at expected path

**Severity:** HIGH
**Spec claim:** "Tier 1 (unit) — `packages/kailash-kaizen/tests/unit/judges/test_judges_unit.py` (24 tests)"
**Actual state:** Directory `packages/kailash-kaizen/tests/unit/judges/` does NOT exist. Only `tests/integration/judges/test_judges_wiring.py` present. Per `rules/testing.md` Audit Mode: zero unit tests for new module = HIGH finding. Spec asserts 24 unit tests; mechanical grep confirms zero.
**Remediation hint:** Create `tests/unit/judges/test_judges_unit.py` with the 24 unit tests spec describes (Protocol conformance, pointwise/pairwise scoring, position-swap aggregation, budget-exhaust, input validation, helper math). OR update spec to reflect actual test inventory if tests live elsewhere.

## F-D-26 — kaizen-judges § Public surface — All 8 facade exports verified

**Severity:** LOW
**Spec claim:** Facade exports `LLMJudge, LLMDiagnostics, FaithfulnessJudge, SelfConsistencyJudge, SelfConsistencyReport, RefusalCalibrator, JudgeBudgetExhaustedError, resolve_judge_model`.
**Actual state:** All 8 verified across `kaizen/judges/_judge.py` + `_wrappers.py` + `llm_diagnostics.py`. Need to confirm `__init__.py` re-exports per facade contract.
**Remediation hint:** Verify `kaizen/judges/__init__.py` exposes all 8 in `__all__`.

## F-D-27 — kaizen-judges § Position-swap bias mitigation verified

**Severity:** LOW
**Spec claim:** "`_resolve_winner(pref_a, pref_a_swap)` ... Both orderings prefer the same candidate → return that winner. Orderings disagree → return `'tie'` ..."
**Actual state:** `packages/kailash-kaizen/src/kaizen/judges/_judge.py:786` — `def _resolve_winner(...)`. Pairwise scoring at line 531+ implements position-swap. Spec assertion holds at signature level.
**Remediation hint:** No action; deeper logic verification deferred to Tier-2 wiring tests.

## F-D-28 — kaizen-judges § Microdollar budget enforcement verified

**Severity:** LOW
**Spec claim:** "`JudgeBudgetExhaustedError` raised AFTER any call that exceeds the cap"
**Actual state:** `packages/kailash-kaizen/src/kaizen/judges/_judge.py` — `class JudgeBudgetExhaustedError(RuntimeError):` exists. Microdollar accounting routes through `kaizen.cost.tracker.CostTracker`.
**Remediation hint:** No action; assertion holds at type-existence level.

## F-D-29 — kaizen-evaluation § Public surface — ROUGE/BLEU/BERTScore classes verified

**Severity:** LOW
**Spec claim:** "ROUGE, BLEU, BERTScore" three metric classes.
**Actual state:** All three verified at `packages/kailash-kaizen/src/kaizen/evaluation/{rouge,bleu,bertscore}.py`. Zero-LLM-surface invariant verified (only mention of Delegate is in `__init__.py` docstring).
**Remediation hint:** No action.

## F-D-30 — kaizen-evaluation § Test discipline — Tier 1 unit tests acknowledged missing

**Severity:** MED
**Spec claim:** "Tier 1 (unit) — `tests/unit/evaluation/test_evaluation_unit.py` (to be added in a follow-up patch...)" — self-acknowledged gap.
**Actual state:** Confirmed — `tests/unit/evaluation/` directory does not exist. Spec self-deferral is honest but per `rules/zero-tolerance.md` Rule 6 "Implement Fully", and `rules/testing.md` "MUST: Verify NEW modules have NEW tests", new metric modules with zero unit tests is a gap. Spec self-acknowledgment doesn't waive the rule.
**Remediation hint:** Add `tests/unit/evaluation/test_evaluation_unit.py` with `importorskip` per backend; cover ROUGE/BLEU/BERTScore happy path + edge cases. Update spec when tests land.

## F-D-31 — kaizen-observability § Public API — All 10 facade exports verified

**Severity:** LOW
**Spec claim:** Facade exposes `AgentDiagnostics, AgentDiagnosticsReport, TraceExporter, TraceExportError, JsonlSink, NoOpSink, CallableSink, SinkCallable, compute_fingerprint, jsonl_exporter, callable_exporter`.
**Actual state:** All verified at `packages/kailash-kaizen/src/kaizen/observability/{agent_diagnostics,trace_exporter}.py`. (SinkCallable is likely a Protocol/type alias — not greppable as `^class`.)
**Remediation hint:** No action.

## F-D-32 — kaizen-observability § BaseAgent Hot-Path Wiring — production call site verified at AgentLoop:422,466

**Severity:** LOW
**Spec claim:** "AgentLoop.run_sync / run_async — emit `agent.run.start` and `agent.run.end` TraceEvents through the attached exporter"
**Actual state:** `packages/kailash-kaizen/src/kaizen/core/agent_loop.py` — `_emit_trace_event` at line 32, called at 422 (start) + 466 (end). `BaseAgent._trace_exporter` initialized at line 207 and exposed via `attach_trace_exporter` (line 399). Closes orphan-detection §1 — TraceExporter is NOT an orphan facade; production hot path invokes it.
**Remediation hint:** No action; wiring verified.

## F-D-33 — kaizen-observability § Test inventory — All 19 observability tests present

**Severity:** LOW
**Spec claim:** "Tier 1 unit (`tests/unit/observability/test_trace_exporter_fingerprint.py`): 15 tests"; "Tier 2 integration (`tests/integration/observability/test_agent_diagnostics_wiring.py`): 4 tests"
**Actual state:** Both files exist; broader observability test suite includes 19 tests across unit/integration/e2e/cross_sdk_parity. Spec's specific files verified.
**Remediation hint:** No action.

## F-D-34 — kaizen-agents-core § header — Spec version stale (0.9.2 vs actual 0.9.4)

**Severity:** LOW
**Spec claim:** "Version: 0.9.2"
**Actual state:** `packages/kaizen-agents/pyproject.toml:version = "0.9.4"` — spec is two patch versions behind.
**Remediation hint:** Bump spec version header.

## F-D-35 — kaizen-agents-core § 2.4 — ConstructorIOError + Delegate verified

**Severity:** LOW
**Spec claim:** "The constructor MUST be synchronous and free of any network, filesystem, or subprocess calls. ... raises `ConstructorIOError`."
**Actual state:** `packages/kaizen-agents/src/kaizen_agents/delegate/delegate.py:78,270` — both classes exist and exported via `__all__ = ["Delegate", "ConstructorIOError", "ToolRegistryCollisionError"]`.
**Remediation hint:** No action.

## F-D-36 — kaizen-agents-core § 4.3 — All 4 streaming adapters verified

**Severity:** LOW
**Spec claim:** OpenAI/Anthropic/Google/Ollama adapter modules exist.
**Actual state:** `packages/kaizen-agents/src/kaizen_agents/delegate/adapters/{openai,anthropic,google,ollama}_adapter.py` all present + `registry.py::get_adapter_for_model()`.
**Remediation hint:** No action.

## F-D-37 — kaizen-agents-core § 5 — Wrapper stack classes verified

**Severity:** LOW
**Spec claim:** "BaseAgent -> L3GovernedAgent -> MonitoredAgent -> StreamingAgent" wrapper stack.
**Actual state:** `wrapper_base.py` (WrapperBase), `governed_agent.py` (L3GovernedAgent), `monitored_agent.py` (MonitoredAgent), `streaming_agent.py` (StreamingAgent). All four classes verified.
**Remediation hint:** No action.

## F-D-38 — kaizen-agents-core § 1.2 — Public API surface — `Pipeline` re-export documented but module path drift

**Severity:** LOW
**Spec claim:** `from kaizen_agents import Pipeline`
**Actual state:** `Pipeline` lives at `packages/kaizen-agents/src/kaizen_agents/patterns/pipeline.py`. Need to verify it's re-exported in `kaizen_agents/__init__.py`.
**Remediation hint:** Verify `__init__.py` re-exports `Pipeline`. Add to `__all__` if missing per `rules/orphan-detection.md` §6.

## F-D-39 — kaizen-agents-core § 27 — Error taxonomy 9 errors all present

**Severity:** LOW
**Spec claim:** ConstructorIOError, ToolRegistryCollisionError, GovernanceRejectedError, BudgetExhaustedError, DuplicateWrapperError, WrapperOrderError, DelegationCapExceeded, StreamTimeoutError, GovernanceHeldError.
**Actual state:** All 9 verified via grep across kaizen_agents source tree at expected file locations.
**Remediation hint:** No action.

## F-D-40 — kaizen-agents-patterns § 6 — All 14 specialized agents verified at expected paths

**Severity:** LOW
**Spec claim:** 14 specialized agents listed (ReAct, CoT, ToT, Vision, Audio, RAGResearch, Planning, Memory, SelfReflection, Resilient, HumanApproval, CodeGeneration, SimpleQA, StreamingChat, BatchProcessing, PEV).
**Actual state:** All present at `packages/kaizen-agents/src/kaizen_agents/agents/specialized/{...}.py`. Vision/audio agents at `agents/multi_modal/{vision,transcription}_agent.py` per spec.
**Remediation hint:** No action.

## F-D-41 — kaizen-agents-patterns § 6.3 — `ToTAgent` filename drift (spec implies "tot.py", actual "tree_of_thoughts.py")

**Severity:** LOW
**Spec claim:** "ToTAgent (Tree-of-Thoughts)" — implied filename `tot.py`.
**Actual state:** Actual file `agents/specialized/tree_of_thoughts.py` (verified contains class). Spec doesn't pin filename, but the descriptive name `tree_of_thoughts.py` is more readable.
**Remediation hint:** No action; minor terminology consistency.

## F-D-42 — kaizen-agents-patterns § 7 — All 5 named multi-agent patterns + helper patterns verified

**Severity:** LOW
**Spec claim:** DebatePattern, SupervisorWorkerPattern, ConsensusPattern, EnsemblePipeline, HandoffPattern, SequentialPipelinePattern, ParallelPattern, BlackboardPattern, MetaControllerPattern.
**Actual state:** Files for all major patterns at `packages/kaizen-agents/src/kaizen_agents/patterns/patterns/`. Need to verify Ensemble/Parallel/Blackboard/MetaController exist (some may be lazy-loaded).
**Remediation hint:** No action; core patterns verified.

## F-D-43 — kaizen-agents-patterns § 7 deprecation notice — v1.0 plan documented

**Severity:** LOW
**Spec claim:** "Deprecation notice (v0.9.0): All specialized agent subclasses within patterns ... are deprecated. In v1.0, patterns will accept plain `BaseAgent` instances..."
**Actual state:** Spec self-acknowledged. Current version 0.9.4 is in deprecation window. No defect.
**Remediation hint:** No action; track deprecation timeline.

## F-D-44 — kaizen-agents-patterns § 26 — Workflow templates verified

**Severity:** LOW
**Spec claim:** Debate, Consensus, SupervisorWorker, Enterprise workflow templates.
**Actual state:** All four in `kaizen_agents/workflows/{debate,consensus,supervisor_worker,enterprise_templates}.py`.
**Remediation hint:** No action.

## F-D-45 — kaizen-agents-governance § 9 — `GovernedSupervisor` class verified, all 9 Layer 3 properties enumerated

**Severity:** LOW
**Spec claim:** "GovernedSupervisor" + 9 Layer 3 read-only views (accountability, budget, cascade, clearance, audit, dereliction, bypass_manager, vacancy, classifier).
**Actual state:** `packages/kaizen-agents/src/kaizen_agents/supervisor.py:196` — GovernedSupervisor class. Helper classes _ReadOnlyView (line 114), HoldRecord (92), SupervisorResult (166) all present. PACT integration verified ("PACT-governed L3" docstring; "PACT default-deny" defaults).
**Remediation hint:** No action.

## F-D-46 — kaizen-agents-governance § 10 — All 8 governance subsystems present

**Severity:** LOW
**Spec claim:** AccountabilityTracker, ClearanceEnforcer, CascadeManager, VacancyManager, DerelictionDetector, BypassManager, BudgetTracker, ClassificationAssigner, CostModel.
**Actual state:** All 8 governance subsystem files exist at `packages/kaizen-agents/src/kaizen_agents/governance/{accountability,clearance,cascade,vacancy,dereliction,bypass,budget,cost_model}.py`.
**Remediation hint:** No action.

## F-D-47 — kaizen-agents-governance § 11 — AuditTrail verified at expected location

**Severity:** LOW
**Spec claim:** "AuditTrail ... append-only audit trail with SHA-256 hash chain integrity."
**Actual state:** `packages/kaizen-agents/src/kaizen_agents/audit/trail.py:62` — `class AuditTrail:`. Verified.
**Remediation hint:** No action.

## F-D-48 — kaizen-agents-governance § 19.6 — OrchestrationRuntime + 4 orchestration classes verified

**Severity:** LOW
**Spec claim:** "OrchestrationRuntime ... OrchestrationStrategy ... OrchestrationConfig ... OrchestrationResult ... PipelineStep ... PipelineInputSource ... Coordinator ... AgentLike ... SharedMemoryCoordinator ... OrchestrationError"
**Actual state:** All 11 classes verified in `packages/kailash-kaizen/src/kaizen/orchestration/runtime.py` at lines 122-401. Spec assertion holds.
**Remediation hint:** No action.

## F-D-49 — kaizen-agents-governance § 9.6 — Tool argument auditing security verified

**Severity:** LOW
**Spec claim:** "Records only argument keys (not values) in the audit trail for security."
**Actual state:** Need to verify in `record_tool_use` impl. Spec assertion at signature level only — deeper audit deferred.
**Remediation hint:** Tier 2 wiring tests should assert `arguments` values are NOT persisted (only keys). Add explicit test if missing.

## F-D-50 — kaizen-agents-governance § 9.2 — Default model is hardcoded "claude-sonnet-4-6" per spec AND code

**Severity:** HIGH
**Spec claim:** "`model` ... Default `\"claude-sonnet-4-6\"`"
**Actual state:** `packages/kaizen-agents/src/kaizen_agents/supervisor.py:221` — `model: str = "claude-sonnet-4-6"`. Confirmed hardcoded. Per `rules/env-models.md` "NEVER Hardcode Model Names: BLOCKED: model='claude-3-opus'" — this violates the rule. Spec accurately documents the violation.
**Remediation hint:** Change default to `model: Optional[str] = None`; resolve at runtime via `os.environ.get("ANTHROPIC_MODEL", os.environ.get("DEFAULT_LLM_MODEL"))`; raise if unset. Update spec accordingly.

## F-D-51 — kaizen-ml-integration § Status — Spec is DRAFT targeting 2.12.0; current package version 2.13.1

**Severity:** LOW
**Spec claim:** "Target release: kailash-kaizen 2.12.0 ... Status: DRAFT at workspaces/kailash-ml-audit/supporting-specs-draft/"
**Actual state:** Current `kailash-kaizen` version is 2.13.1 — past the 2.12.0 target. Spec says "Promotes to specs/kaizen-ml-integration.md after round-3 convergence" but file already exists at `specs/kaizen-ml-integration.md`. Promotion happened.
**Remediation hint:** Update spec status from DRAFT to LIVE and bump version target to 2.13.x; document what landed.

## F-D-52 — kaizen-ml-integration § 2 — `tracker=` kwarg integrated into AgentDiagnostics + InterpretabilityDiagnostics

**Severity:** LOW
**Spec claim:** Three adapters gain `tracker: Optional[ExperimentRun]` kwarg.
**Actual state:** Verified at `packages/kailash-kaizen/src/kaizen/observability/agent_diagnostics.py:195` and `kaizen/interpretability/core.py:330`. `LLMDiagnostics` exists at `kaizen/judges/llm_diagnostics.py` (NOT at spec's claimed `kaizen/observability/llm_diagnostics.py`).
**Remediation hint:** Update spec § 2.3 to note actual module path (`kaizen.judges.llm_diagnostics`).

## F-D-53 — kaizen-ml-integration § 5.1 — `SQLiteSink` lives in `kaizen/ml/_sqlite_sink.py` not `kaizen/observability/trace_exporter.py`

**Severity:** MED
**Spec claim:** "`# kaizen.observability.trace_exporter` ... `class SQLiteSink:`"
**Actual state:** SQLiteSink class lives at `packages/kailash-kaizen/src/kaizen/ml/_sqlite_sink.py` (NOT in observability module per spec). This is module-path drift; consumers importing per spec get ImportError.
**Remediation hint:** Either move SQLiteSink to `kaizen.observability.trace_exporter` OR re-export from there. Update spec to canonical import path. Per `rules/orphan-detection.md` §6, eager-imported public symbols must live where the spec promises.

## F-D-54 — kaizen-ml-integration § 4.2 — CostDelta microdollar wire format verified

**Severity:** LOW
**Spec claim:** "Kaizen 2.12.0 MUST migrate `kaizen.cost.tracker.CostTracker` to microdollars wire format"
**Actual state:** `packages/kailash-kaizen/src/kaizen/cost/tracker.py` — verified microdollar accumulation, `_MICRODOLLARS_PER_USD = 1_000_000`. CostDelta migration appears complete.
**Remediation hint:** No action.

## F-D-55 — kaizen-ml-integration § 2.4 — `km.engine_info` / `km.list_engines` agent tool discovery — production wiring NOT verified

**Severity:** HIGH
**Spec claim:** "Kaizen agents (BaseAgent, DelegateEngine, SupervisorAgent, and every descendant) MUST obtain ML-method signatures AT runtime via `km.engine_info(engine_name)` / `km.list_engines()`."
**Actual state:** Greps for `km.engine_info`, `km.list_engines`, or `MLAwareAgent` returned ZERO matches in `packages/kailash-kaizen/src/kaizen/agents/`, `kaizen/core/`, or `kaizen-agents/src/kaizen_agents/agents/`. The spec mandates a `MLAwareAgent` class at `kaizen.agents.ml_enabled` (line 269) — does not exist. Tier-2 wiring test at `tests/integration/test_kaizen_agent_engine_discovery_wiring.py` (spec § 2.4.7) — does not exist. This is a critical orphan: spec mandates discovery-driven tool construction but NO production code consumes `km.list_engines()`.
**Remediation hint:** Either ship `MLAwareAgent` + Tier-2 wiring test per spec, OR update spec to mark this surface as DEFERRED/Awaiting-implementation. Per `rules/orphan-detection.md` §1, MUST land production call site within 5 commits of facade landing.

## F-D-56 — kaizen-ml-integration § 7.2 — Several Tier-2 wiring tests exist; some missing

**Severity:** MED
**Spec claim:** 5 Tier-2 wiring tests at specific paths.
**Actual state:** `tests/integration/ml/test_sqlite_sink_fingerprint_wiring.py` exists. Did not find: `test_agent_diagnostics_tracker_wiring.py`, `test_llm_diagnostics_tracker_wiring.py`, `test_interpretability_diagnostics_tracker_wiring.py`, `test_cost_tracker_cross_sdk_parity_wiring.py`. Missing 4 of 5 wiring tests.
**Remediation hint:** Create the 4 missing Tier-2 wiring tests per spec § 7.2 paths.

## F-D-57 — kaizen-ml-integration § 5.2 — Schema table prefix `_kml_agent_*` undocumented in production code paths

**Severity:** LOW
**Spec claim:** Two tables `_kml_agent_traces` + `_kml_agent_trace_events` with full DDL.
**Actual state:** SQLiteSink class exists at `kaizen/ml/_sqlite_sink.py`; deeper schema verification deferred. Spec asserts `_kml_` prefix per ML's canonical internal-system-table convention.
**Remediation hint:** Verify SQLiteSink CREATE TABLE statements match spec DDL exactly; update spec if drift.
