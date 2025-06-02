# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Data nodes: CSVReader, JSONReader, CSVWriter, JSONWriter, SQLReader, SQLWriter
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

[Unreleased]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/terrene-foundation/kailash-py/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/terrene-foundation/kailash-py/releases/tag/v0.1.0
