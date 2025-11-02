# Kailash LocalRuntime Load Testing Framework

A comprehensive, enterprise-grade load testing framework for the enhanced LocalRuntime capable of testing 1000+ concurrent workflows with real infrastructure. This framework follows the 3-tier testing strategy and provides detailed performance analysis, bottleneck identification, and regression detection.

## 🏗️ Architecture Overview

### Framework Components

- **LoadTestFramework**: Core testing orchestration and execution
- **ResourceMonitor**: Real-time system and database resource monitoring
- **FailureInjector**: Realistic failure scenario injection
- **WorkflowGenerator**: Dynamic workflow generation for testing
- **PerformanceMetrics**: Comprehensive metrics collection and analysis
- **Docker Infrastructure**: Production-like test environment

### Key Features

✅ **Concurrent Execution**: Test 1-10,000+ concurrent workflows
✅ **Real Infrastructure**: PostgreSQL, MySQL, Redis, MongoDB integration
✅ **Performance Metrics**: Throughput, latency, resource usage tracking
✅ **Failure Injection**: Database timeouts, connection exhaustion, resource pressure
✅ **Regression Detection**: Automated performance comparison and alerting
✅ **Endurance Testing**: 24-hour stability and memory leak detection
✅ **Enterprise Monitoring**: Prometheus + Grafana observability stack

## 🚀 Quick Start

### 1. Setup Infrastructure

```bash
# Start the performance testing environment
make setup
make start

# Verify all services are running
make status
```

### 2. Run Basic Performance Tests

```bash
# Quick validation (1-2 minutes)
make test-quick

# Baseline performance testing (5-10 minutes)
make test-baseline

# View results
make report
```

### 3. Access Monitoring Dashboards

- **Grafana**: http://localhost:3000 (admin/performance)
- **Prometheus**: http://localhost:9090
- **Performance Dashboard**: http://localhost:8081

## 📊 Test Scenarios

### Baseline Performance Testing

Tests normal load conditions with increasing concurrency:

```bash
# Test 100, 500, 1000 concurrent workflows
make test-baseline

# Custom concurrency levels
python3 performance_test_runner.py --scenario baseline --concurrency 100 500 1000 2000
```

**Expected Results:**
- **100 concurrent**: >10 workflows/sec, <1s avg latency
- **500 concurrent**: >25 workflows/sec, <2s avg latency
- **1000 concurrent**: >40 workflows/sec, <5s avg latency

### Stress Testing

Tests system behavior under extreme load conditions:

```bash
# Stress test up to 2000 concurrent workflows
make test-stress

# Custom maximum concurrency
python3 performance_test_runner.py --scenario stress --max-concurrency 3000
```

**Stress Levels:**
- **500 workflows**: Baseline stress
- **1000 workflows**: Medium stress
- **1500 workflows**: High stress
- **2000+ workflows**: Extreme stress

### Database Stress Testing

Tests database connection pool exhaustion and recovery:

```bash
# Database-focused stress testing
make test-database
```

**Database Scenarios:**
- **Light Load**: 100 concurrent, normal connection pool
- **Medium Load**: 300 concurrent, database stress enabled
- **Heavy Load**: 500 concurrent, high database utilization
- **Connection Exhaustion**: 200 concurrent, limited connection pool (50 connections)

### Endurance Testing

Long-running stability and memory leak detection:

```bash
# 1-hour endurance test
make test-endurance

# 24-hour endurance test (manual execution)
make test-endurance-24h
```

**Monitoring:**
- Memory usage growth over time
- Performance degradation detection
- Resource leak identification
- Error rate stability

### Failure Recovery Testing

Realistic failure injection and recovery validation:

```bash
# Run with failure injection enabled
python3 performance_test_runner.py --scenario baseline --concurrency 500
```

**Failure Types:**
- **Database Timeouts**: Simulated slow queries
- **Connection Exhaustion**: Pool saturation scenarios
- **Memory Pressure**: Temporary memory allocation
- **Resource Exhaustion**: CPU and I/O saturation

## 🔧 Configuration

### LoadTestConfig Options

