# Common Node Patterns

## Data I/O
```python
# CSV Reading with centralized data paths (Session 062)
from examples.utils.data_paths import get_input_data_path, get_output_data_path

workflow.add_node("csv_in", CSVReaderNode(),
    file_path=str(get_input_data_path("customers.csv")),
    delimiter=",",
    has_header=True
)

# JSON Writing to centralized output
workflow.add_node("json_out", JSONWriterNode(),
    file_path=str(get_output_data_path("results.json")),
    indent=2
)
```

## AI/LLM Integration
```python
# LLM Processing
workflow.add_node("llm", LLMAgentNode(),
    provider="openai",
    model="gpt-4",
    temperature=0.7,
    system_prompt="You are a data analyst."
)

# Generate Embeddings
workflow.add_node("embedder", EmbeddingGeneratorNode(),
    provider="openai",
    model="text-embedding-ada-002"
)
```

## API Calls
```python
# Simple HTTP Request
workflow.add_node("api_call", HTTPRequestNode(),
    url="https://api.example.com/data",
    method="GET",
    headers={"Authorization": "Bearer token"}
)

# REST Client with Auth
workflow.add_node("rest", RESTClientNode(),
    base_url="https://api.example.com",
    auth_type="bearer",
    auth_config={"token": "your-token"}
)
```

## Data Transformation
```python
workflow.add_node("transform", DataTransformerNode(),
    operations=[
        {"type": "filter", "condition": "status == 'active'"},
        {"type": "map", "expression": "{'id': id, 'name': name.upper()}"},
        {"type": "sort", "key": "created_at", "reverse": True}
    ]
)
```

## Conditional Logic
```python
# Route based on conditions
workflow.add_node("router", SwitchNode(),
    conditions=[
        {"output": "high", "expression": "value > 100"},
        {"output": "medium", "expression": "value > 50"},
        {"output": "low", "expression": "value <= 50"}
    ]
)

# Connect conditional outputs
workflow.connect("router", "high_handler", mapping={"high": "input"})
workflow.connect("router", "medium_handler", mapping={"medium": "input"})
workflow.connect("router", "low_handler", mapping={"low": "input"})
```

## Custom Python Code
```python
# ✅ CORRECT: Raw statements with input_types
workflow.add_node("custom", PythonCodeNode(
    name="custom",  # Required first parameter
    code='''
# Variables injected directly into namespace
try:
    data = data
except:
    data = []

# Process data
result = []
for item in data:
    if item.get('score', 0) > 0.8:
        result.append({
            'id': item['id'],
            'category': 'high_confidence',
            'score': item['score']
        })

result = {'filtered': result}
''',
    input_types={"data": list}  # Define expected parameters
))

# ❌ WRONG: Function definitions don't execute
workflow.add_node("custom", PythonCodeNode(
    name="custom",
    code='''
def execute(data):  # Returns function object, doesn't execute
    return {'result': data}
'''
))
```

## PythonCodeNode in Cycles
```python
# Complete cycle pattern with all required elements
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
# Use bare except - specific exceptions not available
try:
    value = value
except:
    value = 0

try:
    target = target
except:
    target = 100

# Process and check convergence
new_value = value + (target - value) * 0.1
converged = abs(new_value - target) < 1.0

result = {
    "value": new_value,
    "target": target,  # Pass constants through cycles
    "converged": converged
}
''',
    input_types={"value": float, "target": float}  # ALL parameters
))

# Map ALL parameters (variables + constants)
workflow.connect("processor", "processor",
    mapping={
        "result.value": "value",    # Variable data
        "result.target": "target"   # Constant (still required!)
    },
    cycle=True,
    max_iterations=10,
    convergence_check="converged == True"  # Direct field access
)
```
