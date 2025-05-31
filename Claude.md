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
   - Sort them according to isort conventions
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

The project structure is recorded in `guide/prd/0000-project_structure.md`. Refer to it when necessary.

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
   - Always reference the PRDs in `guide/prd` when generating codes and implementing features.
   - Update the PRD if requirements change during development
   - Link ADRs to relevant sections of the PRD

2. **Architecture Decision Records (ADRs)**
   - All significant architectural decisions should be documented using ADRs:
     - **README.md**: Follow the instructions in `guide/adr/README.md` for creating and managing ADRs.
     - **Format**: Follow the ADR template in `guide/adr/`
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
     - **Summary**: Include a summary of new ADRs in guide/adr/README.md

3. **Todos Management**:
   - Use the TodoRead and TodoWrite tools to manage active tasks during sessions.
   - Maintain the master todo list in `guide/todos/000-master.md` using this structure:

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
   - Examples are organized into categories:
     - `node_examples/` - Individual node usage examples
     - `workflow_examples/` - Workflow patterns and use cases
     - `integration_examples/` - API and external system integrations
     - `visualization_examples/` - Workflow visualization and reporting
   - Follow naming conventions: `{category}_{description}.py` (e.g., `node_custom_creation.py`, `workflow_basic.py`)
   - Ensure examples demonstrate best practices and common usage patterns.
   - Read the `guide/mistakes/000-master.md` file to avoid common pitfalls in examples.
   - **Testing Examples**: Use `examples/_utils/test_all_examples.py` as the entrypoint to test all examples:
     ```bash
     cd examples
     python _utils/test_all_examples.py
     ```
   - This script automatically discovers and validates all example files across all categories
   - Create a basic, simple, and complex examples, such as:
     - Basic Node Example: Create a simple node that reads data from a file and writes it to another file
     - Simple Workflow Example: Create a simple workflow that connects two nodes (e.g., a data reader and a transformer)
     - Complex Workflow Example: Create a complex workflow that includes multiple nodes, data transformations, and AI model execution

5. **Unit Tests**:
   - Ensure that examples have been tested and validated before creating unit tests
   - Create unit tests for all components using pytest
   - Maintain >80% code coverage
   - Place tests in a separate `tests/` directory mirroring the package structure
   - Read the `guide/mistakes/000-master.md` file to avoid common pitfalls.

6. **Integration Tests**:
   - Ensure that unit tests have been created for all components before creating integration tests
   - Create integration tests for workflow execution
   - Test export functionality for compatibility with Kailash
   - Read the `guide/mistakes/000-master.md` file to avoid common pitfalls.

7. **Sphinx Documentation**
   - Complete API documentation framework in `docs/`
   - Build with: `cd docs && python build_docs.py`
   - Auto-deployed via GitHub Actions to GitHub Pages
   - All public APIs must have comprehensive docstrings with examples

8. **Documentation Tests**:
   - Include examples in docstrings that can be verified with doctest

9. **Mistakes**: Record all coding mistakes in `guide/mistakes/000-master.md`
    - **Example**: If a node fails to execute due to a missing import, document the mistake in `guide/mistakes/missing_import.md`
    - Include:
      - Description of the mistake
      - Code example that caused the issue
      - Solution or fix applied

10. **Update README.md**:
    - Overview of the project
    - Installation instructions
    - Quick start guide
    - Usage examples
    - API reference
    - Contribution guidelines
    - Reference to the PRD and ADRs

11. **Update ADRs**:
    - Ensure all architectural decisions are documented in the ADRs.
    - Link relevant ADRs to the PRD and README.md.
    - Update ADRs as new decisions are made or existing ones are modified.

12. **Update Claude.md**:
    - If there are any changes to the coding standards, conventions, or design principles, update the Claude.md file accordingly.
    - Update the project structure if there are any changes to the directory layout or file organization.

13. **Pre-commit Hooks and Code Quality**:
    - **Pre-commit Setup**: Use automated pre-commit hooks to enforce coding standards
    - **Automated Hooks Configuration** (`.pre-commit-config.yaml`):
      - **Black**: Code formatting (88 character line length)
      - **isort**: Import sorting (Black-compatible profile)
      - **Ruff**: Fast Python linting with auto-fixes
      - **pytest**: Unit tests (subset for speed)
      - **Trivy**: Security vulnerability scanning
      - **detect-secrets**: Secret detection with baseline
      - **doc8**: Documentation linting
      - **mypy**: Type checking
      - **Built-in checks**: Whitespace, file endings, syntax validation
    - **Development Workflow**:
      - Hooks run automatically on every commit
      - Failed hooks prevent commits (encourages fixing issues immediately)
      - Manual formatting commands still available when needed
      - See `guide/development/pre-commit-hooks.md` for comprehensive documentation

14. **Github Actions**:
    - Use Github Actions for continuous integration.
    - Test locally before pushing changes.

15. **Github Issues and Project Update**:
    - Use the Github Issues and Projects to track tasks and progress.
    - Create issues for each task in the Todo list, describing the task and linking to the relevant ADR or PRD.
    - Update the project board as tasks are completed.

# important-instruction-reminders
Do what has been asked; nothing more, nothing less.
NEVER create files unless they're absolutely necessary for achieving your goal.
ALWAYS prefer editing an existing file to creating a new one.
NEVER proactively create documentation files (*.md) or README files. Only create documentation files if explicitly requested by the User.
