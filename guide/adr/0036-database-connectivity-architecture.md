# ADR-0036: Database Connectivity Architecture

## Status

Accepted

Date: 2025-06-06

## Context

The Kailash Python SDK currently lacks production-ready database connectivity for relational databases (SQLite, PostgreSQL, MySQL). The existing `SQLDatabaseNode` implementation is a placeholder that returns mock data, preventing users from building real data workflows.

Key requirements identified:
- **Production Database Support**: SQLite, PostgreSQL, MySQL with real SQLAlchemy implementation
- **Framework Consistency**: Input parameter validation following existing Node patterns
- **Simple API**: Clean interface without validation overhead
- **Security First**: SQL injection prevention, secure connection handling
- **Database Focus**: Let the database handle data validation, not the SDK

### Current Limitations
- `SQLDatabaseNode.run()` contains placeholder code returning simulated data
- No real database driver dependencies (SQLAlchemy, psycopg2, pymysql)
- Missing input parameter validation consistent with framework patterns
- Security vulnerabilities in connection string handling

## Decision

We will implement a clean, simple database connectivity architecture with a single-node design:

### 1. Single SQLDatabaseNode Architecture
**Design Principle**: One node = one operation for visual workflow clarity
- Single `SQLDatabaseNode` for all database operations
- Raw SQL interface only (no query building complexity)
- Users write SQL directly or use external query builders

### 2. SQLAlchemy-Based Implementation
- Replace placeholder code with real SQLAlchemy engine integration
- Support connection strings: `sqlite://`, `postgresql://`, `mysql://`
- Connection pooling and transaction management
- Parameterized queries for SQL injection prevention

### 3. Framework Input Validation
**Input Validation via `get_parameters()`:**
```python
def get_parameters(self) -> Dict[str, NodeParameter]:
    return {
        "connection_string": NodeParameter(type=str, required=False),
        "query": NodeParameter(type=str, required=False),
        "parameters": NodeParameter(type=list, default=[]),
        "result_format": NodeParameter(type=str, default="dict"),
        "timeout": NodeParameter(type=int, default=30)
    }
```

**Simple Output Structure:**
```python
# No get_output_schema() needed - database validates its own structure
def run(self, **kwargs) -> Dict[str, Any]:
    return {
        "data": query_results,           # List of results in specified format
        "row_count": affected_rows,      # Number of rows returned/affected
        "columns": column_names,         # Column names from query
        "execution_time": time_seconds   # Query execution time
    }
```

### 4. Security Implementation
- Secure connection string handling (mask passwords in logs)
- SQL injection prevention via parameterized queries only
- Input sanitization for dynamic table/column names
- Connection timeout and retry logic

### 5. Database Driver Dependencies
Add to `pyproject.toml`:
- `sqlalchemy>=2.0.0` - Core SQLAlchemy ORM
- `psycopg2-binary>=2.9.0` - PostgreSQL driver
- `pymysql>=1.1.0` - MySQL driver
- `aiosqlite>=0.19.0` - Async SQLite support

## Rationale

### Why SQLAlchemy Over Alternatives
- **Industry Standard**: Most widely used Python database ORM
- **Multi-Database Support**: Unified interface for all target databases
- **Connection Pooling**: Built-in production-ready features
- **Security**: Parameterized queries and SQL injection prevention
- **Performance**: Optimized for production workloads

### Why Single-Node Architecture
- **Visual Workflow Clarity**: One node = one operation principle for drag-and-drop interfaces
- **Framework Consistency**: Input validation follows exact same patterns as all other SDK nodes
- **Database Responsibility**: Database engines already validate data structure and types
- **Reduced Complexity**: No unnecessary validation overhead for users
- **Performance**: Direct database connectivity without intermediate validation layers
- **Simplicity**: Clean, minimal API focused on essential database operations
- **User Control**: Users choose their own query building tools or write raw SQL

## Consequences

### Positive
- **Production Ready**: Real database connectivity with SQLAlchemy
- **Framework Consistent**: Follows exact same input validation patterns as other nodes
- **Security First**: SQL injection prevention and secure connection handling
- **User Friendly**: Clean, simple API with minimal configuration
- **Performance**: No validation overhead, direct database operations
- **Multi-Database**: SQLite, PostgreSQL, MySQL support with unified interface
- **Maintainable**: Simple codebase without complex validation logic
- **Visual Workflow Clarity**: Single node design reduces confusion in drag-and-drop interfaces

