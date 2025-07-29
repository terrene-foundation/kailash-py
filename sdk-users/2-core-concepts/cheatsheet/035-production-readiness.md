# Production Readiness Checklist

*Quick checklist and patterns for production deployment*

## ✅ Quick Pre-Deployment Checks (30 seconds)

```bash
# Quick grep check for common issues
grep -r "PythonCodeNode(" --include="*.py" . | grep -v "from_function"  # Should be empty!
grep -r "outputs/" --include="*.py" . | grep -v "get_output_data_path"  # Should be empty!
grep -r "List\[" --include="*.py" .  # Should be empty! (Use 'list' instead)
```

### Critical Validation Checklist
- [ ] All PythonCodeNode >3 lines uses `.from_function()`
- [ ] All node names end with "Node"
- [ ] All file paths use centralized data utilities
- [ ] No hardcoded API keys or secrets
- [ ] All external calls have error handling

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

### Safe File Handling
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

from examples.utils.data_paths import get_input_data_path, get_output_data_path

def workflow.()  # Type signature example -> dict:
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

# Usage
secure_processor = PythonCodeNode.from_function(
    name="secure_processor", func=secure_file_processor
)

```

## 📊 Performance Patterns

### Batch Processing for Large Datasets
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
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

# Usage
large_processor = PythonCodeNode.from_function(
    name="large_processor", func=batch_process_large_dataset
)

```

### Memory-Efficient Processing
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
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

# Usage
memory_processor = PythonCodeNode.from_function(
    name="memory_processor", func=memory_efficient_processing
)

```

## 🛡️ Error Handling Patterns

### Robust API Call Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
def workflow.()  # Type signature example -> dict:
    """API call with automatic retry and comprehensive error handling."""
    try:
        # Make API call
        response = external_api.execute(data)

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

# Usage
api_caller = PythonCodeNode.from_function(
    name="robust_api_caller", func=robust_api_call
)

```

### Graceful Degradation Pattern
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
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

# Usage
fallback_processor = PythonCodeNode.from_function(
    name="fallback_processor", func=process_with_fallback
)

```

## 📝 Monitoring & Logging

### Production Logging Setup
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

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

# Usage in production workflows
def workflow.()  # Type signature example -> dict:
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

# Usage
monitored_processor = PythonCodeNode.from_function(
    name="monitored_processor", func=monitored_processing
)

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

## 🔧 Production-Ready Example

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

def workflow.()  # Type signature example -> dict:
    """Complete production-ready processing function."""
    import time
    import logging

    logger = logging.getLogger(__name__)
    start_time = time.time()

    try:
        # 1. Validate inputs
        if not data or not isinstance(data, list):
            raise ValueError("Data must be a non-empty list")

        if len(data) > config.get('max_records', 10000):
            raise ValueError(f"Dataset too large: {len(data)} records")

        # 2. Process with batching
        batch_size = config.get('batch_size', 1000)
        results = []

        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            batch_result = process_batch_safely(batch)
            results.extend(batch_result)

            # Progress logging
            progress = min((i + batch_size) / len(data) * 100, 100)
            logger.info(f"Processed {progress:.1f}% ({len(results)}/{len(data)})")

        # 3. Validate results
        if len(results) < len(data) * 0.8:  # Less than 80% success
            logger.warning(f"Low success rate: {len(results)}/{len(data)}")

        processing_time = time.time() - start_time

        return {
            'result': results,
            'status': 'success',
            'statistics': {
                'input_records': len(data),
                'output_records': len(results),
                'success_rate': len(results) / len(data) * 100,
                'processing_time': processing_time
            }
        }

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Processing failed: {e}")

        return {
            'result': [],
            'status': 'error',
            'error': str(e),
            'processing_time': processing_time
        }

# Usage
production_processor = PythonCodeNode.from_function(
    name="production_processor", func=production_ready_processor
)

```

---

**Remember**: Production readiness is about reliability, not just functionality!

*Related: [034-data-integration-patterns.md](034-data-integration-patterns.md), [007-error-handling.md](007-error-handling.md)*
