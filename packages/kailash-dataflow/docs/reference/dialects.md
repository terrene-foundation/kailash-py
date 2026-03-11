# DataFlow Database Dialects Reference

Reference guide for database-specific features and configurations in DataFlow.

## Supported Databases

DataFlow supports multiple database dialects with optimized configurations for each:

- **PostgreSQL** (9.6+)
- **MySQL** (5.7+, 8.0+)
- **SQLite** (3.25+)
- **MongoDB** (4.0+)
- **Redis** (5.0+)

## PostgreSQL

### Configuration

```python
from kailash_dataflow import DataFlow, DataFlowConfig

config = DataFlowConfig(
    database_url="postgresql://user:pass@localhost:5434/myapp",
    dialect="postgresql",
    pool_size=20,
    pool_max_overflow=30,
    pool_recycle=3600,
    pool_pre_ping=True,
    statement_cache_size=1200,
    server_side_cursors=True
)

db = DataFlow(config=config)
```

### PostgreSQL-Specific Features

#### JSON/JSONB Support

```python
@db.model
class Event:
    id: int
    name: str
    metadata: dict  # Stored as JSONB
    tags: list      # Stored as JSONB array

    __dataflow__ = {
        'indexes': [
            {'fields': ['metadata'], 'type': 'gin'},  # GIN index for JSONB
            {'fields': ['tags'], 'type': 'gin'}
        ]
    }

# Query JSONB fields
workflow.add_node("EventListNode", "search_events", {
    "filter": {
        "metadata->category": "analytics",
        "metadata->>status": "active",  # ->> for text extraction
        "tags": {"@>": ["important", "urgent"]}  # Array contains
    }
})
```

#### Array Operations

```python
# PostgreSQL arrays
workflow.add_node("ProductUpdateNode", "add_tags", {
    "id": product_id,
    "data": {
        "tags": {"$push": ["new-tag", "featured"]},  # Array append
        "categories": {"$pull": "deprecated"}        # Array remove
    }
})

# Array queries
workflow.add_node("ProductListNode", "find_by_tags", {
    "filter": {
        "tags": {"&&": ["electronics", "sale"]},  # Array overlap
        "categories": {"@>": ["computers"]}       # Array contains
    }
})
```

#### Full-Text Search

```python
@db.model
class Article:
    id: int
    title: str
    content: str
    search_vector: str  # tsvector column

    __dataflow__ = {
        'indexes': [
            {'fields': ['search_vector'], 'type': 'gin'}
        ],
        'triggers': [
            {
                'name': 'update_search_vector',
                'timing': 'BEFORE INSERT OR UPDATE',
                'function': """
                    NEW.search_vector =
                        setweight(to_tsvector('english', NEW.title), 'A') ||
                        setweight(to_tsvector('english', NEW.content), 'B');
                    RETURN NEW;
                """
            }
        ]
    }

# Full-text search
workflow.add_node("ArticleSearchNode", "search", {
    "query": "SELECT * FROM articles WHERE search_vector @@ plainto_tsquery('english', :search_term)",
    "params": {"search_term": "machine learning"}
})
```

#### Partitioning

```python
@db.model
class TimeSeries:
    id: int
    timestamp: datetime
    value: float
    sensor_id: str

    __dataflow__ = {
        'partitioning': {
            'strategy': 'range',
            'column': 'timestamp',
            'interval': 'monthly',
            'retention': '12 months'
        }
    }
```

### PostgreSQL Optimizations

```python
# Connection optimizations
@db.on_connect
def optimize_postgres(connection, record):
    with connection.cursor() as cursor:
        # Optimize for OLTP workloads
        cursor.execute("SET random_page_cost = 1.1")
        cursor.execute("SET effective_cache_size = '4GB'")
        cursor.execute("SET shared_buffers = '1GB'")

        # Set application name for monitoring
        cursor.execute(f"SET application_name = 'dataflow-{os.getpid()}'")
```

## MySQL

### Configuration

```python
config = DataFlowConfig(
    database_url="mysql://user:pass@localhost:3307/myapp",
    dialect="mysql",
    pool_size=30,
    pool_max_overflow=50,
    pool_recycle=7200,
    charset="utf8mb4",
    sql_mode="TRADITIONAL",
    isolation_level="READ_COMMITTED"
)

db = DataFlow(config=config)
```

### MySQL-Specific Features

#### JSON Support

```python
@db.model
class Config:
    id: int
    name: str
    settings: dict  # Stored as JSON

    __dataflow__ = {
        'indexes': [
            # MySQL virtual column index
            {
                'name': 'idx_settings_env',
                'expression': "(JSON_EXTRACT(settings, '$.environment'))",
                'type': 'btree'
            }
        ]
    }

# JSON queries
workflow.add_node("ConfigListNode", "find_prod", {
    "filter": {
        "settings->$.environment": "production",
        "JSON_CONTAINS(settings, '\"active\"', '$.status')": True
    }
})
```

