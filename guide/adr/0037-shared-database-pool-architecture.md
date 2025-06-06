# ADR-0037: Shared Database Pool Architecture

## Status
**PROPOSED** - 2025-01-06

## Context

The current SQLDatabaseNode implementation creates a new SQLAlchemy engine for every workflow execution, leading to connection proliferation and potential database connection exhaustion. This approach is fundamentally incompatible with production database systems that have connection limits, particularly cloud databases like AWS RDS.

### Current Problems

1. **Connection Explosion**: Each workflow execution creates a new engine with its own connection pool
   ```python
   # Current problematic behavior
   100 concurrent workflows × 5 connections per pool = 500 database connections
   ```

2. **RDS Connection Limits**: Cloud databases have strict connection limits
   - AWS RDS t3.micro: 90 connections
   - AWS RDS t3.small: 180 connections  
   - Connection exhaustion causes application failures

3. **Resource Waste**: Multiple engines to the same database waste memory and network resources

4. **Configuration Conflicts**: Node-level pool configuration creates conflicts when multiple workflows use different settings for the same database

5. **Idle Connection Accumulation**: Engines persist beyond workflow completion, leading to idle connections that eventually hit database timeouts

### Requirements

1. **Connection Pool Sharing**: Multiple workflows should share connection pools to the same database
2. **Predictable Connection Usage**: Total connections should be bounded and configurable
3. **Project-Level Configuration**: Database connection settings should be managed at the project level
4. **Simple Node Interface**: Nodes should not expose complex connection pool parameters
5. **Production Ready**: Must handle high-concurrency scenarios without connection exhaustion

## Decision

We will implement a **Shared Database Pool Architecture** with the following key components:

### 1. Shared Connection Pool Strategy

Implement a global connection pool strategy where all SQLDatabaseNode instances sharing the same database configuration use a single, shared SQLAlchemy engine and connection pool.

```python
class SQLDatabaseNode(Node):
    # Class-level shared pools
    _shared_pools = {}  # {(connection_string, config_hash): engine}
    _pool_lock = threading.Lock()
    
    def _get_shared_engine(self, connection_string: str, config: dict):
        """Get or create shared engine for database connection."""
        cache_key = (connection_string, frozenset(config.items()))
        
        with self._pool_lock:
            if cache_key not in self._shared_pools:
                engine = create_engine(connection_string, **config)
                self._shared_pools[cache_key] = engine
                
            return self._shared_pools[cache_key]
```

### 2. Project-Level Database Configuration

Move database connection configuration from individual nodes to project-level configuration files, eliminating configuration conflicts and providing centralized management.

```yaml
# kailash_project.yaml
name: "Customer Analytics Platform"
version: "1.0.0"

databases:
  customer_db:
    url: "${CUSTOMER_DB_URL}"
    pool_size: 20
    max_overflow: 30
    pool_timeout: 60
    pool_recycle: 3600
    pool_pre_ping: true
    
  analytics_db:
    url: "${ANALYTICS_DB_URL}"
    pool_size: 50
    max_overflow: 100
    pool_timeout: 120
    pool_recycle: 3600
    
  default:
    pool_size: 10
    max_overflow: 20
    pool_timeout: 60
    pool_recycle: 3600
    pool_pre_ping: true
```

### 3. Simplified Node Interface

Remove complex database configuration from node parameters, allowing users to focus on business logic rather than infrastructure concerns.

```python
class SQLDatabaseNode(Node):
    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "connection": NodeParameter(
                name="connection",
                type=str,
                required=True,
                description="Database connection name from project configuration"
            ),
            "query": NodeParameter(
                name="query", 
                type=str,
                required=True,
                description="SQL query to execute"
            ),
            "parameters": NodeParameter(
                name="parameters",
                type=list,
                required=False,
                default=[],
                description="Query parameters for parameterized queries"
            )
            # No db_config, pool_strategy, or other infrastructure parameters
        }
```

## Implementation Details

### Database Configuration Resolution

```python
class DatabaseConfigManager:
    """Manages database configurations from project settings."""
    
    def __init__(self, project_config_path: str):
        self.config = self._load_project_config(project_config_path)
    
    def get_database_config(self, connection_name: str) -> tuple[str, dict]:
        """Get database configuration by connection name."""
        databases = self.config.get('databases', {})
        
        if connection_name in databases:
            db_config = databases[connection_name].copy()
            connection_string = db_config.pop('url')
            return connection_string, db_config
        
        # Fall back to default configuration
        if 'default' in databases:
            default_config = databases['default'].copy()
            if 'url' in default_config:
                connection_string = default_config.pop('url')
                return connection_string, default_config
        
        # Ultimate fallback
        raise NodeExecutionError(f"Database connection '{connection_name}' not found in project configuration")
```

