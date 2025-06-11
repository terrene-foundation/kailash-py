# Mistake #077: Complex Routing Anti-Pattern

**Date**: 2025-06-11
**Session**: 064
**Severity**: High
**Status**: Active (Session 064 - Finance Workflows)

## Problem Description

Using SwitchNode and complex routing patterns to process lists of items with different conditions, leading to workflow complexity and failures.

## Symptoms

```python
# ❌ WRONG: SwitchNode can't handle lists
risk_assessments = [
    {'customer_id': 'C001', 'decision': 'approved'},
    {'customer_id': 'C002', 'decision': 'declined'},
    {'customer_id': 'C003', 'decision': 'review'}
]

workflow.add_node("router", SwitchNode(
    name="router",
    condition_field="decision",
    condition_type="string"
))

# This fails - SwitchNode expects single item with 'decision' field
workflow.connect("scorer", "router", mapping={"result": "input_data"})
# Error: Required parameter 'input_data' not provided
```

## Root Causes

1. **Misunderstanding SwitchNode**: It's designed for single-item routing, not list processing
2. **Over-engineering**: Creating complex node graphs when simple logic suffices
3. **Workflow Complexity**: Multiple nodes for what should be single processing step
4. **Data Structure Mismatch**: List of items vs single routing decision

## Impact

### Development Issues
- **Complex Debugging**: Multiple nodes and connections to trace
- **Maintenance Burden**: Changes require updating multiple nodes
- **Performance Overhead**: Unnecessary node execution overhead
- **Testing Complexity**: Need to test multiple paths and nodes

### Runtime Issues
- **Execution Failures**: SwitchNode parameter errors
- **Data Loss**: Items may not route correctly
- **Inconsistent State**: Partial processing of lists

## Correct Solution

### Process All Items in Single Node

```python
# ✅ CORRECT: Linear processing in one node
def process_all_decisions(risk_assessments: list) -> dict:
    """Process all decision types in one place."""
    # Group by decision type
    results = {
        'approved': [],
        'declined': [],
        'review': []
    }

    for assessment in risk_assessments:
        decision = assessment.get('decision', 'review')

        if decision == 'approved':
            # Process approved application
            approval_letter = {
                'customer_id': assessment['customer_id'],
                'approved_amount': assessment['approved_amount'],
                'interest_rate': calculate_rate(assessment['risk_score']),
                'terms': '36 months',
                'letter_generated': datetime.now().isoformat()
            }
            results['approved'].append(approval_letter)

        elif decision == 'declined':
            # Process declined application
            decline_letter = {
                'customer_id': assessment['customer_id'],
                'decline_reasons': get_decline_reasons(assessment),
                'reapply_date': (datetime.now() + timedelta(days=180)).isoformat()
            }
            results['declined'].append(decline_letter)

        else:  # review
            # Queue for manual review
            review_item = {
                'customer_id': assessment['customer_id'],
                'risk_score': assessment['risk_score'],
                'priority': 'high' if assessment['requested_amount'] > 50000 else 'medium',
                'assigned_to': 'credit_review_team'
            }
            results['review'].append(review_item)

    # Return comprehensive results
    return {
        'processed': results,
        'statistics': {
            'total': len(risk_assessments),
            'approved': len(results['approved']),
            'declined': len(results['declined']),
            'review': len(results['review'])
        }
    }

# Single node handles all logic
workflow.add_node("decision_processor", PythonCodeNode.from_function(
    func=process_all_decisions,
    name="decision_processor",
    description="Process all decision types"
))

# Simple linear connection
workflow.connect("risk_scorer", "decision_processor",
                mapping={"result": "risk_assessments"})
```

## Alternative Patterns

### Pattern 1: Pre-Filter if Needed
```python
# If you really need separate processing, pre-filter
approved_only = [a for a in assessments if a['decision'] == 'approved']
declined_only = [a for a in assessments if a['decision'] == 'declined']

# Then process each list separately
```

### Pattern 2: Use Dictionary Dispatch
```python
def process_decisions(assessments: list) -> dict:
    """Process using dispatch pattern."""

    # Define processors
    processors = {
        'approved': process_approval,
        'declined': process_decline,
        'review': process_review
    }

    results = {}
    for decision_type, processor in processors.items():
        items = [a for a in assessments if a.get('decision') == decision_type]
        results[decision_type] = processor(items)

    return {'result': results}
```

### Pattern 3: Conditional Logic in Workflow
```python
# For truly different processing needs, use separate workflows
if workflow_type == 'approvals':
    workflow = create_approval_workflow()
elif workflow_type == 'declines':
    workflow = create_decline_workflow()
```

## Benefits of Linear Processing

1. **Simpler Debugging**: All logic in one place
2. **Better Performance**: No routing overhead
3. **Easier Testing**: Test one function, not multiple nodes
4. **Clearer Data Flow**: Linear path is obvious
5. **Flexible Logic**: Easy to add new decision types
6. **Atomic Processing**: All items processed together

## Detection Patterns

### Code Review Checklist
- ❌ Using SwitchNode with list data
- ❌ Multiple processor nodes for list items
- ❌ Complex node graphs for simple logic
- ❌ Trying to route individual list items

### Warning Signs
```python
# Multiple nodes for similar processing
workflow.add_node("approved_processor", ...)
workflow.add_node("declined_processor", ...)
workflow.add_node("review_processor", ...)

# Complex routing logic
workflow.connect("router", "processor1", condition="A")
workflow.connect("router", "processor2", condition="B")
workflow.connect("router", "processor3", condition="C")

# Attempts to split lists
for item in items:
    workflow.route(item)  # Not how it works!
```

## Testing

### Verify Linear Processing
```python
def test_linear_processing():
    """Test that all items are processed correctly."""
    test_data = [
        {'customer_id': 'C001', 'decision': 'approved', 'risk_score': 0.8},
        {'customer_id': 'C002', 'decision': 'declined', 'risk_score': 0.2},
        {'customer_id': 'C003', 'decision': 'review', 'risk_score': 0.5}
    ]

    result = process_all_decisions(test_data)

    assert result['statistics']['total'] == 3
    assert result['statistics']['approved'] == 1
    assert result['statistics']['declined'] == 1
    assert result['statistics']['review'] == 1
    assert len(result['processed']['approved']) == 1
```

## Related Issues

- **Mistake #053**: Confusion between configuration and runtime parameters
- **Mistake #056**: Inconsistent connection APIs
- **Session 064**: Finance workflow implementation patterns

## Resolution Guidelines

1. **Identify List Processing**: Check if data is a list
2. **Use Single Node**: Process all items in one place
3. **Group by Type**: Use dictionaries to organize results
4. **Return Statistics**: Include counts and summaries
5. **Test Thoroughly**: Verify all paths work correctly

## Best Practices

1. **Default to Linear**: Start with simple linear workflows
2. **Avoid Over-Engineering**: Don't create complex graphs unnecessarily
3. **Use Functions**: Leverage .from_function() for complex logic
4. **Think in Batches**: Process collections, not individuals
5. **Document Flow**: Make data flow obvious

---

**Key Learning**: When processing lists of items with different types, use conditional logic within a single node rather than complex routing patterns. This results in simpler, more maintainable, and more performant workflows.
