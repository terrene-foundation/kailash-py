"""
AI-Enhanced Database Operations for Kaizen-DataFlow integration.

Provides intelligent database capabilities:
- Natural language to SQL query conversion
- Intelligent data transformation and schema mapping
- Data quality assessment and automated cleaning
- Semantic database search

Architecture:
- Signature-based LLM integration for intelligent operations
- Extends DataFlowAwareAgent for database access
- Production-ready error handling and validation
"""

import json
import logging
from typing import Any, Dict, List, Optional

from kaizen.signatures import InputField, OutputField, Signature

from .base import DataFlowAwareAgent

logger = logging.getLogger(__name__)


# ============================================================================
# Signature Definitions
# ============================================================================


class NLQuerySignature(Signature):
    """Convert natural language to DataFlow query."""

    natural_query: str = InputField(desc="User's natural language query")
    table_schema: dict = InputField(desc="Database table schema information")
    available_tables: list = InputField(desc="List of available tables")

    target_table: str = OutputField(desc="Target table for query")
    filter_dict: str = OutputField(
        desc="MongoDB-style filter for DataFlow (as JSON string)"
    )
    projection_fields: str = OutputField(desc="Fields to return (as JSON list)")
    explanation: str = OutputField(desc="Explanation of query interpretation")


class DataTransformSignature(Signature):
    """Intelligent data transformation between schemas."""

    source_sample: str = InputField(desc="Sample source data (as JSON)")
    source_schema: str = InputField(desc="Source data schema (as JSON)")
    target_schema: str = InputField(desc="Target schema to match (as JSON)")

    transformation_rules: str = OutputField(desc="Field mapping rules (as JSON dict)")
    data_quality_issues: str = OutputField(
        desc="Identified quality issues (as JSON list)"
    )
    confidence_score: float = OutputField(desc="Transformation confidence (0-1)")


class DataQualitySignature(Signature):
    """Assess and improve data quality."""

    data_sample: str = InputField(desc="Sample data for analysis (as JSON)")
    schema: str = InputField(desc="Expected schema (as JSON)")
    quality_rules: str = InputField(desc="Quality rules to check (as JSON)")

    quality_score: float = OutputField(desc="Overall quality score (0-1)")
    issues_found: str = OutputField(desc="List of quality issues (as JSON)")
    suggested_fixes: str = OutputField(desc="Recommended corrections (as JSON)")
    cleaned_sample: str = OutputField(desc="Cleaned data sample (as JSON)")


class SemanticSearchSignature(Signature):
    """Semantic search across database."""

    search_query: str = InputField(desc="Semantic search query")
    table_schemas: str = InputField(desc="All table schemas (as JSON)")
    search_context: str = InputField(desc="Additional context")

    relevant_tables: str = OutputField(
        desc="Tables likely to have results (as JSON list)"
    )
    search_strategy: str = OutputField(desc="How to search each table (as JSON dict)")
    combined_query: str = OutputField(desc="Optimized search query (as JSON)")


# ============================================================================
# AI-Enhanced Agent Implementations
# ============================================================================


