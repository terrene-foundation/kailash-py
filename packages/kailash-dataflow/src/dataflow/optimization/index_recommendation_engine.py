"""
DataFlow Index Recommendation Engine

Advanced database index recommendation system that analyzes query patterns,
workflow structures, and data access patterns to suggest optimal indexes
for maximum performance improvement.

Features:
- Query pattern analysis
- Join optimization
- Composite index recommendations
- Partial index suggestions
- Index maintenance cost analysis
- Performance impact estimation
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .sql_query_optimizer import OptimizedQuery, SQLDialect
from .workflow_analyzer import OptimizationOpportunity, PatternType, WorkflowNode

logger = logging.getLogger(__name__)


class IndexType(Enum):
    """Types of database indexes."""

    BTREE = "btree"
    HASH = "hash"
    GIN = "gin"
    GIST = "gist"
    PARTIAL = "partial"
    UNIQUE = "unique"
    COMPOSITE = "composite"
    COVERING = "covering"


class IndexPriority(Enum):
    """Priority levels for index recommendations."""

    CRITICAL = "critical"  # High impact, low cost
    HIGH = "high"  # Good impact/cost ratio
    MEDIUM = "medium"  # Moderate impact
    LOW = "low"  # Low impact or high cost
    OPTIONAL = "optional"  # Nice to have


@dataclass
class IndexRecommendation:
    """Represents a database index recommendation."""

    table_name: str
    column_names: List[str]
    index_type: IndexType
    priority: IndexPriority
    estimated_impact: str
    maintenance_cost: str
    sql_dialect: SQLDialect
    create_statement: str
    rationale: str
    query_patterns: List[str]
    performance_gain: float  # Estimated performance improvement (multiplier)
    size_estimate_mb: float
    unique: bool = False
    partial_condition: Optional[str] = None
    include_columns: Optional[List[str]] = None  # For covering indexes


@dataclass
class IndexAnalysisResult:
    """Results from index analysis."""

    recommendations: List[IndexRecommendation]
    existing_indexes: List[str]
    redundant_indexes: List[str]
    missing_critical_indexes: List[IndexRecommendation]
    total_estimated_gain: float
    analysis_summary: str


class IndexRecommendationEngine:
    """
    Advanced index recommendation engine for DataFlow optimizations.

    Analyzes workflow patterns, query structures, and data access patterns
    to recommend optimal database indexes for maximum performance improvement.

    Features:
    - Pattern-based index recommendations
    - Composite index optimization
    - Partial index suggestions
    - Covering index recommendations
    - Performance impact estimation
    - Index maintenance cost analysis
    """

    def __init__(self, dialect: SQLDialect = SQLDialect.POSTGRESQL):
        self.dialect = dialect
        self.index_patterns = self._initialize_index_patterns()
        self.performance_weights = self._initialize_performance_weights()

    def _initialize_index_patterns(self) -> Dict[PatternType, Dict[str, Any]]:
        """Initialize index recommendation patterns for different optimization types."""
        return {
            PatternType.QUERY_MERGE_AGGREGATE: {
                "join_indexes": ["foreign_key_columns", "primary_key_columns"],
                "filter_indexes": ["where_clause_columns"],
                "group_by_indexes": ["group_by_columns"],
                "composite_indexes": ["join_and_filter_columns"],
                "covering_indexes": ["frequently_selected_columns"],
            },
            PatternType.MULTIPLE_QUERIES: {
                "filter_indexes": ["common_filter_columns"],
                "unique_indexes": ["unique_constraint_columns"],
                "partial_indexes": ["selective_filter_columns"],
            },
            PatternType.REDUNDANT_OPERATIONS: {
                "cache_indexes": ["frequently_accessed_columns"],
                "partial_indexes": ["redundant_filter_columns"],
            },
            PatternType.INEFFICIENT_JOINS: {
                "join_indexes": ["all_join_columns"],
                "composite_indexes": ["multi_table_join_columns"],
                "foreign_key_indexes": ["referential_integrity_columns"],
            },
        }

    def _initialize_performance_weights(self) -> Dict[str, float]:
        """Initialize performance impact weights for different index types."""
        return {
            "primary_key": 10.0,  # Extremely high impact
            "foreign_key": 8.0,  # Very high impact for joins
            "unique": 7.0,  # High impact for unique lookups
            "filter": 6.0,  # High impact for WHERE clauses
            "composite": 5.0,  # Good impact for multi-column queries
            "group_by": 4.0,  # Good impact for aggregations
            "covering": 3.0,  # Moderate impact, reduces I/O
            "partial": 2.0,  # Moderate impact, specific cases
            "sort": 1.5,  # Lower impact for ORDER BY
        }

    def analyze_and_recommend(
        self,
        opportunities: List[OptimizationOpportunity],
        optimized_queries: List[OptimizedQuery],
        existing_indexes: Optional[List[str]] = None,
    ) -> IndexAnalysisResult:
        """
        Analyze optimization opportunities and recommend indexes.

        Args:
            opportunities: List of optimization opportunities from WorkflowAnalyzer
            optimized_queries: List of optimized queries from SQLQueryOptimizer
            existing_indexes: List of existing database indexes

        Returns:
            Comprehensive index analysis and recommendations
        """
        logger.info(
            f"Analyzing index recommendations for {len(opportunities)} opportunities"
        )

        if existing_indexes is None:
            existing_indexes = []

        # Analyze different aspects
        pattern_recommendations = self._analyze_optimization_patterns(opportunities)
        query_recommendations = self._analyze_optimized_queries(optimized_queries)
        join_recommendations = self._analyze_join_patterns(opportunities)
        aggregate_recommendations = self._analyze_aggregation_patterns(opportunities)
        filter_recommendations = self._analyze_filter_patterns(opportunities)

        # Combine and deduplicate recommendations
        all_recommendations = (
            pattern_recommendations
            + query_recommendations
            + join_recommendations
            + aggregate_recommendations
            + filter_recommendations
        )

        # Deduplicate and prioritize
        recommendations = self._deduplicate_and_prioritize(all_recommendations)

        # Analyze existing indexes
        redundant_indexes = self._find_redundant_indexes(
            recommendations, existing_indexes
        )
        missing_critical = self._find_missing_critical_indexes(recommendations)

        # Calculate performance impact
        total_estimated_gain = sum(rec.performance_gain for rec in recommendations)

        # Generate analysis summary
        analysis_summary = self._generate_analysis_summary(
            recommendations, redundant_indexes, missing_critical, total_estimated_gain
        )

        return IndexAnalysisResult(
            recommendations=recommendations,
            existing_indexes=existing_indexes,
            redundant_indexes=redundant_indexes,
            missing_critical_indexes=missing_critical,
            total_estimated_gain=total_estimated_gain,
            analysis_summary=analysis_summary,
        )

    def _analyze_optimization_patterns(
        self, opportunities: List[OptimizationOpportunity]
    ) -> List[IndexRecommendation]:
        """Analyze optimization patterns and recommend indexes."""
        recommendations = []

        for opportunity in opportunities:
            pattern_config = self.index_patterns.get(opportunity.pattern_type, {})

            if opportunity.pattern_type == PatternType.QUERY_MERGE_AGGREGATE:
                recommendations.extend(
                    self._recommend_qma_indexes(opportunity, pattern_config)
                )
            elif opportunity.pattern_type == PatternType.MULTIPLE_QUERIES:
                recommendations.extend(
                    self._recommend_multiple_query_indexes(opportunity, pattern_config)
                )
            elif opportunity.pattern_type == PatternType.REDUNDANT_OPERATIONS:
                recommendations.extend(
                    self._recommend_redundancy_indexes(opportunity, pattern_config)
                )
            elif opportunity.pattern_type == PatternType.INEFFICIENT_JOINS:
                recommendations.extend(
                    self._recommend_join_indexes(opportunity, pattern_config)
                )

        return recommendations

    def _analyze_optimized_queries(
        self, optimized_queries: List[OptimizedQuery]
    ) -> List[IndexRecommendation]:
        """Analyze optimized SQL queries and recommend indexes."""
        recommendations = []

        for query in optimized_queries:
            sql = query.optimized_sql.upper()

            # Extract table names
            tables = self._extract_table_names(sql)

            # Extract JOIN conditions
            join_conditions = self._extract_join_conditions(sql)

            # Extract WHERE conditions
            where_conditions = self._extract_where_conditions(sql)

            # Extract GROUP BY columns
            group_by_columns = self._extract_group_by_columns(sql)

            # Extract ORDER BY columns
            order_by_columns = self._extract_order_by_columns(sql)

            # Generate recommendations for each aspect
            recommendations.extend(
                self._recommend_join_indexes_from_sql(tables, join_conditions)
            )
            recommendations.extend(
                self._recommend_filter_indexes_from_sql(tables, where_conditions)
            )
            recommendations.extend(
                self._recommend_group_by_indexes(tables, group_by_columns)
            )
            recommendations.extend(
                self._recommend_sort_indexes(tables, order_by_columns)
            )
            recommendations.extend(self._recommend_covering_indexes(query, tables))

        return recommendations

    def _analyze_join_patterns(
        self, opportunities: List[OptimizationOpportunity]
    ) -> List[IndexRecommendation]:
        """Analyze join patterns and recommend optimized indexes."""
        recommendations = []

        join_analysis = {}

        for opportunity in opportunities:
            if "join" in opportunity.optimization_strategy.lower():
                # Extract join information
                join_info = self._extract_join_info_from_opportunity(opportunity)

                for table_pair, join_conditions in join_info.items():
                    if table_pair not in join_analysis:
                        join_analysis[table_pair] = []
                    join_analysis[table_pair].extend(join_conditions)

        # Generate join index recommendations
        for table_pair, conditions in join_analysis.items():
            recommendations.extend(
                self._recommend_optimized_join_indexes(table_pair, conditions)
            )

        return recommendations

    def _analyze_aggregation_patterns(
        self, opportunities: List[OptimizationOpportunity]
    ) -> List[IndexRecommendation]:
        """Analyze aggregation patterns and recommend indexes."""
        recommendations = []

        for opportunity in opportunities:
            if opportunity.pattern_type == PatternType.QUERY_MERGE_AGGREGATE:
                # Extract aggregation information
                agg_info = self._extract_aggregation_info_from_opportunity(opportunity)

                # Recommend indexes for GROUP BY columns
                if agg_info.get("group_by_columns"):
                    recommendations.extend(
                        self._recommend_aggregation_indexes(
                            agg_info["table"], agg_info["group_by_columns"]
                        )
                    )

                # Recommend covering indexes for aggregation functions
                if agg_info.get("aggregate_columns"):
                    recommendations.extend(
                        self._recommend_aggregation_covering_indexes(
                            agg_info["table"],
                            agg_info["group_by_columns"],
                            agg_info["aggregate_columns"],
                        )
                    )

        return recommendations

    def _analyze_filter_patterns(
        self, opportunities: List[OptimizationOpportunity]
    ) -> List[IndexRecommendation]:
        """Analyze filter patterns and recommend indexes."""
        recommendations = []

        filter_analysis = {}

        for opportunity in opportunities:
            # Extract filter information from opportunity
            filter_info = self._extract_filter_info_from_opportunity(opportunity)

            for table, filters in filter_info.items():
                if table not in filter_analysis:
                    filter_analysis[table] = {}

                for column, filter_type in filters.items():
                    if column not in filter_analysis[table]:
                        filter_analysis[table][column] = []
                    filter_analysis[table][column].append(filter_type)

        # Generate filter index recommendations
        for table, columns in filter_analysis.items():
            for column, filter_types in columns.items():
                recommendations.extend(
                    self._recommend_filter_indexes(table, column, filter_types)
                )

        return recommendations

    def _recommend_qma_indexes(
        self, opportunity: OptimizationOpportunity, config: Dict[str, Any]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for Query→Merge→Aggregate patterns."""
        recommendations = []

        # Extract pattern information
        pattern_info = self._extract_qma_pattern_info(opportunity)

        # Primary join indexes
        for join_condition in pattern_info.get("join_conditions", []):
            rec = IndexRecommendation(
                table_name=join_condition["left_table"],
                column_names=[join_condition["left_column"]],
                index_type=IndexType.BTREE,
                priority=IndexPriority.CRITICAL,
                estimated_impact="10-50x faster joins",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    join_condition["left_table"],
                    [join_condition["left_column"]],
                    IndexType.BTREE,
                ),
                rationale=f"Critical for join performance on {join_condition['left_table']}.{join_condition['left_column']}",
                query_patterns=["JOIN operations"],
                performance_gain=self.performance_weights["foreign_key"],
                size_estimate_mb=self._estimate_index_size(
                    [join_condition["left_column"]]
                ),
            )
            recommendations.append(rec)

        # Composite indexes for filter + join
        if pattern_info.get("filter_columns") and pattern_info.get("join_conditions"):
            for join_condition in pattern_info["join_conditions"]:
                filter_cols = pattern_info["filter_columns"][
                    :2
                ]  # Limit to 2 filter columns
                composite_columns = [join_condition["left_column"]] + filter_cols

                rec = IndexRecommendation(
                    table_name=join_condition["left_table"],
                    column_names=composite_columns,
                    index_type=IndexType.COMPOSITE,
                    priority=IndexPriority.HIGH,
                    estimated_impact="5-20x faster filtered joins",
                    maintenance_cost="Medium",
                    sql_dialect=self.dialect,
                    create_statement=self._generate_create_statement(
                        join_condition["left_table"],
                        composite_columns,
                        IndexType.COMPOSITE,
                    ),
                    rationale="Composite index for join and filter optimization",
                    query_patterns=["Filtered JOIN operations"],
                    performance_gain=self.performance_weights["composite"],
                    size_estimate_mb=self._estimate_index_size(composite_columns),
                )
                recommendations.append(rec)

        # Group by indexes
        if pattern_info.get("group_by_columns"):
            group_by_cols = pattern_info["group_by_columns"]
            primary_table = pattern_info.get("primary_table", "table1")

            rec = IndexRecommendation(
                table_name=primary_table,
                column_names=group_by_cols,
                index_type=IndexType.BTREE,
                priority=IndexPriority.HIGH,
                estimated_impact="3-15x faster aggregations",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    primary_table, group_by_cols, IndexType.BTREE
                ),
                rationale=f"Optimize GROUP BY operations on {', '.join(group_by_cols)}",
                query_patterns=["GROUP BY aggregations"],
                performance_gain=self.performance_weights["group_by"],
                size_estimate_mb=self._estimate_index_size(group_by_cols),
            )
            recommendations.append(rec)

        return recommendations

    def _recommend_multiple_query_indexes(
        self, opportunity: OptimizationOpportunity, config: Dict[str, Any]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for multiple queries patterns."""
        recommendations = []

        # Extract common filter patterns
        query_info = self._extract_multiple_query_info(opportunity)

        for table, filters in query_info.get("common_filters", {}).items():
            for column, selectivity in filters.items():
                if selectivity < 0.1:  # High selectivity (< 10% of rows)
                    # Recommend partial index
                    rec = IndexRecommendation(
                        table_name=table,
                        column_names=[column],
                        index_type=IndexType.PARTIAL,
                        priority=IndexPriority.HIGH,
                        estimated_impact="5-25x faster selective queries",
                        maintenance_cost="Low",
                        sql_dialect=self.dialect,
                        create_statement=self._generate_partial_index_statement(
                            table, column, selectivity
                        ),
                        rationale=f"Partial index for highly selective filter on {column}",
                        query_patterns=["Selective filtering"],
                        performance_gain=self.performance_weights["partial"],
                        size_estimate_mb=self._estimate_index_size([column])
                        * selectivity,
                        partial_condition=f"{column} = 'common_value'",
                    )
                    recommendations.append(rec)
                else:
                    # Regular index
                    rec = IndexRecommendation(
                        table_name=table,
                        column_names=[column],
                        index_type=IndexType.BTREE,
                        priority=IndexPriority.MEDIUM,
                        estimated_impact="2-10x faster queries",
                        maintenance_cost="Low",
                        sql_dialect=self.dialect,
                        create_statement=self._generate_create_statement(
                            table, [column], IndexType.BTREE
                        ),
                        rationale=f"Common filter optimization for {column}",
                        query_patterns=["Multiple query filtering"],
                        performance_gain=self.performance_weights["filter"],
                        size_estimate_mb=self._estimate_index_size([column]),
                    )
                    recommendations.append(rec)

        return recommendations

    def _recommend_redundancy_indexes(
        self, opportunity: OptimizationOpportunity, config: Dict[str, Any]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for redundant operations optimization."""
        recommendations = []

        # For redundant operations, recommend caching indexes
        redundancy_info = self._extract_redundancy_info(opportunity)

        for table, access_patterns in redundancy_info.get(
            "frequent_access", {}
        ).items():
            for column, frequency in access_patterns.items():
                if frequency > 0.8:  # Very frequent access (> 80% of operations)
                    rec = IndexRecommendation(
                        table_name=table,
                        column_names=[column],
                        index_type=IndexType.BTREE,
                        priority=IndexPriority.CRITICAL,
                        estimated_impact="10-50x faster repeated queries",
                        maintenance_cost="Low",
                        sql_dialect=self.dialect,
                        create_statement=self._generate_create_statement(
                            table, [column], IndexType.BTREE
                        ),
                        rationale=f"Cache optimization for frequently accessed {column}",
                        query_patterns=["Repeated data access"],
                        performance_gain=self.performance_weights["filter"]
                        * 2,  # Double impact for caching
                        size_estimate_mb=self._estimate_index_size([column]),
                    )
                    recommendations.append(rec)

        return recommendations

    def _recommend_join_indexes(
        self, opportunity: OptimizationOpportunity, config: Dict[str, Any]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for inefficient joins optimization."""
        recommendations = []

        join_info = self._extract_join_info_from_opportunity(opportunity)

        for table_pair, join_conditions in join_info.items():
            left_table, right_table = table_pair.split("_TO_")

            for condition in join_conditions:
                # Left table index
                rec_left = IndexRecommendation(
                    table_name=left_table,
                    column_names=[condition["left_column"]],
                    index_type=IndexType.BTREE,
                    priority=IndexPriority.CRITICAL,
                    estimated_impact="5-25x faster joins",
                    maintenance_cost="Low",
                    sql_dialect=self.dialect,
                    create_statement=self._generate_create_statement(
                        left_table, [condition["left_column"]], IndexType.BTREE
                    ),
                    rationale=f"Join optimization for {left_table}.{condition['left_column']}",
                    query_patterns=["JOIN operations"],
                    performance_gain=self.performance_weights["foreign_key"],
                    size_estimate_mb=self._estimate_index_size(
                        [condition["left_column"]]
                    ),
                )
                recommendations.append(rec_left)

                # Right table index
                rec_right = IndexRecommendation(
                    table_name=right_table,
                    column_names=[condition["right_column"]],
                    index_type=IndexType.BTREE,
                    priority=IndexPriority.CRITICAL,
                    estimated_impact="5-25x faster joins",
                    maintenance_cost="Low",
                    sql_dialect=self.dialect,
                    create_statement=self._generate_create_statement(
                        right_table, [condition["right_column"]], IndexType.BTREE
                    ),
                    rationale=f"Join optimization for {right_table}.{condition['right_column']}",
                    query_patterns=["JOIN operations"],
                    performance_gain=self.performance_weights["foreign_key"],
                    size_estimate_mb=self._estimate_index_size(
                        [condition["right_column"]]
                    ),
                )
                recommendations.append(rec_right)

        return recommendations

    def _recommend_join_indexes_from_sql(
        self, tables: List[str], join_conditions: List[Dict[str, str]]
    ) -> List[IndexRecommendation]:
        """Recommend indexes based on SQL JOIN analysis."""
        recommendations = []

        for condition in join_conditions:
            left_table = condition.get("left_table", tables[0] if tables else "table1")
            right_table = condition.get(
                "right_table", tables[1] if len(tables) > 1 else "table2"
            )
            left_column = condition.get("left_column", "id")
            right_column = condition.get("right_column", "foreign_id")

            # Left side index
            rec = IndexRecommendation(
                table_name=left_table,
                column_names=[left_column],
                index_type=IndexType.BTREE,
                priority=IndexPriority.HIGH,
                estimated_impact="3-15x faster joins",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    left_table, [left_column], IndexType.BTREE
                ),
                rationale=f"SQL JOIN optimization for {left_table}.{left_column}",
                query_patterns=["SQL JOIN operations"],
                performance_gain=self.performance_weights["foreign_key"],
                size_estimate_mb=self._estimate_index_size([left_column]),
            )
            recommendations.append(rec)

            # Right side index
            rec = IndexRecommendation(
                table_name=right_table,
                column_names=[right_column],
                index_type=IndexType.BTREE,
                priority=IndexPriority.HIGH,
                estimated_impact="3-15x faster joins",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    right_table, [right_column], IndexType.BTREE
                ),
                rationale=f"SQL JOIN optimization for {right_table}.{right_column}",
                query_patterns=["SQL JOIN operations"],
                performance_gain=self.performance_weights["foreign_key"],
                size_estimate_mb=self._estimate_index_size([right_column]),
            )
            recommendations.append(rec)

        return recommendations

    def _recommend_filter_indexes_from_sql(
        self, tables: List[str], where_conditions: List[Dict[str, str]]
    ) -> List[IndexRecommendation]:
        """Recommend indexes based on SQL WHERE clause analysis."""
        recommendations = []

        for condition in where_conditions:
            table = condition.get("table", tables[0] if tables else "table1")
            column = condition.get("column", "status")
            operator = condition.get("operator", "=")

            # Determine index type based on operator
            if operator in ["=", "IN"]:
                index_type = IndexType.BTREE
                priority = IndexPriority.HIGH
                impact = "5-20x faster equality queries"
            elif operator in [">", "<", ">=", "<=", "BETWEEN"]:
                index_type = IndexType.BTREE
                priority = IndexPriority.MEDIUM
                impact = "2-10x faster range queries"
            elif operator in ["LIKE", "ILIKE"]:
                index_type = (
                    IndexType.GIN
                    if self.dialect == SQLDialect.POSTGRESQL
                    else IndexType.BTREE
                )
                priority = IndexPriority.MEDIUM
                impact = "2-8x faster text search"
            else:
                index_type = IndexType.BTREE
                priority = IndexPriority.LOW
                impact = "2-5x faster queries"

            rec = IndexRecommendation(
                table_name=table,
                column_names=[column],
                index_type=index_type,
                priority=priority,
                estimated_impact=impact,
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    table, [column], index_type
                ),
                rationale=f"WHERE clause optimization for {table}.{column} {operator}",
                query_patterns=[f"WHERE {column} {operator}"],
                performance_gain=self.performance_weights["filter"],
                size_estimate_mb=self._estimate_index_size([column]),
            )
            recommendations.append(rec)

        return recommendations

    def _recommend_group_by_indexes(
        self, tables: List[str], group_by_columns: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for GROUP BY optimization."""
        recommendations = []

        if not group_by_columns:
            return recommendations

        primary_table = tables[0] if tables else "table1"

        # Single column indexes
        for column in group_by_columns:
            rec = IndexRecommendation(
                table_name=primary_table,
                column_names=[column],
                index_type=IndexType.BTREE,
                priority=IndexPriority.MEDIUM,
                estimated_impact="2-8x faster aggregations",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    primary_table, [column], IndexType.BTREE
                ),
                rationale=f"GROUP BY optimization for {column}",
                query_patterns=["GROUP BY aggregations"],
                performance_gain=self.performance_weights["group_by"],
                size_estimate_mb=self._estimate_index_size([column]),
            )
            recommendations.append(rec)

        # Composite index for multiple GROUP BY columns
        if len(group_by_columns) > 1:
            rec = IndexRecommendation(
                table_name=primary_table,
                column_names=group_by_columns,
                index_type=IndexType.COMPOSITE,
                priority=IndexPriority.HIGH,
                estimated_impact="5-15x faster multi-column aggregations",
                maintenance_cost="Medium",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    primary_table, group_by_columns, IndexType.COMPOSITE
                ),
                rationale=f"Composite GROUP BY optimization for {', '.join(group_by_columns)}",
                query_patterns=["Multi-column GROUP BY"],
                performance_gain=self.performance_weights["composite"],
                size_estimate_mb=self._estimate_index_size(group_by_columns),
            )
            recommendations.append(rec)

        return recommendations

    def _recommend_sort_indexes(
        self, tables: List[str], order_by_columns: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for ORDER BY optimization."""
        recommendations = []

        if not order_by_columns:
            return recommendations

        primary_table = tables[0] if tables else "table1"

        rec = IndexRecommendation(
            table_name=primary_table,
            column_names=order_by_columns,
            index_type=IndexType.BTREE,
            priority=IndexPriority.LOW,
            estimated_impact="2-5x faster sorting",
            maintenance_cost="Low",
            sql_dialect=self.dialect,
            create_statement=self._generate_create_statement(
                primary_table, order_by_columns, IndexType.BTREE
            ),
            rationale=f"ORDER BY optimization for {', '.join(order_by_columns)}",
            query_patterns=["ORDER BY sorting"],
            performance_gain=self.performance_weights["sort"],
            size_estimate_mb=self._estimate_index_size(order_by_columns),
        )
        recommendations.append(rec)

        return recommendations

    def _recommend_covering_indexes(
        self, query: OptimizedQuery, tables: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend covering indexes to eliminate table lookups."""
        recommendations = []

        if not tables:
            return recommendations

        primary_table = tables[0]

        # Extract frequently selected columns from the query
        selected_columns = self._extract_selected_columns(query.optimized_sql)

        if (
            len(selected_columns) > 1 and len(selected_columns) <= 5
        ):  # Practical limit for covering indexes
            rec = IndexRecommendation(
                table_name=primary_table,
                column_names=selected_columns[:3],  # Limit to first 3 columns
                index_type=IndexType.COVERING,
                priority=IndexPriority.MEDIUM,
                estimated_impact="2-6x faster SELECT operations",
                maintenance_cost="High",
                sql_dialect=self.dialect,
                create_statement=self._generate_covering_index_statement(
                    primary_table,
                    selected_columns[:1],  # Index column
                    selected_columns[1:3],  # Include columns
                ),
                rationale="Covering index to eliminate table lookups",
                query_patterns=["SELECT with multiple columns"],
                performance_gain=self.performance_weights["covering"],
                size_estimate_mb=self._estimate_index_size(selected_columns[:3])
                * 1.5,  # Covering indexes are larger
                include_columns=selected_columns[1:3],
            )
            recommendations.append(rec)

        return recommendations

    def _deduplicate_and_prioritize(
        self, recommendations: List[IndexRecommendation]
    ) -> List[IndexRecommendation]:
        """Remove duplicate recommendations and prioritize by impact."""
        # Group by table and columns
        unique_recommendations = {}

        for rec in recommendations:
            key = (rec.table_name, tuple(sorted(rec.column_names)), rec.index_type)

            if key not in unique_recommendations:
                unique_recommendations[key] = rec
            else:
                # Keep the one with higher priority or performance gain
                existing = unique_recommendations[key]
                if (
                    rec.priority.value
                    < existing.priority.value  # Lower enum value = higher priority
                    or rec.performance_gain > existing.performance_gain
                ):
                    unique_recommendations[key] = rec

        # Sort by priority and performance gain
        result = list(unique_recommendations.values())
        priority_order = {p: i for i, p in enumerate(IndexPriority)}

        result.sort(key=lambda x: (priority_order[x.priority], -x.performance_gain))

        return result

    def _find_redundant_indexes(
        self, recommendations: List[IndexRecommendation], existing_indexes: List[str]
    ) -> List[str]:
        """Find existing indexes that are redundant given the recommendations."""
        redundant = []

        # Simple heuristic: if we recommend a composite index that covers an existing single-column index
        for existing in existing_indexes:
            for rec in recommendations:
                if (
                    rec.index_type == IndexType.COMPOSITE
                    and len(rec.column_names) > 1
                    and any(col in existing.lower() for col in rec.column_names)
                ):
                    if existing not in redundant:
                        redundant.append(existing)

        return redundant

    def _find_missing_critical_indexes(
        self, recommendations: List[IndexRecommendation]
    ) -> List[IndexRecommendation]:
        """Find recommendations that are critical and should be implemented immediately."""
        return [
            rec for rec in recommendations if rec.priority == IndexPriority.CRITICAL
        ]

    def _generate_analysis_summary(
        self,
        recommendations: List[IndexRecommendation],
        redundant_indexes: List[str],
        missing_critical: List[IndexRecommendation],
        total_estimated_gain: float,
    ) -> str:
        """Generate a summary of the index analysis."""
        summary = "Index Analysis Summary\n"
        summary += "=====================\n\n"
        summary += f"Total recommendations: {len(recommendations)}\n"
        summary += f"Critical recommendations: {len(missing_critical)}\n"
        summary += f"Redundant existing indexes: {len(redundant_indexes)}\n"
        summary += f"Total estimated performance gain: {total_estimated_gain:.1f}x\n\n"

        # Priority breakdown
        priority_counts = {}
        for rec in recommendations:
            priority_counts[rec.priority] = priority_counts.get(rec.priority, 0) + 1

        summary += "Recommendations by priority:\n"
        for priority, count in priority_counts.items():
            summary += f"  {priority.value.title()}: {count}\n"

        summary += "\nTop 3 critical recommendations:\n"
        for i, rec in enumerate(missing_critical[:3], 1):
            summary += f"  {i}. {rec.table_name}.{','.join(rec.column_names)} - {rec.estimated_impact}\n"

        return summary

    # Utility methods for SQL parsing and analysis

    def _extract_table_names(self, sql: str) -> List[str]:
        """Extract table names from SQL query."""
        # Simple regex to find table names after FROM and JOIN
        from_pattern = r"FROM\s+(\w+)"
        join_pattern = r"JOIN\s+(\w+)"

        tables = []
        tables.extend(re.findall(from_pattern, sql, re.IGNORECASE))
        tables.extend(re.findall(join_pattern, sql, re.IGNORECASE))

        return list(set(tables))  # Remove duplicates

    def _extract_join_conditions(self, sql: str) -> List[Dict[str, str]]:
        """Extract JOIN conditions from SQL query."""
        # Pattern to match JOIN ... ON conditions
        join_pattern = r"JOIN\s+(\w+)\s+\w*\s*ON\s+(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)"
        matches = re.findall(join_pattern, sql, re.IGNORECASE)

        conditions = []
        for match in matches:
            right_table, left_table, left_column, right_table_alias, right_column = (
                match
            )
            conditions.append(
                {
                    "left_table": left_table,
                    "left_column": left_column,
                    "right_table": right_table,
                    "right_column": right_column,
                }
            )

        return conditions

    def _extract_where_conditions(self, sql: str) -> List[Dict[str, str]]:
        """Extract WHERE conditions from SQL query."""
        # Pattern to match WHERE conditions
        where_pattern = r"WHERE\s+.*?(\w+)\.?(\w+)\s*(=|>|<|>=|<=|LIKE|IN|BETWEEN)\s*"
        matches = re.findall(where_pattern, sql, re.IGNORECASE)

        conditions = []
        for match in matches:
            table, column, operator = match
            conditions.append(
                {
                    "table": table if "." in sql else "main_table",
                    "column": column,
                    "operator": operator.upper(),
                }
            )

        return conditions

    def _extract_group_by_columns(self, sql: str) -> List[str]:
        """Extract GROUP BY columns from SQL query."""
        group_by_pattern = r"GROUP\s+BY\s+([\w\s,]+)"
        match = re.search(group_by_pattern, sql, re.IGNORECASE)

        if match:
            columns_str = match.group(1)
            return [col.strip() for col in columns_str.split(",")]

        return []

    def _extract_order_by_columns(self, sql: str) -> List[str]:
        """Extract ORDER BY columns from SQL query."""
        order_by_pattern = r"ORDER\s+BY\s+([\w\s,]+?)(?:\s+ASC|\s+DESC|$|\s+LIMIT)"
        match = re.search(order_by_pattern, sql, re.IGNORECASE)

        if match:
            columns_str = match.group(1)
            return [
                col.strip().split()[0] for col in columns_str.split(",")
            ]  # Remove ASC/DESC

        return []

    def _extract_selected_columns(self, sql: str) -> List[str]:
        """Extract selected columns from SQL query."""
        # Simple extraction - look for columns after SELECT
        select_pattern = r"SELECT\s+(.*?)\s+FROM"
        match = re.search(select_pattern, sql, re.IGNORECASE | re.DOTALL)

        if match:
            select_clause = match.group(1)
            if "*" in select_clause:
                return []  # Can't optimize SELECT *

            # Extract individual columns (simple approach)
            columns = []
            for part in select_clause.split(","):
                part = part.strip()
                # Remove aliases and functions
                if " AS " in part.upper():
                    part = part.split(" AS ")[0].strip()
                if "(" in part:  # Skip aggregate functions
                    continue
                if "." in part:
                    part = part.split(".")[1]  # Remove table prefix
                columns.append(part)

            return columns[:5]  # Limit to 5 columns

        return []

    def _generate_create_statement(
        self, table: str, columns: List[str], index_type: IndexType
    ) -> str:
        """Generate CREATE INDEX statement."""
        index_name = f"idx_{table}_{'_'.join(columns)}"
        columns_str = ", ".join(columns)

        if self.dialect == SQLDialect.POSTGRESQL:
            if index_type == IndexType.GIN:
                return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} USING gin ({columns_str});"
            elif index_type == IndexType.GIST:
                return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} USING gist ({columns_str});"
            else:
                return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} ({columns_str});"

        elif self.dialect == SQLDialect.MYSQL:
            return f"CREATE INDEX {index_name} ON {table} ({columns_str});"

        elif self.dialect == SQLDialect.SQLITE:
            return f"CREATE INDEX {index_name} ON {table} ({columns_str});"

        else:
            return f"CREATE INDEX {index_name} ON {table} ({columns_str});"

    def _generate_partial_index_statement(
        self, table: str, column: str, selectivity: float
    ) -> str:
        """Generate partial index CREATE statement."""
        index_name = f"idx_{table}_{column}_partial"

        if self.dialect == SQLDialect.POSTGRESQL:
            # Example partial condition - would need real data analysis
            condition = f"{column} IS NOT NULL AND {column} != ''"
            return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} ({column}) WHERE {condition};"

        # Fallback to regular index for databases that don't support partial indexes
        return self._generate_create_statement(table, [column], IndexType.BTREE)

    def _generate_covering_index_statement(
        self, table: str, index_columns: List[str], include_columns: List[str]
    ) -> str:
        """Generate covering index CREATE statement."""
        index_name = f"idx_{table}_{'_'.join(index_columns)}_covering"
        index_cols_str = ", ".join(index_columns)

        if self.dialect == SQLDialect.POSTGRESQL and include_columns:
            include_cols_str = ", ".join(include_columns)
            return f"CREATE INDEX CONCURRENTLY {index_name} ON {table} ({index_cols_str}) INCLUDE ({include_cols_str});"

        # Fallback to composite index
        all_columns = index_columns + include_columns
        return self._generate_create_statement(table, all_columns, IndexType.COMPOSITE)

    def _estimate_index_size(self, columns: List[str]) -> float:
        """Estimate index size in MB."""
        # Simple heuristic: 10MB per million rows per column
        base_size_per_column = 10.0
        return len(columns) * base_size_per_column

    # Pattern information extraction methods (would be implemented based on actual opportunity structure)

    def _extract_qma_pattern_info(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, Any]:
        """Extract Query→Merge→Aggregate pattern information."""
        return {
            "join_conditions": [
                {
                    "left_table": "users",
                    "left_column": "id",
                    "right_table": "orders",
                    "right_column": "user_id",
                }
            ],
            "filter_columns": ["status", "created_at"],
            "group_by_columns": ["region", "category"],
            "primary_table": "users",
        }

    def _extract_multiple_query_info(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, Any]:
        """Extract multiple queries pattern information."""
        return {
            "common_filters": {
                "users": {"status": 0.8, "active": 0.05},  # selectivity
                "orders": {"status": 0.3},
            }
        }

    def _extract_redundancy_info(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, Any]:
        """Extract redundancy pattern information."""
        return {
            "frequent_access": {
                "users": {"email": 0.9, "status": 0.85},
                "orders": {"user_id": 0.95},
            }
        }

    def _extract_join_info_from_opportunity(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, List[Dict[str, str]]]:
        """Extract join information from opportunity."""
        return {"users_TO_orders": [{"left_column": "id", "right_column": "user_id"}]}

    def _extract_aggregation_info_from_opportunity(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, Any]:
        """Extract aggregation information from opportunity."""
        return {
            "table": "orders",
            "group_by_columns": ["region", "status"],
            "aggregate_columns": ["total", "quantity"],
        }

    def _extract_filter_info_from_opportunity(
        self, opportunity: OptimizationOpportunity
    ) -> Dict[str, Dict[str, List[str]]]:
        """Extract filter information from opportunity."""
        return {
            "users": {"status": ["equality"], "created_at": ["range"]},
            "orders": {"total": ["range"], "status": ["equality"]},
        }

    def _recommend_aggregation_indexes(
        self, table: str, group_by_columns: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for aggregation operations."""
        recommendations = []

        rec = IndexRecommendation(
            table_name=table,
            column_names=group_by_columns,
            index_type=IndexType.BTREE,
            priority=IndexPriority.HIGH,
            estimated_impact="5-20x faster aggregations",
            maintenance_cost="Medium",
            sql_dialect=self.dialect,
            create_statement=self._generate_create_statement(
                table, group_by_columns, IndexType.BTREE
            ),
            rationale=f"Aggregation optimization for GROUP BY {', '.join(group_by_columns)}",
            query_patterns=["Aggregation queries"],
            performance_gain=self.performance_weights["group_by"],
            size_estimate_mb=self._estimate_index_size(group_by_columns),
        )
        recommendations.append(rec)

        return recommendations

    def _recommend_aggregation_covering_indexes(
        self, table: str, group_by_columns: List[str], aggregate_columns: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend covering indexes for aggregation operations."""
        recommendations = []

        if len(group_by_columns) + len(aggregate_columns) <= 5:  # Practical limit
            rec = IndexRecommendation(
                table_name=table,
                column_names=group_by_columns,
                index_type=IndexType.COVERING,
                priority=IndexPriority.MEDIUM,
                estimated_impact="3-12x faster aggregations",
                maintenance_cost="High",
                sql_dialect=self.dialect,
                create_statement=self._generate_covering_index_statement(
                    table, group_by_columns, aggregate_columns
                ),
                rationale="Covering index for aggregation operations",
                query_patterns=["Aggregation with covering"],
                performance_gain=self.performance_weights["covering"],
                size_estimate_mb=self._estimate_index_size(
                    group_by_columns + aggregate_columns
                )
                * 1.5,
                include_columns=aggregate_columns,
            )
            recommendations.append(rec)

        return recommendations

    def _recommend_filter_indexes(
        self, table: str, column: str, filter_types: List[str]
    ) -> List[IndexRecommendation]:
        """Recommend indexes for filter operations."""
        recommendations = []

        # Determine best index type based on filter types
        if "equality" in filter_types:
            index_type = IndexType.BTREE
            priority = IndexPriority.HIGH
            impact = "5-25x faster equality queries"
        elif "range" in filter_types:
            index_type = IndexType.BTREE
            priority = IndexPriority.MEDIUM
            impact = "3-15x faster range queries"
        else:
            index_type = IndexType.BTREE
            priority = IndexPriority.LOW
            impact = "2-8x faster queries"

        rec = IndexRecommendation(
            table_name=table,
            column_names=[column],
            index_type=index_type,
            priority=priority,
            estimated_impact=impact,
            maintenance_cost="Low",
            sql_dialect=self.dialect,
            create_statement=self._generate_create_statement(
                table, [column], index_type
            ),
            rationale=f"Filter optimization for {table}.{column}",
            query_patterns=[f"Filter on {column}"],
            performance_gain=self.performance_weights["filter"],
            size_estimate_mb=self._estimate_index_size([column]),
        )
        recommendations.append(rec)

        return recommendations

    def _recommend_optimized_join_indexes(
        self, table_pair: str, conditions: List[Dict[str, str]]
    ) -> List[IndexRecommendation]:
        """Recommend optimized indexes for join operations."""
        recommendations = []

        left_table, right_table = table_pair.split("_TO_")

        for condition in conditions:
            # High-priority join indexes
            rec = IndexRecommendation(
                table_name=left_table,
                column_names=[condition["left_column"]],
                index_type=IndexType.BTREE,
                priority=IndexPriority.CRITICAL,
                estimated_impact="10-50x faster joins",
                maintenance_cost="Low",
                sql_dialect=self.dialect,
                create_statement=self._generate_create_statement(
                    left_table, [condition["left_column"]], IndexType.BTREE
                ),
                rationale=f"Critical join optimization for {left_table}.{condition['left_column']}",
                query_patterns=["Critical join operations"],
                performance_gain=self.performance_weights["foreign_key"],
                size_estimate_mb=self._estimate_index_size([condition["left_column"]]),
            )
            recommendations.append(rec)

        return recommendations

    def generate_implementation_plan(self, analysis_result: IndexAnalysisResult) -> str:
        """Generate a step-by-step implementation plan for the recommended indexes."""
        plan = "Index Implementation Plan\n"
        plan += "=========================\n\n"

        # Phase 1: Critical indexes
        critical_recs = [
            r
            for r in analysis_result.recommendations
            if r.priority == IndexPriority.CRITICAL
        ]
        if critical_recs:
            plan += "Phase 1: Critical Indexes (Implement Immediately)\n"
            plan += "-" * 50 + "\n"
            for i, rec in enumerate(critical_recs, 1):
                plan += f"{i}. {rec.create_statement}\n"
                plan += f"   Impact: {rec.estimated_impact}\n"
                plan += f"   Rationale: {rec.rationale}\n\n"

        # Phase 2: High priority indexes
        high_recs = [
            r
            for r in analysis_result.recommendations
            if r.priority == IndexPriority.HIGH
        ]
        if high_recs:
            plan += "Phase 2: High Priority Indexes (Implement Within Week)\n"
            plan += "-" * 55 + "\n"
            for i, rec in enumerate(high_recs, 1):
                plan += f"{i}. {rec.create_statement}\n"
                plan += f"   Impact: {rec.estimated_impact}\n\n"

        # Phase 3: Medium/Low priority indexes
        other_recs = [
            r
            for r in analysis_result.recommendations
            if r.priority in [IndexPriority.MEDIUM, IndexPriority.LOW]
        ]
        if other_recs:
            plan += "Phase 3: Additional Optimizations (Implement As Needed)\n"
            plan += "-" * 58 + "\n"
            for i, rec in enumerate(other_recs, 1):
                plan += f"{i}. {rec.create_statement}\n"

        # Cleanup recommendations
        if analysis_result.redundant_indexes:
            plan += "\nCleanup: Remove Redundant Indexes\n"
            plan += "-" * 35 + "\n"
            for index in analysis_result.redundant_indexes:
                plan += f"DROP INDEX {index};\n"

        plan += f"\nTotal Expected Performance Gain: {analysis_result.total_estimated_gain:.1f}x\n"

        return plan
