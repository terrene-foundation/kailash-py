# Kaizen Composition Validation

DAG cycle detection, schema compatibility checking, and cost estimation for composite agent pipelines.

## Overview

The composition module validates multi-agent pipelines before execution:

- **`validate_dag()`**: Iterative DFS cycle detection with 3-color marking (WHITE/GRAY/BLACK), max 1000 agents
- **`check_schema_compatibility()`**: JSON Schema structural subtyping -- output must provide all required input fields with compatible types
- **`estimate_cost()`**: Historical data cost projection with confidence levels (high/medium/low)

**Source modules**:


---

## DAG Validation

### Basic Usage

```python
from kaizen.composition.dag_validator import validate_dag

# Define agents with their dependencies
agents = [
    {"name": "fetcher", "inputs_from": []},
    {"name": "analyzer", "inputs_from": ["fetcher"]},
    {"name": "reporter", "inputs_from": ["analyzer"]},
]

result = validate_dag(agents)

assert result.is_valid is True
assert result.topological_order == ["fetcher", "analyzer", "reporter"]
assert result.cycles == []
assert result.warnings == []
```

### Cycle Detection

```python
# Cycle: A -> B -> C -> A
agents = [
    {"name": "A", "inputs_from": ["C"]},
    {"name": "B", "inputs_from": ["A"]},
    {"name": "C", "inputs_from": ["B"]},
]

result = validate_dag(agents)

assert result.is_valid is False
assert len(result.cycles) > 0
# result.cycles[0] contains the cycle path, e.g. ["A", "C", "B"]
```

### Missing Dependencies

Missing dependencies (referencing an agent not in the list) produce warnings but do not fail validation.

```python
agents = [
    {"name": "analyzer", "inputs_from": ["external-service"]},
]

result = validate_dag(agents)

assert result.is_valid is True  # Still valid
assert len(result.warnings) == 1
# "Agent 'analyzer' depends on 'external-service' which is not in the agent list"
```

### Guard Rails

```python
from kaizen.composition.models import CompositionError

# Duplicate names raise CompositionError
try:
    validate_dag([
        {"name": "agent-1", "inputs_from": []},
        {"name": "agent-1", "inputs_from": []},  # Duplicate!
    ])
except CompositionError as e:
    print(e)  # "Duplicate agent names: ['agent-1']"
    print(e.details)  # {"duplicates": ["agent-1"]}

# Exceeding max_agents raises CompositionError (DoS prevention)
try:
    validate_dag(agents, max_agents=5)  # Default is 1000
except CompositionError as e:
    print(e)  # "Composition exceeds maximum of 5 agents (got ...)"
```

### Algorithm Details

- Uses **iterative DFS** (not recursive) to avoid Python stack overflow on deep chains up to max_agents=1000
- 3-color marking: WHITE (unvisited), GRAY (in current path), BLACK (fully processed)
- Back-edge to a GRAY node indicates a cycle
- Topological order is the reverse post-order (dependencies come before dependents)
- Deterministic: nodes are processed in sorted order

### Return Type: `ValidationResult`

```python
@dataclass
class ValidationResult:
    is_valid: bool                        # True if no cycles
    topological_order: List[str] = []     # Valid execution order (empty if cycles)
    cycles: List[List[str]] = []          # Detected cycles (each is a list of agent names)
    warnings: List[str] = []             # Non-fatal issues
```

---

## Schema Compatibility

### Basic Usage

```python
from kaizen.composition.schema_compat import check_schema_compatibility

# Output schema from upstream agent
output_schema = {
    "type": "object",
    "properties": {
        "user_id": {"type": "integer"},
        "name": {"type": "string"},
        "email": {"type": "string"},
    },
}

# Input schema expected by downstream agent
input_schema = {
    "type": "object",
    "properties": {
        "user_id": {"type": "integer"},
        "name": {"type": "string"},
    },
    "required": ["user_id", "name"],
}

result = check_schema_compatibility(output_schema, input_schema)

assert result.compatible is True
assert result.mismatches == []
```

### Type Mismatches

```python
output_schema = {
    "type": "object",
    "properties": {
        "count": {"type": "string"},  # String, but downstream expects integer
    },
}

input_schema = {
    "type": "object",
    "properties": {
        "count": {"type": "integer"},
    },
    "required": ["count"],
}

result = check_schema_compatibility(output_schema, input_schema)

assert result.compatible is False
assert len(result.mismatches) == 1
assert result.mismatches[0]["reason"] == "type_mismatch"
assert result.mismatches[0]["field"] == "count"
```

### Missing Required Fields

```python
output_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
    },
}

input_schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"},
    },
    "required": ["name", "email"],
}

result = check_schema_compatibility(output_schema, input_schema)

assert result.compatible is False
assert result.mismatches[0]["reason"] == "missing_required_field"
assert result.mismatches[0]["field"] == "email"
```

### Type Widening

The checker supports structural subtyping with type widening:

- `integer` output is compatible with `number` input (widening)
- `number` output is NOT compatible with `integer` input (narrowing)

