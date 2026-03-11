"""
Safe Type Converter for Column Datatype Migration.

This module provides safe, multi-step conversion processes for complex datatype changes,
integrating with the Data Validation Engine and Migration Orchestration Engine.

Key Features:
- Multi-step conversion process for complex type changes
- Type compatibility matrix for decision making
- Query impact analysis for existing queries
- Safe conversion strategies with rollback capability
- Integration with DataFlow's PostgreSQL execution model
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.runtime import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from .data_validation_engine import (
    DataValidationEngine,
    ValidationResult,
    ValidationSeverity,
)
from .orchestration_engine import (
    Migration,
    MigrationOperation,
    MigrationOrchestrationEngine,
    MigrationType,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class ConversionStrategy(Enum):
    """Strategies for type conversion."""

    DIRECT = "direct"  # Direct ALTER COLUMN TYPE
    MULTI_STEP = "multi_step"  # Multiple operations with temp columns
    REBUILD_TABLE = "rebuild_table"  # Create new table and migrate data
    MANUAL_INTERVENTION = "manual"  # Requires manual data cleanup


class ConversionRisk(Enum):
    """Risk levels for type conversions."""

    SAFE = "safe"  # No data loss risk
    LOW_RISK = "low_risk"  # Minimal risk, reversible
    MEDIUM_RISK = "medium_risk"  # Some risk, partial reversibility
    HIGH_RISK = "high_risk"  # High risk, limited reversibility
    DESTRUCTIVE = "destructive"  # Permanent data loss possible


@dataclass
class TypeCompatibility:
    """Compatibility information between two types."""

    old_type: str
    new_type: str
    risk_level: ConversionRisk
    strategy: ConversionStrategy
    requires_validation: bool = True
    supports_rollback: bool = True
    notes: Optional[str] = None


@dataclass
class ConversionStep:
    """A single step in the conversion process."""

    operation: str
    sql_template: str
    risk_level: RiskLevel
    rollback_sql: Optional[str] = None
    validation_query: Optional[str] = None
    description: str = ""


@dataclass
class ConversionPlan:
    """Complete plan for type conversion."""

    table_name: str
    column_name: str
    old_type: str
    new_type: str
    strategy: ConversionStrategy
    steps: List[ConversionStep]
    estimated_time_ms: int
    validation_result: Optional[ValidationResult] = None
    risk_assessment: ConversionRisk = ConversionRisk.MEDIUM_RISK


@dataclass
class ConversionResult:
    """Result of type conversion execution."""

    success: bool
    plan: ConversionPlan
    executed_steps: int
    execution_time_ms: int
    error_message: Optional[str] = None
    rollback_performed: bool = False


@dataclass
class QueryImpact:
    """Impact assessment for existing queries."""

    query_type: str
    impact_level: str  # "none", "warning", "breaking"
    description: str
    affected_operations: List[str] = field(default_factory=list)
    mitigation_suggestions: List[str] = field(default_factory=list)


class TypeCompatibilityMatrix:
    """
    Matrix defining compatibility rules between PostgreSQL types.

    This class encapsulates the logic for determining how to safely convert
    between different PostgreSQL data types, including risk assessment and
    conversion strategies.
    """

    def __init__(self):
        """Initialize the type compatibility matrix."""
        self._compatibility_rules = self._build_compatibility_matrix()

        logger.info("Type Compatibility Matrix initialized with PostgreSQL rules")

    def get_compatibility(self, old_type: str, new_type: str) -> TypeCompatibility:
        """
        Get compatibility information for a type conversion.

        Args:
            old_type: Source type
            new_type: Target type

        Returns:
            TypeCompatibility with conversion details
        """
        old_norm = self._normalize_type(old_type)
        new_norm = self._normalize_type(new_type)

        # Check direct compatibility
        key = (old_norm, new_norm)
        if key in self._compatibility_rules:
            return self._compatibility_rules[key]

        # Check category-based compatibility
        category_compat = self._check_category_compatibility(old_norm, new_norm)
        if category_compat:
            return category_compat

        # Default to high-risk manual conversion
        return TypeCompatibility(
            old_type=old_type,
            new_type=new_type,
            risk_level=ConversionRisk.HIGH_RISK,
            strategy=ConversionStrategy.MANUAL_INTERVENTION,
            requires_validation=True,
            supports_rollback=False,
            notes=f"No predefined conversion rule for {old_type} -> {new_type}",
        )

    def _build_compatibility_matrix(self) -> Dict[Tuple[str, str], TypeCompatibility]:
        """Build the complete compatibility matrix."""
        rules = {}

        # Safe numeric conversions (widening)
        safe_numeric_widenings = [
            ("smallint", "integer"),
            ("integer", "bigint"),
            ("real", "double precision"),
            ("integer", "numeric"),
            ("smallint", "numeric"),
            ("bigint", "numeric"),
        ]

        for old, new in safe_numeric_widenings:
            rules[(old, new)] = TypeCompatibility(
                old_type=old,
                new_type=new,
                risk_level=ConversionRisk.SAFE,
                strategy=ConversionStrategy.DIRECT,
                requires_validation=False,
                supports_rollback=True,
                notes="Safe widening conversion",
            )

        # Risky numeric conversions (narrowing)
        risky_numeric_narrowings = [
            ("bigint", "integer"),
            ("integer", "smallint"),
            ("double precision", "real"),
            ("numeric", "integer"),
            ("double precision", "integer"),
            ("real", "integer"),
        ]

        for old, new in risky_numeric_narrowings:
            rules[(old, new)] = TypeCompatibility(
                old_type=old,
                new_type=new,
                risk_level=ConversionRisk.MEDIUM_RISK,
                strategy=ConversionStrategy.MULTI_STEP,
                requires_validation=True,
                supports_rollback=True,
                notes="Potential precision/range loss",
            )

        # String type conversions
        string_conversions = [
            ("text", "varchar"),
            ("varchar", "text"),
            ("char", "varchar"),
            ("char", "text"),
        ]

        for old, new in string_conversions:
            risk = (
                ConversionRisk.LOW_RISK if new == "text" else ConversionRisk.MEDIUM_RISK
            )
            rules[(old, new)] = TypeCompatibility(
                old_type=old,
                new_type=new,
                risk_level=risk,
                strategy=ConversionStrategy.DIRECT,
                requires_validation=True,
                supports_rollback=True,
                notes="String type conversion",
            )

        # Text to typed conversions (high risk)
        text_to_typed = [
            ("text", "integer"),
            ("text", "bigint"),
            ("text", "numeric"),
            ("text", "date"),
            ("text", "timestamp"),
            ("text", "boolean"),
            ("varchar", "integer"),
            ("varchar", "date"),
            ("varchar", "timestamp"),
        ]

        for old, new in text_to_typed:
            rules[(old, new)] = TypeCompatibility(
                old_type=old,
                new_type=new,
                risk_level=ConversionRisk.HIGH_RISK,
                strategy=ConversionStrategy.MULTI_STEP,
                requires_validation=True,
                supports_rollback=True,
                notes="Format validation required",
            )

        # Boolean conversions
        boolean_conversions = [
            ("boolean", "text"),
            ("boolean", "varchar"),
            ("integer", "boolean"),
            ("text", "boolean"),
        ]

        for old, new in boolean_conversions:
            rules[(old, new)] = TypeCompatibility(
                old_type=old,
                new_type=new,
                risk_level=ConversionRisk.MEDIUM_RISK,
                strategy=ConversionStrategy.MULTI_STEP,
                requires_validation=True,
                supports_rollback=True,
                notes="Boolean conversion with format validation",
            )

        return rules

    def _check_category_compatibility(
        self, old_type: str, new_type: str
    ) -> Optional[TypeCompatibility]:
        """Check compatibility based on type categories."""

        numeric_types = {
            "smallint",
            "integer",
            "bigint",
            "real",
            "double precision",
            "numeric",
            "decimal",
        }
        string_types = {"text", "varchar", "char"}
        datetime_types = {"date", "timestamp", "timestamptz", "time"}

        # Within same category
        if old_type in numeric_types and new_type in numeric_types:
            return TypeCompatibility(
                old_type=old_type,
                new_type=new_type,
                risk_level=ConversionRisk.MEDIUM_RISK,
                strategy=ConversionStrategy.MULTI_STEP,
                requires_validation=True,
                notes="Numeric category conversion",
            )

        if old_type in string_types and new_type in string_types:
            return TypeCompatibility(
                old_type=old_type,
                new_type=new_type,
                risk_level=ConversionRisk.LOW_RISK,
                strategy=ConversionStrategy.DIRECT,
                requires_validation=True,
                notes="String category conversion",
            )

        # Cross-category conversions are high risk
        return None

    def _normalize_type(self, type_name: str) -> str:
        """Normalize type name for matrix lookup."""
        type_name = type_name.lower().strip()

        # Remove size specifications
        type_name = re.sub(r"\([^)]*\)", "", type_name)

        # Handle aliases
        type_aliases = {
            "int4": "integer",
            "int8": "bigint",
            "int2": "smallint",
            "float4": "real",
            "float8": "double precision",
            "bool": "boolean",
        }

        return type_aliases.get(type_name, type_name)


class QueryImpactAnalyzer:
    """
    Analyzer for assessing query compatibility impact of type changes.

    This class analyzes potential impacts on existing queries when column
    types are changed, helping to identify breaking changes before migration.
    """

    def __init__(self, connection_string: str):
        """
        Initialize the Query Impact Analyzer.

        Args:
            connection_string: PostgreSQL connection string
        """
        self.connection_string = connection_string

        # ✅ FIX: Detect async context and use appropriate runtime
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "QueryImpactAnalyzer: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug(
                "QueryImpactAnalyzer: Detected sync context, using LocalRuntime"
            )

        logger.info("Query Impact Analyzer initialized")

    async def analyze_query_impact(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> List[QueryImpact]:
        """
        Analyze potential impact on queries from type conversion.

        Args:
            table_name: Name of the table
            column_name: Name of the column
            old_type: Current type
            new_type: Target type

        Returns:
            List of QueryImpact assessments
        """
        impacts = []

        try:
            # Analyze different query operation impacts
            impacts.extend(await self._analyze_comparison_impacts(old_type, new_type))
            impacts.extend(await self._analyze_function_impacts(old_type, new_type))
            impacts.extend(
                await self._analyze_index_impacts(
                    table_name, column_name, old_type, new_type
                )
            )
            impacts.extend(
                await self._analyze_constraint_impacts(
                    table_name, column_name, old_type, new_type
                )
            )

            logger.debug(
                f"Query impact analysis completed: {len(impacts)} potential impacts"
            )

        except Exception as e:
            logger.error(f"Query impact analysis failed: {e}")
            impacts.append(
                QueryImpact(
                    query_type="analysis_error",
                    impact_level="warning",
                    description=f"Could not complete impact analysis: {str(e)}",
                    mitigation_suggestions=["Manual review recommended"],
                )
            )

        return impacts

    async def _analyze_comparison_impacts(
        self, old_type: str, new_type: str
    ) -> List[QueryImpact]:
        """Analyze impact on comparison operations."""
        impacts = []

        old_norm = self._normalize_type(old_type)
        new_norm = self._normalize_type(new_type)

        # String to numeric conversion impacts
        if old_norm in ["text", "varchar", "char"] and new_norm in [
            "integer",
            "bigint",
            "numeric",
        ]:
            impacts.append(
                QueryImpact(
                    query_type="comparison",
                    impact_level="breaking",
                    description="String comparisons will behave differently after conversion to numeric type",
                    affected_operations=[
                        "WHERE clauses",
                        "ORDER BY",
                        "LIKE operations",
                    ],
                    mitigation_suggestions=[
                        "Review all WHERE clauses using this column",
                        "Update LIKE operations to use CAST() for string representation",
                        "Check ORDER BY clauses for sort order changes",
                    ],
                )
            )

        # Numeric precision changes
        if old_norm in ["double precision", "real"] and new_norm in [
            "integer",
            "bigint",
        ]:
            impacts.append(
                QueryImpact(
                    query_type="comparison",
                    impact_level="warning",
                    description="Decimal comparisons will change behavior after conversion to integer",
                    affected_operations=["Equality comparisons", "Range queries"],
                    mitigation_suggestions=[
                        "Review queries using decimal values for comparison",
                        "Consider using ROUND() or FLOOR() functions",
                    ],
                )
            )

        return impacts

    async def _analyze_function_impacts(
        self, old_type: str, new_type: str
    ) -> List[QueryImpact]:
        """Analyze impact on function calls."""
        impacts = []

        old_norm = self._normalize_type(old_type)
        new_norm = self._normalize_type(new_type)

        # String function impacts
        if old_norm in ["text", "varchar", "char"] and new_norm not in [
            "text",
            "varchar",
            "char",
        ]:
            impacts.append(
                QueryImpact(
                    query_type="string_functions",
                    impact_level="breaking",
                    description="String functions will no longer work after type conversion",
                    affected_operations=[
                        "LENGTH()",
                        "SUBSTRING()",
                        "UPPER()",
                        "LOWER()",
                        "LIKE",
                        "REGEXP",
                    ],
                    mitigation_suggestions=[
                        "Replace string functions with appropriate type-specific functions",
                        "Use CAST() to convert back to string for string operations",
                        "Review all string manipulation queries",
                    ],
                )
            )

        # Date function impacts
        if old_norm in ["date", "timestamp"] and new_norm not in [
            "date",
            "timestamp",
            "timestamptz",
        ]:
            impacts.append(
                QueryImpact(
                    query_type="date_functions",
                    impact_level="breaking",
                    description="Date/time functions will no longer work after type conversion",
                    affected_operations=[
                        "DATE_PART()",
                        "EXTRACT()",
                        "AGE()",
                        "DATE arithmetic",
                    ],
                    mitigation_suggestions=[
                        "Update queries to use appropriate functions for new type",
                        "Consider using CAST() for date operations if needed",
                    ],
                )
            )

        return impacts

    async def _analyze_index_impacts(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> List[QueryImpact]:
        """Analyze impact on indexes."""
        impacts = []

        try:
            # Query for existing indexes on the column
            index_query = f"""
            SELECT
                indexname,
                indexdef
            FROM pg_indexes
            WHERE tablename = '{table_name}'
            AND indexdef LIKE '%{column_name}%'
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "check_indexes",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": index_query,
                },
            )

            # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())

            if "check_indexes" in results and not results["check_indexes"].get("error"):
                indexes = results["check_indexes"].get("rows", [])

                if indexes:
                    impacts.append(
                        QueryImpact(
                            query_type="indexes",
                            impact_level="warning",
                            description=f"Found {len(indexes)} indexes that may be affected by type change",
                            affected_operations=["Query performance", "Index scans"],
                            mitigation_suggestions=[
                                "Indexes may need to be rebuilt after type conversion",
                                "Monitor query performance after migration",
                                f"Consider recreating indexes: {[idx['indexname'] for idx in indexes]}",
                            ],
                        )
                    )

        except Exception as e:
            logger.warning(f"Could not analyze index impacts: {e}")

        return impacts

    async def _analyze_constraint_impacts(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> List[QueryImpact]:
        """Analyze impact on constraints."""
        impacts = []

        try:
            # Query for constraints on the column
            constraint_query = f"""
            SELECT
                conname,
                contype,
                pg_get_constraintdef(oid) as definition
            FROM pg_constraint
            WHERE conrelid = '{table_name}'::regclass
            AND conkey @> ARRAY[(
                SELECT attnum
                FROM pg_attribute
                WHERE attrelid = '{table_name}'::regclass
                AND attname = '{column_name}'
            )]
            """

            workflow = WorkflowBuilder()
            workflow.add_node(
                "AsyncSQLDatabaseNode",
                "check_constraints",
                {
                    "connection_string": self.connection_string,
                    "database_type": self.database_type,
                    "query": constraint_query,
                },
            )

            # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
            init_runtime = LocalRuntime()
            results, _ = init_runtime.execute(workflow.build())

            if "check_constraints" in results and not results["check_constraints"].get(
                "error"
            ):
                constraints = results["check_constraints"].get("rows", [])

                if constraints:
                    impacts.append(
                        QueryImpact(
                            query_type="constraints",
                            impact_level="breaking",
                            description=f"Found {len(constraints)} constraints that may conflict with type change",
                            affected_operations=[
                                "Data validation",
                                "INSERT/UPDATE operations",
                            ],
                            mitigation_suggestions=[
                                "Review constraint definitions for compatibility",
                                "May need to drop and recreate constraints",
                                f"Affected constraints: {[c['conname'] for c in constraints]}",
                            ],
                        )
                    )

        except Exception as e:
            logger.warning(f"Could not analyze constraint impacts: {e}")

        return impacts

    def _normalize_type(self, type_name: str) -> str:
        """Normalize type name for analysis."""
        return re.sub(r"\([^)]*\)", "", type_name.lower().strip())


class SafeTypeConverter:
    """
    Main class for safe column type conversions.

    This class orchestrates the entire type conversion process, from validation
    through execution, using the Migration Orchestration Engine for safety.
    """

    def __init__(
        self,
        connection_string: str,
        orchestration_engine: Optional[MigrationOrchestrationEngine] = None,
    ):
        """
        Initialize the Safe Type Converter.

        Args:
            connection_string: PostgreSQL connection string
            orchestration_engine: Optional existing orchestration engine
        """
        self.connection_string = connection_string
        self.orchestration_engine = orchestration_engine

        # Detect database type for AsyncSQLDatabaseNode
        from ..adapters.connection_parser import ConnectionParser

        self.database_type = ConnectionParser.detect_database_type(connection_string)

        # Initialize components
        self.data_validator = DataValidationEngine(connection_string)
        self.compatibility_matrix = TypeCompatibilityMatrix()
        self.query_analyzer = QueryImpactAnalyzer(connection_string)

        # ✅ FIX: Detect async context and use appropriate runtime
        try:
            asyncio.get_running_loop()
            # Running in async context - use AsyncLocalRuntime
            self.runtime = AsyncLocalRuntime()
            self._is_async = True
            logger.debug(
                "SafeTypeConverter: Detected async context, using AsyncLocalRuntime"
            )
        except RuntimeError:
            # No event loop - use sync LocalRuntime
            self.runtime = LocalRuntime()
            self._is_async = False
            logger.debug("SafeTypeConverter: Detected sync context, using LocalRuntime")

        logger.info("Safe Type Converter initialized")

    async def convert_column_type_safe(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> ConversionResult:
        """
        Safely convert a column type with comprehensive validation and rollback.

        Args:
            table_name: Name of the table
            column_name: Name of the column
            old_type: Current column type
            new_type: Target column type

        Returns:
            ConversionResult with execution details
        """
        start_time = datetime.now()

        try:
            logger.info(
                f"Starting safe type conversion: {table_name}.{column_name} {old_type} -> {new_type}"
            )

            # Step 1: Create conversion plan
            plan = await self.create_conversion_plan(
                table_name, column_name, old_type, new_type
            )

            if not plan:
                return ConversionResult(
                    success=False,
                    plan=None,
                    executed_steps=0,
                    execution_time_ms=0,
                    error_message="Could not create conversion plan",
                )

            # Step 2: Execute conversion plan
            if plan.strategy == ConversionStrategy.MANUAL_INTERVENTION:
                return ConversionResult(
                    success=False,
                    plan=plan,
                    executed_steps=0,
                    execution_time_ms=0,
                    error_message="Manual intervention required - conversion blocked",
                )

            # Step 3: Execute using orchestration engine if available
            if self.orchestration_engine:
                result = await self._execute_with_orchestration(plan)
            else:
                result = self._execute_direct(plan)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            result.execution_time_ms = execution_time

            if result.success:
                logger.info(
                    f"Type conversion completed successfully in {execution_time}ms"
                )
            else:
                logger.error(
                    f"Type conversion failed after {execution_time}ms: {result.error_message}"
                )

            return result

        except Exception as e:
            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"Type conversion failed with exception: {e}")

            return ConversionResult(
                success=False,
                plan=None,
                executed_steps=0,
                execution_time_ms=execution_time,
                error_message=str(e),
            )

    async def create_conversion_plan(
        self, table_name: str, column_name: str, old_type: str, new_type: str
    ) -> Optional[ConversionPlan]:
        """Create a detailed conversion plan with validation and impact analysis."""

        try:
            # Step 1: Check type compatibility
            compatibility = self.compatibility_matrix.get_compatibility(
                old_type, new_type
            )

            # Step 2: Validate data if required
            validation_result = None
            if compatibility.requires_validation:
                validation_result = await self.data_validator.validate_type_conversion(
                    table_name, column_name, old_type, new_type
                )

                # Block conversion if critical issues found
                if not validation_result.is_compatible:
                    logger.warning("Validation failed - blocking conversion")
                    compatibility.strategy = ConversionStrategy.MANUAL_INTERVENTION

            # Step 3: Analyze query impact
            query_impacts = await self.query_analyzer.analyze_query_impact(
                table_name, column_name, old_type, new_type
            )

            # Step 4: Generate conversion steps based on strategy
            steps = self._generate_conversion_steps(
                table_name,
                column_name,
                old_type,
                new_type,
                compatibility,
                validation_result,
            )

            # Step 5: Estimate execution time
            estimated_time = self._estimate_total_conversion_time(
                steps, validation_result
            )

            plan = ConversionPlan(
                table_name=table_name,
                column_name=column_name,
                old_type=old_type,
                new_type=new_type,
                strategy=compatibility.strategy,
                steps=steps,
                estimated_time_ms=estimated_time,
                validation_result=validation_result,
                risk_assessment=compatibility.risk_level,
            )

            logger.info(
                f"Conversion plan created: {compatibility.strategy.value} strategy with {len(steps)} steps"
            )

            return plan

        except Exception as e:
            logger.error(f"Failed to create conversion plan: {e}")
            return None

    def _generate_conversion_steps(
        self,
        table_name: str,
        column_name: str,
        old_type: str,
        new_type: str,
        compatibility: TypeCompatibility,
        validation_result: Optional[ValidationResult],
    ) -> List[ConversionStep]:
        """Generate specific conversion steps based on strategy."""

        steps = []

        if compatibility.strategy == ConversionStrategy.DIRECT:
            # Direct ALTER COLUMN TYPE
            steps.append(
                ConversionStep(
                    operation="alter_column_type",
                    sql_template=f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE {new_type}',
                    risk_level=(
                        RiskLevel.LOW
                        if compatibility.risk_level == ConversionRisk.SAFE
                        else RiskLevel.MEDIUM
                    ),
                    rollback_sql=f'ALTER TABLE "{table_name}" ALTER COLUMN "{column_name}" TYPE {old_type}',
                    description=f"Direct conversion from {old_type} to {new_type}",
                )
            )

        elif compatibility.strategy == ConversionStrategy.MULTI_STEP:
            # Multi-step conversion with temporary column
            temp_column = f"{column_name}_temp_{int(datetime.now().timestamp())}"

            # Step 1: Add temporary column
            steps.append(
                ConversionStep(
                    operation="add_temp_column",
                    sql_template=f'ALTER TABLE "{table_name}" ADD COLUMN "{temp_column}" {new_type}',
                    risk_level=RiskLevel.LOW,
                    rollback_sql=f'ALTER TABLE "{table_name}" DROP COLUMN "{temp_column}"',
                    description=f"Add temporary column {temp_column}",
                )
            )

            # Step 2: Populate temporary column with converted data
            conversion_expr = self._get_conversion_expression(
                column_name, old_type, new_type
            )
            steps.append(
                ConversionStep(
                    operation="populate_temp_column",
                    sql_template=f'UPDATE "{table_name}" SET "{temp_column}" = {conversion_expr}',
                    risk_level=RiskLevel.MEDIUM,
                    validation_query=f'SELECT COUNT(*) FROM "{table_name}" WHERE "{temp_column}" IS NULL AND "{column_name}" IS NOT NULL',
                    description="Populate temporary column with converted data",
                )
            )

            # Step 3: Drop original column
            steps.append(
                ConversionStep(
                    operation="drop_original_column",
                    sql_template=f'ALTER TABLE "{table_name}" DROP COLUMN "{column_name}"',
                    risk_level=RiskLevel.HIGH,
                    description="Drop original column",
                )
            )

            # Step 4: Rename temporary column
            steps.append(
                ConversionStep(
                    operation="rename_temp_column",
                    sql_template=f'ALTER TABLE "{table_name}" RENAME COLUMN "{temp_column}" TO "{column_name}"',
                    risk_level=RiskLevel.LOW,
                    rollback_sql=f'ALTER TABLE "{table_name}" RENAME COLUMN "{column_name}" TO "{temp_column}"',
                    description="Rename temporary column to original name",
                )
            )

        elif compatibility.strategy == ConversionStrategy.REBUILD_TABLE:
            # Full table rebuild (for complex conversions)
            temp_table = f"{table_name}_temp_{int(datetime.now().timestamp())}"

            steps.append(
                ConversionStep(
                    operation="create_temp_table",
                    sql_template=f'CREATE TABLE "{temp_table}" AS SELECT * FROM "{table_name}" WHERE 1=0',
                    risk_level=RiskLevel.LOW,
                    rollback_sql=f'DROP TABLE IF EXISTS "{temp_table}"',
                    description="Create temporary table with new schema",
                )
            )

            # Additional steps would be added for full rebuild...

        return steps

    def _get_conversion_expression(
        self, column_name: str, old_type: str, new_type: str
    ) -> str:
        """Get SQL expression for converting between types."""

        old_norm = self.compatibility_matrix._normalize_type(old_type)
        new_norm = self.compatibility_matrix._normalize_type(new_type)

        # Text to numeric conversions
        if old_norm in ["text", "varchar", "char"] and new_norm in [
            "integer",
            "bigint",
            "numeric",
        ]:
            return f'CASE WHEN "{column_name}" ~ \'^-?[0-9]+\.?[0-9]*$\' THEN CAST("{column_name}" AS {new_type}) ELSE NULL END'

        # Text to date conversions
        if old_norm in ["text", "varchar", "char"] and new_norm in [
            "date",
            "timestamp",
        ]:
            return f'CASE WHEN "{column_name}" ~ \'^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}\' THEN CAST("{column_name}" AS {new_type}) ELSE NULL END'

        # Default: direct cast
        return f'CAST("{column_name}" AS {new_type})'

    def _estimate_total_conversion_time(
        self, steps: List[ConversionStep], validation_result: Optional[ValidationResult]
    ) -> int:
        """Estimate total conversion time for all steps."""

        # Base time per step
        total_time = len(steps) * 1000  # 1 second per step base

        # Add validation time if available
        if validation_result:
            total_time += validation_result.estimated_conversion_time_ms

        # Add complexity factors for high-risk steps
        for step in steps:
            if step.risk_level == RiskLevel.HIGH:
                total_time += 5000  # Extra 5 seconds for high-risk operations
            elif step.risk_level == RiskLevel.MEDIUM:
                total_time += 2000  # Extra 2 seconds for medium-risk operations

        return min(total_time, 300000)  # Cap at 5 minutes

    async def _execute_with_orchestration(
        self, plan: ConversionPlan
    ) -> ConversionResult:
        """Execute conversion plan using the Migration Orchestration Engine."""

        if not self.orchestration_engine:
            raise Exception("Orchestration engine not available")

        # Convert ConversionPlan to Migration
        operations = []
        for step in plan.steps:
            operations.append(
                MigrationOperation(
                    operation_type=MigrationType.MODIFY_COLUMN,
                    table_name=plan.table_name,
                    metadata={
                        "column_name": plan.column_name,
                        "old_type": plan.old_type,
                        "new_type": plan.new_type,
                        "step_operation": step.operation,
                        "sql": step.sql_template,
                    },
                    rollback_sql=step.rollback_sql,
                )
            )

        migration = Migration(
            operations=operations,
            version=f"type_conversion_{plan.table_name}_{plan.column_name}_{int(datetime.now().timestamp())}",
            risk_level=(
                RiskLevel.MEDIUM
                if plan.risk_assessment == ConversionRisk.MEDIUM_RISK
                else RiskLevel.HIGH
            ),
        )

        # Execute through orchestration engine
        migration_result = await self.orchestration_engine.execute_migration(migration)

        return ConversionResult(
            success=migration_result.success,
            plan=plan,
            executed_steps=migration_result.executed_operations,
            execution_time_ms=migration_result.execution_time_ms,
            error_message=migration_result.error_message,
        )

    def _execute_direct(self, plan: ConversionPlan) -> ConversionResult:
        """Execute conversion plan directly without orchestration engine."""

        executed_steps = 0

        try:
            for i, step in enumerate(plan.steps):
                logger.debug(
                    f"Executing step {i+1}/{len(plan.steps)}: {step.description}"
                )

                # Execute step SQL
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "AsyncSQLDatabaseNode",
                    f"step_{i+1}",
                    {
                        "connection_string": self.connection_string,
                        "database_type": self.database_type,
                        "query": step.sql_template,
                        "validate_queries": False,
                    },
                )

                # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
                init_runtime = LocalRuntime()
                results, _ = init_runtime.execute(workflow.build())
                node_id = f"step_{i+1}"

                if node_id not in results or results[node_id].get("error"):
                    error_msg = results.get(node_id, {}).get("error", "Unknown error")
                    logger.error(f"Step {i+1} failed: {error_msg}")

                    return ConversionResult(
                        success=False,
                        plan=plan,
                        executed_steps=executed_steps,
                        execution_time_ms=0,
                        error_message=f"Step {i+1} failed: {error_msg}",
                    )

                executed_steps += 1

                # Run validation query if provided
                if step.validation_query:
                    validation_workflow = WorkflowBuilder()
                    validation_workflow.add_node(
                        "AsyncSQLDatabaseNode",
                        "validation",
                        {
                            "connection_string": self.connection_string,
                            "database_type": self.database_type,
                            "query": step.validation_query,
                        },
                    )

                    # ✅ FIX: Use LocalRuntime for migration operations to avoid async context issues
                    init_runtime = LocalRuntime()
                    val_results, _ = init_runtime.execute(validation_workflow.build())
                    if "validation" in val_results:
                        val_data = val_results["validation"]
                        if val_data.get("rows") and len(val_data["rows"]) > 0:
                            count = val_data["rows"][0].get("count", 0)
                            if count > 0:
                                logger.warning(
                                    f"Validation found {count} potential issues after step {i+1}"
                                )

            return ConversionResult(
                success=True,
                plan=plan,
                executed_steps=executed_steps,
                execution_time_ms=0,
                error_message=None,
            )

        except Exception as e:
            logger.error(f"Direct execution failed: {e}")

            return ConversionResult(
                success=False,
                plan=plan,
                executed_steps=executed_steps,
                execution_time_ms=0,
                error_message=str(e),
            )