### Enhanced SQLDatabaseNode Implementation

```python
class SQLDatabaseNode(Node):
    """Enhanced SQL database node with shared connection pools."""
    
    # Class-level shared resources
    _shared_pools = {}
    _pool_metrics = {}
    _pool_lock = threading.Lock()
    _config_manager = None
    
    @classmethod
    def initialize(cls, project_config_path: str):
        """Initialize shared resources with project configuration."""
        cls._config_manager = DatabaseConfigManager(project_config_path)
    
    def _get_shared_engine(self, connection_string: str, config: dict):
        """Get or create shared engine for database connection."""
        cache_key = (connection_string, frozenset(config.items()))
        
        with self._pool_lock:
            if cache_key not in self._shared_pools:
                self.logger.info(f"Creating shared pool for {self._mask_connection_string(connection_string)}")
                
                # Apply sensible defaults
                pool_config = {
                    "poolclass": QueuePool,
                    "pool_size": config.get("pool_size", 10),
                    "max_overflow": config.get("max_overflow", 20),
                    "pool_timeout": config.get("pool_timeout", 60),
                    "pool_recycle": config.get("pool_recycle", 3600),
                    "pool_pre_ping": config.get("pool_pre_ping", True),
                }
                
                # Add any additional config
                for key, value in config.items():
                    if key not in pool_config:
                        pool_config[key] = value
                
                engine = create_engine(connection_string, **pool_config)
                
                self._shared_pools[cache_key] = engine
                self._pool_metrics[cache_key] = {
                    'created_at': datetime.now(),
                    'total_queries': 0
                }
            
            return self._shared_pools[cache_key]
    
    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute SQL query using shared connection pool."""
        connection_name = kwargs.get("connection")
        query = kwargs.get("query")
        parameters = kwargs.get("parameters", [])
        
        if not connection_name:
            raise NodeExecutionError("connection parameter is required")
        if not query:
            raise NodeExecutionError("query parameter is required")
        
        # Get database configuration
        if not self._config_manager:
            raise NodeExecutionError("SQLDatabaseNode not initialized. Call initialize() first.")
        
        connection_string, db_config = self._config_manager.get_database_config(connection_name)
        
        # Get shared engine
        engine = self._get_shared_engine(connection_string, db_config)
        
        # Track metrics
        cache_key = (connection_string, frozenset(db_config.items()))
        with self._pool_lock:
            self._pool_metrics[cache_key]['total_queries'] += 1
        
        # Execute query with shared connection pool
        start_time = time.time()
        
        try:
            with engine.connect() as conn:
                with conn.begin() as trans:
                    try:
                        # Handle parameterized queries
                        if parameters and isinstance(parameters, list):
                            param_dict = {}
                            modified_query = query
                            for i, param in enumerate(parameters):
                                param_name = f"param{i}"
                                param_dict[param_name] = param
                                modified_query = modified_query.replace("?", f":{param_name}", 1)
                            result = conn.execute(text(modified_query), param_dict)
                        elif parameters and isinstance(parameters, dict):
                            result = conn.execute(text(query), parameters)
                        else:
                            result = conn.execute(text(query))
                        
                        execution_time = time.time() - start_time
                        
                        # Process results
                        if result.returns_rows:
                            rows = result.fetchall()
                            columns = list(result.keys()) if result.keys() else []
                            row_count = len(rows)
                            formatted_data = [dict(row._mapping) for row in rows]
                        else:
                            formatted_data = []
                            columns = []
                            row_count = result.rowcount if result.rowcount != -1 else 0
                        
                        trans.commit()
                        
                    except Exception as e:
                        trans.rollback()
                        raise
                        
        except SQLAlchemyError as e:
            execution_time = time.time() - start_time
            sanitized_error = self._sanitize_error_message(str(e))
            raise NodeExecutionError(f"Database error: {sanitized_error}") from e
        
        self.logger.info(f"Query executed in {execution_time:.3f}s, {row_count} rows affected/returned")
        
        return {
            "data": formatted_data,
            "row_count": row_count,
            "columns": columns,
            "execution_time": execution_time
        }
    
    @classmethod
    def get_pool_status(cls) -> Dict[str, Any]:
        """Get status of all shared connection pools."""
        with cls._pool_lock:
            status = {}
            for key, engine in cls._shared_pools.items():
                pool = engine.pool
                connection_string = key[0]
                masked_string = cls._mask_connection_string(connection_string)
                
                status[masked_string] = {
                    'pool_size': pool.size(),
                    'checked_out': pool.checkedout(),
                    'overflow': pool.overflow(),
                    'total_capacity': pool.size() + pool.overflow(),
                    'utilization': pool.checkedout() / (pool.size() + pool.overflow()) if (pool.size() + pool.overflow()) > 0 else 0,
                    'metrics': cls._pool_metrics.get(key, {})
                }
            
            return status
    
    @classmethod
    def cleanup_pools(cls):
        """Clean up all shared connection pools."""
        with cls._pool_lock:
            for engine in cls._shared_pools.values():
                engine.dispose()
            cls._shared_pools.clear()
            cls._pool_metrics.clear()
```

