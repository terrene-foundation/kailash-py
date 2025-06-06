# Kailash Workflow Studio Examples

This directory contains comprehensive examples and templates for the Kailash Workflow Studio visual workflow builder.

## Files

### 1. `studio_comprehensive.py` ⭐
Complete demonstration of all Studio features:
- **Standalone Database Examples**: Direct database operations (no server required)
- **API Client Examples**: REST API and WebSocket usage
- Workflow management (CRUD operations)
- Custom node creation (all types)
- Execution tracking and monitoring
- Performance analytics
- Multi-tenant support
- Template management

### 2. `studio_standalone.py`
Simplified examples using real database operations:
- Basic workflow creation and execution
- Custom node examples (Python, API, Workflow types)
- Multi-tenant isolation demonstration
- Workflow templates
- Works without running API server

### 3. `custom_node_templates.py`
Complete template library for creating custom nodes:
- **Python nodes**: Execute Python code with DataFrames
- **Workflow nodes**: Compose nodes from other workflows
- **API nodes**: Wrap external REST APIs

Each template includes:
- Complete JSON structure
- Parameter definitions
- Input/output specifications
- Implementation details

### 4. `test_custom_nodes.py`
Test suite for custom node creation:
- Creates nodes using templates
- Tests database persistence
- Validates node structure
- Simulates execution

## Quick Start

```bash
# Run comprehensive examples (no server required)
python studio_comprehensive.py

# Run standalone examples
python studio_standalone.py

# Test custom node creation
python test_custom_nodes.py
```

## Usage

### Using Templates with Studio API

```python
import httpx
from custom_node_templates import sentiment_analyzer_template

# Create custom node via API
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8000/api/custom-nodes",
        json=sentiment_analyzer_template
    )
    node = response.json()
    print(f"Created node: {node['id']}")
```

### Direct Database Usage

```python
from kailash.api.database import init_database, get_db_session, CustomNodeRepository
from custom_node_templates import data_validator_template

SessionLocal, _ = init_database()
with get_db_session(SessionLocal) as session:
    repo = CustomNodeRepository(session)
    node = repo.create("my-tenant", data_validator_template)
```

### Testing Custom Nodes

```bash
# Run the test suite
python test_custom_nodes.py

# This will:
# - Create nodes from templates
# - Test database operations
# - Validate node structure
# - Clean up test database
```

## Custom Node Types

### 1. Python Nodes
Execute Python code in a sandboxed environment:
- Access to pandas, numpy, and standard libraries
- Receive parameters and input data
- Return structured output

Example: `SentimentAnalyzer`, `DataValidator`

### 2. Workflow Nodes
Compose complex functionality from existing nodes:
- Define internal workflow structure
- Map inputs/outputs between sub-nodes
- Reuse existing node functionality

Example: `DataQualityPipeline`

### 3. API Nodes
Integrate external REST APIs:
- Configure endpoints and authentication
- Map request/response data
- Handle rate limiting and retries

Example: `GeocodingService`, `WeatherDataEnricher`

## Integration with Studio UI

These templates are designed to work with the Workflow Studio UI:

1. **Node Palette**: Templates appear as draggable nodes
2. **Property Panel**: Parameters become UI form fields
3. **Canvas**: Nodes can be connected based on input/output types
4. **Execution**: Nodes execute according to their implementation type

## Next Steps

1. Start the Studio API: `python -m kailash.api.studio`
2. Access the API docs: http://localhost:8000/docs
3. Use templates to create custom nodes
4. Build workflows using your custom nodes
