# DataFlow v0.5.0 Release Notes

## Major Features

### Context-Aware Table Creation Pattern
- **String ID Preservation**: Fixed critical bug where string/UUID IDs were incorrectly coerced to integers
- **Multi-Instance Isolation**: Multiple DataFlow instances now maintain separate contexts without interference
- **Instance-Bound Node Generation**: Generated CRUD nodes maintain references to their originating DataFlow instance
- **Deferred Schema Operations**: Model registration is synchronous while table creation is deferred for better performance

## Improvements

### Type-Aware ID Processing
- Respects model field type annotations for ID fields
- Preserves string IDs exactly as provided (no forced integer conversion)
- Supports UUIDs, session IDs, and other string-based identifiers
- Maintains backward compatibility with integer ID models

### Enhanced Multi-Instance Support
```python
# Each instance operates independently
dev_db = DataFlow("sqlite:///dev.db")
prod_db = DataFlow("postgresql://prod...")

@dev_db.model
class User:
    id: str  # String ID preserved
    name: str

@prod_db.model
class User:  # Same model name, different instance
    id: str
    name: str
    email: str
```

### Performance Optimizations
- Synchronous model registration (no async overhead during import)
- Lazy table creation on first use
- Reduced memory footprint for multi-instance scenarios
- Faster startup time with deferred schema operations

## Bug Fixes
- Fixed string ID coercion causing PostgreSQL type mismatch errors
- Fixed node context loss in multi-instance environments
- Fixed race conditions in concurrent schema operations
- Fixed instance isolation for models with identical names

## Breaking Changes
None - Full backward compatibility maintained

## Migration Guide
No migration required. Existing code continues to work without changes. To use string IDs, explicitly declare `id: str` in your models.

## Dependencies
- Requires Kailash Core SDK v0.9.19+
- Compatible with PostgreSQL, MySQL, SQLite
