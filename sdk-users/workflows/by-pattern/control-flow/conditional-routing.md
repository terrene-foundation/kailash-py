# Conditional Routing Patterns

**Smart decision-making in workflows** - Route data and control flow based on dynamic conditions.

## 📋 Pattern Overview

Conditional routing allows workflows to make intelligent decisions based on data, implementing business logic directly in the workflow structure. This pattern is fundamental for creating adaptive, context-aware automation.

## 🚀 Working Examples

### Basic Conditional Routing
**Script**: [scripts/conditional_routing_basic.py](scripts/conditional_routing_basic.py)

```python
from kailash import Workflow
from kailash.nodes.logic import SwitchNode
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime

def create_basic_routing_workflow():
    """Customer segmentation based on purchase value."""
    workflow = Workflow("customer_routing", "Segment customers by value")

    # Read customer data
    workflow.add_node("reader", CSVReaderNode())

    # Route based on customer lifetime value
    value_router = SwitchNode(
        id="value_router",
        condition="lifetime_value > 10000"  # Premium threshold
    )
    workflow.add_node("value_router", value_router)

    # Premium customer processing
    premium_processor = DataTransformer(
        id="premium_processor",
        transformations=[
            "lambda x: {**x, 'segment': 'premium', 'benefits': ['free_shipping', 'priority_support', 'exclusive_offers']}"
        ]
    )
    workflow.add_node("premium_processor", premium_processor)

    # Standard customer processing
    standard_processor = DataTransformer(
        id="standard_processor",
        transformations=[
            "lambda x: {**x, 'segment': 'standard', 'benefits': ['newsletter', 'seasonal_offers']}"
        ]
    )
    workflow.add_node("standard_processor", standard_processor)

    # Connect routing logic
    workflow.add_connection("reader", "data", "value_router", "data")
    workflow.add_connection("value_router", "true_output", "premium_processor", "data")
    workflow.add_connection("value_router", "false_output", "standard_processor", "data")

    return workflow

```

### Multi-Way Routing with Business Rules
**Script**: [scripts/conditional_routing_advanced.py](scripts/conditional_routing_advanced.py)

```python
from kailash.nodes.code import PythonCodeNode

def create_multi_way_routing():
    """Complex routing with multiple conditions and business rules."""
    workflow = Workflow("order_routing", "Route orders by multiple criteria")

    # Initial order classification
    order_classifier = PythonCodeNode(
        name="order_classifier",
        code='''
# Classify orders based on multiple criteria
classified_orders = []

for order in orders:
    amount = order.get('total_amount', 0)
    is_prime = order.get('prime_member', False)
    item_count = order.get('item_count', 0)
    destination = order.get('shipping_country', 'US')

    # Multi-dimensional classification
    order_class = {
        'order_id': order['order_id'],
        'original': order,
        'priority': 'standard',
        'shipping_method': 'ground',
        'processing_queue': 'normal'
    }

    # Priority rules
    if amount > 500 and is_prime:
        order_class.update({
            'priority': 'urgent',
            'shipping_method': 'express',
            'processing_queue': 'priority'
        })
    elif amount > 200 or (is_prime and item_count < 5):
        order_class.update({
            'priority': 'high',
            'shipping_method': 'expedited',
            'processing_queue': 'fast'
        })
    elif destination != 'US':
        order_class.update({
            'priority': 'international',
            'shipping_method': 'international_standard',
            'processing_queue': 'international'
        })

    classified_orders.append(order_class)

result = {
    'classified_orders': classified_orders,
    'routing_summary': {
        'urgent': sum(1 for o in classified_orders if o['priority'] == 'urgent'),
        'high': sum(1 for o in classified_orders if o['priority'] == 'high'),
        'standard': sum(1 for o in classified_orders if o['priority'] == 'standard'),
        'international': sum(1 for o in classified_orders if o['priority'] == 'international')
    }
}
'''
    )
    workflow.add_node("order_classifier", order_classifier)

    # Route to different processing pipelines
    priority_router = SwitchNode(
        id="priority_router",
        condition="priority == 'urgent'"
    )
    workflow.add_node("priority_router", priority_router)

    # Urgent order fast-track
    urgent_processor = PythonCodeNode(
        name="urgent_processor",
        code='''
# Fast-track processing for urgent orders
processed_orders = []

for order in urgent_orders:
    processed = {
        **order['original'],
        'processed_at': datetime.now().isoformat(),
        'warehouse': 'nearest_available',
        'packing_priority': 1,
        'estimated_delivery': '1-2 business days',
        'tracking_enabled': True,
        'notifications': ['sms', 'email', 'app']
    }
    processed_orders.append(processed)

result = {'processed_urgent_orders': processed_orders}
'''
    )
    workflow.add_node("urgent_processor", urgent_processor)

    return workflow

```

### Conditional Routing with Fallbacks
**Script**: [scripts/conditional_routing_resilient.py](scripts/conditional_routing_resilient.py)

