# DataFlow Production Configuration Guide

**Complete guide to configuring DataFlow for optimal performance and safety in production environments.**

## 🎯 Configuration Overview

DataFlow v0.4.5+ provides fine-grained control over migration behavior and performance characteristics through key configuration parameters.

### Critical Parameters (v0.4.5 Focus)

| Parameter | Default | Performance | When to Use |
|-----------|---------|-------------|-------------|
| `auto_migrate=True` | ✅ Default | 2-5s startup | Development, staging, new deployments |
| `auto_migrate=False` | ❌ | <1s startup | Existing production, manual control |
| `existing_schema_mode=True` | ❌ | <1s startup | Legacy systems, maximum safety |

## 🚀 auto_migrate Parameter (v0.4.5 Fixed)

The `auto_migrate` parameter is the most critical configuration for production deployments. **v0.4.5 fixed a critical regression** where this parameter wasn't working correctly.

### auto_migrate=True (Default Behavior)

**When migration system is enabled:**

```python
db = DataFlow(
    database_url="postgresql://user:pass@host:5432/db",
    auto_migrate=True  # Default: enables full migration system
)
```

**What happens:**
- ✅ Migration system initialized on DataFlow startup
- ✅ Visual migration previews when models change
- ✅ Interactive confirmation for schema changes
- ✅ Automatic table creation and updates
- ✅ Schema evolution as you develop
- ⏱️ **Startup Time**: 2-5 seconds

**Best for:**
- 🏗️ Development and prototyping
- 🧪 Staging environments
- 🆕 New production deployments
- 🔄 Applications requiring automatic schema evolution

**Example Development Workflow:**
```python
# Development environment - full automation
db = DataFlow(
    database_url="sqlite:///dev.db",  # or PostgreSQL
    auto_migrate=True  # Let DataFlow manage everything
)

@db.model
class User:
    name: str
    email: str

# DataFlow automatically:
# 1. Creates the users table
# 2. Shows visual preview of schema changes
# 3. Applies migrations with confirmation
```

### auto_migrate=False (Production Optimization)

**When migration system is disabled (v0.4.5 FIXED):**

```python
db = DataFlow(
    database_url="postgresql://user:pass@host:5432/db",
    auto_migrate=False  # 🚨 v0.4.5 FIXED: Now properly disables migrations
)
```

**What happens:**
- ✅ No migration system initialization (95% faster startup)
- ✅ No automatic schema changes on model registration
- ✅ Tables created on-demand during first node execution
- ✅ Manual migration control when needed
- ⏱️ **Startup Time**: <1 second

**Performance Benefits (v0.4.5):**
- 🚀 **95% faster initialization** compared to auto_migrate=True
- ⚡ **Sub-second startup times** for production services
- 📊 **Eliminated 30+ second hangs** that occurred in v0.4.0-v0.4.4
- 🔧 **Manual migration control** for production environments

**Best for:**
- 🏭 Existing production databases
- ⚡ Microservices requiring fast startup
- 🛠️ Manual migration control requirements
- 📊 Multiple DataFlow instances (avoid migration conflicts)
- 🏢 Enterprise production deployments

**Example Production Configuration:**
```python
# Production service - manual migration control
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=False,  # 🚀 Fast startup
    pool_size=50,
    echo=False,
    monitoring=True
)

@db.model
class Order:
    customer_id: int
    total: float
    status: str = 'pending'

# No automatic migration occurs here
# Tables created when first node executes
```

### existing_schema_mode=True (Maximum Safety)

**When schema changes must be prevented:**

```python
db = DataFlow(
    database_url="postgresql://user:pass@host:5432/legacy_db",
    auto_migrate=False,
    existing_schema_mode=True  # 🛡️ Prevents ALL schema modifications
)
```

**What happens:**
- ✅ Complete schema safety for existing databases
- ✅ No table creation, no migrations, no schema changes
- ✅ Validates model compatibility with existing schema
- ✅ Fails fast if models don't match existing tables
- ⏱️ **Startup Time**: <1 second

**Best for:**
- 🏛️ Legacy systems with external schema management
- 🔒 Shared databases with other applications
- 🛡️ Production systems where schema changes are forbidden
- 📊 Analytics services that only read data

## 🎛️ Configuration Combinations

### Development Configuration

```python
# Fast development with automatic schema evolution
db = DataFlow(
    database_url="sqlite:///dev.db",
    auto_migrate=True,  # Full automation
    echo=True,          # See SQL queries
    debug=True          # Detailed logging
)
```

### Staging Configuration

```python
# Controlled staging environment
db = DataFlow(
    database_url="postgresql://user:pass@staging:5432/app",
    auto_migrate=True,  # Allow migrations for testing
    pool_size=10,
    monitoring=True
)
```

### Production Configuration (Recommended)

```python
# High-performance production with manual migration control
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    auto_migrate=False,  # 🚀 Fast startup, manual control
    pool_size=50,
    pool_max_overflow=100,
    echo=False,
    monitoring=True,
    audit_logging=True,
    cache_enabled=True
)
```

