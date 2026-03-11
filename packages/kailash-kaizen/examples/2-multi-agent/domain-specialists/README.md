# Domain-Specialists Multi-Agent Pattern

## Overview

The Domain-Specialists pattern demonstrates expert routing where a router analyzes questions, routes them to appropriate domain experts (Python, Database, Security), and an integrator synthesizes multi-domain answers.

## Pattern Architecture

```
Question
     |
     v
RouterAgent (analyzes domain)
     |
     v (single domain)
Specialist (Python/Database/Security)
     |
     v (writes answer to SharedMemoryPool)
SharedMemoryPool ["answer", domain_name]
     |
     v (multi-domain path)
Multiple Specialists
     |
     v (all write answers)
IntegratorAgent (reads + synthesizes)
     |
     v (writes to SharedMemoryPool)
SharedMemoryPool ["answer", "integrated"]
     |
     v
Final Answer
```

## Quick Start

```python
from workflow import domain_specialists_workflow

# Single domain question
result = domain_specialists_workflow(
    question="What are Python decorators?"
)

# Multi-domain question
result = domain_specialists_workflow(
    question="How do I securely connect Python to a PostgreSQL database?"
)

print(f"Answer: {result['answer']}")
```

## Agents

### RouterAgent
Analyzes questions to identify domains (python/database/security) and routes to appropriate specialists.

### PythonExpertAgent
Provides Python programming expertise with confidence scores and references.

### DatabaseExpertAgent
Provides database design and query expertise.

### SecurityExpertAgent
Provides security and authentication expertise.

### IntegratorAgent
Synthesizes multi-domain answers when multiple specialists are involved.

## Test Coverage

18 comprehensive tests covering all aspects of the pattern.

Run tests:
```bash
pytest tests/unit/examples/test_domain_specialists.py -v
```

All tests passing!
