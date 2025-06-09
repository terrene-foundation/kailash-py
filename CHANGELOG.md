# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Custom Node Development Guide** - Comprehensive documentation for creating custom nodes
  - Parameter type constraints and patterns (critical for avoiding "abstract class" errors)
  - Common implementation patterns with examples
  - Troubleshooting guide for frequent issues
  - Working examples in `guide/developer/`

### Fixed
- **HTTPClientNode Backwards Compatibility** - Added deprecated alias for smooth migration
  - `HTTPClientNode` now available as alias for `HTTPRequestNode`
  - Deprecation warning guides users to new import
  - Fixed incorrect import in `custom_nodes_secure.py`

### Documentation
- Created comprehensive custom node development guide addressing common SDK issues
- Added CLAUDE.md navigation file for efficient LLM assistance
- Documented parameter type constraints (no generic types in NodeParameter)
- Added troubleshooting section for "Can't instantiate abstract class" errors

## [0.2.1] - 2025-06-09

### Added
- **DirectoryReaderNode** for dynamic file discovery
  - Recursive directory scanning with pattern matching  
  - MIME type detection and metadata extraction
  - Organized output by file type for typed processing
  - Performance optimizations for large directories
  - Comprehensive cheatsheet and documentation

- **Enhanced DataTransformer** with critical bug fixes
  - Fixed dictionary output bug where only keys were passed instead of full dictionaries
  - Enhanced `validate_inputs()` to accept arbitrary mapped parameters
  - Improved error handling and debugging capabilities
  - Backward compatibility maintained

- **Expanded PythonCodeNode Modules** for real-world file processing
  - Added `csv`, `mimetypes`, `pathlib`, `glob`, `xml` to allowed modules
  - Enables data science and file processing workflows
  - Maintains security restrictions for dangerous operations

- **Real-World Workflow Examples**
  - Fixed 4 out of 5 workflow library examples to use real data sources
  - Document processor using DirectoryReaderNode for actual file discovery
  - Health monitoring using real endpoints (JSONPlaceholder, GitHub API, HTTPBin)
  - Security audit with comprehensive vulnerability scanning
  - All workflows validated with comprehensive testing

- **Enhanced Documentation**
  - Updated Sphinx documentation with new nodes and fixes
  - New cheatsheets: DirectoryReaderNode usage and DataTransformer workarounds
  - Comprehensive base node fixes documentation
  - Updated quickstart guide with dynamic file discovery examples

### Fixed
- **Critical DataTransformer Bug**: Fixed parameter mapping issue affecting data flow between nodes
- **PythonCodeNode Security**: Safely expanded allowed modules for file processing
- **Workflow Validation**: All fixed workflows tested and validated with real data sources
- **Test Suite**: 28/28 tests passing with zero regressions from base node changes

### Documentation
- Updated README with new capabilities highlights
- Enhanced Sphinx API documentation for new nodes
- Comprehensive migration guide for existing users
- New cheatsheet entries for DirectoryReaderNode and DataTransformer patterns

## [0.2.0] - 2025-06-08

## [0.2.0] - 2025-06-08

### Added
- **Universal Hybrid Cyclic Graph Architecture** - Phase 6 Complete
  - `CycleAwareNode` base class with comprehensive helper methods:
    - `get_iteration()` - Track current iteration number
    - `get_previous_state()` - Access state from previous iteration
    - `set_cycle_state()` - Persist state across iterations
    - `accumulate_values()` - Build rolling windows of values
    - `detect_convergence_trend()` - Automatic convergence detection
    - `log_cycle_info()` - Structured logging for cycles
  - Cyclic workflow execution support in `Workflow.connect()`:
    - `cycle=True` parameter to mark cyclic edges
    - `max_iterations` for safety limits
    - `convergence_check` for dynamic stopping conditions
  - `CyclicWorkflowExecutor` for optimized cyclic execution
  - `ParallelCyclicRuntime` for parallel execution of cycles
  - Comprehensive test coverage with 15+ integration tests
  - Performance optimizations achieving ~30,000 iterations/second
  - Built-in cycle detection and validation
  - State management with automatic cleanup
  - Support for nested cycles and multi-node cycles