### Legacy System Configuration

```python
# Maximum safety for existing legacy databases
db = DataFlow(
    database_url=os.environ["LEGACY_DATABASE_URL"],
    auto_migrate=False,
    existing_schema_mode=True,  # 🛡️ No schema changes allowed
    pool_size=20,
    echo=False
)
```

## 🚀 Multi-Service Architecture (v0.4.5 Optimized)

**Before v0.4.5**: Multi-service deployments could take 120+ seconds due to registry endless loops.
**After v0.4.5**: Multi-service deployments complete in <15 seconds.

### Service Configuration Pattern

```python
# Service A: API Backend
api_db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # 🚀 <1s startup
    enable_model_persistence=True,
    pool_size=50
)

# Service B: Background Worker
worker_db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # 🚀 <1s startup
    enable_model_persistence=True,  # Shares models with API
    pool_size=20
)

# Service C: Analytics Service (Read-only)
analytics_db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,
    existing_schema_mode=True,  # 🛡️ No schema changes
    pool_size=30
)

# Service D: Migration Service (Dedicated)
migration_db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=True,  # Only service that handles migrations
    pool_size=5
)
```

**Deployment Results (v0.4.5):**
- ⏱️ Each service: <1-2 seconds startup
- 🚀 Total deployment: <15 seconds (was 120+ seconds)
- 💾 Shared model registry across services
- 🔧 Centralized migration control

## 📊 Performance Characteristics (v0.4.5)

### Startup Time Comparison

| Configuration | v0.4.0-v0.4.4 | v0.4.5 | Improvement |
|---------------|---------------|---------|-------------|
| `auto_migrate=False` | 30+ seconds* | <1 second | 95%+ faster |
| `auto_migrate=True` | 5-10 seconds | 2-5 seconds | 50%+ faster |
| `existing_schema_mode=True` | 30+ seconds* | <1 second | 95%+ faster |

*Due to registry endless loop bug and auto_migrate=False regression

### Memory Usage

```python
# Memory-optimized configuration
db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # No migration system overhead
    pool_size=20,        # Appropriate pool size
    enable_model_persistence=True,  # Efficient model sharing
    cache_enabled=True,  # Query result caching
    cache_ttl=3600      # 1 hour cache TTL
)
```

## 🛠️ Manual Migration Control

When using `auto_migrate=False`, you can still run migrations manually when needed:

### Option 1: Environment-Based Migration

```python
db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False  # Fast startup
)

# Models registered without automatic migration
@db.model
class User:
    name: str
    email: str

# Manual migration based on environment variable
if os.environ.get('RUN_MIGRATIONS', '').lower() == 'true':
    success, migrations = await db.auto_migrate(
        dry_run=False,
        auto_confirm=True
    )
    if success:
        print(f"Applied {len(migrations)} migrations")
    else:
        print("Migration failed")
        sys.exit(1)
```

### Option 2: Dedicated Migration Service

```python
class MigrationService:
    def __init__(self):
        self.migration_db = DataFlow(
            database_url=DATABASE_URL,
            auto_migrate=True,  # Only migration service enables auto-migration
            pool_size=5
        )
    
    async def apply_migrations(self):
        """Apply pending migrations."""
        return await self.migration_db.auto_migrate(
            dry_run=False,
            auto_confirm=True,
            max_risk_level="MEDIUM"
        )
    
    async def preview_migrations(self):
        """Preview pending migrations."""
        return await self.migration_db.auto_migrate(dry_run=True)

# Other services use auto_migrate=False
app_db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # Fast startup for application services
    pool_size=50
)
```

### Option 3: CI/CD Integration

```yaml
# docker-compose.yml
version: '3.8'
services:
  migration:
    image: myapp:latest
    command: python migrate.py
    environment:
      - RUN_MIGRATIONS=true
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - postgres

  api:
    image: myapp:latest
    command: python api.py
    environment:
      - AUTO_MIGRATE=false
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - migration
```

```python
# migrate.py - Dedicated migration script
async def main():
    db = DataFlow(
        database_url=os.environ["DATABASE_URL"],
        auto_migrate=True  # Enable for migration script
    )
    
    success, migrations = await db.auto_migrate(auto_confirm=True)
    if not success:
        sys.exit(1)
    
    print(f"Applied {len(migrations)} migrations successfully")

# api.py - Application service
async def main():
    db = DataFlow(
        database_url=os.environ["DATABASE_URL"], 
        auto_migrate=False  # Fast startup for API service
    )
    # Start API server...
```

## 🔧 Environment Variable Configuration

```bash
# Production environment variables
export DATABASE_URL="postgresql://user:pass@host:5432/production"
export DATAFLOW_AUTO_MIGRATE="false"
export DATAFLOW_EXISTING_SCHEMA_MODE="false"
export DATAFLOW_POOL_SIZE="50"
export DATAFLOW_MONITORING="true"
export DATAFLOW_AUDIT_LOGGING="true"
```

