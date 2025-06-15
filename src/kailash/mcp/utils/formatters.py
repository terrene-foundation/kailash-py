"""
Response formatting utilities for MCP servers.

Provides consistent formatting for tool responses, making them more readable
and structured for LLM consumption.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class ResponseFormatter:
    """Base class for response formatters."""

    def format(self, data: Any, **kwargs) -> str:
        """Format data into string representation."""
        raise NotImplementedError


class JSONFormatter(ResponseFormatter):
    """Format responses as pretty-printed JSON."""

    def __init__(self, indent: int = 2, ensure_ascii: bool = False):
        self.indent = indent
        self.ensure_ascii = ensure_ascii

    def format(self, data: Any, **kwargs) -> str:
        """Format data as JSON string."""
        try:
            return json.dumps(
                data,
                indent=self.indent,
                ensure_ascii=self.ensure_ascii,
                default=self._json_serializer,
            )
        except Exception as e:
            return f"Error formatting JSON: {e}"

    def _json_serializer(self, obj):
        """Handle non-serializable objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)


class MarkdownFormatter(ResponseFormatter):
    """Format responses as Markdown for better readability."""

    def format(self, data: Any, title: Optional[str] = None, **kwargs) -> str:
        """Format data as Markdown."""
        if isinstance(data, dict):
            return self._format_dict(data, title)
        elif isinstance(data, list):
            return self._format_list(data, title)
        else:
            return self._format_simple(data, title)

    def _format_dict(self, data: Dict[str, Any], title: Optional[str] = None) -> str:
        """Format dictionary as Markdown."""
        lines = []

        if title:
            lines.append(f"# {title}\n")

        for key, value in data.items():
            lines.append(f"**{key}**: {self._format_value(value)}")

        return "\n".join(lines)

    def _format_list(self, data: List[Any], title: Optional[str] = None) -> str:
        """Format list as Markdown."""
        lines = []

        if title:
            lines.append(f"# {title}\n")

        for i, item in enumerate(data, 1):
            if isinstance(item, dict):
                lines.append(f"## {i}. Item")
                for key, value in item.items():
                    lines.append(f"- **{key}**: {self._format_value(value)}")
                lines.append("")
            else:
                lines.append(f"{i}. {self._format_value(item)}")

        return "\n".join(lines)

    def _format_simple(self, data: Any, title: Optional[str] = None) -> str:
        """Format simple value as Markdown."""
        lines = []

        if title:
            lines.append(f"# {title}\n")

        lines.append(str(data))
        return "\n".join(lines)

    def _format_value(self, value: Any) -> str:
        """Format individual value."""
        if isinstance(value, (list, tuple)) and len(value) <= 5:
            return ", ".join(str(v) for v in value)
        elif isinstance(value, dict) and len(value) <= 3:
            return ", ".join(f"{k}: {v}" for k, v in value.items())
        else:
            return str(value)


class TableFormatter(ResponseFormatter):
    """Format tabular data as ASCII tables."""

    def format(
        self, data: List[Dict[str, Any]], headers: Optional[List[str]] = None, **kwargs
    ) -> str:
        """Format list of dictionaries as ASCII table."""
        if not data:
            return "No data available"

        if not isinstance(data, list) or not all(
            isinstance(item, dict) for item in data
        ):
            return "Data must be a list of dictionaries for table formatting"

        # Determine headers
        if headers is None:
            headers = list(data[0].keys()) if data else []

        # Calculate column widths
        col_widths = {}
        for header in headers:
            col_widths[header] = len(header)

        for row in data:
            for header in headers:
                value = str(row.get(header, ""))
                col_widths[header] = max(col_widths[header], len(value))

        # Build table
        lines = []

        # Header row
        header_line = " | ".join(header.ljust(col_widths[header]) for header in headers)
        lines.append(header_line)

        # Separator
        separator = "-+-".join("-" * col_widths[header] for header in headers)
        lines.append(separator)

        # Data rows
        for row in data:
            row_line = " | ".join(
                str(row.get(header, "")).ljust(col_widths[header]) for header in headers
            )
            lines.append(row_line)

        return "\n".join(lines)


