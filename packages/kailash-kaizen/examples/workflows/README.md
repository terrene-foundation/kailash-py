# Kaizen Production Workflow Examples

This directory contains production-ready workflow examples for Kaizen v0.2.0, demonstrating real-world autonomous agentic capabilities.

## 📁 Production Workflows

### 01_data_processing_pipeline.py
**Automated Data Processing Pipeline**

Process CSV/text files, transform data, generate analytics reports. Handles errors gracefully, validates data, and produces structured results.

**Use Cases**:
- Batch file processing
- Data transformation pipelines
- Automated report generation
- ETL operations

**Run**:
```bash
INPUT_DIR=/path/to/data OUTPUT_DIR=/path/to/results python examples/workflows/01_data_processing_pipeline.py
```

---

### 02_api_integration_workflow.py
**Multi-API Data Aggregation**

Fetch data from multiple REST APIs concurrently, handle retries with exponential backoff, aggregate results, and generate consolidated reports.

**Use Cases**:
- API data aggregation
- Multi-source data collection
- Service health monitoring
- Data synchronization

**Features**:
- Concurrent API fetching
- Automatic retry with exponential backoff
- Error recovery and reporting
- Configurable timeout and retry policies

**Run**:
```bash
API_ENDPOINTS="https://api1.com,https://api2.com" python examples/workflows/02_api_integration_workflow.py
```

---

### 03_monitoring_alerting_workflow.py
**System Health Monitoring & Alerting**

Monitor endpoints and file systems, detect failures, track consecutive errors, and generate alerts with severity classification.

**Use Cases**:
- Service health checks
- Endpoint monitoring
- File system validation
- Automated alerting
- SLA compliance monitoring

**Features**:
- Concurrent health checks
- Failure threshold detection
- Alert severity classification
- Continuous monitoring mode
- Detailed health reports

**Run**:
```bash
MONITOR_ENDPOINTS="https://service1.com,https://service2.com" python examples/workflows/03_monitoring_alerting_workflow.py
```

---

### 04_document_processing_workflow.py
**Document Analysis & Entity Extraction**

Extract text from documents, analyze content structure, extract entities (emails, URLs, dates), and generate comprehensive analysis reports.

**Use Cases**:
- Document analysis automation
- Entity extraction
- Content summarization
- Batch document processing
- Compliance document review

**Features**:
- Named entity recognition (emails, URLs, phones, dates)
- Content statistics and analysis
- Extractive summarization
- Batch processing support
- Structured reporting

**Run**:
```bash
INPUT_DIR=/path/to/docs OUTPUT_DIR=/path/to/analysis python examples/workflows/04_document_processing_workflow.py
```

---

## 🚀 Quick Start

### 1. Installation

```bash
pip install kailash-kaizen==0.2.0 python-dotenv
```

### 2. Configuration

Create `.env` file with your API key:
```bash
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

### 3. Run Production Workflows

```bash
# Data processing
INPUT_DIR=/tmp/data OUTPUT_DIR=/tmp/results python examples/workflows/01_data_processing_pipeline.py

# API aggregation
API_ENDPOINTS="https://api1.com,https://api2.com" python examples/workflows/02_api_integration_workflow.py

# System monitoring
MONITOR_ENDPOINTS="https://service1.com,https://service2.com" python examples/workflows/03_monitoring_alerting_workflow.py

# Document analysis
INPUT_DIR=/tmp/docs OUTPUT_DIR=/tmp/analysis python examples/workflows/04_document_processing_workflow.py
```

---

## 🏭 Production Features

### Autonomous Tool Calling (v0.2.0)
All workflows leverage Kaizen's autonomous tool calling with 12 builtin tools:
- **File Operations**: read_file, write_file, delete_file, list_directory, file_exists
- **HTTP Requests**: http_get, http_post, http_put, http_delete
- **System**: bash_command
- **Web**: fetch_url, extract_links

### Error Handling & Resilience
- Automatic retry with exponential backoff
- Graceful error recovery
- Detailed error reporting
- Failure tracking and alerting

### Environment Configuration
All workflows support environment-based configuration:
- No hardcoded paths or URLs
- Configurable timeouts and thresholds
- Flexible input/output directories
- Production-ready defaults

---

## 📊 Architecture Patterns

### Batch Processing Pattern
```python
async def batch_process(self, input_dir: str, output_dir: str) -> Dict:
    results = {"processed": [], "failed": [], "stats": {}}

    list_result = await self.execute_tool("list_directory", {"path": input_dir})

    for file_info in files:
        try:
            # Process file with error handling
            result = await self.process_file(file_info)
            results["processed"].append(result)
        except Exception as e:
            results["failed"].append({"file": file_info, "error": str(e)})

    return results