#### Full-Text Search

```python
@db.model
class Document:
    id: int
    title: str
    content: str

    __dataflow__ = {
        'indexes': [
            {'fields': ['title', 'content'], 'type': 'fulltext'}
        ]
    }

# Full-text search with relevance
workflow.add_node("DocumentSearchNode", "search", {
    "query": """
        SELECT *, MATCH(title, content) AGAINST(:term IN NATURAL LANGUAGE MODE) as relevance
        FROM documents
        WHERE MATCH(title, content) AGAINST(:term IN NATURAL LANGUAGE MODE)
        ORDER BY relevance DESC
    """,
    "params": {"term": "database optimization"}
})
```

#### MySQL-Specific Optimizations

```python
# Table optimizations
@db.model
class HighVolumeTable:
    id: int
    data: str

    __dataflow__ = {
        'table_options': {
            'engine': 'InnoDB',
            'row_format': 'COMPRESSED',
            'key_block_size': 8,
            'stats_persistent': 1,
            'stats_auto_recalc': 0
        }
    }
```

### MySQL Connection Settings

```python
@db.on_connect
def optimize_mysql(connection, record):
    with connection.cursor() as cursor:
        # Set timezone
        cursor.execute("SET time_zone = '+00:00'")

        # Optimize for bulk operations
        cursor.execute("SET bulk_insert_buffer_size = 256M")
        cursor.execute("SET unique_checks = 0")
        cursor.execute("SET foreign_key_checks = 0")
```

## SQLite

### Configuration

```python
config = DataFlowConfig(
    database_url="sqlite:///./app.db",
    dialect="sqlite",
    pool_size=1,  # SQLite is single-threaded
    pool_max_overflow=0,
    check_same_thread=False,
    pragma={
        "journal_mode": "WAL",
        "cache_size": -64000,  # 64MB
        "foreign_keys": 1,
        "synchronous": "NORMAL"
    }
)

db = DataFlow(config=config)
```

### SQLite-Specific Features

#### JSON Support (SQLite 3.38+)

```python
# JSON operations in SQLite
workflow.add_node("SettingsUpdateNode", "update_json", {
    "query": """
        UPDATE settings
        SET config = json_set(config, '$.theme', :theme)
        WHERE user_id = :user_id
    """,
    "params": {"theme": "dark", "user_id": user_id}
})
```

#### Custom Functions

```python
@db.sqlite_function
def regexp(pattern, string):
    """Add REGEXP support to SQLite."""
    import re
    return re.search(pattern, string) is not None

# Use in queries
workflow.add_node("UserListNode", "find_emails", {
    "filter": {
        "email": {"REGEXP": r".*@(gmail|yahoo)\.com$"}
    }
})
```

### SQLite Optimizations

```python
# In-memory database for testing
test_config = DataFlowConfig(
    database_url="sqlite:///:memory:",
    dialect="sqlite"
)

# Attach additional databases
workflow.add_node("SQLiteAttachNode", "attach_db", {
    "database_path": "./analytics.db",
    "schema_name": "analytics",
    "mode": "readonly"
})
```

## MongoDB

### Configuration

```python
config = DataFlowConfig(
    database_url="mongodb://localhost:27017/myapp",
    dialect="mongodb",
    pool_size=50,
    max_idle_time_ms=30000,
    server_selection_timeout_ms=5000,
    read_preference="secondaryPreferred",
    write_concern={
        "w": "majority",
        "j": True,
        "wtimeout": 5000
    }
)

db = DataFlow(config=config)
```

### MongoDB-Specific Features

#### Document Models

```python
@db.model
class Product:
    _id: str
    name: str
    categories: list
    specifications: dict
    reviews: list[dict]

    __dataflow__ = {
        'collection': 'products',
        'indexes': [
            {'fields': ['name'], 'type': 'text'},
            {'fields': ['categories'], 'type': '2dsphere'},
            {'fields': [('price', -1), ('rating', -1)]},  # Compound
        ],
        'sharding': {
            'key': {'_id': 'hashed'},
            'unique': True
        }
    }
```

#### Aggregation Pipeline

```python
workflow.add_node("MongoAggregationNode", "sales_report", {
    "collection": "orders",
    "pipeline": [
        {"$match": {"status": "completed", "date": {"$gte": start_date}}},
        {"$group": {
            "_id": "$product_id",
            "total_sales": {"$sum": "$amount"},
            "count": {"$sum": 1},
            "avg_amount": {"$avg": "$amount"}
        }},
        {"$sort": {"total_sales": -1}},
        {"$limit": 10}
    ]
})
```

#### Change Streams

```python
workflow.add_node("MongoChangeStreamNode", "watch_orders", {
    "collection": "orders",
    "pipeline": [
        {"$match": {"operationType": {"$in": ["insert", "update"]}}}
    ],
    "full_document": "updateLookup",
    "handler": "process_order_change"
})
```

