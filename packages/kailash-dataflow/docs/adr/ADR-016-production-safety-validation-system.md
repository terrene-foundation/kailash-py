# ADR-016: Production Safety Validation System for Migration Orchestration

## Status
**PROPOSED** - Implementation Priority: CRITICAL

## Context

### Problem Statement
The CompleteRenameOrchestrator currently uses hardcoded mock safety checks that **always pass**, creating critical data corruption risks in production deployments:

**Current Implementation (Lines 410-415, 581-583)**:
```python
# Production safety validation
if workflow.enable_production_safety_checks:
    result.production_safety_validated = True
    result.safety_check_results = {
        "schema_integrity": self._mock_safety_check(True),  # ❌ Always passes!
        "application_compatibility": self._mock_safety_check(True),  # ❌ Always passes!
    }

def _mock_safety_check(self, passed: bool) -> Any:
    """Create mock safety check result."""
    return type("MockSafetyCheck", (), {"passed": passed})()
```

### Critical Risks
1. **Schema Integrity Failures Undetected**: Foreign key constraints, unique indexes, check constraints may become invalid after rename but checks pass
2. **Application Compatibility Breaks**: Views, triggers, functions referencing old table name will break but validation succeeds
3. **Data Corruption**: Cascade operations may execute incorrectly without validation
4. **Zero Production Safety**: No actual validation of migration safety before execution

### Business Impact
- **Production Outages**: Invalid migrations deployed to production cause system failures
- **Data Loss**: Referential integrity violations lead to data corruption
- **Customer Impact**: Application failures affect end users directly
- **Operational Cost**: Emergency rollbacks and manual fixes required

### Technical Context
- **Integration Point**: CompleteRenameOrchestrator (Phase 3 of table rename system)
- **Database Access**: connection_manager available for database queries
- **Multi-DB Support**: Must work with PostgreSQL AND SQLite
- **Performance Requirement**: <5 seconds validation for typical schemas
- **Existing Components**: TableRenameAnalyzer, RenameCoordinationEngine, ApplicationSafeRenameStrategy

## Decision

### Architecture Overview
We will implement a **comprehensive production safety validation system** with real database introspection and detailed error reporting:

```
┌──────────────────────────────────────────────┐
│      Production Safety Validation System     │
├──────────────────────────────────────────────┤
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │   Schema Integrity Validation          │ │
│  │  • Foreign Key Constraint Validation   │ │
│  │  • Unique Index Validation             │ │
│  │  • Check Constraint Validation         │ │
│  │  • Primary Key Validation              │ │
│  │  • Trigger Validation                  │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │  Application Compatibility Validation  │ │
│  │  • View Dependency Validation          │ │
│  │  • Function/Procedure Validation       │ │
│  │  • Trigger Reference Validation        │ │
│  │  • Materialized View Validation        │ │
│  │  • Sequence Ownership Validation       │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │    Database-Specific Validators        │ │
│  │  • PostgreSQL Validator                │ │
│  │  • SQLite Validator                    │ │
│  │  • Common Base Validator               │ │
│  └────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

### Core Components

#### 1. SafetyCheckResult Dataclass
```python
@dataclass
class SafetyCheckResult:
    """Result of a production safety check."""

    check_name: str
    passed: bool
    severity: SafetyCheckSeverity  # CRITICAL, HIGH, MEDIUM, LOW
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    execution_time_ms: float = 0.0

    # Database evidence
    affected_objects: List[str] = field(default_factory=list)
    sql_queries_executed: List[str] = field(default_factory=list)
```

#### 2. Safety Check Severity Levels
```python
class SafetyCheckSeverity(Enum):
    """Severity levels for safety check failures."""

    CRITICAL = "critical"  # Blocks deployment - data corruption risk
    HIGH = "high"          # Requires approval - application failure risk
    MEDIUM = "medium"      # Warning - degraded functionality risk
    LOW = "low"            # Info - best practice violation
