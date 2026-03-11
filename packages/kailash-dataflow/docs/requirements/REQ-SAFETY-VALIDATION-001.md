# REQ-SAFETY-VALIDATION-001: Production Safety Validation System

## Requirements Analysis Report

### Executive Summary
- **Feature**: Replace mock migration safety checks with real database validation
- **Complexity**: High
- **Risk Level**: Critical (current implementation poses data corruption risk)
- **Estimated Effort**: 14 days (2-3 weeks)
- **Priority**: CRITICAL - P0 (blocks safe production deployment)

---

## Functional Requirements Matrix

| Requirement ID | Description | Input | Output | Business Logic | Edge Cases | SDK Mapping |
|----------------|-------------|-------|---------|----------------|------------|-------------|
| **FR-001** | Foreign Key Constraint Validation | old_table, new_table, connection | SafetyCheckResult | Query pg_constraint for FKs referencing old/new table, validate all FKs updated | Circular FKs, CASCADE rules, multi-column FKs | PostgreSQL system catalogs |
| **FR-002** | Unique Index Validation | old_table, new_table, connection | SafetyCheckResult | Query pg_indexes for indexes on old table (should be none) and new table (should exist) | Partial indexes, expression indexes, multi-column unique | pg_indexes, pg_index |
| **FR-003** | Check Constraint Validation | old_table, new_table, connection | SafetyCheckResult | Query pg_constraint for CHECK constraints, validate definitions don't reference old table | Complex check expressions, multiple constraints | pg_constraint, pg_get_constraintdef |
| **FR-004** | Primary Key Validation | old_table, new_table, connection | SafetyCheckResult | Validate PK exists on new table, no PK on old table | Composite PKs, named vs unnamed PKs | pg_constraint |
| **FR-005** | View Dependency Validation | old_table, new_table, connection | SafetyCheckResult | Query pg_views for views referencing old table name in SQL definition | Complex view queries, nested views, aliased tables | pg_views, pg_get_viewdef |
| **FR-006** | Materialized View Validation | old_table, new_table, connection | SafetyCheckResult | Query pg_matviews for materialized views, ensure refreshable | WITH NO DATA matviews, concurrent refresh | pg_matviews |
| **FR-007** | Trigger Reference Validation | old_table, new_table, connection | SafetyCheckResult | Query information_schema.triggers for triggers on old table (none) and new table | Trigger functions referencing table, BEFORE/AFTER triggers | information_schema.triggers |
| **FR-008** | Function/Procedure Validation | old_table, new_table, connection | SafetyCheckResult | Search pg_proc for functions with table references in body | Dynamic SQL in functions, table parameters | pg_proc, pg_get_functiondef |
| **FR-009** | SQLite FK Validation | old_table, new_table, connection | SafetyCheckResult | Use PRAGMA foreign_key_list to validate FKs | SQLite FK enforcement modes, PRAGMA foreign_keys=ON | sqlite_master, PRAGMA |
| **FR-010** | SQLite Index Validation | old_table, new_table, connection | SafetyCheckResult | Query sqlite_master for indexes on table | Automatic indexes, unique constraints | sqlite_master |
| **FR-011** | Database Type Detection | connection | DatabaseType | Detect if connection is PostgreSQL or SQLite | Mixed database environments, connection pooling | asyncpg.Connection type checking |
| **FR-012** | Safety Check Aggregation | list of SafetyCheckResults | ProductionSafetyResults | Aggregate all checks, determine overall pass/fail, severity | Conflicting results, warning vs error | N/A |
| **FR-013** | Orchestrator Integration | workflow configuration | OrchestratorResult | Call safety validation, fail deployment on CRITICAL violations | Safety checks disabled, staging-only mode | CompleteRenameOrchestrator |
| **FR-014** | Error Reporting | SafetyCheckResult | formatted error message | Generate user-friendly error with violations, recommendations, affected objects | Multiple violations, long object names | Logging infrastructure |
| **FR-015** | Performance Optimization | validation queries | execution time | Optimize queries for large schemas, parallel execution where safe | 1000+ table schemas, complex views | Connection pooling |

