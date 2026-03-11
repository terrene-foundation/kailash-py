"""
DataFlow Query Plan Analyzer

Advanced query execution plan analysis system that examines database query
execution plans to identify optimization opportunities and performance bottlenecks.

Features:
- Multi-database execution plan parsing (PostgreSQL, MySQL, SQLite)
- Cost analysis and bottleneck identification
- Performance recommendation generation
- Optimization strategy suggestions
- Real-time execution plan monitoring
"""

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .index_recommendation_engine import IndexPriority, IndexRecommendation, IndexType
from .sql_query_optimizer import OptimizedQuery, SQLDialect

logger = logging.getLogger(__name__)


class PlanNodeType(Enum):
    """Types of execution plan nodes."""

    SEQ_SCAN = "seq_scan"
    INDEX_SCAN = "index_scan"
    INDEX_ONLY_SCAN = "index_only_scan"
    BITMAP_HEAP_SCAN = "bitmap_heap_scan"
    NESTED_LOOP = "nested_loop"
    HASH_JOIN = "hash_join"
    MERGE_JOIN = "merge_join"
    SORT = "sort"
    HASH = "hash"
    AGGREGATE = "aggregate"
    GROUP = "group"
    LIMIT = "limit"
    SUBQUERY_SCAN = "subquery_scan"
    FUNCTION_SCAN = "function_scan"
    MATERIALIZE = "materialize"
    UNIQUE = "unique"


class BottleneckType(Enum):
    """Types of performance bottlenecks."""

    SEQUENTIAL_SCAN = "sequential_scan"
    MISSING_INDEX = "missing_index"
    INEFFICIENT_JOIN = "inefficient_join"
    EXPENSIVE_SORT = "expensive_sort"
    HIGH_COST_OPERATION = "high_cost_operation"
    LARGE_RESULT_SET = "large_result_set"
    NESTED_LOOP_ISSUE = "nested_loop_issue"
    SUBQUERY_INEFFICIENCY = "subquery_inefficiency"
    MEMORY_INTENSIVE = "memory_intensive"


@dataclass
class PlanNode:
    """Represents a node in the query execution plan."""

    node_type: str
    relation_name: Optional[str]
    index_name: Optional[str]
    startup_cost: float
    total_cost: float
    plan_rows: int
    plan_width: int
    actual_time_first: Optional[float] = None
    actual_time_total: Optional[float] = None
    actual_rows: Optional[int] = None
    actual_loops: Optional[int] = None
    children: List["PlanNode"] = None
    conditions: List[str] = None
    join_type: Optional[str] = None
    sort_key: Optional[List[str]] = None

    def __post_init__(self):
        if self.children is None:
            self.children = []
        if self.conditions is None:
            self.conditions = []


@dataclass
class PerformanceBottleneck:
    """Represents a performance bottleneck in the execution plan."""

    bottleneck_type: BottleneckType
    node: PlanNode
    severity: str  # "critical", "high", "medium", "low"
    impact_description: str
    optimization_suggestions: List[str]
    estimated_improvement: str
    related_tables: List[str]
    related_columns: List[str]


@dataclass
class QueryPlanAnalysis:
    """Results from query plan analysis."""

    query_sql: str
    execution_time_ms: float
    total_cost: float
    plan_nodes: List[PlanNode]
    bottlenecks: List[PerformanceBottleneck]
    index_recommendations: List[IndexRecommendation]
    optimization_score: float  # 0-100, higher is better
    analysis_summary: str
    suggested_rewrites: List[str]


