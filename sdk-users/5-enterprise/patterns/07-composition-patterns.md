# Composition Patterns

Patterns for building complex workflows through composition, nesting, and dynamic generation.

## 1. Nested Workflow Pattern

**Purpose**: Reuse existing workflows as components in larger workflows

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.logic import WorkflowNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Create reusable sub-workflows
def create_data_validation_workflow():
    """Reusable data validation workflow"""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "schema_check", {
        "code": """
# Validate data schema
required_fields = ['id', 'name', 'value', 'timestamp']
missing_fields = [f for f in required_fields if f not in data[0].keys()]

if missing_fields:
    raise ValueError(f"Missing required fields: {missing_fields}")

# Validate data types
for record in data:
    if not isinstance(record.get('id'), (int, str)):
        raise TypeError(f"Invalid id type: {type(record.get('id'))}")
    if not isinstance(record.get('value'), (int, float)):
        raise TypeError(f"Invalid value type: {type(record.get('value'))}")

result = {'valid': True, 'record_count': len(data), 'data': data}
"""
    })

    workflow.add_node("PythonCodeNode", "quality_check", {
        "code": """
# Check data quality
issues = []
clean_data = []

for record in data:
    if record.get('value', 0) < 0:
        issues.append(f"Negative value in record {record['id']}")
    elif record.get('value', 0) > 1000000:
        issues.append(f"Suspiciously high value in record {record['id']}")
    else:
        clean_data.append(record)

result = {
    'data': clean_data,
    'removed_count': len(data) - len(clean_data),
    'issues': issues,
    'quality_score': len(clean_data) / len(data) if data else 0
}
"""
    })

    workflow.add_connection("schema_check", "data", "quality_check", "data")
    return workflow

# Create main workflow that uses sub-workflows
main_workflow = WorkflowBuilder()

# Add sub-workflow as a node
main_workflow.add_node("WorkflowNode", "validator", {
    "workflow": create_data_validation_workflow(),
    # Map main workflow data to sub-workflow inputs
    "input_mapping": {"data": "data"},
    # Map sub-workflow outputs to main workflow
    "output_mapping": {"validation_result": "result"}
})

# Continue with main workflow
main_workflow.add_node("PythonCodeNode", "processor", {
    "code": """
# Process validated data
print(f"Processing {validation_result['quality_score']:.0%} quality data")

processed_data = []
for record in validation_result['data']:
    processed = {
        **record,
        'processed_value': record['value'] * 1.1,
        'status': 'processed'
    }
    processed_data.append(processed)

result = {
    'data': processed_data,
    'metadata': {
        'quality_score': validation_result['quality_score'],
        'processed_count': len(processed_data)
    }
}
"""
})

main_workflow.add_connection("validator", "validation_result", "processor", "validation_result")

# Execute main workflow
runtime = LocalRuntime()
results, run_id = runtime.execute(main_workflow, parameters={
    "validator": {"raw_data": [
        {"id": 1, "name": "Item1", "value": 100, "timestamp": "2024-01-01"},
        {"id": 2, "name": "Item2", "value": -50, "timestamp": "2024-01-02"},
        {"id": 3, "name": "Item3", "value": 200, "timestamp": "2024-01-03"}
    ]}
})