```python
def create_resilient_routing():
    """Routing with error handling and fallback paths."""
    workflow = Workflow("payment_routing", "Process payments with fallbacks")

    # Try primary payment processor
    primary_processor = RestClientNode(
        id="primary_processor",
        url="https://primary-payment.api/process",
        timeout=5000
    )
    workflow.add_node("primary_processor", primary_processor)

    # Check if primary succeeded
    primary_check = SwitchNode(
        id="primary_check",
        condition="status_code == 200"
    )
    workflow.add_node("primary_check", primary_check)

    # Fallback to secondary processor
    secondary_processor = RestClientNode(
        id="secondary_processor",
        url="https://backup-payment.api/process",
        timeout=8000
    )
    workflow.add_node("secondary_processor", secondary_processor)

    # Check secondary result
    secondary_check = SwitchNode(
        id="secondary_check",
        condition="status_code == 200"
    )
    workflow.add_node("secondary_check", secondary_check)

    # Manual processing queue for failures
    manual_queue = PythonCodeNode(
        name="manual_queue",
        code='''
# Queue failed payments for manual processing
import json
from datetime import datetime

failed_payment = {
    'payment_id': payment_data.get('id'),
    'amount': payment_data.get('amount'),
    'attempts': [
        {'processor': 'primary', 'status': primary_result.get('status_code', 'failed')},
        {'processor': 'secondary', 'status': secondary_result.get('status_code', 'failed')}
    ],
    'queued_at': datetime.now().isoformat(),
    'queue_priority': 'high' if payment_data.get('amount', 0) > 1000 else 'normal',
    'customer_notified': False
}

# In production, this would write to a queue service
result = {
    'manual_queue_entry': failed_payment,
    'queue_status': 'pending_review',
    'estimated_resolution': '4-6 hours'
}
'''
    )
    workflow.add_node("manual_queue", manual_queue)

    # Connect with fallback logic
    workflow.add_connection("payment_input", "data", "primary_processor", "payment_data")
    workflow.add_connection("primary_processor", "response", "primary_check", "data")
    workflow.add_connection("primary_check", "true_output", "payment_success", "data")
    workflow.add_connection("primary_check", "false_output", "secondary_processor", "payment_data")
    workflow.add_connection("secondary_processor", "response", "secondary_check", "data")
    workflow.add_connection("secondary_check", "true_output", "payment_success", "data")
    workflow.add_connection("secondary_check", "false_output", "manual_queue", "data")

    return workflow

```

## 🎯 Common Use Cases

### 1. Customer Journey Routing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Route customers through different experiences
journey_router = SwitchNode(
    condition="customer_segment == 'vip' and visit_count > 5"
)
workflow.add_node("journey_router", journey_router)

# VIP experience
workflow.add_connection("journey_router", "true_output", "personalized_homepage", "data")

# Standard experience
workflow.add_connection("journey_router", "false_output", "default_homepage", "data")

```

### 2. Data Quality Gating
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Only process high-quality data
quality_gate = SwitchNode(
    condition="data_quality_score >= 0.85"
)
workflow.add_node("quality_gate", quality_gate)

# Good data continues
workflow.add_connection("quality_gate", "true_output", "ml_processing", "data")

# Poor data goes to cleaning
workflow.add_connection("quality_gate", "false_output", "data_cleaning", "data")

```

### 3. Approval Workflows
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Multi-level approval based on amount
approval_router = SwitchNode(
    condition="expense_amount > 10000"
)
workflow.add_node("approval_router", approval_router)

# High amounts need VP approval
workflow.add_connection("approval_router", "true_output", "vp_approval_queue", "data")

# Standard amounts need manager approval
workflow.add_connection("approval_router", "false_output", "manager_approval_queue", "data")

```

### 4. A/B Testing
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# Route users to different variants
ab_test_router = SwitchNode(
    condition="hash(user_id) % 100 < 20"  # 20% to variant B
)
workflow.add_node("ab_test_router", ab_test_router)

workflow.add_connection("ab_test_router", "true_output", "variant_b_experience", "data")
workflow.add_connection("ab_test_router", "false_output", "variant_a_experience", "data")

```

## 📊 Best Practices

### 1. **Clear Conditions**
```python
# GOOD: Explicit, testable condition
condition="order_total > 100 and customer_type == 'premium'"

# BAD: Complex, hard to test
condition="(a > b and c < d) or (e == f and g != h) or i > j"

```

### 2. **Always Handle Both Paths**
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# GOOD: Both outputs connected
workflow.add_connection("router", "true_output", "path_a", "data")
workflow.add_connection("router", "false_output", "path_b", "data")

# BAD: Missing false path - data gets lost!
workflow.add_connection("router", "true_output", "path_a", "data")
# No false_output connection

```

### 3. **Avoid Deep Nesting**
```python
# GOOD: Flattened multi-condition routing
conditions = [
    ("is_premium and high_value", "premium_path"),
    ("is_premium and not high_value", "standard_premium_path"),
    ("not is_premium and high_value", "upgrade_path"),
    ("not is_premium and not high_value", "basic_path")
]

# BAD: Deeply nested switches
if is_premium:
    if high_value:
        # premium path
    else:
        # standard premium
else:
    if high_value:
        # upgrade path
    else:
        # basic path

```

### 4. **Document Routing Logic**
```python
# GOOD: Clear documentation
value_router = SwitchNode(
    id="customer_value_router",
    condition="lifetime_value > 10000",
    description="Routes customers based on lifetime value threshold. Premium: >$10k"
)

```

## 🔗 Related Examples

- **Examples Directory**: `/examples/workflow_examples/workflow_conditional_routing.py`
- **Advanced Routing**: `/examples/workflow_examples/workflow_switch.py`
- **With Error Handling**: See [error-handling.md](error-handling.md)
- **In Parallel Flows**: See [parallel-execution.md](parallel-execution.md)

## ⚠️ Common Pitfalls

1. **Missing Default Handling**
   - Always connect both true and false outputs
   - Consider adding a default/catch-all path

2. **Complex Conditions**
   - Break complex logic into multiple switches
   - Use PythonCodeNode for very complex routing

3. **State Dependencies**
   - Ensure routing conditions don't depend on mutable state
   - Pass all needed data explicitly

4. **Performance Issues**
   - Avoid expensive computations in conditions
   - Pre-calculate routing keys when possible

---

*Conditional routing is the foundation of intelligent workflow automation. Master these patterns to build adaptive, business-aware workflows.*
