# Column Datatype Migration Safety Guide

**Safe column type conversions and DataFlow pattern integration for enterprise database operations.**

## 🎯 Overview

The Column Datatype Migration Engine provides safe, automated column type conversions with comprehensive safety analysis, data preservation guarantees, and DataFlow pattern compliance.

### Key Safety Features

- **Type Compatibility Matrix** - Automated safety assessment for all type conversions
- **Data Preservation Guarantees** - Zero data loss for safe conversions
- **PostgreSQL Optimization** - Native PostgreSQL type system integration
- **Rollback Support** - Automatic rollback generation for all type changes
- **Performance Analysis** - Impact assessment for large table conversions

## 🚀 Quick Start

### Basic Type Conversion

```python
from dataflow import DataFlow
from decimal import Decimal

# PostgreSQL connection required for DataFlow execution
db = DataFlow(database_url="postgresql://user:password@localhost:5432/mydb")

# Initial model with basic types
@db.model
class Product:
    name: str
    price: int      # Start with integer price
    weight: float
    active: bool = True

# Evolution: Safe type conversions
@db.model
class Product:
    name: str
    price: Decimal      # SAFE: int -> Decimal (no precision loss)
    weight: float
    dimensions: dict = None  # SAFE: new JSONB column
    active: bool = True
```

## 🛡️ Type Safety Matrix

### SAFE Conversions (Auto-Approved)

#### Numeric Type Widening
```python
@db.model
class Measurement:
    # All these conversions are SAFE (widening)
    small_int: int      # smallint -> integer -> bigint
    price: Decimal      # integer -> numeric/decimal
    temperature: float  # real -> double precision
    percentage: float   # integer -> float (safe widening)
```

#### String Type Expansion
```python
@db.model
class Article:
    # SAFE: VARCHAR length expansion
    title: str          # varchar(50) -> varchar(255) -> text
    content: str        # Always safe to expand string limits
    slug: str = None    # New string columns with defaults
```

#### PostgreSQL JSONB Integration
```python
@db.model
class Configuration:
    name: str
    # SAFE: Native PostgreSQL JSONB types
    settings: dict      # Becomes JSONB with GIN indexes
    features: list      # Becomes JSONB array
    metadata: dict = {} # JSONB with default empty object

    __dataflow__ = {
        'postgresql': {
            'jsonb_gin_indexes': ['settings', 'features'],
            'type_optimizations': {
                'settings': 'jsonb_pretty',  # Auto-format JSON
                'features': 'jsonb_array_elements'  # Array optimization
            }
        }
    }
```

### MEDIUM Risk Conversions (Review Required)

#### Precision Changes
```python
@db.model
class FinancialRecord:
    # MEDIUM: May require precision analysis
    amount: Decimal     # float -> decimal (check precision)
    rate: float         # decimal -> float (may lose precision)

    __dataflow__ = {
        'type_migrations': {
            'amount': {
                'precision_check': True,    # Analyze existing data
                'backup_before_conversion': True,
                'validation_queries': [
                    'SELECT COUNT(*) FROM table WHERE amount::text != amount::float::text'
                ]
            }
        }
    }
```

#### String to Structured Types
```python
@db.model
class UserProfile:
    name: str
    # MEDIUM: String to JSONB conversion
    preferences_json: str = None    # Legacy text field
    preferences: dict = None        # New JSONB field

    __dataflow__ = {
        'migration_strategy': 'dual_column',  # Keep both during transition
        'data_migration': {
            'from_field': 'preferences_json',
            'to_field': 'preferences',
            'converter': 'parse_json_safe',
            'fallback_value': '{}'
        }
    }
```

#### Nullability Changes
```python
@db.model
class Customer:
    name: str
    email: str
    # MEDIUM: Adding NOT NULL to existing nullable column
    phone: str          # nullable -> NOT NULL (requires data validation)

    __dataflow__ = {
        'nullability_migrations': {
            'phone': {
                'pre_migration_check': 'SELECT COUNT(*) FROM customers WHERE phone IS NULL',
                'default_value': 'UNKNOWN',  # For existing NULL values
                'validation_required': True
            }
        }
    }
```

