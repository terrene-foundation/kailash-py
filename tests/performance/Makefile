# Kailash Performance Testing Makefile
# Comprehensive test orchestration and infrastructure management

.PHONY: help setup start stop status clean test-quick test-full test-stress test-endurance test-regression report logs

# Default target
help:
	@echo "Kailash Performance Testing Commands"
	@echo "===================================="
	@echo ""
	@echo "Infrastructure Management:"
	@echo "  setup          - Initial setup of performance testing infrastructure"
	@echo "  start          - Start all performance testing services"
	@echo "  stop           - Stop all performance testing services"
	@echo "  status         - Show status of all services"
	@echo "  clean          - Clean up containers, volumes, and data"
	@echo "  logs           - Show logs from all services"
	@echo ""
	@echo "Testing Commands:"
	@echo "  test-quick     - Quick performance validation (1-2 minutes)"
	@echo "  test-baseline  - Baseline performance testing (5-10 minutes)"
	@echo "  test-stress    - Stress testing with high concurrency (10-20 minutes)"
	@echo "  test-database  - Database-focused stress testing (15 minutes)"
	@echo "  test-endurance - Long-running endurance test (1 hour)"
	@echo "  test-full      - Complete performance test suite (30-60 minutes)"
	@echo ""
	@echo "Analysis Commands:"
	@echo "  test-regression BASELINE=<file> - Run regression analysis"
	@echo "  report         - Generate comprehensive report from latest results"
	@echo "  dashboard      - Open Grafana dashboard in browser"
	@echo ""
	@echo "CI/CD Commands:"
	@echo "  ci-test        - CI-friendly quick tests"
	@echo "  ci-validate    - Validate infrastructure for CI"
	@echo ""

# Infrastructure Management
setup:
	@echo "Setting up performance testing infrastructure..."
	@docker-compose -f docker-compose.performance.yml pull
	@mkdir -p results dashboards config logs
	@echo "Infrastructure setup complete"

start:
	@echo "Starting performance testing services..."
	@docker-compose -f docker-compose.performance.yml up -d
	@echo "Waiting for services to be healthy..."
	@sleep 30
	@$(MAKE) status

stop:
	@echo "Stopping performance testing services..."
	@docker-compose -f docker-compose.performance.yml down

status:
	@echo "Performance Testing Infrastructure Status:"
	@echo "========================================="
	@docker-compose -f docker-compose.performance.yml ps
	@echo ""
	@echo "Service Health Checks:"
	@echo "====================="
	@python3 -c "
import docker, sys
client = docker.from_env()
services = ['kailash_perf_postgres', 'kailash_perf_redis', 'kailash_perf_mysql', 'kailash_perf_prometheus', 'kailash_perf_grafana']
all_healthy = True
for service in services:
    try:
        container = client.containers.get(service)
        status = container.status
        health = getattr(container.attrs.get('State', {}), 'Health', {}).get('Status', 'unknown')
        print(f'  {service}: {status} (health: {health})')
        if status != 'running':
            all_healthy = False
    except Exception as e:
        print(f'  {service}: ERROR - {e}')
        all_healthy = False
if all_healthy:
    print('\\n✅ All services are running and healthy')
    print('\\n🌐 Service URLs:')
    print('  - Grafana: http://localhost:3000 (admin/performance)')
    print('  - Prometheus: http://localhost:9090')
    print('  - Performance Dashboard: http://localhost:8081')
else:
    print('\\n❌ Some services are not healthy')
    sys.exit(1)
"

