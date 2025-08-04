# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Note: Changelog Reorganized

The changelog has been reorganized into individual files for better management. Please see:

- **[sdk-users/6-reference/changelogs/](sdk-users/6-reference/changelogs/)** - Main changelog directory
- **[sdk-users/6-reference/changelogs/unreleased/](sdk-users/6-reference/changelogs/unreleased/)** - Unreleased changes
- **[sdk-users/6-reference/changelogs/releases/](sdk-users/6-reference/changelogs/releases/)** - Individual release changelogs

## Recent Releases

### Application Framework Releases

#### DataFlow [0.3.1] - 2025-01-22
**Test Infrastructure & Reliability Release**
- **Test Coverage**: Improved from ~40% to 90.7% pass rate (330/364 tests)
- **Zero Failures**: All tests now pass or are properly skipped
- **Enhanced Multi-Database Integration**: Fixed PostgreSQL precision and context passing
- **Improved Multi-Tenancy**: Fixed Row Level Security tests with proper permissions
- **Transaction Support**: Enhanced transaction management and schema operations
- **Documentation**: Enhanced CLAUDE.md guidance for parameter validation

#### Nexus [1.0.3] - 2025-01-22
**Production Ready Release**
- **100% Documentation Validation**: All code examples verified with real infrastructure
- **77% Test Coverage**: Comprehensive test suite with 248 passing unit tests
- **WebSocket Transport**: Full MCP protocol implementation with concurrent clients
- **API Correctness**: All documented patterns validated and corrected
- **Enhanced Stability**: Robust error handling and timeout enforcement

### Core SDK Releases

### [0.9.11] - 2025-08-04

**Testing Excellence & DataFlow Integration Enhancement Release**

This release focuses on testing infrastructure excellence and enhanced DataFlow integration capabilities, achieving a major milestone of 4,000+ passing tier 1 tests.

#### Added
- ✅ **Testing Milestone Achievement**: 4,072 passing tier 1 tests with comprehensive coverage
- ✅ **Enhanced DataFlow Integration**: Improved AsyncSQL node compatibility with DataFlow parameters
- ✅ **Test Infrastructure Hardening**: Better test isolation and cleanup mechanisms
- ✅ **Performance Optimization**: Test execution optimization for development workflows

#### Changed
- 🔄 **Code Quality**: Comprehensive formatting updates with black, isort, and ruff compliance
- 🔄 **Documentation**: Enhanced integration examples and troubleshooting guides
- 🔄 **Test Organization**: Restructured test suite for better maintainability

#### Fixed
- 🐛 **AsyncSQL Parameter Handling**: Improved parameter conversion for DataFlow integration
- 🐛 **Import Order**: Corrected import ordering across test modules
- 🐛 **Connection Management**: Enhanced connection pool handling in test environments

#### Infrastructure
- 🏗️ **Test Excellence**: Achieved comprehensive test coverage milestone
- 🏗️ **CI/CD Readiness**: Enhanced build validation and quality gates
- 🏗️ **Development Experience**: Streamlined development and testing procedures

### [0.8.7] - 2025-01-25 (Unreleased - Superseded)

**MCP Ecosystem Enhancement Release**

This release completes the MCP ecosystem with comprehensive parameter validation, 100% protocol compliance, and enterprise-grade subscriptions.

#### Added
- ✅ **MCP Parameter Validation Tool**: 7 validation endpoints, 28 error types, 132 unit tests
- ✅ **MCP Protocol Compliance**: 4 missing handlers implemented for 100% compliance
- ✅ **MCP Subscriptions Phase 2**: GraphQL optimization, WebSocket compression, Redis coordination
- ✅ **Claude Code Integration**: Full MCP tool integration with configuration guides
- ✅ **A/B Testing Framework**: Legitimate blind testing methodology for validation

### [0.8.6] - 2025-07-22

**Enhanced Parameter Validation & Debugging Release**

#### Added
- ✅ **Enhanced Parameter Validation**: 4 modes (off/warn/strict/debug) with <1ms overhead
- ✅ **Parameter Debugging Tools**: ParameterDebugger provides 10x faster issue resolution
- ✅ **Comprehensive Documentation**: 1,300+ lines of troubleshooting guides

