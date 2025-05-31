# 🚀 Workflow Performance Report

**Run ID:** 732fb8a1-a102-43a2-8222-6a9d52fe28f5
**Workflow:** Simple Dashboard Demo
**Started:** 2025-05-31 04:58:32.253550+00:00
**Status:** completed

## 📊 Executive Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 3 |
| Completed Tasks | 3 |
| Failed Tasks | 0 |
| Total Duration | 0.00s |
| Average CPU Usage | 0.0% |
| Peak Memory Usage | 133MB |
| Throughput | 240975.01 tasks/min |
| Efficiency Score | 100/100 |

## 💡 Performance Insights

### 🔍 Execution Time Bottleneck (MEDIUM)

**Description:** Task writer (CSVWriter) is taking 0.00s, significantly longer than average.

**Recommendation:** Consider optimizing this task or running it in parallel with other operations.

### 🔍 High Memory Usage (MEDIUM)

**Description:** Task writer is using 132.7MB of memory.

**Recommendation:** Consider processing data in chunks or optimizing data structures to reduce memory footprint.

## 📋 Task Performance by Node Type

| Node Type | Count | Completed | Avg Duration | Success Rate |
|-----------|-------|-----------|--------------|--------------|
| CSVReader | 1 | 1 | 0.00s | 100.0% |
| Filter | 1 | 1 | 0.00s | 100.0% |
| CSVWriter | 1 | 1 | 0.00s | 100.0% |

## 🔍 Performance Bottlenecks

- **writer** (CSVWriter): memory = 132.72 (threshold: 132.71) - medium severity
- **writer** (CSVWriter): duration = 0.00 (threshold: 0.00) - medium severity

---
*Generated on 2025-05-31 12:58:36 by Kailash Performance Reporter*
