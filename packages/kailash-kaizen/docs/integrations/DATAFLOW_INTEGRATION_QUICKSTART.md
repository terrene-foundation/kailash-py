# Kaizen-DataFlow Integration Quick Start

**Status**: Phase 1 Complete - Architecture Design
**Framework Independence**: ✅ Kaizen works with or without DataFlow

## Installation

```bash
# Kaizen only (no database features)
pip install kailash-kaizen

# Kaizen + DataFlow (database-enabled agents)
pip install kailash-kaizen kailash[dataflow]
```

## Quick Start

### Check Integration Availability

```python
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

if DATAFLOW_AVAILABLE:
    print("✅ DataFlow integration active")
else:
    print("⚠️  DataFlow not installed - using Kaizen only")
```

### Pattern 1: Basic Agent (No DataFlow)

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig

# Create standard Kaizen agent
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4"
)

agent = BaseAgent(config)
# Agent works perfectly without database features
```

### Pattern 2: Database-Enabled Agent

```python
from kaizen.integrations.dataflow import DataFlowAwareAgent
from kaizen.core.config import BaseAgentConfig
from dataflow import DataFlow

# Setup database
db = DataFlow("postgresql://localhost/mydb")

# Define model
@db.model
class User:
    name: str
    email: str
    active: bool = True

# Create database-enabled agent
config = BaseAgentConfig(
    llm_provider="openai",
    model="gpt-4"
)

agent = DataFlowAwareAgent(config=config, db=db)

# Agent now has database operations
users = agent.query_database(
    table='users',
    filter={'active': True},
    limit=10
)
```

### Pattern 3: Optional Database Connection

```python
from kaizen.integrations.dataflow import DataFlowAwareAgent

# Create agent without database
agent = DataFlowAwareAgent(config=config)
# Agent works normally

# Connect to database later (if needed)
if need_database:
    agent.connect_dataflow(db)
    # Now database operations available
```

### Pattern 4: Custom Agent with Database

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.integrations.dataflow import DataFlowOperationsMixin

class CustomDatabaseAgent(BaseAgent, DataFlowOperationsMixin):
    """Custom agent with database capabilities."""

    def __init__(self, config, db=None):
        super().__init__(config)
        if db is not None:
            self.connect_dataflow(db)

    def process_user_data(self):
        """Custom method using database."""
        users = self.query_database(
            table='users',
            filter={'active': True}
        )
        return self.analyze_users(users)

# Use custom agent
agent = CustomDatabaseAgent(config=config, db=db)
results = agent.process_user_data()
```

## Available Database Operations

### DataFlowOperationsMixin Methods

```python
# Query database
results = agent.query_database(
    table='users',
    filter={'age': {'$gte': 18}},
    limit=100,
    order_by=['-created_at']
)

# Insert record
user = agent.insert_record(
    table='users',
    data={'name': 'Alice', 'email': 'alice@example.com'}
)

# Update record
updated = agent.update_record(
    table='users',
    record_id=123,
    data={'email': 'newemail@example.com'}
)

# Delete record
success = agent.delete_record(table='users', record_id=123)

# Bulk insert
users = agent.bulk_insert(
    table='users',
    records=[
        {'name': 'Bob', 'email': 'bob@example.com'},
        {'name': 'Carol', 'email': 'carol@example.com'}
    ],
    batch_size=1000
)
```

### DataFlowAwareAgent Methods

```python
# Get database info
info = agent.get_database_info()
print(info['connected'])  # True/False
print(info['tables'])     # ['users', 'products', ...]

# List available tables
tables = agent.list_available_tables()

# Get table schema
schema = agent.get_table_schema('users')
print(schema['columns'])
```

## Connection Interface

### Direct Connection Usage