class SearchResultFormatter(ResponseFormatter):
    """Specialized formatter for search results."""

    def format(
        self,
        results: List[Dict[str, Any]],
        query: Optional[str] = None,
        total_count: Optional[int] = None,
        **kwargs,
    ) -> str:
        """Format search results with query context."""
        lines = []

        # Header
        if query:
            lines.append(f"# Search Results for: '{query}'\n")
        else:
            lines.append("# Search Results\n")

        # Summary
        result_count = len(results)
        if total_count and total_count > result_count:
            lines.append(f"Showing {result_count} of {total_count} results\n")
        else:
            lines.append(f"Found {result_count} results\n")

        # Results
        for i, result in enumerate(results, 1):
            lines.append(f"## {i}. {result.get('name', result.get('title', 'Result'))}")

            # Score if available
            if "_relevance_score" in result:
                score = result["_relevance_score"]
                lines.append(f"**Relevance**: {score:.2f}")

            # Description
            if "description" in result:
                lines.append(f"{result['description']}")

            # Additional fields
            for key, value in result.items():
                if key not in ["name", "title", "description", "_relevance_score"]:
                    if isinstance(value, (list, tuple)):
                        if value:  # Only show non-empty lists
                            lines.append(
                                f"**{key.title()}**: {', '.join(str(v) for v in value)}"
                            )
                    elif value:  # Only show non-empty values
                        lines.append(f"**{key.title()}**: {value}")

            lines.append("")  # Empty line between results

        return "\n".join(lines)


class MetricsFormatter(ResponseFormatter):
    """Specialized formatter for metrics data."""

    def format(self, metrics: Dict[str, Any], **kwargs) -> str:
        """Format metrics data in human-readable format."""
        lines = []
        lines.append("# Server Metrics\n")

        # Server stats
        if "server" in metrics:
            server = metrics["server"]
            lines.append("## Server Statistics")
            lines.append(
                f"- **Uptime**: {self._format_duration(server.get('uptime_seconds', 0))}"
            )
            lines.append(f"- **Total Calls**: {server.get('total_calls', 0):,}")
            lines.append(f"- **Total Errors**: {server.get('total_errors', 0):,}")
            lines.append(f"- **Error Rate**: {server.get('overall_error_rate', 0):.2%}")
            lines.append(f"- **Calls/Second**: {server.get('calls_per_second', 0):.2f}")
            lines.append("")

        # Tool stats
        if "tools" in metrics and metrics["tools"]:
            lines.append("## Tool Statistics")
            for tool_name, stats in metrics["tools"].items():
                lines.append(f"### {tool_name}")
                lines.append(f"- **Calls**: {stats.get('calls', 0):,}")
                lines.append(f"- **Errors**: {stats.get('errors', 0):,}")
                lines.append(f"- **Error Rate**: {stats.get('error_rate', 0):.2%}")

                if "avg_latency" in stats:
                    lines.append(f"- **Avg Latency**: {stats['avg_latency']:.3f}s")
                    lines.append(f"- **P95 Latency**: {stats['p95_latency']:.3f}s")

                lines.append("")

        return "\n".join(lines)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f} seconds"
        elif seconds < 3600:
            return f"{seconds/60:.1f} minutes"
        elif seconds < 86400:
            return f"{seconds/3600:.1f} hours"
        else:
            return f"{seconds/86400:.1f} days"


# Default formatter instances
json_formatter = JSONFormatter()
markdown_formatter = MarkdownFormatter()
table_formatter = TableFormatter()
search_formatter = SearchResultFormatter()
metrics_formatter = MetricsFormatter()


def format_response(data: Any, format_type: str = "json", **kwargs) -> str:
    """
    Format response using specified formatter.

    Args:
        data: Data to format
        format_type: Type of formatting ("json", "markdown", "table", "search", "metrics")
        **kwargs: Additional formatting options

    Returns:
        Formatted string
    """
    formatters = {
        "json": json_formatter,
        "markdown": markdown_formatter,
        "table": table_formatter,
        "search": search_formatter,
        "metrics": metrics_formatter,
    }

    formatter = formatters.get(format_type, json_formatter)
    return formatter.format(data, **kwargs)