---

## Non-Functional Requirements

### Performance Requirements
- **NFR-001**: Safety validation must complete in <5 seconds for schemas with <100 tables
- **NFR-002**: Safety validation must complete in <30 seconds for schemas with <1000 tables
- **NFR-003**: Individual safety check must complete in <2 seconds
- **NFR-004**: Database query optimization: use indexes, limit result sets, minimize round trips
- **NFR-005**: Memory usage: <100MB for validation data structures

**Measurement Strategy**:
- Benchmark against test databases of varying sizes (10, 100, 1000 tables)
- Profile query execution time using EXPLAIN ANALYZE
- Monitor memory usage during validation
- Set timeout thresholds with graceful degradation

### Security Requirements
- **NFR-006**: All database queries must use parameterized queries (prevent SQL injection)
- **NFR-007**: No database credentials stored in safety check results
- **NFR-008**: Database connection must be obtained from connection_manager (no direct connections)
- **NFR-009**: Safety check logs must not expose sensitive schema information in clear text
- **NFR-010**: Read-only database operations (no mutations during validation)

**Security Validation**:
- Code review for SQL injection vulnerabilities
- Audit all queries for parameterization
- Test with malicious table names
- Verify no write operations in validation code

### Scalability Requirements
- **NFR-011**: Support schemas with 10,000+ tables
- **NFR-012**: Support tables with 1000+ columns
- **NFR-013**: Support databases with 100+ concurrent connections
- **NFR-014**: Parallel validation execution where safe (non-blocking checks)

**Scalability Testing**:
- Generate large test schemas
- Load test with concurrent validations
- Monitor database connection pool usage

### Reliability Requirements
- **NFR-015**: Validation must be idempotent (same input = same output)
- **NFR-016**: Failed validation must not modify database state
- **NFR-017**: Connection failures must be gracefully handled with clear error messages
- **NFR-018**: Validation must work across database restarts/reconnections

**Reliability Testing**:
- Test validation retry logic
- Simulate connection failures
- Verify no state changes in database

### Maintainability Requirements
- **NFR-019**: Database-specific logic must be isolated in separate classes
- **NFR-020**: New database support requires implementing BaseSafetyValidator interface
- **NFR-021**: All validation queries must be documented with purpose and expected results
- **NFR-022**: Validation results must include executed SQL for debugging

**Maintainability Practices**:
- Clear separation of concerns (PostgreSQL vs SQLite)
- Comprehensive inline documentation
- Logging all executed queries with parameters

---

## User Journey Mapping

### Developer Journey: Safe Production Deployment

**Persona**: Backend Developer deploying table rename to production

**Steps**:
1. **Configure rename workflow**
   ```python
   workflow = EndToEndRenameWorkflow(
       workflow_id="prod_rename_001",
       old_table_name="users",
       new_table_name="app_users",
       enable_production_safety_checks=True  # Enable safety validation
   )
   ```

2. **Execute orchestration**
   ```python
   orchestrator = CompleteRenameOrchestrator(connection_manager)
   result = await orchestrator.execute_complete_rename(
       old_table="users",
       new_table="app_users",
       enable_production_safety_checks=True
   )
   ```

3. **Receive validation results**
   - ✓ Safety validation executes automatically
   - ✓ Real database introspection performed
   - ✓ Detailed results returned in OrchestratorResult

4. **Handle validation outcomes**

   **Success Case**:
   ```python
   if result.success and result.production_safety_validated:
       print("✓ Production deployment safe!")
       print(f"Schema integrity: PASS")
       print(f"Application compatibility: PASS")
   ```

   **Failure Case**:
   ```python
   if not result.production_safety_validated:
       print("✗ Production deployment BLOCKED!")
       print(f"Violations found: {result.safety_check_results}")

       # Example output:
       # schema_integrity:
       #   - FK constraint 'fk_user_orders' still references old table 'users'
       #   - View 'active_users_view' still references old table 'users'
       # application_compatibility:
       #   - Trigger 'update_user_timestamp' still on old table 'users'
   ```