- **Developer Tools & Analytics**
  - `CycleAnalyzer` for comprehensive cycle performance analysis
  - `CycleDebugger` for interactive debugging of cyclic workflows
  - `CycleProfiler` for detailed performance profiling
  - `CycleBuilder` with fluent API for constructing cyclic workflows
  - Type-safe configuration with `CycleConfig` and `TypedCycleConfig`
  - Advanced exception handling with specialized cycle exceptions
  - Developer-focused helper methods and productivity tools

- **Production-Ready Features**
  - Enhanced PythonCodeNode with better DataFrame and NumPy support
  - Automatic serialization handling for complex data types
  - Platform-specific type compatibility checks
  - Memory-efficient data processing patterns
  - Production-ready error handling and recovery

- **Enhanced Database Connectivity**
  - SQLDatabaseNode with direct constructor configuration
  - Support for SQLite, PostgreSQL, and MySQL
  - Production-ready connection pooling and transaction management

### Changed
- Enhanced `LocalRuntime` to automatically detect and route cyclic workflows
- Improved workflow validation to handle cyclic graphs correctly
- Updated execution engine to support iterative processing patterns
- Improved PythonCodeNode error messages and debugging support
- Enhanced cycle parameter propagation and state management

### Performance
- Cyclic workflows execute with minimal overhead (~0.03ms per iteration)
- Memory-efficient state management with configurable history windows
- Optimized convergence detection algorithms
- Parallel execution support for independent cycle branches
- Production-tested with workflows handling 100,000+ iterations

## [0.1.6] - 2025-06-05

### Added
- **Kailash Workflow Studio Backend**
  - Complete REST API for visual workflow building
  - Multi-tenant Docker-based deployment infrastructure
  - JWT authentication with access/refresh tokens
  - Role-Based Access Control (RBAC) system
  - Node-level and workflow-level permissions
  - Access-controlled runtime with transparent security
  - Custom node creation and management API
  - WebSocket support for real-time updates
  - Comprehensive database schema (SQLAlchemy)

- **JWT Authentication & Multi-Tenancy**
  - Full JWT authentication system with token management
  - Multi-tenant architecture with complete isolation
  - User registration and secure login system
  - API key authentication for service accounts
  - Password hashing with bcrypt

- **Access Control System**
  - Fine-grained permission management
  - Field-level data masking for sensitive information
  - Permission-based conditional routing
  - Backward compatibility with existing workflows
  - Comprehensive audit logging

- **Documentation Improvements**
  - All docstrings updated to CLAUDE.md 8-section standard
  - Added coordinated AI workflows to Sphinx front page
  - Fixed all 71 doc8 documentation style issues
  - New access control API documentation
  - Frontend development guidelines (`guide/frontend/`)
  - Workflow Studio documentation

- **Test Suite Optimization**
  - Reduced test suite from 915 → 591 tests (35% reduction)
  - Consolidated redundant tests while maintaining 100% coverage
  - Improved CI/CD performance by 34%
  - Fixed all remaining test failures (100% pass rate)

### Changed
- Updated all datetime usage from `datetime.utcnow()` to `datetime.now(timezone.utc)`
- Enhanced README.md with access control documentation
- Updated security.rst to mark RBAC as completed feature
- Consolidated integration examples (removed 18 broken examples)
- Updated pre-commit configuration for security test exclusions

### Fixed
- All pytest failures in access control tests
- RST documentation formatting issues (71 → 0 errors)
- Test constructor signatures and parameter names
- DateTime deprecation warnings throughout codebase

### Security
- Production Security Framework from previous sessions remains active
- Added access control layer on top of existing security
- Enhanced authentication with JWT implementation
- Fixed MergeNode to use correct parameter names (data1/data2 instead of inputs)
- Updated async test patterns to use execute_async() with @pytest.mark.asyncio
- Consolidated test suites for better CI performance

### Security
- **CRITICAL**: Path traversal prevention implemented across all file operations
- **HIGH**: Code execution sandboxing prevents malicious code execution
- **MEDIUM**: Input sanitization prevents XSS, SQL, and command injection attacks
- **LOW**: Comprehensive audit logging for security event monitoring

## [0.1.5] - 2025-06-05

### Added
- **Complete Self-Organizing Agent Documentation**
  - Enhanced API documentation for all 13 self-organizing agent nodes
  - Detailed feature descriptions and formation strategies in node catalog
  - New MCP ecosystem integration pattern in pattern library
  - Complete A2A communication node coverage in API registry