## Recommended Configuration Guidelines

### By Traffic Volume

**Low Traffic (< 50 requests/minute)**
```yaml
databases:
  app_db:
    url: "${DATABASE_URL}"
    pool_size: 5
    max_overflow: 5
    pool_timeout: 30
    pool_recycle: 3600
```

**Medium Traffic (50-500 requests/minute)**
```yaml
databases:
  app_db:
    url: "${DATABASE_URL}"
    pool_size: 20
    max_overflow: 30
    pool_timeout: 60
    pool_recycle: 3600
```

**High Traffic (> 500 requests/minute)**
```yaml
databases:
  app_db:
    url: "${DATABASE_URL}"
    pool_size: 50
    max_overflow: 100
    pool_timeout: 120
    pool_recycle: 3600
```

### By Database Instance Size

**Small RDS (t3.micro/small - 90-180 connections)**
```yaml
databases:
  prod_db:
    url: "${DATABASE_URL}"
    pool_size: 15
    max_overflow: 25
    pool_timeout: 60
    pool_recycle: 3600
    # Conservative: use ~40 total connections max
```

**Medium RDS (t3.medium/large - 300-500+ connections)**
```yaml
databases:
  prod_db:
    url: "${DATABASE_URL}"
    pool_size: 50
    max_overflow: 80
    pool_timeout: 90
    pool_recycle: 3600
    # Can use ~130 total connections
```

### Environment-Specific Configuration

```yaml
# Development
databases:
  app_db:
    url: "postgresql://localhost/dev_db"
    pool_size: 2
    max_overflow: 3
    pool_timeout: 30
    pool_recycle: 300

# Production  
databases:
  app_db:
    url: "${PROD_DATABASE_URL}"
    pool_size: 30
    max_overflow: 50
    pool_timeout: 90
    pool_recycle: 3600
    pool_pre_ping: true
    connect_args:
      connect_timeout: 10
      statement_timeout: 60000
```

## Benefits

### 1. **Predictable Connection Usage**
```python
# Before: Unpredictable connection explosion
100 workflows × 5 connections = 500 connections

# After: Bounded, shared pools
All workflows share 20-50 total connections
```

### 2. **Simplified User Experience**
```python
# Before: Complex configuration
SQLDatabaseNode(
    connection_string="postgresql://...",
    db_config={"pool_size": 20, "max_overflow": 30, ...}
)

# After: Simple reference
SQLDatabaseNode(
    connection="customer_db",
    query="SELECT * FROM customers"
)
```

### 3. **Centralized Configuration Management**
- Single source of truth for database settings
- Environment-specific configurations
- DevOps control over infrastructure parameters
- No configuration conflicts between workflows

### 4. **Production Ready**
- Prevents connection exhaustion
- Efficient resource utilization
- Monitoring and observability
- Graceful degradation under load

## Risks and Mitigations

### Risk 1: Shared Pool Contention
**Risk**: Multiple workflows competing for the same connection pool could cause queuing delays.

**Mitigation**: 
- Proper pool sizing based on workload analysis
- Monitoring and alerting on pool utilization
- Configure appropriate timeouts

### Risk 2: Pool Resource Leaks
**Risk**: Shared pools might accumulate connections over time.

**Mitigation**:
- Automatic connection recycling (`pool_recycle`)
- Health checks (`pool_pre_ping`)
- Explicit cleanup methods for testing/shutdown

### Risk 3: Configuration Complexity
**Risk**: Project-level configuration might be complex for simple cases.

**Mitigation**:
- Sensible defaults that work for most scenarios
- Clear documentation and examples
- Fallback to default configuration

## Success Metrics

1. **Connection Usage**: Total database connections should be bounded and predictable
2. **Performance**: No degradation in query execution times
3. **Reliability**: Elimination of connection exhaustion errors
4. **Usability**: Simplified node configuration

## Implementation

See TODO-037: Shared Database Pool Implementation for detailed implementation plan and tasks.

---

**Decision Date**: 2025-01-06  
**Next Review**: 2025-04-06 (3 months after implementation)  
**Status**: PROPOSED - Pending implementation and testing