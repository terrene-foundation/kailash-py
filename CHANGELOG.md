# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
