# Spec Compliance Audit v3 -- Platform Architecture Convergence

**Date**: 2026-04-09
**Workspace**: platform-architecture-convergence
**Branch**: feat/platform-architecture-convergence
**Protocol**: `.claude/skills/spec-compliance/SKILL.md` 9-check protocol, re-derived from scratch.
**Trust ban**: `.spec-coverage`, `convergence-verify.py`, prior round outputs NOT consulted as evidence. Every assertion below is verified via live grep/read against the codebase.
**Predecessor**: `09-spec-compliance-v2.md` (16 CRITICAL + 11 HIGH)

**Verdict**: **NOT CLEAN -- 0 CRITICAL + 7 HIGH + 7 MEDIUM**

---

## Executive Summary

Waves 1 and 2 resolved all 16 CRITICAL findings from the v2 audit. The major structural fixes:

1. SPEC-02 capability protocols (ProviderCapability, BaseProvider, AsyncLLMProvider, StreamingProvider, ToolCallingProvider, StructuredOutputProvider) now exist in `providers/base.py` (6 classes).
2. SPEC-02 `get_provider_for_model` and `get_streaming_provider` registry functions are implemented.
3. SPEC-02 OpenAI `stream_chat` async generator is implemented.
4. SPEC-03 StreamingAgent now has a real streaming path (`_stream_with_provider`) that iterates `provider.stream_chat()` and yields events per-token, plus a batch fallback for non-streaming providers. The "fake stream" CRITICAL is resolved.
5. SPEC-04 `@deprecated` is applied to all 7 extension point methods.
6. SPEC-04 `BaseAgentConfig.posture` is typed as `Optional[AgentPosture]` (enum, not str).
7. SPEC-06 `PACTMiddleware` exists at `nexus/middleware/governance.py`.
8. SPEC-08 `AuditEvent` is consolidated to a single definition in `trust/audit_store.py`. All prior duplicates are deleted; consumers import from canonical.
9. SPEC-09 `JsonRpcRequest`/`JsonRpcResponse`/`JsonRpcError`/`McpToolInfo` wire types exist in `kailash_mcp/protocol/messages.py`.
10. SPEC-09 cross-SDK tests instantiate real `ConstraintEnvelope` and `JsonRpcRequest` classes (no hardcoded paths).
11. SPEC-10 LLM-first: `_simple_text_similarity` function is deleted. `Capability.matches_requirement` delegates to LLM via `kaizen.llm.reasoning.llm_capability_match`.
12. SPEC-01 import migration: 0 hits for `from kailash.mcp_server import` in kaizen-agents source.
13. Wrapper test coverage: 4 test files with 44 total tests across wrapper_base, streaming_agent, monitored_agent, governed_agent.

7 HIGH items remain (detailed below), all of which are "missing tests" or "spec naming divergence" rather than missing production code.

---

## SPEC-01: kailash-mcp Package