### Negative
- **Dependency Growth**: Additional database driver dependencies
- **Database Dependency**: Users must ensure their database schema is correct
- **Raw SQL Requirement**: Users must write SQL directly or use external query builders

### Neutral
- **Breaking Changes**: None - current placeholder will be replaced
- **Migration Path**: Existing mock queries will need real database connections

## Implementation Details

### 1. Core Implementation Structure
```python
# Real SQLAlchemy implementation
from sqlalchemy import create_engine, text
import time

def run(self, **kwargs) -> Dict[str, Any]:
    # Framework-validated inputs
    connection_string = kwargs.get("connection_string")  # Guaranteed str or None
    query = kwargs.get("query")  # Guaranteed str or None
    parameters = kwargs.get("parameters", [])  # Guaranteed list
    result_format = kwargs.get("result_format", "dict")  # Guaranteed str
    timeout = kwargs.get("timeout", 30)  # Guaranteed int
    
    # Create engine and execute
    start_time = time.time()
    engine = create_engine(
        connection_string,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_timeout=timeout
    )
    
    with engine.connect() as conn:
        with conn.begin():  # Transaction management
            result = conn.execute(text(query), parameters)
            formatted_data = self.format_results(result, result_format)
            execution_time = time.time() - start_time
    
    return {
        "data": formatted_data,
        "row_count": len(formatted_data) if isinstance(formatted_data, list) else result.rowcount,
        "columns": list(result.keys()) if result.keys() else [],
        "execution_time": execution_time
    }
```

### 2. Usage Examples
```python
# Simple query
db_node.execute(
    connection_string="sqlite:///data.db",
    query="SELECT * FROM customers"
)

# Production query with parameters
db_node.execute(
    connection_string="postgresql://user:pass@host/db",
    query="SELECT id, name, age FROM customers WHERE active = ?",
    parameters=[True],
    result_format="dict",
    timeout=30
)
```

## Implementation Tasks

### High Priority (Core Implementation)
1. ✅ **DB-002**: Add SQLAlchemy dependencies to pyproject.toml
2. 🚧 **DB-003**: Replace placeholder with real SQLAlchemy implementation
3. ✅ **DB-004**: Implement input validation with clean parameters in get_parameters()
4. **DB-010**: Implement security features (connection masking, SQL injection prevention)

### Medium Priority (Enhanced Features)
5. **DB-009**: Add advanced connection pooling and transaction management
6. **DB-007**: Write comprehensive integration tests

### Documentation & Testing
7. ✅ **DB-006**: Create user-friendly examples for database connectivity
8. ✅ **DB-008**: Update API registry and node catalog

## Alternatives Considered

### Alternative ORMs
- **Peewee**: Lighter weight but less feature-complete than SQLAlchemy
- **Django ORM**: Too heavyweight and Django-specific
- **Raw Database Drivers**: No abstraction, would require separate implementations

### API Design Approaches
- **Complex Validation**: Additional schema validation layers (rejected - adds overhead)
- **Multiple Nodes**: Separate nodes for different database operations (rejected - too granular)
- **Configuration Classes**: Require users to define database config classes like `DatabaseConfig(connection_string="...", query="...")` instead of simple parameters (rejected - adds boilerplate, not consistent with other SDK nodes)
- **Dual Interface Design**: Single node with both raw SQL and query builder interfaces (rejected - adds complexity, confusing for visual workflows)
- **Query Builder Node**: Separate SQLQueryBuilderNode for dynamic query construction (rejected - violates single-purpose principle, confusing in visual workflows)

## Related ADRs

- [ADR-0003: Base Node Interface](0003-base-node-interface.md) - Node validation patterns
- [ADR-0032: Production Security Architecture](0032-production-security-architecture.md) - Security requirements
- [ADR-0015: API Integration Architecture](0015-api-integration-architecture.md) - Similar validation patterns

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [MySQL Documentation](https://dev.mysql.com/doc/)
- [Python Type Hints PEP 484](https://peps.python.org/pep-0484/)
- [SQL Injection Prevention Guide](https://owasp.org/www-community/attacks/SQL_Injection)