## Redis

### Configuration

```python
config = DataFlowConfig(
    database_url="redis://localhost:6380/0",
    dialect="redis",
    pool_size=50,
    decode_responses=True,
    socket_timeout=5,
    socket_connect_timeout=5,
    retry_on_timeout=True,
    health_check_interval=30
)

db = DataFlow(config=config)
```

### Redis-Specific Features

#### Data Structures

```python
# Redis data types
workflow.add_node("RedisHashNode", "user_session", {
    "operation": "hset",
    "key": f"session:{session_id}",
    "fields": {
        "user_id": user_id,
        "last_active": datetime.now().isoformat(),
        "ip_address": ip
    },
    "expire": 3600  # 1 hour TTL
})

# Sorted sets for leaderboards
workflow.add_node("RedisSortedSetNode", "update_score", {
    "operation": "zadd",
    "key": "leaderboard:daily",
    "members": {user_id: score},
    "options": {"xx": True}  # Only update existing
})

# Pub/Sub
workflow.add_node("RedisPubSubNode", "publish_event", {
    "channel": "events:user_activity",
    "message": {
        "user_id": user_id,
        "action": "login",
        "timestamp": datetime.now().isoformat()
    }
})
```

#### Redis Modules

```python
# RedisJSON
workflow.add_node("RedisJSONNode", "store_document", {
    "key": f"doc:{doc_id}",
    "path": "$",
    "value": document_data
})

# RedisSearch
workflow.add_node("RedisSearchNode", "create_index", {
    "index": "products",
    "schema": {
        "name": "TEXT WEIGHT 2.0",
        "description": "TEXT",
        "price": "NUMERIC SORTABLE",
        "categories": "TAG SEPARATOR ,"
    }
})

# RediTimeSeries
workflow.add_node("RedisTimeSeriesNode", "add_metric", {
    "key": f"metric:{metric_name}",
    "timestamp": "*",  # Auto timestamp
    "value": value,
    "labels": {"sensor": sensor_id, "location": location}
})
```

## Cross-Database Compatibility

### Portable Models

```python
@db.model
class User:
    id: int
    email: str
    created_at: datetime

    __dataflow__ = {
        'indexes': ['email'],  # Works across all databases
        'dialect_specific': {
            'postgresql': {
                'indexes': [
                    {'fields': ['email'], 'type': 'hash'}
                ]
            },
            'mysql': {
                'table_options': {'engine': 'InnoDB'}
            },
            'mongodb': {
                'collection': 'users',
                'indexes': [{'fields': ['email'], 'unique': True}]
            }
        }
    }
```

### Query Abstraction

```python
# DataFlow handles dialect differences
workflow.add_node("UserListNode", "search", {
    "filter": {
        "name": {"$regex": "john", "$options": "i"}  # Case-insensitive
    }
})

# Translates to:
# PostgreSQL: name ~* 'john'
# MySQL: name REGEXP '(?i)john'
# SQLite: name REGEXP '(?i)john' (with custom function)
# MongoDB: {name: {$regex: 'john', $options: 'i'}}
```

## Performance Considerations

### Connection Pooling by Dialect

| Database | Recommended Pool Size | Max Overflow | Recycle Time |
|----------|---------------------|--------------|--------------|
| PostgreSQL | CPU * 4 | CPU * 6 | 1 hour |
| MySQL | CPU * 6 | CPU * 10 | 2 hours |
| SQLite | 1 | 0 | N/A |
| MongoDB | 50-100 | N/A | 30 seconds |
| Redis | 50-100 | N/A | N/A |

### Dialect-Specific Optimizations

```python
# Optimize based on dialect
if db.dialect == "postgresql":
    workflow.add_node("VacuumNode", "maintenance", {
        "tables": ["high_churn_table"],
        "analyze": True
    })
elif db.dialect == "mysql":
    workflow.add_node("OptimizeTableNode", "optimize", {
        "tables": ["fragmented_table"]
    })
elif db.dialect == "mongodb":
    workflow.add_node("CompactNode", "compact", {
        "collection": "large_collection"
    })
```

## Migration Between Dialects

```python
# Export from one dialect
source_db = DataFlow(source_config)
workflow.add_node("ExportNode", "export_data", {
    "format": "dataflow_portable",
    "include_schema": True
})

# Import to another dialect
target_db = DataFlow(target_config)
workflow.add_node("ImportNode", "import_data", {
    "source": ":export_path",
    "dialect_mapping": True,
    "type_conversion": "auto"
})
```

## Next Steps

- **Configuration**: [Configuration Guide](../getting-started/configuration.md)
- **Performance**: [Performance Guide](../production/performance.md)
- **Migration**: [Migration Guide](../migration/README.md)

Choose the right database dialect for your use case and leverage dialect-specific features for optimal performance.
