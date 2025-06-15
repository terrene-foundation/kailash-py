# Performance Benchmarks

This directory contains performance benchmarks and resource-intensive tests that were moved from the main test suite to avoid impacting CI/CD pipeline execution times.

## Purpose

These tests are designed for:
- **Performance regression detection** - Identifying when changes impact SDK performance
- **Resource utilization analysis** - Understanding memory, CPU, and I/O usage patterns
- **Load testing** - Validating SDK behavior under high-volume scenarios
- **Benchmark comparisons** - Measuring performance across SDK versions

## Contents

### Cycle Performance Tests
- `test_cycle_performance.py` - Large-scale iteration tests (1000+ iterations)
  - Memory usage tracking across iterations
  - State accumulation performance analysis
  - Parallel cycle execution benchmarks
  - Cycle overhead measurements

### Monitoring Benchmarks
- `test_performance_benchmark.py` - PerformanceBenchmarkNode functionality
  - Latency measurement and tracking
  - Throughput monitoring
  - Resource utilization analysis
  - SLA compliance validation
  - Anomaly detection testing

### Integration Performance
- `test_performance_tracking_integration.py` - End-to-end performance tracking
  - Integration with monitoring systems
  - Performance metrics collection
  - Real-time tracking validation

### LLM Agent Performance
- `qa_llm_agent_test.py` - LLM agent performance testing
  - Large-scale LLM operations
  - Resource-intensive AI workflows
  - Quality assurance benchmarks

## Usage

These tests are not part of the regular CI/CD pipeline due to their resource requirements and execution time. They should be run:

### Manual Execution
```bash
# Run all performance benchmarks
python -m pytest examples/performance_benchmarks/ -v

# Run specific benchmark
python -m pytest examples/performance_benchmarks/test_cycle_performance.py -v

# Run with performance markers
python -m pytest examples/performance_benchmarks/ -m "performance" -v
```

### Scheduled Performance Testing
```bash
# Run nightly performance regression tests
python -m pytest examples/performance_benchmarks/ --benchmark-sort=name
```

### Local Development
```bash
# Quick performance check
python -m pytest examples/performance_benchmarks/ -k "quick" -v
```

## Requirements

Some benchmarks may require additional dependencies:
- `psutil` - System resource monitoring
- `numpy` - Numerical performance analysis
- `pytest-benchmark` - Performance measurement framework

## Guidelines

### Adding New Benchmarks
1. **Focus on regression detection** - Test performance-critical code paths
2. **Include baseline measurements** - Establish expected performance ranges
3. **Document resource requirements** - Memory, CPU, and time expectations
4. **Use appropriate markers** - `@pytest.mark.performance`, `@pytest.mark.slow`

### Performance Test Patterns
```python
@pytest.mark.performance
def test_large_workflow_execution():
    """Test workflow execution performance with large datasets."""
    # Setup large dataset
    # Execute workflow with timing
    # Assert performance thresholds
    pass

@pytest.mark.slow
def test_memory_usage_over_time():
    """Monitor memory usage during long-running operations."""
    # Track memory usage
    # Detect memory leaks
    # Validate cleanup
    pass
```

## Integration with CI/CD

While these tests don't run in regular CI, they can be integrated:
- **Nightly builds** - Run comprehensive performance suite
- **Release validation** - Execute before major releases
- **Performance gates** - Block releases that regress performance
- **Trend analysis** - Track performance over time

## Monitoring

Performance benchmark results should be:
- **Tracked over time** - Identify performance trends
- **Alerted on regressions** - Notify when thresholds are exceeded
- **Reported in releases** - Include performance impact in release notes
- **Documented for users** - Help users understand performance characteristics

This separation ensures the main test suite remains fast while preserving important performance validation capabilities.