```

## 2. Workflow Factory Pattern

**Purpose**: Create workflows dynamically based on configuration

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.data import CSVReaderNode, JSONWriterNode, SQLNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.ai import LLMAgentNode

class WorkflowFactory:
    """Factory for creating workflows based on configuration"""

    def __init__(self):
        self.node_registry = {
            'csv_reader': CSVReaderNode,
            'json_writer': JSONWriterNode,
            'sql_query': SQLNode,
            'python_code': PythonCodeNode,
            'llm_agent': LLMAgentNode,
            'transformer': self._create_transformer_node,
            'aggregator': self._create_aggregator_node
        }

    def create_workflow(self, config):
        """Create workflow from configuration dictionary"""
        workflow = WorkflowBuilder()
workflow.        )

        # Create nodes
        for node_config in config['nodes']:
            node_type = node_config['type']
            node_id = node_config['id']

            # Get node class or factory method
            node_creator = self.node_registry.get(node_type)
            if not node_creator:
                raise ValueError(f"Unknown node type: {node_type}")

            # Create node instance
            if callable(node_creator) and not isinstance(node_creator, type):
                # Factory method
                node = node_creator(node_config)
            else:
                # Node class
                node = node_creator()

            # Add node with configuration
            workflow.add_node(node_id, node, **node_config.get('config', {}))

        # Create connections
        for conn in config['connections']:
            workflow.add_connection(conn['from'], "result", conn['to'], "input"),
                **conn.get('options', {})
            )

        return workflow

    def _create_transformer_node(self, config):
        """Factory method for transformer nodes"""
        transform_type = config.get('transform_type', 'custom')

        if transform_type == 'uppercase':
            code = "result = [item.upper() if isinstance(item, str) else item for item in data]"
        elif transform_type == 'aggregate':
            code = "result = {'sum': sum(data), 'count': len(data), 'avg': sum(data)/len(data)}"
        else:
            code = config.get('code', 'result = data')

        return PythonCodeNode(code=code)

    def _create_aggregator_node(self, config):
        """Factory method for aggregator nodes"""
        agg_type = config.get('aggregation', 'sum')

        code_templates = {
            'sum': "result = sum(item.get('value', 0) for item in data)",
            'count': "result = len(data)",
            'average': "result = sum(item.get('value', 0) for item in data) / len(data)",
            'group_by': f"""
grouped = {{}}
for item in data:
    key = item.get('{config.get('group_field', 'category')}')
    if key not in grouped:
        grouped[key] = []
    grouped[key].append(item)
result = grouped
"""
        }

        code = code_templates.get(agg_type, "result = data")
        return PythonCodeNode(code=code)

# Use the factory
factory = WorkflowFactory()

# Configuration-driven workflow creation
workflow_config = {
    'id': 'etl_pipeline',
    'name': 'ETL Pipeline',
    'description': 'Configurable ETL workflow',
    'nodes': [
        {
            'id': 'reader',
            'type': 'csv_reader',
            'config': {'file_path': 'input.csv'}
        },
        {
            'id': 'transformer',
            'type': 'transformer',
            'transform_type': 'custom',
            'code': 'result = [{"id": r["id"], "value": r["value"] * 2} for r in data]'
        },
        {
            'id': 'aggregator',
            'type': 'aggregator',
            'aggregation': 'group_by',
            'group_field': 'category'
        },
        {
            'id': 'writer',
            'type': 'json_writer',
            'config': {'file_path': 'output.json'}
        }
    ],
    'connections': [
        {'from': 'reader', 'to': 'transformer', 'mapping': {'data': 'data'}},
        {'from': 'transformer', 'to': 'aggregator', 'mapping': {'result': 'data'}},
        {'from': 'aggregator', 'to': 'writer', 'mapping': {'result': 'data'}}
    ]
}

workflow = factory.create_workflow(workflow_config)

```

## 3. Template-Based Workflow Pattern

**Purpose**: Create workflows from predefined templates with customization

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

class WorkflowTemplate:
    """Base class for workflow templates"""

    def create_workflow(self, **params):
        """Create workflow with custom parameters"""
        raise NotImplementedError

class DataQualityTemplate(WorkflowTemplate):
    """Template for data quality workflows"""

    def create_workflow(self, **params):
        workflow = WorkflowBuilder(),
            params.get('name', 'Data Quality Check')
        )

        # Configurable validation rules
        validation_rules = params.get('validation_rules', [])

        # Create validation node with custom rules
        validation_code = self._generate_validation_code(validation_rules)
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "validator", {}), code=validation_code)

        # Add reporting node
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "reporter", {}),
            code="""
report = {
    'total_records': validation_result['total'],
    'valid_records': validation_result['valid_count'],
    'invalid_records': validation_result['invalid_count'],
    'validation_errors': validation_result['errors'],
    'quality_score': validation_result['valid_count'] / validation_result['total']
}

# Generate detailed report
if report['quality_score'] < 0.95:
    report['status'] = 'QUALITY_ISSUE'
    report['recommendation'] = 'Review data sources'
else:
    report['status'] = 'PASSED'

result = report
"""
        )

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

        return workflow

    def _generate_validation_code(self, rules):
        """Generate validation code from rules"""
        rule_checks = []

        for rule in rules:
            if rule['type'] == 'required':
                rule_checks.append(f"""
if not record.get('{rule['field']}'):
    errors.append({{
        'record_id': record.get('id', 'unknown'),
        'field': '{rule['field']}',
        'error': 'Required field missing'
    }})
    continue
""")
            elif rule['type'] == 'range':
                rule_checks.append(f"""
value = record.get('{rule['field']}', 0)
if not ({rule['min']} <= value <= {rule['max']}):
    errors.append({{
        'record_id': record.get('id', 'unknown'),
        'field': '{rule['field']}',
        'error': f'Value {{value}} outside range [{rule['min']}, {rule['max']}]'
    }})
    continue
""")
            elif rule['type'] == 'regex':
                rule_checks.append(f"""
import re
value = str(record.get('{rule['field']}', ''))
if not re.match(r'{rule['pattern']}', value):
    errors.append({{
        'record_id': record.get('id', 'unknown'),
        'field': '{rule['field']}',
        'error': f'Value {{value}} does not match pattern {rule['pattern']}'
    }})
    continue
""")

        code = f"""
errors = []
valid_records = []

for record in data:
    {''.join(rule_checks)}
    valid_records.append(record)

result = {{
    'total': len(data),
    'valid_count': len(valid_records),
    'invalid_count': len(errors),
    'errors': errors,
    'valid_data': valid_records
}}
"""
        return code

