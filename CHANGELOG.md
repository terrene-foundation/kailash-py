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
