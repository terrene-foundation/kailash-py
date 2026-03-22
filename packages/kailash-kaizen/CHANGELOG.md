# Changelog

All notable changes to the Kaizen AI Agent Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