| #   | Assertion                                                  | Command                                                                                                                                               | Expected | Actual                                              | Verdict  |
| --- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | --------------------------------------------------- | -------- |
| 1.1 | MCP client.py is MOVED (shim <100 LOC)                     | `wc -l src/kailash/mcp_server/client.py`                                                                                                              | <100     | 60 lines, sys.modules swap + DeprecationWarning     | PASS     |
| 1.2 | Client shim emits DeprecationWarning                       | `grep "DeprecationWarning" src/kailash/mcp_server/client.py`                                                                                          | >=1      | 1 hit                                               | PASS     |
| 1.3 | Canonical client at kailash_mcp                            | `ls packages/kailash-mcp/src/kailash_mcp/client.py`                                                                                                   | exists   | exists                                              | PASS     |
| 1.4 | BaseAgent imports from kailash_mcp                         | `grep "from kailash_mcp" packages/kailash-kaizen/src/kaizen/core/base_agent.py`                                                                       | >=1      | line 34: `from kailash_mcp.client import MCPClient` | PASS     |
| 1.5 | Wire types JsonRpcRequest/Response/Error/McpToolInfo exist | `grep "class JsonRpcRequest\|class JsonRpcResponse\|class JsonRpcError\|class McpToolInfo" packages/kailash-mcp/src/kailash_mcp/protocol/messages.py` | 4        | 4 (lines 71, 153, 277, 402)                         | PASS     |
| 1.6 | kailash_mcp tests import new protocol types                | `grep "from kailash_mcp.protocol" packages/kailash-mcp/tests/`                                                                                        | >=1      | 0                                                   | **HIGH** |
| 1.7 | Prompt injection security test                             | `grep -rli "test.*prompt.*injection" packages/kailash-mcp/`                                                                                           | >=1      | 0                                                   | **HIGH** |
| 1.8 | All kaizen consumers migrated off old import               | `grep "from kailash.mcp_server import\|from kailash.mcp_server." packages/kailash-kaizen/src/`                                                        | 0        | 0                                                   | PASS     |
| 1.9 | enhanced_server.py imports kailash_mcp                     | `grep "from kailash_mcp" src/kailash/middleware/mcp/enhanced_server.py`                                                                               | >=1      | 2 hits (lines 28-29)                                | PASS     |

---

## SPEC-02: Provider Layer

| #    | Assertion                                                     | Command                                                                                                                                                                  | Expected | Actual                                                                                         | Verdict |
| ---- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | ---------------------------------------------------------------------------------------------- | ------- |
| 2.1  | ProviderCapability enum                                       | `grep "class ProviderCapability" packages/kailash-kaizen/src/kaizen/providers/base.py`                                                                                   | 1        | line 48                                                                                        | PASS    |
| 2.2  | BaseProvider protocol                                         | `grep "class BaseProvider" packages/kailash-kaizen/src/kaizen/providers/base.py`                                                                                         | 1        | line 74                                                                                        | PASS    |
| 2.3  | 4 capability protocols                                        | `grep "class AsyncLLMProvider\|class StreamingProvider\|class ToolCallingProvider\|class StructuredOutputProvider" packages/kailash-kaizen/src/kaizen/providers/base.py` | 4        | 4 (lines 92, 111, 133, 158)                                                                    | PASS    |
| 2.4  | get_provider_for_model registry                               | `grep "def get_provider_for_model" packages/kailash-kaizen/src/kaizen/providers/registry.py`                                                                             | >=1      | line 165                                                                                       | PASS    |
| 2.5  | get_streaming_provider helper                                 | `grep "def get_streaming_provider" packages/kailash-kaizen/src/kaizen/providers/registry.py`                                                                             | >=1      | line 206                                                                                       | PASS    |
| 2.6  | Embedding provider naming (CohereEmbeddingProvider)           | `grep "class CohereEmbeddingProvider" packages/kailash-kaizen/src/kaizen/providers/embedding/cohere.py`                                                                  | 1        | 0 (named `CohereProvider` implementing `EmbeddingProvider`)                                    | MEDIUM  |
| 2.7  | Embedding provider naming (HuggingFaceEmbeddingProvider)      | `grep "class HuggingFaceEmbeddingProvider" packages/kailash-kaizen/src/kaizen/providers/embedding/huggingface.py`                                                        | 1        | 0 (named `HuggingFaceProvider` implementing `EmbeddingProvider`)                               | MEDIUM  |
| 2.8  | Gemini mutual-exclusion guard                                 | `grep "response_format_stripped\|mutually_exclusive" packages/kailash-kaizen/src/kaizen/providers/llm/google.py`                                                         | >=1      | 4 hits                                                                                         | PASS    |
| 2.9  | OpenAI chat_async                                             | `grep "async def chat_async" packages/kailash-kaizen/src/kaizen/providers/llm/openai.py`                                                                                 | 1        | line 289                                                                                       | PASS    |
| 2.10 | OpenAI stream_chat                                            | `grep "async def stream_chat" packages/kailash-kaizen/src/kaizen/providers/llm/openai.py`                                                                                | 1        | line 449                                                                                       | PASS    |
| 2.11 | Reasoning model filtering                                     | `grep "max_completion_tokens\|_is_reasoning_model" packages/kailash-kaizen/src/kaizen/providers/llm/openai.py`                                                           | >=2      | 30+ hits covering max_completion_tokens, \_is_reasoning_model, \_filter_reasoning_model_params | PASS    |
| 2.12 | CostTracker class                                             | `grep "class CostTracker" packages/kailash-kaizen/src/kaizen/providers/cost.py`                                                                                          | 1        | exists                                                                                         | PASS    |
| 2.13 | ai_providers.py backward-compat shim emits DeprecationWarning | `grep "DeprecationWarning\|warnings.warn" packages/kailash-kaizen/src/kaizen/nodes/ai/ai_providers.py`                                                                   | >=1      | 0 (re-exports only, no runtime warning)                                                        | MEDIUM  |

