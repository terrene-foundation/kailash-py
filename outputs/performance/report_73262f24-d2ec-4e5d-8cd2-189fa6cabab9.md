# Performance Report for Run 73262f24-d2ec-4e5d-8cd2-189fa6cabab9

**Workflow:** fastapi_test_workflow
**Started:** 2025-05-31 05:47:38.178257+00:00
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