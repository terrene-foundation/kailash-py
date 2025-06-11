# Production Readiness Checklist

Ensure your workflows are ready for production deployment with this comprehensive checklist.

## 🔍 Pre-Deployment Validation

### ✅ Code Quality
- [ ] **PythonCodeNode Functions**: All code >3 lines uses `.from_function()` pattern
- [ ] **Node Names**: All custom nodes end with "Node" suffix
- [ ] **Error Handling**: Each function includes try-catch blocks
- [ ] **Input Validation**: All inputs validated before processing
- [ ] **Type Hints**: All functions have proper type annotations

```python
# ✅ PRODUCTION READY
def process_customer_data(customers: list, transactions: list) -> dict:
    """Process customer data with full error handling."""
    try:
        # Validate inputs
        if not customers or not transactions:
            raise ValueError("Missing required input data")
        
        # Process with error handling
        result = complex_processing(customers, transactions)
        return {'result': result, 'status': 'success'}
    
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return {'result': [], 'status': 'error', 'error': str(e)}

processor = PythonCodeNode.from_function(
    name="customer_processor",
    func=process_customer_data
)
```

### ✅ Data Management
- [ ] **File Paths**: Use centralized `get_input_data_path()` and `get_output_data_path()`
- [ ] **Data Validation**: Schema validation for all inputs
- [ ] **Large Files**: Batch processing for datasets >1000 records
- [ ] **Backup Strategy**: Output files include timestamps
- [ ] **Clean Up**: Temporary files properly removed

```python
# ✅ PRODUCTION DATA HANDLING
from examples.utils.data_paths import get_input_data_path, get_output_data_path

# Input validation
input_file = get_input_data_path("customers.csv")
if not input_file.exists():
    raise FileNotFoundError(f"Required input file missing: {input_file}")

# Output with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = get_output_data_path(f"results_{timestamp}.json")
```

### ✅ Workflow Architecture
- [ ] **Single Responsibility**: Each node has one clear purpose
- [ ] **Fail-Fast**: Input validation at workflow start
- [ ] **Graceful Degradation**: Fallback strategies for failures
- [ ] **Progress Tracking**: Long-running workflows include progress updates
- [ ] **Resource Management**: Memory and CPU usage optimized

```python
# ✅ PRODUCTION WORKFLOW STRUCTURE
def create_production_workflow():
    workflow = Workflow("production-etl", "Production ETL Pipeline")
    
    # 1. Input validation (fail-fast)
    validator = PythonCodeNode.from_function(
        name="input_validator",
        func=validate_all_inputs
    )
    
    # 2. Main processing with error handling
    processor = PythonCodeNode.from_function(
        name="main_processor",
        func=process_with_fallback
    )
    
    # 3. Results validation
    result_validator = PythonCodeNode.from_function(
        name="result_validator", 
        func=validate_outputs
    )
    
    # Connect with descriptive mappings
    workflow.connect("input_validator", "main_processor", 
                    mapping={"result": "validated_inputs"})
    workflow.connect("main_processor", "result_validator",
                    mapping={"result": "processed_data"})
    
    return workflow
```

## 🔒 Security & Access Control

### ✅ Authentication & Authorization
- [ ] **API Keys**: All secrets in environment variables
- [ ] **Access Control**: Role-based permissions configured
- [ ] **Input Sanitization**: All user inputs sanitized
- [ ] **Output Filtering**: Sensitive data filtered from outputs
- [ ] **Audit Logging**: All operations logged

```python
# ✅ SECURE CONFIGURATION
import os
from kailash.access_control import SecureWorkflowRunner

# Environment-based configuration
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    raise ValueError("Missing required API key")

# Secure workflow execution
secure_runner = SecureWorkflowRunner(
    tenant_id="production",
    allowed_roles=["data_analyst", "workflow_admin"]
)

results = secure_runner.execute(
    workflow=workflow,
    user_id="user123",
    role="data_analyst"
)
```

### ✅ Data Privacy
- [ ] **PII Handling**: Personal data properly masked/encrypted
- [ ] **Data Retention**: Clear retention policies implemented
- [ ] **Export Controls**: Sensitive data cannot be exported
- [ ] **Compliance**: GDPR/CCPA requirements met

## 📊 Performance & Monitoring

### ✅ Performance Optimization
- [ ] **Memory Usage**: Workflows tested with production data volumes
- [ ] **Processing Time**: Acceptable latency for all operations
- [ ] **Concurrent Execution**: Thread-safe for parallel processing
- [ ] **Resource Limits**: CPU and memory limits configured
- [ ] **Caching**: Expensive operations cached appropriately

```python
# ✅ PERFORMANCE MONITORING
from kailash.tracking import MetricsCollector

metrics = MetricsCollector()

# Monitor execution
with metrics.timer("workflow_execution"):
    results, run_id = runtime.execute(workflow, inputs=inputs)

# Track resource usage
metrics.record_memory_usage()
metrics.record_processing_time()
print(f"Workflow completed in {metrics.get_duration('workflow_execution'):.2f}s")
```

### ✅ Error Handling & Recovery
- [ ] **Comprehensive Logging**: All errors logged with context
- [ ] **Retry Logic**: Transient failures automatically retried
- [ ] **Circuit Breakers**: External service failures handled gracefully
- [ ] **Dead Letter Queue**: Failed items stored for manual review
- [ ] **Alerting**: Critical failures trigger immediate alerts