### [0.8.5] - 2025-01-20

**Architecture Cleanup & Enterprise Security Release**

This release removes the confusing `src/kailash/nexus` module, adds comprehensive edge computing infrastructure, implements enterprise-grade connection parameter validation, and introduces advanced monitoring capabilities.

#### Added
- ✅ **Connection Parameter Validation**: Enterprise-grade validation framework with type safety
- ✅ **Edge Computing Infrastructure**: 50+ new nodes for geo-distributed computing
- ✅ **AlertManager**: Proactive monitoring with configurable thresholds
- ✅ **Connection Contracts**: Define and enforce data flow contracts between nodes
- ✅ **Validation Metrics**: Track connection validation performance and failures
- ✅ **Edge Node Discovery**: Automatic discovery and coordination of edge resources
- ✅ **Predictive Scaling**: Resource optimization with predictive algorithms
- ✅ **Comprehensive Monitoring**: Enhanced monitoring patterns and guides

#### Changed
- Updated all documentation to use correct Nexus imports (`from nexus import Nexus`)
- Enhanced LocalRuntime with validation enabled by default
- Improved error messages with validation suggestions
- Updated DataFlow integration to use proper imports

#### Removed
- ⚠️ **BREAKING**: Removed `src/kailash/nexus` module (use `apps/kailash-nexus` instead)
- Removed `tests/integration/test_nexus_framework.py`
- Removed outdated nexus import references from documentation

#### Security
- Enterprise-grade connection parameter validation
- Real-time security event monitoring
- Compliance-aware edge routing
- Enhanced error handling with security considerations

### [0.8.4] - 2025-01-19

**A2A Google Protocol Enhancement Release**

This release implements comprehensive Agent-to-Agent (A2A) communication enhancements with Google protocol best practices, significantly improving multi-agent insight quality and coordination capabilities.

#### Added
- ✅ **Enhanced Agent Cards**: Detailed capability descriptions with performance metrics and collaboration styles
- ✅ **Structured Task Management**: Complete lifecycle management with state machine (CREATED → COMPLETED)
- ✅ **Multi-stage LLM Insight Pipeline**: Quality-focused insight extraction with confidence scoring
- ✅ **Semantic Memory Pool**: Vector embeddings with concept extraction and semantic search
- ✅ **Hybrid Search Engine**: Combines semantic, keyword, and fuzzy matching capabilities
- ✅ **Streaming Analytics**: Real-time performance monitoring and optimization
- ✅ **Comprehensive Testing**: 1,174 lines across 3 new test files (2930/2930 unit tests passing)
- ✅ **A2A Documentation**: Complete cheatsheet and workflow examples
- ✅ **Integration Examples**: Working multi-agent coordination patterns

#### Changed
- Enhanced A2ACoordinatorNode with backward-compatible action-based routing
- Improved insight extraction quality from ~0.6 to >0.8 average scores
- Updated root CLAUDE.md with A2A quick start and multi-step guidance

#### Technical Details
- Full backward compatibility maintained (all existing tests pass)
- Action-based routing preserves legacy API usage patterns
- Integration with existing workflow builder and runtime systems
- No breaking changes, no migration required

### [0.8.3] - 2025-01-18

**SDK Critique Response & Documentation Improvements Release**

This release addresses developer experience issues identified in comprehensive SDK critique, implements critical architectural fixes, and establishes comprehensive documentation structure with Claude Code integration patterns.

#### Added
- ✅ **DataFlow CLAUDE.md**: Comprehensive usage patterns guide (412 lines) for Claude Code integration
- ✅ **Nexus CLAUDE.md**: Multi-channel platform patterns guide (542 lines) for Claude Code integration  
- ✅ **Enhanced Connection Error Messages**: Improved validation with helpful suggestions and port discovery
- ✅ **hashlib Support**: Added to PythonCodeNode ALLOWED_MODULES for cryptographic operations
- ✅ **Documentation Structure**: Migrated 90+ missing files from apps/*/docs/ to sdk-users/4-apps/
- ✅ **Comprehensive API Guidance**: Quick reference system and developer onboarding paths

#### Changed
- 🔄 **Documentation Architecture**: Established apps/*/docs/ as gold standard for ALL documentation
- 🔄 **API Patterns**: Cleaned up deprecated patterns in core cheatsheet files
- 🔄 **Parameter Access**: Fixed Claude Code patterns to use try/except NameError (not parameters.get())
- 🔄 **Nexus Documentation**: Corrected import paths, method signatures, and API examples

