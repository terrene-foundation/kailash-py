"""
Tests for data-reporting enterprise workflow example.

This test suite validates:
1. Individual agent behavior (DataCollectorAgent, DataProcessorAgent, ChartGeneratorAgent, ReportCompilerAgent)
2. Workflow integration and multi-agent collaboration
3. Shared memory usage for report generation pipeline
4. Real-world automated reporting scenarios

Following TDD methodology - these tests are written BEFORE implementation.
"""

# Standardized example loading
from example_import_helper import import_example_module

# Load data-reporting example
_data_reporting_module = import_example_module(
    "examples/3-enterprise-workflows/data-reporting"
)
DataCollectorAgent = _data_reporting_module.DataCollectorAgent
DataProcessorAgent = _data_reporting_module.DataProcessorAgent
ChartGeneratorAgent = _data_reporting_module.ChartGeneratorAgent
ReportCompilerAgent = _data_reporting_module.ReportCompilerAgent
DataReportingConfig = _data_reporting_module.DataReportingConfig
batch_reporting_workflow = _data_reporting_module.batch_reporting_workflow
data_reporting_workflow = _data_reporting_module.data_reporting_workflow


class TestDataReportingAgents:
    """Test individual agent behavior."""

    def test_data_collector_agent_collects_data(self):
        """Test DataCollectorAgent collects data from sources."""

        config = DataReportingConfig(llm_provider="mock")
        agent = DataCollectorAgent(config)

        sources = {
            "database": "SELECT * FROM sales WHERE date >= '2024-01-01'",
            "api": "https://api.example.com/metrics",
            "file": "data/monthly_stats.csv",
        }

        result = agent.collect(sources)

        assert result is not None
        assert "data" in result
        assert "metadata" in result
        assert "sources_processed" in result["metadata"]

    def test_data_processor_agent_processes_data(self):
        """Test DataProcessorAgent processes and aggregates data."""

        config = DataReportingConfig(llm_provider="mock")
        agent = DataProcessorAgent(config)

        raw_data = {"sales": [100, 200, 300, 400], "revenue": [1000, 2000, 3000, 4000]}

        result = agent.process(raw_data)

        assert result is not None
        assert "processed_data" in result
        assert "statistics" in result
        assert "aggregations" in result

    def test_chart_generator_agent_creates_charts(self):
        """Test ChartGeneratorAgent creates visualizations.

        Note: With mock provider, we test structure only. Content depends on
        LLM provider (real or mock).
        """
        config = DataReportingConfig(llm_provider="mock")
        agent = ChartGeneratorAgent(config)

        processed_data = {
            "sales_trend": [100, 150, 200, 250],
            "revenue_by_region": {"North": 10000, "South": 15000},
        }

        result = agent.generate_charts(processed_data)

        # Structure test only - charts may be empty list with mock provider
        assert result is not None
        assert "charts" in result
        assert isinstance(result["charts"], list)

    def test_report_compiler_agent_compiles_report(self):
        """Test ReportCompilerAgent compiles final report."""

        config = DataReportingConfig(llm_provider="mock")
        agent = ReportCompilerAgent(config)

        report_data = {
            "title": "Monthly Sales Report",
            "data": {"total_sales": 5000},
            "charts": [{"type": "line", "data": [1, 2, 3]}],
        }

        result = agent.compile_report(report_data)

        assert result is not None
        assert "report" in result
        assert "format" in result


class TestDataReportingWorkflow:
    """Test complete data reporting workflow."""

    def test_single_report_generation(self):
        """Test generating a single report."""

        config = DataReportingConfig(llm_provider="mock")

        report_spec = {
            "title": "Q1 Sales Report",
            "sources": {"database": "SELECT * FROM sales"},
            "report_type": "sales",
            "format": "pdf",
        }

        result = data_reporting_workflow(report_spec, config)

        assert result is not None
        assert "collected" in result
        assert "processed" in result
        assert "charts" in result
        assert "final_report" in result

    def test_batch_report_generation(self):
        """Test generating multiple reports."""

        config = DataReportingConfig(llm_provider="mock")

        report_specs = [
            {
                "title": "Sales Report",
                "sources": {"db": "sales"},
                "report_type": "sales",
            },
            {
                "title": "Revenue Report",
                "sources": {"db": "revenue"},
                "report_type": "financial",
            },
            {
                "title": "User Report",
                "sources": {"db": "users"},
                "report_type": "analytics",
            },
        ]

        results = batch_reporting_workflow(report_specs, config)

        assert results is not None
        assert len(results) == 3
        assert all("final_report" in r for r in results)

    def test_scheduled_report_generation(self):
        """Test scheduled report generation."""

        config = DataReportingConfig(llm_provider="mock", schedule="daily")

        report_spec = {
            "title": "Daily Summary",
            "sources": {"database": "SELECT * FROM daily_stats"},
            "report_type": "summary",
        }

        result = data_reporting_workflow(report_spec, config)

        assert result is not None


