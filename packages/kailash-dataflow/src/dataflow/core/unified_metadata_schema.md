# Unified DataFlow Metadata Schema

## Proposed Integration Strategy

### Core Principle
Extend the existing migration system to support model registry functionality rather than creating separate systems.

### Unified Table Structure

#### 1. Enhanced Migration Table
```sql
-- Extend existing dataflow_migrations table
ALTER TABLE dataflow_migrations ADD COLUMN IF NOT EXISTS model_definitions JSONB;
ALTER TABLE dataflow_migrations ADD COLUMN IF NOT EXISTS application_id VARCHAR(255);
ALTER TABLE dataflow_migrations ADD COLUMN IF NOT EXISTS model_registry_sync BOOLEAN DEFAULT FALSE;
```

#### 2. Model Registry View
```sql
-- Create view for model registry functionality
CREATE VIEW dataflow_model_registry AS
SELECT
    application_id,
    model_definitions,
    checksum as model_checksum,
    applied_at as registered_at,
    version as schema_version
FROM dataflow_migrations
WHERE model_registry_sync = TRUE
AND status = 'applied'
ORDER BY applied_at DESC;
```

### Integration Points

#### 1. Model Registration Flow
```
Model Registration → Schema Comparison → Migration Generation → Model Registry Update
```

#### 2. Multi-Application Discovery
```
App Startup → Query Model Registry View → Sync Missing Models → Register Locally
```

#### 3. Unified Checksum Strategy
```
Model Definition + Schema Structure → Single Checksum → Used by Both Systems
```

## Implementation Steps

### Phase 1: Extend Migration System
1. Add model registry columns to existing migration table
2. Update migration recording to include model definitions
3. Create model registry view for queries

### Phase 2: Integrate Model Registry
1. Modify ModelRegistry to use migration system backend
2. Update discovery methods to query the view
3. Ensure checksum compatibility

### Phase 3: Unified API
1. Single interface for both migration and model registry operations
2. Coordinated initialization sequence
3. Consistent error handling

## Benefits

1. **Single Source of Truth**: All metadata in migration system
2. **Consistent Checksums**: One algorithm for change detection
3. **Coordinated Operations**: No race conditions between systems
4. **Simplified Maintenance**: One metadata schema to manage
5. **Backward Compatibility**: Existing migration system continues to work