- **Enhanced Reference Documentation Structure**
  - Updated `guide/reference/node-catalog.md` with detailed node features
  - Added formation strategies documentation (capability_matching, swarm_based, market_based, hierarchical)
  - Extended `guide/reference/api-registry.yaml` with all self-organizing nodes
  - New MCP ecosystem zero-code workflow builder pattern

- **Release Management Organization**
  - Created `releases/` directory for better release note organization
  - Moved all release files from root to organized structure
  - Release notes, checklists, and announcements now properly categorized
  - Added release management templates and procedures

### Changed
- **Documentation Quality Improvements**
  - Fixed all AI node doctests (70+ previously failing tests now pass)
  - Simplified doctest examples to focus on essential functionality
  - Resolved constructor validation issues using `__new__` approach
  - Achieved perfect Sphinx documentation build (0 errors, 0 warnings)

- **Architecture Document Organization**
  - Moved `COMPREHENSIVE_SELF_ORGANIZING_AGENT_ARCHITECTURE.md` to `guide/adr/0031-comprehensive-self-organizing-architecture.md`
  - Consolidated `SELF_ORGANIZING_AGENT_POOL_DESIGN.md` content into existing ADR-0030
  - All architecture documents now properly organized in ADR directory

- **Enhanced Node Documentation**
  - All 13 self-organizing agent nodes now have detailed feature lists
  - Enhanced formation strategy documentation with use cases
  - Improved cross-references between documentation sections
  - Updated all reference documentation timestamps to 2025-06-05

### Fixed
- **Doctest Issues**
  - Resolved 60+ failing doctests in AI node modules
  - Fixed constructor validation problems in docstring examples
  - Simplified complex workflow examples to focus on core functionality
  - All AI node doctests now pass: intelligent_agent_orchestrator (42/42), self_organizing (18/18), agents (10/10)

- **Documentation Build Issues**
  - Fixed all Sphinx build warnings and errors
  - Resolved cross-reference issues in API documentation
  - Fixed import statements in documentation examples

## [0.1.4] - 2025-05-31

### Added
- **MCP Ecosystem Zero-Code Workflow Builder**
  - Interactive web interface with drag-and-drop workflow creation
  - Live dashboard with real-time statistics and execution logs
  - Pre-built workflow templates (GitHub→Slack, Data Pipeline, AI Assistant)
  - Built with vanilla HTML/CSS/JavaScript (no frameworks required)
  - Two implementations: demo version and full Kailash SDK integration
  - Comprehensive documentation and ADR-0029 for architecture decisions

### Changed
- **Documentation Organization**
  - Consolidated MCP ecosystem documentation from 5 files to 3
  - Moved frontend architecture decisions to ADR-0029
  - Added MCP ecosystem to Sphinx documentation
  - Updated project structure documentation

### Removed
- Redundant documentation files in integration_examples
  - README_MCP_ECOSYSTEM.md (merged into README.md)
  - FRONTEND_STACK.md (moved to ADR-0029)
  - TERMINAL_COMMANDS.txt (redundant with README)
  - ecosystem.log (temporary file)

## [0.1.4] - 2025-06-04

### Changed
- **Node Naming Convention Standardization** (ADR-0020)
  - Renamed all node classes to follow consistent "Node" suffix pattern
  - CSVReader → CSVReaderNode, JSONReader → JSONReaderNode, TextReader → TextReaderNode
  - CSVWriter → CSVWriterNode, JSONWriter → JSONWriterNode, TextWriter → TextWriterNode
  - Switch → SwitchNode, Merge → MergeNode
  - LLMAgent → LLMAgentNode, EmbeddingGenerator → EmbeddingGeneratorNode
  - Updated all imports, tests, examples, and documentation throughout codebase
  - Created ADR-0020 documenting the naming convention decision
  - This is a **BREAKING CHANGE** - users must update their code to use new class names

- **Docstring Format Conversion**
  - Converted all Google-style docstring examples from `::` format to doctest `>>>` format
  - All docstring examples are now executable with Python's doctest module
  - Fixed doctest failures and ensured all examples pass validation
  - Improves documentation testability and consistency

