"""
DataFlow Workflow Analysis Engine

Analyzes workflows to detect common patterns that can be optimized,
particularly Query→Merge→Aggregate sequences that can be converted
to optimized SQL operations for significant performance improvements.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of optimization patterns that can be detected."""

    QUERY_MERGE_AGGREGATE = "query_merge_aggregate"
    MULTIPLE_QUERIES = "multiple_queries"
    REDUNDANT_OPERATIONS = "redundant_operations"
    INEFFICIENT_JOINS = "inefficient_joins"
    MISSING_INDEXES = "missing_indexes"


@dataclass
class OptimizationOpportunity:
    """Represents a detected optimization opportunity."""

    pattern_type: PatternType
    nodes_involved: List[str]
    estimated_improvement: str  # e.g., "10x faster", "90% less memory"
    optimization_strategy: str
    confidence: float  # 0.0 to 1.0
    description: str
    proposed_sql: Optional[str] = None


@dataclass
class WorkflowNode:
    """Simplified representation of a workflow node for analysis."""

    id: str
    type: str
    parameters: Dict[str, Any]
    inputs: List[str]
    outputs: List[str]
    connections: List[Tuple[str, str]]  # (from_node, to_node)


class WorkflowAnalyzer:
    """
    Analyzes DataFlow workflows to detect optimization opportunities.

    The analyzer identifies common patterns like:
    1. Query→Merge→Aggregate sequences that can become single SQL operations
    2. Multiple separate queries that can be combined with JOINs
    3. Redundant operations that can be eliminated
    4. Inefficient join patterns that can be optimized

    Example:
        >>> analyzer = WorkflowAnalyzer()
        >>> workflow = build_sample_workflow()
        >>> opportunities = analyzer.analyze_workflow(workflow)
        >>> for opp in opportunities:
        ...     print(f"Found {opp.pattern_type}: {opp.estimated_improvement}")
    """

    def __init__(self):
        """Initialize the workflow analyzer."""
        self.pattern_detectors = {
            PatternType.QUERY_MERGE_AGGREGATE: self._detect_query_merge_aggregate,
            PatternType.MULTIPLE_QUERIES: self._detect_multiple_queries,
            PatternType.REDUNDANT_OPERATIONS: self._detect_redundant_operations,
            PatternType.INEFFICIENT_JOINS: self._detect_inefficient_joins,
        }

        # Node type mappings
        self.query_nodes = {
            "UserListNode",
            "OrderListNode",
            "ProductListNode",
            "CSVReaderNode",
            "SQLDatabaseNode",
            "AsyncSQLDatabaseNode",
        }

        self.merge_nodes = {"SmartMergeNode", "MergeNode", "JoinNode"}

        self.aggregate_nodes = {"AggregateNode", "GroupByNode", "SumNode", "CountNode"}

        self.filter_nodes = {"NaturalLanguageFilterNode", "FilterNode", "WhereNode"}

    def analyze_workflow(
        self, workflow: Dict[str, Any]
    ) -> List[OptimizationOpportunity]:
        """
        Analyze a workflow and return detected optimization opportunities.

        Args:
            workflow: Dictionary representation of a workflow with nodes and connections

        Returns:
            List of optimization opportunities ordered by estimated impact
        """
        logger.info(f"Analyzing workflow with {len(workflow.get('nodes', {}))} nodes")

        # Convert workflow to internal representation
        nodes = self._parse_workflow(workflow)

        # Detect all patterns
        opportunities = []
        for pattern_type, detector in self.pattern_detectors.items():
            detected = detector(nodes)
            opportunities.extend(detected)

        # Sort by confidence and estimated improvement
        opportunities.sort(
            key=lambda x: (x.confidence, self._impact_score(x.estimated_improvement)),
            reverse=True,
        )

        logger.info(f"Found {len(opportunities)} optimization opportunities")
        return opportunities

    def _parse_workflow(self, workflow: Dict[str, Any]) -> List[WorkflowNode]:
        """Convert workflow dictionary to internal WorkflowNode representation."""
        nodes = []
        workflow_nodes = workflow.get("nodes", {})
        connections = workflow.get("connections", [])

        # Build connection mapping
        node_connections = {}
        for conn in connections:
            from_node = conn.get("from_node")
            to_node = conn.get("to_node")
            if from_node and to_node:
                if from_node not in node_connections:
                    node_connections[from_node] = []
                node_connections[from_node].append(to_node)

        # Create WorkflowNode objects
        for node_id, node_info in workflow_nodes.items():
            node_type = node_info.get("type", "Unknown")
            parameters = node_info.get("parameters", {})

            # Determine inputs and outputs from connections
            inputs = [
                conn["from_node"]
                for conn in connections
                if conn.get("to_node") == node_id
            ]
            outputs = node_connections.get(node_id, [])
            node_conns = [(node_id, output) for output in outputs]

            nodes.append(
                WorkflowNode(
                    id=node_id,
                    type=node_type,
                    parameters=parameters,
                    inputs=inputs,
                    outputs=outputs,
                    connections=node_conns,
                )
            )

        return nodes

    def _detect_query_merge_aggregate(
        self, nodes: List[WorkflowNode]
    ) -> List[OptimizationOpportunity]:
        """Detect Query→Merge→Aggregate patterns that can be optimized to SQL."""
        opportunities = []

        # Find sequences of query → merge → aggregate
        for i, node in enumerate(nodes):
            if node.type in self.query_nodes:
                # Look for merge nodes that take this query as input
                for merge_node in nodes:
                    if (
                        merge_node.type in self.merge_nodes
                        and node.id in merge_node.inputs
                    ):

                        # Look for aggregate nodes that take the merge as input
                        for agg_node in nodes:
                            if (
                                agg_node.type in self.aggregate_nodes
                                and merge_node.id in agg_node.inputs
                            ):

                                # Found a Query→Merge→Aggregate pattern!
                                opportunity = self._create_qma_optimization(
                                    query_node=node,
                                    merge_node=merge_node,
                                    aggregate_node=agg_node,
                                    nodes=nodes,
                                )
                                if opportunity:
                                    opportunities.append(opportunity)

        return opportunities

    def _create_qma_optimization(
        self,
        query_node: WorkflowNode,
        merge_node: WorkflowNode,
        aggregate_node: WorkflowNode,
        nodes: List[WorkflowNode],
    ) -> Optional[OptimizationOpportunity]:
        """Create optimization opportunity for Query→Merge→Aggregate pattern."""

        # Analyze the pattern to determine optimization potential
        query_params = query_node.parameters
        merge_params = merge_node.parameters
        agg_params = aggregate_node.parameters

        # Estimate improvement based on pattern complexity
        estimated_improvement = "10-100x faster"
        confidence = 0.8

        # Check if we can identify the tables and operations
        tables_involved = set()
        if "table" in query_params:
            tables_involved.add(query_params["table"])

        # Find other query nodes connected to the merge
        for input_node_id in merge_node.inputs:
            input_node = next((n for n in nodes if n.id == input_node_id), None)
            if input_node and input_node.type in self.query_nodes:
                if "table" in input_node.parameters:
                    tables_involved.add(input_node.parameters["table"])

        # Generate proposed SQL optimization
        proposed_sql = self._generate_optimized_sql(
            tables=list(tables_involved),
            merge_params=merge_params,
            agg_params=agg_params,
        )

        return OptimizationOpportunity(
            pattern_type=PatternType.QUERY_MERGE_AGGREGATE,
            nodes_involved=[query_node.id, merge_node.id, aggregate_node.id],
            estimated_improvement=estimated_improvement,
            optimization_strategy="Replace with single SQL query using JOINs and GROUP BY",
            confidence=confidence,
            description=f"Optimize {len([query_node.id, merge_node.id, aggregate_node.id])} node sequence into single SQL operation",
            proposed_sql=proposed_sql,
        )

    def _generate_optimized_sql(
        self, tables: List[str], merge_params: Dict, agg_params: Dict
    ) -> str:
        """Generate optimized SQL for Query→Merge→Aggregate pattern."""
        if len(tables) < 2:
            return "-- Single table optimization"

        # Basic SQL template for common patterns
        primary_table = tables[0]
        secondary_table = tables[1] if len(tables) > 1 else tables[0]

        # Extract aggregation info
        agg_expression = agg_params.get("aggregate_expression", "count(*)")
        group_by_fields = agg_params.get("group_by", [])

        # Parse aggregation expression
        if "sum of" in agg_expression.lower():
            agg_func = "SUM"
            field = agg_expression.lower().replace("sum of", "").strip()
        elif "count" in agg_expression.lower():
            agg_func = "COUNT"
            field = "*"
        elif "average" in agg_expression.lower() or "avg" in agg_expression.lower():
            agg_func = "AVG"
            field = (
                agg_expression.lower()
                .replace("average of", "")
                .replace("avg of", "")
                .strip()
            )
        else:
            agg_func = "COUNT"
            field = "*"

        # Build SQL
        select_clause = (
            f"SELECT {', '.join(group_by_fields) if group_by_fields else 'NULL'}"
        )
        if field != "*":
            select_clause += f", {agg_func}({field}) as result"
        else:
            select_clause += f", {agg_func}({field}) as result"

        join_clause = f"FROM {primary_table} p JOIN {secondary_table} s ON p.id = s.{primary_table.lower()}_id"

        if group_by_fields:
            group_clause = f"GROUP BY {', '.join(group_by_fields)}"
        else:
            group_clause = ""

        sql = f"""
-- Optimized Query→Merge→Aggregate pattern
{select_clause}
{join_clause}
{group_clause}
""".strip()

        return sql

    def _detect_multiple_queries(
        self, nodes: List[WorkflowNode]
    ) -> List[OptimizationOpportunity]:
        """Detect multiple separate queries that could be combined."""
        opportunities = []

        # Find all query nodes
        query_nodes = [n for n in nodes if n.type in self.query_nodes]

        if len(query_nodes) > 1:
            # Group by table/database
            tables = {}
            for qnode in query_nodes:
                table = qnode.parameters.get("table", "unknown")
                if table not in tables:
                    tables[table] = []
                tables[table].append(qnode)

            # Look for opportunities to combine queries on the same table
            for table, table_queries in tables.items():
                if len(table_queries) > 1:
                    opportunity = OptimizationOpportunity(
                        pattern_type=PatternType.MULTIPLE_QUERIES,
                        nodes_involved=[q.id for q in table_queries],
                        estimated_improvement="2-5x faster",
                        optimization_strategy="Combine multiple queries into single query with UNION",
                        confidence=0.6,
                        description=f"Combine {len(table_queries)} separate queries on {table} table",
                        proposed_sql=f"-- SELECT ... FROM {table} WHERE condition1 UNION SELECT ... FROM {table} WHERE condition2",
                    )
                    opportunities.append(opportunity)

        return opportunities

    def _detect_redundant_operations(
        self, nodes: List[WorkflowNode]
    ) -> List[OptimizationOpportunity]:
        """Detect redundant operations that can be eliminated."""
        opportunities = []

        # Look for duplicate node types with similar parameters
        node_groups = {}
        for node in nodes:
            key = (node.type, str(sorted(node.parameters.items())))
            if key not in node_groups:
                node_groups[key] = []
            node_groups[key].append(node)

        # Find groups with multiple nodes (potential redundancy)
        for (node_type, params_str), group in node_groups.items():
            if len(group) > 1:
                opportunity = OptimizationOpportunity(
                    pattern_type=PatternType.REDUNDANT_OPERATIONS,
                    nodes_involved=[n.id for n in group],
                    estimated_improvement="50% less compute",
                    optimization_strategy="Eliminate duplicate operations and reuse results",
                    confidence=0.7,
                    description=f"Remove {len(group)-1} redundant {node_type} operations",
                )
                opportunities.append(opportunity)

        return opportunities

    def _detect_inefficient_joins(
        self, nodes: List[WorkflowNode]
    ) -> List[OptimizationOpportunity]:
        """Detect inefficient join patterns."""
        opportunities = []

        # Look for merge nodes that might benefit from index suggestions
        for node in nodes:
            if node.type in self.merge_nodes:
                join_conditions = node.parameters.get("join_conditions", {})
                merge_type = node.parameters.get("merge_type", "inner")

                if join_conditions and merge_type != "auto":
                    # Suggest index optimization
                    opportunity = OptimizationOpportunity(
                        pattern_type=PatternType.INEFFICIENT_JOINS,
                        nodes_involved=[node.id],
                        estimated_improvement="2-10x faster joins",
                        optimization_strategy="Add database indexes on join columns",
                        confidence=0.5,
                        description=f"Optimize join performance with indexes on {join_conditions}",
                    )
                    opportunities.append(opportunity)

        return opportunities

    def _impact_score(self, estimated_improvement: str) -> float:
        """Convert estimated improvement string to numeric score for sorting."""
        if "100x" in estimated_improvement or "1000x" in estimated_improvement:
            return 100.0
        elif "10x" in estimated_improvement or "50x" in estimated_improvement:
            return 10.0
        elif "5x" in estimated_improvement:
            return 5.0
        elif "2x" in estimated_improvement:
            return 2.0
        else:
            return 1.0

    def generate_optimization_report(
        self, opportunities: List[OptimizationOpportunity]
    ) -> str:
        """Generate a human-readable optimization report."""
        if not opportunities:
            return "No optimization opportunities detected."

        report = f"DataFlow Workflow Optimization Report\n{'=' * 50}\n\n"
        report += f"Found {len(opportunities)} optimization opportunities:\n\n"

        for i, opp in enumerate(opportunities, 1):
            report += f"{i}. {opp.pattern_type.value.upper()}\n"
            report += f"   Nodes: {', '.join(opp.nodes_involved)}\n"
            report += f"   Impact: {opp.estimated_improvement}\n"
            report += f"   Strategy: {opp.optimization_strategy}\n"
            report += f"   Confidence: {opp.confidence:.1%}\n"
            report += f"   Description: {opp.description}\n"

            if opp.proposed_sql:
                report += f"   Proposed SQL:\n{opp.proposed_sql}\n"

            report += "\n"

        return report