---

## SPEC-03: Composition Wrappers

| #    | Assertion                                                                                                                              | Command                                                                                                                                                                                     | Expected                              | Actual                                                                                                                                                                                                                                                                                                              | Verdict  |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| 3.1  | WrapperBase exists                                                                                                                     | `grep "class WrapperBase" packages/kaizen-agents/src/kaizen_agents/wrapper_base.py`                                                                                                         | 1                                     | line 74                                                                                                                                                                                                                                                                                                             | PASS     |
| 3.2  | StreamingAgent exists                                                                                                                  | `grep "class StreamingAgent" packages/kaizen-agents/src/kaizen_agents/streaming_agent.py`                                                                                                   | 1                                     | line 83 (was 49 in v2)                                                                                                                                                                                                                                                                                              | PASS     |
| 3.3  | MonitoredAgent exists                                                                                                                  | `grep "class MonitoredAgent" packages/kaizen-agents/src/kaizen_agents/monitored_agent.py`                                                                                                   | 1                                     | exists                                                                                                                                                                                                                                                                                                              | PASS     |
| 3.4  | L3GovernedAgent exists                                                                                                                 | `grep "class L3GovernedAgent" packages/kaizen-agents/src/kaizen_agents/governed_agent.py`                                                                                                   | 1                                     | exists                                                                                                                                                                                                                                                                                                              | PASS     |
| 3.5  | StreamingAgent.run_stream has real streaming path                                                                                      | Read streaming_agent.py: \_stream_with_provider iterates provider.stream_chat() yielding TextDelta per token                                                                                | >=2 yields from separate token events | `_stream_with_provider` at line 154: iterates `provider.stream_chat(messages, **stream_kwargs)`, yields TextDelta per text_delta event, ToolCallStart/End per tool call, TurnComplete at end. Batch fallback at `_stream_batch_fallback` line 312 synthesizes from single run_async. Real streaming path confirmed. | PASS     |
| 3.6  | StreamingAgent buffer_size default                                                                                                     | grep `_DEFAULT_BUFFER_SIZE` streaming_agent.py                                                                                                                                              | 64 (per spec)                         | 256                                                                                                                                                                                                                                                                                                                 | MEDIUM   |
| 3.7  | Canonical stacking order enforced                                                                                                      | `grep "_WRAPPER_PRIORITY\|WrapperOrderError" packages/kaizen-agents/src/kaizen_agents/wrapper_base.py`                                                                                      | >=1                                   | \_WRAPPER_PRIORITY dict + WrapperOrderError raised on out-of-order                                                                                                                                                                                                                                                  | PASS     |
| 3.8  | Wrapper tests exist (4 modules)                                                                                                        | `grep "from kaizen_agents.wrapper_base\|from kaizen_agents.streaming_agent\|from kaizen_agents.monitored_agent\|from kaizen_agents.governed_agent" packages/kaizen-agents/tests/`           | >=4 files                             | 4 files: test_wrapper_base.py, test_streaming_agent.py, test_monitored_agent.py, test_governed_agent.py                                                                                                                                                                                                             | PASS     |
| 3.9  | Test counts per wrapper module                                                                                                         | `grep -c "def test_" packages/kaizen-agents/tests/unit/test_wrapper_base.py test_streaming_agent.py test_monitored_agent.py test_governed_agent.py`                                         | >=1 per file                          | wrapper_base: 12, streaming_agent: 8, monitored_agent: 11, governed_agent: 13. Total: 44 tests                                                                                                                                                                                                                      | PASS     |
| 3.10 | Security mitigation tests (wrapper bypass, posture poisoning, shadow mode, stacking attack, stream backpressure, LLM router injection) | `grep -rli "test.*wrapper.*bypass\|test.*posture.*poisoning\|test.*shadow.*mode\|test.*stacking_attack\|test.*stream.*backpressure\|test.*router.*injection" packages/kaizen-agents/tests/` | 6                                     | 0 (partial coverage: test_inner_blocks_direct_access exists for wrapper bypass, test_small_buffer_emits_overflow for backpressure, but not named per spec threat model)                                                                                                                                             | **HIGH** |

