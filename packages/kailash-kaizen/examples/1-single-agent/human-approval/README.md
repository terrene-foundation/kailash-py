# Approval Agent

Human-in-the-loop approval for critical decisions using `HumanInLoopStrategy`.

## Overview

This example demonstrates how to build an approval agent that requests human oversight before executing critical operations, providing audit trails and decision transparency.

## Features

- **Human approval checkpoints**: Request approval before returning results
- **Custom approval callbacks**: CLI prompts, web forms, webhooks
- **Approval history tracking**: Complete audit trail with feedback
- **Built on BaseAgent**: Enterprise features (logging, error handling, performance tracking)

## Use Cases

1. **Financial Transactions**: Approve payments, transfers, refunds
2. **Content Moderation**: Review before publishing content
3. **Critical Operations**: Database changes, user permissions, deletions
4. **Quality Control**: Human review of AI-generated outputs

## Quick Start

### Auto-Approval (Test Mode)

```python
import asyncio
from workflow import ApprovalAgent, ApprovalConfig

# Default auto-approval for testing
config = ApprovalConfig(llm_provider="openai")
agent = ApprovalAgent(config)

# Decision automatically approved
result = asyncio.run(agent.decide_async("Process payment"))
print(f"Approved: {result['_human_approved']}")
```

### Custom Approval Callback

```python
# Define approval callback
def approve_callback(result):
    print(f"Review decision: {result.get('decision')}")
    response = input("Approve? (y/n): ")
    approved = response.lower() == 'y'
    feedback = "Approved by user" if approved else "Rejected by user"
    return approved, feedback

config = ApprovalConfig(approval_callback=approve_callback)
agent = ApprovalAgent(config)

# Requests human approval
try:
    result = asyncio.run(agent.decide_async("Transfer $1000"))
    print("Transaction approved")
except RuntimeError as e:
    print(f"Transaction rejected: {e}")
```

## Configuration Options

```python
@dataclass
class ApprovalConfig:
    llm_provider: str = "openai"         # LLM provider
    model: str = "gpt-4"                 # Model name
    temperature: float = 0.3             # Generation temperature
    max_tokens: int = 300                # Max response length
    approval_callback: Optional[Callable] = None  # Approval function
```

### Approval Callback Signature

```python
def approval_callback(result: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Args:
        result: Execution result to approve

    Returns:
        Tuple of (approved: bool, feedback: str)
    """
    # Review result
    approved = decide_approval(result)
    feedback = "Reason for decision"
    return approved, feedback
```

## Architecture

```
ApprovalAgent (BaseAgent)
    ├── HumanInLoopStrategy (approval checkpoint)
    │   ├── execute() → requests approval
    │   ├── approval_callback() → human decision
    │   └── approval_history → audit trail
    ├── DecisionSignature (I/O structure)
    │   ├── Input: prompt
    │   └── Output: decision
    └── BaseAgent Features
        ├── LoggingMixin
        ├── PerformanceMixin
        └── ErrorHandlingMixin
```

## HumanInLoopStrategy API

### `execute(agent, inputs)` → Dict[str, Any]

Execute with human approval checkpoint.

```python
result = await strategy.execute(agent, {"prompt": "test"})
```

**Returns** (if approved):
```python
{
    "decision": "...",
    "_human_approved": True,
    "_approval_feedback": "Approved by user"
}
```

**Raises**: `RuntimeError` if human rejects

### `get_approval_history()` → List[Dict[str, Any]]

Get complete approval history.

```python
history = strategy.get_approval_history()
# [{"result": {...}, "approved": True, "feedback": "..."}]
```

## Performance

### Approval Flow

1. **Agent executes** normally
2. **Request approval** via callback
3. **If approved**: Return result with metadata
4. **If rejected**: Raise RuntimeError with feedback
5. **Record decision** in approval history

### Synchronous Approval

- Execution blocks until human decision
- Suitable for critical operations requiring immediate review
- Consider async workflows for non-blocking approval

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/examples/test_human_approval.py -v
```

Tests cover:
- Agent initialization with HumanInLoopStrategy
- Auto-approval (test mode)
- Custom approval callbacks
- Rejection handling
- Approval history tracking
- Integration with BaseAgent

## Demo

Run the example:

```bash
cd examples/1-single-agent/human-approval
python workflow.py
```

Output:
```
Auto-Approval Demo (Test Mode)
==================================================
Note: Auto-approval enabled for testing

1. Decision: Process payment of $100
   Recommendation: Placeholder result for decision
   Approved: True
   Feedback: Auto-approved (test mode)

2. Decision: Publish blog post
   Recommendation: Placeholder result for decision
   Approved: True
   Feedback: Auto-approved (test mode)

3. Decision: Grant admin access
   Recommendation: Placeholder result for decision
   Approved: True
   Feedback: Auto-approved (test mode)

Custom Approval Demo
==================================================
Pre-configured approvals:
  ✓ Approve: Process payment
  ✗ Reject: Delete database

1. Decision: Process payment
   Status: ✓ Approved
   Feedback: Approved by user

2. Decision: Delete database
   Status: ✗ Rejected
   Reason: Human rejected result: Rejected by user

Approval History Demo
==================================================
Total decisions: 3

1. Approved: True
   Feedback: Auto-approved (test mode)
   Result: Placeholder result for decision

2. Approved: True
   Feedback: Auto-approved (test mode)
   Result: Placeholder result for decision

3. Approved: True
   Feedback: Auto-approved (test mode)
   Result: Placeholder result for decision
```

## Integration with Core SDK

Convert to workflow node:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

# Create agent
agent = ApprovalAgent(config)

# Convert to workflow node
workflow = WorkflowBuilder()
workflow.add_node_instance(agent)

# Execute via Core SDK
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Use Case Examples

### 1. Financial Transaction Approval

```python
def financial_callback(result):
    amount = extract_amount(result)
    if amount > 10000:
        # Require manager approval
        return get_manager_approval(result)
    else:
        # Auto-approve small amounts
        return True, f"Auto-approved (under $10k)"

config = ApprovalConfig(approval_callback=financial_callback)
agent = ApprovalAgent(config)

result = await agent.decide_async("Transfer $50,000")
```

### 2. Content Moderation

```python
def moderation_callback(result):
    content = result.get("decision")
    if contains_sensitive_content(content):
        # Require human review
        return request_human_review(content)
    else:
        # Auto-publish
        return True, "Content safe for publication"

config = ApprovalConfig(approval_callback=moderation_callback)
agent = ApprovalAgent(config)

result = await agent.decide_async("Publish: [content]")
```

### 3. Webhook-based Approval

```python
import requests

def webhook_callback(result):
    # Send to approval system
    response = requests.post(
        "https://approval-system.com/review",
        json={"result": result}
    )

    # Wait for decision
    decision = response.json()
    return decision["approved"], decision["feedback"]

config = ApprovalConfig(approval_callback=webhook_callback)
```

## Next Steps

1. **Implement async approval** for non-blocking workflows
2. **Add approval levels** (user → manager → admin)
3. **Integrate with ticketing systems** (JIRA, ServiceNow)
4. **Build approval dashboards** for oversight teams

## Related Examples

- `streaming-chat/` - Real-time token streaming
- `batch-processing/` - Concurrent batch processing
- `resilient-fallback/` - Multi-strategy fallback
- `simple-qa/` - Basic single-shot processing

## References

- `src/kaizen/strategies/human_in_loop.py` - HumanInLoopStrategy implementation
- `tests/unit/strategies/test_human_in_loop_strategy.py` - Strategy tests
- ADR-006: Agent Base Architecture
