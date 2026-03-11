"""
Data Reporting Enterprise Workflow

This example demonstrates automated report generation using multi-agent collaboration.

Agents:
1. DataCollectorAgent - Collects data from various sources (database, API, files)
2. DataProcessorAgent - Processes and aggregates collected data
3. ChartGeneratorAgent - Creates visualizations and charts
4. ReportCompilerAgent - Compiles final report in various formats

Use Cases:
- Automated daily/weekly/monthly reporting
- Executive dashboards
- Performance metrics reporting
- Financial reporting
- Analytics reports

Architecture Pattern: Sequential Pipeline with Shared Memory
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class DataReportingConfig:
    """Configuration for data reporting workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    output_format: str = "pdf"  # "pdf", "html", "excel"
    chart_types: List[str] = field(default_factory=lambda: ["line", "bar", "pie"])
    schedule: Optional[str] = None  # "daily", "weekly", "monthly"
    delivery_emails: List[str] = field(default_factory=list)


# ===== Signatures =====


class DataCollectionSignature(Signature):
    """Signature for data collection."""

    data_sources: str = InputField(description="Data sources specification as JSON")

    collected_data: str = OutputField(description="Collected data as JSON")
    metadata: str = OutputField(description="Collection metadata")


class DataProcessingSignature(Signature):
    """Signature for data processing."""

    raw_data: str = InputField(description="Raw data to process as JSON")

    processed_data: str = OutputField(description="Processed and aggregated data")
    statistics: str = OutputField(description="Statistical summary")
    aggregations: str = OutputField(description="Data aggregations")


class ChartGenerationSignature(Signature):
    """Signature for chart generation."""

    processed_data: str = InputField(description="Processed data for visualization")

    charts: str = OutputField(description="Generated charts specification as JSON")


class ReportCompilationSignature(Signature):
    """Signature for report compilation."""

    report_data: str = InputField(description="Complete report data as JSON")

    report: str = OutputField(description="Compiled report content")
    report_format: str = OutputField(description="Report format")


# ===== Agents =====


class DataCollectorAgent(BaseAgent):
    """Agent for collecting data from various sources."""

    def __init__(
        self,
        config: DataReportingConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "collector",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=DataCollectionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.report_config = config

    def collect(self, sources: Dict[str, Any]) -> Dict[str, Any]:
        """Collect data from specified sources."""
        # Run agent
        result = self.run(data_sources=json.dumps(sources))

        # Extract outputs
        collected_data_raw = result.get("collected_data", "{}")

        # Parse collected data
        if isinstance(collected_data_raw, str):
            try:
                collected_data = (
                    json.loads(collected_data_raw) if collected_data_raw else {}
                )
            except:
                collected_data = {"raw": collected_data_raw}
        else:
            collected_data = (
                collected_data_raw if isinstance(collected_data_raw, dict) else {}
            )

        # Extract metadata
        metadata_raw = result.get("metadata", "{}")
        if isinstance(metadata_raw, str):
            try:
                metadata = json.loads(metadata_raw) if metadata_raw else {}
            except:
                metadata = {"raw": metadata_raw}
        else:
            metadata = metadata_raw if isinstance(metadata_raw, dict) else {}

        # Ensure required fields
        if "sources_processed" not in metadata:
            metadata["sources_processed"] = len(sources)

        collection_result = {"data": collected_data, "metadata": metadata}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=collection_result,  # Auto-serialized
            tags=["collected_data", "pipeline"],
            importance=0.8,
            segment="pipeline",
        )

        return collection_result