```python
config = LoadTestConfig(
    concurrent_workflows=1000,        # Number of concurrent workflows
    total_workflows=2000,            # Total workflows to execute
    workflow_complexity="medium",     # simple, medium, complex
    enable_database_stress=True,      # Enable database stress testing
    enable_failure_injection=True,    # Enable failure injection
    failure_rate=0.05,               # 5% failure injection rate
    max_db_connections=100,          # Database connection limit
    memory_limit_mb=512,             # Memory limit for pressure testing
    test_duration=300                # Test duration in seconds
)
```

### Workflow Types

**Data Processing Workflows:**
- CSV data ingestion
- Data validation and transformation
- Analytics generation
- Database storage

**Analytics Workflows:**
- Database query execution
- Statistical analysis
- Result caching
- Performance optimization

**Transformation Workflows:**
- Data generation and filtering
- Complex data grouping
- Multi-stage processing

## 📈 Performance Metrics

### Execution Metrics
- **Throughput**: Workflows per second
- **Latency**: Average, P50, P90, P99 response times
- **Success Rate**: Percentage of successful workflows
- **Error Rate**: Failure percentage and categorization

### Resource Metrics
- **Memory**: Peak and average usage, leak detection
- **CPU**: Utilization percentages and saturation
- **Database**: Connection counts, query performance
- **Network**: I/O throughput and bandwidth usage

### Quality Metrics
- **Reliability**: Error recovery and circuit breaker effectiveness
- **Stability**: Performance consistency over time
- **Scalability**: Performance degradation under load

## 🔍 Performance Analysis

### Automated Analysis

```python
# Compare performance between runs
regression_analysis = framework.analyze_performance_regression(
    baseline_metrics, current_metrics
)

# Check for regressions
if regression_analysis['performance_regression_detected']:
    severity = regression_analysis['regression_severity']  # minor, major, critical
    recommendations = regression_analysis['recommendations']
```

### Key Performance Indicators (KPIs)

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Throughput | >50 workflows/sec | >10 workflows/sec | <5 workflows/sec |
| Avg Latency | <1 second | <5 seconds | >10 seconds |
| P99 Latency | <5 seconds | <15 seconds | >30 seconds |
| Success Rate | >99% | >95% | <90% |
| Memory Usage | <500 MB | <1 GB | >2 GB |

## 🧪 Test Execution Examples

### CI/CD Integration

```bash
# Quick CI validation
make ci-test

# Full CI pipeline
make start && make ci-test && make stop
```

### Development Workflow

```bash
# Development setup
make dev-setup

# Run development tests
make dev-test

# Monitor resources during development
make monitor-resources
```

### Release Validation

```bash
# Complete release validation
make example-release

# Exports results for archival
make export-results
```

### Regression Testing

```bash
# Run regression analysis against baseline
make test-regression BASELINE=results/baseline_20241201_120000.json

# View regression report
make report
```

## 🏗️ Infrastructure Details

### Docker Services

**Core Databases:**
- **PostgreSQL 15**: Performance-tuned, 500 max connections
- **MySQL 8.0**: Optimized InnoDB, query cache enabled
- **Redis 7**: 2GB memory, persistence disabled for performance
- **MongoDB 6**: WiredTiger compression enabled

**Monitoring Stack:**
- **Prometheus**: Metrics collection and alerting
- **Grafana**: Performance visualization and dashboards
- **Elasticsearch + Kibana**: Log aggregation and analysis
- **cAdvisor**: Container resource monitoring

**Performance Exporters:**
- **Node Exporter**: System metrics
- **Redis Exporter**: Redis-specific metrics
- **PostgreSQL Exporter**: Database performance metrics
- **MySQL Exporter**: MySQL-specific monitoring

### Resource Allocation

```yaml
services:
  perf-postgres:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## 📋 Test Organization

### Tier 1: Unit Tests (< 1 second)
```bash
pytest tests/unit/performance/ --timeout=1
```

### Tier 2: Integration Tests (< 5 seconds)
```bash
# Requires real infrastructure
pytest tests/performance/test_load_testing_scenarios.py::TestBaselinePerformanceScenarios --timeout=300
```

### Tier 3: End-to-End Tests (< 10 seconds per workflow)
```bash
# Full system testing with real infrastructure
pytest tests/performance/test_load_testing_scenarios.py::TestEnduranceScenarios --timeout=3600
```

## 🐛 Troubleshooting

### Common Issues

**Infrastructure Not Starting:**
```bash
# Check Docker daemon
docker info

