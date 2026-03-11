"""
SQLite-Specific Query Optimizer and Index Recommendation Engine

Extends the DataFlow optimization system with SQLite-specific features:
- SQLite query plan analysis and optimization
- Partial index recommendations for SQLite
- WAL mode optimization strategies
- SQLite-specific performance tuning
- Database file size and fragmentation analysis
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .index_recommendation_engine import (
    IndexAnalysisResult,
    IndexPriority,
    IndexRecommendation,
    IndexRecommendationEngine,
    IndexType,
    SQLDialect,
)
from .sql_query_optimizer import OptimizedQuery
from .workflow_analyzer import OptimizationOpportunity, PatternType

logger = logging.getLogger(__name__)


class SQLiteOptimizationType(Enum):
    """Types of SQLite-specific optimizations."""

    PARTIAL_INDEX = "partial_index"
    EXPRESSION_INDEX = "expression_index"
    WAL_OPTIMIZATION = "wal_optimization"
    VACUUM_OPTIMIZATION = "vacuum_optimization"
    PRAGMA_TUNING = "pragma_tuning"
    FILE_SIZE_OPTIMIZATION = "file_size_optimization"
    CACHE_OPTIMIZATION = "cache_optimization"


@dataclass
class SQLitePragmaRecommendation:
    """SQLite PRAGMA setting recommendation."""

    pragma_name: str
    current_value: Optional[str]
    recommended_value: str
    rationale: str
    priority: IndexPriority
    estimated_impact: str
    requirements: List[str]


@dataclass
class SQLiteOptimizationResult:
    """Results from SQLite-specific optimization analysis."""

    index_recommendations: List[IndexRecommendation]
    pragma_recommendations: List[SQLitePragmaRecommendation]
    wal_recommendations: List[str]
    vacuum_recommendations: List[str]
    file_size_analysis: Dict[str, Any]
    performance_insights: Dict[str, Any]
    optimization_priority_order: List[str]
    estimated_total_improvement: float


class SQLiteQueryOptimizer(IndexRecommendationEngine):
    """
    SQLite-specific query optimizer and index recommendation engine.

    Extends the base IndexRecommendationEngine with SQLite-specific features:
    - Partial index analysis and recommendations
    - Expression index opportunities
    - WAL mode optimization strategies
    - SQLite-specific query patterns
    - Database file organization recommendations
    """

    def __init__(self, database_path: Optional[str] = None, **kwargs):
        super().__init__(dialect=SQLDialect.SQLITE)
        self.database_path = database_path
        self.sqlite_features = self._initialize_sqlite_features()
        self.pragma_optimizations = self._initialize_pragma_optimizations()

    def _initialize_sqlite_features(self) -> Dict[str, Any]:
        """Initialize SQLite-specific feature support."""
        return {
            "partial_indexes": True,
            "expression_indexes": True,
            "fts5": True,
            "json1": True,
            "rtree": False,  # Requires extension
            "wal_mode": True,
            "memory_mapping": True,
            "incremental_vacuum": True,
            "secure_delete": True,
            "case_sensitive_like": True,
        }

    def _initialize_pragma_optimizations(self) -> Dict[str, Dict[str, Any]]:
        """Initialize PRAGMA optimization recommendations."""
        return {
            "cache_size": {
                "recommended_values": {
                    "small_db": "-32768",  # 32MB
                    "medium_db": "-65536",  # 64MB
                    "large_db": "-131072",  # 128MB
                },
                "rationale": "Larger cache reduces disk I/O and improves query performance",
                "priority": IndexPriority.HIGH,
            },
            "journal_mode": {
                "recommended_values": {
                    "single_user": "WAL",
                    "multi_user": "WAL",
                    "read_only": "DELETE",
                },
                "rationale": "WAL mode allows concurrent reads and better performance",
                "priority": IndexPriority.CRITICAL,
            },
            "synchronous": {
                "recommended_values": {
                    "performance_critical": "NORMAL",
                    "safety_critical": "FULL",
                    "development": "NORMAL",
                },
                "rationale": "Balance between data safety and performance",
                "priority": IndexPriority.MEDIUM,
            },
            "mmap_size": {
                "recommended_values": {
                    "default": "268435456",  # 256MB
                    "large_db": "1073741824",  # 1GB
                },
                "rationale": "Memory-mapped I/O improves read performance",
                "priority": IndexPriority.MEDIUM,
            },
            "temp_store": {
                "recommended_values": {
                    "default": "MEMORY",
                },
                "rationale": "Store temporary tables in memory for better performance",
                "priority": IndexPriority.LOW,
            },
            "auto_vacuum": {
                "recommended_values": {
                    "active_db": "INCREMENTAL",
                    "archive_db": "FULL",
                    "read_only": "NONE",
                },
                "rationale": "Prevent database bloat while minimizing impact",
                "priority": IndexPriority.MEDIUM,
            },
        }

    def analyze_sqlite_optimization_opportunities(
        self,
        opportunities: List[OptimizationOpportunity],
        optimized_queries: List[OptimizedQuery],
        current_pragmas: Optional[Dict[str, str]] = None,
        database_stats: Optional[Dict[str, Any]] = None,
    ) -> SQLiteOptimizationResult:
        """
        Comprehensive SQLite optimization analysis.

        Args:
            opportunities: Optimization opportunities from WorkflowAnalyzer
            optimized_queries: Optimized queries from SQLQueryOptimizer
            current_pragmas: Current PRAGMA settings
            database_stats: Current database statistics

        Returns:
            Comprehensive SQLite optimization recommendations
        """
        logger.info("Starting comprehensive SQLite optimization analysis")

        # Get base index recommendations
        base_analysis = self.analyze_and_recommend(opportunities, optimized_queries)

        # SQLite-specific analysis
        sqlite_indexes = self._analyze_sqlite_specific_indexes(
            opportunities, optimized_queries
        )
        partial_indexes = self._analyze_partial_index_opportunities(
            optimized_queries, database_stats
        )
        expression_indexes = self._analyze_expression_index_opportunities(
            optimized_queries
        )

        # Combine index recommendations
        all_index_recommendations = (
            base_analysis.recommendations
            + sqlite_indexes
            + partial_indexes
            + expression_indexes
        )

        # Deduplicate and prioritize
        final_index_recommendations = self._deduplicate_and_prioritize(
            all_index_recommendations
        )

        # PRAGMA analysis
        pragma_recommendations = self._analyze_pragma_optimizations(
            current_pragmas, database_stats
        )

        # WAL mode analysis
        wal_recommendations = self._analyze_wal_optimizations(
            current_pragmas, opportunities
        )

        # Vacuum analysis
        vacuum_recommendations = self._analyze_vacuum_needs(database_stats)

        # File size analysis
        file_size_analysis = self._analyze_file_size_optimization(database_stats)

        # Performance insights
        performance_insights = self._generate_sqlite_performance_insights(
            final_index_recommendations, pragma_recommendations, database_stats
        )

        # Priority ordering
        optimization_priority = self._determine_optimization_priority(
            final_index_recommendations,
            pragma_recommendations,
            wal_recommendations,
            vacuum_recommendations,
        )

        # Estimate total improvement
        total_improvement = self._estimate_total_performance_improvement(
            final_index_recommendations, pragma_recommendations
        )

        return SQLiteOptimizationResult(
            index_recommendations=final_index_recommendations,
            pragma_recommendations=pragma_recommendations,
            wal_recommendations=wal_recommendations,
            vacuum_recommendations=vacuum_recommendations,
            file_size_analysis=file_size_analysis,
            performance_insights=performance_insights,
            optimization_priority_order=optimization_priority,
            estimated_total_improvement=total_improvement,
        )

    def _analyze_sqlite_specific_indexes(
        self,
        opportunities: List[OptimizationOpportunity],
        optimized_queries: List[OptimizedQuery],
    ) -> List[IndexRecommendation]:
        """Analyze SQLite-specific index opportunities."""
        recommendations = []

        for query in optimized_queries:
            sql = query.optimized_sql.upper()

            # FTS (Full-Text Search) opportunities
            if any(pattern in sql for pattern in ["LIKE '%", "MATCH", "FTS"]):
                fts_recommendations = self._analyze_fts_opportunities(query)
                recommendations.extend(fts_recommendations)

            # JSON path index opportunities (SQLite 3.38+)
            if "JSON_EXTRACT" in sql or "->" in sql or "->>" in sql:
                json_recommendations = self._analyze_json_index_opportunities(query)
                recommendations.extend(json_recommendations)

            # ROWID optimization opportunities
            if "ROWID" in sql or "_ROWID_" in sql:
                rowid_recommendations = self._analyze_rowid_optimization(query)
                recommendations.extend(rowid_recommendations)

        return recommendations

    def _analyze_partial_index_opportunities(
        self,
        optimized_queries: List[OptimizedQuery],
        database_stats: Optional[Dict[str, Any]] = None,
    ) -> List[IndexRecommendation]:
        """Analyze opportunities for partial indexes."""
        recommendations = []

        for query in optimized_queries:
            sql = query.optimized_sql.upper()

            # Look for selective WHERE conditions
            where_patterns = self._extract_selective_where_conditions(sql)

            for pattern in where_patterns:
                if pattern["selectivity"] < 0.1:  # Less than 10% of rows
                    rec = IndexRecommendation(
                        table_name=pattern["table"],
                        column_names=[pattern["column"]],
                        index_type=IndexType.PARTIAL,
                        priority=IndexPriority.HIGH,
                        estimated_impact="5-20x faster selective queries",
                        maintenance_cost="Low",
                        sql_dialect=SQLDialect.SQLITE,
                        create_statement=self._generate_partial_index_statement(
                            pattern["table"], pattern["column"], pattern["condition"]
                        ),
                        rationale=f"Partial index for selective condition: {pattern['condition']}",
                        query_patterns=[f"Selective WHERE {pattern['condition']}"],
                        performance_gain=8.0,
                        size_estimate_mb=self._estimate_index_size([pattern["column"]])
                        * pattern["selectivity"],
                        partial_condition=pattern["condition"],
                    )
                    recommendations.append(rec)

        return recommendations

    def _analyze_expression_index_opportunities(
        self, optimized_queries: List[OptimizedQuery]
    ) -> List[IndexRecommendation]:
        """Analyze opportunities for expression indexes."""
        recommendations = []

        for query in optimized_queries:
            sql = query.optimized_sql.upper()

            # Look for function calls in WHERE clauses
            function_patterns = [
                r"WHERE\s+LOWER\((\w+)\)\s*=",
                r"WHERE\s+UPPER\((\w+)\)\s*=",
                r"WHERE\s+SUBSTR\((\w+),\s*\d+,\s*\d+\)\s*=",
                r"WHERE\s+DATE\((\w+)\)\s*=",
                r"WHERE\s+ABS\((\w+)\)\s*[<>=]",
            ]

            for pattern in function_patterns:
                matches = re.findall(pattern, sql)
                for match in matches:
                    column = match if isinstance(match, str) else match[0]

                    # Generate expression index recommendation
                    expression = self._extract_expression_from_pattern(pattern, column)
                    if expression:
                        rec = IndexRecommendation(
                            table_name="table",  # Would need better table detection
                            column_names=[f"EXPR({expression})"],
                            index_type=IndexType.BTREE,
                            priority=IndexPriority.MEDIUM,
                            estimated_impact="3-10x faster function-based queries",
                            maintenance_cost="Medium",
                            sql_dialect=SQLDialect.SQLITE,
                            create_statement=f"CREATE INDEX idx_expr_{column} ON table ({expression});",
                            rationale=f"Expression index for function: {expression}",
                            query_patterns=[f"Function-based WHERE: {expression}"],
                            performance_gain=5.0,
                            size_estimate_mb=self._estimate_index_size([column]) * 1.2,
                        )
                        recommendations.append(rec)

        return recommendations

    def _analyze_fts_opportunities(
        self, query: OptimizedQuery
    ) -> List[IndexRecommendation]:
        """Analyze Full-Text Search index opportunities."""
        recommendations = []
        sql = query.optimized_sql.upper()

        # Look for text search patterns
        text_search_patterns = [
            r"LIKE\s+'%(\w+)%'",
            r"LIKE\s+'(\w+)%'",
            r"(\w+)\s+LIKE\s+'%\w+%'",
        ]

        text_columns = set()
        for pattern in text_search_patterns:
            matches = re.findall(pattern, sql)
            for match in matches:
                if isinstance(match, tuple):
                    text_columns.update(match)
                else:
                    text_columns.add(match)

        for column in text_columns:
            if column.isalpha():  # Basic validation
                rec = IndexRecommendation(
                    table_name="content_table",  # Would need better detection
                    column_names=[column],
                    index_type=IndexType.GIN,  # FTS in SQLite is similar to GIN
                    priority=IndexPriority.HIGH,
                    estimated_impact="10-50x faster text search",
                    maintenance_cost="Medium",
                    sql_dialect=SQLDialect.SQLITE,
                    create_statement=f"CREATE VIRTUAL TABLE fts_{column} USING fts5({column});",
                    rationale=f"Full-text search index for text column: {column}",
                    query_patterns=["Text search with LIKE"],
                    performance_gain=15.0,
                    size_estimate_mb=self._estimate_index_size([column])
                    * 2.0,  # FTS indexes are larger
                )
                recommendations.append(rec)

        return recommendations

    def _analyze_json_index_opportunities(
        self, query: OptimizedQuery
    ) -> List[IndexRecommendation]:
        """Analyze JSON path index opportunities."""
        recommendations = []
        sql = query.optimized_sql.upper()

        # Look for JSON operations
        json_patterns = [
            r"JSON_EXTRACT\((\w+),\s*'([^']+)'\)",
            r"(\w+)\s*->\s*'([^']+)'",
            r"(\w+)\s*->>\s*'([^']+)'",
        ]

        json_paths = []
        for pattern in json_patterns:
            matches = re.findall(pattern, sql)
            for match in matches:
                if len(match) == 2:
                    column, path = match
                    json_paths.append((column, path))

        for column, path in json_paths:
            rec = IndexRecommendation(
                table_name="json_table",  # Would need better detection
                column_names=[f"{column}->>'{path}'"],
                index_type=IndexType.BTREE,
                priority=IndexPriority.MEDIUM,
                estimated_impact="5-15x faster JSON queries",
                maintenance_cost="Medium",
                sql_dialect=SQLDialect.SQLITE,
                create_statement=f"CREATE INDEX idx_json_{column}_{path.replace('.', '_')} ON table ({column}->'>'{path}');",
                rationale=f"JSON path index for: {column}->>'{path}'",
                query_patterns=[f"JSON path extraction: {path}"],
                performance_gain=7.0,
                size_estimate_mb=self._estimate_index_size([column]),
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_rowid_optimization(
        self, query: OptimizedQuery
    ) -> List[IndexRecommendation]:
        """Analyze ROWID optimization opportunities."""
        recommendations = []
        sql = query.optimized_sql.upper()

        # SQLite ROWID is automatically indexed, but we can suggest optimizations
        if "ROWID" in sql and "ORDER BY" in sql:
            rec = IndexRecommendation(
                table_name="table",
                column_names=["INTEGER PRIMARY KEY"],
                index_type=IndexType.BTREE,
                priority=IndexPriority.LOW,
                estimated_impact="Use explicit INTEGER PRIMARY KEY instead of ROWID",
                maintenance_cost="None",
                sql_dialect=SQLDialect.SQLITE,
                create_statement="-- Use INTEGER PRIMARY KEY in table definition",
                rationale="Explicit INTEGER PRIMARY KEY is clearer and may have slight performance benefits",
                query_patterns=["ROWID usage"],
                performance_gain=1.1,
                size_estimate_mb=0.0,  # No additional storage needed
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_pragma_optimizations(
        self,
        current_pragmas: Optional[Dict[str, str]] = None,
        database_stats: Optional[Dict[str, Any]] = None,
    ) -> List[SQLitePragmaRecommendation]:
        """Analyze PRAGMA setting optimizations."""
        recommendations = []
        current_pragmas = current_pragmas or {}
        database_stats = database_stats or {}

        # Determine database size category
        db_size_mb = database_stats.get("db_size_mb", 0)
        if db_size_mb < 100:
            size_category = "small_db"
        elif db_size_mb < 1000:
            size_category = "medium_db"
        else:
            size_category = "large_db"

        # Cache size optimization
        current_cache = current_pragmas.get("cache_size", "-2000")
        pragma_config = self.pragma_optimizations["cache_size"]
        recommended_cache = pragma_config["recommended_values"].get(
            size_category, "-65536"
        )

        if current_cache != recommended_cache:
            rec = SQLitePragmaRecommendation(
                pragma_name="cache_size",
                current_value=current_cache,
                recommended_value=recommended_cache,
                rationale=pragma_config["rationale"],
                priority=pragma_config["priority"],
                estimated_impact="10-50% query performance improvement",
                requirements=["Sufficient system memory"],
            )
            recommendations.append(rec)

        # Journal mode optimization
        current_journal = current_pragmas.get("journal_mode", "DELETE")
        if current_journal != "WAL":
            pragma_config = self.pragma_optimizations["journal_mode"]
            rec = SQLitePragmaRecommendation(
                pragma_name="journal_mode",
                current_value=current_journal,
                recommended_value="WAL",
                rationale=pragma_config["rationale"],
                priority=pragma_config["priority"],
                estimated_impact="Better concurrency and 20-40% write performance improvement",
                requirements=["File-based database (not :memory:)"],
            )
            recommendations.append(rec)

        # Memory mapping optimization
        current_mmap = current_pragmas.get("mmap_size", "0")
        pragma_config = self.pragma_optimizations["mmap_size"]
        recommended_mmap = pragma_config["recommended_values"].get(
            "large_db" if db_size_mb > 500 else "default"
        )

        if int(current_mmap) < int(recommended_mmap):
            rec = SQLitePragmaRecommendation(
                pragma_name="mmap_size",
                current_value=current_mmap,
                recommended_value=recommended_mmap,
                rationale=pragma_config["rationale"],
                priority=pragma_config["priority"],
                estimated_impact="10-30% read performance improvement",
                requirements=["64-bit system", "Sufficient virtual memory"],
            )
            recommendations.append(rec)

        # Auto-vacuum optimization
        current_vacuum = current_pragmas.get("auto_vacuum", "0")
        fragmentation_ratio = database_stats.get("fragmentation_ratio", 0)

        if fragmentation_ratio > 0.2 and current_vacuum == "0":  # 20% fragmentation
            pragma_config = self.pragma_optimizations["auto_vacuum"]
            rec = SQLitePragmaRecommendation(
                pragma_name="auto_vacuum",
                current_value=current_vacuum,
                recommended_value="INCREMENTAL",
                rationale="High fragmentation detected - " + pragma_config["rationale"],
                priority=IndexPriority.HIGH,
                estimated_impact="Prevent database bloat and improve long-term performance",
                requirements=["Regular PRAGMA incremental_vacuum calls"],
            )
            recommendations.append(rec)

        return recommendations

    def _analyze_wal_optimizations(
        self,
        current_pragmas: Optional[Dict[str, str]] = None,
        opportunities: List[OptimizationOpportunity] = None,
    ) -> List[str]:
        """Analyze WAL mode optimization opportunities."""
        recommendations = []
        current_pragmas = current_pragmas or {}

        current_journal = current_pragmas.get("journal_mode", "DELETE")

        if current_journal != "WAL":
            recommendations.extend(
                [
                    "Enable WAL mode for better concurrent read performance",
                    "WAL mode allows readers to proceed without blocking writers",
                    "Consider WAL checkpoint frequency based on write patterns",
                ]
            )
        else:
            # WAL is enabled, provide optimization tips
            current_checkpoint = current_pragmas.get("wal_autocheckpoint", "1000")

            if int(current_checkpoint) > 10000:
                recommendations.append(
                    "Consider reducing wal_autocheckpoint for more frequent checkpoints"
                )
            elif int(current_checkpoint) < 100:
                recommendations.append(
                    "Consider increasing wal_autocheckpoint to reduce checkpoint overhead"
                )

            recommendations.extend(
                [
                    "Monitor WAL file size growth patterns",
                    "Use PRAGMA wal_checkpoint(RESTART) periodically for maintenance",
                    "Consider busy_timeout setting for concurrent access patterns",
                ]
            )

        return recommendations

    def _analyze_vacuum_needs(
        self, database_stats: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Analyze database vacuum needs."""
        recommendations = []
        database_stats = database_stats or {}

        fragmentation_ratio = database_stats.get("fragmentation_ratio", 0)
        db_size_mb = database_stats.get("db_size_mb", 0)
        free_pages = database_stats.get("free_pages", 0)

        if fragmentation_ratio > 0.25:  # 25% fragmentation
            recommendations.extend(
                [
                    "High fragmentation detected - run VACUUM to reclaim space",
                    f"Current fragmentation: {fragmentation_ratio:.1%}",
                    "Consider enabling auto_vacuum=INCREMENTAL for future maintenance",
                ]
            )
        elif fragmentation_ratio > 0.1:  # 10% fragmentation
            recommendations.extend(
                [
                    "Moderate fragmentation detected - consider running VACUUM",
                    "Monitor fragmentation trends over time",
                ]
            )

        if free_pages > 1000:
            recommendations.append(
                f"Database has {free_pages} free pages - VACUUM could reclaim space"
            )

        if (
            db_size_mb > 1000 and fragmentation_ratio > 0.05
        ):  # Large database with any fragmentation
            recommendations.extend(
                [
                    "Large database detected - consider incremental maintenance strategy",
                    "Use PRAGMA incremental_vacuum(N) for gradual cleanup",
                ]
            )

        return recommendations

    def _analyze_file_size_optimization(
        self, database_stats: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Analyze database file size optimization opportunities."""
        database_stats = database_stats or {}

        analysis = {
            "current_size_mb": database_stats.get("db_size_mb", 0),
            "wal_size_mb": database_stats.get("wal_size_mb", 0),
            "total_size_mb": database_stats.get("total_size_mb", 0),
            "fragmentation_ratio": database_stats.get("fragmentation_ratio", 0),
            "optimization_potential": "low",
            "recommendations": [],
            "estimated_savings_mb": 0,
        }

        fragmentation_ratio = analysis["fragmentation_ratio"]
        current_size = analysis["current_size_mb"]

        if fragmentation_ratio > 0.25:
            analysis["optimization_potential"] = "high"
            analysis["estimated_savings_mb"] = current_size * fragmentation_ratio
            analysis["recommendations"].extend(
                [
                    "Run VACUUM to reclaim fragmented space",
                    "Enable auto_vacuum=INCREMENTAL to prevent future fragmentation",
                    f"Potential space savings: {analysis['estimated_savings_mb']:.1f}MB",
                ]
            )
        elif fragmentation_ratio > 0.1:
            analysis["optimization_potential"] = "medium"
            analysis["estimated_savings_mb"] = current_size * fragmentation_ratio * 0.8
            analysis["recommendations"].extend(
                [
                    "Consider running VACUUM during maintenance window",
                    f"Potential space savings: {analysis['estimated_savings_mb']:.1f}MB",
                ]
            )

        # WAL file analysis
        wal_size = analysis["wal_size_mb"]
        if wal_size > current_size * 0.1:  # WAL > 10% of database size
            analysis["recommendations"].extend(
                [
                    f"Large WAL file detected: {wal_size:.1f}MB",
                    "Consider running PRAGMA wal_checkpoint(RESTART)",
                    "Review wal_autocheckpoint setting",
                ]
            )

        return analysis

    def _generate_sqlite_performance_insights(
        self,
        index_recommendations: List[IndexRecommendation],
        pragma_recommendations: List[SQLitePragmaRecommendation],
        database_stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate SQLite-specific performance insights."""
        insights = {
            "index_analysis": {
                "total_recommended": len(index_recommendations),
                "critical_indexes": len(
                    [
                        r
                        for r in index_recommendations
                        if r.priority == IndexPriority.CRITICAL
                    ]
                ),
                "partial_indexes": len(
                    [
                        r
                        for r in index_recommendations
                        if r.index_type == IndexType.PARTIAL
                    ]
                ),
                "estimated_total_gain": sum(
                    r.performance_gain for r in index_recommendations
                ),
            },
            "pragma_analysis": {
                "total_recommendations": len(pragma_recommendations),
                "critical_pragmas": len(
                    [
                        r
                        for r in pragma_recommendations
                        if r.priority == IndexPriority.CRITICAL
                    ]
                ),
                "high_impact_pragmas": [
                    r.pragma_name
                    for r in pragma_recommendations
                    if r.priority in [IndexPriority.CRITICAL, IndexPriority.HIGH]
                ],
            },
            "database_health": {
                "size_mb": database_stats.get("db_size_mb", 0) if database_stats else 0,
                "fragmentation_status": (
                    "high"
                    if database_stats
                    and database_stats.get("fragmentation_ratio", 0) > 0.25
                    else "acceptable"
                ),
                "wal_status": (
                    "active"
                    if database_stats and database_stats.get("wal_size_mb", 0) > 0
                    else "inactive"
                ),
            },
            "optimization_focus": [],
        }

        # Determine optimization focus areas
        if insights["index_analysis"]["critical_indexes"] > 0:
            insights["optimization_focus"].append("Critical index creation")

        if insights["pragma_analysis"]["critical_pragmas"] > 0:
            insights["optimization_focus"].append("PRAGMA setting optimization")

        if insights["database_health"]["fragmentation_status"] == "high":
            insights["optimization_focus"].append("Database maintenance (VACUUM)")

        if insights["database_health"]["wal_status"] == "inactive":
            insights["optimization_focus"].append("WAL mode activation")

        return insights

    def _determine_optimization_priority(
        self,
        index_recommendations: List[IndexRecommendation],
        pragma_recommendations: List[SQLitePragmaRecommendation],
        wal_recommendations: List[str],
        vacuum_recommendations: List[str],
    ) -> List[str]:
        """Determine the priority order for optimization implementation."""
        priority_order = []

        # Phase 1: Critical infrastructure
        critical_pragmas = [
            r for r in pragma_recommendations if r.priority == IndexPriority.CRITICAL
        ]
        if critical_pragmas:
            priority_order.append(
                "Phase 1: Critical PRAGMA settings (journal_mode, etc.)"
            )

        # Phase 2: Critical indexes
        critical_indexes = [
            r for r in index_recommendations if r.priority == IndexPriority.CRITICAL
        ]
        if critical_indexes:
            priority_order.append("Phase 2: Critical index creation")

        # Phase 3: Database maintenance
        if vacuum_recommendations:
            priority_order.append(
                "Phase 3: Database maintenance (VACUUM, fragmentation)"
            )

        # Phase 4: Performance tuning
        high_priority_pragmas = [
            r for r in pragma_recommendations if r.priority == IndexPriority.HIGH
        ]
        high_priority_indexes = [
            r for r in index_recommendations if r.priority == IndexPriority.HIGH
        ]
        if high_priority_pragmas or high_priority_indexes:
            priority_order.append(
                "Phase 4: Performance optimization (cache_size, high-priority indexes)"
            )

        # Phase 5: Fine-tuning
        medium_low_items = [
            r
            for r in pragma_recommendations + index_recommendations
            if r.priority in [IndexPriority.MEDIUM, IndexPriority.LOW]
        ]
        if medium_low_items:
            priority_order.append("Phase 5: Fine-tuning and optional optimizations")

        return priority_order

    def _estimate_total_performance_improvement(
        self,
        index_recommendations: List[IndexRecommendation],
        pragma_recommendations: List[SQLitePragmaRecommendation],
    ) -> float:
        """Estimate total performance improvement from all recommendations."""
        # Base improvement from indexes
        index_improvement = sum(r.performance_gain for r in index_recommendations)

        # Estimate improvement from PRAGMA settings
        pragma_improvement = 0.0
        for rec in pragma_recommendations:
            if rec.pragma_name == "journal_mode" and rec.recommended_value == "WAL":
                pragma_improvement += 2.0  # WAL mode provides significant improvement
            elif rec.pragma_name == "cache_size":
                pragma_improvement += 1.5  # Cache size improvements
            elif rec.pragma_name == "mmap_size":
                pragma_improvement += 1.2  # Memory mapping improvements
            else:
                pragma_improvement += 0.5  # Other PRAGMA improvements

        # Apply diminishing returns (optimizations don't simply multiply)
        total_multiplier = index_improvement + pragma_improvement
        if total_multiplier > 10:
            # Apply logarithmic scaling for very high improvements
            import math

            total_multiplier = 10 + math.log(total_multiplier - 9)

        return total_multiplier

    # Helper methods

    def _extract_selective_where_conditions(self, sql: str) -> List[Dict[str, Any]]:
        """Extract WHERE conditions that might benefit from partial indexes."""
        conditions = []

        # Simple patterns for demonstration - in practice, would need more sophisticated parsing
        patterns = [
            r"WHERE\s+(\w+)\s*=\s*'([^']+)'",
            r"WHERE\s+(\w+)\s*IS\s+NOT\s+NULL",
            r"WHERE\s+(\w+)\s*>\s*(\d+)",
            r"WHERE\s+(\w+)\s*<\s*(\d+)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple) and len(match) >= 2:
                    column, value = match[0], match[1]
                    conditions.append(
                        {
                            "table": "table",  # Would need better table detection
                            "column": column,
                            "condition": (
                                f"{column} = '{value}'"
                                if value.isalpha()
                                else f"{column} = {value}"
                            ),
                            "selectivity": 0.05,  # Estimate - would need actual statistics
                        }
                    )

        return conditions

    def _extract_expression_from_pattern(
        self, pattern: str, column: str
    ) -> Optional[str]:
        """Extract SQL expression from regex pattern."""
        if "LOWER" in pattern:
            return f"LOWER({column})"
        elif "UPPER" in pattern:
            return f"UPPER({column})"
        elif "DATE" in pattern:
            return f"DATE({column})"
        elif "ABS" in pattern:
            return f"ABS({column})"
        elif "SUBSTR" in pattern:
            return f"SUBSTR({column}, 1, 10)"  # Example
        return None

    def _generate_partial_index_statement(
        self, table: str, column: str, condition: str
    ) -> str:
        """Generate CREATE INDEX statement for partial index."""
        index_name = f"idx_{table}_{column}_partial"
        return f"CREATE INDEX {index_name} ON {table} ({column}) WHERE {condition};"

    def generate_sqlite_optimization_report(
        self, optimization_result: SQLiteOptimizationResult
    ) -> str:
        """Generate a comprehensive SQLite optimization report."""
        report = ["SQLite Database Optimization Report", "=" * 40, ""]

        # Executive Summary
        report.extend(
            [
                "EXECUTIVE SUMMARY",
                "-" * 17,
                f"Total Recommendations: {len(optimization_result.index_recommendations + optimization_result.pragma_recommendations)}",
                f"Estimated Performance Improvement: {optimization_result.estimated_total_improvement:.1f}x",
                f"Optimization Priority Areas: {len(optimization_result.optimization_priority_order)} phases",
                "",
            ]
        )

        # Index Recommendations
        if optimization_result.index_recommendations:
            report.extend(
                [
                    "INDEX RECOMMENDATIONS",
                    "-" * 20,
                ]
            )

            for i, rec in enumerate(
                optimization_result.index_recommendations[:5], 1
            ):  # Top 5
                report.extend(
                    [
                        f"{i}. {rec.table_name}.{','.join(rec.column_names)} ({rec.index_type.value})",
                        f"   Priority: {rec.priority.value.title()}",
                        f"   Impact: {rec.estimated_impact}",
                        f"   SQL: {rec.create_statement}",
                        "",
                    ]
                )

        # PRAGMA Recommendations
        if optimization_result.pragma_recommendations:
            report.extend(
                [
                    "PRAGMA OPTIMIZATIONS",
                    "-" * 19,
                ]
            )

            for rec in optimization_result.pragma_recommendations:
                report.extend(
                    [
                        f"PRAGMA {rec.pragma_name}",
                        f"   Current: {rec.current_value}",
                        f"   Recommended: {rec.recommended_value}",
                        f"   Impact: {rec.estimated_impact}",
                        f"   Rationale: {rec.rationale}",
                        "",
                    ]
                )

        # Implementation Plan
        report.extend(
            [
                "IMPLEMENTATION PRIORITY",
                "-" * 23,
            ]
        )

        for i, phase in enumerate(optimization_result.optimization_priority_order, 1):
            report.append(f"{i}. {phase}")

        report.extend(["", "END OF REPORT"])

        return "\n".join(report)
