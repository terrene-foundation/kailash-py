# Housekeeping Analysis for DataFlow and Nexus

## DataFlow Obsolete Files

### 1. Definitely Obsolete (Safe to Remove)
- `apps/kailash-dataflow/temp_test_dataflow_comprehensive.py` - Temporary test file
- `apps/kailash-dataflow/temp_test_dataflow_docs_execution.py` - Temporary test file
- `apps/kailash-dataflow/temp_test_dataflow_comprehensive_fixed.py` - Temporary test file
- `apps/kailash-dataflow/test_basic_examples.py` - Old test file at root level

### 2. Duplicate Structure (Needs Migration Check)
- `apps/kailash-dataflow/core/` directory - OLD monolithic structure
  - `engine.py` (746 lines) → Replaced by `src/dataflow/core/engine.py` (193 lines)
  - `config.py` → Contains `Environment` enum used by some tests - NEEDS MIGRATION
  - `schema.py` → Contains schema classes used by tests - NEEDS MIGRATION
  - `__init__.py` → Can be removed after migration

### 3. Test Files with Import Issues (NOT Obsolete - Need Fixing)
- `tests/unit/test_config.py` - Tests configuration functionality (needs import fix)
- `tests/unit/test_schema.py` - Tests schema functionality (needs import fix)
- `tests/unit/test_engine.py` - Tests engine functionality (needs import fix)
- `tests/unit/test_modular_*.py` - Tests for modular structure (need verification)

## Nexus Obsolete Files

### 1. Definitely Obsolete (Safe to Remove)
- `apps/kailash-nexus/temp_test_nexus_docs_execution.py` - Temporary test file
- `apps/kailash-nexus/temp_test_nexus_docs_integration.py` - Temporary test file
- `apps/kailash-nexus/temp_test_nexus_docs_simple.py` - Temporary test file
- `apps/kailash-nexus/temp_test_nexus_comprehensive.py` - Temporary test file

### 2. Current Structure (No Duplicates Found)
- `src/nexus/enterprise/backup.py` - Current implementation (KEEP)
- `src/nexus/enterprise/disaster_recovery.py` - Current implementation (KEEP)

## Migration Strategy

### For DataFlow:
1. First migrate `Environment` enum and any unique configuration from `core/config.py` to `src/dataflow/core/models.py`
2. Migrate any unique schema functionality from `core/schema.py`
3. Update all test imports to use new paths
4. Remove old `core/` directory only after verification

### For Nexus:
1. Remove temporary test files
2. No structural changes needed

## Import Fixes Needed
- 20 files importing from `kailash_dataflow` need to change to `dataflow`
- Test files using `Environment` need updated imports after migration
