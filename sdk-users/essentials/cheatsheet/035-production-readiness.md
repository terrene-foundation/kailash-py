# Production Readiness Checklist

**Version**: 0.2.1 | **Topic**: Production Deployment | **Session 064 Learning**

Quick checklist and patterns for ensuring workflows are production-ready.

## 🔍 Pre-Deployment Quick Checks

### ✅ Code Quality (30 seconds)
```bash
# Quick grep check for common issues
grep -r "PythonCodeNode(" --include="*.py" . | grep -v "from_function"  # Should be empty!
grep -r "outputs/" --include="*.py" . | grep -v "get_output_data_path"  # Should be empty!
grep -r "List\[" --include="*.py" .  # Should be empty! (Use 'list' instead)
```

### ✅ Critical Validation
- [ ] **All PythonCodeNode code >3 lines uses `.from_function()`**
- [ ] **All node names end with "Node"**
- [ ] **All file paths use centralized data utilities**
- [ ] **No hardcoded API keys or secrets**
- [ ] **All external calls have error handling**

```python
# ✅ PRODUCTION READY PATTERN
def process_customer_data(customers: list, transactions: list) -> dict:
    """Process customer data with full error handling."""
    try:
        # Validate inputs
        if not customers or not transactions:
            raise ValueError("Missing required input data")

        # Process with comprehensive error handling
        result = complex_processing(customers, transactions)

        return {
            'result': result,
            'status': 'success',
            'processed_count': len(result)
        }

    except ValueError as e:
        logger.error(f"Input validation failed: {e}")
        return {'result': [], 'status': 'validation_error', 'error': str(e)}

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        return {'result': [], 'status': 'processing_error', 'error': str(e)}

# Always use from_function for complex logic
processor = PythonCodeNode.from_function(
    name="customer_processor",
    func=process_customer_data
)
```

## 🔒 Security Essentials

### Environment Configuration
```python
import os
from dataclasses import dataclass

@dataclass
class ProductionConfig:
    """Centralized production configuration."""
    openai_api_key: str = os.getenv('OPENAI_API_KEY', '')
    max_workers: int = int(os.getenv('MAX_WORKERS', '4'))
    timeout_seconds: int = int(os.getenv('TIMEOUT_SECONDS', '300'))
    log_level: str = os.getenv('LOG_LEVEL', 'INFO')

    def validate(self):
        """Validate configuration before startup."""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable required")
        if self.max_workers < 1:
            raise ValueError("MAX_WORKERS must be positive")

# Use in production
config = ProductionConfig()
config.validate()
```

### Safe Data Handling
```python
# ✅ SECURE file path handling
from examples.utils.data_paths import get_input_data_path, get_output_data_path

def secure_file_processor(file_name: str) -> dict:
    """Process files with secure path handling."""
    try:
        # Validate file name (prevent path traversal)
        if '..' in file_name or file_name.startswith('/'):
            raise ValueError(f"Invalid file name: {file_name}")

        # Use centralized, secure path resolution
        input_file = get_input_data_path(file_name)

        # Validate file exists and is readable
        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Process with size limits
        file_size = input_file.stat().st_size
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            raise ValueError(f"File too large: {file_size} bytes")

        return {'status': 'success', 'file_path': str(input_file)}

    except Exception as e:
        return {'status': 'error', 'error': str(e)}
```

## 📊 Performance Patterns

### Batch Processing for Large Datasets
```python
def batch_process_large_dataset(input_data: list, batch_size: int = 1000) -> dict:
    """Process large datasets in batches for memory efficiency."""
    results = []
    total_records = len(input_data)

    for i in range(0, total_records, batch_size):
        batch = input_data[i:i + batch_size]

        try:
            # Process batch
            batch_result = process_batch(batch)
            results.extend(batch_result)

            # Progress tracking
            progress = min((i + batch_size) / total_records * 100, 100)
            print(f"Processed {progress:.1f}% ({len(results)}/{total_records})")

        except Exception as e:
            # Log error but continue with next batch
            print(f"Batch {i//batch_size + 1} failed: {e}")
            continue

    return {
        'result': results,
        'total_processed': len(results),
        'total_input': total_records,
        'success_rate': len(results) / total_records * 100
    }

# Use for large datasets
large_processor = PythonCodeNode.from_function(
    name="large_processor",
    func=batch_process_large_dataset
)
```

### Memory-Efficient Data Processing
```python
def memory_efficient_processing(data: list) -> dict:
    """Process data with memory efficiency."""
    import gc

    try:
        # Process in chunks to manage memory
        chunk_size = 500
        processed_chunks = []

        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]

            # Process chunk
            processed_chunk = transform_data_chunk(chunk)
            processed_chunks.append(processed_chunk)

            # Force garbage collection after each chunk
            gc.collect()

        # Combine results
        final_result = combine_chunks(processed_chunks)

        return {
            'result': final_result,
            'chunks_processed': len(processed_chunks),
            'memory_efficient': True
        }

    except MemoryError:
        return {
            'result': [],
            'error': 'Insufficient memory for processing',
            'suggestion': 'Reduce batch size or use streaming processing'
        }
```

## 🛡️ Error Handling Patterns

