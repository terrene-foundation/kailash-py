# ADR-0019: Real-time Dashboard Architecture

## Status

Accepted

Date: 2025-05-31

## Context

The Kailash Python SDK needed real-time monitoring capabilities to observe workflow execution as it happens. Users require immediate feedback on task progress, resource utilization, and performance metrics during long-running workflows. Traditional static reporting after completion was insufficient for operational monitoring and debugging.

Key requirements included:
- Live metrics collection during workflow execution
- Real-time dashboard updates without page refreshes
- API endpoints for programmatic access to metrics
- WebSocket streaming for continuous data feeds
- Interactive visualizations with historical data
- Integration with existing task tracking infrastructure

## Decision

Implement a comprehensive real-time dashboard architecture consisting of:

1. **RealTimeDashboard** - Core monitoring component with background metrics collection
2. **DashboardConfig** - Configuration for update intervals and display options
3. **LiveMetrics** - Data model for current performance metrics
4. **WorkflowPerformanceReporter** - Comprehensive report generation
5. **SimpleDashboardAPI** - REST API endpoints for metrics access
6. **DashboardAPIServer** - FastAPI-based WebSocket streaming server

The architecture uses threading for background metrics collection, callback systems for event handling, and HTML/JavaScript generation for interactive dashboards.

## Rationale

This decision was made to provide comprehensive real-time monitoring without disrupting existing workflow execution patterns. Key factors:

**Threading Approach**: Background collection ensures minimal impact on workflow performance
**Callback System**: Enables responsive event handling and custom integrations
**Multi-format Output**: Supports both programmatic (JSON/API) and visual (HTML) consumption
**WebSocket Streaming**: Provides low-latency updates for live dashboards
**Integration Design**: Builds on existing TaskManager infrastructure

Alternatives considered:
- **Polling-only approach**: Rejected due to higher latency and resource overhead
- **Database-heavy solution**: Rejected to maintain lightweight architecture
- **External monitoring service**: Rejected to keep dependencies minimal

## Consequences

### Positive
- Real-time visibility into workflow execution progress
- Interactive dashboards for operational monitoring
- API access enables custom monitoring integrations
- Background collection minimizes performance impact
- Scalable architecture supports multiple concurrent workflows
- Enhanced debugging capabilities with live metrics

### Negative
- Additional memory overhead for metrics storage
- Threading complexity requires careful resource management
- Optional FastAPI dependency for full WebSocket functionality
- HTML dashboard generation adds file I/O operations

### Neutral
- Requires psutil dependency for system metrics collection
- Configuration complexity increased with dashboard options
- Additional testing surface area for real-time components

## Implementation Notes

### Core Components

**RealTimeDashboard Class**:
- Starts background monitoring thread
- Collects metrics at configurable intervals
- Supports callback registration for custom event handling
- Generates HTML dashboards with Chart.js integration

**Dashboard Configuration**:
```python
config = DashboardConfig(
    update_interval=1.0,  # seconds
    max_history_points=100,
    auto_refresh=True,
    show_completed=True,
    theme="light"
)
```

**API Endpoints**:
- `GET /api/v1/runs` - List workflow runs
- `GET /api/v1/metrics/current` - Current metrics snapshot
- `GET /api/v1/metrics/history` - Historical metrics
- `WebSocket /api/v1/metrics/stream` - Live streaming

### Integration Patterns

**Basic Usage**:
```python
dashboard = RealTimeDashboard(task_manager, config)
dashboard.start_monitoring()
# Execute workflow
dashboard.stop_monitoring()
```

**API Streaming**:
```python
api = SimpleDashboardAPI(task_manager)
api.start_monitoring()
metrics = api.get_current_metrics()
```

## Alternatives Considered

1. **External Monitoring Systems**: Prometheus/Grafana integration was considered but rejected to maintain zero external dependencies

2. **Database Storage**: Persistent metrics storage was considered but rejected to keep the architecture lightweight and avoid database dependencies

3. **Event-Driven Architecture**: Pure event system was considered but threading approach provided better performance isolation

4. **Client-Side Polling**: JavaScript-only updates were considered but WebSocket streaming provides better real-time experience

## Related ADRs

- [ADR-0006: Task Tracking Architecture](0006-task-tracking-architecture.md) - Foundation for metrics collection
- [ADR-0018: Performance Metrics Architecture](0018-performance-metrics-architecture.md) - Underlying metrics framework

## References

- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [Chart.js Real-time Updates](https://www.chartjs.org/docs/latest/developers/updates.html)
- [Python Threading Best Practices](https://docs.python.org/3/library/threading.html)
