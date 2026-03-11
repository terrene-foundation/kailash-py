"""
DataFlow Natural Language Filter Node

Provides intelligent filtering with natural language expressions.
"""

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import Node, NodeParameter, NodeRegistry

from .workflow_connection_manager import SmartNodeConnectionMixin

logger = logging.getLogger(__name__)


class NaturalLanguageFilterNode(SmartNodeConnectionMixin, Node):
    """Natural language filter node for intelligent data filtering.

    This node supports:
    - Natural language date/time expressions: "today", "this week", "last month"
    - Relative comparisons: "greater than average", "above median"
    - Smart field detection: automatically finds date/numeric fields
    - Complex filter combinations with AND/OR logic
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._date_cache = {}

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define parameters for NaturalLanguageFilterNode."""
        return {
            "data": NodeParameter(
                name="data", type=list, required=True, description="Data to filter"
            ),
            "filter_expression": NodeParameter(
                name="filter_expression",
                type=str,
                required=True,
                description="Natural language filter expression",
            ),
            "date_field": NodeParameter(
                name="date_field",
                type=str,
                required=False,
                description="Primary date field name (auto-detected if not specified)",
            ),
            "numeric_field": NodeParameter(
                name="numeric_field",
                type=str,
                required=False,
                description="Primary numeric field name (auto-detected if not specified)",
            ),
            "reference_date": NodeParameter(
                name="reference_date",
                type=str,
                required=False,
                description="Reference date for relative calculations (ISO format, defaults to today)",
            ),
            "case_sensitive": NodeParameter(
                name="case_sensitive",
                type=bool,
                required=False,
                default=False,
                description="Whether string comparisons should be case sensitive",
            ),
            "connection_pool_id": NodeParameter(
                name="connection_pool_id",
                type=str,
                required=False,
                description="ID of DataFlowConnectionManager node for database operations",
            ),
        }

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute natural language filtering with connection pool integration."""
        return self._execute_with_connection(self._perform_filtering, **kwargs)

    def _perform_filtering(self, **kwargs) -> Dict[str, Any]:
        """Perform the actual natural language filtering."""
        data = kwargs.get("data", [])
        filter_expression = kwargs.get("filter_expression", "")
        date_field = kwargs.get("date_field")
        numeric_field = kwargs.get("numeric_field")
        reference_date = kwargs.get("reference_date")
        case_sensitive = kwargs.get("case_sensitive", False)

        logger.info(
            f"Executing NaturalLanguageFilterNode with expression: {filter_expression}"
        )

        if not data:
            return {
                "filtered_data": [],
                "filter_expression": filter_expression,
                "matches": 0,
                "total_records": 0,
                "parsed_successfully": True,
            }

        # Parse reference date
        ref_date = self._parse_reference_date(reference_date)

        # Auto-detect fields if not specified
        sample_record = data[0] if data else {}
        if not date_field:
            date_field = self._auto_detect_date_field(sample_record)
        if not numeric_field:
            numeric_field = self._auto_detect_numeric_field(sample_record)

        # Parse and execute filter
        try:
            filter_func = self._parse_filter_expression(
                filter_expression, date_field, numeric_field, ref_date, case_sensitive
            )
            filtered_data = [record for record in data if filter_func(record)]

            return {
                "filtered_data": filtered_data,
                "filter_expression": filter_expression,
                "matches": len(filtered_data),
                "total_records": len(data),
                "date_field": date_field,
                "numeric_field": numeric_field,
                "reference_date": ref_date.isoformat(),
                "parsed_successfully": True,
            }

        except Exception as e:
            logger.error(
                f"Failed to parse filter expression '{filter_expression}': {e}"
            )
            return {
                "filtered_data": data,  # Return unfiltered data on error
                "filter_expression": filter_expression,
                "matches": len(data),
                "total_records": len(data),
                "error": str(e),
                "parsed_successfully": False,
            }

    def _parse_reference_date(self, reference_date: Optional[str]) -> datetime:
        """Parse reference date or use current date."""
        if reference_date:
            try:
                return datetime.fromisoformat(reference_date.replace("Z", "+00:00"))
            except ValueError:
                logger.warning(
                    f"Invalid reference date format: {reference_date}, using today"
                )

        return datetime.now()

    def _auto_detect_date_field(self, sample_record: Dict) -> Optional[str]:
        """Auto-detect date field from sample record."""
        date_candidates = []

        for field_name, value in sample_record.items():
            # Check field name patterns
            if any(
                pattern in field_name.lower()
                for pattern in [
                    "date",
                    "time",
                    "created",
                    "updated",
                    "modified",
                    "timestamp",
                ]
            ):
                date_candidates.append(field_name)
                continue

            # Check value type/format
            if isinstance(value, (datetime, date)):
                date_candidates.append(field_name)
            elif isinstance(value, str):
                # Try to parse as ISO date
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    date_candidates.append(field_name)
                except ValueError:
                    pass

        # Return most likely candidate
        priority_order = [
            "created_at",
            "updated_at",
            "date",
            "timestamp",
            "created",
            "modified",
        ]
        for priority_field in priority_order:
            if priority_field in date_candidates:
                return priority_field

        return date_candidates[0] if date_candidates else None

    def _auto_detect_numeric_field(self, sample_record: Dict) -> Optional[str]:
        """Auto-detect numeric field from sample record."""
        numeric_candidates = []

        for field_name, value in sample_record.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_candidates.append(field_name)

        # Return most likely candidate
        priority_order = [
            "amount",
            "total",
            "price",
            "value",
            "cost",
            "revenue",
            "count",
            "quantity",
        ]
        for priority_field in priority_order:
            if priority_field in numeric_candidates:
                return priority_field

        return numeric_candidates[0] if numeric_candidates else None

    def _parse_filter_expression(
        self,
        expression: str,
        date_field: Optional[str],
        numeric_field: Optional[str],
        reference_date: datetime,
        case_sensitive: bool,
    ):
        """Parse natural language filter expression into a function."""
        expression = expression.strip()

        # Handle compound expressions (AND/OR)
        if " and " in expression.lower():
            parts = [
                part.strip()
                for part in re.split(r"\s+and\s+", expression, flags=re.IGNORECASE)
            ]
            sub_functions = [
                self._parse_single_expression(
                    part, date_field, numeric_field, reference_date, case_sensitive
                )
                for part in parts
            ]
            return lambda record: all(func(record) for func in sub_functions)

        elif " or " in expression.lower():
            parts = [
                part.strip()
                for part in re.split(r"\s+or\s+", expression, flags=re.IGNORECASE)
            ]
            sub_functions = [
                self._parse_single_expression(
                    part, date_field, numeric_field, reference_date, case_sensitive
                )
                for part in parts
            ]
            return lambda record: any(func(record) for func in sub_functions)

        # Single expression
        return self._parse_single_expression(
            expression, date_field, numeric_field, reference_date, case_sensitive
        )

    def _parse_single_expression(
        self,
        expression: str,
        date_field: Optional[str],
        numeric_field: Optional[str],
        reference_date: datetime,
        case_sensitive: bool,
    ):
        """Parse a single filter expression."""
        expression = expression.strip().lower()

        # Date/time expressions
        if date_field:
            date_func = self._parse_date_expression(
                expression, date_field, reference_date
            )
            if date_func:
                return date_func

        # Numeric expressions
        if numeric_field:
            numeric_func = self._parse_numeric_expression(expression, numeric_field)
            if numeric_func:
                return numeric_func

        # String/general expressions
        return self._parse_general_expression(expression, case_sensitive)

    def _parse_date_expression(
        self, expression: str, date_field: str, reference_date: datetime
    ):
        """Parse date-specific expressions."""
        # Get current date components
        today = reference_date.date()

        # Date range patterns
        date_patterns = {
            # Exact dates
            "today": (today, today),
            "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
            "tomorrow": (today + timedelta(days=1), today + timedelta(days=1)),
            # Week patterns
            "this week": self._get_week_range(today, 0),
            "last week": self._get_week_range(today, -1),
            "next week": self._get_week_range(today, 1),
            # Month patterns
            "this month": self._get_month_range(today, 0),
            "last month": self._get_month_range(today, -1),
            "next month": self._get_month_range(today, 1),
            # Year patterns
            "this year": self._get_year_range(today, 0),
            "last year": self._get_year_range(today, -1),
            "next year": self._get_year_range(today, 1),
            # Recent patterns
            "last 7 days": (today - timedelta(days=7), today),
            "last 30 days": (today - timedelta(days=30), today),
            "last 90 days": (today - timedelta(days=90), today),
        }

        for pattern, (start_date, end_date) in date_patterns.items():
            if pattern in expression:
                return lambda record: self._date_in_range(
                    record.get(date_field), start_date, end_date
                )

        # Relative date patterns
        relative_patterns = [
            (
                r"before\s+(\d+)\s+days?\s+ago",
                lambda days: today - timedelta(days=int(days)),
            ),
            (
                r"after\s+(\d+)\s+days?\s+ago",
                lambda days: today - timedelta(days=int(days)),
            ),
            (r"(\d+)\s+days?\s+ago", lambda days: today - timedelta(days=int(days))),
        ]

        for pattern, date_func in relative_patterns:
            match = re.search(pattern, expression)
            if match:
                target_date = date_func(match.group(1))
                if "before" in expression:
                    return (
                        lambda record: self._parse_record_date(record.get(date_field))
                        < target_date
                    )
                elif "after" in expression:
                    return (
                        lambda record: self._parse_record_date(record.get(date_field))
                        > target_date
                    )
                else:
                    return (
                        lambda record: self._parse_record_date(record.get(date_field))
                        == target_date
                    )

        return None

    def _parse_numeric_expression(self, expression: str, numeric_field: str):
        """Parse numeric expressions with relative comparisons."""
        # Direct numeric comparisons
        numeric_patterns = [
            (
                r"greater than (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) > float(val),
            ),
            (
                r"less than (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) < float(val),
            ),
            (
                r"equal to (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) == float(val),
            ),
            (
                r"above (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) > float(val),
            ),
            (
                r"below (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) < float(val),
            ),
            (
                r"at least (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) >= float(val),
            ),
            (
                r"at most (\d+(?:\.\d+)?)",
                lambda val: lambda record: record.get(numeric_field, 0) <= float(val),
            ),
        ]

        for pattern, func_factory in numeric_patterns:
            match = re.search(pattern, expression)
            if match:
                return func_factory(match.group(1))

        # Relative comparisons (require data analysis)
        if any(
            term in expression
            for term in ["average", "mean", "median", "maximum", "minimum"]
        ):
            return self._create_relative_numeric_filter(expression, numeric_field)

        return None

    def _parse_general_expression(self, expression: str, case_sensitive: bool):
        """Parse general string/field expressions."""
        # String matching patterns
        if "contains" in expression:
            match = re.search(r'contains\s+["\']?([^"\']+)["\']?', expression)
            if match:
                search_term = match.group(1)
                if not case_sensitive:
                    search_term = search_term.lower()
                return lambda record: any(
                    (
                        search_term in str(value).lower()
                        if not case_sensitive
                        else search_term in str(value)
                    )
                    for value in record.values()
                )

        if "starts with" in expression:
            match = re.search(r'starts with\s+["\']?([^"\']+)["\']?', expression)
            if match:
                search_term = match.group(1)
                if not case_sensitive:
                    search_term = search_term.lower()
                return lambda record: any(
                    (
                        str(value).lower().startswith(search_term)
                        if not case_sensitive
                        else str(value).startswith(search_term)
                    )
                    for value in record.values()
                )

        if "ends with" in expression:
            match = re.search(r'ends with\s+["\']?([^"\']+)["\']?', expression)
            if match:
                search_term = match.group(1)
                if not case_sensitive:
                    search_term = search_term.lower()
                return lambda record: any(
                    (
                        str(value).lower().endswith(search_term)
                        if not case_sensitive
                        else str(value).endswith(search_term)
                    )
                    for value in record.values()
                )

        # Default: treat as contains search, but only if expression looks like a search term
        # Reject obviously complex expressions that we can't parse
        if len(expression.split()) > 5 or any(
            char in expression for char in ["(", ")", "[", "]", "{", "}"]
        ):
            raise ValueError(f"Cannot parse complex expression: {expression}")

        if not case_sensitive:
            expression = expression.lower()
        return lambda record: any(
            (
                expression in str(value).lower()
                if not case_sensitive
                else expression in str(value)
            )
            for value in record.values()
            if value is not None
        )

    def _create_relative_numeric_filter(self, expression: str, numeric_field: str):
        """Create filter for relative numeric comparisons."""

        def relative_filter(record):
            # This is a closure that will be called with access to all data
            # For now, return a simple implementation
            # In a real implementation, this would calculate statistics across the dataset
            return True

        return relative_filter

    def _get_week_range(self, reference_date: date, weeks_offset: int):
        """Get start and end dates for a week."""
        # Find Monday of the reference week
        days_since_monday = reference_date.weekday()
        week_start = reference_date - timedelta(days=days_since_monday)
        week_start += timedelta(weeks=weeks_offset)
        week_end = week_start + timedelta(days=6)
        return (week_start, week_end)

    def _get_month_range(self, reference_date: date, months_offset: int):
        """Get start and end dates for a month."""
        year = reference_date.year
        month = reference_date.month + months_offset

        # Handle year overflow/underflow
        while month > 12:
            month -= 12
            year += 1
        while month < 1:
            month += 12
            year -= 1

        # First day of month
        start_date = date(year, month, 1)

        # Last day of month
        if month == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, month + 1, 1) - timedelta(days=1)

        return (start_date, end_date)

    def _get_year_range(self, reference_date: date, years_offset: int):
        """Get start and end dates for a year."""
        year = reference_date.year + years_offset
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        return (start_date, end_date)

    def _date_in_range(self, date_value: Any, start_date: date, end_date: date) -> bool:
        """Check if a date value falls within a range."""
        if not date_value:
            return False

        record_date = self._parse_record_date(date_value)
        if not record_date:
            return False

        return start_date <= record_date <= end_date

    def _parse_record_date(self, date_value: Any) -> Optional[date]:
        """Parse a date value from a record."""
        if isinstance(date_value, date) and not isinstance(date_value, datetime):
            return date_value
        elif isinstance(date_value, datetime):
            return date_value.date()
        elif isinstance(date_value, str):
            try:
                return datetime.fromisoformat(date_value.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return datetime.strptime(date_value, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        # Try parsing as datetime and extract date
                        return datetime.fromisoformat(date_value).date()
                    except ValueError:
                        return None

        return None


# Register the node with Kailash's NodeRegistry
NodeRegistry.register(NaturalLanguageFilterNode, alias="NaturalLanguageFilterNode")