### HIGH Risk Conversions (Manual Approval Required)

#### Precision Loss Operations
```python
# HIGH RISK: These require explicit approval
@db.model
class SensorData:
    timestamp: datetime
    # HIGH RISK: Potential precision/data loss
    # value: float    # OLD: double precision
    # value: int      # NEW: integer (HIGH RISK - precision loss)

    # SAFER APPROACH: Add new column first
    value_float: float = None    # Keep original
    value_rounded: int = None    # Add new field

    __dataflow__ = {
        'high_risk_migrations': {
            'value_conversion': {
                'requires_approval': True,
                'backup_required': True,
                'data_validation': [
                    'SELECT COUNT(*) FROM sensor_data WHERE value != ROUND(value)',
                    'SELECT MIN(value), MAX(value) FROM sensor_data'
                ],
                'rollback_plan': 'restore_from_backup'
            }
        }
    }
```

## 🔧 Column Migration Strategies

### 1. Dual Column Strategy (Safest)

```python
@db.model
class Account:
    id: int
    name: str

    # Phase 1: Add new column alongside old
    balance_cents: int = None      # Legacy integer (cents)
    balance_decimal: Decimal = None # New decimal field

    __dataflow__ = {
        'migration_phases': [
            {
                'phase': 1,
                'description': 'Add new decimal column',
                'operations': ['ADD_COLUMN balance_decimal']
            },
            {
                'phase': 2,
                'description': 'Migrate data from cents to decimal',
                'operations': ['UPDATE balance_decimal = balance_cents::decimal / 100']
            },
            {
                'phase': 3,
                'description': 'Validate data consistency',
                'operations': ['SELECT * WHERE balance_cents/100 != balance_decimal']
            },
            {
                'phase': 4,
                'description': 'Drop old column after app deployment',
                'operations': ['DROP_COLUMN balance_cents'],
                'requires_approval': True
            }
        ]
    }
```

### 2. In-Place Conversion (Medium Risk)

```python
@db.model
class Product:
    name: str
    # Direct type conversion with safety checks
    price: Decimal      # Converting from float to decimal

    __dataflow__ = {
        'in_place_conversions': {
            'price': {
                'from_type': 'REAL',
                'to_type': 'NUMERIC(10,2)',
                'safety_checks': [
                    'data_range_validation',
                    'precision_loss_detection',
                    'null_value_handling'
                ],
                'conversion_sql': 'ALTER TABLE products ALTER COLUMN price TYPE NUMERIC(10,2)',
                'rollback_sql': 'ALTER TABLE products ALTER COLUMN price TYPE REAL'
            }
        }
    }
```

### 3. Batch Conversion (Large Tables)

```python
@db.model
class EventLog:
    timestamp: datetime
    event_data: dict    # Converting large text field to JSONB

    __dataflow__ = {
        'batch_conversions': {
            'event_data': {
                'batch_size': 10000,        # Process in chunks
                'conversion_timeout': 300,  # 5 minutes per batch
                'parallel_workers': 4,      # Concurrent processing
                'progress_tracking': True,
                'pause_on_error': True,
                'conversion_logic': '''
                    UPDATE event_logs
                    SET event_data = event_data_text::jsonb
                    WHERE id BETWEEN $1 AND $2
                '''
            }
        }
    }
```

## 🔍 Type Safety Validation

### Pre-Migration Analysis