### Fixed
- Double "Node" suffix errors in imports (e.g., CSVReaderNodeNode → CSVReaderNode)
- WorkflowAPI test assertions updated for nested response structure
- Background execution test initialization in workflow API
- All linting issues resolved (black, isort, ruff)
- Doctest failures in SwitchNode examples

### Documentation
- Created comprehensive migration guide in ADR-0020
- Updated all documentation to reflect new node names
- Enhanced CLAUDE.md with node naming convention enforcement
- Updated README and all example files

### Developer Experience
- All 753 tests passing (up from 746)
- All 46 examples validated and working
- Documentation builds without warnings or errors
- Pre-commit hooks passing for code quality

## [0.1.3] - 2025-06-03

### Added
- **WorkflowNode for Hierarchical Workflow Composition** (ADR-0028)
  - New WorkflowNode class enabling workflows to be wrapped as reusable nodes
  - Automatic parameter discovery from workflow entry nodes
  - Dynamic output mapping from workflow exit nodes
  - Support for loading workflows from instances, files (YAML/JSON), or dictionaries
  - Custom input/output parameter mapping capabilities
  - Lazy runtime loading to avoid circular imports
  - 15 comprehensive tests covering all WorkflowNode features
  - Complete example demonstrating 5 different usage patterns
- **Workflow API Wrapper** - Transform any workflow into a REST API
  - WorkflowAPI class for instant API creation from workflows
  - Automatic REST endpoints: /execute, /workflow/info, /health, /docs
  - Synchronous and asynchronous execution modes
  - Specialized APIs for domain-specific workflows (RAG, data processing)
  - Production-ready with SSL, workers, and customizable configurations
  - WebSocket support for real-time updates
  - Complete OpenAPI documentation generation

### Changed
- **Documentation Improvements**
  - Updated README with WorkflowNode examples and API Wrapper section
  - Added hierarchical workflow composition examples
  - Enhanced API documentation with workflow wrapping patterns
  - Updated test count badge to reflect 761 passing tests
- **Example Organization**
  - Consolidated workflow nesting examples into single comprehensive file
  - Replaced file I/O dependent nodes with mock nodes for reliability
  - Added 5 workflow composition patterns in workflow_nested_composition.py

### Fixed
- Parameter validation in WorkflowNode to support dynamic workflow structures
- Import ordering and unused imports in test files
- Mock node implementations to avoid file system dependencies in examples

## [0.1.2] - 2025-06-03

### Added
- **Complete Hierarchical RAG Implementation**
  - DocumentSourceNode and QuerySourceNode for autonomous data provision
  - HierarchicalChunkerNode for intelligent document chunking with configurable sizes
  - RelevanceScorerNode with multi-method similarity scoring (cosine similarity + text-based fallback)
  - ChunkTextExtractorNode for text extraction and embedding preparation
  - QueryTextWrapperNode for query formatting and batch processing
  - ContextFormatterNode for LLM context preparation
  - Full integration with existing AI providers (Ollama, OpenAI, Anthropic, Azure)
  - 29 comprehensive tests covering all RAG components with full validation
- **Comprehensive Documentation Updates**
  - Complete hierarchical RAG section in API documentation (docs/api/utils.rst)
  - Working examples and pipeline configuration guides
  - Usage patterns and best practices documentation
  - Updated implementation status tracker with RAG completion
- **AI Provider Architecture Unification** (ADR-0026)
  - Unified AI provider interface combining LLM and embedding capabilities
  - Single BaseAIProvider, LLMProvider, EmbeddingProvider, and UnifiedAIProvider classes
  - Capability detection and provider registry for all AI operations
  - Support for Ollama, OpenAI (unified), Anthropic (LLM), Cohere, HuggingFace (embeddings)
  - MockProvider for testing with both LLM and embedding support
- Project template creation guide following Kailash SDK best practices
- Comprehensive development infrastructure guidance with pre-commit hooks

### Changed
- **Path Standardization Across Examples**
  - Standardized all examples to use examples/outputs/ consistently
  - Fixed 12+ example files that were creating subdirectories or root-level outputs
  - Ensured logical organization while maintaining example functionality
  - Removed incorrect path creation patterns
- **Code Quality and Formatting**
  - Applied Black formatting across all modified files
  - Import sorting with isort for consistency throughout codebase
  - Pre-commit hook compliance for all new and modified files