```python
from kaizen.integrations.dataflow import DataFlowConnection

# Create connection
connection = DataFlowConnection(db=db, lazy_init=True)

# List tables
tables = connection.list_tables()

# Get schema
schema = connection.get_table_schema('users')

# Get DataFlow nodes for table
nodes = connection.get_nodes_for_table('User')
# Returns: {'create': 'UserCreateNode', 'read': 'UserReadNode', ...}
```

## Multi-Agent Coordination

### Shared Database Pattern

```python
from kaizen.integrations.dataflow import DataFlowAwareAgent
from dataflow import DataFlow

# Setup shared database
db = DataFlow("postgresql://localhost/shared_db")

# Create multiple agents sharing database
reader_agent = DataFlowAwareAgent(
    config=BaseAgentConfig(llm_provider="openai", model="gpt-4"),
    db=db
)

writer_agent = DataFlowAwareAgent(
    config=BaseAgentConfig(llm_provider="openai", model="gpt-4"),
    db=db
)

# Both agents can coordinate via shared database
writer_agent.insert_record('tasks', {'task': 'Process data'})
tasks = reader_agent.query_database('tasks')
```

## Error Handling

### Check Connection Before Operations

```python
agent = DataFlowAwareAgent(config=config)

try:
    # This will raise RuntimeError if no connection
    results = agent.query_database('users')
except RuntimeError as e:
    print(f"No database connection: {e}")
    # Connect and retry
    agent.connect_dataflow(db)
    results = agent.query_database('users')
```

### Validate DataFlow Instance

```python
from kaizen.integrations.dataflow import DataFlowOperationsMixin

mixin = DataFlowOperationsMixin()

try:
    mixin.connect_dataflow("not a dataflow instance")
except TypeError as e:
    print(f"Invalid DataFlow instance: {e}")
```

## Architecture Notes

### Framework Independence

- Kaizen works independently without DataFlow
- DataFlow works independently without Kaizen
- Integration is OPTIONAL and activates only when both present
- No hard dependencies between frameworks

### Lazy Initialization

```python
# Connection doesn't initialize until first use
connection = DataFlowConnection(db=db, lazy_init=True)
# No overhead yet

# First operation triggers initialization
tables = connection.list_tables()
# Now initialized
```

### Clean Separation

```python
# Kaizen core - no DataFlow dependency
from kaizen.core.base_agent import BaseAgent

# Integration layer - optional
from kaizen.integrations.dataflow import DataFlowAwareAgent

# DataFlow - independent
from dataflow import DataFlow
```

## Testing

### Check Integration Status

```python
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE

def test_with_or_without_dataflow():
    if DATAFLOW_AVAILABLE:
        # Use database-enabled features
        agent = DataFlowAwareAgent(config=config, db=db)
    else:
        # Use standard features
        agent = BaseAgent(config=config)

    # Both agents support core Kaizen features
    result = agent.execute(...)
```

## Next Steps

1. **Review**: See `TODO-148-PHASE-1-COMPLETION-REPORT.md` for detailed architecture
2. **Verify**: Run `python verify_phase1_integration.py`
3. **Wait for Phase 2**: Full workflow integration (coming soon)

## Phase 2 Preview (Coming Soon)

Phase 2 will add:
- Full workflow integration with DataFlow nodes
- Memory persistence via DataFlow models
- Advanced multi-agent coordination patterns
- Complete integration test suite

## Resources

- **Completion Report**: `TODO-148-PHASE-1-COMPLETION-REPORT.md`
- **Executive Summary**: `TODO-148-PHASE-1-SUMMARY.md`
- **Verification Script**: `verify_phase1_integration.py`
- **Tests**: `tests/unit/integrations/`

## Questions?

Check DATAFLOW_AVAILABLE:
```python
from kaizen.integrations.dataflow import DATAFLOW_AVAILABLE
print(f"DataFlow integration: {DATAFLOW_AVAILABLE}")
```

---

**Status**: ✅ Phase 1 Complete
**Last Updated**: 2025-10-05
**Next Phase**: Integration Implementation
