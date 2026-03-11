# Data Reporting Enterprise Workflow

**Category**: Enterprise Workflows
**Pattern**: Multi-Agent Sequential Pipeline
**Complexity**: Intermediate
**Use Cases**: Automated reporting, executive dashboards, performance metrics, financial reporting, analytics reports

## Overview

This example demonstrates an automated report generation pipeline using four specialized agents that collaborate through SharedMemoryPool to collect, process, visualize, and compile business reports.

### Key Features

- **Multi-source data collection** - Collect from databases, APIs, files, streams
- **Automated processing** - Process and aggregate data with statistics
- **Chart generation** - Create visualizations (line, bar, pie, scatter)
- **Flexible formats** - Generate reports in PDF, HTML, Excel
- **Batch processing** - Generate multiple reports concurrently
- **Scheduled reporting** - Support for daily, weekly, monthly schedules

## Architecture

```
Report Specification
     |
     v
┌─────────────────────┐
│ DataCollectorAgent  │ - Collects data from multiple sources
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["collected_data", "pipeline"]
           │
           v
┌─────────────────────┐
│ DataProcessorAgent  │ - Processes and aggregates data
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["processed_data", "pipeline"]
           │
           v
┌─────────────────────┐
│ChartGeneratorAgent  │ - Creates charts and visualizations
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["charts", "pipeline"]
           │
           v
┌─────────────────────┐
│ReportCompilerAgent  │ - Compiles final report
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["final_report", "pipeline"]
           │
           v
   Final Report Output
```

## Agents

### 1. DataCollectorAgent

**Signature**: `DataCollectionSignature`
- **Inputs**: `data_sources` (str) - Data sources specification as JSON
- **Outputs**:
  - `collected_data` (str) - Collected data as JSON
  - `metadata` (str) - Collection metadata

**Responsibilities**:
- Collect data from databases, APIs, files, streams
- Validate and normalize data
- Track sources processed
- Write collected data to SharedMemoryPool

**SharedMemory Tags**: `["collected_data", "pipeline"]`, segment: `"pipeline"`

### 2. DataProcessorAgent

**Signature**: `DataProcessingSignature`
- **Inputs**: `raw_data` (str) - Raw data to process as JSON
- **Outputs**:
  - `processed_data` (str) - Processed and aggregated data
  - `statistics` (str) - Statistical summary
  - `aggregations` (str) - Data aggregations

**Responsibilities**:
- Process and aggregate raw data
- Calculate statistics (mean, median, std, etc.)
- Perform data aggregations
- Write processed data to SharedMemoryPool

**SharedMemory Tags**: `["processed_data", "pipeline"]`, segment: `"pipeline"`

### 3. ChartGeneratorAgent

**Signature**: `ChartGenerationSignature`
- **Inputs**: `processed_data` (str) - Processed data for visualization
- **Outputs**: `charts` (str) - Generated charts specification as JSON

**Responsibilities**:
- Create visualizations (line, bar, pie, scatter charts)
- Generate chart specifications
- Write charts to SharedMemoryPool

**SharedMemory Tags**: `["charts", "pipeline"]`, segment: `"pipeline"`

### 4. ReportCompilerAgent

**Signature**: `ReportCompilationSignature`
- **Inputs**: `report_data` (str) - Complete report data as JSON
- **Outputs**:
  - `report` (str) - Compiled report content
  - `report_format` (str) - Report format (pdf, html, excel)

**Responsibilities**:
- Compile final report from all components
- Format output (PDF, HTML, Excel)
- Write final report to SharedMemoryPool

**SharedMemory Tags**: `["final_report", "pipeline"]`, segment: `"pipeline"`

## Quick Start

### 1. Basic Usage

```python
from workflow import data_reporting_workflow, DataReportingConfig

config = DataReportingConfig(llm_provider="mock")

report_spec = {
    "title": "Monthly Sales Report",
    "sources": {
        "database": "SELECT * FROM sales WHERE month = 'January'"
    }
}

result = data_reporting_workflow(report_spec, config)
print(f"Report generated: {result['final_report']['format']}")
```

### 2. Custom Configuration

```python
config = DataReportingConfig(
    llm_provider="openai",
    model="gpt-4",
    output_format="excel",  # "pdf", "html", "excel"
    chart_types=["line", "bar", "pie", "scatter"],
    schedule="daily",
    delivery_emails=["admin@example.com"]
)
```

### 3. Batch Report Generation

```python
from workflow import batch_reporting_workflow

report_specs = [
    {"title": "Sales Report", "sources": {"database": "sales"}},
    {"title": "Revenue Report", "sources": {"database": "revenue"}},
    {"title": "User Analytics", "sources": {"api": "https://api.example.com/users"}}
]

results = batch_reporting_workflow(report_specs, config)
print(f"Generated {len(results)} reports")
```

## Configuration

### DataReportingConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "mock" | LLM provider (mock, openai, anthropic) |
| `model` | str | "gpt-3.5-turbo" | Model name |
| `output_format` | str | "pdf" | Report format: pdf, html, excel |
| `chart_types` | List[str] | ["line", "bar", "pie"] | Supported chart types |
| `schedule` | str | None | Schedule: daily, weekly, monthly |
| `delivery_emails` | List[str] | [] | Email recipients for delivery |

## Use Cases

### 1. Automated Daily Reports

Generate daily performance reports automatically.

### 2. Executive Dashboards

Create executive summaries with key metrics and visualizations.

### 3. Financial Reporting

Compile financial reports with charts and analysis.

### 4. Performance Metrics

Track KPIs and performance metrics over time.

### 5. Analytics Reports

Generate analytics reports from multiple data sources.

## Testing

```bash
# Run all tests
pytest tests/unit/examples/test_data_reporting.py -v

# Run specific test class
pytest tests/unit/examples/test_data_reporting.py::TestDataReportingAgents -v
```

**Test Coverage**: 17 tests, 100% passing

## Related Examples

- **document-analysis** - Multi-agent document processing
- **simple-qa** - Basic question answering
- **rag-research** - Research with VectorMemory

## Implementation Notes

- **Phase**: 5E.2 (Enterprise Workflow Examples)
- **Created**: 2025-10-02
- **Tests**: 17/17 passing
- **TDD**: Tests written first, implementation second

## Author

Kaizen Framework Team
