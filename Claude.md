# Rules for Claude.md - Kailash Python SDK

## Project Purpose and Background

The Kailash Python SDK is designed to solve a collaboration problem between 
AI Business Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. 

The SDK provides a framework for creating nodes and workflows that align with 
Kailash's container-node architecture while allowing ABCs to prototype rapidly 
without deep technical knowledge.

## Coding Standards and Conventions

### General Principles

1. **Clean Architecture**: Follow the principles of clean architecture with clear separation of concerns.
2. **Pythonic Style**: Write code that follows Python best practices and idioms.
3. **Type Hints**: Use type hints throughout the codebase to enhance IDE support and documentation.
4. **Documentation**: All classes, methods, and functions must have docstrings.
5. **Error Handling**: Use explicit error handling with descriptive error messages.

### Style Guidelines

1. **Naming Conventions**:
   - Classes: `PascalCase`
   - Functions/Methods: `snake_case`
   - Variables: `snake_case`
   - Constants: `UPPER_SNAKE_CASE`
   - Private attributes/methods: `_leading_underscore`

2. **Code Formatting**:
   - Line length: 88 characters (Black standard)
   - Use spaces, not tabs (4 spaces per indentation level)
   - Follow PEP 8 for other formatting guidelines

3. **Imports**:
   - Group imports in the following order:
     1. Standard library imports
     2. Third-party library imports
     3. Local application imports
   - Sort alphabetically within each group
   - Use absolute imports within the package

## Documentation Requirements

1. **Module Docstrings**: Every module should have a docstring explaining its purpose.
2. **Class Docstrings**: Every class should have a docstring explaining its purpose, behavior, and usage.
3. **Method Docstrings**: Every public method should have a docstring in the following format:
   ```python
   def method(self, arg1, arg2=None):
       """
       Short description of the method.
       
       Longer description if necessary.
       
       Args:
           arg1 (type): Description of arg1
           arg2 (type, optional): Description of arg2. Defaults to None.
           
       Returns:
           type: Description of return value
           
       Raises:
           ExceptionType: Description of when this exception is raised
       """
   ```

4. **Docstrings must comprehensively include the following**
   - Design purpose and philosophy: Explaining why each component exists
   - Upstream dependencies: What components create/use this class
   - Downstream consumers: What components depend on this class
   - Usage patterns: Common ways the component is used
   - Implementation details: How the component works internally
   - Error handling: What exceptions are raised and when
   - Side effects: Any state changes or external impacts
   - Examples: Concrete usage examples where helpful


## Project Structure

The project follows this current structure:

```
kailash_python_sdk/           # Project root directory
├── src/                      # Source directory
│   └── kailash/              # Package directory (what gets imported)
│       ├── __init__.py       # Package initialization
│       ├── manifest.py       # Core manifest and registry
│       ├── sdk_exceptions.py # Custom exceptions
│       ├── nodes/            # Node definitions
│       │   ├── __init__.py
│       │   ├── base.py       # Base node class
│       │   ├── base_async.py # Async base node
│       │   ├── data/         # Data connector nodes
│       │   │   ├── __init__.py
│       │   │   ├── readers.py # Data source nodes
│       │   │   ├── writers.py # Data sink nodes
│       │   │   ├── sql.py     # SQL database nodes
│       │   │   ├── streaming.py # Streaming data nodes
│       │   │   └── vector_db.py # Vector database nodes
│       │   ├── transform/    # Transformation nodes
│       │   │   ├── __init__.py
│       │   │   └── processors.py # Data transformation nodes
│       │   ├── logic/        # Business logic nodes
│       │   │   ├── __init__.py
│       │   │   ├── operations.py # Logical operation nodes
│       │   │   └── async_operations.py # Async operations
│       │   ├── ai/           # AI & ML nodes
│       │   │   ├── __init__.py
│       │   │   ├── models.py  # ML model nodes
│       │   │   └── agents.py  # AI agent nodes
│       │   ├── api/          # API integration nodes
│       │   │   ├── __init__.py
│       │   │   ├── http.py    # HTTP client nodes
│       │   │   ├── rest.py    # REST API nodes
│       │   │   ├── graphql.py # GraphQL nodes
│       │   │   ├── auth.py    # Authentication nodes
│       │   │   └── rate_limiting.py # Rate limiting
│       │   └── code/         # Code execution nodes
│       │       ├── __init__.py
│       │       └── python.py  # Python code execution
│       ├── workflow/         # Workflow management
│       │   ├── __init__.py
│       │   ├── builder.py    # Workflow builder
│       │   ├── graph.py      # Workflow graph definition
│       │   ├── runner.py     # Workflow execution
│       │   ├── state.py      # State management
│       │   ├── visualization.py # Visualization utilities
│       │   ├── visualization_backup.py # Backup visualization
│       │   └── mock_registry.py # Mock registry for testing
│       ├── runtime/          # Execution environment
│       │   ├── __init__.py
│       │   ├── local.py      # Local execution engine
│       │   ├── async_local.py # Async local execution
│       │   ├── parallel.py   # Parallel execution
│       │   ├── docker.py     # Docker runtime
│       │   ├── runner.py     # Runtime runner
│       │   └── testing.py    # Testing utilities
│       ├── tracking/         # Task tracking system
│       │   ├── __init__.py
│       │   ├── models.py     # Task data models
│       │   ├── manager.py    # Task manager
│       │   └── storage/      # Storage backends
│       │       ├── __init__.py
│       │       ├── base.py   # Base storage interface
│       │       ├── filesystem.py # File system storage
│       │       └── database.py # Database storage
│       ├── utils/            # Helper utilities
│       │   ├── __init__.py
│       │   ├── export.py     # Export utilities
│       │   └── templates.py  # Node templates
│       └── cli/              # Command-line interface
│           ├── __init__.py
│           └── commands.py   # CLI commands
├── tests/                    # Test directory (mirrors src structure)
│   ├── __init__.py
│   ├── conftest.py          # PyTest configuration
│   ├── sample_data/         # Test data files
│   ├── test_nodes/          # Node tests
│   │   ├── test_base.py
│   │   ├── test_data.py
│   │   ├── test_api.py
│   │   ├── test_ai.py
│   │   ├── test_code.py
│   │   ├── test_logic.py
│   │   ├── test_transform.py
│   │   └── test_async_operations.py
│   ├── test_workflow/       # Workflow tests
│   │   ├── test_graph.py
│   │   ├── test_state_management.py
│   │   ├── test_visualization.py
│   │   └── test_hmi_state_management.py
│   ├── test_runtime/        # Runtime tests
│   │   ├── test_local.py
│   │   ├── test_docker.py
│   │   ├── test_simple_runtime.py
│   │   └── test_testing.py
│   ├── test_tracking/       # Tracking tests
│   │   ├── test_manager.py
│   │   ├── test_models.py
│   │   └── test_storage.py
│   ├── test_utils/          # Utility tests
│   │   ├── test_export.py
│   │   └── test_templates.py
│   ├── test_cli/            # CLI tests
│   │   └── test_commands.py
│   ├── test_schema/         # Schema validation tests
│   ├── test_validation/     # Type validation tests
│   ├── integration/         # Integration tests
│   │   ├── test_workflow_execution.py
│   │   ├── test_node_communication.py
│   │   ├── test_error_propagation.py
│   │   ├── test_performance.py
│   │   ├── test_storage_integration.py
│   │   ├── test_export_integration.py
│   │   ├── test_visualization_integration.py
│   │   ├── test_task_tracking_integration.py
│   │   ├── test_code_node_integration.py
│   │   ├── test_complex_workflows.py
│   │   └── test_cli_integration.py
│   └── test_ci_setup.py     # CI/CD setup tests
├── docs/                    # Documentation
│   ├── prd/                 # Product Requirements Documents
│   │   └── 0001-kailash_python_sdk_prd.md
│   ├── adr/                 # Architecture Decision Records
│   │   ├── README.md        # ADR summary
│   │   ├── 0000-template.md # ADR template
│   │   ├── 0001-base-node-interface.md
│   │   ├── 0002-workflow-representation.md
│   │   ├── 0003-base-node-interface.md
│   │   ├── 0004-workflow-representation.md
│   │   ├── 0005-local-execution-strategy.md
│   │   ├── 0006-task-tracking-architecture.md
│   │   ├── 0007-export-format.md
│   │   ├── 0008-docker-runtime-architecture.md
│   │   ├── 0009-src-layout-for-package.md
│   │   ├── 0010-python-code-node.md
│   │   ├── 0011-workflow-execution-improvements.md
│   │   ├── 0012-workflow-conditional-routing.md
│   │   ├── 0013-simplify-conditional-logic-nodes.md
│   │   ├── 0014-async-node-execution.md
│   │   ├── 0015-api-integration-architecture.md
│   │   └── 0016-immutable-state-management.md
│   ├── features/            # Feature documentation
│   │   ├── api_integration.md
│   │   ├── python_code_node.md
│   │   └── workflow_pattern.md
│   ├── todos/               # Development task tracking
│   │   ├── 000-master.md    # Master todo list
│   │   └── [session-specific todos]
│   └── adr.md              # ADR overview documentation
├── examples/                # Example usage and demonstrations
│   ├── basic_workflow.py    # Basic workflow patterns
│   ├── comprehensive_workflow_example.py # Complex examples
│   ├── python_code_node_example.py # Code execution
│   ├── api_integration_comprehensive.py # API integration
│   ├── conditional_workflow_example.py # Conditional logic
│   ├── parallel_workflow_example.py # Parallel execution
│   ├── docker_workflow_example.py # Docker runtime
│   ├── state_management_example.py # State management
│   ├── visualization_example.py # Workflow visualization
│   ├── task_tracking_example.py # Task tracking
│   ├── export_workflow.py   # Export functionality
│   ├── error_handling.py    # Error handling patterns
│   ├── data_transformation.py # Data processing
│   ├── custom_node.py       # Custom node development
│   ├── workflow_example.py  # General workflow patterns
│   ├── data/                # Example data files
│   │   ├── customers.csv
│   │   ├── input.csv
│   │   ├── transactions.json
│   │   ├── outputs/         # Generated example outputs
│   │   └── task_storage/    # Task tracking data
│   └── test_all_examples.py # Example validation tests
├── data/                    # Root-level data for testing
│   ├── customers.csv        # Sample datasets
│   ├── transactions.json
│   ├── outputs/             # Processing outputs
│   └── task_storage/        # Task tracking storage
├── output/                  # Generated output files
├── pyproject.toml           # Package build configuration
├── setup.py                 # Package setup script  
├── setup.cfg                # Setup configuration
├── pytest.ini              # PyTest configuration
├── uv.lock                  # UV lockfile
├── README.md                # Project README
├── CONTRIBUTING.md          # Contribution guidelines
├── LICENSE                  # License file
└── Claude.md                # Development guidelines (this file)
```

