# Rules for Claude.md - Kailash Python SDK

## Project Purpose and Background

The Kailash Python SDK is designed to solve a collaboration problem between AI Business Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. The SDK provides a framework for creating nodes and workflows that align with Kailash's container-node architecture while allowing ABCs to prototype rapidly without deep technical knowledge.

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

4. **Product Requirements Document (PRD)**:
   - Include the full PRD in the `docs/prd/` directory
   - Reference the PRD in code comments when implementing specific requirements
   - Update the PRD if requirements change during development
   - Link ADRs to relevant sections of the PRD

5. **README.md**: Include comprehensive documentation with:
   - Installation instructions
   - Quick start guide
   - Example usage
   - API reference
   - Contributing guidelines
   - Reference to the PRD and ADRs

## Project Structure

The project should follow this structure:

```
kailash_python_sdk/           # Project root directory
├── src/                      # Source directory
│   └── kailash/              # Package directory (what gets imported)
│       ├── __init__.py       # Package initialization
│       ├── nodes/            # Node definitions
│       │   ├── __init__.py
│       │   ├── base.py       # Base node class
│       │   ├── data/         # Data connector nodes
│       │   │   ├── __init__.py
│       │   │   ├── readers.py # Data source nodes
│       │   │   └── writers.py # Data sink nodes
│       │   ├── transform/    # Transformation nodes
│       │   │   ├── __init__.py
│       │   │   └── processors.py # Data transformation nodes
│       │   ├── logic/        # Business logic nodes
│       │   │   ├── __init__.py
│       │   │   └── operations.py # Logical operation nodes
│       │   └── ai/           # AI & ML nodes
│       │       ├── __init__.py
│       │       └── models.py  # ML model nodes
│       ├── workflow/         # Workflow builder
│       │   ├── __init__.py
│       │   ├── graph.py      # Workflow graph definition
│       │   └── visualization.py # Visualization utilities
│       ├── runtime/          # Execution environment
│       │   ├── __init__.py
│       │   ├── local.py      # Local execution engine
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
│       ├── cli/              # Command-line interface
│       │   ├── __init__.py
│       │   └── commands.py   # CLI commands
│       └── exceptions.py     # Custom exceptions
├── tests/                    # Test directory
│   ├── __init__.py
│   ├── test_nodes/
│   ├── test_workflow/
│   ├── test_runtime/
│   └── test_tracking/
├── docs/                     # Documentation
│   ├── prd/                  # Product Requirements Document
│   │   └── kailash_python_sdk_prd.md # Main PRD document
│   └── adr/                  # Architecture Decision Records
├── examples/                 # Example usage
├── pyproject.toml            # Package build configuration
├── setup.py                  # Package setup script
└── README.md                 # Project README
```
## PRD Requirements
1. **Product Requirements Document (PRD)**:
   - Include the full PRD in the `docs/prd/` directory
   - Reference the PRD when implementing specific requirements
   - Update the PRD if requirements change during development
   - Link ADRs to relevant sections of the PRD

## Tests and Validation

1. **Unit Tests**:
   - Create unit tests for all components using pytest
   - Maintain >80% code coverage
   - Place tests in a separate `tests/` directory mirroring the package structure

2. **Integration Tests**:
   - Create integration tests for workflow execution
   - Test export functionality for compatibility with Kailash

3. **Documentation Tests**:
   - Include examples in docstrings that can be verified with doctest

## Examples
1. **Basic Node Example**:
   - Create a simple node that reads data from a file and writes it to another file
   - Include example code in the `examples/` directory

2. **Simple Workflow Example**:
   - Create a simple workflow that connects two nodes (e.g., a data reader and a transformer)
   - Include example code in the `examples/` directory
   
3. **Complex Workflow Example**:
   - Create a complex workflow that includes multiple nodes, data transformations, and AI model execution
   - Include example code in the `examples/` directory

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

## Deliverables

The final deliverables should include:

1. Complete `kailash_python_sdk` package with all components
2. Comprehensive test suite
3. Documentation including:
   - API reference
   - User guide
   - Examples
   - Developer guide
   - Architecture Decision Records (ADRs)
4. Example projects demonstrating typical usage
5. Setup files for PyPI publication

## Architecture Decision Records (ADRs)

All significant architectural decisions should be documented using ADRs:

1. **Format**: Follow the ADR template in `docs/adr/`
2. **Numbering**: Use sequential numbering (e.g., ADR-0001)
3. **Status**: Mark each ADR as Proposed, Accepted, Deprecated, or Superseded
4. **Updates**: Create new ADRs rather than modifying existing ones
5. **Required ADRs**:
   - Base Node Interface
   - Workflow Representation
   - Local Execution Strategy
   - Data Passing Mechanism
   - Export Format
   - Task Tracking Design
   - Storage Backend Strategy

## Additional Notes

- Focus on making the API intuitive for ABCs who are not deep technical experts
- Prioritize a smooth developer experience
- Balance flexibility with guardrails to guide users toward architectural compliance
- Include helpful error messages that guide users toward correct usage

## Code Generation Guidelines
1. Instructions are inside the `docs/instructions/` directory. Read the latest instructions before starting any implementation.
   - Example: `docs/instructions/001-initial.md` contains the initial instructions for the project.
   - Example: `docs/instructions/002-advanced.md` contains advanced instructions for the project.
   
2. Always reference the PRDs in docs/prd when generating codes.

3. **Todos List**:
   - Use the TodoRead and TodoWrite tools to manage tasks
   - Create the list of tasks before starting the implementation
   - Also, create todo markdown files in the format `docs/todos/001-todo.md`, incrementing the number for each new file
   - Each todo file should contain:
   - A list of tasks to be completed
     - Task descriptions
     - Status of each task (e.g., "To Do", "In Progress", "Done")
     - Example:
      ```
       # Todo List for Kailash Python SDK
       - Task 1: Implement base Node class
         - Description: Create the base class for all nodes with validation and execution contract
         - Status: In Progress
      ```
4. **Github Issues and Project Update**
   - Use the Github Issues and Projects to track tasks and progress
   - Create issues for each task in the Todo list, describing the task and linking to the relevant ADR or PRD
   - Update the project board as tasks are completed