5. **Remediate issues**
   - Review specific violations
   - Fix schema objects (update views, recreate triggers, etc.)
   - Re-run validation
   - Deploy when validation passes

**Success Criteria**:
- ✓ Developer gets clear pass/fail indication
- ✓ Specific violations identified with object names
- ✓ Recommendations provided for fixes
- ✓ Validation completes in <10 seconds
- ✓ No unsafe migrations deployed

**Failure Points**:
- ❌ Unclear error messages (fix: detailed violation reporting)
- ❌ Long validation time (fix: query optimization)
- ❌ False positives (fix: severity levels with warnings)
- ❌ Missing database permissions (fix: graceful error handling)

---

## Architecture Decision Record Summary

**Decision**: Implement comprehensive production safety validation system

**Key Components**:
1. **SafetyCheckResult**: Structured validation results with severity levels
2. **BaseSafetyValidator**: Abstract base class for database-specific validators
3. **PostgreSQLSafetyValidator**: PostgreSQL-specific validation using system catalogs
4. **SQLiteSafetyValidator**: SQLite-specific validation using PRAGMA and sqlite_master
5. **ProductionSafetyValidator**: Main orchestrator coordinating all checks

**Validation Categories**:
- **Schema Integrity**: FK constraints, unique indexes, check constraints, PKs
- **Application Compatibility**: Views, triggers, functions, materialized views

**Integration Point**: CompleteRenameOrchestrator._execute_orchestration_workflow()

---

## Risk Assessment Matrix

### High Probability, High Impact (CRITICAL)

**1. Current Mock Checks Allow Data Corruption**
- **Risk**: Dangerous migrations proceed unchecked, causing production data corruption
- **Probability**: High (mock checks always pass)
- **Impact**: Critical (data loss, production outages)
- **Mitigation**: Replace with real validation (THIS PROJECT)
- **Prevention**: Comprehensive test coverage, staging validation required

**2. False Negatives in Validation**
- **Risk**: Real safety issues not detected by validation logic
- **Probability**: Medium (complex database features)
- **Impact**: High (unsafe migration deployed)
- **Mitigation**: Comprehensive test coverage with real databases
- **Prevention**: Continuous validation testing, user feedback loop

### Medium Probability, Medium Impact (MONITOR)

**3. Performance Degradation on Large Schemas**
- **Risk**: Validation takes too long, blocks deployments
- **Probability**: Medium (large enterprise schemas)
- **Impact**: Medium (delayed deployments)
- **Mitigation**: Query optimization, parallel execution, timeouts
- **Prevention**: Performance benchmarking, profiling

**4. Database Permission Issues**
- **Risk**: Insufficient permissions to query system catalogs
- **Probability**: Medium (restrictive production environments)
- **Impact**: Medium (validation cannot run)
- **Mitigation**: Clear error messages, permission requirement documentation
- **Prevention**: Permission check in initialization

**5. False Positives from Validation**
- **Risk**: Safe migrations blocked by overly strict validation
- **Probability**: Medium (complex edge cases)
- **Impact**: Medium (developer frustration)
- **Mitigation**: Severity levels (WARNING vs ERROR), override mechanisms
- **Prevention**: Comprehensive testing, user feedback

### Low Probability, Low Impact (ACCEPT)

**6. Database Version Compatibility**
- **Risk**: Validation queries don't work on older/newer database versions
- **Probability**: Low (stable system catalog structure)
- **Impact**: Low (specific version issues)
- **Mitigation**: Version detection, fallback queries
- **Prevention**: Multi-version testing

---

## Integration with Existing SDK

### Reusable Components Analysis

#### Can Reuse Directly

**1. TableRenameAnalyzer**
- **Component**: Phase 1 schema analysis engine
- **Usage**: Provides schema object discovery (FKs, views, indexes, triggers)
- **Integration**: Use discovered objects as basis for safety validation
- **Benefits**: Avoid duplicate schema introspection