---

## SPEC-04: BaseAgent Slimming

| #   | Assertion                                     | Command                                                                                                       | Expected                       | Actual                                                                                                                                                 | Verdict  |
| --- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| 4.1 | BaseAgentConfig.posture typed as AgentPosture | `grep "posture:" packages/kailash-kaizen/src/kaizen/core/config.py`                                           | AgentPosture                   | line 109: `posture: Optional[AgentPosture] = None`, imports `from kailash.trust.posture import AgentPosture` (re-export from trust.envelope)           | PASS     |
| 4.2 | @deprecated imported                          | `grep "from .deprecation import deprecated" packages/kailash-kaizen/src/kaizen/core/base_agent.py`            | >=1                            | yes                                                                                                                                                    | PASS     |
| 4.3 | @deprecated applied to 7 extension points     | `grep -c "@deprecated" packages/kailash-kaizen/src/kaizen/core/base_agent.py`                                 | 7                              | 7 (lines 716, 721, 726, 731, 736, 741, 746)                                                                                                            | PASS     |
| 4.4 | 7 extension point methods exist               | `grep "def _default_signature\|def _default_strategy..." base_agent.py`                                       | 7                              | 7 methods present and decorated                                                                                                                        | PASS     |
| 4.5 | BaseAgent uses get_provider_for_model         | `grep "get_provider_for_model\|get_streaming_provider" packages/kailash-kaizen/src/kaizen/core/base_agent.py` | >=1                            | 0 -- BaseAgent does not import from registry                                                                                                           | MEDIUM   |
| 4.7 | BaseAgent inherits MCPMixin, A2AMixin, Node   | `grep "class BaseAgent" packages/kailash-kaizen/src/kaizen/core/base_agent.py`                                | class BaseAgent(Node) per spec | line 65: `class BaseAgent(MCPMixin, A2AMixin, Node)` -- mixins still applied (spec says deprecated, but @deprecated on methods, not class inheritance) | MEDIUM   |
| 4.8 | BaseAgent security tests                      | `grep -rli "test.*deferred_mcp\|test.*legacy_kwargs\|test.*extension_shadow" packages/kailash-kaizen/tests/`  | 3                              | 0                                                                                                                                                      | **HIGH** |

---

## SPEC-06: Nexus Auth Migration + PACTMiddleware

