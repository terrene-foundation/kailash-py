# Async Database & ABAC Patterns

**Session 065**: Enterprise async database operations and attribute-based access control

## 🚨 Critical Rules for Async Database Nodes

1. **Return Dict from get_parameters()**: Not a list
2. **Implement run() method**: For synchronous compatibility
3. **Convert DB types**: Decimal → float, datetime → isostring
4. **Separate SQL commands**: asyncpg doesn't support multiple commands
5. **Use proper connection pooling**: AsyncConnectionManager singleton pattern

## 📊 Node Quick Reference

| Task | Node | Key Features |
|------|------|--------------|
| Async SQL queries | `AsyncSQLDatabaseNode` | PostgreSQL, MySQL, SQLite with pooling |
| Vector similarity | `AsyncPostgreSQLVectorNode` | pgvector HNSW/IVFFlat indexes |
| Access control | `AccessControlManager` | Unified RBAC/ABAC/Hybrid |
| Connection pooling | `AsyncConnectionManager` | Per-tenant isolation, health monitoring |

## ⚡ Quick Patterns

### 1. Basic Async Database Query

```python
from kailash.nodes.data import AsyncSQLDatabaseNode

# Create node
db_node = AsyncSQLDatabaseNode(
    name="fetch_portfolios",
    database_type="postgresql",
    host="localhost",
    port=5432,
    database="investment_db",
    user="postgres",
    password="postgres",
    query="""
    SELECT portfolio_id, client_name, total_value
    FROM portfolios
    WHERE risk_profile = $1
    ORDER BY total_value DESC
    """,
    fetch_mode="all",
    pool_size=20,
    max_pool_size=50
)

# Execute with parameters
result = await db_node.execute_async(params=["Conservative"])
portfolios = result["result"]["data"]
```

### 2. Vector Similarity Search

```python
from kailash.nodes.data import AsyncPostgreSQLVectorNode

# Create vector search node
search_node = AsyncPostgreSQLVectorNode(
    name="semantic_search",
    connection_string="postgresql://user:pass@localhost:5432/vector_db",
    table_name="document_embeddings",
    operation="search",
    vector=[0.1, 0.2, ...],  # Query embedding (1536 dimensions)
    distance_metric="cosine",
    limit=10,
    metadata_filter="metadata->>'category' = 'financial'"
)

# Execute search
result = await search_node.execute_async()
matches = result["result"]["matches"]
for match in matches:
    print(f"Distance: {match['distance']:.3f}")
    print(f"Content: {match['metadata']['content']}")
```

### 3. ABAC Access Control

```python
from kailash.access_control_abac import (
    AccessControlManager,
    AttributeCondition,
    AttributeOperator
)
from kailash.access_control import UserContext, NodePermission

# Create access control manager
acm = AccessControlManager(strategy="abac")

# Create user context
user = UserContext(
    user_id="analyst_001",
    tenant_id="financial_corp",
    email="analyst@corp.com",
    roles=["analyst", "portfolio_viewer"],
    attributes={
        "department": "investment.analytics",
        "clearance": "confidential",
        "region": "us_east",
        "access_level": 5
    }
)

# Check access with complex conditions
decision = acm.check_node_access(
    user=user,
    resource_id="sensitive_portfolios",
    permission=NodePermission.EXECUTE
)

if decision.allowed:
    print("✅ Access granted")
else:
    print(f"❌ Access denied: {decision.reason}")
```

### 4. Data Masking Based on Attributes

```python
# Define masking rules
masking_rules = {
    "ssn": {
        "condition": {
            "attribute_path": "user.attributes.clearance",
            "operator": "security_level_below",
            "value": "secret"
        },
        "mask_type": "partial",
        "visible_chars": 4
    },
    "account_balance": {
        "condition": {
            "attribute_path": "user.attributes.access_level",
            "operator": "less_than",
            "value": 7
        },
        "mask_type": "range",
        "ranges": ["< $1M", "$1M-$10M", "$10M-$50M", "> $50M"]
    }
}

# Apply masking
masked_data = acm.mask_data(
    data={"ssn": "123-45-6789", "account_balance": 5000000},
    masking_rules=masking_rules,
    user=user
)
print(masked_data)  # {"ssn": "12*****89", "account_balance": "$1M-$10M"}
```

