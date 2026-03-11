# AI Query Optimization Example

Demonstrates AI-enhanced database operations with Kaizen + DataFlow integration.

## Features

This example showcases:

1. **Natural Language to SQL** - Convert plain English queries to DataFlow operations
2. **Query Optimization** - AI-driven query analysis and optimization suggestions
3. **Intelligent Data Access** - Semantic understanding of database queries

## Prerequisites

```bash
# Install DataFlow
pip install kailash[dataflow]

# Or install separately
pip install kailash-dataflow
```

## Usage

```bash
# Run the demo
python workflow.py
```

## Example Queries

The demo shows how to execute natural language queries:

```python
from kaizen.integrations.dataflow import NLToSQLAgent
from dataflow import DataFlow

# Setup database
db = DataFlow("sqlite:///demo.db")

@db.model
class Product:
    name: str
    inventory: int
    demand_score: float

# Create agent
agent = NLToSQLAgent(config=config, db=db)

# Natural language query
result = agent.query("Show me products with less than 10 items in stock")

print(result['explanation'])  # AI explanation of query
print(result['results'])      # Actual database results
```

## What You'll See

1. **Database Setup** - Automatic table creation and sample data insertion
2. **NL Query Execution** - Three example queries demonstrating different patterns:
   - Inventory filters ("less than 10 items")
   - Category + attribute filters ("electronics with high demand")
   - Simple category queries ("all furniture items")
3. **Query Optimization** - Analysis of query structure with suggestions

## Sample Output

```
============================================================
AI-Enhanced Natural Language Query Demo
============================================================

1. Setting up database...
✓ Sample data inserted

2. Creating NL to SQL agent...
3. Ready for natural language queries!

Query 1: 'Show me products with less than 10 items in stock'
------------------------------------------------------------
📝 Explanation: Filtering products where inventory < 10
🔍 Filter: {'inventory': {'$lt': 10}}
📊 Results: 3 items found
  - Laptop Pro 15
    Category: Electronics, Inventory: 5, Demand: 0.9
  - USB-C Cable
    Category: Electronics, Inventory: 8, Demand: 0.95
  - Ergonomic Chair
    Category: Furniture, Inventory: 3, Demand: 0.85
```

## How It Works

### 1. Natural Language Processing

The `NLToSQLAgent` uses an LLM to:
- Parse natural language query intent
- Identify target tables from context
- Generate MongoDB-style filters for DataFlow
- Explain the query interpretation

### 2. DataFlow Integration

DataFlow provides:
- Automatic model-to-node generation (@db.model)
- MongoDB-style query interface
- Type-safe database operations

### 3. AI-Enhanced Operations

The integration combines:
- LLM intelligence for query understanding
- DataFlow's database abstraction
- Signature-based programming from Kaizen

## Configuration

Customize the agent behavior:

```python
@dataclass
class QueryConfig:
    llm_provider: str = "openai"     # or "anthropic"
    model: str = "gpt-4"             # LLM model
    temperature: float = 0.2         # Low for precise queries
    max_tokens: int = 1000
```

## Related Examples

- **Basic DataFlow** - See Phase 1 integration examples
- **Multi-Agent Coordination** - Combine NL agents with data processing agents
- **Enterprise Workflows** - Use in production data pipelines

## Architecture

```
User Query (Natural Language)
       ↓
NLToSQLAgent (Kaizen)
  - LLM analysis via signature
  - Query interpretation
       ↓
DataFlow (Database Layer)
  - MongoDB-style filters
  - Generated CRUD nodes
       ↓
Database (PostgreSQL/SQLite)
  - Actual SQL execution
       ↓
Results (Structured Data)
```

## Next Steps

1. Try custom queries with your own data
2. Integrate with multi-agent workflows
3. Add data transformation with `DataTransformAgent`
4. Enable quality assessment with `DataQualityAgent`
5. Implement semantic search with `SemanticSearchAgent`

## License

Part of the Kailash Kaizen framework.
