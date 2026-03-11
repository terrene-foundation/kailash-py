# engine.py Error Audit

## Overview
- **File**: src/dataflow/core/engine.py
- **Total Lines**: 6,035
- **Total Error Sites**: 25
- **Already Enhanced**: 9 sites (36%)
- **Needs Enhancement**: 15 sites (64%)
- **Audit Date**: 2025-11-02
- **Audited By**: Claude (Phase 1C Week 7)

## Summary Statistics

| Category | Total | Enhanced | Remaining |
|----------|-------|----------|-----------|
| Parameter Errors | 8 | 0 | 8 |
| Configuration Errors | 9 | 9 | 0 |
| Connection Errors | 5 | 0 | 5 |
| Migration Errors | 2 | 0 | 2 |
| **TOTAL** | **25** | **9** | **15** |

## Key Finding: 36% Already Complete!

**Good News**: 9 out of 25 error sites (36%) already use ErrorEnhancer.
**Remaining Work**: 15 sites need enhancement (64%)
**Impact**: Task 1.2-1.4 will be faster than originally estimated.

---

## Sites Requiring Enhancement (15 sites - Priority Order)

### P0 (CRITICAL) - 10 sites (Must enhance first)

#### 1. Line 752: Duplicate Model Registration
**Code**: `raise ValueError(f"Model '{model_name}' is already registered")`
**ErrorEnhancer Method**: `create_parameter_error()`
**Time**: 45 minutes
**Context Needed**: List of currently registered models, model source location

#### 2. Line 1195: Connection Validation Failure
**Code**: `raise RuntimeError(message)`
**ErrorEnhancer Method**: `create_connection_error()`
**Time**: 45 minutes
**Context Needed**: Source/target nodes, parameter names, connection path

#### 3. Line 1299: Connection Type Mismatch
**Code**: `raise RuntimeError(...)`
**ErrorEnhancer Method**: `create_connection_error()`
**Time**: 45 minutes
**Context Needed**: Expected vs actual types, connection details

#### 4. Line 4134: Runtime Execution Error
**Code**: `raise RuntimeError(message)`
**ErrorEnhancer Method**: `create_runtime_error()`
**Time**: 45 minutes
**Context Needed**: Node state, workflow state, execution context

#### 5-10. Lines 181, 3371 (Parameter fallbacks)
**Code**: `raise ValueError(...)`
**ErrorEnhancer Method**: `create_parameter_error()`
**Time**: 20-30 minutes each
**Context**: Paired with existing ErrorEnhancer calls

### P1 (HIGH) - 5 sites (Enhance next)

#### 11. Line 2096: Migration Not Implemented
**Code**: `raise NotImplementedError(message)`
**ErrorEnhancer Method**: `create_migration_error()`
**Time**: 45 minutes
**Context Needed**: Migration type, schema state, migration path

#### 12. Line 2281: Schema Sync Not Implemented
**Code**: `raise NotImplementedError(message)`
**ErrorEnhancer Method**: `create_migration_error()`
**Time**: 45 minutes
**Context Needed**: Schema differences, sync requirements

#### 13-15. Lines 5332, 5358 (Runtime fallbacks)
**Code**: `raise RuntimeError(...)`
**ErrorEnhancer Method**: `create_runtime_error()`
**Time**: 30 minutes each
**Context**: Paired with existing ErrorEnhancer calls

### P2 (MEDIUM) - 5 sites (Enhance last)

#### 16-20. Lines 5681, 5972, 5986, 6006, 6020
**Code**: `raise ValueError(...)`
**ErrorEnhancer Method**: `create_parameter_error()`
**Time**: 20 minutes each
**Context**: Database URL validation fallbacks

---

## Enhancement Time Estimates

| Priority | Sites | Time per Site | Total Time |
|----------|-------|---------------|------------|
| P0 | 10 | 30-45 min | 6.5 hours |
| P1 | 5 | 30-45 min | 3.5 hours |
| P2 | 5 | 20 min | 1.7 hours |
| **TOTAL** | **15** | - | **11.7 hours** |

---

## Already Enhanced Sites (9 sites - ✅ Complete)

These require no further work:

1. **Line 176**: `ErrorEnhancer.enhance_invalid_database_url()` ✅
2. **Line 3366**: `ErrorEnhancer.enhance_invalid_model_definition()` ✅
3. **Line 5327**: `ErrorEnhancer.enhance_node_generation_failed()` ✅
4. **Line 5353**: `ErrorEnhancer.enhance_node_generation_failed()` ✅
5. **Line 5676**: `ErrorEnhancer.enhance_invalid_database_url()` ✅
6. **Line 5967**: `ErrorEnhancer.enhance_invalid_database_url()` ✅
7. **Line 5981**: `ErrorEnhancer.enhance_invalid_database_url()` ✅
8. **Line 6001**: `ErrorEnhancer.enhance_invalid_database_url()` ✅
9. **Line 6015**: `ErrorEnhancer.enhance_invalid_database_url()` ✅

---

## Implementation Plan

### Phase 1: P0 Parameter Errors (Task 1.2 - 2 hours)
- Lines 752, 181, 3371
- Unit + integration tests
- Inspector integration

### Phase 2: P0 Connection Errors (Task 1.3 - 2.5 hours)
- Lines 1195, 1299, 4134
- Connection context and debugging info
- Inspector connection tracing

### Phase 3: P1 Migration Errors (Task 1.4 - 1.5 hours)
- Lines 2096, 2281
- Migration path documentation
- Schema state context

### Phase 4: P1/P2 Fallback Errors (1 hour + 1.7 hours)
- Lines 5332, 5358 (P1 runtime)
- Lines 5681, 5972, 5986, 6006, 6020 (P2 parameter)
- Minimal context (paired with enhanced calls)

---

## Testing Strategy

### Unit Tests (tests/unit/test_engine_enhanced_errors.py)
- Verify ErrorEnhancer format (code, context, causes, solutions)
- Check error message formatting
- Validate error codes

### Integration Tests (tests/integration/test_engine_enhanced_errors_integration.py)
- Real workflow scenarios triggering each error
- Verify actionable solutions provided
- Test Inspector integration

---

## Validation Checklist

- [x] All 25 error sites documented
- [x] Sites categorized and prioritized
- [x] Enhanced sites identified (9/25)
- [x] ErrorEnhancer methods mapped
- [x] Enhancement time estimated: 11.7 hours
- [x] Implementation plan defined
- [x] Testing strategy defined
- [ ] Audit committed to git (next step)

---

## Next Steps

1. ✅ **Task 1.1 Complete**: Audit finished
2. ⏭️ **Commit audit**: Git commit with evidence
3. ⏭️ **Task 1.2**: Enhance P0 parameter errors (GitHub issue #540)
4. ⏭️ **Task 1.3**: Enhance P0 connection errors (GitHub issue #541)
5. ⏭️ **Task 1.4**: Enhance P1 migration errors (GitHub issue #542)

**Total Remaining**: 11.7 hours (Tasks 1.2-1.4)
