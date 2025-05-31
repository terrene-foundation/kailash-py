# 🚀 Workflow Performance Report

**Run ID:** 634d8aaa-85b1-4818-ba3d-8c0b019a9c6e
**Workflow:** Dashboard Demo Workflow
**Started:** 2025-05-31 02:42:41.270246+00:00
**Status:** completed

## 📊 Executive Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 3 |
| Completed Tasks | 3 |
| Failed Tasks | 0 |
| Total Duration | 0.00s |
| Average CPU Usage | 0.0% |
| Peak Memory Usage | 134MB |
| Throughput | 209366.26 tasks/min |
| Efficiency Score | 100/100 |

## 💡 Performance Insights

### 🔍 Execution Time Bottleneck (MEDIUM)

**Description:** Task data_reader (CSVReader) is taking 0.00s, significantly longer than average.

**Recommendation:** Consider optimizing this task or running it in parallel with other operations.

### 🔍 High Memory Usage (MEDIUM)

**Description:** Task data_writer is using 134.4MB of memory.

**Recommendation:** Consider processing data in chunks or optimizing data structures to reduce memory footprint.

## 📋 Task Performance by Node Type

| Node Type | Count | Completed | Avg Duration | Success Rate |
|-----------|-------|-----------|--------------|--------------|
| CSVReader | 1 | 1 | 0.00s | 100.0% |
| Filter | 1 | 1 | 0.00s | 100.0% |
| CSVWriter | 1 | 1 | 0.00s | 100.0% |

## 🔍 Performance Bottlenecks

- **data_writer** (CSVWriter): memory = 134.41 (threshold: 134.39) - medium severity
- **data_reader** (CSVReader): duration = 0.00 (threshold: 0.00) - medium severity

---
*Generated on 2025-05-31 10:42:49 by Kailash Performance Reporter*