### Robust API Call Pattern
```python
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def robust_api_call(data: dict) -> dict:
    """API call with automatic retry and comprehensive error handling."""
    try:
        # Make API call
        response = external_api.process(data)

        # Validate response
        if not response or 'error' in response:
            raise APIResponseError(f"Invalid API response: {response}")

        logger.info(f"API call successful for {len(data)} records")
        return {'result': response, 'status': 'success'}

    except requests.exceptions.Timeout:
        logger.warning("API call timed out, will retry")
        raise  # Will be retried by tenacity

    except requests.exceptions.ConnectionError:
        logger.warning("API connection failed, will retry")
        raise  # Will be retried by tenacity

    except APIRateLimitError as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise  # Will be retried with exponential backoff

    except Exception as e:
        logger.error(f"Unrecoverable API error: {e}")
        return {
            'result': [],
            'status': 'error',
            'error': str(e),
            'fallback_applied': False
        }

# Use in workflow
api_caller = PythonCodeNode.from_function(
    name="robust_api_caller",
    func=robust_api_call
)
```

### Graceful Degradation Pattern
```python
def process_with_fallback(primary_data: dict, fallback_data: dict = None) -> dict:
    """Process data with fallback strategy."""
    try:
        # Primary processing path
        result = complex_primary_processing(primary_data)

        return {
            'result': result,
            'status': 'primary_success',
            'processing_method': 'primary'
        }

    except CriticalError as e:
        # Some errors shouldn't have fallbacks
        return {
            'result': [],
            'status': 'critical_error',
            'error': str(e),
            'requires_manual_intervention': True
        }

    except Exception as e:
        # Try fallback processing
        logger.warning(f"Primary processing failed: {e}, trying fallback")

        try:
            if fallback_data:
                result = simple_fallback_processing(fallback_data)
            else:
                result = simple_fallback_processing(primary_data)

            return {
                'result': result,
                'status': 'fallback_success',
                'processing_method': 'fallback',
                'primary_error': str(e)
            }

        except Exception as fallback_error:
            return {
                'result': [],
                'status': 'complete_failure',
                'primary_error': str(e),
                'fallback_error': str(fallback_error)
            }
```

## 📝 Monitoring & Logging

### Production Logging Setup
```python
import logging
import json
from datetime import datetime

def setup_production_logging():
    """Configure structured logging for production."""

    # Create custom formatter for structured logs
    class StructuredFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': record.levelname,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno
            }

            # Add extra fields if present
            if hasattr(record, 'workflow_id'):
                log_entry['workflow_id'] = record.workflow_id
            if hasattr(record, 'run_id'):
                log_entry['run_id'] = record.run_id

            return json.dumps(log_entry)

    # Configure logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

    return logger

# Use in production workflows
def monitored_processing(data: list, run_id: str) -> dict:
    """Processing with comprehensive monitoring."""
    logger = logging.getLogger(__name__)

    # Create logger adapter with context
    log_extra = {'run_id': run_id, 'workflow_id': 'production_etl'}
    contextual_logger = logging.LoggerAdapter(logger, log_extra)

    start_time = datetime.utcnow()
    contextual_logger.info(f"Starting processing for {len(data)} records")

    try:
        result = process_data(data)

        duration = (datetime.utcnow() - start_time).total_seconds()
        contextual_logger.info(
            f"Processing completed successfully in {duration:.2f}s, "
            f"processed {len(result)} records"
        )

        return {
            'result': result,
            'status': 'success',
            'processing_time': duration,
            'records_processed': len(result)
        }

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        contextual_logger.error(
            f"Processing failed after {duration:.2f}s: {str(e)}"
        )

        return {
            'result': [],
            'status': 'error',
            'error': str(e),
            'processing_time': duration
        }
```

## 🚀 Quick Production Checklist

### Before Deployment
- [ ] All environment variables configured
- [ ] No hardcoded secrets or API keys
- [ ] All PythonCodeNode >3 lines uses `.from_function()`
- [ ] Error handling for all external calls
- [ ] Input validation at entry points
- [ ] Resource limits configured (memory, timeout)
- [ ] Logging properly configured
- [ ] Health check endpoint available

### Performance Validation
- [ ] Tested with production-sized datasets
- [ ] Memory usage within acceptable limits
- [ ] Processing time meets SLA requirements
- [ ] Concurrent execution tested
- [ ] Batch processing for large datasets

### Security Validation
- [ ] Input sanitization implemented
- [ ] No path traversal vulnerabilities
- [ ] API keys in environment variables
- [ ] Output doesn't expose sensitive data
- [ ] Access control configured

### Monitoring Validation
- [ ] Structured logging implemented
- [ ] Key metrics collected
- [ ] Alert rules configured
- [ ] Health check working
- [ ] Error tracking enabled

## 💡 Production Tips

1. **Start with validation** - Validate inputs early, fail fast
2. **Use batch processing** - For datasets >1000 records
3. **Implement fallbacks** - Graceful degradation for external failures
4. **Monitor everything** - Logs, metrics, health checks
5. **Test error scenarios** - Don't just test the happy path
6. **Use environment variables** - Never hardcode configuration
7. **Handle timeouts** - All external calls should have timeouts
8. **Plan for rollback** - Know how to quickly revert changes

---

**Remember**: Production readiness is about reliability, not just functionality!

*Related: [033-workflow-design-process.md](033-workflow-design-process.md), [034-data-integration-patterns.md](034-data-integration-patterns.md)*
