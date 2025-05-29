# Kailash Python SDK - Product Requirements Document

## 1. Executive Summary

The Kailash Python SDK bridges the gap between AI Business Coaches (ABCs) and the Product Delivery Team (PDT) at Terrene Foundation. This SDK enables ABCs to rapidly prototype workflows within Kailash's container-node architecture without requiring deep technical knowledge, while ensuring a smooth handoff to PDT for production deployment.

### 1.1 Problem Statement

ABCs generate code without consulting PDT, resulting in architectural misalignment. ABCs follow traditional scripting approaches while Kailash uses a container-node architecture, creating friction during handoff as PDT must extensively refactor ABC prototypes.

### 1.2 Solution Overview

A PyPI-hosted package (`kailash_python_sdk`) that provides:

1. A Pythonic interface for defining nodes and workflows
2. Automatic validation of node contracts
3. Local execution capabilities for testing
4. Export functionality to convert workflows into Kailash-compatible formats
5. Pre-built node types for common operations
6. Task tracking for execution monitoring

## 1.3 Deliverables

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

## 1.4 Additional Notes

- Focus on making the API intuitive for ABCs who are not deep technical experts
- Prioritize a smooth developer experience
- Balance flexibility with guardrails to guide users toward architectural compliance
- Include helpful error messages that guide users toward correct usage

## 2. Component Requirements

### 2.1 Node System

#### Base Node Interface
- Standard contract (`run(**kwargs) -> dict`)
- Parameter validation and type checking
- JSON-serializable outputs
- Logging and error handling
- Metadata support (description, version, author)

#### Node Types
- **Data Connectors**: CSV/JSON/DB readers and writers
- **Transformations**: Data processors and filters
- **Logic Nodes**: Conditionals (Switch/Merge) and operations
- **AI/ML Nodes**: ML model integration and agents
- **Code Nodes**: Custom Python code execution

### 2.2 Workflow System

#### Core Components
- **Workflow**: Main class for creating and executing directed acyclic graphs (DAGs)
- **WorkflowBuilder**: Helper class using the builder pattern for complex workflow creation
- **Graph**: Underlying representation of workflow using NetworkX

#### Key Features
- Add nodes with configuration
- Connect nodes with explicit data mappings
- Validate workflow integrity (cycle detection, required inputs)
- Support visualization
- Execute workflows locally
- Export to Kailash-compatible formats

### 2.3 Runtime System

#### Local Execution
- Execute nodes in topological order
- Handle data passing between nodes
- Provide execution status and debugging information
- Support parameter overrides

#### Docker Runtime
- Execute workflows using Docker containers
- Map node types to appropriate container images
- Handle volume mounting for data sharing

### 2.4 Task Tracking

- Track execution status of workflows and nodes
- Record execution metrics (duration, status)
- Persist execution history
- Support filesystem storage backend

### 2.5 Export System

- Generate Kailash-compatible YAML/JSON definitions
- Conversion between Python nodes and Kailash containers
- Support deployment manifests

## 3. API Specifications

### 3.1 Node API

```python
class Node(ABC):
    @abstractmethod
    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        
    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output parameters for this node."""
        
    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute the node's logic."""
        
    def execute(self, **runtime_inputs) -> Dict[str, Any]:
        """Execute with validation and error handling."""
```

### 3.2 Workflow API

```python
class Workflow:
    def __init__(self, workflow_id: str, name: str, **kwargs):
        """Create a new workflow."""
        
    def _add_node_internal(self, node_id: str, node_type: str, 
                         config: Optional[Dict[str, Any]] = None):
        """Add a node to the workflow (internal method)."""
        
    def get_node(self, node_id: str) -> Optional[Node]:
        """Get node instance by ID."""
        
    def get_execution_order(self) -> List[str]:
        """Get topological execution order for nodes."""
        
    def validate(self) -> None:
        """Validate the workflow structure."""
        
    def execute(self, inputs: Optional[Dict[str, Any]] = None,
              task_manager: Optional[TaskManager] = None) -> Dict[str, Any]:
        """Execute the workflow."""
```

### 3.3 WorkflowBuilder API

```python
class WorkflowBuilder:
    def __init__(self):
        """Initialize an empty workflow builder."""
        
    def add_node(self, node_type: str, node_id: Optional[str] = None, 
                config: Optional[Dict[str, Any]] = None) -> str:
        """Add a node to the workflow."""
        
    def add_connection(self, from_node: str, from_output: str,
                     to_node: str, to_input: str) -> None:
        """Connect two nodes in the workflow."""
        
    def build(self, workflow_id: str, **kwargs) -> Workflow:
        """Build and return a Workflow instance."""
        
    def clear(self) -> "WorkflowBuilder":
        """Clear builder state."""
        
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "WorkflowBuilder":
        """Create builder from dictionary configuration."""
```