**2. Connection Manager**
- **Component**: Database connection management
- **Usage**: Obtain connections for validation queries
- **Integration**: All validators use connection_manager.get_connection()
- **Benefits**: Consistent connection handling, pooling support

**3. RenameCoordinationEngine**
- **Component**: Phase 2 rename coordination
- **Usage**: Workflow context and table name tracking
- **Integration**: Access workflow state during validation
- **Benefits**: Consistent table name handling

**4. ProductionDeploymentValidator**
- **Component**: Existing production validation infrastructure
- **Usage**: Deployment gates, approval workflows, risk assessment
- **Integration**: Add safety validation as additional deployment gate
- **Benefits**: Consistent deployment safety framework

#### Need Modification

**5. OrchestratorResult**
- **Current**: Uses mock SafetyCheck objects
- **Modification**: Replace with SafetyCheckResult objects
- **Reason**: Need structured results with severity, violations, warnings

**6. EndToEndRenameWorkflow**
- **Current**: Boolean enable_production_safety_checks flag
- **Modification**: Add safety_validation_config: SafetyValidationConfig
- **Reason**: Allow configuration of validation behavior (timeouts, severity thresholds)

#### Must Build New

**7. BaseSafetyValidator**
- **Purpose**: Abstract base class for database-specific validators
- **Reason**: Need polymorphic interface for PostgreSQL vs SQLite

**8. SafetyCheckResult**
- **Purpose**: Structured validation result with severity levels
- **Reason**: No existing equivalent for detailed validation results

**9. PostgreSQLSafetyValidator**
- **Purpose**: PostgreSQL-specific validation logic
- **Reason**: Need database-specific system catalog queries

**10. SQLiteSafetyValidator**
- **Purpose**: SQLite-specific validation logic
- **Reason**: Need database-specific PRAGMA and sqlite_master queries

---

## Edge Cases and Failure Scenarios

### Edge Case 1: Circular Foreign Key Dependencies
**Scenario**: Table A references Table B, Table B references Table A

**Handling**:
- Detect circular dependencies in FK validation
- Report as WARNING (not ERROR) if both tables renamed consistently
- Provide recommendation to use deferred constraints

**Test Case**:
```python
# Table structure:
# orders (id, user_id FK → users.id)
# users (id, last_order_id FK → orders.id)

# Rename both: orders → customer_orders, users → app_users
# Expected: WARNING if both FKs updated correctly
```

### Edge Case 2: Complex View with Multiple Table References
**Scenario**: View references renamed table multiple times with aliases

**Handling**:
- Parse view definition for all table references
- Match table name with word boundaries (avoid false positives)
- Check view is queryable after rename

**Test Case**:
```sql
CREATE VIEW order_summary AS
SELECT u1.name as customer_name,
       u2.name as sales_rep_name
FROM orders o
JOIN users u1 ON o.customer_id = u1.id
JOIN users u2 ON o.sales_rep_id = u2.id;

-- If 'users' renamed to 'app_users':
-- Expected: CRITICAL violation, view broken
```

### Edge Case 3: Materialized View with Data Dependencies
**Scenario**: Materialized view populated with data from renamed table

**Handling**:
- Validate materialized view is refreshable
- Check if WITH NO DATA (no refresh needed)
- Ensure CONCURRENTLY refresh still possible

**Test Case**:
```sql
CREATE MATERIALIZED VIEW user_stats AS
SELECT user_id, COUNT(*) as order_count
FROM orders GROUP BY user_id;

-- If 'orders' renamed:
-- Expected: HIGH violation, matview needs recreation
```

### Edge Case 4: Trigger Function with Dynamic SQL
**Scenario**: Trigger function uses EXECUTE with dynamic table names

**Handling**:
- Parse trigger function body for table references
- Flag dynamic SQL as WARNING (cannot validate fully)
- Recommend manual verification