class DataProcessorAgent(BaseAgent):
    """Agent for processing and aggregating data."""

    def __init__(
        self,
        config: DataReportingConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "processor",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=DataProcessingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.report_config = config

    def process(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process and aggregate raw data."""
        # Run agent
        result = self.run(raw_data=json.dumps(raw_data))

        # Extract outputs
        processed_data_raw = result.get("processed_data", "{}")
        if isinstance(processed_data_raw, str):
            try:
                processed_data = (
                    json.loads(processed_data_raw) if processed_data_raw else {}
                )
            except:
                processed_data = {"raw": processed_data_raw}
        else:
            processed_data = (
                processed_data_raw if isinstance(processed_data_raw, dict) else {}
            )

        statistics_raw = result.get("statistics", "{}")
        if isinstance(statistics_raw, str):
            try:
                statistics = json.loads(statistics_raw) if statistics_raw else {}
            except:
                statistics = {"raw": statistics_raw}
        else:
            statistics = statistics_raw if isinstance(statistics_raw, dict) else {}

        aggregations_raw = result.get("aggregations", "{}")
        if isinstance(aggregations_raw, str):
            try:
                aggregations = json.loads(aggregations_raw) if aggregations_raw else {}
            except:
                aggregations = {"raw": aggregations_raw}
        else:
            aggregations = (
                aggregations_raw if isinstance(aggregations_raw, dict) else {}
            )

        processing_result = {
            "processed_data": processed_data,
            "statistics": statistics,
            "aggregations": aggregations,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=processing_result,  # Auto-serialized
            tags=["processed_data", "pipeline"],
            importance=0.9,
            segment="pipeline",
        )

        return processing_result


class ChartGeneratorAgent(BaseAgent):
    """Agent for generating charts and visualizations."""

    def __init__(
        self,
        config: DataReportingConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "chart_generator",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ChartGenerationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.report_config = config

    def generate_charts(self, processed_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate charts from processed data."""
        # Run agent
        result = self.run(processed_data=json.dumps(processed_data))

        # Extract outputs
        charts_raw = result.get("charts", "[]")
        if isinstance(charts_raw, str):
            try:
                charts = json.loads(charts_raw) if charts_raw else []
            except:
                charts = [{"type": "default", "data": charts_raw}]
        else:
            charts = (
                charts_raw
                if isinstance(charts_raw, list)
                else [charts_raw] if charts_raw else []
            )

        chart_result = {"charts": charts}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=chart_result,  # Auto-serialized
            tags=["charts", "pipeline"],
            importance=0.9,
            segment="pipeline",
        )

        return chart_result


class ReportCompilerAgent(BaseAgent):
    """Agent for compiling final report."""

    def __init__(
        self,
        config: DataReportingConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "compiler",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ReportCompilationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.report_config = config

    def compile_report(self, report_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compile final report."""
        # Run agent
        result = self.run(report_data=json.dumps(report_data))

        # Extract outputs
        report = result.get("report", "Report not generated")
        report_format_raw = result.get(
            "report_format", self.report_config.output_format
        )

        # Validate format or use config default
        valid_formats = ["pdf", "html", "excel"]
        report_format = (
            report_format_raw
            if report_format_raw in valid_formats
            else self.report_config.output_format
        )

        compilation_result = {"report": report, "format": report_format}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=compilation_result,  # Auto-serialized
            tags=["final_report", "pipeline"],
            importance=1.0,
            segment="pipeline",
        )

        return compilation_result


# ===== Workflow Functions =====


def data_reporting_workflow(
    report_spec: Dict[str, Any], config: Optional[DataReportingConfig] = None
) -> Dict[str, Any]:
    """
    Execute data reporting workflow.

    Args:
        report_spec: Report specification with 'title', 'sources', etc.
        config: Configuration for data reporting

    Returns:
        Complete report with collected data, processing, charts, and final report
    """
    if config is None:
        config = DataReportingConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    collector = DataCollectorAgent(config, shared_pool, "collector")
    processor = DataProcessorAgent(config, shared_pool, "processor")
    chart_generator = ChartGeneratorAgent(config, shared_pool, "chart_generator")
    compiler = ReportCompilerAgent(config, shared_pool, "compiler")

    # Execute pipeline
    # Stage 1: Collect data
    sources = report_spec.get("sources", {})
    collected = collector.collect(sources)

    # Stage 2: Process data
    processed = processor.process(collected["data"])

    # Stage 3: Generate charts
    charts = chart_generator.generate_charts(processed["processed_data"])

    # Stage 4: Compile report
    report_data = {
        "title": report_spec.get("title", "Untitled Report"),
        "data": processed["processed_data"],
        "statistics": processed["statistics"],
        "aggregations": processed["aggregations"],
        "charts": charts["charts"],
    }

    final_report = compiler.compile_report(report_data)

    return {
        "title": report_spec.get("title", "Untitled Report"),
        "collected": collected,
        "processed": processed,
        "charts": charts,
        "final_report": final_report,
    }


def batch_reporting_workflow(
    report_specs: List[Dict[str, Any]], config: Optional[DataReportingConfig] = None
) -> List[Dict[str, Any]]:
    """
    Execute batch reporting workflow on multiple report specifications.

    Args:
        report_specs: List of report specifications
        config: Configuration for data reporting

    Returns:
        List of complete reports
    """
    if config is None:
        config = DataReportingConfig()

    results = []

    # Process each report
    for spec in report_specs:
        result = data_reporting_workflow(spec, config)
        results.append(result)

    return results


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = DataReportingConfig(llm_provider="mock")

    # Single report generation
    report_spec = {
        "title": "Monthly Sales Report",
        "sources": {
            "database": "SELECT * FROM sales WHERE month = 'January'",
            "api": "https://api.example.com/sales/metrics",
        },
        "report_type": "sales",
        "format": "pdf",
    }

    print("=== Single Report Generation ===")
    result = data_reporting_workflow(report_spec, config)
    print(f"Report: {result['title']}")
    print(
        f"Sources processed: {result['collected']['metadata'].get('sources_processed', 0)}"
    )
    print(f"Charts generated: {len(result['charts']['charts'])}")
    print(f"Format: {result['final_report']['format']}")

    # Batch report generation
    report_specs = [
        {"title": "Sales Report", "sources": {"database": "sales"}},
        {"title": "Revenue Report", "sources": {"database": "revenue"}},
        {
            "title": "User Analytics",
            "sources": {"api": "https://api.example.com/users"},
        },
    ]

    print("\n=== Batch Report Generation ===")
    results = batch_reporting_workflow(report_specs, config)
    print(f"Generated {len(results)} reports")
    for i, result in enumerate(results, 1):
        print(f"{i}. {result['title']}: {result['final_report']['format']}")
