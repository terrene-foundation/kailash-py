"""Log processing node for comprehensive log analysis and management.

This module provides advanced log processing capabilities including parsing,
filtering, aggregation, pattern matching, and forwarding to various backends.
"""

import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """Standard log levels for filtering."""

    CRITICAL = 50
    ERROR = 40
    WARNING = 30
    INFO = 20
    DEBUG = 10
    NOTSET = 0


class LogFormat(Enum):
    """Supported log output formats."""

    JSON = "json"
    STRUCTURED = "structured"
    RAW = "raw"
    SYSLOG = "syslog"
    ELK = "elk"  # Elasticsearch/Logstash/Kibana format


class AggregationType(Enum):
    """Types of log aggregation."""

    COUNT = "count"
    RATE = "rate"
    UNIQUE = "unique"
    TOP_VALUES = "top_values"
    TIMELINE = "timeline"


@register_node()
class LogProcessorNode(AsyncNode):
    """Node for processing, filtering, and analyzing logs.

    This node provides comprehensive log processing capabilities including:
    - Multi-format log parsing (JSON, structured text, regex patterns)
    - Advanced filtering by level, timestamp, content, and custom rules
    - Pattern extraction and field parsing
    - Log aggregation and statistics
    - Real-time alerting on log patterns
    - Output formatting for various backends
    - Log forwarding and streaming

    Design Purpose:
    - Centralized log processing for monitoring and observability
    - Real-time log analysis and alerting
    - Log data enrichment and transformation
    - Support for various log backends and formats

    Examples:
        >>> # Basic log filtering and parsing
        >>> processor = LogProcessorNode()
        >>> result = await processor.execute(
        ...     logs=[
        ...         "2024-01-01 10:00:00 ERROR Failed to connect to database",
        ...         "2024-01-01 10:00:01 INFO User logged in successfully",
        ...         "2024-01-01 10:00:02 WARNING High memory usage detected"
        ...     ],
        ...     filters={"min_level": "WARNING"},
        ...     output_format="json"
        ... )

        >>> # Advanced pattern matching and alerting
        >>> result = await processor.execute(
        ...     logs=log_stream,
        ...     patterns=[
        ...         {"name": "error_spike", "regex": r"ERROR.*database", "threshold": 5},
        ...         {"name": "auth_failure", "regex": r"authentication.*failed", "threshold": 3}
        ...     ],
        ...     aggregation={"type": "timeline", "interval": 60}
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the log processor node."""
        super().__init__(**kwargs)
        self.compiled_patterns: Dict[str, Pattern] = {}
        self.aggregation_buffer: List[Dict[str, Any]] = []
        self.last_aggregation_time = time.time()
        self.logger.info(f"Initialized LogProcessorNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "logs": NodeParameter(
                name="logs",
                type=Any,
                required=True,
                description="Log entries to process (string or list of strings)",
            ),
            "log_format": NodeParameter(
                name="log_format",
                type=str,
                required=False,
                default="auto",
                description="Input log format (auto, json, structured, raw)",
            ),
            "filters": NodeParameter(
                name="filters",
                type=dict,
                required=False,
                default={},
                description="Filtering criteria for logs",
            ),
            "patterns": NodeParameter(
                name="patterns",
                type=list,
                required=False,
                default=[],
                description="Pattern extraction and matching rules",
            ),
            "aggregation": NodeParameter(
                name="aggregation",
                type=dict,
                required=False,
                default={},
                description="Aggregation configuration",
            ),
            "output_format": NodeParameter(
                name="output_format",
                type=str,
                required=False,
                default="json",
                description="Output format (json, structured, raw, syslog, elk)",
            ),
            "enrichment": NodeParameter(
                name="enrichment",
                type=dict,
                required=False,
                default={},
                description="Log enrichment configuration",
            ),
            "alerts": NodeParameter(
                name="alerts",
                type=list,
                required=False,
                default=[],
                description="Alert rules for pattern matching",
            ),
            "max_buffer_size": NodeParameter(
                name="max_buffer_size",
                type=int,
                required=False,
                default=10000,
                description="Maximum number of logs to buffer",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "processed_logs": NodeParameter(
                name="processed_logs",
                type=list,
                description="Processed and filtered log entries",
            ),
            "filtered_count": NodeParameter(
                name="filtered_count",
                type=int,
                description="Number of logs that passed filters",
            ),
            "total_count": NodeParameter(
                name="total_count",
                type=int,
                description="Total number of input logs",
            ),
            "patterns_matched": NodeParameter(
                name="patterns_matched",
                type=dict,
                description="Pattern matching results and counts",
            ),
            "aggregations": NodeParameter(
                name="aggregations",
                type=dict,
                description="Log aggregation results",
            ),
            "alerts_triggered": NodeParameter(
                name="alerts_triggered",
                type=list,
                description="Alerts triggered during processing",
            ),
            "processing_time": NodeParameter(
                name="processing_time",
                type=float,
                description="Time taken to process logs",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=str,
                description="ISO timestamp of processing",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Process logs based on configuration."""
        logs = kwargs["logs"]
        log_format = kwargs.get("log_format", "auto")
        filters = kwargs.get("filters", {})
        patterns = kwargs.get("patterns", [])
        aggregation = kwargs.get("aggregation", {})
        output_format = LogFormat(kwargs.get("output_format", "json"))
        enrichment = kwargs.get("enrichment", {})
        alerts = kwargs.get("alerts", [])
        max_buffer_size = kwargs.get("max_buffer_size", 10000)

        start_time = time.time()

        try:
            # Validate input
            if logs is None:
                raise ValueError("Logs parameter cannot be None")

            # Normalize input logs to list
            if isinstance(logs, str):
                logs = [logs]

            # Validate buffer size
            if len(logs) > max_buffer_size:
                self.logger.warning(
                    f"Input logs ({len(logs)}) exceed buffer size ({max_buffer_size}), truncating"
                )
                logs = logs[:max_buffer_size]

            # Parse logs
            parsed_logs = await self._parse_logs(logs, log_format)

            # Apply filters
            filtered_logs = await self._filter_logs(parsed_logs, filters)

            # Process patterns
            pattern_results = await self._process_patterns(filtered_logs, patterns)

            # Enrich logs if configured
            if enrichment:
                filtered_logs = await self._enrich_logs(filtered_logs, enrichment)

            # Process aggregations
            aggregation_results = await self._process_aggregations(
                filtered_logs, aggregation
            )

            # Check alert rules
            alerts_triggered = await self._check_alerts(
                filtered_logs, alerts, pattern_results
            )

            # Format output
            formatted_logs = await self._format_output(filtered_logs, output_format)

            processing_time = time.time() - start_time

            return {
                "success": True,
                "processed_logs": formatted_logs,
                "filtered_count": len(filtered_logs),
                "total_count": len(logs),
                "patterns_matched": pattern_results,
                "aggregations": aggregation_results,
                "alerts_triggered": alerts_triggered,
                "processing_time": processing_time,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Log processing failed: {str(e)}")
            raise NodeExecutionError(f"Failed to process logs: {str(e)}")

    async def _parse_logs(
        self, logs: List[str], log_format: str
    ) -> List[Dict[str, Any]]:
        """Parse raw log entries into structured format."""
        parsed_logs = []

        for log_entry in logs:
            try:
                if log_format == "json":
                    parsed_log = json.loads(log_entry)
                elif log_format == "auto":
                    # Try JSON first, then fall back to structured parsing
                    try:
                        parsed_log = json.loads(log_entry)
                    except json.JSONDecodeError:
                        parsed_log = await self._parse_structured_log(log_entry)
                else:
                    parsed_log = await self._parse_structured_log(log_entry)

                # Ensure required fields
                if "timestamp" not in parsed_log:
                    parsed_log["timestamp"] = datetime.now(UTC).isoformat()
                if "level" not in parsed_log:
                    parsed_log["level"] = await self._extract_log_level(log_entry)
                if "message" not in parsed_log:
                    parsed_log["message"] = log_entry

                parsed_logs.append(parsed_log)

            except Exception as e:
                # If parsing fails, create a minimal log entry
                self.logger.debug(f"Failed to parse log entry, using raw: {str(e)}")
                parsed_logs.append(
                    {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "level": "INFO",
                        "message": log_entry,
                        "raw": True,
                        "parse_error": str(e),
                    }
                )

        return parsed_logs

    async def _parse_structured_log(self, log_entry: str) -> Dict[str, Any]:
        """Parse structured log entries using common patterns."""
        # Common log patterns
        patterns = [
            # ISO timestamp + level + message
            r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+(?P<level>\w+)\s+(?P<message>.*)",
            # Date time + level + message
            r"(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+(?P<level>\w+)\s+(?P<message>.*)",
            # Syslog format
            r"(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<hostname>\S+)\s+(?P<program>\S+):\s+(?P<message>.*)",
            # Simple level + message
            r"(?P<level>\w+):\s+(?P<message>.*)",
        ]

        for pattern in patterns:
            match = re.match(pattern, log_entry.strip())
            if match:
                return match.groupdict()

        # If no pattern matches, return as raw message
        return {"message": log_entry}

    async def _extract_log_level(self, log_entry: str) -> str:
        """Extract log level from raw log entry."""
        level_patterns = {
            "CRITICAL": ["critical", "fatal", "crit"],
            "ERROR": ["error", "err"],
            "WARNING": ["warning", "warn"],
            "INFO": ["info", "information"],
            "DEBUG": ["debug", "trace"],
        }

        log_lower = log_entry.lower()
        for level, keywords in level_patterns.items():
            for keyword in keywords:
                if keyword in log_lower:
                    return level

        return "INFO"  # Default level

    async def _filter_logs(
        self, logs: List[Dict[str, Any]], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply filtering criteria to logs."""
        if not filters:
            return logs

        filtered_logs = []

        for log_entry in logs:
            # Level filtering
            if "min_level" in filters:
                min_level = LogLevel[filters["min_level"].upper()]
                log_level = LogLevel[log_entry.get("level", "INFO").upper()]
                if log_level.value < min_level.value:
                    continue

            # Time range filtering
            if "start_time" in filters or "end_time" in filters:
                log_time = datetime.fromisoformat(
                    log_entry.get("timestamp", datetime.now(UTC).isoformat())
                )

                if "start_time" in filters:
                    start_time = datetime.fromisoformat(filters["start_time"])
                    if log_time < start_time:
                        continue

                if "end_time" in filters:
                    end_time = datetime.fromisoformat(filters["end_time"])
                    if log_time > end_time:
                        continue

            # Content filtering
            if "contains" in filters:
                if filters["contains"] not in log_entry.get("message", ""):
                    continue

            if "excludes" in filters:
                exclude_text = filters["excludes"]
                # Check in message, level, or raw fields
                if (
                    exclude_text in log_entry.get("message", "")
                    or exclude_text in log_entry.get("level", "")
                    or exclude_text in str(log_entry.get("raw", ""))
                ):
                    continue

            # Regex filtering
            if "regex" in filters:
                if not re.search(filters["regex"], log_entry.get("message", "")):
                    continue

            # Field-based filtering
            if "fields" in filters:
                field_match = True
                for field, value in filters["fields"].items():
                    if log_entry.get(field) != value:
                        field_match = False
                        break
                if not field_match:
                    continue

            filtered_logs.append(log_entry)

        return filtered_logs

    async def _process_patterns(
        self, logs: List[Dict[str, Any]], patterns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process pattern matching and extraction rules."""
        if not patterns:
            return {}

        pattern_results = {}

        for pattern_config in patterns:
            pattern_name = pattern_config.get("name", "unnamed")
            regex_pattern = pattern_config.get("regex")
            extract_fields = pattern_config.get("extract_fields", [])

            if not regex_pattern:
                continue

            # Compile pattern if not already compiled
            if pattern_name not in self.compiled_patterns:
                try:
                    self.compiled_patterns[pattern_name] = re.compile(regex_pattern)
                except re.error as e:
                    self.logger.warning(f"Invalid regex pattern '{pattern_name}': {e}")
                    continue

            compiled_pattern = self.compiled_patterns[pattern_name]
            matches = []
            match_count = 0

            for log_entry in logs:
                message = log_entry.get("message", "")
                level = log_entry.get("level", "")
                # Search in message first, then in level + message combined
                match = compiled_pattern.search(message)
                if not match and level:
                    combined_text = f"{level} {message}"
                    match = compiled_pattern.search(combined_text)

                if match:
                    match_count += 1
                    match_data = {
                        "timestamp": log_entry.get("timestamp"),
                        "full_match": match.group(0),
                        "groups": match.groups(),
                        "log_entry": log_entry,
                    }

                    # Extract named groups
                    if match.groupdict():
                        match_data["named_groups"] = match.groupdict()

                    # Extract specified fields
                    if extract_fields:
                        extracted = {}
                        for field in extract_fields:
                            if field in log_entry:
                                extracted[field] = log_entry[field]
                        match_data["extracted_fields"] = extracted

                    matches.append(match_data)

            pattern_results[pattern_name] = {
                "match_count": match_count,
                "matches": matches,
                "pattern": regex_pattern,
            }

        return pattern_results

    async def _enrich_logs(
        self, logs: List[Dict[str, Any]], enrichment: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Enrich logs with additional data."""
        enriched_logs = []

        for log_entry in logs.copy():
            # Add static fields
            if "static_fields" in enrichment:
                log_entry.update(enrichment["static_fields"])

            # Add computed fields
            if "computed_fields" in enrichment:
                for field_name, computation in enrichment["computed_fields"].items():
                    if computation["type"] == "timestamp_parse":
                        # Parse timestamp to components
                        try:
                            dt = datetime.fromisoformat(log_entry.get("timestamp", ""))
                            log_entry[field_name] = {
                                "year": dt.year,
                                "month": dt.month,
                                "day": dt.day,
                                "hour": dt.hour,
                                "minute": dt.minute,
                                "weekday": dt.strftime("%A"),
                            }
                        except Exception:
                            log_entry[field_name] = None

                    elif computation["type"] == "field_extraction":
                        # Extract field using regex
                        source_field = computation.get("source_field", "message")
                        pattern = computation.get("pattern")
                        if pattern and source_field in log_entry:
                            match = re.search(pattern, str(log_entry[source_field]))
                            if match:
                                log_entry[field_name] = (
                                    match.group(1) if match.groups() else match.group(0)
                                )

            # Add processing metadata
            log_entry["_processed_at"] = datetime.now(UTC).isoformat()
            log_entry["_processor_id"] = self.id

            enriched_logs.append(log_entry)

        return enriched_logs

    async def _process_aggregations(
        self, logs: List[Dict[str, Any]], aggregation: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process log aggregations."""
        if not aggregation:
            return {}

        agg_type = AggregationType(aggregation.get("type", "count"))
        field = aggregation.get("field", "level")
        interval = aggregation.get("interval", 60)  # seconds

        results = {}

        if agg_type == AggregationType.COUNT:
            # Count by field values
            counts = {}
            for log_entry in logs:
                value = log_entry.get(field, "unknown")
                counts[value] = counts.get(value, 0) + 1
            results["counts"] = counts

        elif agg_type == AggregationType.RATE:
            # Calculate rate over time
            if logs:
                time_span = (
                    datetime.fromisoformat(logs[-1]["timestamp"])
                    - datetime.fromisoformat(logs[0]["timestamp"])
                ).total_seconds()
                if time_span > 0:
                    results["rate"] = len(logs) / time_span
                else:
                    results["rate"] = 0

        elif agg_type == AggregationType.UNIQUE:
            # Count unique values
            unique_values = set()
            for log_entry in logs:
                value = log_entry.get(field)
                if value is not None:
                    unique_values.add(str(value))
            results["unique_count"] = len(unique_values)
            results["unique_values"] = list(unique_values)

        elif agg_type == AggregationType.TOP_VALUES:
            # Top N values by count
            counts = {}
            for log_entry in logs:
                value = log_entry.get(field, "unknown")
                counts[value] = counts.get(value, 0) + 1

            top_n = aggregation.get("top_n", 10)
            top_values = sorted(counts.items(), key=lambda x: x[1], reverse=True)[
                :top_n
            ]
            results["top_values"] = top_values

        elif agg_type == AggregationType.TIMELINE:
            # Timeline aggregation
            timeline = {}
            for log_entry in logs:
                timestamp = datetime.fromisoformat(log_entry["timestamp"])
                # Round to interval
                interval_start = timestamp.replace(second=0, microsecond=0)
                if interval >= 3600:  # Hour intervals
                    interval_start = interval_start.replace(minute=0)

                interval_key = interval_start.isoformat()
                if interval_key not in timeline:
                    timeline[interval_key] = 0
                timeline[interval_key] += 1

            results["timeline"] = timeline

        return results

    async def _check_alerts(
        self,
        logs: List[Dict[str, Any]],
        alerts: List[Dict[str, Any]],
        pattern_results: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Check alert rules and trigger alerts."""
        triggered_alerts = []

        for alert_config in alerts:
            alert_name = alert_config.get("name", "unnamed")
            alert_type = alert_config.get("type", "threshold")

            if alert_type == "threshold":
                # Threshold-based alerts
                threshold = alert_config.get("threshold", 0)
                field = alert_config.get("field", "level")
                condition = alert_config.get("condition", "ERROR")

                count = sum(1 for log in logs if log.get(field) == condition)
                if count >= threshold:
                    triggered_alerts.append(
                        {
                            "name": alert_name,
                            "type": alert_type,
                            "triggered_at": datetime.now(UTC).isoformat(),
                            "threshold": threshold,
                            "actual_count": count,
                            "condition": condition,
                            "severity": alert_config.get("severity", "medium"),
                        }
                    )

            elif alert_type == "pattern":
                # Pattern-based alerts
                pattern_name = alert_config.get("pattern_name")
                threshold = alert_config.get("threshold", 1)

                if pattern_name in pattern_results:
                    match_count = pattern_results[pattern_name]["match_count"]
                    if match_count >= threshold:
                        triggered_alerts.append(
                            {
                                "name": alert_name,
                                "type": alert_type,
                                "triggered_at": datetime.now(UTC).isoformat(),
                                "pattern_name": pattern_name,
                                "threshold": threshold,
                                "match_count": match_count,
                                "severity": alert_config.get("severity", "medium"),
                            }
                        )

            elif alert_type == "rate":
                # Rate-based alerts
                time_window = alert_config.get("time_window", 300)  # 5 minutes
                rate_threshold = alert_config.get(
                    "rate_threshold", 10
                )  # logs per second

                now = datetime.now(UTC)
                window_start = now - timedelta(seconds=time_window)

                recent_logs = [
                    log
                    for log in logs
                    if datetime.fromisoformat(log["timestamp"]) >= window_start
                ]

                if recent_logs:
                    rate = len(recent_logs) / time_window
                    if rate >= rate_threshold:
                        triggered_alerts.append(
                            {
                                "name": alert_name,
                                "type": alert_type,
                                "triggered_at": datetime.now(UTC).isoformat(),
                                "rate_threshold": rate_threshold,
                                "actual_rate": rate,
                                "time_window": time_window,
                                "log_count": len(recent_logs),
                                "severity": alert_config.get("severity", "medium"),
                            }
                        )

        return triggered_alerts

    async def _format_output(
        self, logs: List[Dict[str, Any]], output_format: LogFormat
    ) -> Union[List[Dict[str, Any]], List[str], str]:
        """Format logs according to specified output format."""
        if output_format == LogFormat.JSON:
            return logs

        elif output_format == LogFormat.RAW:
            return [log.get("message", str(log)) for log in logs]

        elif output_format == LogFormat.STRUCTURED:
            formatted = []
            for log in logs:
                timestamp = log.get("timestamp", "")
                level = log.get("level", "INFO")
                message = log.get("message", "")
                formatted.append(f"{timestamp} {level} {message}")
            return formatted

        elif output_format == LogFormat.SYSLOG:
            formatted = []
            for log in logs:
                timestamp = log.get("timestamp", "")
                hostname = log.get("hostname", "localhost")
                program = log.get("program", "kailash")
                message = log.get("message", "")
                formatted.append(f"{timestamp} {hostname} {program}: {message}")
            return formatted

        elif output_format == LogFormat.ELK:
            # Elasticsearch/Logstash/Kibana format
            elk_logs = []
            for log in logs:
                elk_log = {
                    "@timestamp": log.get("timestamp"),
                    "@version": "1",
                    "message": log.get("message"),
                    "level": log.get("level"),
                    "logger_name": log.get("logger", "kailash"),
                    "thread_name": log.get("thread", "main"),
                    "fields": {
                        k: v
                        for k, v in log.items()
                        if k not in ["timestamp", "message", "level"]
                    },
                }
                elk_logs.append(elk_log)
            return elk_logs

        return logs

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            try:
                result = asyncio.run(self.async_run(**kwargs))
                return result
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "processed_logs": [],
                    "filtered_count": 0,
                    "total_count": 0,
                    "patterns_matched": {},
                    "aggregations": {},
                    "alerts_triggered": [],
                    "processing_time": 0.0,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
        else:
            # Event loop is running, create a task
            import concurrent.futures

            try:
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.async_run(**kwargs))
                    result = future.result()
                    return result
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "processed_logs": [],
                    "filtered_count": 0,
                    "total_count": 0,
                    "patterns_matched": {},
                    "aggregations": {},
                    "alerts_triggered": [],
                    "processing_time": 0.0,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
