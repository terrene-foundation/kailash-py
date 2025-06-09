# Mistake #053: Confusion Between Configuration and Runtime Parameters

## Problem
Users frequently confused which parameters should be passed as configuration (when adding nodes) vs runtime parameters (data flowing through connections).

### Bad Example
```python
# BAD - Passing runtime data as configuration
workflow.add_node("processor", ProcessorNode(),
    data=[1, 2, 3],  # WRONG: data should flow through connections
    text="Process this"  # WRONG: runtime data as config
)

# GOOD - Configuration vs runtime separation
# Configuration: HOW the node operates
workflow.add_node("reader", CSVReaderNode(),
    file_path="data.csv",  # Config: WHERE to read
    delimiter=","          # Config: HOW to parse
)
workflow.add_node("processor", ProcessorNode(),
    chunk_size=1000       # Config: HOW to process
)
# Runtime: WHAT flows through connections
workflow.connect("reader", "processor", mapping={"data": "input_data"})

```

## Solution
Added comprehensive documentation in validation-guide.md explaining:
- Configuration parameters = HOW the node works (file paths, API keys, models, settings)
- Runtime parameters = WHAT the node processes (data, text, documents)
- Simple rule: "If it's data to be processed, it flows through connections"
- **Critical clarification**: The `get_parameters()` method defines ALL parameters a node can accept
- The same parameter can be configuration OR runtime depending on usage
- At execution, runtime inputs override configuration defaults

**Key Learning**: The distinction is fundamental to the node-based architecture:
- Nodes are configured once with static settings
- Data flows dynamically between nodes at runtime
- This separation enables reusable, composable workflows

## Impact
- Workflow validation errors about missing inputs
- Confusion about why data isn't flowing correctly
- Incorrect workflow patterns that don't follow the node-based architecture

## Fixed In
Session 40 - Added comprehensive guidance to validation-guide.md

## Related Issues
#49 (Missing Data Source Nodes) - same root misunderstanding

## Categories
api-design, configuration

---