```

#### 3. Schema Integrity Validator
```python
class SchemaIntegrityValidator:
    """Validates database schema integrity after rename."""

    async def validate_foreign_key_constraints(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate all foreign key constraints reference correct table.

        Checks:
        - All FK constraints updated to new table name
        - No broken FK references remaining
        - Cascade rules still valid
        - Referential integrity maintained
        """

    async def validate_unique_indexes(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate unique indexes after rename.

        Checks:
        - All unique indexes exist on new table
        - Index definitions correct
        - No duplicate unique constraints
        """

    async def validate_check_constraints(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate check constraints after rename.

        Checks:
        - All check constraints migrated
        - Constraint definitions valid
        - No orphaned constraints
        """
```

#### 4. Application Compatibility Validator
```python
class ApplicationCompatibilityValidator:
    """Validates application-level compatibility after rename."""

    async def validate_view_dependencies(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate views after table rename.

        Checks:
        - No views reference old table name
        - All view definitions valid
        - Materialized views refreshable
        - View dependencies resolved
        """

    async def validate_function_references(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate functions/procedures after rename.

        Checks:
        - No functions reference old table name in body
        - All function calls still valid
        - Return types correct
        """

    async def validate_trigger_references(
        self,
        old_table: str,
        new_table: str,
        connection: asyncpg.Connection
    ) -> SafetyCheckResult:
        """
        Validate triggers after rename.

        Checks:
        - All triggers on new table
        - Trigger functions valid
        - No orphaned triggers on old table
        """
```

### Implementation Strategy

#### Phase 1: Core Safety Check Infrastructure (Week 1)

**1.1 SafetyCheckResult and Base Classes**
```python
# File: src/dataflow/migrations/safety_check_result.py

@dataclass
class SafetyCheckResult:
    """Production safety check result with detailed reporting."""
    check_name: str
    passed: bool
    severity: SafetyCheckSeverity
    message: str
    # ... (full implementation)

class BaseSafetyValidator:
    """Base class for all safety validators."""

    def __init__(self, connection_manager: Any):
        self.connection_manager = connection_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection from manager."""
        return await self.connection_manager.get_connection()

    def _create_result(
        self,
        check_name: str,
        passed: bool,
        severity: SafetyCheckSeverity,
        message: str,
        **kwargs
    ) -> SafetyCheckResult:
        """Helper to create standardized results."""
        return SafetyCheckResult(
            check_name=check_name,
            passed=passed,
            severity=severity,
            message=message,
            **kwargs
        )
```

**1.2 Database Detection and Abstraction**
```python
# File: src/dataflow/migrations/database_detector.py

class DatabaseType(Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"

class DatabaseDetector:
    """Detect database type from connection."""

    @staticmethod
    async def detect_database_type(
        connection: Union[asyncpg.Connection, Any]
    ) -> DatabaseType:
        """Detect database type from connection object."""
        # Check connection type
        if isinstance(connection, asyncpg.Connection):
            return DatabaseType.POSTGRESQL
        # SQLite detection logic
        return DatabaseType.SQLITE
```

#### Phase 2: PostgreSQL Schema Integrity Validation (Week 1-2)

**2.1 Foreign Key Constraint Validation**
```python
async def validate_foreign_key_constraints(
    self,
    old_table: str,
    new_table: str,
    connection: asyncpg.Connection
) -> SafetyCheckResult:
    """Validate FK constraints after rename."""

    start_time = time.time()
    violations = []
    warnings = []
    affected_objects = []

    # Check 1: Find any FKs still referencing old table name
    orphaned_fk_query = """
    SELECT DISTINCT
        tc.constraint_name,
        tc.table_name as source_table,
        ccu.table_name AS referenced_table
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
        AND (tc.table_name = $1 OR ccu.table_name = $1)
        AND tc.table_schema = 'public'
    """

    orphaned_fks = await connection.fetch(orphaned_fk_query, old_table)

    if orphaned_fks:
        for fk in orphaned_fks:
            violations.append(
                f"FK constraint '{fk['constraint_name']}' still references old table '{old_table}'"
            )
            affected_objects.append(fk['constraint_name'])

    # Check 2: Validate all FKs on new table are valid
    new_table_fk_query = """
    SELECT DISTINCT
        tc.constraint_name,
        tc.table_name,
        pg_get_constraintdef(pgc.oid) as definition
    FROM information_schema.table_constraints AS tc
    JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
        AND (tc.table_name = $1 OR tc.constraint_name LIKE '%' || $1 || '%')
        AND tc.table_schema = 'public'
    """

    new_fks = await connection.fetch(new_table_fk_query, new_table)

    # Check 3: Validate FK definitions are syntactically correct
    for fk in new_fks:
        try:
            # Attempt to query constraint metadata to ensure it's valid
            validate_query = f"""
            SELECT convalidated FROM pg_constraint
            WHERE conname = $1
            """
            result = await connection.fetchrow(validate_query, fk['constraint_name'])

            if result and not result['convalidated']:
                warnings.append(
                    f"FK constraint '{fk['constraint_name']}' not validated"
                )
        except Exception as e:
            violations.append(
                f"FK constraint '{fk['constraint_name']}' validation failed: {e}"
            )

    execution_time = (time.time() - start_time) * 1000

    passed = len(violations) == 0
    severity = SafetyCheckSeverity.CRITICAL if not passed else SafetyCheckSeverity.LOW

    return SafetyCheckResult(
        check_name="foreign_key_constraints",
        passed=passed,
        severity=severity,
        message=f"{'✓' if passed else '✗'} FK constraint validation: {len(violations)} violations, {len(warnings)} warnings",
        violations=violations,
        warnings=warnings,
        affected_objects=affected_objects,
        execution_time_ms=execution_time,
        details={
            "total_fks_checked": len(new_fks),
            "orphaned_fks_found": len(orphaned_fks),
        }
    )
```

**2.2 Unique Index Validation**
```python
async def validate_unique_indexes(
    self,
    old_table: str,
    new_table: str,
    connection: asyncpg.Connection
) -> SafetyCheckResult:
    """Validate unique indexes after rename."""

    start_time = time.time()
    violations = []
    warnings = []

    # Check 1: Find indexes on old table (should be none)
    old_table_indexes_query = """
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename = $1 AND schemaname = 'public'
    """

    old_indexes = await connection.fetch(old_table_indexes_query, old_table)

    if old_indexes:
        for idx in old_indexes:
            violations.append(
                f"Index '{idx['indexname']}' still exists on old table '{old_table}'"
            )

    # Check 2: Validate unique indexes on new table
    new_table_indexes_query = """
    SELECT
        i.indexname,
        i.indexdef,
        ix.indisunique,
        ix.indisprimary
    FROM pg_indexes i
    JOIN pg_class t ON t.relname = i.tablename
    JOIN pg_index ix ON ix.indrelid = t.oid
    JOIN pg_class idx ON idx.oid = ix.indexrelid
    WHERE i.tablename = $1
        AND i.schemaname = 'public'
        AND ix.indisunique = true
    """

    new_indexes = await connection.fetch(new_table_indexes_query, new_table)

    # Check 3: Ensure indexes are valid
    for idx in new_indexes:
        try:
            # Check index is valid and usable
            check_query = """
            SELECT pg_index.indisvalid, pg_index.indisready
            FROM pg_index
            JOIN pg_class ON pg_class.oid = pg_index.indexrelid
            WHERE pg_class.relname = $1
            """
            result = await connection.fetchrow(check_query, idx['indexname'])

            if result and not result['indisvalid']:
                violations.append(
                    f"Unique index '{idx['indexname']}' is not valid"
                )
            if result and not result['indisready']:
                warnings.append(
                    f"Unique index '{idx['indexname']}' is not ready for queries"
                )
        except Exception as e:
            violations.append(f"Index validation failed for '{idx['indexname']}': {e}")

    execution_time = (time.time() - start_time) * 1000
    passed = len(violations) == 0

    return SafetyCheckResult(
        check_name="unique_indexes",
        passed=passed,
        severity=SafetyCheckSeverity.HIGH if not passed else SafetyCheckSeverity.LOW,
        message=f"{'✓' if passed else '✗'} Unique index validation: {len(violations)} violations",
        violations=violations,
        warnings=warnings,
        execution_time_ms=execution_time,
        details={
            "total_unique_indexes": len(new_indexes),
            "orphaned_indexes": len(old_indexes),
        }
    )
```

#### Phase 3: Application Compatibility Validation (Week 2)

**3.1 View Dependency Validation**
```python
async def validate_view_dependencies(
    self,
    old_table: str,
    new_table: str,
    connection: asyncpg.Connection
) -> SafetyCheckResult:
    """Validate views after table rename."""

    start_time = time.time()
    violations = []
    warnings = []
    affected_views = []

    # Check 1: Find views still referencing old table name
    view_check_query = """
    SELECT
        viewname,
        definition,
        schemaname
    FROM pg_views
    WHERE schemaname = 'public'
        AND (
            definition ILIKE '%' || $1 || '%'
        )
    """

    views_with_old_ref = await connection.fetch(view_check_query, old_table)

    for view in views_with_old_ref:
        # Parse view definition to check if it's a real reference
        definition = view['definition'].lower()

        # Check for table reference patterns
        if f" from {old_table} " in definition or \
           f" from {old_table}\n" in definition or \
           f" join {old_table} " in definition:
            violations.append(
                f"View '{view['viewname']}' still references old table '{old_table}'"
            )
            affected_views.append(view['viewname'])

    # Check 2: Validate views on new table are queryable
    new_table_views_query = """
    SELECT
        viewname,
        definition
    FROM pg_views
    WHERE schemaname = 'public'
        AND definition ILIKE '%' || $1 || '%'
    """

    new_table_views = await connection.fetch(new_table_views_query, new_table)

    for view in new_table_views:
        try:
            # Test view is queryable
            test_query = f"SELECT 1 FROM {view['viewname']} LIMIT 0"
            await connection.execute(test_query)
        except Exception as e:
            violations.append(
                f"View '{view['viewname']}' is not queryable: {e}"
            )

    # Check 3: Materialized views
    matview_query = """
    SELECT
        matviewname,
        definition
    FROM pg_matviews
    WHERE schemaname = 'public'
        AND (definition ILIKE '%' || $1 || '%' OR definition ILIKE '%' || $2 || '%')
    """

    matviews = await connection.fetch(matview_query, old_table, new_table)

    for matview in matviews:
        if old_table.lower() in matview['definition'].lower():
            violations.append(
                f"Materialized view '{matview['matviewname']}' references old table '{old_table}'"
            )

    execution_time = (time.time() - start_time) * 1000
    passed = len(violations) == 0

    return SafetyCheckResult(
        check_name="view_dependencies",
        passed=passed,
        severity=SafetyCheckSeverity.HIGH if not passed else SafetyCheckSeverity.LOW,
        message=f"{'✓' if passed else '✗'} View dependency validation: {len(violations)} violations",
        violations=violations,
        warnings=warnings,
        affected_objects=affected_views,
        execution_time_ms=execution_time,
        details={
            "views_checked": len(new_table_views),
            "materialized_views_checked": len(matviews),
        }
    )
```

**3.2 Trigger Validation**
```python
async def validate_trigger_references(
    self,
    old_table: str,
    new_table: str,
    connection: asyncpg.Connection
) -> SafetyCheckResult:
    """Validate triggers after rename."""

    start_time = time.time()
    violations = []
    warnings = []

    # Check 1: No triggers on old table
    old_table_triggers_query = """
    SELECT DISTINCT trigger_name, event_manipulation, action_statement
    FROM information_schema.triggers
    WHERE event_object_table = $1 AND event_object_schema = 'public'
    """

    old_triggers = await connection.fetch(old_table_triggers_query, old_table)

    if old_triggers:
        for trigger in old_triggers:
            violations.append(
                f"Trigger '{trigger['trigger_name']}' still exists on old table '{old_table}'"
            )

    # Check 2: Validate triggers on new table
    new_table_triggers_query = """
    SELECT DISTINCT trigger_name, event_manipulation, action_statement
    FROM information_schema.triggers
    WHERE event_object_table = $1 AND event_object_schema = 'public'
    """

    new_triggers = await connection.fetch(new_table_triggers_query, new_table)

    # Check 3: Validate trigger functions are valid
    for trigger in new_triggers:
        # Extract function name from action_statement
        action = trigger['action_statement']

        # Check trigger function doesn't reference old table
        if old_table.lower() in action.lower():
            violations.append(
                f"Trigger '{trigger['trigger_name']}' function still references old table '{old_table}'"
            )

    execution_time = (time.time() - start_time) * 1000
    passed = len(violations) == 0

    return SafetyCheckResult(
        check_name="trigger_references",
        passed=passed,
        severity=SafetyCheckSeverity.HIGH if not passed else SafetyCheckSeverity.LOW,
        message=f"{'✓' if passed else '✗'} Trigger validation: {len(violations)} violations",
        violations=violations,
        warnings=warnings,
        execution_time_ms=execution_time,
        details={
            "triggers_on_new_table": len(new_triggers),
            "orphaned_triggers": len(old_triggers),
        }
    )
```

#### Phase 4: SQLite Support and Integration (Week 2-3)

**4.1 SQLite Validator Implementation**
```python
class SQLiteSafetyValidator(BaseSafetyValidator):
    """SQLite-specific safety validation."""

    async def validate_foreign_key_constraints(
        self,
        old_table: str,
        new_table: str,
        connection: Any
    ) -> SafetyCheckResult:
        """Validate FK constraints for SQLite."""

        # SQLite FK validation using pragma foreign_key_list
        violations = []

        # Check new table FKs
        new_table_fks = await connection.execute(
            f"PRAGMA foreign_key_list('{new_table}')"
        )

        # Validate each FK
        for fk in new_table_fks:
            # Check referenced table exists
            table_check = await connection.fetchone(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (fk['table'],)
            )
            if not table_check:
                violations.append(
                    f"FK references non-existent table: {fk['table']}"
                )

        passed = len(violations) == 0

        return SafetyCheckResult(
            check_name="foreign_key_constraints",
            passed=passed,
            severity=SafetyCheckSeverity.CRITICAL if not passed else SafetyCheckSeverity.LOW,
            message=f"SQLite FK validation: {len(violations)} violations",
            violations=violations
        )
```

**4.2 Orchestrator Integration**
```python
# File: src/dataflow/migrations/complete_rename_orchestrator.py

from .production_safety_validator import ProductionSafetyValidator

class CompleteRenameOrchestrator:
    """Enhanced with real production safety validation."""

    def __init__(
        self,
        connection_manager: Any,
        safety_validator: Optional[ProductionSafetyValidator] = None,
        # ... existing parameters
    ):
        self.connection_manager = connection_manager
        self.safety_validator = safety_validator or ProductionSafetyValidator(
            connection_manager
        )
        # ... existing initialization

    async def _execute_orchestration_workflow(
        self, workflow: EndToEndRenameWorkflow
    ) -> OrchestratorResult:
        """Execute with real safety validation."""

        # ... existing phases ...

        # Production safety validation (REAL, not mock!)
        if workflow.enable_production_safety_checks:
            safety_results = await self._execute_production_safety_validation(
                workflow.old_table_name,
                workflow.new_table_name
            )

            result.production_safety_validated = safety_results.all_passed
            result.safety_check_results = {
                "schema_integrity": safety_results.schema_integrity_result,
                "application_compatibility": safety_results.application_compatibility_result,
            }

            # FAIL DEPLOYMENT if critical checks fail
            if not safety_results.all_passed:
                critical_failures = [
                    r for r in safety_results.all_results
                    if not r.passed and r.severity == SafetyCheckSeverity.CRITICAL
                ]

                if critical_failures:
                    result.success = False
                    result.error_message = (
                        f"Production safety validation failed with {len(critical_failures)} "
                        f"critical violations. Deployment blocked."
                    )
                    return result

        return result

    async def _execute_production_safety_validation(
        self,
        old_table: str,
        new_table: str
    ) -> "ProductionSafetyResults":
        """Execute comprehensive production safety validation."""

        start_time = time.time()

        # Run all safety validators
        schema_integrity = await self.safety_validator.validate_schema_integrity(
            old_table, new_table
        )

        app_compatibility = await self.safety_validator.validate_application_compatibility(
            old_table, new_table
        )

        execution_time = time.time() - start_time

        self.logger.info(
            f"Production safety validation completed in {execution_time:.2f}s: "
            f"Schema integrity={'PASS' if schema_integrity.passed else 'FAIL'}, "
            f"App compatibility={'PASS' if app_compatibility.passed else 'FAIL'}"
        )

        return ProductionSafetyResults(
            schema_integrity_result=schema_integrity,
            application_compatibility_result=app_compatibility,
            total_execution_time=execution_time
        )
```

### Database-Specific Validation Queries

#### PostgreSQL Critical Queries

**1. Foreign Key Constraint Validation**
```sql
-- Find orphaned FK constraints referencing old table
SELECT DISTINCT
    tc.constraint_name,
    tc.table_name as source_table,
    ccu.table_name AS referenced_table,
    pg_get_constraintdef(pgc.oid) as definition
FROM information_schema.table_constraints AS tc
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
    AND (tc.table_name = $1 OR ccu.table_name = $1)
    AND tc.table_schema = 'public'
```

**2. Check Constraint Validation**
```sql
-- Validate check constraints on new table
SELECT
    tc.constraint_name,
    cc.check_clause,
    pg_get_constraintdef(pgc.oid) as full_definition
FROM information_schema.table_constraints AS tc
JOIN information_schema.check_constraints AS cc
    ON cc.constraint_name = tc.constraint_name
JOIN pg_constraint pgc ON pgc.conname = tc.constraint_name
WHERE tc.table_name = $1
    AND tc.constraint_type = 'CHECK'
    AND tc.table_schema = 'public'
```

**3. View Dependency Validation**
```sql
-- Find views referencing tables
SELECT
    v.viewname,
    v.definition,
    v.schemaname,
    pg_get_viewdef(c.oid) as full_definition
FROM pg_views v
JOIN pg_class c ON c.relname = v.viewname
WHERE v.schemaname = 'public'
    AND (v.definition ILIKE '%' || $1 || '%'
         OR v.definition ILIKE '%' || $2 || '%')
```

**4. Trigger Validation**
```sql
-- Validate triggers and their functions
SELECT DISTINCT
    t.trigger_name,
    t.event_manipulation,
    t.action_statement,
    t.action_timing,
    p.proname as function_name,
    pg_get_functiondef(p.oid) as function_definition
FROM information_schema.triggers t
LEFT JOIN pg_proc p ON p.proname = SUBSTRING(t.action_statement FROM 'EXECUTE (?:PROCEDURE |FUNCTION )?([^\(]+)')
WHERE t.event_object_table = $1
    AND t.event_object_schema = 'public'
```

#### SQLite Critical Queries

**1. Foreign Key Validation**
```sql
-- SQLite uses PRAGMA for FK introspection
PRAGMA foreign_key_list('{table_name}')
-- Returns: id, seq, table, from, to, on_update, on_delete, match
```

**2. Index Validation**
```sql
-- Get indexes for table
SELECT name, sql FROM sqlite_master
WHERE type='index' AND tbl_name=?
```

**3. Trigger Validation**
```sql
-- Get triggers for table
SELECT name, sql FROM sqlite_master
WHERE type='trigger' AND tbl_name=?
```

## Consequences

### Positive Consequences

#### 1. Production Safety Dramatically Improved
- ✅ **Real Validation**: Actual database introspection replaces hardcoded mocks
- ✅ **Data Integrity Protection**: FK, unique, and check constraint validation prevents corruption
- ✅ **Application Safety**: View and trigger validation prevents runtime failures
- ✅ **Detailed Reporting**: Clear error messages guide remediation

#### 2. Developer Experience Enhanced
- ✅ **Clear Feedback**: Specific violations identified with affected objects
- ✅ **Actionable Errors**: Recommendations for fixing safety violations
- ✅ **Fast Validation**: <5 second validation for typical schemas
- ✅ **Severity Levels**: CRITICAL vs HIGH vs MEDIUM prioritization

#### 3. Operational Excellence
- ✅ **Deployment Confidence**: High confidence in migration safety
- ✅ **Reduced Incidents**: Fewer production failures from schema issues
- ✅ **Audit Trail**: Complete record of safety validations
- ✅ **Multi-DB Support**: Works with PostgreSQL AND SQLite

### Negative Consequences (Accepted Trade-offs)

#### 1. Implementation Complexity
- ❌ **Development Time**: 2-3 week implementation timeline
- ❌ **Database Expertise**: Requires deep PostgreSQL/SQLite knowledge
- ❌ **Testing Complexity**: Must test against real databases (no mocking)
- ❌ **Maintenance**: Ongoing updates for new database versions

#### 2. Performance Considerations
- ❌ **Validation Time**: 2-5 seconds added to deployment workflow
- ❌ **Database Load**: Multiple introspection queries executed
- ❌ **Connection Usage**: Requires database connection during validation

#### 3. Error Handling Requirements
- ❌ **False Positives**: May flag issues that aren't actual problems
- ❌ **Database Versions**: Different PostgreSQL versions may require adjustments
- ❌ **Permission Issues**: Requires appropriate database permissions

### Risk Mitigation Strategies

#### Technical Risks
1. **Query Performance**: Index system catalogs, limit query scope
2. **False Positives**: Provide severity levels and override mechanisms
3. **Database Compatibility**: Version detection and feature flags
4. **Connection Failures**: Graceful degradation with warnings

#### Operational Risks
1. **Breaking Deployments**: Warning severity allows deployment with non-critical issues
2. **Developer Friction**: Clear documentation and error messages
3. **Legacy Systems**: Backward compatibility mode with less strict validation

## Alternatives Considered

### Alternative 1: Keep Mock Checks
**Description**: Leave current mock implementation in place.

**Pros**:
- No development effort required
- No risk of breaking changes
- No performance impact

**Cons**:
- ❌ **Critical safety risk**: Dangerous migrations can proceed unchecked
- ❌ **Production incidents**: Will cause data corruption
- ❌ **Not production-ready**: Cannot be used safely in production

**Why Rejected**: Unacceptable data corruption risk. Mock checks provide zero safety value.

### Alternative 2: External Validation Tool
**Description**: Use external migration validation tool like sqlfluff or Liquibase.

**Pros**:
- Proven validation logic
- Maintained by external teams
- Industry standard approach

**Cons**:
- ❌ **External dependency**: Additional dependency management
- ❌ **Integration complexity**: Complex integration with DataFlow
- ❌ **Less control**: Limited customization for DataFlow needs
- ❌ **Deployment complexity**: Adds deployment dependencies

**Why Rejected**: Integrated solution provides better user experience and tighter control.

### Alternative 3: Manual Validation Only
**Description**: Require users to manually validate migrations before deployment.

**Pros**:
- No automated validation needed
- User has full control
- Simpler implementation

**Cons**:
- ❌ **Error-prone**: Human errors will occur
- ❌ **Inconsistent**: Different validation quality per user
- ❌ **Time-consuming**: Manual validation is slow
- ❌ **Not scalable**: Doesn't work for automated deployments

**Why Rejected**: Automated validation is critical for production safety and developer productivity.

### Alternative 4: Schema Diff Only
**Description**: Only validate schema matches expected state, no safety checks.

**Pros**:
- Simpler implementation
- Faster validation
- Less database expertise required

**Cons**:
- ❌ **Incomplete safety**: Doesn't catch application compatibility issues
- ❌ **Missing edge cases**: Views, triggers, functions not validated
- ❌ **False confidence**: Schema match doesn't guarantee safety

**Why Rejected**: Insufficient safety validation. Must validate application-level compatibility.

## Implementation Plan

### Phase 1: Core Infrastructure (Days 1-3)
1. **SafetyCheckResult and Base Classes** (Day 1)
   - Implement SafetyCheckResult dataclass
   - Create BaseSafetyValidator base class
   - Add SafetyCheckSeverity enum
   - Create ProductionSafetyResults container

2. **Database Detection** (Day 2)
   - Implement DatabaseDetector
   - Add database type detection logic
   - Create database-specific factory pattern

3. **Testing Infrastructure** (Day 3)
   - Set up test databases (PostgreSQL + SQLite)
   - Create test fixtures with schema objects
   - Implement test helpers

### Phase 2: PostgreSQL Validation (Days 4-7)
1. **Schema Integrity Validator** (Days 4-5)
   - Foreign key constraint validation
   - Unique index validation
   - Check constraint validation
   - Primary key validation
   - Comprehensive test coverage

2. **Application Compatibility Validator** (Days 6-7)
   - View dependency validation
   - Materialized view validation
   - Trigger reference validation
   - Function/procedure validation
   - Comprehensive test coverage

### Phase 3: SQLite Support (Days 8-10)
1. **SQLite Validator Implementation** (Days 8-9)
   - SQLite-specific FK validation
   - SQLite index validation
   - SQLite trigger validation
   - Adapt queries for SQLite system tables

2. **Cross-Database Testing** (Day 10)
   - Test validation across PostgreSQL and SQLite
   - Ensure consistent behavior
   - Performance benchmarking

### Phase 4: Integration (Days 11-14)
1. **Orchestrator Integration** (Days 11-12)
   - Replace mock checks in CompleteRenameOrchestrator
   - Add safety validator initialization
   - Implement failure handling logic
   - Update OrchestratorResult structure

2. **Error Reporting Enhancement** (Day 13)
   - Detailed error messages
   - Recommendation generation
   - Logging improvements
   - User-facing documentation

3. **End-to-End Testing** (Day 14)
   - Full workflow testing
   - Failure scenario testing
   - Performance validation
   - Documentation updates

## Success Metrics

### Technical Metrics
- **Validation Accuracy**: >95% accurate detection of safety violations
- **False Positive Rate**: <10% false positives
- **Performance**: <5 seconds for 100-table schemas
- **Coverage**: 100% of schema object types validated

### Safety Metrics
- **Production Incidents**: Zero data corruption incidents post-implementation
- **Blocked Unsafe Deployments**: Track count of blocked dangerous migrations
- **Detection Rate**: Percentage of real issues caught in staging

### User Experience Metrics
- **Error Clarity**: >90% of users can fix issues from error messages alone
- **Validation Time**: <10 seconds for 95% of validations
- **Developer Satisfaction**: Positive feedback on safety confidence

## Files Affected

### New Files
```
packages/kailash-dataflow/src/dataflow/migrations/
├── safety_check_result.py          # SafetyCheckResult dataclass and enums
├── base_safety_validator.py        # BaseSafetyValidator base class
├── production_safety_validator.py  # Main orchestrator of safety checks
├── schema_integrity_validator.py   # Schema integrity validation
├── application_compatibility_validator.py  # Application compatibility validation
├── postgresql_safety_validator.py  # PostgreSQL-specific validation
├── sqlite_safety_validator.py      # SQLite-specific validation
└── database_detector.py            # Database type detection
```

### Modified Files
```
packages/kailash-dataflow/src/dataflow/migrations/
├── complete_rename_orchestrator.py  # Remove mock checks, add real validation
└── __init__.py                      # Export new safety validation classes
```

### Test Files
```
packages/kailash-dataflow/tests/
├── unit/test_safety_check_result.py
├── unit/test_schema_integrity_validator.py
├── unit/test_application_compatibility_validator.py
├── integration/test_production_safety_validation_postgresql.py
├── integration/test_production_safety_validation_sqlite.py
└── e2e/test_complete_rename_with_safety_validation.py
```

## Review and Approval

### Technical Review Requirements
- [ ] **Architecture Review**: Core SDK team approval of safety validation architecture
- [ ] **Security Review**: Validation of database query safety
- [ ] **Performance Review**: Validation performance benchmarks approved
- [ ] **Database Team Review**: PostgreSQL and SQLite query validation

### Implementation Gates
- [ ] **Phase 1 Gate**: Base infrastructure passes all unit tests
- [ ] **Phase 2 Gate**: PostgreSQL validation achieves >95% accuracy
- [ ] **Phase 3 Gate**: SQLite validation achieves >95% accuracy
- [ ] **Production Gate**: End-to-end tests pass with real databases

---

**This ADR establishes production-ready safety validation for DataFlow's migration orchestration system, replacing dangerous hardcoded mocks with comprehensive database introspection and validation.**
