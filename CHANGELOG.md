# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Note: Changelog Reorganized

The changelog has been reorganized into individual files for better management. Please see:

- **[changelogs/](changelogs/)** - Main changelog directory
- **[changelogs/unreleased/](changelogs/unreleased/)** - Unreleased changes
- **[changelogs/releases/](changelogs/releases/)** - Individual release changelogs

## Recent Releases

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
- See [migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md](sdk-users/migration-guides/version-specific/v0.6.6-infrastructure-enhancements.md) for details

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
- **Migration Guide Consolidation**: Unified location at `sdk-users/migration-guides/`
- **MCP Platform Unification**: Created `apps/mcp_platform/` from 6 scattered directories
- **Documentation Quality**: 100% coverage (up from 72.7%), all examples validated
- **API Design**: Clean server hierarchy with backward compatibility

**Breaking Changes:** None - fully backward compatible

### [0.6.2] - 2025-07-03

See [changelogs/releases/v0.6.2-2025-07-03.md](changelogs/releases/v0.6.2-2025-07-03.md) for full details.

**Key Features:** LLM integration enhancements with Ollama backend_config support, 100% test coverage across all tiers, comprehensive documentation updates

### [0.6.1] - 2025-01-26

See [changelogs/releases/v0.6.1-2025-01-26.md](changelogs/releases/v0.6.1-2025-01-26.md) for full details.

**Key Features:** Critical middleware bug fixes, standardized test environment, massive CI performance improvements (10min → 40sec)

### [0.6.0] - 2025-01-24

See [changelogs/releases/v0.6.0-2025-01-24.md](changelogs/releases/v0.6.0-2025-01-24.md) for full details.

**Key Features:** User Management System, Enterprise Admin Infrastructure

### [0.5.0] - 2025-01-19

See [changelogs/releases/v0.5.0-2025-01-19.md](changelogs/releases/v0.5.0-2025-01-19.md) for full details.

**Key Features:** Major Architecture Refactoring, Performance Optimization, API Standardization

### [0.4.2] - 2025-06-18

See [changelogs/releases/v0.4.2-2025-06-18.md](changelogs/releases/v0.4.2-2025-06-18.md) for full details.

**Key Features:** Circular Import Resolution, Changelog Organization

### [0.4.1] - 2025-06-16

See [changelogs/releases/v0.4.1-2025-06-16.md](changelogs/releases/v0.4.1-2025-06-16.md) for full details.

**Key Features:** Alert Nodes System, AI Provider Vision Support

### [0.4.0] - 2025-06-15

See [changelogs/releases/v0.4.0-2025-06-15.md](changelogs/releases/v0.4.0-2025-06-15.md) for full details.

**Key Features:** Enterprise Middleware Architecture, Test Excellence Improvements

### [0.3.2] - 2025-06-11

See [changelogs/releases/v0.3.2-2025-06-11.md](changelogs/releases/v0.3.2-2025-06-11.md) for full details.

**Key Features:** PythonCodeNode Output Validation Fix, Manufacturing Workflow Library

### [0.3.1] - 2025-06-11

See [changelogs/releases/v0.3.1-2025-06-11.md](changelogs/releases/v0.3.1-2025-06-11.md) for full details.

**Key Features:** Complete Finance Workflow Library, PythonCodeNode Training Data

### [0.3.0] - 2025-06-10

See [changelogs/releases/v0.3.0-2025-06-10.md](changelogs/releases/v0.3.0-2025-06-10.md) for full details.

**Key Features:** Parameter Lifecycle Architecture, Centralized Data Management

For complete release history, see [changelogs/README.md](changelogs/README.md).