## Design Principles

1. **Composition Over Inheritance**:
   - Prefer composing functionality over deep inheritance hierarchies
   - Keep inheritance hierarchies shallow (max 2-3 levels)

2. **Single Responsibility Principle**:
   - Each class should have a single responsibility
   - Each module should have a clear, focused purpose

3. **Interface Segregation**:
   - Define clear interfaces through abstract base classes
   - Keep interfaces small and focused

4. **Dependency Inversion**:
   - Depend on abstractions, not concretions
   - Use dependency injection where appropriate

5. **Fail Fast**:
   - Validate inputs early
   - Provide clear error messages
   - Do not silently ignore errors

## Dependencies

Keep dependencies minimal and explicit:

1. **Core Dependencies**:
   - `networkx`: For graph representation and operations
   - `pydantic`: For data validation and schema definition
   - `matplotlib`: For visualization
   - `pyyaml`: For YAML serialization/deserialization

2. **Optional Dependencies**:
   - `pygraphviz`: For advanced visualization (if installed)
   - `pytest`: For testing
   - `black` and `isort`: For code formatting

## Implementation Guidelines

1. **Error Handling**:
   - Define custom exception classes in `exceptions.py`
   - Use specific exception types for different error conditions
   - Include context information in exception messages

2. **Configuration**:
   - Use environment variables for configuration
   - Provide sensible defaults
   - Support configuration overrides

3. **Extensibility**:
   - Design for extension through plugins or custom nodes
   - Document extension points

4. **Performance**:
   - Optimize for developer experience first
   - Address performance bottlenecks as identified

5. **Backward Compatibility**:
   - Maintain compatibility with existing Kailash architecture
   - Document any breaking changes clearly

## Must Follow: Code Generation Guidelines