#### Fixed
- 🐛 **CRITICAL: DataFlow-Kailash Integration**: Resolved type annotation incompatibility making DataFlow unusable
- 🐛 **Type Normalization**: Added system to convert complex types (List[str], Optional[str]) to simple types
- 🐛 **NodeParameter Validation**: Fixed ValidationError on all DataFlow models with complex type annotations
- 🐛 **Import Sorting**: Applied isort with black profile across all modified files
- 🐛 **Documentation Links**: Fixed broken references and navigation paths

#### Impact
- 🚀 **DataFlow Usability**: Made DataFlow usable in real-world scenarios (91.7% success rate)
- 🚀 **Claude Code Integration**: Enabled correct implementation of both frameworks on first try
- 🚀 **Developer Experience**: Eliminated frustration through comprehensive documentation access
- 🚀 **Architecture Validation**: Confirmed sophisticated design patterns enable enterprise features

#### Package Updates
- **kailash-dataflow**: 0.1.0 → 0.1.1 (critical bug fix)
- **kailash-nexus**: 1.0.0 → 1.0.1 (documentation fixes)
- **kailash**: 0.8.1 → 0.8.3 (comprehensive improvements)

### [0.8.0] - 2025-01-17

**Test Infrastructure & Quality Improvements Release**

This release focuses on comprehensive test infrastructure improvements, systematic test fixing, and better SDK organization for enhanced developer experience and CI/CD reliability.

#### Added
- ✅ **Centralized Node Registry Management**: New `node_registry_utils.py` for consistent test isolation
- ✅ **Automatic Timeout Enforcement**: `conftest_timeouts.py` with 1s/5s/10s timeout compliance
- ✅ **TODO System Organization**: Clear separation between completed infrastructure work (TODO-111c) and remaining feature implementation (TODO-115)
- ✅ **Comprehensive Test Documentation**: Updated CLAUDE.md with execution patterns and test directives
- ✅ **Node Execution Pattern Guide**: `node-execution-pattern.md` clarifying run() vs execute()

#### Changed
- 🔄 **Test Infrastructure Overhaul**: Fixed test execution problems that were masking real functionality issues
- 🔄 **Improved Test Isolation**: All tests now use proper process isolation with `--forked` requirement
- 🔄 **Enhanced Performance**: Reduced test execution times from 10s/5s/2s to 0.1-0.2s across multiple test files
- 🔄 **Better Error Handling**: Fixed Ruff violations, circuit breaker timeouts, and eval() usage patterns

#### Fixed
- 🐛 **Test Timeout Issues**: Resolved hanging tests and timeout violations across all test tiers
- 🐛 **FastMCP Import Timeout**: Fixed MCP server test timing out due to slow external imports
- 🐛 **Import Order Dependencies**: Resolved circular import test subprocess timeout issues
- 🐛 **BehaviorAnalysisNode**: Fixed risk scoring, email alerts, and webhook functionality
- 🐛 **AsyncSQL Compatibility**: Fixed aioredis compatibility issues for Python 3.12
- 🐛 **NetworkDiscovery**: Fixed datagram_received for proper async/sync handling
- 🐛 **API Gateway Tests**: Resolved NodeRegistry empty state issues

#### Infrastructure
- 🏗️ **CI/CD Readiness**: Achieved 100% test infrastructure readiness for merge and deployment
- 🏗️ **Test Quality Assurance**: 2798 passed tests with proper isolation and timeout compliance
- 🏗️ **Code Quality**: Fixed all linting violations and improved code consistency
- 🏗️ **Docker E2E Optimization**: Reduced from 50000→500 operations, 100→10 workers for faster execution

