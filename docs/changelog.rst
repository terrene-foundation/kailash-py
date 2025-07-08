.. _changelog:


Changelog
=========

All notable changes to the Kailash Python SDK will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning
<https://semver.org/spec/v2.0.0.html>`_.

[0.6.6] - 2025-07-08
--------------------

Fixed
~~~~~
- **AgentUIMiddleware Shared Workflow Execution** - Shared workflows registered with ``make_shared=True`` couldn't be executed from sessions. Now automatically copied to sessions when first executed.

Changed
~~~~~~~
- **API Method Standardization** - Deprecated ``AgentUIMiddleware.execute_workflow()`` in favor of ``execute()`` for consistency with runtime API

Added
~~~~~
- **Documentation** - Updated Agent-UI communication guide with shared workflow behavior section
- **Testing** - Added 4 comprehensive integration tests for shared workflow functionality
- **Migration Guide** - Added v0.6.5+ migration guide explaining the fix

[0.6.5] - 2025-07-08
--------------------

Added
~~~~~
- **AsyncSQL Transaction Management** - Auto, manual, and none modes for precise control
- **Optimistic Locking** - Version-based concurrency control with conflict resolution
- **Advanced Parameter Handling** - PostgreSQL ANY(), JSON, arrays, date/datetime support

Fixed
~~~~~
- **PostgreSQL ANY() Parameters** - Fixed list parameter conversion for array operations
- **DNS/Network Error Retries** - Added missing error patterns for network failures
- **Optimistic Locking Version Check** - Fixed WHERE clause detection for version validation
- **E2E Transaction Timeouts** - Added timeout configurations to prevent deadlocks

Enhanced
~~~~~~~~
- **Testing Infrastructure** - Removed ALL mocks from integration tests (policy compliance)
- **Documentation Quality** - Complete AsyncSQL enterprise patterns with validated examples
- **Connection Pool Sharing** - Event loop management for shared pools across instances

[0.6.4] - 2025-07-06
--------------------

Added
~~~~~
- **Enterprise Parameter Injection** - WorkflowBuilder ``add_workflow_inputs()`` with dot notation support
- **E2E Test Excellence** - 100% pass rate on all comprehensive E2E tests
- **Documentation Quality** - Updated based on E2E test findings with correct patterns

Fixed
~~~~~
- **Permission Check Structure** - Fixed nested result structure (``result.check.allowed``)
- **PythonCodeNode Parameters** - Direct namespace injection now working correctly
- **Integration Test Stability** - Improved cache handling and async node behavior

[0.6.3] - 2025-07-05
--------------------

Added
~~~~~
- **MCP Testing Infrastructure** - 407 comprehensive tests (391 unit, 14 integration, 2 E2E) with 100% pass rate
- **MCP Tool Execution** - Complete LLMAgent automatic tool execution with multi-round support
- **Enterprise MCP Testing** - 4 E2E tests with custom enterprise nodes for real-world scenarios
- **Documentation Validation** - Framework achieving 100% test pass rate across all patterns

Fixed
~~~~~
- **MCP Namespace Collision** - Resolved critical import error (``kailash.mcp`` → ``kailash.mcp_server``)
- **Core SDK Issues** - EdgeDiscovery, SSOAuthenticationNode, PythonCodeNode, StreamPublisherNode fixes
- **Documentation** - 200+ pattern corrections ensuring all examples work correctly

[0.6.0] - 2025-01-24
--------------------

Added
~~~~~
- **User Management System** - Complete enterprise user management infrastructure
- **Enterprise Admin Infrastructure** - RBAC, audit logging, multi-tenant support

[0.3.0] - 2025-06-10
--------------------

Added
~~~~~
- **Parameter Lifecycle Architecture** - Major architectural improvement for node parameter handling

  - Nodes can now be created without required parameters (validated at execution)
  - Clear separation between construction, configuration, and execution phases
  - Runtime parameter support in workflow validation
  - More flexible workflow construction patterns

- **Centralized Data Management** - Complete reorganization of data files

  - New ``/data/`` directory structure with organized subdirectories
  - Data access utilities in ``examples/utils/data_paths.py``
  - Backward compatibility for existing file paths
  - Standardized patterns for data file access

- **PythonCodeNode Enhancements** - Improved developer experience

  - Better support for ``from_function()`` with full IDE capabilities
  - Enhanced data science module support (pandas, numpy, scipy)
  - Improved type inference and error messages
  - Best practices documentation for code organization

- **Enterprise Workflow Library** - Production-ready workflow patterns

  - Control flow patterns with comprehensive examples
  - Enterprise data processing workflows
  - Industry-specific implementations
  - Migration examples from code-heavy to proper node usage

Changed
~~~~~~~
- **Runtime Architecture** - Fixed critical method calling bug

  - All runtime modules now correctly call ``node.run()`` instead of ``node.execute()``
  - Direct configuration updates without non-existent ``configure()`` method
  - Improved error handling and validation

- **API Enhancements**

  - Workflow validation now accepts ``runtime_parameters`` argument
  - Better parameter validation with lifecycle support
  - Enhanced error messages at appropriate lifecycle phases

Fixed
~~~~~
- Critical runtime bug where wrong method was being called
- Parameter validation timing issues (fixes mistakes #020, #053, #058)
- Workflow validation failures with runtime parameters
- Data file path inconsistencies across examples

[0.1.1] - 2025-05-31
--------------------

Added
~~~~~
- Complete test suite with 539 tests passing
- Comprehensive API documentation with Sphinx
- Real-time performance monitoring and dashboards
- SharePoint Graph API integration
- Pre-commit hooks for code quality
- PyPI package distribution

Changed
~~~~~~~
- Improved package distribution (removed unnecessary files)
- Fixed documentation build warnings
- Updated README examples to match current API

Fixed
~~~~~
- Task tracking datetime comparison issues
- Performance monitoring integration
- Documentation formatting errors

[0.1.0] - 2025-05-31
--------------------

Added
~~~~~
- Initial release of Kailash Python SDK
- Core node system with 50+ node types
- Workflow builder and execution engine
- Local and async runtime options
- Task tracking and monitoring
- Export functionality (YAML/JSON)
- CLI interface
- Comprehensive examples

Known Issues
~~~~~~~~~~~~
- Package includes unnecessary files (tests, docs)
- Some datetime comparison issues in task tracking

.. note::
   For the latest changes, see the `GitHub repository <https://github.com/terrene-foundation/kailash-py>`_.