**Test Case**:
```sql
CREATE FUNCTION audit_changes() RETURNS TRIGGER AS $$
BEGIN
    EXECUTE 'INSERT INTO ' || TG_TABLE_NAME || '_audit VALUES ($1)'
    USING NEW.id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- If table renamed:
-- Expected: WARNING, dynamic SQL requires manual check
```

### Edge Case 5: Multi-Column Unique Constraints
**Scenario**: Unique constraint spans multiple columns

**Handling**:
- Validate all columns still exist
- Check constraint definition updated
- Ensure uniqueness still enforced

**Test Case**:
```sql
ALTER TABLE users ADD CONSTRAINT uq_email_tenant
UNIQUE (email, tenant_id);

-- If 'users' renamed to 'app_users':
-- Expected: Validate constraint exists on app_users
```

### Edge Case 6: Partial Indexes
**Scenario**: Index with WHERE clause

**Handling**:
- Validate index predicate doesn't reference old table
- Check index is usable
- Ensure index valid and ready

**Test Case**:
```sql
CREATE UNIQUE INDEX idx_active_users_email
ON users (email)
WHERE status = 'active';

-- If 'users' renamed:
-- Expected: Validate index on new table, predicate valid
```

### Edge Case 7: PostgreSQL Extensions
**Scenario**: Table uses PostgreSQL extension features (e.g., PostGIS geometry)

**Handling**:
- Validate extension types still resolved
- Check extension-specific indexes
- Ensure extension functions compatible

**Test Case**:
```sql
CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    point GEOMETRY(Point, 4326)
);
CREATE INDEX idx_locations_gist ON locations USING GIST (point);

-- If 'locations' renamed:
-- Expected: Validate GIST index exists and usable
```

### Edge Case 8: SQLite Without Foreign Key Enforcement
**Scenario**: SQLite database with PRAGMA foreign_keys = OFF

**Handling**:
- Detect FK enforcement mode
- Report WARNING if FKs not enforced
- Validate FK structure even if not enforced

**Test Case**:
```python
# SQLite with PRAGMA foreign_keys = OFF
# Expected: WARNING - FKs exist but not enforced
# Still validate FK definitions correct
```

### Edge Case 9: Database Connection Loss During Validation
**Scenario**: Connection drops mid-validation

**Handling**:
- Catch connection exceptions
- Return FAILED validation with clear error
- Don't mark as PASSED on error

**Test Case**:
```python
# Simulate connection loss during validation
# Expected: SafetyCheckResult(passed=False, message="Connection lost")
```

### Edge Case 10: Very Large Tables (Timeout Risk)
**Scenario**: Table with 100M+ rows, validation queries timeout

**Handling**:
- Set query timeouts (default 10 seconds)
- Use LIMIT in validation queries where appropriate
- Fail gracefully on timeout

**Test Case**:
```python
# Large table validation with timeout
# Expected: Complete within timeout or return timeout error
```

---

## Success Criteria

### Functional Success Criteria

**1. All FK Constraints Validated**
- [ ] Detect orphaned FKs on old table
- [ ] Validate all FKs on new table correct
- [ ] Check CASCADE rules still valid
- [ ] Test with circular FKs

**2. All Unique Indexes Validated**
- [ ] Detect indexes on old table
- [ ] Validate indexes on new table exist
- [ ] Check index definitions correct
- [ ] Test with partial indexes

**3. All Check Constraints Validated**
- [ ] Detect constraints on old table
- [ ] Validate constraints on new table
- [ ] Check constraint expressions valid
- [ ] Test with complex expressions

**4. All Views Validated**
- [ ] Detect views referencing old table
- [ ] Validate views on new table queryable
- [ ] Check materialized views refreshable
- [ ] Test with nested views

**5. All Triggers Validated**
- [ ] Detect triggers on old table
- [ ] Validate triggers on new table functional
- [ ] Check trigger functions valid
- [ ] Test with trigger dependencies

### Performance Success Criteria

**1. Validation Speed**
- [ ] <5 seconds for 100-table schema
- [ ] <30 seconds for 1000-table schema
- [ ] Individual checks <2 seconds
- [ ] Parallel execution where safe