```python
# integer -> number is OK (widening)
output = {"type": "object", "properties": {"val": {"type": "integer"}}}
input_ = {"type": "object", "properties": {"val": {"type": "number"}}, "required": ["val"]}
result = check_schema_compatibility(output, input_)
assert result.compatible is True

# number -> integer is NOT OK (narrowing)
output = {"type": "object", "properties": {"val": {"type": "number"}}}
input_ = {"type": "object", "properties": {"val": {"type": "integer"}}, "required": ["val"]}
result = check_schema_compatibility(output, input_)
assert result.compatible is False
```

### Nested Objects and Arrays

The checker recursively validates nested object schemas and array item schemas.

```python
output_schema = {
    "type": "object",
    "properties": {
        "address": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "zip": {"type": "string"},
            },
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}
```

### Optional Fields

Optional fields (defined in `properties` but not in `required`) produce warnings if missing from the output, but do NOT cause incompatibility.

### Return Type: `CompatibilityResult`

```python
@dataclass
class CompatibilityResult:
    compatible: bool                      # True if all required fields match
    mismatches: List[Dict[str, Any]] = [] # Field-level incompatibilities
    warnings: List[str] = []             # Non-fatal issues (optional field missing)
```

Each mismatch dict contains:

- `field`: Dot-separated field path (e.g. `"address.city"`)
- `reason`: `"missing_required_field"` or `"type_mismatch"`
- `detail`: Human-readable description
- `output_type` / `input_type`: (for type mismatches)

---

## Cost Estimation

### Basic Usage

```python
from kaizen.composition.cost_estimator import estimate_cost

# Define the composition (list of agents)
composition = [
    {"name": "fetcher"},
    {"name": "analyzer"},
    {"name": "reporter"},
]

# Historical cost data (from production metrics)
historical_data = {
    "fetcher": {"avg_cost_microdollars": 500, "invocation_count": 150},
    "analyzer": {"avg_cost_microdollars": 2000, "invocation_count": 120},
    "reporter": {"avg_cost_microdollars": 300, "invocation_count": 200},
}

result = estimate_cost(composition, historical_data)

assert result.estimated_total_microdollars == 2800  # 500 + 2000 + 300
assert result.per_agent == {"fetcher": 500, "analyzer": 2000, "reporter": 300}
assert result.confidence == "high"  # All agents have 100+ invocations
assert result.warnings == []
```

### Confidence Levels

Confidence is determined by the **minimum invocation count** across all agents:

| Invocation Count | Confidence | Condition                               |
| ---------------- | ---------- | --------------------------------------- |
| >= 100           | `"high"`   | All agents have 100+ invocations        |
| >= 10            | `"medium"` | All agents have 10+ invocations         |
| < 10             | `"low"`    | Any agent has fewer than 10 invocations |
| (missing agent)  | `"low"`    | Any agent has no historical data at all |

### Missing Historical Data

Agents without historical data get 0 cost and produce a warning.

```python
composition = [{"name": "new-agent"}]
historical_data = {}  # No data

result = estimate_cost(composition, historical_data)

assert result.estimated_total_microdollars == 0
assert result.confidence == "low"
assert len(result.warnings) == 1
# "Agent 'new-agent' has no historical data; cost estimate is 0 microdollars"
```

### Return Type: `CostEstimate`

```python
@dataclass
class CostEstimate:
    estimated_total_microdollars: int = 0       # Total pipeline cost
    per_agent: Dict[str, int] = {}              # Per-agent breakdown
    confidence: str = "low"                     # "high", "medium", or "low"
    warnings: List[str] = []                    # Accuracy-affecting issues
```

---

## Error Hierarchy

All composition errors inherit from a common base:

```python
from kaizen.composition.models import CompositionError, CycleDetectedError, SchemaIncompatibleError

# CompositionError -- base error for all composition failures
#   has .details: Dict[str, Any]
# CycleDetectedError -- cycle found in DAG (inherits CompositionError)
# SchemaIncompatibleError -- schema mismatch (inherits CompositionError)
```

---

## Serialization

All result types support `to_dict()` and `from_dict()`:

```python
# Serialize
result_dict = validation_result.to_dict()
compat_dict = compat_result.to_dict()
cost_dict = cost_estimate.to_dict()

# Deserialize
ValidationResult.from_dict(result_dict)
CompatibilityResult.from_dict(compat_dict)
CostEstimate.from_dict(cost_dict)
```

---

## Critical Rules

- **ALWAYS** validate DAG before executing a composite pipeline
- **ALWAYS** check schema compatibility when connecting agents with typed interfaces
- `validate_dag()` raises `CompositionError` on duplicate names -- callers must handle this
- `max_agents` default is 1000 to prevent DoS -- increase only if needed
- Cost estimation requires historical data -- new agents will have 0 cost and `"low"` confidence
- Type widening is one-directional: `integer` -> `number` is OK, `number` -> `integer` is NOT
- All result types are serializable via `to_dict()` / `from_dict()` for API transport

## References

- **Source**: `kaizen/composition/dag_validator.py`
- **Source**: `kaizen/composition/schema_compat.py`
- **Source**: `kaizen/composition/cost_estimator.py`
- **Source**: `kaizen/composition/models.py`
- **Source**: `kaizen/composition/errors.py`