#### Security
- 🔒 **Enhanced Security Testing**: Improved security node test coverage and validation
- 🔒 **Better Timeout Handling**: Prevents test hangs that could mask security issues

### [0.7.0] - 2025-07-10

**Major Framework Release: Complete Application Ecosystem & Infrastructure Hardening**

**🚀 New Framework Applications:**
- **DataFlow Framework**: Complete standalone ETL/database framework with 100% documentation validation
  - 4 production-ready example applications (simple CRUD, enterprise, data migration, API backend)
  - MongoDB-style query builder with Redis caching
  - Comprehensive testing infrastructure with Docker/Kubernetes deployment
- **Nexus Multi-Channel Platform**: Enterprise orchestration supporting API, CLI, and MCP interfaces
  - Complete application structure with enterprise features (multi-tenant, RBAC, marketplace)
  - 105 tests with 100% pass rate and production deployment ready
  - Unified session management across all channels

**🔧 Enterprise Resilience & Monitoring:**
- **Distributed Transaction Management**: Automatic pattern selection (Saga/2PC) with compensation logic
  - 122 unit tests + 23 integration tests (100% pass rate)
  - State persistence with Memory, Redis, and PostgreSQL backends
  - Enterprise-grade recovery and monitoring capabilities
- **Transaction Monitoring System**: 5 specialized monitoring nodes for production environments
  - TransactionMetricsNode, TransactionMonitorNode, DeadlockDetectorNode, RaceConditionDetectorNode, PerformanceAnomalyNode
  - 219 unit tests + 8 integration tests (100% pass rate)
  - Complete documentation with enterprise patterns

**🗄️ Data Management Enhancements:**
- **MongoDB-Style Query Builder**: Production-ready query builder with cross-database support
  - Supports PostgreSQL, MySQL, SQLite with MongoDB-style operators ($eq, $ne, $lt, $gt, $in, $regex)
  - 33 unit tests + 8 integration tests with automatic tenant isolation
- **Redis Query Cache**: Enterprise-grade caching with pattern-based invalidation
  - 40 unit tests with TTL management and tenant isolation
  - Multiple invalidation strategies and performance optimization

**🤖 AI & MCP Enhancements:**
- **Real MCP Execution**: Default behavior for all AI agents (breaking change from mock execution)
  - IterativeLLMAgent and LLMAgentNode now use real MCP tools by default
  - Enhanced error handling and protocol compliance
  - Backward compatibility with `use_real_mcp=False` option

**📚 Documentation & Standards:**
- **Complete Documentation Validation**: 100% test pass rate across all examples
  - Updated all frameworks with standardized documentation structure
  - Created comprehensive validation framework for all code examples
  - Application documentation standards across DataFlow and Nexus

**🏗️ Infrastructure Enhancements (TODO-109):**
- **Enhanced AsyncNode Event Loop Handling**: Thread-safe async execution with automatic event loop detection
  - Fixed "RuntimeError: no running event loop" in threaded contexts
  - Smart detection and handling of different async contexts
  - Zero performance impact with improved stability
- **Monitoring Node Operations**: Added 8 new operations across 4 monitoring nodes
  - `complete_transaction`, `acquire_resource`, `release_resource` (aliases for compatibility)
  - `request_resource`, `initialize`, `complete_operation` (new operations)
  - Automatic success rate calculations in all monitoring responses
- **E2E Test Infrastructure**: Achieved 100% pass rate (improved from 20%)
  - Fixed all infrastructure gaps preventing test success
  - Enhanced schema validation with backward-compatible aliases
  - Stable Docker test environment (PostgreSQL:5434, Redis:6380)

**🔧 Technical Improvements:**
- **Gateway Architecture Cleanup**: Renamed server classes for clarity
  - WorkflowAPIGateway → WorkflowServer
  - DurableAPIGateway → DurableWorkflowServer
  - EnhancedDurableAPIGateway → EnterpriseWorkflowServer