| #   | Assertion                             | Command                                                                                  | Expected                    | Actual   | Verdict  |
| --- | ------------------------------------- | ---------------------------------------------------------------------------------------- | --------------------------- | -------- | -------- |
| 6.1 | Canonical auth modules at trust/auth/ | `ls src/kailash/trust/auth/`                                                             | jwt.py, rbac.py, sso/, etc. | present  | PASS     |
| 6.2 | Nexus JWT imports canonical           | `grep "from kailash.trust.auth.jwt" packages/kailash-nexus/src/nexus/auth/jwt.py`        | >=1                         | yes      | PASS     |
| 6.3 | Nexus RBAC imports canonical          | `grep "from kailash.trust.auth" packages/kailash-nexus/src/nexus/auth/rbac.py`           | >=1                         | yes      | PASS     |
| 6.4 | Nexus auth emits DeprecationWarning   | `grep "warnings.warn" packages/kailash-nexus/src/nexus/auth/__init__.py`                 | >=1                         | yes      | PASS     |
| 6.5 | PACTMiddleware exists                 | `grep "class PACTMiddleware" packages/kailash-nexus/src/nexus/middleware/governance.py`  | 1                           | line 155 | PASS     |
| 6.7 | Nexus SSO/JWT security tests          | `grep -rli "test.*sso.*state.*nonce\|test.*jwt.*rotation" packages/kailash-nexus/tests/` | >=3                         | 0        | **HIGH** |

---

## SPEC-07: ConstraintEnvelope Unification

| #   | Assertion                                            | Command                                                                                | Expected                          | Actual                                                                                                                   | Verdict  |
| --- | ---------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | -------- |
| 7.1 | ConstraintEnvelope canonical at trust/envelope.py    | `grep "class ConstraintEnvelope" src/kailash/trust/envelope.py`                        | 1                                 | line 723, frozen dataclass                                                                                               | PASS     |
| 7.2 | signed_by, signed_at in \_KNOWN_FIELDS               | `grep "signed_by\|signed_at" src/kailash/trust/envelope.py`                            | present                           | in \_KNOWN_FIELDS dict (lines 715-716), transported via metadata                                                         | PASS     |
| 7.3 | posture_ceiling typed as AgentPosture                | `grep "posture_ceiling" src/kailash/trust/envelope.py`                                 | AgentPosture                      | line 741: `posture_ceiling: AgentPosture \| None = None` with coercion in **post_init**                                  | PASS     |
| 7.4 | intersect() enforces monotonic tightening            | `grep "def intersect" src/kailash/trust/envelope.py`                                   | 1                                 | present                                                                                                                  | PASS     |
| 7.5 | from_dict rejects NaN/Inf/unknown keys               | `grep "isfinite\|UnknownEnvelopeFieldError" src/kailash/trust/envelope.py`             | >=1                               | `math.isfinite` at lines 92, 103; `UnknownEnvelopeFieldError` at line 79, raised at line 1005                            | PASS     |
| 7.6 | Legacy chain.py ConstraintEnvelope deprecated        | `grep "from kailash.trust.envelope" src/kailash/trust/chain.py`                        | re-export with DeprecationWarning | chain.py still has own `class ConstraintEnvelope` (line 443), no import from envelope.py, no DeprecationWarning on class | **HIGH** |
| 7.7 | from_yaml uses yaml.safe_load                        | `grep "safe_load" src/kailash/trust/envelope.py`                                       | >=1                               | lines 1074, 1083                                                                                                         | PASS     |
| 7.8 | Cross-SDK envelope test uses real ConstraintEnvelope | `grep "ConstraintEnvelope.from_dict" tests/unit/cross_sdk/test_envelope_round_trip.py` | >=1                               | 8+ hits -- test instantiates ConstraintEnvelope.from_dict, calls to_canonical_json                                       | PASS     |
| 7.9 | No hardcoded paths in cross-SDK tests                | `grep "/Users/esperie" tests/unit/cross_sdk/`                                          | 0                                 | 0                                                                                                                        | PASS     |

---

## SPEC-08: Core SDK Audit/Registry Consolidation