**2. Resource Usage**
- [ ] <100MB memory for validation
- [ ] Minimal database connection usage
- [ ] No connection pool exhaustion
- [ ] Graceful degradation on resource limits

### Quality Success Criteria

**1. Accuracy**
- [ ] >95% accuracy in violation detection
- [ ] <10% false positive rate
- [ ] Zero false negatives for critical issues
- [ ] Clear severity classification

**2. Usability**
- [ ] Clear error messages for all violations
- [ ] Actionable recommendations provided
- [ ] Affected objects clearly identified
- [ ] Execution time reported

**3. Reliability**
- [ ] Idempotent validation (same input = same output)
- [ ] No database state changes during validation
- [ ] Graceful handling of connection failures
- [ ] Works across database restarts

---

## Implementation Roadmap

### Phase 1: Foundation (Days 1-3)
**Objective**: Core infrastructure and PostgreSQL FK validation

**Deliverables**:
- SafetyCheckResult dataclass
- BaseSafetyValidator base class
- DatabaseDetector
- PostgreSQL FK constraint validation
- Unit tests for all components

**Validation**:
- All unit tests pass
- FK validation detects orphaned constraints
- Clear error messages generated

### Phase 2: PostgreSQL Schema Integrity (Days 4-7)
**Objective**: Complete PostgreSQL schema integrity validation

**Deliverables**:
- Unique index validation
- Check constraint validation
- Primary key validation
- Trigger validation
- Integration tests

**Validation**:
- All validation types work on real PostgreSQL
- <5 second validation for 100-table schema
- Comprehensive test coverage

### Phase 3: Application Compatibility (Days 8-10)
**Objective**: PostgreSQL application compatibility validation

**Deliverables**:
- View dependency validation
- Materialized view validation
- Function/procedure validation
- Complete PostgreSQL validator

**Validation**:
- Views, functions, triggers all validated
- Complex edge cases handled
- Clear recommendations for fixes

### Phase 4: SQLite Support (Days 11-12)
**Objective**: SQLite validation implementation

**Deliverables**:
- SQLiteSafetyValidator
- SQLite FK validation
- SQLite index validation
- SQLite trigger validation

**Validation**:
- All validation types work on SQLite
- Feature parity with PostgreSQL
- Cross-database test coverage

### Phase 5: Integration and Polish (Days 13-14)
**Objective**: Orchestrator integration and production readiness

**Deliverables**:
- CompleteRenameOrchestrator integration
- Remove mock safety checks
- Error reporting enhancements
- End-to-end testing
- Documentation

**Validation**:
- End-to-end workflows pass
- No regressions in existing functionality
- Production-ready error handling
- Complete documentation

---

## Validation Strategy

### Unit Testing
**Coverage**: Individual validation functions

**Test Cases**:
1. FK constraint validation with valid FKs
2. FK constraint validation with orphaned FKs
3. Unique index validation with valid indexes
4. Unique index validation with missing indexes
5. View validation with broken views
6. Trigger validation with invalid triggers
7. Database type detection (PostgreSQL vs SQLite)
8. SafetyCheckResult severity classification
9. Error message generation
10. Performance benchmarking

**Framework**: pytest with real database fixtures (NO MOCKING)

### Integration Testing
**Coverage**: End-to-end validation workflows

**Test Cases**:
1. Complete validation on PostgreSQL with all object types
2. Complete validation on SQLite with all object types
3. Validation failure scenarios (broken FKs, views, triggers)
4. Performance testing with large schemas
5. Connection failure handling
6. Timeout scenarios
7. Concurrent validation execution
8. Database version compatibility
9. Permission error handling
10. Cross-database consistency

**Framework**: pytest with real PostgreSQL + SQLite databases

### End-to-End Testing
**Coverage**: Full orchestration workflow with safety validation

**Test Cases**:
1. Successful rename with safety validation PASS
2. Blocked rename with CRITICAL violations
3. Warning-level violations (deployment proceeds)
4. Multiple safety check failures
5. Orchestrator error handling
6. Result reporting and logging
7. Staging validation integration
8. Production deployment gates
9. Rollback after validation failure
10. Performance under production load