# Restart services
make stop && make start

# Check service logs
make logs
```

**Performance Degradation:**
```bash
# Check resource usage
make monitor-resources

# Verify database health
make healthcheck

# Review Grafana dashboards
make dashboard
```

**High Error Rates:**
```bash
# Check database connections
docker exec kailash_perf_postgres psql -U perf_user -c "SELECT count(*) FROM pg_stat_activity;"

# Review error logs
docker logs kailash_perf_postgres

# Reduce concurrency
python3 performance_test_runner.py --scenario baseline --concurrency 50 100
```

### Performance Optimization

**Database Tuning:**
- Increase `shared_buffers` for PostgreSQL
- Optimize `innodb_buffer_pool_size` for MySQL
- Adjust connection pool sizes

**System Resources:**
- Increase available memory
- Use SSD storage for better I/O
- Ensure adequate CPU cores

**Test Configuration:**
- Start with lower concurrency
- Use simpler workflow complexity
- Disable failure injection for baseline

## 📚 Advanced Usage

### Custom Workflow Generation

```python
from load_test_framework import WorkflowGenerator

generator = WorkflowGenerator(complexity="complex")
workflow = generator.generate_data_processing_workflow()
```

### Custom Failure Injection

```python
from load_test_framework import FailureInjector

injector = FailureInjector(config)
with injector.inject_failure("database_timeout"):
    # Test code here
    pass
```

### Performance Regression Detection

```python
from load_test_framework import LoadTestFramework

framework = LoadTestFramework()
regression_analysis = framework.analyze_performance_regression(
    baseline_metrics, current_metrics
)
```

## 🔒 Security Considerations

- All test databases use non-production credentials
- Network isolation through Docker bridge networks
- Resource limits prevent system exhaustion
- Automated cleanup of test data

## 📊 Reporting and Analytics

### Automated Reports

```bash
# Generate comprehensive report
make report

# Export results for analysis
make export-results
```

### Custom Analysis

```python
# Load test results
import json
with open('results/baseline_100_20241201_120000.json') as f:
    metrics = json.load(f)

# Analyze trends
throughput_trend = [m['throughput'] for m in metrics]
latency_trend = [m['avg_latency'] for m in metrics]
```

## 🚀 Performance Targets

### Production Readiness Criteria

**Minimum Acceptable Performance:**
- ✅ 100 concurrent workflows: >5 workflows/sec, <2s avg latency
- ✅ 500 concurrent workflows: >15 workflows/sec, <5s avg latency
- ✅ 1000 concurrent workflows: >25 workflows/sec, <10s avg latency
- ✅ Error rate: <5% under normal load, <15% under stress
- ✅ Memory usage: <1GB peak under normal load
- ✅ 24-hour stability: <10% performance degradation

**Target Performance Goals:**
- 🎯 1000 concurrent workflows: >50 workflows/sec, <5s avg latency
- 🎯 2000 concurrent workflows: >80 workflows/sec, <8s avg latency
- 🎯 Error rate: <2% under normal load, <10% under stress
- 🎯 P99 latency: <15 seconds under normal load
- 🎯 Memory usage: <500MB peak under normal load

## 🤝 Contributing

### Adding New Test Scenarios

1. Create test methods in `test_load_testing_scenarios.py`
2. Follow 3-tier testing strategy (no mocking in Tiers 2-3)
3. Use real infrastructure from Docker services
4. Add appropriate pytest markers (`@pytest.mark.integration`)

### Performance Optimization

1. Profile bottlenecks using built-in monitoring
2. Optimize database queries and connection usage
3. Tune JVM/runtime parameters for better performance
4. Implement caching strategies for repeated operations

### Documentation

- Update README.md for new features
- Add inline documentation for complex algorithms
- Provide usage examples for new capabilities
- Update troubleshooting guides

---

## 📞 Support

For questions or issues with the load testing framework:

1. Check the troubleshooting section above
2. Review Grafana dashboards for performance insights
3. Examine test logs in `logs/` directory
4. Create GitHub issues with performance test results attached

**Happy Load Testing! 🚀**
