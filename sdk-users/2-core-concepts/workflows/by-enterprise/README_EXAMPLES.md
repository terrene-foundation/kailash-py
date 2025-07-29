# Enterprise Workflow Examples - Usage Guide

## Example Types

### 1. Minimal Examples (✓ Run Out of Box)
These examples demonstrate the core patterns without external dependencies:

- `financial_processor_minimal.py` - Basic CSV processing workflow
- `lead_scoring_minimal.py` - Simple lead scoring with LLM

**To run:**
```bash
python financial_processor_minimal.py
python lead_scoring_minimal.py
```

### 2. Original Examples (❌ Anti-Pattern)
These show what NOT to do - excessive PythonCodeNode usage:

- `financial_data_processor.py` - Uses 7 PythonCodeNodes (BAD)
- `lead_scoring_engine.py` - Uses 6 PythonCodeNodes (BAD)

**Purpose:** Training data showing wrong patterns

### 3. Refactored Examples (✓ Best Practice, Needs Config)
These show proper architecture but require real infrastructure:

- `financial_data_processor_refactored.py` - Uses RESTClientNode, SQLDatabaseNode, etc.
- `lead_scoring_engine_refactored.py` - Proper node usage with real integrations

**Requirements:**
- Kafka broker for streaming data
- PostgreSQL databases (transactions, compliance, analytics)
- REST APIs for webhooks and notifications
- API keys (OpenAI, notification services)

**Configuration needed:**
```bash
export KAFKA_BROKERS=localhost:9092
export TRANSACTION_DB=postgresql://user:pass@localhost/transactions
export COMPLIANCE_DB=postgresql://user:pass@localhost/compliance
export ANALYTICS_DB=postgresql://user:pass@localhost/analytics
export WEBHOOK_API=https://api.example.com
export OPENAI_API_KEY=your-key-here
```

## Key Patterns Demonstrated

### ✓ DO: Use Specialized Nodes
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Good - use existing nodes
csv_reader = CSVReaderNode(file_path="data.csv")
filter_node = FilterNode()
api_client = RESTClientNode()

```

### ❌ DON'T: Overuse PythonCodeNode
```python
# Bad - using PythonCodeNode for everything
processor = PythonCodeNode(code="""
# Reading CSV in Python
import csv
with open('data.csv') as f:
    data = list(csv.DictReader(f))
""")

```

## Running Order

1. **Start with minimal examples** - Understand the patterns
2. **Study refactored examples** - See production architecture
3. **Avoid original examples** - Only for learning what not to do

## Production Deployment

The refactored examples are production-ready architectures. To deploy:

1. Set up required infrastructure (Kafka, databases, APIs)
2. Configure environment variables
3. Adjust connection strings and endpoints
4. Add proper error handling and monitoring
5. Scale nodes as needed

Remember: The goal is to minimize PythonCodeNode usage and leverage the SDK's specialized nodes!
