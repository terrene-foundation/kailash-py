# Data Analysis Agent

## Overview

API data fetching and statistical analysis agent with checkpoint persistence. The agent fetches data from APIs, performs comprehensive statistical analysis, generates actionable insights, and saves results with automatic checkpointing for failure recovery.

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **Kailash Kaizen** installed (`pip install kailash-kaizen`)
- **Internet connection** for API calls

## Installation

```bash
# 1. Install Ollama (if not already installed)
ollama serve
ollama pull llama3.1:8b-instruct-q8_0

# 2. Install dependencies
pip install kailash-kaizen
```

## Usage

```bash
python data_analysis_agent.py <api_url>
```

Example with sample data:
```bash
python data_analysis_agent.py https://api.example.com/data
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│            DATA ANALYSIS AGENT                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────┐        ┌───────────────────┐   │
│  │ State Manager    │◄──────►│  Checkpoint       │   │
│  │ (Filesystem)     │        │  Storage          │   │
│  └──────────────────┘        └───────────────────┘   │
│          │                                             │
│          ▼                                             │
│  ┌──────────────────────────────────────────────┐    │
│  │         BaseAutonomousAgent                  │    │
│  │  1. Checkpoint before API call               │    │
│  │  2. Fetch data with http_get                 │    │
│  │  3. Statistical analysis                     │    │
│  │  4. Generate insights                        │    │
│  │  5. Checkpoint after completion              │    │
│  └──────────────────────────────────────────────┘    │
│          │                                            │
│          ▼                                            │
│  ┌──────────────────────────────────────────────┐   │
│  │         MCP Tools                            │   │
│  │  - http_get (fetch API data)                 │   │
│  │  - http_post (submit analysis)               │   │
│  └──────────────────────────────────────────────┘   │
│                                                       │
└───────────────────────────────────────────────────────┘
```

## Expected Output

```
============================================================
🤖 DATA ANALYSIS AGENT
============================================================
🌐 API URL: https://api.example.com/data
🔧 LLM: ollama/llama3.1:8b-instruct-q8_0
💾 Checkpoints: .kaizen/checkpoints/data_analysis
📊 Budget Limit: $10.00
============================================================

📊 Starting data analysis from: https://api.example.com/data

📍 Checkpoint created: checkpoint_1730650000.jsonl

🌐 Fetching data from API...
✅ Fetched 100 data points

📈 Performing statistical analysis...

📍 Results saved to checkpoint: checkpoint_1730650010.jsonl

============================================================
📊 DATA ANALYSIS REPORT
============================================================

📈 DESCRIPTIVE STATISTICS:
  • Count: 100
  • Mean: 99.87
  • Median: 99.45
  • Std Dev: 15.23
  • Min: 68.12
  • Max: 131.54
  • Q1: 89.34
  • Q3: 110.67
  • IQR: 21.33

💡 KEY INSIGHTS:
  ✓ Data shows low variability (stable distribution)
  ✓ No significant outliers detected
  ✓ Symmetric distribution (mean ≈ median)
  ✓ Narrow range of values (low spread)

============================================================

💰 Cost: $0.00 (using Ollama local inference)
📊 Checkpoints Created: 2 (before fetch, after analysis)
📦 Checkpoint Location: .kaizen/checkpoints/data_analysis
```

## Features

### 1. HTTP Tool Integration
- **http_get**: Fetch data from REST APIs
- **http_post**: Submit analysis results
- **Error handling**: Retry with exponential backoff
- **Timeout protection**: 30-second timeout per request

### 2. Statistical Analysis
- **Descriptive Statistics**: mean, median, std dev, min, max
- **Quartile Analysis**: Q1, Q3, IQR for outlier detection
- **Distribution Analysis**: Symmetry and variability checks
- **Outlier Detection**: 1.5 * IQR rule for anomalies

### 3. Checkpoint System
- **Automatic Checkpoints**: Before API call and after analysis
- **Failure Recovery**: Resume from last checkpoint
- **Metadata Tracking**: Data points, insights count
- **Retention Policy**: Keep last 10 checkpoints