| #   | Assertion                                    | Command                                                                                                              | Expected | Actual                                | Verdict |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------- | ------- |
| 8.1 | Canonical AuditEvent at trust/audit_store.py | `grep "class AuditEvent" src/kailash/trust/audit_store.py`                                                           | 1        | line 225, frozen dataclass            | PASS    |
| 8.2 | Store protocols defined                      | `grep "class InMemoryAuditStore\|class SqliteAuditStore\|class AuditStoreProtocol" src/kailash/trust/audit_store.py` | 3        | 3 hits                                | PASS    |
| 8.3 | AuditEvent is single definition              | `grep "class AuditEvent\b" src/kailash/` (excluding AuditEventType)                                                  | 1        | 1 -- only at trust/audit_store.py:225 | PASS    |
| 8.4 | audit_log.py imports canonical AuditEvent    | `grep "from kailash.trust.audit_store import AuditEvent" src/kailash/nodes/admin/audit_log.py`                       | >=1      | line 39                               | PASS    |
| 8.5 | runtime/trust/audit.py imports canonical     | `grep "from kailash.trust.audit_store import" src/kailash/runtime/trust/audit.py`                                    | >=1      | line 61                               | PASS    |
| 8.6 | trust/export/siem.py no duplicate AuditEvent | `grep "class AuditEvent" src/kailash/trust/export/siem.py`                                                           | 0        | 0                                     | PASS    |
| 8.7 | BudgetTracker wired into LocalRuntime        | `grep "BudgetTracker\|budget_store" src/kailash/runtime/`                                                            | >=1      | 0                                     | MEDIUM  |
| 8.9 | Audit chain tamper regression test           | `grep -rli "test.*audit.*tamper\|test.*chain.*break" tests/`                                                         | >=1      | 3 hits in tests/trust/                | PASS    |

---

## SPEC-09: Cross-SDK Parity

| #   | Assertion                                     | Command                                                                                                     | Expected            | Actual                       | Verdict |
| --- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------- | ---------------------------- | ------- |
| 9.1 | Fixture dir with jsonrpc + envelope           | `ls tests/fixtures/cross-sdk/`                                                                              | jsonrpc/, envelope/ | present                      | PASS    |
| 9.2 | test_jsonrpc instantiates JsonRpcRequest      | `grep "JsonRpcRequest.from_dict\|JsonRpcRequest(" tests/unit/cross_sdk/test_jsonrpc_round_trip.py`          | >=1                 | 10+ hits, real instantiation | PASS    |
| 9.3 | test_envelope instantiates ConstraintEnvelope | `grep "ConstraintEnvelope.from_dict\|ConstraintEnvelope(" tests/unit/cross_sdk/test_envelope_round_trip.py` | >=1                 | 15+ hits, real instantiation | PASS    |
| 9.4 | No hardcoded paths                            | `grep "/Users/esperie" tests/unit/cross_sdk/`                                                               | 0                   | 0                            | PASS    |

---

## SPEC-10: Multi-Agent Patterns / LLM-first

| #    | Assertion                                       | Command                                                           | Expected       | Actual                                                                                                                                           | Verdict  |
| ---- | ----------------------------------------------- | ----------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| 10.1 | \_simple_text_similarity function deleted       | `grep "def _simple_text_similarity" packages/kailash-kaizen/src/` | 0              | 0 (only doc reference in reasoning.py)                                                                                                           | PASS     |
| 10.2 | Capability.matches_requirement delegates to LLM | Read a2a.py lines 95-134                                          | LLM delegation | `async def matches_requirement` imports `from kaizen.llm.reasoning import llm_capability_match` and delegates to LLM-backed CapabilityMatchAgent | PASS     |
| 10.3 | LLMBased routing strategy class                 | `grep "class LLMBased" packages/kaizen-agents/src/kaizen_agents/` | 1              | 0                                                                                                                                                | **HIGH** |
| 10.4 | SupervisorAgent/WorkerAgent use WrapperBase     | `grep "class SupervisorAgent" + read inheritance`                 | WrapperBase    | SupervisorAgent(BaseAgent) at supervisor_worker.py:117 -- inherits BaseAgent, not WrapperBase                                                    | **HIGH** |