# Use template to create customized workflow
template = DataQualityTemplate()
quality_workflow = template.create_workflow(
    id='customer_quality',
    name='Customer Data Quality',
    validation_rules=[
        {'type': 'required', 'field': 'customer_id'},
        {'type': 'required', 'field': 'email'},
        {'type': 'range', 'field': 'age', 'min': 18, 'max': 120},
        {'type': 'regex', 'field': 'email', 'pattern': r'^[\w\.-]+@[\w\.-]+\.\w+$'}
    ]
)

```

## 4. Plugin-Based Workflow Pattern

**Purpose**: Extend workflows with pluggable components

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

class WorkflowPlugin:
    """Base class for workflow plugins"""

    def enhance_workflow(self, workflow, attachment_point, **config):
        """Add plugin functionality to workflow"""
        raise NotImplementedError

class LoggingPlugin(WorkflowPlugin):
    """Add logging to any workflow"""

    def enhance_workflow(self, workflow, attachment_point, **config):
        log_level = config.get('log_level', 'INFO')

        # Add logging before the attachment point
        logger_id = f"{attachment_point}_logger"
workflow = WorkflowBuilder()
workflow.add_node(logger_id, "PythonCodeNode",
            code=f"""
import datetime
import json

log_entry = {{
    'timestamp': datetime.datetime.now().isoformat(),
    'node': '{attachment_point}',
    'level': '{log_level}',
    'data_preview': str(data)[:200] if data else None,
    'data_type': type(data).__name__,
    'data_size': len(data) if hasattr(data, '__len__') else 'N/A'
}}

print(f"[{{log_entry['timestamp']}}] {{log_entry['level']}}: Node {{log_entry['node']}} - {{log_entry['data_type']}} ({{log_entry['data_size']}} items)")

# Pass through data unchanged
result = data
"""
        )

        # Rewire connections through logger
        # Find connections to attachment point
workflow = WorkflowBuilder()
workflow.connections:
            if conn['to'] == attachment_point:
                # Redirect to logger first
                conn['to'] = logger_id
                # Then connect logger to original target
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

class CachingPlugin(WorkflowPlugin):
    """Add caching to expensive nodes"""

    def enhance_workflow(self, workflow, attachment_point, **config):
        cache_ttl = config.get('ttl', 3600)

        cache_id = f"{attachment_point}_cache"
workflow = WorkflowBuilder()
workflow.add_node(cache_id, "PythonCodeNode",
            code=f"""
import hashlib
import json
import time

# Initialize cache
if not hasattr(self, '_cache'):
    self._cache = {{}}

# Generate cache key
cache_key = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()

# Check cache
if cache_key in self._cache:
    entry = self._cache[cache_key]
    if time.time() - entry['timestamp'] < {cache_ttl}:
        print(f"Cache hit for {attachment_point}")
        result = entry['data']
        return result

# Cache miss - will proceed to actual node
print(f"Cache miss for {attachment_point}")
result = data  # Pass through to actual node
"""
        )

        # Add cache storage after the node
        cache_store_id = f"{attachment_point}_cache_store"
workflow = WorkflowBuilder()
workflow.add_node(cache_store_id, "PythonCodeNode",
            code="""
# Store result in cache
if not hasattr(self, '_cache'):
    self._cache = {}

cache_key = hashlib.md5(json.dumps(original_input, sort_keys=True).encode()).hexdigest()
self._cache[cache_key] = {
    'data': node_output,
    'timestamp': time.time()
}

result = node_output  # Pass through
"""
        )

# Create workflow with plugins
base_workflow = WorkflowBuilder()

# Add base nodes
workflow = WorkflowBuilder()
workflow.add_node("CSVReaderNode", "data_source", {}), file_path="data.csv")
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "expensive_processor", {}),
    code="""
# Simulate expensive computation
import time
time.sleep(2)
result = [{'id': r['id'], 'computed': r['value'] * 100} for r in data]
"""
)
workflow = WorkflowBuilder()
workflow.add_node("JSONWriterNode", "output", {}), file_path="output.json")

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Enhance with plugins
logging_plugin = LoggingPlugin()
logging_plugin.enhance_workflow(base_workflow, "expensive_processor", log_level="DEBUG")

caching_plugin = CachingPlugin()
caching_plugin.enhance_workflow(base_workflow, "expensive_processor", ttl=600)

```