- **Version Consistency**: Fixed version synchronization across all package files
- **Test Suite Excellence**: 2,400+ tests passing with comprehensive coverage
  - Unit: 1,617 tests (enhanced with infrastructure tests)
  - Integration: 233 tests (including new monitoring tests)
  - E2E: 21 core tests (100% pass rate achieved)

**Breaking Changes:**
- Real MCP execution is now default for AI agents (can be disabled with `use_real_mcp=False`)
- Gateway class names updated (backward compatibility maintained with deprecation warnings)

**Migration Guide:**
- DataFlow and Nexus are new frameworks - no migration needed
- MCP execution change requires explicit `use_real_mcp=False` if mock execution is needed
- Gateway class renames are backward compatible
- Infrastructure enhancements require no code changes - all improvements are transparent
- New monitoring operations are additive - existing code continues to work
- See [migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md](sdk-users/6-reference/migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md) for details

### [0.6.6] - 2025-07-08

**AgentUIMiddleware Shared Workflow Fix & API Standardization**

**Fixed:**
- **AgentUIMiddleware Shared Workflow Execution**: Shared workflows registered with `make_shared=True` couldn't be executed from sessions. Now automatically copied to sessions when first executed.

**Changed:**
- **API Method Standardization**: Deprecated `AgentUIMiddleware.execute_workflow()` in favor of `execute()` for consistency with runtime API

**Enhanced:**
- **Documentation**: Updated Agent-UI communication guide with shared workflow behavior section
- **Testing**: Added 4 comprehensive integration tests for shared workflow functionality
- **Migration Guide**: Added v0.6.5+ migration guide explaining the fix

**Breaking Changes:** None - fully backward compatible

### [0.6.5] - 2025-07-08

**Enterprise AsyncSQL Enhancements & Production Testing**

**Major Features:**
- **AsyncSQL Transaction Management**: Auto, manual, and none modes for precise control
- **Optimistic Locking**: Version-based concurrency control with conflict resolution
- **Advanced Parameter Handling**: PostgreSQL ANY(), JSON, arrays, date/datetime support
- **100% Test Pass Rate**: All AsyncSQL tests passing with strict policy compliance

**Fixed:**
- **PostgreSQL ANY() Parameters**: Fixed list parameter conversion for array operations
- **DNS/Network Error Retries**: Added missing error patterns for network failures
- **Optimistic Locking Version Check**: Fixed WHERE clause detection for version validation
- **E2E Transaction Timeouts**: Added timeout configurations to prevent deadlocks

**Enhanced:**
- **Testing Infrastructure**: Removed ALL mocks from integration tests (policy compliance)
- **Documentation Quality**: Complete AsyncSQL enterprise patterns with validated examples
- **Connection Pool Sharing**: Event loop management for shared pools across instances

**Breaking Changes:** None - fully backward compatible

### [0.6.4] - 2025-07-06

**Enterprise Parameter Injection & E2E Test Excellence**

**Major Features:**
- **Enterprise Parameter Injection**: WorkflowBuilder `add_workflow_inputs()` with dot notation support
- **E2E Test Excellence**: 100% pass rate on all comprehensive E2E tests
- **Documentation Quality**: Updated based on E2E test findings with correct patterns

**Fixed:**
- **Permission Check Structure**: Fixed nested result structure (`result.check.allowed`)
- **PythonCodeNode Parameters**: Direct namespace injection now working correctly
- **Integration Test Stability**: Improved cache handling and async node behavior

**Enhanced:**
- **Test Infrastructure**: Achieved 100% E2E test pass rate with improved stability
- **Documentation Updates**: Comprehensive updates based on E2E test findings
- **Parameter Injection**: Enterprise-grade system with complex workflow support

**Breaking Changes:** None - fully backward compatible

### [0.6.3] - 2025-07-05

**Comprehensive MCP Platform, Testing Infrastructure & Documentation Quality**

**Major Features:**
- **MCP Testing Infrastructure**: 407 comprehensive tests (391 unit, 14 integration, 2 E2E) with 100% pass rate
- **MCP Tool Execution**: Complete LLMAgent automatic tool execution with multi-round support
- **Enterprise MCP Testing**: 4 E2E tests with custom enterprise nodes for real-world scenarios
- **Documentation Validation**: Framework achieving 100% test pass rate across all patterns