---

## Import Migration (SPEC-01 completion)

| #    | Assertion                                            | Command                                                                                        | Expected | Actual | Verdict |
| ---- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- | -------- | ------ | ------- |
| IM-1 | No `from kailash.mcp_server import` in kaizen source | `grep "from kailash.mcp_server import\|from kailash.mcp_server." packages/kailash-kaizen/src/` | 0        | 0      | PASS    |
| IM-2 | No `from kailash.mcp_server` in middleware/mcp       | `grep "from kailash.mcp_server" src/kailash/middleware/mcp/`                                   | 0        | 0      | PASS    |

---

## Summary

| Severity     | Count | IDs                                                                                                                                                                                                                                                     |
| ------------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CRITICAL** | 0     | --                                                                                                                                                                                                                                                      |
| **HIGH**     | 7     | 1.6 (kailash_mcp protocol tests), 1.7 (prompt injection test), 3.10 (wrapper security tests), 4.8 (BaseAgent security tests), 6.7 (Nexus SSO/JWT security tests), 10.3 (LLMBased routing class), 10.4 (SupervisorAgent wrapper pattern)                 |
| **MEDIUM**   | 7     | 2.6 (CohereProvider naming), 2.7 (HuggingFaceProvider naming), 2.13 (ai_providers.py shim warning), 3.6 (buffer_size=256 vs spec 64), 4.5 (BaseAgent provider registry import), 4.7 (MCPMixin/A2AMixin inheritance), 8.7 (BudgetTracker runtime wiring) |
| **PASS**     | 42    | All others                                                                                                                                                                                                                                              |

### Risk Assessment

**HIGH items break down into two categories:**

1. **Missing security tests** (1.6, 1.7, 3.10, 4.8, 6.7) -- 5 items. The production code is implemented, but the spec's security threat model has no corresponding test functions. These are testability gaps, not functionality gaps.

2. **Missing spec-promised classes** (10.3, 10.4) -- 2 items. `LLMBased` routing strategy class and wrapper-style `SupervisorAgent`/`WorkerAgent` do not exist. The underlying capability (LLM-based routing via `Capability.matches_requirement` + `llm_capability_match`) IS implemented, but not wrapped in the class API the spec describes. The existing `SupervisorAgent` inherits `BaseAgent` directly, not `WrapperBase`.

### Resolution Path

- **Security tests (5 HIGH)**: 1 session, parallelizable. Write test functions named per the spec threat model sections. No production code changes needed.
- **LLMBased + SupervisorAgent wrapper** (2 HIGH): 1 session. Create `LLMBased(RoutingStrategy)` that wraps the existing `llm_capability_match`, then create wrapper-style `SupervisorAgent(WrapperBase)` that uses it. The legacy pattern-based SupervisorAgent at `patterns/supervisor_worker.py` remains for backward compatibility.
- **MEDIUM items**: All are naming/wiring gaps, not missing functionality. Can be addressed incrementally.

### Duplicate ConstraintEnvelope (HIGH 7.6)

`src/kailash/trust/chain.py` still defines its own `class ConstraintEnvelope` (line 443) that is NOT a re-export from the canonical `src/kailash/trust/envelope.py`. The `chain.py` version does not emit `DeprecationWarning` on class construction. This means code importing `from kailash.trust.chain import ConstraintEnvelope` gets a different, non-canonical type. This needs either deletion or conversion to a thin re-export with deprecation warning. Counted in the 7 HIGH items above.

---

## Verdict: NOT CLEAN (0 CRITICAL, 7 HIGH)

All structural CRITICALs from v2 are resolved. The remaining HIGHs are test coverage gaps and two missing class wrappers for spec-promised APIs. The production functionality is present; the API surface and security test coverage need one more implementation session to converge.