```python
# ✅ PRODUCTION ERROR HANDLING
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def robust_api_call(data: dict) -> dict:
    """API call with automatic retry logic."""
    try:
        response = external_api.process(data)
        logger.info(f"API call successful for {len(data)} records")
        return {'result': response, 'status': 'success'}
    
    except APITimeoutError as e:
        logger.warning(f"API timeout, retrying: {e}")
        raise  # Will be retried
    
    except APIRateLimitError as e:
        logger.warning(f"Rate limit hit, backing off: {e}")
        raise  # Will be retried with exponential backoff
    
    except Exception as e:
        logger.error(f"Unrecoverable API error: {e}")
        return {'result': [], 'status': 'error', 'error': str(e)}
```

## 🧪 Testing & Validation

### ✅ Test Coverage
- [ ] **Unit Tests**: All functions tested independently
- [ ] **Integration Tests**: End-to-end workflow testing
- [ ] **Performance Tests**: Load testing with production volumes
- [ ] **Error Scenarios**: Failure cases tested
- [ ] **Data Quality**: Input/output validation tests

```python
# ✅ PRODUCTION TEST SUITE
import pytest
from unittest.mock import Mock, patch

def test_workflow_with_production_data():
    """Test workflow with realistic production data volumes."""
    # Load production-sized test data
    large_dataset = load_test_data(size=10000)
    
    # Execute workflow
    results, run_id = runtime.execute(workflow, inputs={"data": large_dataset})
    
    # Validate results
    assert results["final_output"]["status"] == "success"
    assert len(results["final_output"]["result"]) > 0
    assert all("customer_id" in record for record in results["final_output"]["result"])

def test_error_handling():
    """Test workflow handles errors gracefully."""
    # Test with malformed data
    bad_data = [{"invalid": "data"}]
    
    results, run_id = runtime.execute(workflow, inputs={"data": bad_data})
    
    # Should handle gracefully, not crash
    assert "error" in results["final_output"]
    assert results["final_output"]["status"] == "error"

@patch('external_service.api_call')
def test_external_service_failure(mock_api):
    """Test workflow handles external service failures."""
    mock_api.side_effect = ConnectionError("Service unavailable")
    
    results, run_id = runtime.execute(workflow, inputs={"data": test_data})
    
    # Should fallback gracefully
    assert results["final_output"]["status"] in ["fallback_success", "error"]
    assert "fallback_applied" in results["final_output"]
```

## 🚀 Deployment

### ✅ Environment Configuration
- [ ] **Environment Variables**: All configuration externalized
- [ ] **Resource Limits**: Memory and CPU limits set
- [ ] **Health Checks**: Endpoint for monitoring service health
- [ ] **Graceful Shutdown**: Clean shutdown procedures implemented
- [ ] **Version Management**: Clear versioning and rollback strategy

```python
# ✅ PRODUCTION CONFIGURATION
import os
from dataclasses import dataclass

@dataclass
class ProductionConfig:
    """Production environment configuration."""
    max_workers: int = int(os.getenv('MAX_WORKERS', '4'))
    timeout_seconds: int = int(os.getenv('TIMEOUT_SECONDS', '300'))
    memory_limit_mb: int = int(os.getenv('MEMORY_LIMIT_MB', '2048'))
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')
    
    def validate(self):
        """Validate configuration before startup."""
        if self.max_workers < 1:
            raise ValueError("MAX_WORKERS must be positive")
        if self.timeout_seconds < 30:
            raise ValueError("TIMEOUT_SECONDS must be at least 30")

# Use in production
config = ProductionConfig()
config.validate()
```

### ✅ Monitoring & Alerting
- [ ] **Health Endpoint**: Service health monitoring
- [ ] **Metrics Collection**: Key performance indicators tracked
- [ ] **Log Aggregation**: Centralized logging configured
- [ ] **Alert Rules**: Critical issues trigger alerts
- [ ] **Dashboard**: Real-time monitoring dashboard

```python
# ✅ PRODUCTION MONITORING
from flask import Flask, jsonify
from kailash.monitoring import HealthChecker

app = Flask(__name__)
health_checker = HealthChecker()

@app.route('/health')
def health_check():
    """Health check endpoint for load balancers."""
    status = health_checker.check_all()
    
    return jsonify({
        'status': 'healthy' if status['overall'] else 'unhealthy',
        'checks': status['checks'],
        'timestamp': status['timestamp']
    }), 200 if status['overall'] else 503

@app.route('/metrics')
def metrics():
    """Metrics endpoint for monitoring systems."""
    return jsonify({
        'workflows_executed': metrics.get_counter('workflows_executed'),
        'average_duration': metrics.get_average('workflow_duration'),
        'error_rate': metrics.get_rate('workflow_errors'),
        'memory_usage': metrics.get_current('memory_usage_mb')
    })
```

## 📋 Pre-Deployment Checklist

### Code Review
- [ ] All PythonCodeNode uses `.from_function()` for code >3 lines
- [ ] No hardcoded file paths or credentials
- [ ] Error handling implemented for all external calls
- [ ] Input validation at workflow entry points
- [ ] Memory usage optimized for large datasets

### Testing
- [ ] Unit tests pass with 90%+ coverage
- [ ] Integration tests pass with production-sized data
- [ ] Performance tests meet SLA requirements
- [ ] Error scenarios tested and handled gracefully
- [ ] Security scan completed with no critical issues

### Infrastructure
- [ ] Environment variables configured
- [ ] Resource limits set appropriately
- [ ] Monitoring and alerting configured
- [ ] Backup and recovery procedures tested
- [ ] Rollback plan documented and tested

### Documentation
- [ ] API documentation updated
- [ ] Deployment guide current
- [ ] Troubleshooting guide includes new workflows
- [ ] Change log updated
- [ ] Team training completed

---

**Remember**: Production readiness is not just about functionality - it's about reliability, security, performance, and maintainability. Take time to validate each item thoroughly before deployment.

**Quick Validation**: If you can't confidently check every box above, your workflow isn't ready for production!