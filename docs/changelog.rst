.. _changelog:


Changelog
=========

All notable changes to the Kailash Python SDK will be documented in this file.

The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_,
and this project adheres to `Semantic Versioning
<https://semver.org/spec/v2.0.0.html>`_.

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