### 3.4 Task Tracking API

```python
class TaskManager:
    def create_run(self, workflow_name: str, metadata: Optional[Dict] = None) -> str:
        """Create a new workflow run."""
        
    def create_task(self, run_id: str, node_id: str, node_type: str) -> TaskRun:
        """Create a new task for a node execution."""
        
    def get_run_summary(self, run_id: str) -> RunSummary:
        """Get a summary of a workflow run."""
        
    def list_tasks(self, run_id: str) -> List[TaskSummary]:
        """List all tasks for a workflow run."""
```

## 4. Example Usage

### Basic Workflow with Direct Creation

```python
from kailash.nodes.data.readers import CSVReader
from kailash.nodes.data.writers import CSVWriter
from kailash.nodes.transform.processors import DataTransformer
from kailash.workflow import Workflow

# Create a workflow
workflow = Workflow(
    workflow_id="simple_etl",
    name="Customer ETL",
    description="Extract, transform, and load customer data"
)

# Add nodes
workflow._add_node_internal(
    "reader",
    "CSVReader",
    {"file_path": "customers.csv", "headers": True}
)

workflow._add_node_internal(
    "transformer",
    "DataTransformer",
    {"transformations": ["lambda row: {**row, 'score': float(row['value']) * 1.5}"]}
)

workflow._add_node_internal(
    "writer",
    "CSVWriter",
    {"file_path": "processed_customers.csv"}
)

# Connect nodes
workflow._add_edge_internal("reader", "data", "transformer", "data")
workflow._add_edge_internal("transformer", "transformed_data", "writer", "data")

# Run the workflow
results = workflow.execute()
```

### Using WorkflowBuilder

```python
from kailash.workflow.builder import WorkflowBuilder

# Create a builder
builder = WorkflowBuilder()

# Add nodes
reader_id = builder.add_node("CSVReader", "reader", 
                           {"file_path": "customers.csv", "headers": True})
transformer_id = builder.add_node("DataTransformer", "transformer", 
                                {"transformations": ["lambda x: {**x, 'tier': 'premium' if x['value'] > 100 else 'standard'}"]})
writer_id = builder.add_node("CSVWriter", "writer", 
                           {"file_path": "processed_customers.csv"})

# Add connections
builder.add_connection(reader_id, "data", transformer_id, "data")
builder.add_connection(transformer_id, "transformed_data", writer_id, "data")

# Build and run the workflow
workflow = builder.build("customer_workflow", name="Customer Processing")
results = workflow.execute()
```

### Conditional Workflow with Switch/Merge

```python
from kailash.workflow.builder import WorkflowBuilder

# Create workflow
builder = WorkflowBuilder()

# Add nodes
reader_id = builder.add_node("JSONReader", "reader", 
                           {"file_path": "transactions.json"})

switch_id = builder.add_node("Switch", "status_router", 
                           {"field": "status", "cases": ["completed", "pending", "failed"]})

# Add processing nodes for each case
completed_id = builder.add_node("DataTransformer", "completed_processor", 
                              {"transformations": ["lambda x: {**x, 'processed': True}"]})
pending_id = builder.add_node("DataTransformer", "pending_processor", 
                            {"transformations": ["lambda x: {**x, 'reminder_sent': True}"]})
failed_id = builder.add_node("DataTransformer", "failed_processor", 
                           {"transformations": ["lambda x: {**x, 'retry_count': x.get('retry_count', 0) + 1}"]})

# Add merge node to combine results
merge_id = builder.add_node("Merge", "result_merger", {})

# Connect nodes
builder.add_connection(reader_id, "data", switch_id, "input")
builder.add_connection(switch_id, "case_completed", completed_id, "data")
builder.add_connection(switch_id, "case_pending", pending_id, "data")
builder.add_connection(switch_id, "case_failed", failed_id, "data")

# Connect outputs to merge node
builder.add_connection(completed_id, "transformed_data", merge_id, "input1")
builder.add_connection(pending_id, "transformed_data", merge_id, "input2")
builder.add_connection(failed_id, "transformed_data", merge_id, "input3")

# Build and run
workflow = builder.build("transaction_processing")
results = workflow.execute()
```

## 5. Success Metrics

1. **Adoption Rate**: >90% of ABCs using the SDK within 3 months
2. **Handoff Efficiency**: >70% reduction in code refactoring during ABC-to-PDT transitions
3. **Prototype Speed**: >50% reduction in time from concept to working prototype
4. **Quality**: <5% of workflows requiring architectural changes after handoff

## 6. Implementation Guidelines

1. Focus on developer experience and intuitive APIs
2. Provide comprehensive documentation and examples
3. Implement robust error handling with helpful messages
4. Ensure test coverage exceeds 80%
5. Maintain compatibility with Kailash architecture