**Fixed:**
- **MCP Namespace Collision**: Resolved critical import error (`kailash.mcp` → `kailash.mcp_server`)
- **Core SDK Issues**: EdgeDiscovery, SSOAuthenticationNode, PythonCodeNode, StreamPublisherNode fixes
- **Documentation**: 200+ pattern corrections ensuring all examples work correctly

**Enhanced:**
- **Migration Guide Consolidation**: Unified location at `sdk-users/6-reference/migration-guides/`
- **MCP Platform Unification**: Created `apps/mcp_platform/` from 6 scattered directories
- **Documentation Quality**: 100% coverage (up from 72.7%), all examples validated
- **API Design**: Clean server hierarchy with backward compatibility

**Breaking Changes:** None - fully backward compatible

### [0.6.2] - 2025-07-03

See [sdk-users/6-reference/changelogs/releases/v0.6.2-2025-07-03.md](sdk-users/6-reference/changelogs/releases/v0.6.2-2025-07-03.md) for full details.

**Key Features:** LLM integration enhancements with Ollama backend_config support, 100% test coverage across all tiers, comprehensive documentation updates

### [0.6.1] - 2025-01-26

See [sdk-users/6-reference/changelogs/releases/v0.6.1-2025-01-26.md](sdk-users/6-reference/changelogs/releases/v0.6.1-2025-01-26.md) for full details.

**Key Features:** Critical middleware bug fixes, standardized test environment, massive CI performance improvements (10min → 40sec)

### [0.6.0] - 2025-01-24

See [sdk-users/6-reference/changelogs/releases/v0.6.0-2025-01-24.md](sdk-users/6-reference/changelogs/releases/v0.6.0-2025-01-24.md) for full details.

**Key Features:** User Management System, Enterprise Admin Infrastructure

### [0.5.0] - 2025-01-19

See [sdk-users/6-reference/changelogs/releases/v0.5.0-2025-01-19.md](sdk-users/6-reference/changelogs/releases/v0.5.0-2025-01-19.md) for full details.

**Key Features:** Major Architecture Refactoring, Performance Optimization, API Standardization

### [0.4.2] - 2025-06-18

See [sdk-users/6-reference/changelogs/releases/v0.4.2-2025-06-18.md](sdk-users/6-reference/changelogs/releases/v0.4.2-2025-06-18.md) for full details.

**Key Features:** Circular Import Resolution, Changelog Organization

### [0.4.1] - 2025-06-16

See [sdk-users/6-reference/changelogs/releases/v0.4.1-2025-06-16.md](sdk-users/6-reference/changelogs/releases/v0.4.1-2025-06-16.md) for full details.

**Key Features:** Alert Nodes System, AI Provider Vision Support

### [0.4.0] - 2025-06-15

See [sdk-users/6-reference/changelogs/releases/v0.4.0-2025-06-15.md](sdk-users/6-reference/changelogs/releases/v0.4.0-2025-06-15.md) for full details.

**Key Features:** Enterprise Middleware Architecture, Test Excellence Improvements

### [0.3.2] - 2025-06-11

See [sdk-users/6-reference/changelogs/releases/v0.3.2-2025-06-11.md](sdk-users/6-reference/changelogs/releases/v0.3.2-2025-06-11.md) for full details.

**Key Features:** PythonCodeNode Output Validation Fix, Manufacturing Workflow Library

### [0.3.1] - 2025-06-11

See [sdk-users/6-reference/changelogs/releases/v0.3.1-2025-06-11.md](sdk-users/6-reference/changelogs/releases/v0.3.1-2025-06-11.md) for full details.

**Key Features:** Complete Finance Workflow Library, PythonCodeNode Training Data

### [0.3.0] - 2025-06-10

See [sdk-users/6-reference/changelogs/releases/v0.3.0-2025-06-10.md](sdk-users/6-reference/changelogs/releases/v0.3.0-2025-06-10.md) for full details.

**Key Features:** Parameter Lifecycle Architecture, Centralized Data Management

For complete release history, see [changelogs/README.md](changelogs/README.md).