1. **PRD Requirements**
   - Always reference the PRDs in `docs/prd` when generating codes and implementing features.
   - Update the PRD if requirements change during development
   - Link ADRs to relevant sections of the PRD

2. **Architecture Decision Records (ADRs)**
   - All significant architectural decisions should be documented using ADRs:
     - **README.md**: Follow the instructions in `docs/adr/README.md` for creating and managing ADRs.
     - **Format**: Follow the ADR template in `docs/adr/`
     - **Numbering**: Use sequential numbering (e.g., ADR-0001)
     - **Status**: Mark each ADR as Proposed, Accepted, Deprecated, or Superseded
     - **Updates**: Create new ADRs rather than modifying existing ones
     - **Required ADRs**:
       - Base Node Interface
       - Workflow Representation
       - Local Execution Strategy
       - Data Passing Mechanism
       - Export Format
       - Task Tracking Design
       - Storage Backend Strategy
     - **Summary**: Include a summary of new ADRs in docs/adr/README.md

3. **Todos Management**:
   - Use the TodoRead and TodoWrite tools to manage active tasks during sessions.
   - Maintain the master todo list in `docs/todos/000-master.md` using this structure:
   
   ```markdown
   # Project Status Overview
   - **Category**: Status - Brief description
   
   ## High Priority - Active Tasks
   - **Task Name**
     - Description: Clear, actionable description
     - Status: To Do | In Progress | Completed
     - Priority: High | Medium | Low
     - Details: Implementation specifics or context
   
   ## Medium/Low Priority Tasks
   [Same format as above]
   
   ## Recent Achievements
   - Brief summary of completed work
   
   ## Completed Tasks Archive
   - Condensed historical record organized by development phase
   ```
   
   - **Organization Principles**:
     - Active tasks first, completed tasks archived at bottom
     - Group by priority and functional area (Testing, Documentation, etc.)
     - Use condensed format for completed tasks to reduce file length
     - Include project status overview for quick health assessment
     - Focus on actionable next steps rather than detailed history
   
   - Other todo files in the same directory should record summaries of completed development cycles
   - Always queue these verification tasks at the end of each development cycle:
     - Test examples affected by recent changes
     - Run unit, integration, and documentation tests
     - Verify local GitHub Actions tests pass
     - Update ADRs, todos, and README as needed

4. **Examples**:
   - Always create example nodes and workflows in the `examples/` directory.
   - Ensure examples demonstrate best practices and common usage patterns.
   - Test examples to ensure they work as expected.
   - Create a basic, simple, and complex examples, such as:
     - Basic Node Example: Create a simple node that reads data from a file and writes it to another file
     - Simple Workflow Example: Create a simple workflow that connects two nodes (e.g., a data reader and a transformer)
     - Complex Workflow Example: Create a complex workflow that includes multiple nodes, data transformations, and AI model execution

5. **Unit Tests**:
   - Ensure that examples have been tested and validated before creating unit tests
   - Create unit tests for all components using pytest
   - Maintain >80% code coverage
   - Place tests in a separate `tests/` directory mirroring the package structure

6. **Integration Tests**:
   - Ensure that unit tests have been created for all components before creating integration tests
   - Create integration tests for workflow execution
   - Test export functionality for compatibility with Kailash

7. **Documentation Tests**:
   - Include examples in docstrings that can be verified with doctest

8. **Github Actions**:
   - Use Github Actions for continuous integration.
   - Test locally before pushing changes.
   - Ensure code is linted and formatted using Black and isort before merging.

9. **Update README.md**
   - Overview of the project
   - Installation instructions
   - Quick start guide
   - Usage examples
   - API reference
   - Contribution guidelines
   - Reference to the PRD and ADRs
   
10. **Update ADRs**
    - Ensure all architectural decisions are documented in the ADRs.
    - Link relevant ADRs to the PRD and README.md.
    - Update ADRs as new decisions are made or existing ones are modified.

11. **Update Claude.md**
    - If there are any changes to the coding standards, conventions, or design principles, update the Claude.md file accordingly.
    - Update the project structure if there are any changes to the directory layout or file organization.
   
12. **Github Issues and Project Update**
    - Use the Github Issues and Projects to track tasks and progress. 
    - Create issues for each task in the Todo list, describing the task and linking to the relevant ADR or PRD. 
    - Update the project board as tasks are completed.