**Framework**: pytest with complete orchestration setup

---

## Documentation Requirements

### User Documentation

**1. Safety Validation Guide**
- How safety validation works
- What each check validates
- How to interpret results
- How to fix violations
- Performance considerations

**2. Error Reference**
- All violation types with examples
- Severity level explanations
- Recommended fixes for each error
- Common edge cases

**3. Configuration Guide**
- How to enable/disable safety checks
- Timeout configuration
- Severity threshold configuration
- Database-specific settings

### Developer Documentation

**1. Architecture Documentation**
- System design overview
- Component interactions
- Database-specific implementations
- Extension points for new databases

**2. API Reference**
- SafetyCheckResult API
- BaseSafetyValidator API
- PostgreSQLSafetyValidator API
- SQLiteSafetyValidator API
- ProductionSafetyValidator API

**3. Contribution Guide**
- How to add new validation checks
- How to add new database support
- Testing requirements
- Code review checklist

---

## Relevant Files and Code Snippets

### Key Integration Point
**File**: `src/dataflow/migrations/complete_rename_orchestrator.py`
**Lines**: 410-415 (mock checks), 581-583 (mock function)

**Current Implementation (TO REPLACE)**:
```python
# Production safety validation
if workflow.enable_production_safety_checks:
    result.production_safety_validated = True
    result.safety_check_results = {
        "schema_integrity": self._mock_safety_check(True),
        "application_compatibility": self._mock_safety_check(True),
    }

def _mock_safety_check(self, passed: bool) -> Any:
    """Create mock safety check result."""
    return type("MockSafetyCheck", (), {"passed": passed})()
```

### Existing Schema Introspection Examples

**Foreign Key Query** (from table_rename_analyzer.py:426-451):
```python
fk_query = """
SELECT DISTINCT
    tc.constraint_name,
    tc.table_name as source_table,
    kcu.column_name as source_column,
    ccu.table_name AS target_table,
    ccu.column_name AS target_column,
    rc.delete_rule,
    rc.update_rule,
    pg_get_constraintdef(pgc.oid) as constraint_definition
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints AS rc
    ON tc.constraint_name = rc.constraint_name
JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND ccu.table_name = $1
"""
```

**View Query** (from table_rename_analyzer.py:556-588):
```python
view_query = """
SELECT
    viewname,
    definition,
    schemaname,
    false as is_materialized
FROM pg_views
WHERE schemaname = 'public'
    AND definition ILIKE '%' || $1 || '%'

UNION ALL

SELECT
    matviewname as viewname,
    definition,
    schemaname,
    true as is_materialized
FROM pg_matviews
WHERE schemaname = 'public'
    AND definition ILIKE '%' || $1 || '%'
"""
```

---

## Conclusion

This requirements analysis establishes a comprehensive foundation for implementing production-ready safety validation in DataFlow's migration orchestration system. The proposed solution replaces dangerous hardcoded mock checks with real database introspection, providing critical data protection for production deployments while maintaining acceptable performance and usability.

**Key Success Factors**:
1. Real database validation (NO MOCKING in implementation)
2. Clear severity levels (CRITICAL blocks, WARNING allows)
3. Detailed error reporting with actionable recommendations
4. Multi-database support (PostgreSQL + SQLite)
5. Performance optimization (<5 seconds for typical schemas)
6. Comprehensive testing with real databases

**Critical to Remember**:
- Current mock checks ALWAYS PASS → critical data corruption risk
- Must validate FK constraints, indexes, views, triggers
- Must work with PostgreSQL AND SQLite
- Must provide detailed error messages
- Must complete quickly (<5 seconds for most cases)
- Must integrate cleanly with CompleteRenameOrchestrator

---

**Document Version**: 1.0
**Date**: 2025-10-20
**Status**: APPROVED for implementation
**Related ADR**: ADR-016-production-safety-validation-system.md
