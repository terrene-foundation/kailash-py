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

### [0.6.3] - 2025-07-03

**Critical MCP Namespace Collision Fix**

**Fixed:**
- **MCP Namespace Collision**: Resolved critical import error where local `kailash.mcp` package was shadowing external `mcp.server`, preventing FastMCP imports
- **API Design**: Consolidated redundant MCP server implementations into clean architecture:
  - `MCPServerBase`: Abstract base for custom implementations
  - `MCPServer`: Main concrete server with all production features
  - `SimpleMCPServer`/`EnhancedMCPServer`: Backward compatibility aliases
- **Zero Skipped Tests**: Fixed all previously skipped MCP tests to enforce quality policy
- **Import Paths**: Updated all imports across codebase from `kailash.mcp` to `kailash.mcp_server`

**Enhanced:**
- Preserved all production features: caching, metrics, formatting, configuration management
- Maintained full backward compatibility for existing code
- 50/50 MCP tests now passing (36 unit + 14 integration)

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
