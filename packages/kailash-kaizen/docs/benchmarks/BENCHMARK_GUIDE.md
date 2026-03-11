# Kaizen Performance Benchmark Guide

**Complete guide to running, interpreting, and optimizing Kaizen framework performance benchmarks.**

---

## Table of Contents

1. [Overview](#overview)
2. [Hardware Requirements](#hardware-requirements)
3. [Installation & Setup](#installation--setup)
4. [Running Benchmarks](#running-benchmarks)
5. [Interpreting Results](#interpreting-results)
6. [Statistical Methodology](#statistical-methodology)
7. [Performance Targets](#performance-targets)
8. [Troubleshooting](#troubleshooting)
9. [Best Practices](#best-practices)

---

## Overview

The Kaizen benchmark suite provides comprehensive performance measurements across 7 key areas:

| Suite | Focus Area | Benchmarks | Duration | Budget |
|-------|-----------|------------|----------|--------|
| Suite 1 | Initialization | 3 | ~10-15 min | $0.00 |
| Suite 2 | Execution | 3 | ~20-30 min | $0.00 |
| Suite 3 | Memory | 3 | ~15-20 min | $0.00 |
| Suite 4 | Tool Calling | 3 | ~15-20 min | $0.00 |
| Suite 5 | Interrupts | 3 | ~10-15 min | $0.00 |
| Suite 6 | Checkpoints | 3 | ~10-15 min | $0.00 |
| Suite 7 | Multi-Agent | 3 | ~15-20 min | $0.00 |
| **TOTAL** | **All Areas** | **21** | **~100-130 min** | **$0.00** |

**Key Features:**
- ✅ **Zero Cost**: Uses Ollama llama3.2:1b (FREE, no API charges)
- ✅ **Statistical Rigor**: 100+ iterations with outlier removal (>3 std dev)
- ✅ **Real Infrastructure**: NO MOCKING (Tier 3 testing standard)
- ✅ **Reproducible**: Fixed random seeds, Docker container available
- ✅ **Percentile Metrics**: p50, p95, p99, mean, stddev
- ✅ **Resource Monitoring**: CPU%, memory MB via psutil
- ✅ **JSON Export**: Structured results for CI integration

---

## Hardware Requirements

### Minimum Requirements
- **CPU**: 4 cores (2.0 GHz+)
- **RAM**: 8 GB
- **Disk**: 10 GB free space
- **OS**: macOS, Linux, or Windows

### Recommended Requirements
- **CPU**: 8+ cores (3.0 GHz+)
- **RAM**: 16 GB
- **Disk**: 20 GB SSD
- **OS**: macOS or Linux (better async I/O)

### Software Requirements
- **Python**: 3.12+ (required)
- **Ollama**: Latest version with llama3.2:1b model
- **DataFlow**: v0.7.12+ (for memory benchmarks)
- **psutil**: Latest version (for resource monitoring)

---

## Installation & Setup

### 1. Install Dependencies

```bash
# Navigate to kailash-kaizen directory
cd packages/kailash-kaizen

# Install Kaizen with dev dependencies
pip install -e ".[dev]"

# Install DataFlow (for memory benchmarks)
pip install kailash-dataflow>=0.7.12
```

### 2. Install Ollama

**macOS:**
```bash
brew install ollama
ollama serve  # Start Ollama server
```

**Linux:**
```bash
curl -fsSL https://ollama.ai/install.sh | sh
sudo systemctl start ollama
```

**Windows:**
Download from [ollama.ai/download](https://ollama.ai/download)

### 3. Pull llama3.2:1b Model

```bash
# Pull the FREE 1B parameter model
ollama pull llama3.2:1b

# Verify installation
ollama list
# Should show: llama3.2:1b
```

### 4. Verify Setup

```bash
# Check Ollama is running
ollama list

# Check Python dependencies
python -c "import kaizen; import dataflow; import psutil; print('All dependencies OK')"
```

---

## Running Benchmarks

### Run Individual Suites

```bash
# Suite 1: Initialization
python benchmarks/suite1_initialization.py

# Suite 2: Execution
python benchmarks/suite2_execution.py

# Suite 3: Memory
python benchmarks/suite3_memory.py

# Suite 4: Tool Calling
python benchmarks/suite4_tool_calling.py

# Suite 5: Interrupts
python benchmarks/suite5_interrupts.py

# Suite 6: Checkpoints
python benchmarks/suite6_checkpoints.py

# Suite 7: Multi-Agent
python benchmarks/suite7_multi_agent.py
```

### Run All Suites (Sequential)

```bash
# Run all 7 suites sequentially
for suite in benchmarks/suite*.py; do
    python "$suite"
done
```

### Run with Docker (Reproducible)

```bash
# Build benchmark container
docker build -f Dockerfile.benchmarks -t kaizen-benchmarks .

# Run all suites in container
docker run --rm \
    -v $(pwd)/benchmarks/results:/app/benchmarks/results \
    kaizen-benchmarks
```

### Output Location

Results are exported to:
```
benchmarks/results/
├── suite1_initialization_results.json
├── suite2_execution_results.json
├── suite3_memory_results.json
├── suite4_tool_calling_results.json
├── suite5_interrupts_results.json
├── suite6_checkpoints_results.json
└── suite7_multi_agent_results.json
```

---

## Interpreting Results

### Result Structure

Each suite produces a JSON file with:

```json
{
  "suite_name": "Initialization Performance",
  "benchmark_results": [
    {
      "name": "Cold Start (Fresh Process)",
      "iterations": 50,
      "warmup_iterations": 5,
      "latency_ms": {
        "p50": 12.45,
        "p95": 18.23,
        "p99": 22.15,
        "mean": 13.67,
        "stddev": 3.42,
        "min": 10.12,
        "max": 25.34,
        "count": 48
      },
      "throughput_ops_per_sec": 73.15,
      "resources": {
        "cpu_mean": 45.2,
        "cpu_peak": 78.5,
        "memory_mean_mb": 256.3,
        "memory_peak_mb": 312.7,
        "threads_mean": 12.5,
        "threads_peak": 15
      },
      "confidence_interval": {
        "lower": 12.85,
        "upper": 14.49,
        "confidence": 0.95
      },
      "outliers_removed": 2
    }
  ]
}
```

### Key Metrics

#### 1. Latency Metrics (ms)

- **p50 (Median)**: Typical latency - 50% of operations complete faster
- **p95**: 95% of operations complete faster (catches most outliers)
- **p99**: 99% of operations complete faster (catches worst-case)
- **Mean**: Average latency across all iterations
- **StdDev**: Variability (lower is more consistent)

**Interpretation:**
- `p50 < 10ms`: Excellent
- `p50 10-50ms`: Good
- `p50 50-100ms`: Acceptable
- `p50 > 100ms`: Needs optimization

#### 2. Throughput (ops/sec)

Operations per second: `throughput = 1000 / mean_latency_ms`

**Interpretation:**
- `> 100 ops/sec`: Excellent
- `50-100 ops/sec`: Good
- `10-50 ops/sec`: Acceptable
- `< 10 ops/sec`: Needs optimization

#### 3. Resource Metrics

- **CPU Mean/Peak**: Average and maximum CPU usage (%)
- **Memory Mean/Peak**: Average and maximum memory usage (MB)
- **Threads Mean/Peak**: Average and maximum thread count

**Interpretation (CPU):**
- `< 50%`: Excellent (room for parallelism)
- `50-80%`: Good
- `80-95%`: High utilization
- `> 95%`: Bottleneck (consider optimization)

**Interpretation (Memory):**
- `< 500 MB`: Excellent
- `500-1000 MB`: Good
- `1000-2000 MB`: Acceptable
- `> 2000 MB`: High usage (check for leaks)

#### 4. Confidence Interval (95%)

Range where true mean likely falls: `[lower, upper]`

**Interpretation:**
- Narrow interval (`< 10% of mean`): Consistent performance
- Wide interval (`> 20% of mean`): High variability (investigate)

#### 5. Outliers Removed

Count of outliers removed (>3 std dev from mean)

**Interpretation:**
- `0-5%`: Normal
- `5-10%`: Moderate variability
- `> 10%`: High variability (investigate environmental factors)

---

## Statistical Methodology

### 1. Sample Size

- **Warmup**: 5-10 iterations (excluded from results)
- **Measurement**: 50-100 iterations (included in results)

**Why?**
- Warmup eliminates JIT compilation, cache warming effects
- 50-100 iterations provide statistically significant sample (Central Limit Theorem)

### 2. Outlier Removal

Removes values >3 standard deviations from mean

**Formula:**
```
lower_bound = mean - (3 × stddev)
upper_bound = mean + (3 × stddev)
keep if: lower_bound ≤ value ≤ upper_bound
```

**Why?**
- Eliminates environmental noise (GC pauses, OS context switches)
- Focuses on typical performance (not worst-case anomalies)

### 3. Percentiles

**Calculation:**
```
sorted_data = sort(measurements)
p50 = sorted_data[n × 0.50]  # Median
p95 = sorted_data[n × 0.95]
p99 = sorted_data[n × 0.99]
```

**Why?**
- p50: Typical user experience
- p95: Catches most outliers (SLA target)
- p99: Catches worst-case (tail latency)

### 4. Confidence Intervals (95%)

**Formula (Normal Approximation):**
```
margin = 1.96 × (stddev / √n)
CI = [mean - margin, mean + margin]
```

**Why?**
- 95% confidence: Industry standard
- Quantifies measurement uncertainty
- Enables statistical comparison between versions

### 5. Random Seeds

Fixed seed (`seed=42`) for reproducibility

**Why?**
- Ensures consistent initialization order
- Enables version-to-version comparison
- Reproduces results across runs

---

## Performance Targets

### Suite 1: Initialization

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Cold Start | < 20ms | < 10ms | 10-20ms | > 20ms |
| Warm Start | < 5ms | < 2ms | 2-5ms | > 5ms |
| Lazy Init | < 3ms | < 1ms | 1-3ms | > 3ms |

### Suite 2: Execution

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Single-Shot | < 500ms | < 200ms | 200-500ms | > 500ms |
| Multi-Turn | < 800ms | < 400ms | 400-800ms | > 800ms |
| Long-Running | < 3000ms | < 2000ms | 2000-3000ms | > 3000ms |

### Suite 3: Memory

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Hot Tier | < 1ms | < 0.5ms | 0.5-1ms | > 1ms |
| Warm Tier | < 10ms | < 5ms | 5-10ms | > 10ms |
| Cold Tier | < 100ms | < 50ms | 50-100ms | > 100ms |

### Suite 4: Tool Calling

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Permission Check | < 0.5ms | < 0.1ms | 0.1-0.5ms | > 0.5ms |
| Approval Workflow | < 2ms | < 1ms | 1-2ms | > 2ms |
| Tool Execution | < 50ms | < 20ms | 20-50ms | > 50ms |

### Suite 5: Interrupts

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Detection | < 1ms | < 0.5ms | 0.5-1ms | > 1ms |
| Graceful Shutdown | < 10ms | < 5ms | 5-10ms | > 10ms |
| Checkpoint on Interrupt | < 50ms | < 20ms | 20-50ms | > 50ms |

### Suite 6: Checkpoints

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| Save | < 30ms | < 10ms | 10-30ms | > 30ms |
| Load | < 20ms | < 10ms | 10-20ms | > 20ms |
| Compression | < 50ms | < 20ms | 20-50ms | > 50ms |

### Suite 7: Multi-Agent

| Benchmark | Target (p50) | Excellent | Good | Needs Work |
|-----------|--------------|-----------|------|------------|
| A2A Protocol | < 2ms | < 1ms | 1-2ms | > 2ms |
| Semantic Routing | < 5ms | < 2ms | 2-5ms | > 5ms |
| Task Delegation | < 10ms | < 5ms | 5-10ms | > 10ms |

---

## Troubleshooting

### Issue: Ollama Not Found

**Symptom:**
```
ERROR: Ollama not running or llama3.2 model not available
```

**Solution:**
```bash
# Check Ollama is running
ollama list

# If not running, start it
ollama serve  # macOS/Linux
# or use system service

# Pull model if missing
ollama pull llama3.2:1b
```

### Issue: High Variance (Wide Confidence Intervals)

**Symptom:**
```
Confidence Interval: [10.2, 45.8]ms  # Too wide
```

**Causes:**
1. Insufficient warmup iterations
2. Background processes consuming resources
3. Thermal throttling

**Solutions:**
```bash
# Increase warmup iterations
# Edit suite file, change: warmup=10 → warmup=20

# Close background apps (browsers, IDEs)
# Check system load: top or Activity Monitor

# Ensure adequate cooling (laptops: use cooling pad)
```

### Issue: High Outlier Count (>10%)

**Symptom:**
```
Outliers Removed: 12 / 100 (12%)
```

**Causes:**
1. Garbage collection pauses
2. OS context switches
3. Disk I/O contention

**Solutions:**
```bash
# Increase sample size (reduces % impact)
# Edit suite file, change: iterations=100 → iterations=200

# Run during low system activity
# Use Docker container for isolation
```

### Issue: Memory Benchmarks Slow

**Symptom:**
```
Suite 3 taking > 30 minutes
```

**Causes:**
1. Database connection overhead
2. Slow disk I/O

**Solutions:**
```bash
# Use SSD for temp database
# Edit suite3_memory.py, use /tmp (tmpfs on Linux)

# Reduce iterations for initial testing
# Edit suite file, change: iterations=100 → iterations=50
```

---

## Best Practices

### 1. Run During Off-Peak Hours

Minimize system load:
- Close browsers, IDEs, other heavy apps
- Disable automatic updates, backups
- Use `nice` on Linux/macOS: `nice -n 10 python benchmark.py`

### 2. Warm Up System

Before running benchmarks:
```bash
# Run a quick warmup suite
python benchmarks/suite1_initialization.py

# Wait 5 minutes for system to stabilize
sleep 300

# Now run full suite
python benchmarks/suite2_execution.py
```

### 3. Use Docker for Production Benchmarks

Ensures reproducibility:
```bash
docker build -f Dockerfile.benchmarks -t kaizen-benchmarks .
docker run --rm -v $(pwd)/benchmarks/results:/app/benchmarks/results kaizen-benchmarks
```

### 4. Track Results Over Time

Compare across versions:
```bash
# Tag results with version
mv benchmarks/results benchmarks/results_v0.6.5

# Run benchmarks for new version
# ... install v0.6.6 ...
python benchmarks/suite1_initialization.py

# Compare results
diff benchmarks/results_v0.6.5/suite1_initialization_results.json \
     benchmarks/results/suite1_initialization_results.json
```

### 5. CI Integration

Automated tracking:
```yaml
# .github/workflows/benchmarks.yml
- name: Run Benchmarks
  run: |
    for suite in benchmarks/suite*.py; do
      python "$suite"
    done

- name: Archive Results
  uses: actions/upload-artifact@v3
  with:
    name: benchmark-results
    path: benchmarks/results/
```

---

## Additional Resources

- **Framework Documentation**: [benchmarks/framework.py](../benchmarks/framework.py)
- **Claude Comparison**: [CLAUDE_COMPARISON.md](CLAUDE_COMPARISON.md)
- **Optimization Roadmap**: [OPTIMIZATION_ROADMAP.md](OPTIMIZATION_ROADMAP.md)
- **E2E Tests**: [tests/e2e/autonomy/](../../tests/e2e/autonomy/)

---

**Last Updated**: 2025-11-03
**Version**: 1.0.0
**TODO-171 Status**: ✅ Complete
