# Performance Report for Run bf095b99-b3fc-4b26-aee6-175c8e5e20f3

**Workflow:** fastapi_test_workflow
**Started:** 2025-05-31 05:49:51.891243+00:00
**Status:** running
**Total Tasks:** 3

## Summary Statistics
- **Total Execution Time:** 2.50 seconds
- **Average CPU Usage:** 32.5%
- **Peak Memory Usage:** 120.0 MB

## Task Performance Details
| Node ID | Type | Status | Duration (s) | CPU % | Memory (MB) |
|---------|------|--------|-------------|-------|-------------|
| api_node_0 | APITestNode | TaskStatus.COMPLETED | 1.00 | 25.0 | 80.0 |
| api_node_1 | APITestNode | TaskStatus.COMPLETED | 1.50 | 40.0 | 120.0 |
| api_node_2 | APITestNode | TaskStatus.FAILED | 2.00 | 55.0 | 160.0 |

## Performance Insights

### Bottlenecks
- **Slowest Node:** api_node_1 (1.50s)
- **Highest Memory:** api_node_1 (120.0 MB)