class TestSharedMemoryIntegration:
    """Test shared memory usage in data reporting pipeline."""

    def test_collector_writes_to_shared_memory(self):
        """Test DataCollectorAgent writes collected data to shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = DataReportingConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()
        agent = DataCollectorAgent(config, shared_pool, "collector")

        sources = {"database": "SELECT * FROM sales"}
        agent.collect(sources)

        # Check shared memory
        insights = shared_pool.read_relevant(
            agent_id="processor", tags=["collected_data"], segments=["pipeline"]
        )

        assert len(insights) > 0
        assert insights[0]["agent_id"] == "collector"

    def test_processor_reads_from_shared_memory(self):
        """Test DataProcessorAgent reads collected data from shared memory."""
        from kaizen.memory.shared_memory import SharedMemoryPool

        config = DataReportingConfig(llm_provider="mock")
        shared_pool = SharedMemoryPool()

        collector = DataCollectorAgent(config, shared_pool, "collector")
        DataProcessorAgent(config, shared_pool, "processor")

        # Collector writes
        sources = {"database": "SELECT * FROM sales"}
        collector.collect(sources)

        # Processor reads
        insights = shared_pool.read_relevant(
            agent_id="processor", tags=["collected_data"], segments=["pipeline"]
        )

        assert len(insights) > 0

    def test_pipeline_coordination_via_shared_memory(self):
        """Test full pipeline coordination via shared memory."""

        config = DataReportingConfig(llm_provider="mock")

        report_spec = {
            "title": "Test Report",
            "sources": {"database": "SELECT * FROM test"},
        }

        result = data_reporting_workflow(report_spec, config)

        # All stages should complete
        assert "collected" in result
        assert "processed" in result
        assert "charts" in result
        assert "final_report" in result


class TestEnterpriseFeatures:
    """Test enterprise-specific features."""

    def test_multi_source_data_collection(self):
        """Test collecting data from multiple sources."""

        config = DataReportingConfig(llm_provider="mock")
        agent = DataCollectorAgent(config)

        sources = {
            "database": "SELECT * FROM sales",
            "api": "https://api.example.com/metrics",
            "file": "data.csv",
            "stream": "kafka://topic",
        }

        result = agent.collect(sources)

        assert result["metadata"]["sources_processed"] >= 1

    def test_custom_chart_types(self):
        """Test custom chart type generation."""

        config = DataReportingConfig(
            llm_provider="mock", chart_types=["line", "bar", "pie", "scatter"]
        )

        agent = ChartGeneratorAgent(config)
        processed_data = {"trend": [1, 2, 3, 4]}

        result = agent.generate_charts(processed_data)

        assert "charts" in result

    def test_report_format_options(self):
        """Test different report format options."""

        # PDF format
        config_pdf = DataReportingConfig(llm_provider="mock", output_format="pdf")
        agent_pdf = ReportCompilerAgent(config_pdf)

        report_data = {"title": "Test Report", "data": {}}
        result = agent_pdf.compile_report(report_data)

        assert "report" in result
        assert result["format"] in ["pdf", "html", "excel"]

    def test_error_handling_missing_data(self):
        """Test error handling for missing data sources."""

        config = DataReportingConfig(llm_provider="mock")

        # Missing sources
        report_spec = {"title": "Test"}  # Missing sources

        result = data_reporting_workflow(report_spec, config)

        # Should handle gracefully
        assert result is not None


class TestConfigurationOptions:
    """Test configuration options."""

    def test_default_config(self):
        """Test default configuration."""

        config = DataReportingConfig()

        assert config.llm_provider == "mock"
        assert config.model == "gpt-3.5-turbo"
        assert config.output_format == "pdf"

    def test_custom_config(self):
        """Test custom configuration."""

        config = DataReportingConfig(
            llm_provider="openai",
            model="gpt-4",
            output_format="excel",
            chart_types=["line", "bar"],
            schedule="daily",
        )

        assert config.llm_provider == "openai"
        assert config.model == "gpt-4"
        assert config.output_format == "excel"
        assert len(config.chart_types) == 2

    def test_scheduling_config(self):
        """Test scheduling configuration."""

        config = DataReportingConfig(
            llm_provider="mock", schedule="daily", delivery_emails=["admin@example.com"]
        )

        assert config.schedule == "daily"
        assert len(config.delivery_emails) == 1