clean:
	@echo "Cleaning up performance testing environment..."
	@docker-compose -f docker-compose.performance.yml down -v
	@docker system prune -f
	@rm -rf results/* logs/*
	@echo "Cleanup complete"

logs:
	@docker-compose -f docker-compose.performance.yml logs -f

# Quick validation test for CI/CD
ci-validate:
	@echo "Validating infrastructure for CI..."
	@python3 performance_test_runner.py --scenario baseline --concurrency 10 --verify-only

ci-test:
	@echo "Running CI-friendly performance tests..."
	@python3 performance_test_runner.py --scenario baseline --concurrency 25 50
	@echo "CI tests completed successfully"

# Performance Testing Commands
test-quick:
	@echo "Running quick performance validation..."
	@python3 -c "
from load_test_framework import run_quick_performance_test
metrics = run_quick_performance_test()
print('Quick Test Results:')
print(f'  Throughput: {metrics.throughput:.2f} workflows/sec')
print(f'  Avg Latency: {metrics.avg_latency:.3f}s')
print(f'  Success Rate: {(metrics.successful_workflows/metrics.total_workflows)*100:.1f}%')
print(f'  Peak Memory: {metrics.peak_memory_mb:.1f} MB')
"

test-baseline:
	@echo "Running baseline performance tests..."
	@python3 performance_test_runner.py --scenario baseline --concurrency 100 500 1000
	@$(MAKE) report

test-stress:
	@echo "Running stress performance tests..."
	@python3 performance_test_runner.py --scenario stress --max-concurrency 2000
	@$(MAKE) report

test-database:
	@echo "Running database stress tests..."
	@python3 performance_test_runner.py --scenario database
	@$(MAKE) report

test-endurance:
	@echo "Running 1-hour endurance test..."
	@python3 performance_test_runner.py --scenario endurance --duration 1
	@$(MAKE) report

test-endurance-24h:
	@echo "Running 24-hour endurance test..."
	@echo "WARNING: This test will run for 24 hours!"
	@read -p "Are you sure? (y/N) " -n 1 -r && echo && \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		python3 performance_test_runner.py --scenario endurance --duration 24; \
		$(MAKE) report; \
	fi

test-full:
	@echo "Running complete performance test suite..."
	@echo "This will take 30-60 minutes to complete"
	@python3 performance_test_runner.py --scenario full
	@$(MAKE) report

# Regression testing (requires baseline file)
test-regression:
	@echo "Running regression analysis..."
ifndef BASELINE
	@echo "ERROR: BASELINE parameter required"
	@echo "Usage: make test-regression BASELINE=results/baseline_20241201_120000.json"
	@exit 1
endif
	@python3 performance_test_runner.py --scenario regression --baseline $(BASELINE)
	@$(MAKE) report

# Analysis and Reporting
report:
	@echo "Generating performance analysis report..."
	@python3 -c "
import json, os, glob
from pathlib import Path
from datetime import datetime

# Find latest results
results_dir = Path('results')
if not results_dir.exists():
    print('No results directory found')
    exit()

latest_files = sorted(results_dir.glob('*.json'), key=os.path.getmtime, reverse=True)
if not latest_files:
    print('No result files found')
    exit()

print('📊 Latest Performance Test Results:')
print('=' * 50)

for i, file in enumerate(latest_files[:5]):  # Show last 5 results
    try:
        with open(file) as f:
            data = json.load(f)

        if isinstance(data, dict) and 'total_workflows' in data:
            print(f'{i+1}. {file.name}')
            print(f'   Workflows: {data[\"total_workflows\"]}')
            print(f'   Throughput: {data.get(\"throughput\", 0):.2f} workflows/sec')
            print(f'   Success Rate: {data.get(\"successful_workflows\", 0)/data[\"total_workflows\"]*100:.1f}%')
            print(f'   Avg Latency: {data.get(\"avg_latency\", 0):.3f}s')
            print()
    except Exception as e:
        continue

print('📈 Open Grafana dashboard: http://localhost:3000')
print('📊 View Prometheus metrics: http://localhost:9090')
"

dashboard:
	@echo "Opening Grafana dashboard..."
	@python3 -c "
import webbrowser, time, requests
try:
    # Check if Grafana is accessible
    response = requests.get('http://localhost:3000', timeout=5)
    if response.status_code == 200:
        webbrowser.open('http://localhost:3000')
        print('Grafana dashboard opened in browser')
        print('Login: admin/performance')
    else:
        print('Grafana is not accessible at http://localhost:3000')
except Exception as e:
    print(f'Cannot access Grafana dashboard: {e}')
    print('Make sure services are running: make start')
"

# Utility commands
export-results:
	@echo "Exporting results archive..."
	@tar -czf performance_results_$(shell date +%Y%m%d_%H%M%S).tar.gz results/ logs/
	@echo "Results exported to performance_results_*.tar.gz"

import-results:
ifndef ARCHIVE
	@echo "ERROR: ARCHIVE parameter required"
	@echo "Usage: make import-results ARCHIVE=performance_results_20241201_120000.tar.gz"
	@exit 1
endif
	@echo "Importing results from $(ARCHIVE)..."
	@tar -xzf $(ARCHIVE)
	@echo "Results imported successfully"

# Development commands
dev-setup:
	@echo "Setting up development environment..."
	@pip install -r requirements.txt
	@pip install pytest pytest-timeout pytest-asyncio
	@$(MAKE) setup

dev-test:
	@echo "Running development tests..."
	@pytest test_load_testing_scenarios.py -v --timeout=300 -k "not endurance and not slow"

# Monitoring commands
monitor-resources:
	@echo "Monitoring system resources during tests..."
	@python3 -c "
import psutil, time
print('📊 System Resource Monitor')
print('=' * 30)
print('Press Ctrl+C to stop')
try:
    while True:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        print(f'\\rCPU: {cpu:5.1f}% | RAM: {memory.percent:5.1f}% | Disk: {disk.percent:5.1f}%', end='', flush=True)
        time.sleep(1)
except KeyboardInterrupt:
    print('\\nMonitoring stopped')
"

# Health check command
healthcheck:
	@echo "Running comprehensive health check..."
	@python3 performance_test_runner.py --verify-only --verbose

# Example workflows for different use cases
example-ci:
	@echo "Example CI/CD integration test..."
	@$(MAKE) start
	@sleep 30
	@$(MAKE) ci-test
	@$(MAKE) stop

example-development:
	@echo "Example development workflow..."
	@$(MAKE) start
	@$(MAKE) test-quick
	@$(MAKE) dashboard

example-release:
	@echo "Example release validation workflow..."
	@$(MAKE) start
	@$(MAKE) test-baseline
	@$(MAKE) test-stress
	@$(MAKE) export-results
	@echo "Release validation complete - check results archive"

# Default concurrency levels for different scenarios
QUICK_CONCURRENCY = 25 50
BASELINE_CONCURRENCY = 100 500 1000
STRESS_CONCURRENCY = 1000 1500 2000 3000

# Help with specific scenarios
help-baseline:
	@echo "Baseline Testing Help"
	@echo "===================="
	@echo "Tests system performance at normal load levels"
	@echo "Concurrency levels: $(BASELINE_CONCURRENCY)"
	@echo "Duration: ~10 minutes"
	@echo "Command: make test-baseline"

help-stress:
	@echo "Stress Testing Help"
	@echo "=================="
	@echo "Tests system behavior under extreme load"
	@echo "Max concurrency: 3000 workflows"
	@echo "Duration: ~20 minutes"
	@echo "Command: make test-stress"

help-endurance:
	@echo "Endurance Testing Help"
	@echo "====================="
	@echo "Tests system stability over extended periods"
	@echo "Default duration: 1 hour (use test-endurance-24h for full test)"
	@echo "Command: make test-endurance"