## 🏗️ Complete Workflow Example

```python
from kailash.workflow import Workflow
from kailash.nodes.data import AsyncSQLDatabaseNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.async_local import AsyncLocalRuntime

async def create_portfolio_analysis():
    """Create async portfolio analysis workflow."""
    workflow = Workflow(workflow_id="portfolio_analysis")

    # 1. Fetch portfolio data
    workflow.add_node(
        "fetch_portfolios",
        AsyncSQLDatabaseNode(
            name="fetch_portfolios",
            database_type="postgresql",
            host="localhost",
            database="investment_db",
            query="""
            WITH latest_prices AS (
                SELECT DISTINCT ON (symbol) symbol, close_price
                FROM market_prices
                ORDER BY symbol, price_date DESC
            )
            SELECT
                p.portfolio_id,
                p.client_name,
                SUM(pos.quantity * lp.close_price) as current_value
            FROM portfolios p
            JOIN positions pos ON p.portfolio_id = pos.portfolio_id
            JOIN latest_prices lp ON pos.symbol = lp.symbol
            GROUP BY p.portfolio_id, p.client_name
            ORDER BY current_value DESC
            """,
            fetch_mode="all"
        )
    )

    # 2. Calculate portfolio metrics
    def calculate_metrics(portfolio_data):
        """Calculate portfolio performance metrics."""
        portfolios = portfolio_data["data"]

        metrics = {
            "total_portfolios": len(portfolios),
            "total_aum": sum(p["current_value"] for p in portfolios),
            "top_portfolio": max(portfolios, key=lambda x: x["current_value"]),
            "avg_portfolio_value": sum(p["current_value"] for p in portfolios) / len(portfolios)
        }

        return {"result": metrics}

    workflow.add_node(
        "calculate_metrics",
        PythonCodeNode.from_function(
            name="calculate_metrics",
            func=calculate_metrics
        )
    )

    # Connect nodes
    workflow.connect("fetch_portfolios", "calculate_metrics", {"result": "portfolio_data"})

    return workflow

# Execute workflow
async def main():
    workflow = await create_portfolio_analysis()
    runtime = AsyncLocalRuntime()

    result, run_id = await runtime.execute(workflow)
    metrics = result["calculate_metrics"]["result"]

    print(f"Total AUM: ${metrics['total_aum']:,.2f}")
    print(f"Top Portfolio: {metrics['top_portfolio']['client_name']}")
    print(f"Average Value: ${metrics['avg_portfolio_value']:,.2f}")

# Run the workflow
import asyncio
asyncio.run(main())
```

## 🔒 ABAC Operators Reference

### Basic Operators
- `equals`, `not_equals` - Exact matching
- `contains`, `not_contains` - Substring/list membership
- `in`, `not_in` - List membership
- `contains_any` - Any item in list matches

### Numeric Operators
- `greater_than`, `less_than` - Numeric comparison
- `greater_or_equal`, `less_or_equal` - Inclusive comparison
- `between` - Range checking (inclusive)

### Advanced Operators
- `matches` - Regex pattern matching
- `hierarchical_match` - Department tree matching ("eng" matches "eng.backend")
- `security_level_meets` - Clearance level comparison
- `security_level_below` - Below clearance threshold
- `matches_data_region` - Regional access control

### Security Clearance Levels
```python
clearance_hierarchy = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "secret": 3,
    "top_secret": 4
}
```

## ⚠️ Common Pitfalls & Fixes

### 1. Abstract Method Implementation
```python
# ❌ Wrong - missing required methods
class MyAsyncNode(AsyncNode):
    def define_parameters(self):  # Wrong method name
        return [...]  # Wrong return type

# ✅ Correct - implement all abstract methods
class MyAsyncNode(AsyncNode):
    def get_parameters(self) -> dict[str, NodeParameter]:
        params = [...]
        return {param.name: param for param in params}

    def run(self, **inputs) -> dict[str, Any]:
        import asyncio
        return asyncio.run(self.execute_async(**inputs))
```