### 4. Budget Tracking
- **Cost Monitoring**: Track API call costs
- **Budget Limits**: $10 maximum per analysis
- **Usage Reporting**: Display cost breakdown

## Use Cases

### 1. Business Analytics
Analyze sales data, customer metrics, revenue trends:
```bash
python data_analysis_agent.py https://api.company.com/sales
```

### 2. IoT Data Analysis
Process sensor data, environmental readings:
```bash
python data_analysis_agent.py https://api.iot-platform.com/sensors
```

### 3. Financial Data
Analyze stock prices, trading volumes:
```bash
python data_analysis_agent.py https://api.finance.com/stocks
```

### 4. Research Data
Process experimental results, survey responses:
```bash
python data_analysis_agent.py https://api.research-platform.com/experiments
```

## Troubleshooting

### Issue: "API connection refused"
**Solution**: Check API endpoint is accessible:
```bash
curl https://api.example.com/data
```

### Issue: "Checkpoint directory not writable"
**Solution**: Check permissions:
```bash
chmod 755 .kaizen/checkpoints/data_analysis
```

### Issue: "Out of memory with large datasets"
**Solution**: Process data in batches (modify `_analyze_statistics` for streaming):
```python
# Process in chunks
chunk_size = 1000
for chunk in self._chunk_data(data, chunk_size):
    partial_analysis = self._analyze_statistics(chunk)
    # Aggregate results
```

### Issue: "API rate limiting"
**Solution**: Add retry logic with exponential backoff:
```python
import time
max_retries = 3
for attempt in range(max_retries):
    try:
        data = await self.execute_tool("http_get", {"url": api_url})
        break
    except Exception as e:
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt
            print(f"⚠️  Retry in {wait_time}s...")
            time.sleep(wait_time)
```

## Production Notes

### Deployment Considerations

1. **Scalability**:
   - Use streaming for large datasets (> 1M data points)
   - Implement parallel processing for multiple APIs
   - Cache results to reduce API calls

2. **Reliability**:
   - Checkpoint before/after expensive operations
   - Implement retry logic for transient failures
   - Monitor API health with circuit breakers

3. **Security**:
   - Store API keys in `.env` file
   - Use HTTPS endpoints only
   - Validate API responses before processing

4. **Monitoring**:
   - Track API response times
   - Monitor checkpoint creation frequency
   - Alert on budget threshold (80% usage)

### Cost Analysis

**Ollama (FREE):**
- $0.00 per analysis
- Unlimited analyses
- Local inference
- Good for development and testing

**GPT-4 (Paid):**
- ~$0.05 per analysis (100 data points)
- Better insight generation
- Cloud API
- Good for production with complex analysis

## Advanced Features

### 1. Time Series Analysis
Extend with trend detection and forecasting:
```python
def _analyze_time_series(self, data: List[Dict]):
    """Detect trends and seasonality."""
    values = [d["value"] for d in data]
    timestamps = [d["timestamp"] for d in data]

    # Calculate moving average
    window = 7
    moving_avg = self._moving_average(values, window)

    # Detect trend
    trend = "increasing" if moving_avg[-1] > moving_avg[0] else "decreasing"

    return {"trend": trend, "moving_avg": moving_avg}
```

### 2. Multi-Source Analysis
Combine data from multiple APIs:
```python
async def analyze_multiple_sources(self, api_urls: List[str]):
    """Fetch and analyze data from multiple sources."""
    all_data = []

    for url in api_urls:
        data = await self._fetch_api_data(url)
        all_data.extend(data)

    return self._analyze_statistics(all_data)
```

### 3. Real-Time Streaming
Process data streams in real-time:
```python
async def analyze_stream(self, stream_url: str):
    """Analyze real-time data stream."""
    async for chunk in self._stream_data(stream_url):
        analysis = self._analyze_statistics(chunk)
        await self._publish_results(analysis)
```

## Related Examples

- [Code Review Agent](../code-review-agent/) - File tools with permission policies
- [DevOps Agent](../devops-agent/) - Bash commands with danger-level approval
- [Long-Running Research](../../memory/long-running-research/) - 3-tier memory for multi-hour tasks
