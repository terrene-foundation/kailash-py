# Kailash Python SDK - Product Requirements Document

## 1. Executive Summary

The Kailash Python SDK is designed to bridge the gap between AI Business Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. This SDK will enable ABCs to rapidly prototype workflows within Kailash's architectural paradigm without requiring deep technical knowledge of containerization, while ensuring a smooth handoff to PDT for production deployment.

### 1.1 Problem Statement

Currently, ABCs generate code without consulting PDT, leading to architectural misalignment. ABCs follow traditional scripting approaches while Kailash uses a container-node architecture. This creates friction during handoff as PDT must extensively refactor ABC prototypes.

### 1.2 Solution Overview

A PyPI-hosted package (`kailash_python_sdk`) that provides:

1. A Pythonic interface for defining nodes and workflows
2. Automatic validation of node contracts
3. Local execution capabilities for rapid testing
4. Export functionality to convert Pythonic workflows into Kailash-compatible formats
5. Pre-built node types for common operations

## 2. Project Goals

1. **Reduce Handoff Friction**: Minimize the refactoring required when transitioning from ABC prototypes to PDT production implementations
2. **Accelerate Prototyping**: Enable ABCs to rapidly create and test workflows without deep technical expertise
3. **Ensure Architectural Compliance**: Guide ABCs toward creating code that aligns with Kailash's container-node architecture
4. **Maintain Flexibility**: Allow domain-specific customization while enforcing structural consistency
5. **Provide Testing Capabilities**: Enable verification of workflows without deploying to the shared Kailash environment

## 3. Architecture Overview

The SDK will consist of the following key components:

```
kailash_python_sdk/
├── nodes/                # Node definitions and base classes
├── workflow/             # Workflow builder and visualization
├── runtime/              # Local execution environment
├── tracking/             # Task tracking and monitoring
├── utils/                # Helper utilities
├── cli/                  # Command-line interface for management
└── docs/                 # Documentation
    └── adr/              # Architecture Decision Records
```

## 4. Component Requirements

### 4.1 Core Node System

#### Base Node Class
- **Purpose**: Provide a consistent interface for all node types
- **Requirements**:
  - Define a standard contract (`run(**kwargs) -> dict`)
  - Handle parameter validation
  - Enforce JSON-serializable outputs
  - Provide logging capabilities
  - Support metadata like description, version, etc.

#### Node Registry
- **Purpose**: Manage available node types
- **Requirements**:
  - Auto-discover custom nodes
  - Provide node catalog functionality
  - Support versioning
  - Enable documentation generation

#### Pre-built Node Types
- **Purpose**: Provide ready-to-use nodes for common operations
- **Requirements**:
  - Data connectors (CSV, JSON, API, database)
  - Transformation nodes (filter, map, join)
  - AI/ML nodes (classification, NLP, embedding)
  - Logic nodes (conditional, loop, aggregation)

### 4.2 Workflow Builder

#### Workflow Class
- **Purpose**: Define and manage directed acyclic graphs (DAGs) of nodes
- **Requirements**:
  - Add nodes with parameters
  - Connect nodes with explicit data mappings
  - Validate workflow integrity (cycle detection, etc.)
  - Support visualization
  - Enable persistence/serialization
  - Export to Kailash-compatible formats

#### Workflow Visualization
- **Purpose**: Visualize workflows for understanding and documentation
- **Requirements**:
  - Generate networkx-based graph diagrams
  - Support interactive visualization
  - Enable export to common formats (PNG, SVG)

### 4.3 Local Runtime

#### Execution Engine
- **Purpose**: Run workflows locally for testing and validation
- **Requirements**:
  - Execute nodes in topological order
  - Handle data passing between nodes
  - Provide execution status and monitoring
  - Support parameter overrides
  - Enable debugging capabilities

#### Testing Utilities
- **Purpose**: Facilitate testing of nodes and workflows
- **Requirements**:
  - Mock data generation
  - Node isolation testing
  - Workflow integration testing
  - Performance benchmarking

### 4.4 Utilities

#### Export Utilities
- **Purpose**: Convert Pythonic workflows to Kailash formats
- **Requirements**:
  - Generate YAML definitions
  - Manage metadata
  - Handle environment variable substitution
  - Support validation

#### Template System
- **Purpose**: Provide starter templates for common use cases
- **Requirements**:
  - Project scaffolding
  - Example workflows
  - Documentation templates

### 4.5 Command-Line Interface

#### CLI Tool
- **Purpose**: Provide command-line management of workflows
- **Requirements**:
  - Initialize projects
  - Run workflows
  - Validate workflows
  - Generate documentation
  - Test nodes and workflows

## 5. Detailed API Specifications

### 5.1 Node API

```python
class Node:
    def __init__(self, name=None, description=None):
        """
        Initialize a new node.
        
        Args:
            name (str, optional): Node name. Defaults to class name.
            description (str, optional): Node description.
        """
    
    def run(self, **kwargs) -> dict:
        """
        Execute the node's logic. Must be implemented by subclasses.
        
        Returns:
            dict: Output data as a JSON-serializable dictionary
        """
        
    def validate_inputs(self, **kwargs) -> bool:
        """
        Validate input parameters.
        
        Returns:
            bool: True if inputs are valid
        """
        
    def get_schema(self) -> dict:
        """
        Get node schema for documentation and validation.
        
        Returns:
            dict: Schema definition
        """
```

### 5.2 Workflow API