```

### Concurrent API Pattern
```python
async def aggregate_endpoints(self, endpoints: List[str]) -> Dict:
    fetch_tasks = [self.fetch_with_retry(ep) for ep in endpoints]
    responses = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    return self._process_responses(responses)
```

### Monitoring Pattern
```python
async def run_health_checks(self, endpoints: List[str]) -> Dict:
    results = {"overall_health": True, "alerts": []}

    checks = await asyncio.gather(*[self.check_endpoint(ep) for ep in endpoints])

    for check in checks:
        if not check["healthy"]:
            results["overall_health"] = False
            if self.failure_counts[endpoint] >= self.alert_threshold:
                results["alerts"].append(self._create_alert(check))

    return results
```

---

## 🔧 Configuration Options

### Environment Variables

All workflows support these environment variables:

```bash
# API Configuration
OPENAI_API_KEY=sk-your-key-here           # Required

# Data Processing Pipeline
INPUT_DIR=/path/to/input                   # Input directory
OUTPUT_DIR=/path/to/output                 # Output directory

# API Integration
API_ENDPOINTS=https://api1.com,https://api2.com  # Comma-separated URLs
RETRY_MAX=3                                # Max retry attempts
RETRY_DELAY=1.0                            # Initial retry delay (seconds)
REQUEST_TIMEOUT=30                         # Request timeout (seconds)

# Monitoring & Alerting
MONITOR_ENDPOINTS=https://service1.com,https://service2.com  # Endpoints to monitor
MONITOR_OUTPUT_DIR=/tmp/monitoring_reports  # Report output directory
ALERT_THRESHOLD=2                          # Consecutive failures before alert
CHECK_INTERVAL=60                          # Monitoring interval (seconds)

# Document Processing
MAX_DOC_SIZE=1000000                       # Max document size (bytes)
CHUNK_SIZE=4000                            # Processing chunk size
```

### Command-Line Overrides

Override environment variables at runtime:

```bash
INPUT_DIR=/custom/path OUTPUT_DIR=/custom/output python examples/workflows/01_data_processing_pipeline.py
```

---

## 📊 Production Deployment

### Docker Deployment

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV OPENAI_API_KEY=your-key-here
ENV INPUT_DIR=/app/data
ENV OUTPUT_DIR=/app/results

CMD ["python", "examples/workflows/01_data_processing_pipeline.py"]
```

### Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: data-processing-pipeline
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: processor
            image: your-registry/kaizen-pipeline:latest
            env:
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: kaizen-secrets
                  key: openai-api-key
            - name: INPUT_DIR
              value: "/data/input"
            - name: OUTPUT_DIR
              value: "/data/output"
```

---

## 📖 Additional Resources

### Documentation
- **Complete API Reference**: `docs/reference/api-reference.md`
- **Architecture Guide**: `docs/architecture/`
- **Testing Strategies**: `docs/development/testing.md`

### Advanced Examples
- **Multi-Agent Coordination**: `examples/2-multi-agent/`
- **Enterprise Workflows**: `examples/3-enterprise-workflows/`
- **RAG Patterns**: `examples/4-advanced-rag/`

### Support
- **GitHub Issues**: https://github.com/terrene-foundation/kailash-py/issues
- **Documentation**: Full docs at `docs/`

---

**Version**: 0.2.0
**Last Updated**: 2025-10-21
**License**: Production-ready workflows for Kaizen v0.2.0