```python
# Environment-driven configuration
db = DataFlow(
    database_url=os.environ.get("DATABASE_URL"),
    auto_migrate=os.environ.get("DATAFLOW_AUTO_MIGRATE", "false").lower() == "true",
    existing_schema_mode=os.environ.get("DATAFLOW_EXISTING_SCHEMA_MODE", "false").lower() == "true",
    pool_size=int(os.environ.get("DATAFLOW_POOL_SIZE", "20")),
    monitoring=os.environ.get("DATAFLOW_MONITORING", "false").lower() == "true",
    audit_logging=os.environ.get("DATAFLOW_AUDIT_LOGGING", "false").lower() == "true"
)
```

## 🚨 Common Configuration Mistakes

### ❌ Wrong: Using auto_migrate=True in Production

```python
# Don't do this in production
db = DataFlow(
    database_url=PRODUCTION_URL,
    auto_migrate=True  # Slower startup, unexpected schema changes
)
```

**Problems:**
- Slower 2-5 second startup times
- Potential unexpected schema changes
- Interactive migration prompts in production
- Multiple instances may conflict

### ✅ Right: Production Configuration

```python
# Correct production configuration  
db = DataFlow(
    database_url=PRODUCTION_URL,
    auto_migrate=False,  # Fast startup, manual control
    existing_schema_mode=True,  # Safety for existing DB
    pool_size=50
)
```

### ❌ Wrong: Mixing Migration-Enabled Services

```python
# Don't do this - multiple services with auto_migrate=True
service1_db = DataFlow(database_url=DB_URL, auto_migrate=True)
service2_db = DataFlow(database_url=DB_URL, auto_migrate=True)
service3_db = DataFlow(database_url=DB_URL, auto_migrate=True)
```

**Problems:**
- Migration conflicts between services
- Slower deployment times
- Race conditions during schema changes

### ✅ Right: Centralized Migration Control

```python
# Only one service handles migrations
migration_service_db = DataFlow(database_url=DB_URL, auto_migrate=True)

# All other services use fast startup
app_service_db = DataFlow(database_url=DB_URL, auto_migrate=False)
worker_service_db = DataFlow(database_url=DB_URL, auto_migrate=False)
analytics_service_db = DataFlow(database_url=DB_URL, auto_migrate=False, existing_schema_mode=True)
```

## 📈 Monitoring Configuration Performance

```python
# Monitor configuration performance in production
import time
import dataflow

start_time = time.time()

db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # Should be <1s
    monitoring=True
)

startup_time = time.time() - start_time
print(f"DataFlow startup time: {startup_time:.2f}s")

# Alert if startup time exceeds expected v0.4.5 performance
if startup_time > 2.0:
    print(f"⚠️ Slow startup detected: {startup_time:.2f}s")
    print("Expected <1s for auto_migrate=False configuration")
    print("Check if you're on DataFlow v0.4.5+")
```

## 🎯 Configuration Decision Matrix

| Use Case | auto_migrate | existing_schema_mode | Startup Time | Best For |
|----------|--------------|----------------------|--------------|----------|
| **Development** | `True` | `False` | 2-5s | Rapid prototyping, automatic schema evolution |
| **Staging** | `True` | `False` | 2-5s | Testing migrations, integration testing |
| **New Production** | `False` | `False` | <1s | New deployments, manual migration control |
| **Existing Production** | `False` | `True` | <1s | Legacy systems, maximum safety |
| **Analytics/Read-Only** | `False` | `True` | <1s | Read-only services, reporting systems |
| **Migration Service** | `True` | `False` | 2-5s | Dedicated migration handling |

## 🚀 Upgrade Path from Pre-v0.4.5

If you're experiencing slow startup times or auto_migrate=False not working:

### Step 1: Upgrade DataFlow

```bash
pip install --upgrade kailash-dataflow==0.4.5
```

### Step 2: Verify Configuration

```python
import dataflow
print(f"DataFlow version: {dataflow.__version__}")

# Ensure v0.4.5+
assert dataflow.__version__ >= "0.4.5", "Please upgrade to v0.4.5+"
```

### Step 3: Update Configuration

```python
# Before v0.4.5 (potentially slow)
db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False  # May not have worked correctly
)

# After v0.4.5 (fast and reliable)
db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False,  # ✅ Now works correctly
    existing_schema_mode=True  # Add for maximum safety
)
```

### Step 4: Validate Performance

```python
import time
start = time.time()

db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=False
)

elapsed = time.time() - start
print(f"Startup time: {elapsed:.2f}s")

# Should be <1s with v0.4.5
if elapsed > 2.0:
    print("⚠️ Performance issue detected - check configuration")
else:
    print("✅ v0.4.5 performance confirmed")
```

---

**Summary**: DataFlow v0.4.5 provides reliable, high-performance configuration options for all deployment scenarios. Use `auto_migrate=False` for production environments to achieve <1 second startup times and manual migration control.