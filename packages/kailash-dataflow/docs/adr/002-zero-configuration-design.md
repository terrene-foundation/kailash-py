# ADR-002: Zero-Configuration Design

## Status
Accepted

## Context
Django's settings.py is powerful but complex. Developers want to start immediately without configuration files, environment variables, or setup scripts. However, production deployments need fine-grained control.

## Decision
Implement progressive configuration disclosure:

### Level 1: Zero Config (Development)
```python
db = DataFlow()  # Just works!
```
- Uses in-memory SQLite
- Enables all development features
- Optimized for developer experience

### Level 2: Basic Config (Staging)
```python
db = DataFlow(database_url="postgresql://localhost/myapp")
```
- Auto-configures based on URL
- Sensible production defaults
- No manual pool configuration needed

### Level 3: Advanced Config (Production)
```python
db = DataFlow(
    pool_size=100,
    multi_tenant=True,
    monitoring=True
)
```
- Fine-tune specific aspects
- Override intelligent defaults
- Full control when needed

### Level 4: Expert Config (Enterprise)
```python
config = DataFlowConfig(
    database=DatabaseConfig(...),
    monitoring=MonitoringConfig(...),
    security=SecurityConfig(...)
)
db = DataFlow(config)
```
- Complete control over every aspect
- Custom configurations
- Enterprise-specific requirements

## Implementation

### Automatic Detection
1. **Environment**: Check KAILASH_ENV, ENVIRONMENT, default to development
2. **Database**: Check DATABASE_URL, then fall back to in-memory SQLite
3. **Pool Size**: Calculate based on CPU cores and environment
4. **Monitoring**: Enable for staging/production automatically

### Intelligent Defaults
```python
# Development
pool_size = min(5, cpu_count)
monitoring = False
debug = True

# Production
pool_size = min(50, cpu_count * 4)
monitoring = True
debug = False
```

### Configuration Sources (Priority Order)
1. Explicit parameters to DataFlow()
2. DataFlowConfig object
3. Environment variables
4. Automatic detection
5. Hardcoded defaults

## Consequences

### Positive
- Instant productivity for new users
- No configuration fatigue
- Production-ready without expertise
- Follows principle of least surprise

### Negative
- Magic can be confusing if not documented
- May hide important production decisions
- Defaults might not fit all use cases

### Mitigation
- Clear documentation of what's automated
- Logging of auto-configured values
- Easy override mechanisms
- Config validation with helpful errors

## Examples

### Development Workflow
```python
from kailash_dataflow import DataFlow

# Zero config - just works!
db = DataFlow()

@db.model
class User:
    name: str
    email: str

# Migrations run automatically
# In-memory database ready
# Hot reload enabled
```

### Production Deployment
```bash
# Set environment variable
export DATABASE_URL=postgresql://prod-server/app
export KAILASH_ENV=production

# Same code, production-ready
python app.py
```

### Custom Enterprise Setup
```python
# Full control when needed
config = DataFlowConfig(
    environment=Environment.PRODUCTION,
    database=DatabaseConfig(
        url=vault.get_secret("db_url"),
        pool_size=200,
        pool_pre_ping=True,
    ),
    security=SecurityConfig(
        multi_tenant=True,
        tenant_isolation_strategy="schema",
        gdpr_mode=True,
    )
)

db = DataFlow(config)
```

## References
- Spring Boot auto-configuration
- Rails convention over configuration
- Supabase instant databases
- Zero-config tools research