```python
from dataflow.migrations import TypeSafetyAnalyzer

class TypeSafetyValidator:
    """Validates type conversions before migration"""

    @staticmethod
    def analyze_conversion(db, table, column, from_type, to_type):
        """Comprehensive type conversion analysis"""

        analyzer = TypeSafetyAnalyzer(db)

        # Data range analysis
        data_analysis = analyzer.analyze_column_data(table, column)

        # Compatibility check
        compatibility = analyzer.check_type_compatibility(from_type, to_type)

        # Performance impact
        performance = analyzer.estimate_conversion_time(table, column)

        return {
            'safety_level': compatibility.safety_level,
            'data_loss_risk': compatibility.data_loss_risk,
            'conversion_time_estimate': performance.estimated_seconds,
            'data_range': {
                'min_value': data_analysis.min_value,
                'max_value': data_analysis.max_value,
                'null_count': data_analysis.null_count,
                'distinct_count': data_analysis.distinct_count
            },
            'recommendations': compatibility.recommendations
        }

# Usage in migration planning
db = DataFlow(database_url="postgresql://...")

analysis = TypeSafetyValidator.analyze_conversion(
    db, 'products', 'price', 'INTEGER', 'NUMERIC(10,2)'
)

print(f"Safety Level: {analysis['safety_level']}")
print(f"Data Loss Risk: {analysis['data_loss_risk']}")
print(f"Estimated Time: {analysis['conversion_time_estimate']}s")
```

### Post-Migration Validation

```python
class PostMigrationValidator:
    """Validates data integrity after type conversions"""

    @staticmethod
    async def validate_conversion(db, table, column, conversion_log):
        """Comprehensive post-conversion validation"""

        validation_results = {
            'data_integrity': await db.execute_query(f'''
                SELECT COUNT(*) as total_rows,
                       COUNT({column}) as non_null_rows,
                       COUNT(DISTINCT {column}) as distinct_values
                FROM {table}
            '''),

            'type_consistency': await db.execute_query(f'''
                SELECT pg_typeof({column}) as actual_type
                FROM {table} LIMIT 1
            '''),

            'constraint_validation': await db.execute_query(f'''
                SELECT conname, consrc
                FROM pg_constraint
                WHERE conrelid = '{table}'::regclass
                AND conkey = ARRAY[(
                    SELECT attnum FROM pg_attribute
                    WHERE attrelid = '{table}'::regclass
                    AND attname = '{column}'
                )]
            ''')
        }

        return validation_results

# Usage after migration
validator = PostMigrationValidator()
results = await validator.validate_conversion(db, 'products', 'price', migration_log)
```

## 📊 PostgreSQL-Specific Optimizations

### Native Type System Integration

```python
@db.model
class PostgreSQLOptimized:
    # Leverage PostgreSQL's rich type system
    id: int                         # SERIAL PRIMARY KEY
    amount: Decimal                 # NUMERIC(10,2) with precision
    tags: list                      # TEXT[] or JSONB array
    metadata: dict                  # JSONB with GIN index
    location: str                   # Can use GEOGRAPHY/GEOMETRY with PostGIS
    search_vector: str = None       # TSVECTOR for full-text search

    __dataflow__ = {
        'postgresql': {
            'column_types': {
                'amount': 'NUMERIC(12,4)',      # Custom precision
                'tags': 'TEXT[]',               # PostgreSQL array
                'metadata': 'JSONB',            # Native JSON storage
                'search_vector': 'TSVECTOR'     # Full-text search
            },
            'indexes': [
                {'fields': ['metadata'], 'type': 'GIN'},     # JSONB search
                {'fields': ['tags'], 'type': 'GIN'},         # Array search
                {'fields': ['search_vector'], 'type': 'GIN'} # Text search
            ],
            'constraints': [
                {'field': 'amount', 'check': 'amount >= 0'},
                {'field': 'tags', 'check': 'array_length(tags, 1) <= 50'}
            ]
        }
    }
```

### Advanced Migration Features

```python
@db.model
class AdvancedMigrations:
    name: str
    data: dict

    __dataflow__ = {
        'postgresql': {
            'advanced_migrations': {
                'concurrent_index_creation': True,  # Don't block writes
                'constraint_validation': 'NOT_VALID',  # Add constraint without validation
                'type_conversion_optimization': {
                    'use_rewrite': False,           # Avoid table rewrite when possible
                    'lock_timeout': '30s',          # Limit lock time
                    'work_mem': '256MB'             # Memory for sorting
                },
                'maintenance_settings': {
                    'maintenance_work_mem': '1GB',
                    'max_parallel_workers': 4,
                    'checkpoint_segments': 64
                }
            }
        }
    }
```

## 🔗 DataFlow Pattern Integration

### Enterprise Features Preservation