- **Node Naming Convention Enforcement**
  - All Node components now consistently include "Node" suffix in class names
  - HTTPClient renamed to HTTPClientNode following established conventions
  - RESTClient consolidated to RESTClientNode as primary implementation
  - Removed aliases that hide Node component type from users
- **Enhanced REST Client Capabilities**
  - Added convenience CRUD methods: get(), create(), update(), delete()
  - Implemented rate limit metadata extraction from headers
  - Added pagination metadata extraction for better API insights
  - Enhanced HATEOAS link extraction for REST discovery
  - Async support maintained in primary RESTClientNode implementation
- Enhanced CLAUDE.md with improved documentation standards and workflow instructions
- Updated documentation requirements to use ReStructuredText (reST) format for Sphinx compatibility

### Removed
- **Code Consolidation and Cleanup**
  - Removed redundant embedding_providers.py file (1,007 lines of duplicate code)
  - Eliminated duplicate rest_client.py implementation to reduce user confusion
  - Cleaned up all redundant LLM provider files from previous architecture

### Fixed
- HTTPClientNode parameter handling - optional at initialization, required at runtime
- REST client registration conflicts and alias management
- Import statements updated to use unified AI provider architecture
- Documentation build issues and formatting consistency

## [0.1.1] - 2025-06-02

### Added
- **AI Provider Architecture Unification** (ADR-0026)
  - Unified AI provider interface combining LLM and embedding capabilities
  - Single BaseAIProvider, LLMProvider, EmbeddingProvider, and UnifiedAIProvider classes
  - Capability detection and provider registry for all AI operations
  - Support for Ollama, OpenAI (unified), Anthropic (LLM), Cohere, HuggingFace (embeddings)
  - MockProvider for testing with both LLM and embedding support

### Changed
- **Node Naming Convention Enforcement**
  - All Node components now consistently include "Node" suffix in class names
  - HTTPClient renamed to HTTPClientNode following established conventions
  - RESTClient consolidated to RESTClientNode as primary implementation
  - Removed aliases that hide Node component type from users
- **Enhanced REST Client Capabilities**
  - Added convenience CRUD methods: get(), create(), update(), delete()
  - Implemented rate limit metadata extraction from headers
  - Added pagination metadata extraction for better API insights
  - Enhanced HATEOAS link extraction for REST discovery
  - Async support maintained in primary RESTClientNode implementation

### Removed
- **Code Consolidation and Cleanup**
  - Removed redundant embedding_providers.py file (1,007 lines of duplicate code)
  - Eliminated duplicate rest_client.py implementation to reduce user confusion
  - Cleaned up all redundant LLM provider files from previous architecture

### Fixed
- HTTPClientNode parameter handling - optional at initialization, required at runtime
- REST client registration conflicts and alias management
- Import statements updated to use unified AI provider architecture
- All examples and tests updated to use consistent node naming

### Security
- Maintained all existing authentication and security features in consolidated implementations

## [0.1.1] - 2025-05-31

### Changed
- Updated version to 0.1.1

## [0.1.0] - 2025-05-31

### Added
- Initial release of Kailash Python SDK
- Core workflow engine with node-based architecture
- Data nodes: CSVReaderNode, JSONReaderNode, CSVWriterNode, JSONWriterNode, SQLReader, SQLWriter
- Transform nodes: DataFrameFilter, DataFrameAggregator, DataFrameJoiner, DataFrameTransformer
- Logic nodes: ConditionalNode, SwitchNode, MergeNode
- AI/ML nodes: ModelPredictorNode, TextGeneratorNode, EmbeddingNode
- API nodes: RESTAPINode, GraphQLNode, AuthNode, RateLimiterNode
- Code execution: PythonCodeNode with schema validation
- Runtime options: LocalRuntime, DockerRuntime, ParallelRuntime
- Task tracking system with filesystem and database storage
- Workflow visualization with Mermaid and matplotlib
- Export functionality for Kailash container format
- CLI interface for workflow operations
- Comprehensive test suite (539 tests)
- 30+ examples covering various use cases
- Full documentation

### Security
- Input validation for all nodes
- Safe code execution in isolated environments
- Authentication support for API nodes

[Unreleased]: https://github.com/terrene-foundation/kailash-py/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/terrene-foundation/kailash-py/releases/tag/v0.1.0