### 2. Database Type Conversion
```python
# ❌ Wrong - PostgreSQL types not JSON serializable
async def async_run(self, **inputs):
    rows = await connection.fetch(query)
    return {"result": {"data": rows}}  # Decimal/datetime objects fail

# ✅ Correct - convert to JSON-safe types
async def async_run(self, **inputs):
    rows = await connection.fetch(query)
    converted_rows = [self._convert_row(dict(row)) for row in rows]
    return {"result": {"data": converted_rows}}

def _convert_row(self, row: dict) -> dict:
    converted = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            converted[key] = float(value)
        elif isinstance(value, datetime):
            converted[key] = value.isoformat()
        else:
            converted[key] = value
    return converted
```

### 3. SQL Command Separation
```python
# ❌ Wrong - multiple commands in one query
query = """
DROP TABLE IF EXISTS test;
CREATE TABLE test (id INT);
INSERT INTO test VALUES (1);
"""
await node.execute_async(query=query)  # PostgresSyntaxError

# ✅ Correct - separate command execution
commands = [
    "DROP TABLE IF EXISTS test",
    "CREATE TABLE test (id INT)",
    "INSERT INTO test VALUES (1)"
]

for cmd in commands:
    setup_node = AsyncSQLDatabaseNode(name="setup", query=cmd, **db_config)
    await setup_node.execute_async()
```

## 🔧 Connection Pool Configuration

```python
# Production pool settings
DB_CONFIG = {
    "database_type": "postgresql",
    "host": "db.company.com",
    "port": 5432,
    "database": "production_db",
    "user": "app_user",
    "password": "secure_password",

    # Pool configuration
    "pool_size": 50,           # Normal connections
    "max_pool_size": 100,      # Peak load connections
    "pool_timeout": 30,        # Connection wait timeout
    "pool_recycle": 3600,      # Recycle connections after 1 hour

    # Performance tuning
    "fetch_mode": "all",       # vs "one" for single row
    "timeout": 30,             # Query timeout
    "retry_attempts": 3,       # Connection retry logic
}
```

## 📈 Performance Best Practices

1. **Use Connection Pooling**: Always configure appropriate pool sizes
2. **Optimize Queries**: Use CTEs, proper indexes, LIMIT clauses
3. **Batch Operations**: Group related queries into single transactions
4. **Monitor Metrics**: Track connection pool usage and query performance
5. **Handle Timeouts**: Set appropriate query and connection timeouts
6. **Test Concurrency**: Validate with realistic concurrent load

## 🎯 Use Cases

### High-Concurrency Applications
- **Portfolio analysis** with 100+ concurrent users
- **Real-time risk calculations** with frequent database updates
- **Document processing** with parallel embedding generation
- **Multi-tenant applications** with isolated connection pools

### Security-Critical Applications
- **Financial data access** with hierarchical permissions
- **Healthcare records** with attribute-based data masking
- **Compliance reporting** with audit trails and access controls
- **Government systems** with security clearance validation

### AI/ML Workflows
- **Vector similarity search** for document retrieval
- **Semantic search** with metadata filtering
- **Recommendation systems** with real-time embedding lookups
- **RAG pipelines** with efficient vector operations

## 📚 Related Documentation

- **[03-common-patterns.md](03-common-patterns.md)** - General data processing patterns
- **[07-troubleshooting.md](07-troubleshooting.md)** - Error resolution
- **[/examples/feature_examples/integrations/tpc_migration/](../../examples/feature_examples/integrations/tpc_migration/)** - Working examples
- **[/shared/mistakes/079-session-065-async-database-abac-implementation.md](../../shared/mistakes/079-session-065-async-database-abac-implementation.md)** - Common mistakes and fixes

---

*Session 065 patterns - Ready for high-concurrency enterprise applications*