class NLToSQLAgent(DataFlowAwareAgent):
    """
    Convert natural language queries to DataFlow operations.

    Uses LLM to understand natural language and generate appropriate
    MongoDB-style filters for DataFlow queries.

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("postgresql://localhost/mydb")
        >>>
        >>> agent = NLToSQLAgent(config=config, db=db)
        >>> result = agent.query("Show me all users who signed up last month")
        >>> print(result['explanation'])
        >>> print(result['results'])
    """

    def __init__(self, config, db: Optional[Any] = None):
        """Initialize NL to SQL agent."""
        super().__init__(config=config, signature=NLQuerySignature(), db=db)

    def query(self, natural_query: str) -> Dict[str, Any]:
        """
        Execute natural language query against database.

        Args:
            natural_query: Natural language query string

        Returns:
            Dictionary containing:
            - results: Query results from database
            - explanation: LLM explanation of query interpretation
            - filter: Generated filter dict
            - table: Target table name

        Example:
            >>> result = agent.query("Find products with low inventory")
            >>> print(result['explanation'])
            >>> for item in result['results']:
            ...     print(item)
        """
        if not self.db_connection:
            raise RuntimeError(
                "No DataFlow connection. Initialize agent with db parameter."
            )

        # Get available tables
        tables = self.db_connection.list_tables()

        # Get schemas for context
        schemas = {}
        for table in tables:
            try:
                schemas[table] = self.db_connection.get_table_schema(table)
            except Exception as e:
                logger.warning(f"Could not get schema for {table}: {e}")

        # Generate query using LLM
        llm_result = self.run(
            natural_query=natural_query, table_schema=schemas, available_tables=tables
        )

        # Extract results from LLM
        target_table = llm_result.get("target_table", "")
        explanation = llm_result.get("explanation", "Query processed")

        # Parse filter dict (LLM returns as JSON string)
        filter_str = llm_result.get("filter_dict", "{}")
        try:
            if isinstance(filter_str, str):
                filter_dict = json.loads(filter_str) if filter_str else {}
            else:
                filter_dict = filter_str
        except json.JSONDecodeError:
            logger.warning(f"Could not parse filter: {filter_str}")
            filter_dict = {}

        # Parse projection fields
        projection_str = llm_result.get("projection_fields", "[]")
        try:
            if isinstance(projection_str, str):
                projection_fields = json.loads(projection_str) if projection_str else []
            else:
                projection_fields = projection_str
        except json.JSONDecodeError:
            logger.warning(f"Could not parse projection: {projection_str}")
            projection_fields = []

        # Execute query via DataFlow
        try:
            query_results = self.query_database(
                table=target_table,
                filter=filter_dict if filter_dict else None,
                limit=100,  # Default limit
            )
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            query_results = []

        return {
            "results": query_results,
            "explanation": explanation,
            "filter": filter_dict,
            "table": target_table,
            "projection": projection_fields,
        }