class QueryPlanAnalyzer:
    """
    Advanced query execution plan analyzer for DataFlow optimizations.

    Analyzes database query execution plans to identify performance bottlenecks,
    suggest optimizations, and recommend database improvements.

    Features:
    - Multi-database plan parsing (PostgreSQL, MySQL, SQLite)
    - Cost analysis and bottleneck detection
    - Index recommendation integration
    - Query rewrite suggestions
    - Performance scoring
    """

    def __init__(self, dialect: SQLDialect = SQLDialect.POSTGRESQL):
        self.dialect = dialect
        self.bottleneck_thresholds = self._initialize_bottleneck_thresholds()
        self.optimization_patterns = self._initialize_optimization_patterns()

    def _initialize_bottleneck_thresholds(self) -> Dict[str, float]:
        """Initialize thresholds for detecting performance bottlenecks."""
        return {
            "high_cost_threshold": 1000.0,  # Cost units
            "seq_scan_rows_threshold": 10000,  # Number of rows
            "sort_memory_threshold": 1000000,  # Work memory in KB
            "nested_loop_threshold": 1000,  # Rows in nested loop
            "execution_time_threshold": 100.0,  # Milliseconds
            "row_estimation_error": 10.0,  # Actual vs estimated rows ratio
            "cost_per_row_threshold": 0.1,  # Cost per row
        }

    def _initialize_optimization_patterns(self) -> Dict[BottleneckType, Dict[str, Any]]:
        """Initialize optimization patterns for different bottleneck types."""
        return {
            BottleneckType.SEQUENTIAL_SCAN: {
                "index_types": [IndexType.BTREE, IndexType.HASH],
                "priority": IndexPriority.HIGH,
                "typical_improvement": "10-50x faster",
                "strategies": [
                    "Add index on filter columns",
                    "Consider partial index for selective queries",
                ],
            },
            BottleneckType.MISSING_INDEX: {
                "index_types": [IndexType.BTREE, IndexType.COMPOSITE],
                "priority": IndexPriority.CRITICAL,
                "typical_improvement": "5-100x faster",
                "strategies": [
                    "Create missing index",
                    "Consider composite index for multi-column filters",
                ],
            },
            BottleneckType.INEFFICIENT_JOIN: {
                "index_types": [IndexType.BTREE, IndexType.COVERING],
                "priority": IndexPriority.HIGH,
                "typical_improvement": "3-25x faster",
                "strategies": [
                    "Index join columns",
                    "Consider covering index",
                    "Rewrite join order",
                ],
            },
            BottleneckType.EXPENSIVE_SORT: {
                "index_types": [IndexType.BTREE],
                "priority": IndexPriority.MEDIUM,
                "typical_improvement": "2-10x faster",
                "strategies": [
                    "Add index on sort columns",
                    "Increase work_mem",
                    "Consider pre-sorted data",
                ],
            },
            BottleneckType.NESTED_LOOP_ISSUE: {
                "index_types": [IndexType.BTREE, IndexType.HASH],
                "priority": IndexPriority.HIGH,
                "typical_improvement": "5-50x faster",
                "strategies": [
                    "Index inner relation",
                    "Force hash join",
                    "Rewrite as EXISTS clause",
                ],
            },
            BottleneckType.SUBQUERY_INEFFICIENCY: {
                "index_types": [IndexType.BTREE],
                "priority": IndexPriority.MEDIUM,
                "typical_improvement": "2-15x faster",
                "strategies": [
                    "Rewrite as JOIN",
                    "Materialize subquery",
                    "Add subquery indexes",
                ],
            },
        }

    def analyze_query_plan(
        self,
        query_sql: str,
        execution_plan: Union[str, Dict[str, Any]],
        execution_time_ms: Optional[float] = None,
    ) -> QueryPlanAnalysis:
        """
        Analyze a query execution plan for optimization opportunities.

        Args:
            query_sql: The SQL query that was executed
            execution_plan: The execution plan (JSON, XML, or text format)
            execution_time_ms: Actual execution time in milliseconds

        Returns:
            Comprehensive analysis of the query plan
        """
        logger.info(f"Analyzing query plan for {self.dialect.value} query")

        # Parse the execution plan
        plan_nodes = self._parse_execution_plan(execution_plan)

        # Calculate total cost and execution time
        total_cost = plan_nodes[0].total_cost if plan_nodes else 0.0
        if execution_time_ms is None:
            execution_time_ms = (
                plan_nodes[0].actual_time_total
                if plan_nodes and plan_nodes[0].actual_time_total
                else 0.0
            )

        # Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(plan_nodes)

        # Generate index recommendations based on bottlenecks
        index_recommendations = self._generate_index_recommendations_from_plan(
            bottlenecks, query_sql
        )

        # Calculate optimization score
        optimization_score = self._calculate_optimization_score(plan_nodes, bottlenecks)

        # Generate suggested query rewrites
        suggested_rewrites = self._suggest_query_rewrites(bottlenecks, query_sql)

        # Generate analysis summary
        analysis_summary = self._generate_analysis_summary(
            plan_nodes, bottlenecks, optimization_score, execution_time_ms
        )

        return QueryPlanAnalysis(
            query_sql=query_sql,
            execution_time_ms=execution_time_ms,
            total_cost=total_cost,
            plan_nodes=plan_nodes,
            bottlenecks=bottlenecks,
            index_recommendations=index_recommendations,
            optimization_score=optimization_score,
            analysis_summary=analysis_summary,
            suggested_rewrites=suggested_rewrites,
        )

    def analyze_multiple_plans(
        self, plans: List[Tuple[str, Union[str, Dict[str, Any]], Optional[float]]]
    ) -> List[QueryPlanAnalysis]:
        """
        Analyze multiple query execution plans.

        Args:
            plans: List of (query_sql, execution_plan, execution_time_ms) tuples

        Returns:
            List of query plan analyses
        """
        analyses = []

        for query_sql, execution_plan, execution_time_ms in plans:
            try:
                analysis = self.analyze_query_plan(
                    query_sql, execution_plan, execution_time_ms
                )
                analyses.append(analysis)
            except Exception as e:
                logger.warning(f"Failed to analyze plan for query: {e}")

        return analyses

    def _parse_execution_plan(
        self, execution_plan: Union[str, Dict[str, Any]]
    ) -> List[PlanNode]:
        """Parse execution plan into structured format."""
        if isinstance(execution_plan, dict):
            return self._parse_json_plan(execution_plan)
        elif isinstance(execution_plan, str):
            if execution_plan.strip().startswith("{"):
                # JSON format
                plan_dict = json.loads(execution_plan)
                return self._parse_json_plan(plan_dict)
            else:
                # Text format
                return self._parse_text_plan(execution_plan)
        else:
            logger.warning("Unsupported execution plan format")
            return []

    def _parse_json_plan(self, plan_dict: Dict[str, Any]) -> List[PlanNode]:
        """Parse JSON execution plan (PostgreSQL EXPLAIN format)."""
        nodes = []

        if "Plan" in plan_dict:
            root_plan = plan_dict["Plan"]
            nodes.append(self._parse_plan_node(root_plan))
        elif isinstance(plan_dict, list) and plan_dict:
            # Handle array format
            for plan in plan_dict:
                if "Plan" in plan:
                    nodes.append(self._parse_plan_node(plan["Plan"]))

        return nodes

    def _parse_plan_node(self, node_dict: Dict[str, Any]) -> PlanNode:
        """Parse a single plan node from JSON."""
        node = PlanNode(
            node_type=node_dict.get("Node Type", "Unknown"),
            relation_name=node_dict.get("Relation Name"),
            index_name=node_dict.get("Index Name"),
            startup_cost=float(node_dict.get("Startup Cost", 0)),
            total_cost=float(node_dict.get("Total Cost", 0)),
            plan_rows=int(node_dict.get("Plan Rows", 0)),
            plan_width=int(node_dict.get("Plan Width", 0)),
            actual_time_first=node_dict.get("Actual Startup Time"),
            actual_time_total=node_dict.get("Actual Total Time"),
            actual_rows=node_dict.get("Actual Rows"),
            actual_loops=node_dict.get("Actual Loops"),
            join_type=node_dict.get("Join Type"),
            sort_key=node_dict.get("Sort Key"),
            conditions=[],
        )

        # Extract conditions
        if "Index Cond" in node_dict:
            node.conditions.append(f"Index: {node_dict['Index Cond']}")
        if "Filter" in node_dict:
            node.conditions.append(f"Filter: {node_dict['Filter']}")
        if "Hash Cond" in node_dict:
            node.conditions.append(f"Hash: {node_dict['Hash Cond']}")
        if "Merge Cond" in node_dict:
            node.conditions.append(f"Merge: {node_dict['Merge Cond']}")

        # Parse child nodes
        if "Plans" in node_dict:
            for child_dict in node_dict["Plans"]:
                node.children.append(self._parse_plan_node(child_dict))

        return node

    def _parse_text_plan(self, plan_text: str) -> List[PlanNode]:
        """Parse text execution plan."""
        # Simple text parsing - this would need to be enhanced for production use
        lines = plan_text.strip().split("\n")
        nodes = []

        # Basic pattern matching for common plan elements
        for line in lines:
            if "Seq Scan" in line:
                node = self._create_node_from_text_line(line, "Seq Scan")
                if node:
                    nodes.append(node)
            elif "Index Scan" in line:
                node = self._create_node_from_text_line(line, "Index Scan")
                if node:
                    nodes.append(node)
            elif "Nested Loop" in line:
                node = self._create_node_from_text_line(line, "Nested Loop")
                if node:
                    nodes.append(node)
            elif "Hash Join" in line:
                node = self._create_node_from_text_line(line, "Hash Join")
                if node:
                    nodes.append(node)

        return nodes

    def _create_node_from_text_line(
        self, line: str, node_type: str
    ) -> Optional[PlanNode]:
        """Create a plan node from a text line."""
        # Extract cost information using regex
        cost_pattern = r"cost=([\d.]+)\.\.([\d.]+)"
        rows_pattern = r"rows=(\d+)"
        width_pattern = r"width=(\d+)"

        cost_match = re.search(cost_pattern, line)
        rows_match = re.search(rows_pattern, line)
        width_match = re.search(width_pattern, line)

        startup_cost = float(cost_match.group(1)) if cost_match else 0.0
        total_cost = float(cost_match.group(2)) if cost_match else 0.0
        plan_rows = int(rows_match.group(1)) if rows_match else 0
        plan_width = int(width_match.group(1)) if width_match else 0

        # Extract table name
        table_pattern = r"on (\w+)"
        table_match = re.search(table_pattern, line)
        relation_name = table_match.group(1) if table_match else None

        return PlanNode(
            node_type=node_type,
            relation_name=relation_name,
            index_name=None,
            startup_cost=startup_cost,
            total_cost=total_cost,
            plan_rows=plan_rows,
            plan_width=plan_width,
        )

    def _identify_bottlenecks(
        self, plan_nodes: List[PlanNode]
    ) -> List[PerformanceBottleneck]:
        """Identify performance bottlenecks in the execution plan."""
        bottlenecks = []

        for node in plan_nodes:
            bottlenecks.extend(self._analyze_node_for_bottlenecks(node))

            # Recursively analyze child nodes
            for child in node.children:
                bottlenecks.extend(self._analyze_node_for_bottlenecks(child))

        return bottlenecks

    def _analyze_node_for_bottlenecks(
        self, node: PlanNode
    ) -> List[PerformanceBottleneck]:
        """Analyze a single node for performance bottlenecks."""
        bottlenecks = []

        # Sequential scan on large table
        if (
            node.node_type == "Seq Scan"
            and node.plan_rows > self.bottleneck_thresholds["seq_scan_rows_threshold"]
        ):
            bottlenecks.append(
                PerformanceBottleneck(
                    bottleneck_type=BottleneckType.SEQUENTIAL_SCAN,
                    node=node,
                    severity="high",
                    impact_description=f"Sequential scan on {node.relation_name} reading {node.plan_rows} rows",
                    optimization_suggestions=[
                        f"Add index on frequently filtered columns of {node.relation_name}",
                        "Consider partial index for selective queries",
                        "Analyze query filters to optimize WHERE clauses",
                    ],
                    estimated_improvement="10-50x faster with proper indexing",
                    related_tables=[node.relation_name] if node.relation_name else [],
                    related_columns=self._extract_columns_from_conditions(
                        node.conditions
                    ),
                )
            )

        # High cost operation
        if node.total_cost > self.bottleneck_thresholds["high_cost_threshold"]:
            bottlenecks.append(
                PerformanceBottleneck(
                    bottleneck_type=BottleneckType.HIGH_COST_OPERATION,
                    node=node,
                    severity="medium",
                    impact_description=f"High cost {node.node_type} operation (cost: {node.total_cost:.1f})",
                    optimization_suggestions=[
                        "Review query structure for optimization opportunities",
                        "Consider adding appropriate indexes",
                        "Analyze if operation can be avoided or simplified",
                    ],
                    estimated_improvement="2-10x faster with optimization",
                    related_tables=[node.relation_name] if node.relation_name else [],
                    related_columns=[],
                )
            )

        # Inefficient nested loop
        if (
            node.node_type == "Nested Loop"
            and node.plan_rows > self.bottleneck_thresholds["nested_loop_threshold"]
        ):
            bottlenecks.append(
                PerformanceBottleneck(
                    bottleneck_type=BottleneckType.NESTED_LOOP_ISSUE,
                    node=node,
                    severity="high",
                    impact_description=f"Inefficient nested loop processing {node.plan_rows} rows",
                    optimization_suggestions=[
                        "Add index on inner relation join column",
                        "Consider forcing hash join instead",
                        "Review join conditions for optimization",
                    ],
                    estimated_improvement="5-50x faster with proper indexing",
                    related_tables=[],
                    related_columns=self._extract_columns_from_conditions(
                        node.conditions
                    ),
                )
            )

        # Expensive sort operation
        if node.node_type == "Sort" and node.total_cost > 100:
            bottlenecks.append(
                PerformanceBottleneck(
                    bottleneck_type=BottleneckType.EXPENSIVE_SORT,
                    node=node,
                    severity="medium",
                    impact_description=f"Expensive sort operation (cost: {node.total_cost:.1f})",
                    optimization_suggestions=[
                        "Add index on sort columns to eliminate sort",
                        "Increase work_mem for better sort performance",
                        "Consider if sorting is necessary",
                    ],
                    estimated_improvement="2-10x faster with index on sort columns",
                    related_tables=[],
                    related_columns=node.sort_key if node.sort_key else [],
                )
            )

        # Row estimation errors
        if (
            node.actual_rows is not None
            and node.plan_rows > 0
            and abs(node.actual_rows - node.plan_rows) / node.plan_rows
            > self.bottleneck_thresholds["row_estimation_error"]
        ):
            bottlenecks.append(
                PerformanceBottleneck(
                    bottleneck_type=BottleneckType.LARGE_RESULT_SET,
                    node=node,
                    severity="low",
                    impact_description=f"Row estimation error: planned {node.plan_rows}, actual {node.actual_rows}",
                    optimization_suggestions=[
                        "Update table statistics with ANALYZE",
                        "Consider histogram adjustments",
                        "Review query selectivity",
                    ],
                    estimated_improvement="Better query planning",
                    related_tables=[node.relation_name] if node.relation_name else [],
                    related_columns=[],
                )
            )

        return bottlenecks

    def _extract_columns_from_conditions(self, conditions: List[str]) -> List[str]:
        """Extract column names from condition strings."""
        columns = []

        for condition in conditions:
            # Simple regex to extract column names
            column_pattern = r"(\w+)\s*[=<>!]"
            matches = re.findall(column_pattern, condition)
            columns.extend(matches)

        return list(set(columns))  # Remove duplicates

    def _generate_index_recommendations_from_plan(
        self, bottlenecks: List[PerformanceBottleneck], query_sql: str
    ) -> List[IndexRecommendation]:
        """Generate index recommendations based on identified bottlenecks."""
        recommendations = []

        for bottleneck in bottlenecks:
            pattern = self.optimization_patterns.get(bottleneck.bottleneck_type)
            if not pattern:
                continue

            for table in bottleneck.related_tables:
                for column in bottleneck.related_columns:
                    for index_type in pattern["index_types"]:
                        rec = IndexRecommendation(
                            table_name=table,
                            column_names=[column],
                            index_type=index_type,
                            priority=pattern["priority"],
                            estimated_impact=pattern["typical_improvement"],
                            maintenance_cost=(
                                "Low" if index_type == IndexType.BTREE else "Medium"
                            ),
                            sql_dialect=self.dialect,
                            create_statement=self._generate_index_statement(
                                table, [column], index_type
                            ),
                            rationale=f"Address {bottleneck.bottleneck_type.value} bottleneck",
                            query_patterns=["Query plan optimization"],
                            performance_gain=self._estimate_performance_gain(
                                bottleneck.bottleneck_type
                            ),
                            size_estimate_mb=10.0,  # Default estimate
                        )
                        recommendations.append(rec)

        return recommendations

    def _generate_index_statement(
        self, table: str, columns: List[str], index_type: IndexType
    ) -> str:
        """Generate CREATE INDEX statement."""
        index_name = f"idx_{table}_{'_'.join(columns)}"
        columns_str = ", ".join(columns)

        if self.dialect == SQLDialect.POSTGRESQL:
            if index_type == IndexType.HASH:
                return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} USING hash ({columns_str});"
            else:
                return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} ({columns_str});"
        else:
            return f"CREATE INDEX {index_name} ON {table} ({columns_str});"

    def _estimate_performance_gain(self, bottleneck_type: BottleneckType) -> float:
        """Estimate performance gain for addressing a bottleneck type."""
        gain_mapping = {
            BottleneckType.SEQUENTIAL_SCAN: 20.0,
            BottleneckType.MISSING_INDEX: 50.0,
            BottleneckType.INEFFICIENT_JOIN: 10.0,
            BottleneckType.EXPENSIVE_SORT: 5.0,
            BottleneckType.NESTED_LOOP_ISSUE: 15.0,
            BottleneckType.SUBQUERY_INEFFICIENCY: 8.0,
            BottleneckType.HIGH_COST_OPERATION: 3.0,
            BottleneckType.LARGE_RESULT_SET: 1.5,
            BottleneckType.MEMORY_INTENSIVE: 2.0,
        }

        return gain_mapping.get(bottleneck_type, 2.0)

    def _calculate_optimization_score(
        self, plan_nodes: List[PlanNode], bottlenecks: List[PerformanceBottleneck]
    ) -> float:
        """Calculate an optimization score (0-100, higher is better)."""
        if not plan_nodes:
            return 0.0

        # Base score starts at 100
        score = 100.0

        # Deduct points for bottlenecks
        severity_penalties = {"critical": 30, "high": 20, "medium": 10, "low": 5}

        for bottleneck in bottlenecks:
            penalty = severity_penalties.get(bottleneck.severity, 5)
            score -= penalty

        # Additional penalties for specific issues
        for node in plan_nodes:
            # Sequential scans on large tables
            if node.node_type == "Seq Scan" and node.plan_rows > 10000:
                score -= 15

            # High cost operations
            if node.total_cost > 1000:
                score -= 10

            # Inefficient joins
            if node.node_type == "Nested Loop" and node.plan_rows > 1000:
                score -= 10

        return max(0.0, min(100.0, score))

    def _suggest_query_rewrites(
        self, bottlenecks: List[PerformanceBottleneck], query_sql: str
    ) -> List[str]:
        """Suggest query rewrites based on bottlenecks."""
        suggestions = []

        for bottleneck in bottlenecks:
            if bottleneck.bottleneck_type == BottleneckType.SUBQUERY_INEFFICIENCY:
                suggestions.append(
                    "Consider rewriting subqueries as JOINs for better performance"
                )

            elif bottleneck.bottleneck_type == BottleneckType.NESTED_LOOP_ISSUE:
                suggestions.append(
                    "Force hash join with /*+ USE_HASH */ hint or SET enable_nestloop = off"
                )

            elif bottleneck.bottleneck_type == BottleneckType.EXPENSIVE_SORT:
                suggestions.append(
                    "Consider adding LIMIT clause if full result set is not needed"
                )
                suggestions.append("Use indexes to eliminate sorting where possible")

            elif bottleneck.bottleneck_type == BottleneckType.SEQUENTIAL_SCAN:
                suggestions.append(
                    "Add WHERE clause with selective conditions to reduce data scan"
                )
                suggestions.append("Consider partitioning large tables")

        # General query optimization suggestions
        if "SELECT *" in query_sql.upper():
            suggestions.append("Avoid SELECT * - specify only needed columns")

        if query_sql.upper().count("JOIN") > 3:
            suggestions.append(
                "Review complex joins - consider breaking into smaller queries"
            )

        if "ORDER BY" in query_sql.upper() and "LIMIT" not in query_sql.upper():
            suggestions.append(
                "Consider adding LIMIT clause with ORDER BY for better performance"
            )

        return list(set(suggestions))  # Remove duplicates

    def _generate_analysis_summary(
        self,
        plan_nodes: List[PlanNode],
        bottlenecks: List[PerformanceBottleneck],
        optimization_score: float,
        execution_time_ms: float,
    ) -> str:
        """Generate a summary of the query plan analysis."""
        summary = "Query Plan Analysis Summary\n"
        summary += "==========================\n\n"
        summary += f"Execution time: {execution_time_ms:.2f}ms\n"
        summary += f"Optimization score: {optimization_score:.1f}/100\n"
        summary += f"Plan nodes analyzed: {len(plan_nodes)}\n"
        summary += f"Bottlenecks identified: {len(bottlenecks)}\n\n"

        # Categorize bottlenecks by severity
        severity_counts = {}
        for bottleneck in bottlenecks:
            severity_counts[bottleneck.severity] = (
                severity_counts.get(bottleneck.severity, 0) + 1
            )

        if severity_counts:
            summary += "Bottlenecks by severity:\n"
            for severity, count in severity_counts.items():
                summary += f"  {severity.title()}: {count}\n"
            summary += "\n"

        # Top bottlenecks
        high_severity_bottlenecks = [
            b for b in bottlenecks if b.severity in ["critical", "high"]
        ]
        if high_severity_bottlenecks:
            summary += "Top optimization opportunities:\n"
            for i, bottleneck in enumerate(high_severity_bottlenecks[:3], 1):
                summary += f"  {i}. {bottleneck.bottleneck_type.value} - {bottleneck.estimated_improvement}\n"

        # Overall assessment
        if optimization_score >= 80:
            summary += "\n✅ Query is well-optimized"
        elif optimization_score >= 60:
            summary += "\n⚠️ Query has moderate optimization opportunities"
        else:
            summary += "\n❌ Query needs significant optimization"

        return summary

    def generate_comprehensive_report(self, analyses: List[QueryPlanAnalysis]) -> str:
        """Generate a comprehensive report from multiple query plan analyses."""
        if not analyses:
            return "No query plans analyzed."

        report = "DataFlow Query Plan Analysis Report\n"
        report += "===================================\n\n"
        report += f"Queries analyzed: {len(analyses)}\n"

        # Overall statistics
        total_execution_time = sum(a.execution_time_ms for a in analyses)
        avg_optimization_score = sum(a.optimization_score for a in analyses) / len(
            analyses
        )
        total_bottlenecks = sum(len(a.bottlenecks) for a in analyses)
        total_index_recommendations = sum(
            len(a.index_recommendations) for a in analyses
        )

        report += f"Total execution time: {total_execution_time:.2f}ms\n"
        report += f"Average optimization score: {avg_optimization_score:.1f}/100\n"
        report += f"Total bottlenecks found: {total_bottlenecks}\n"
        report += f"Index recommendations: {total_index_recommendations}\n\n"

        # Query performance ranking
        sorted_analyses = sorted(
            analyses, key=lambda x: x.optimization_score, reverse=True
        )

        report += "Query Performance Ranking:\n"
        report += "--------------------------\n"
        for i, analysis in enumerate(sorted_analyses, 1):
            status = (
                "✅"
                if analysis.optimization_score >= 80
                else "⚠️" if analysis.optimization_score >= 60 else "❌"
            )
            report += f"{i}. {status} Score: {analysis.optimization_score:.1f} - {analysis.execution_time_ms:.1f}ms\n"
            if len(analysis.query_sql) > 50:
                query_preview = analysis.query_sql[:50] + "..."
            else:
                query_preview = analysis.query_sql
            report += f"   Query: {query_preview}\n"

        # Most common bottlenecks
        all_bottlenecks = []
        for analysis in analyses:
            all_bottlenecks.extend(analysis.bottlenecks)

        bottleneck_counts = {}
        for bottleneck in all_bottlenecks:
            bottleneck_type = bottleneck.bottleneck_type.value
            bottleneck_counts[bottleneck_type] = (
                bottleneck_counts.get(bottleneck_type, 0) + 1
            )

        if bottleneck_counts:
            report += "\nMost Common Bottlenecks:\n"
            report += "------------------------\n"
            sorted_bottlenecks = sorted(
                bottleneck_counts.items(), key=lambda x: x[1], reverse=True
            )
            for bottleneck_type, count in sorted_bottlenecks[:5]:
                report += f"{count}x {bottleneck_type.replace('_', ' ').title()}\n"

        # Optimization recommendations
        report += "\nTop Optimization Recommendations:\n"
        report += "---------------------------------\n"

        # Find queries with lowest scores
        worst_queries = [a for a in sorted_analyses if a.optimization_score < 60]
        if worst_queries:
            report += "Priority queries for optimization:\n"
            for analysis in worst_queries[:3]:
                report += f"  - Score {analysis.optimization_score:.1f}: {len(analysis.bottlenecks)} bottlenecks found\n"

        # Most impactful index recommendations
        all_index_recs = []
        for analysis in analyses:
            all_index_recs.extend(analysis.index_recommendations)

        critical_indexes = [
            r for r in all_index_recs if r.priority == IndexPriority.CRITICAL
        ]
        if critical_indexes:
            report += "\nCritical Index Recommendations:\n"
            for rec in critical_indexes[:5]:
                report += f"  - {rec.table_name}.{','.join(rec.column_names)}: {rec.estimated_impact}\n"

        return report

    def monitor_query_performance(
        self, query_analyses: List[QueryPlanAnalysis], threshold_ms: float = 100.0
    ) -> Dict[str, Any]:
        """Monitor query performance and identify trends."""
        monitoring_data = {
            "slow_queries": [],
            "optimization_trends": {},
            "bottleneck_frequency": {},
            "recommendations": [],
        }

        # Identify slow queries
        for analysis in query_analyses:
            if analysis.execution_time_ms > threshold_ms:
                monitoring_data["slow_queries"].append(
                    {
                        "query": (
                            analysis.query_sql[:100] + "..."
                            if len(analysis.query_sql) > 100
                            else analysis.query_sql
                        ),
                        "execution_time_ms": analysis.execution_time_ms,
                        "optimization_score": analysis.optimization_score,
                        "bottleneck_count": len(analysis.bottlenecks),
                    }
                )

        # Track bottleneck frequency
        for analysis in query_analyses:
            for bottleneck in analysis.bottlenecks:
                bottleneck_type = bottleneck.bottleneck_type.value
                if bottleneck_type not in monitoring_data["bottleneck_frequency"]:
                    monitoring_data["bottleneck_frequency"][bottleneck_type] = 0
                monitoring_data["bottleneck_frequency"][bottleneck_type] += 1

        # Generate monitoring recommendations
        if len(monitoring_data["slow_queries"]) > len(query_analyses) * 0.3:
            monitoring_data["recommendations"].append(
                "High percentage of slow queries detected - review indexing strategy"
            )

        most_common_bottleneck = max(
            monitoring_data["bottleneck_frequency"].items(),
            key=lambda x: x[1],
            default=(None, 0),
        )

        if most_common_bottleneck[1] > 0:
            monitoring_data["recommendations"].append(
                f"Most common bottleneck: {most_common_bottleneck[0]} - consider targeted optimization"
            )

        return monitoring_data