```python
class Workflow:
    def __init__(self, name, description=None):
        """
        Create a new workflow.
        
        Args:
            name (str): Workflow name
            description (str, optional): Workflow description
        """
    
    def add_node(self, id, node, **params) -> str:
        """
        Add a node to the workflow.
        
        Args:
            id (str): Node identifier
            node (Node): Node instance
            **params: Node parameters
            
        Returns:
            str: Node identifier
        """
    
    def connect(self, from_node, to_node, mappings=None):
        """
        Connect two nodes.
        
        Args:
            from_node (str): Source node ID
            to_node (str): Target node ID
            mappings (dict, optional): Output-to-input key mappings
        """
    
    def visualize(self, output_path=None):
        """
        Generate a visualization of the workflow.
        
        Args:
            output_path (str, optional): Path to save the visualization
        """
    
    def export_to_kailash(self, path):
        """
        Export workflow to Kailash format.
        
        Args:
            path (str): Output file path
        """
    
    def run(self, inputs=None) -> dict:
        """
        Execute the workflow locally.
        
        Args:
            inputs (dict, optional): Runtime parameter overrides
            
        Returns:
            dict: Execution results
        """
```

### 5.3 Runtime API

```python
def execute_workflow(workflow, inputs=None) -> dict:
    """
    Execute a workflow locally.
    
    Args:
        workflow (Workflow): Workflow to execute
        inputs (dict, optional): Runtime parameter overrides
        
    Returns:
        dict: Execution results
    """
```

## 6. User Workflows

### 6.1 ABC Workflow Creation

1. Install the SDK: `pip install kailash-python-sdk`
2. Create a new project: `kailash init my_project`
3. Define custom nodes (or use pre-built nodes)
4. Create a workflow by connecting nodes
5. Test the workflow locally
6. Export to Kailash format for PDT handoff

### 6.2 PDT Integration

1. Receive exported workflow from ABC
2. Review node definitions and connections
3. Optimize for production deployment
4. Deploy to Kailash cluster

## 7. Dependencies and Constraints

### 7.1 Dependencies

- **Python**: >=3.8
- **Core Libraries**:
  - networkx: For graph representation
  - pydantic: For schema validation
  - matplotlib/pygraphviz: For visualization
  - PyYAML: For serialization

### 7.2 Constraints

- Must maintain backward compatibility with Kailash architecture
- Must be installable via pip from PyPI
- Must work cross-platform (Windows, macOS, Linux)
- Must not require Docker for basic operations

## 8. Implementation Timeline

### Phase 1: Core Framework (Weeks 1-2)
- Base node class and registration system
- Workflow builder
- Basic visualization
- Initial ADRs for core architecture

### Phase 2: Runtime and Testing (Weeks 3-4)
- Local execution engine
- Testing utilities
- Example nodes
- ADRs for execution strategy

### Phase 3: Task Tracking System (Weeks 5-6)
- Task tracking models and manager
- Storage backends
- Monitoring capabilities
- ADRs for task tracking architecture

### Phase 4: CLI and Integration (Weeks 7-8)
- Command-line interface
- Kailash export functionality
- Task monitoring commands
- Documentation

### Phase 5: Pre-built Nodes (Weeks 9-10)
- Data connector nodes
- Transformation nodes
- AI/ML nodes

## 9. Success Metrics

1. **Adoption Rate**: >90% of ABCs using the SDK within 3 months
2. **Handoff Efficiency**: >70% reduction in code refactoring during ABC-to-PDT transitions
3. **Prototype Speed**: >50% reduction in time from concept to working prototype
4. **Quality**: <5% of workflows requiring architectural changes after handoff

## 10. Appendix: Example Implementation

### Example: Custom Node

```python
from kailash_python_sdk.nodes.base import Node

class DataTransformNode(Node):
    """Transform data using a provided function."""
    
    def run(self, data, transform_function=None):
        """
        Apply a transformation to input data.
        
        Args:
            data (list): Input data to transform
            transform_function (callable, optional): Function to apply
            
        Returns:
            dict: Transformed data
        """
        if transform_function is None:
            # Default transformation: identity
            result = data
        else:
            result = [transform_function(item) for item in data]
        
        return {
            "transformed_data": result,
            "count": len(result)
        }
```

### Example: Workflow Definition

```python
from kailash_python_sdk.workflow import Workflow
from kailash_python_sdk.nodes.data import CSVReader
from kailash_python_sdk.nodes.transform import Filter, Aggregator
from my_nodes import DataTransformNode

# Create workflow
workflow = Workflow(
    name="data_processing_workflow",
    description="Process CSV data and generate aggregations"
)

# Add nodes
workflow.add_node(
    "read_csv",
    CSVReader(),
    file_path="data.csv",
    delimiter=","
)

workflow.add_node(
    "filter",
    Filter(),
    condition=lambda row: row["value"] > 100
)

workflow.add_node(
    "transform",
    DataTransformNode(),
    transform_function=lambda x: x * 2
)

workflow.add_node(
    "aggregate",
    Aggregator(),
    group_by="category",
    metrics=["sum", "avg", "count"]
)

# Connect nodes
workflow.connect("read_csv", "filter", {
    "data": "data"
})

workflow.connect("filter", "transform", {
    "filtered_data": "data"
})

workflow.connect("transform", "aggregate", {
    "transformed_data": "data"
})

# Visualize and save
workflow.visualize("workflow.png")

# Run workflow
results = workflow.run()

# Export for PDT
workflow.export_to_kailash("workflow.yaml")
```