```python
@db.model
class EnterpriseModel:
    name: str
    value: Decimal      # Type change preserves enterprise features

    __dataflow__ = {
        'multi_tenant': True,       # Preserved during type migrations
        'soft_delete': True,        # Preserved during type migrations
        'audit_log': True,         # All type changes logged
        'versioned': True,         # Version tracking maintained

        'migration_preservation': {
            'tenant_isolation': True,      # Type changes respect tenancy
            'audit_trail': True,           # Log all type conversions
            'version_compatibility': True,  # Maintain version fields
            'soft_delete_integrity': True  # Preserve deletion logic
        }
    }

# Migration automatically preserves all enterprise features
# Tenant isolation, audit logs, and versioning continue working
```

### Connection Pooling During Migrations

```python
# Type migrations respect connection pooling
db = DataFlow(
    database_url="postgresql://user:pass@localhost/db",
    pool_size=20,
    migration_config={
        'connection_strategy': 'DEDICATED',    # Use separate connection for migrations
        'pool_preservation': True,             # Don't disrupt existing connections
        'migration_pool_size': 2,              # Dedicated migration connections
        'lock_timeout': 30,                    # Prevent long-running locks
        'statement_timeout': 300               # 5-minute timeout for migrations
    }
)
```

## 🎯 Best Practices

### 1. Safety First
```python
# Always validate before type changes
analysis = db.analyze_type_conversion('products', 'price', 'INTEGER', 'NUMERIC')
if analysis.safety_level == 'HIGH':
    print("Manual approval required")
    backup_table_before_migration()
```

### 2. Gradual Migration
```python
# Use phased approach for large tables
@db.model
class Product:
    price_old: int = None      # Phase 1: Keep original
    price_new: Decimal = None  # Phase 1: Add new column
    # price: Decimal            # Phase 3: Replace after validation
```

### 3. Performance Optimization
```python
# Monitor migration performance
migration_config = {
    'batch_size': 10000,
    'progress_reporting': True,
    'performance_monitoring': True,
    'pause_on_slow_query': True
}
```

### 4. Rollback Readiness
```python
# Always have rollback plan
migration_plan = {
    'forward_migration': 'ALTER COLUMN price TYPE NUMERIC(10,2)',
    'rollback_migration': 'ALTER COLUMN price TYPE INTEGER',
    'data_validation': 'SELECT COUNT(*) WHERE price != ROUND(price)',
    'backup_table': 'CREATE TABLE products_backup AS SELECT * FROM products'
}
```

## 📈 Migration Monitoring

### Real-Time Progress Tracking

```python
async def monitor_type_migration():
    """Monitor type conversion progress"""

    progress = await db.get_migration_progress()

    print(f"Migration: {progress.operation}")
    print(f"Progress: {progress.percent_complete}%")
    print(f"Estimated remaining: {progress.time_remaining_seconds}s")
    print(f"Rows processed: {progress.rows_processed}/{progress.total_rows}")

    if progress.errors:
        print(f"Errors encountered: {len(progress.errors)}")
        for error in progress.errors:
            print(f"  - {error.message}")
```

### Performance Metrics

```python
# Get detailed migration performance data
metrics = await db.get_type_migration_metrics()

print(f"Average conversion time per row: {metrics.avg_time_per_row}ms")
print(f"Memory usage peak: {metrics.peak_memory_mb}MB")
print(f"Disk I/O: {metrics.disk_reads}/{metrics.disk_writes}")
print(f"Lock wait time: {metrics.lock_wait_time_ms}ms")
```

---

## 🎯 Next Steps

- **[Migration Orchestration Engine](migration-orchestration-engine.md)**: Central coordination system
- **[Auto-Migration System](auto-migration.md)**: Interactive migration workflows
- **[Production Deployment](../production/deployment.md)**: Production migration strategies
- **[Database Optimization](../advanced/database-optimization.md)**: Performance tuning

---

**Column Datatype Migration Safety: Enterprise-grade type conversions with zero data loss and comprehensive safety controls.** 🛡️

*Transform your database type changes from risky manual operations to safe, automated, and intelligent conversions.*