## 5. Workflow Inheritance Pattern

**Purpose**: Create specialized workflows by extending base workflows

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

class BaseWorkflow:
    """Base workflow class with common functionality"""

    def __init__(self, workflow_id, name):
        self.workflow = WorkflowBuilder()
workflow.        self._setup_common_nodes()

    def _setup_common_nodes(self):
        """Setup nodes common to all workflows"""
        # Add input validation
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "input_validator", {}),
            code="""
if not data:
    raise ValueError("Input data is empty")

if not isinstance(data, (list, dict)):
    raise TypeError(f"Expected list or dict, got {type(data)}")

result = {'validated': True, 'data': data}
"""
        )

        # Add error handler
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "error_handler", {}),
            code="""
error_log = {
    'error_type': error.get('type', 'unknown'),
    'error_message': error.get('message', 'Unknown error'),
    'timestamp': datetime.datetime.now().isoformat(),
    'context': error.get('context', {})
}

# Log error
print(f"ERROR: {error_log['error_message']}")

# Return safe default
result = {'status': 'error', 'error': error_log, 'data': None}
"""
        )

    def add_processing_logic(self):
        """Override in subclasses to add specific processing"""
        raise NotImplementedError

    def build(self):
        """Build and return the workflow"""
        self.add_processing_logic()
        return self.workflow

class DataTransformWorkflow(BaseWorkflow):
    """Specialized workflow for data transformation"""

    def __init__(self, workflow_id="data_transform", name="Data Transform"):
        super().__init__(workflow_id, name)
        self.transformers = []

    def add_transformer(self, transformer_id, transform_code):
        """Add a transformation step"""
        self.transformers.append({
            'id': transformer_id,
            'code': transform_code
        })

    def add_processing_logic(self):
        """Add transformation pipeline"""
        prev_node = "input_validator"

        # Chain transformers
        for i, transformer in enumerate(self.transformers):
            node_id = f"transformer_{i}"
workflow = WorkflowBuilder()
workflow.add_node(node_id, "PythonCodeNode",
                code=transformer['code']
            )

            # mapping removed)
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
            prev_node = node_id

        # Add final output formatter
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "output_formatter", {}),
            code="""
result = {
    'transformed_data': data,
    'record_count': len(data) if isinstance(data, list) else 1,
    'transformation_complete': True
}
"""
        )

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

# Use inherited workflow
transform_workflow = DataTransformWorkflow("customer_transform", "Customer Data Transform")

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature.strip().title()
    result.append(cleaned)
""")

workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature[0])
        enhanced['age'] = datetime.now().year - birth_year
    result.append(enhanced)
""")

workflow = WorkflowBuilder()
workflow.build()

```

## Best Practices

1. **Modularity**:
   - Keep sub-workflows focused on single responsibilities
   - Use clear interfaces between workflows
   - Document input/output contracts

2. **Reusability**:
   - Design workflows to be configuration-driven
   - Use templates for common patterns
   - Create plugin interfaces for extensions

3. **Maintainability**:
   - Use factory patterns for complex creation logic
   - Implement proper error handling at boundaries
   - Version your workflow templates

4. **Testing**:
   - Test sub-workflows independently
   - Mock sub-workflows in integration tests
   - Validate workflow composition

## See Also
- [Core Patterns](01-core-patterns.md) - Basic workflow building blocks
- [Control Flow Patterns](02-control-flow-patterns.md) - Routing and conditions
- [Best Practices](11-best-practices.md) - General design guidelines