class DataTransformAgent(DataFlowAwareAgent):
    """
    AI-driven data transformation and validation.

    Uses LLM to intelligently map fields between schemas and
    transform data to match target schema.

    Example:
        >>> agent = DataTransformAgent(config=config, db=db)
        >>> result = agent.transform_data(
        ...     source_data=[{'firstName': 'Alice', 'emailAddr': 'alice@example.com'}],
        ...     target_table='users'
        ... )
        >>> print(f"Inserted {result['inserted_count']} records")
        >>> print(f"Confidence: {result['confidence']}")
    """

    def __init__(self, config, db: Optional[Any] = None):
        """Initialize data transformation agent."""
        super().__init__(config=config, signature=DataTransformSignature(), db=db)

    def transform_data(
        self, source_data: List[Dict[str, Any]], target_table: str
    ) -> Dict[str, Any]:
        """
        Transform data to match target schema.

        Args:
            source_data: List of source data records
            target_table: Target table name

        Returns:
            Dictionary containing:
            - inserted_count: Number of records inserted
            - quality_issues: List of data quality issues
            - confidence: Transformation confidence score
            - transformation_rules: Applied field mappings

        Example:
            >>> source = [{'name': 'Alice', 'email': 'alice@example.com'}]
            >>> result = agent.transform_data(source, 'users')
        """
        if not self.db_connection:
            raise RuntimeError("No DataFlow connection.")

        # Get target schema from DataFlow
        target_schema = self.db_connection.get_table_schema(target_table)

        # Infer source schema from data
        source_schema = self._infer_schema(source_data)

        # Generate transformation via LLM (use sample for analysis)
        sample_data = source_data[:5] if len(source_data) > 5 else source_data

        llm_result = self.run(
            source_sample=json.dumps(sample_data),
            source_schema=json.dumps(source_schema),
            target_schema=json.dumps(target_schema),
        )

        # Parse transformation rules
        rules_str = llm_result.get("transformation_rules", "{}")
        try:
            transformation_rules = (
                json.loads(rules_str) if isinstance(rules_str, str) else rules_str
            )
        except json.JSONDecodeError:
            transformation_rules = {}

        # Parse quality issues
        issues_str = llm_result.get("data_quality_issues", "[]")
        try:
            quality_issues = (
                json.loads(issues_str) if isinstance(issues_str, str) else issues_str
            )
        except json.JSONDecodeError:
            quality_issues = []

        # Get confidence
        confidence = llm_result.get("confidence_score", 0.5)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except ValueError:
                confidence = 0.5

        # Apply transformations
        transformed_data = self._apply_transforms(source_data, transformation_rules)

        # Bulk insert via DataFlow
        try:
            insert_result = self.bulk_insert(target_table, transformed_data)
            inserted_count = len(insert_result)
        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            inserted_count = 0

        return {
            "inserted_count": inserted_count,
            "quality_issues": quality_issues,
            "confidence": confidence,
            "transformation_rules": transformation_rules,
        }

    def _infer_schema(self, data: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """Infer schema from data sample."""
        if not data:
            return {}

        schema = {}
        sample = data[0]

        for field, value in sample.items():
            field_type = type(value).__name__
            schema[field] = {"type": field_type, "nullable": value is None}

        return schema

    def _apply_transforms(
        self, source_data: List[Dict[str, Any]], rules: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply transformation rules to data."""
        transformed = []

        for record in source_data:
            new_record = {}

            for target_field, source_field in rules.items():
                # Skip if source_field is not a string (malformed rule)
                if not isinstance(source_field, str):
                    logger.warning(
                        f"Skipping malformed transformation rule: "
                        f"{target_field} -> {source_field}"
                    )
                    new_record[target_field] = None
                    continue

                # Handle nested field access (e.g., "user.name")
                if "." in source_field:
                    value = record
                    for part in source_field.split("."):
                        # Only call .get() if value is a dict
                        if isinstance(value, dict):
                            value = value.get(part, None)
                        else:
                            value = None
                            break
                        if value is None:
                            break
                else:
                    value = (
                        record.get(source_field) if isinstance(record, dict) else None
                    )

                new_record[target_field] = value

            transformed.append(new_record)

        return transformed


class DataQualityAgent(DataFlowAwareAgent):
    """
    AI-based data validation and quality checking.

    Uses LLM to assess data quality, identify issues, and
    suggest corrections.

    Example:
        >>> agent = DataQualityAgent(config=config)
        >>> result = agent.assess_quality(
        ...     data_sample=[{'name': '', 'email': 'invalid'}],
        ...     schema={'columns': {'name': {'type': 'str', 'nullable': False}}}
        ... )
        >>> print(f"Quality score: {result['quality_score']}")
        >>> print(f"Issues: {result['issues_found']}")
    """

    def __init__(self, config, db: Optional[Any] = None):
        """Initialize data quality agent."""
        super().__init__(config=config, signature=DataQualitySignature(), db=db)

    def assess_quality(
        self,
        data_sample: List[Dict[str, Any]],
        schema: Dict[str, Any],
        quality_rules: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Assess data quality.

        Args:
            data_sample: Sample data to assess
            schema: Expected schema
            quality_rules: Optional custom quality rules

        Returns:
            Dictionary containing:
            - quality_score: Overall quality score (0-1)
            - issues_found: List of issues
            - suggested_fixes: Recommended corrections

        Example:
            >>> result = agent.assess_quality(
            ...     data_sample=[{'age': 150}],
            ...     schema={'columns': {'age': {'type': 'int'}}},
            ...     quality_rules={'age': {'min': 0, 'max': 120}}
            ... )
        """
        if quality_rules is None:
            quality_rules = {}

        # Run LLM analysis
        llm_result = self.run(
            data_sample=json.dumps(data_sample),
            schema=json.dumps(schema),
            quality_rules=json.dumps(quality_rules),
        )

        # Parse results
        quality_score = llm_result.get("quality_score", 0.0)
        if isinstance(quality_score, str):
            try:
                quality_score = float(quality_score)
            except ValueError:
                quality_score = 0.0

        issues_str = llm_result.get("issues_found", "[]")
        try:
            issues_found = (
                json.loads(issues_str) if isinstance(issues_str, str) else issues_str
            )
        except json.JSONDecodeError:
            issues_found = []

        fixes_str = llm_result.get("suggested_fixes", "{}")
        try:
            suggested_fixes = (
                json.loads(fixes_str) if isinstance(fixes_str, str) else fixes_str
            )
        except json.JSONDecodeError:
            suggested_fixes = {}

        return {
            "quality_score": quality_score,
            "issues_found": issues_found,
            "suggested_fixes": suggested_fixes,
        }

    def clean_data(self, data_sample: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Clean and normalize data.

        Args:
            data_sample: Data to clean

        Returns:
            Dictionary containing cleaned_data

        Example:
            >>> result = agent.clean_data([
            ...     {'name': '  Alice  ', 'email': 'ALICE@EXAMPLE.COM'}
            ... ])
            >>> print(result['cleaned_data'])
        """
        # For now, apply basic cleaning rules
        cleaned = []

        for record in data_sample:
            cleaned_record = {}

            for field, value in record.items():
                if isinstance(value, str):
                    # Strip whitespace and normalize
                    value = value.strip()

                    # Lowercase emails
                    if "email" in field.lower():
                        value = value.lower()

                cleaned_record[field] = value

            cleaned.append(cleaned_record)

        return {"cleaned_data": cleaned}


class SemanticSearchAgent(DataFlowAwareAgent):
    """
    AI-powered semantic database search.

    Uses LLM to understand semantic queries and search across
    multiple tables intelligently.

    Example:
        >>> agent = SemanticSearchAgent(config=config, db=db)
        >>> result = agent.search(
        ...     query="Find customers who bought electronics recently"
        ... )
        >>> print(result['relevant_tables'])
        >>> print(result['results'])
    """

    def __init__(self, config, db: Optional[Any] = None):
        """Initialize semantic search agent."""
        super().__init__(config=config, signature=SemanticSearchSignature(), db=db)

    def search(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute semantic search across database.

        Args:
            query: Semantic search query
            context: Optional additional context

        Returns:
            Dictionary containing:
            - relevant_tables: Tables likely to have results
            - search_strategy: How to search each table
            - results: Combined search results

        Example:
            >>> result = agent.search(
            ...     query="Popular products",
            ...     context="Focus on high demand items"
            ... )
        """
        if not self.db_connection:
            raise RuntimeError("No DataFlow connection.")

        # Get all table schemas
        tables = self.db_connection.list_tables()
        schemas = {}
        for table in tables:
            try:
                schemas[table] = self.db_connection.get_table_schema(table)
            except Exception as e:
                logger.warning(f"Could not get schema for {table}: {e}")

        # Run LLM analysis
        llm_result = self.run(
            search_query=query,
            table_schemas=json.dumps(schemas),
            search_context=context or "No additional context",
        )

        # Parse results
        tables_str = llm_result.get("relevant_tables", "[]")
        try:
            relevant_tables = (
                json.loads(tables_str) if isinstance(tables_str, str) else tables_str
            )
        except json.JSONDecodeError:
            relevant_tables = []

        strategy_str = llm_result.get("search_strategy", "{}")
        try:
            search_strategy = (
                json.loads(strategy_str)
                if isinstance(strategy_str, str)
                else strategy_str
            )
        except json.JSONDecodeError:
            search_strategy = {}

        # Execute searches
        results = {}
        for table in relevant_tables:
            table_strategy = search_strategy.get(table, {})
            filter_dict = table_strategy.get("filter", {})

            try:
                table_results = self.query_database(
                    table=table, filter=filter_dict if filter_dict else None, limit=10
                )
                results[table] = table_results
            except Exception as e:
                logger.error(f"Search failed for {table}: {e}")
                results[table] = []

        return {
            "relevant_tables": relevant_tables,
            "search_strategy": search_strategy,
            "results": results,
        }
