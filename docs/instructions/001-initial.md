## Package Setup Details

### Package Structure
Set up the project with a modern src-layout:
```
kailash_python_sdk/           # Project/repository root
├── src/                      # Source directory
│   └── kailash/              # Actual package (what gets imported)
```

### Build Configuration
Create `pyproject.toml` with:
```toml
[build-system]
requires = ["setuptools>=42", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "kailash"
version = "0.1.0"
description = "Python SDK for the Kailash container-node architecture"
authors = [
    {name = "Terrene Foundation", email = "info@terrene.foundation"}
]
readme = "README.md"
requires-python = ">=3.11"
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
]
dependencies = [
    "networkx>=2.7",
    "pydantic>=1.9",
    "matplotlib>=3.5",
    "pyyaml>=6.0",
    "click>=8.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=3.0",
    "black>=22.0",
    "isort>=5.10",
    "mypy>=0.9",
]

[project.urls]
"Homepage" = "https://github.com/terrene-foundation/kailash-py"
"Bug Tracker" = "https://github.com/terrene-foundation/kailash-py/issues"

[tool.setuptools]
package-dir = {"" = "src"}

[project.scripts]
kailash = "kailash.cli:main"
```

## Project Overview

Create the `kailash_python_sdk` package, a Python SDK that enables AI Business Coaches (ABCs) to develop workflows that align with Kailash's container-node architecture while simplifying the handoff to the Product Delivery Team (PDT). The package should include a comprehensive task tracking system and maintain Architecture Decision Records (ADRs) to document design choices.

The package will use the modern src-layout structure, with the actual importable package being `kailash` inside the `src` directory of the project repository.

## Code Generation Tasks

Generate the following components in order:

1. **Project Structure & Package Setup**
   - Create directory structure with src/kailash layout
   - Set up `pyproject.toml` and `setup.py` for src layout
   - Create README.md and other documentation files
   - Initialize ADR directory with template and initial ADRs
   - Copy the PRD to the docs/prd/ directory

2. **Core Node System**
   - Implement base `Node` class with validation and execution contract
   - Create node registry for discovery and cataloging
   - Implement basic node types
   - Create ADR for node interface design

3. **Workflow Builder**
   - Create `Workflow` class for DAG definition
   - Implement connection and mapping system
   - Add validation logic for workflow integrity
   - Create ADR for workflow representation

4. **Local Runtime**
   - Build execution engine for local testing
   - Implement data passing between nodes
   - Add execution monitoring and debugging capabilities
   - Create ADR for execution strategy

5. **Task Tracking System**
   - Implement task and run data models
   - Create task manager for execution tracking
   - Develop storage backends for persistence
   - Add monitoring and reporting capabilities
   - Create ADR for task tracking architecture

6. **Utilities & Export**
   - Create export functionality to Kailash format
   - Implement visualization utilities
   - Add template system for common patterns
   - Create ADR for export format

7. **CLI Tool**
   - Build command-line interface
   - Implement project scaffolding
   - Add workflow validation and execution commands
   - Implement task monitoring commands

8. **Example Implementation**
   - Create sample nodes and workflows
   - Build comprehensive example project with task tracking

## Implementation Details

### 1. Node System
- Base `Node` class must enforce the contract: `run(**kwargs) -> dict`
- Parameter validation should use type annotations and runtime checking
- All outputs must be JSON-serializable
- Include logging capabilities
- Support metadata like description, version, etc.

### 2. Workflow System
- Support directed acyclic graphs (DAGs) of nodes
- Enable explicit data mappings between nodes
- Validate workflow integrity (detect cycles, missing connections)
- Visualize workflows using networkx and matplotlib
- Support serialization to/from YAML for Kailash compatibility

### 3. Runtime System
- Execute nodes in topological order
- Pass data between nodes according to mappings
- Support parameter overrides at runtime
- Provide execution status and monitoring
- Enable debugging capabilities

### 4. Task Tracking System
- Implement `TaskRun` and `Task` models to represent execution state
- Create a `TaskManager` to coordinate tracking and monitoring
- Develop storage backends (filesystem, database) for persistence
- Add CLI commands for inspecting task history and status
- Integrate with workflow execution to capture execution details

### 5. Export System
- Generate Kailash-compatible YAML definitions
- Handle environment variable substitution
- Support validation of exported workflows
- Maintain metadata during export

### 6. CLI System
- Support project initialization
- Enable workflow execution from command line
- Provide validation commands
- Generate documentation
- Add task monitoring commands

## Key Requirements

1. **Usability**: Make the API intuitive for non-technical ABCs
2. **Architectural Alignment**: Ensure outputs are compatible with Kailash's container-node architecture
3. **Testing Support**: Enable thorough testing without deploying to shared environments
4. **Documentation**: Provide comprehensive documentation and examples
5. **Extensibility**: Allow for custom node types and workflows

## Technical Specifications

1. **Python Version**: Target Python 3.11+
2. **Core Dependencies**:
   - networkx
   - pydantic
   - matplotlib/pygraphviz
   - pyyaml
   - click (for CLI)

3. **Code Style**:
   - Follow PEP 8
   - Use typing hints throughout
   - Document all public interfaces
   - Write unit tests for all components

## Example Usage

The final SDK should support this workflow:

```python
from kailash.workflow import Workflow
from kailash.nodes.data import CSVReader
from kailash.nodes.transform import Filter
from kailash.nodes.logic import Aggregator
from kailash.tracking import TaskManager

# Create workflow
workflow = Workflow(name="data_processing")

# Add nodes
workflow.add_node("read_csv", CSVReader(), file_path="data.csv")
workflow.add_node("filter", Filter(), condition=lambda row: row["value"] > 100)
workflow.add_node("aggregate", Aggregator(), group_by="category")

# Connect nodes
workflow.connect("read_csv", "filter", {"data": "input_data"})
workflow.connect("filter", "aggregate", {"filtered_data": "data"})

# Visualize
workflow.visualize("workflow.png")

# Initialize task tracking
task_manager = TaskManager()

# Run locally with task tracking
results, run_id = workflow.run(task_manager=task_manager)

# View execution results
tasks = task_manager.list_tasks(run_id)
for task in tasks:
    print(f"Task {task.node_id}: {task.status} in {task.get_duration()}s")

# Export for PDT handoff
workflow.export_to_kailash("workflow.yaml")
```

## Development Plan

1. Start with the core `Node` and `Workflow` classes
2. Add basic runtime execution capabilities
3. Implement task tracking system
4. Create storage backends for task persistence
5. Implement export functionality
6. Create pre-built node types
7. Build CLI and utility features
8. Add visualization and documentation features
9. Create example implementations
10. Write comprehensive tests
11. Document architecture decisions in ADRs throughout development

## Architecture Decision Records (ADRs)

For each major architectural decision, create an ADR document following the template provided in the ADR guide. Initial ADRs to create:

1. **Base Node Interface**: Define the standard contract for all nodes
2. **Workflow Representation**: Decide on the graph structure and API
3. **Local Execution Strategy**: Determine how workflows will be executed locally
4. **Task Tracking Architecture**: Establish the design for task tracking and monitoring
5. **Storage Backend Strategy**: Decide on the approach for persisting workflow state

Each ADR should include:
- Context that led to the decision
- The decision itself
- Rationale behind the decision
- Consequences (both positive and negative)
- Implementation notes (if applicable)

Store all ADRs in the `docs/adr/` directory with sequential numbering.
