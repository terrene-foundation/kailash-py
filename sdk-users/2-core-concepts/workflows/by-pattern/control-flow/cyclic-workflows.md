# ⚠️ CYCLIC WORKFLOWS - PLANNED FEATURE

> **STATUS**: This feature is planned but NOT YET IMPLEMENTED in the current SDK version (v0.9.31).
>
> Cyclic workflows (feedback loops, iterative processing) are under active development.
> The CycleBuilder API shown in this documentation represents the planned interface.
>
> **Current Alternatives**:
> - Recursive workflows with manual iteration
> - External loop control with sequential workflow executions
> - State machines with conditional routing (SwitchNode)
> - Python loops around workflow execution

---

# Cyclic Workflow Patterns (PLANNED)

**Iterative processes and feedback loops** - Build workflows that repeat until conditions are met.

## 📋 Pattern Overview (Future Capability)

Cyclic workflows will enable iterative processing, optimization loops, and state-based flows where nodes can receive feedback from downstream processes. This pattern will be essential for machine learning training, iterative refinement, retry mechanisms, and any process that requires convergence or repeated attempts.

## 🚀 Working Examples

### Basic Retry Pattern with Cycles
**Script**: [scripts/cyclic_retry_pattern.py](scripts/cyclic_retry_pattern.py)

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.cycle_builder import CycleBuilder
from kailash.nodes.api import RestClientNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.code import PythonCodeNode

def create_retry_workflow():
    """API call with exponential backoff retry."""
    # Create cycle-aware workflow
    cycle_builder = CycleBuilder()
    workflow = cycle_builder.create_workflow(
        "api_retry_workflow",
        "Retry API calls with exponential backoff"
    )

    # Track retry state
    retry_tracker = PythonCodeNode(
        name="retry_tracker",
        code='''
# Initialize or update retry state
if not hasattr(self, '_retry_count'):
    self._retry_count = 0
    self._last_wait = 1

retry_state = {
    'attempt': self._retry_count + 1,
    'wait_seconds': self._last_wait,
    'max_retries': 5
}

# Exponential backoff
if self._retry_count > 0:
    self._last_wait = min(self._last_wait * 2, 60)  # Cap at 60 seconds

self._retry_count += 1

result = retry_state
'''
    )
    cycle_builder.add_cycle_node("retry_tracker", retry_tracker)

    # API call attempt
    api_caller = RestClientNode(
        id="api_caller",
        url="https://flaky-api.example.com/data",
        timeout=5000
    )
    cycle_builder.add_cycle_node("api_caller", api_caller)

    # Check if successful or should retry
    retry_decider = SwitchNode(
        id="retry_decider",
        condition="status_code == 200 or attempt >= max_retries"
    )
    cycle_builder.add_cycle_node("retry_decider", retry_decider)

    # Wait before retry
    wait_handler = PythonCodeNode(
        name="wait_handler",
        code='''
import time

# Wait with exponential backoff
wait_time = retry_state.get('wait_seconds', 1)
print(f"Waiting {wait_time} seconds before retry...")
time.sleep(wait_time)

result = {'waited': wait_time, 'ready_to_retry': True}
'''
    )
    cycle_builder.add_cycle_node("wait_handler", wait_handler)

    # Connect the retry cycle
    cycle_builder.connect_cycle_nodes("retry_tracker", "api_caller",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("api_caller", "retry_decider",
                                     # mapping removed)

    # Exit on success or max retries
    cycle_builder.set_cycle_exit_condition("retry_decider", exit_on="true_output")

    # Continue cycle on failure
    cycle_builder.connect_cycle_nodes("retry_decider", "wait_handler",
                                     output_key="false_output",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("wait_handler", "retry_tracker",
                                     # mapping removed)

    return workflow

```

### Optimization Loop Pattern
**Script**: [scripts/cyclic_optimization.py](scripts/cyclic_optimization.py)

```python
def create_optimization_workflow():
    """Iterative optimization with convergence checking."""
    cycle_builder = CycleBuilder()
    workflow = cycle_builder.create_workflow(
        "optimization_workflow",
        "Gradient descent optimization"
    )

    # Initialize optimization state
    initializer = PythonCodeNode(
        name="initializer",
        code='''
import numpy as np

# Initialize or get current state
if 'parameters' not in globals():
    # First iteration - initialize
    parameters = np.random.randn(10)  # 10-dimensional optimization
    best_loss = float('inf')
    learning_rate = 0.01
    iteration = 0
else:
    # Subsequent iterations - use cycle state
    parameters = cycle_state.get('parameters')
    best_loss = cycle_state.get('best_loss')
    learning_rate = cycle_state.get('learning_rate')
    iteration = cycle_state.get('iteration', 0) + 1

result = {
    'parameters': parameters.tolist(),
    'best_loss': best_loss,
    'learning_rate': learning_rate,
    'iteration': iteration
}
'''
    )
    cycle_builder.add_cycle_node("initializer", initializer)

    # Compute gradient and loss
    gradient_computer = PythonCodeNode(
        name="gradient_computer",
        code='''

# Simulated loss function (quadratic)
params = np.array(current_state['parameters'])
target = np.ones_like(params) * 5  # Optimal point at [5,5,5,...]

# Compute loss and gradient
loss = np.sum((params - target) ** 2)
gradient = 2 * (params - target)

# Add noise to simulate stochastic gradient
gradient += np.random.randn(*gradient.shape) * 0.1

result = {
    'loss': float(loss),
    'gradient': gradient.tolist(),
    'parameters': params.tolist()
}
'''
    )
    cycle_builder.add_cycle_node("gradient_computer", gradient_computer)

    # Update parameters
    parameter_updater = PythonCodeNode(
        name="parameter_updater",
        code='''

# Update parameters using gradient descent
params = np.array(gradient_result['parameters'])
gradient = np.array(gradient_result['gradient'])
learning_rate = current_state['learning_rate']

# Update with momentum
if 'momentum' in current_state:
    momentum = np.array(current_state['momentum'])
    momentum = 0.9 * momentum + learning_rate * gradient
else:
    momentum = learning_rate * gradient

new_params = params - momentum

# Adaptive learning rate
if gradient_result['loss'] > current_state['best_loss']:
    learning_rate *= 0.9  # Reduce if not improving
else:
    learning_rate *= 1.01  # Increase if improving

result = {
    'parameters': new_params.tolist(),
    'momentum': momentum.tolist(),
    'learning_rate': min(learning_rate, 0.1),  # Cap learning rate
    'loss': gradient_result['loss'],
    'best_loss': min(gradient_result['loss'], current_state['best_loss']),
    'iteration': current_state['iteration']
}
'''
    )
    cycle_builder.add_cycle_node("parameter_updater", parameter_updater)

    # Check convergence
    convergence_checker = SwitchNode(
        id="convergence_checker",
        condition="abs(loss - best_loss) < 0.001 or iteration >= 1000"
    )
    cycle_builder.add_cycle_node("convergence_checker", convergence_checker)

    # Connect optimization cycle
    cycle_builder.connect_cycle_nodes("initializer", "gradient_computer",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("gradient_computer", "parameter_updater",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("parameter_updater", "convergence_checker",
                                     # mapping removed)

    # Exit when converged
    cycle_builder.set_cycle_exit_condition("convergence_checker", exit_on="true_output")

    # Continue optimization if not converged
    cycle_builder.connect_cycle_nodes("convergence_checker", "initializer",
                                     output_key="false_output",
                                     # mapping removed)

    # Set maximum iterations
    cycle_builder.set_max_iterations(1000)

    return workflow

```

### State Machine Pattern
**Script**: [scripts/cyclic_state_machine.py](scripts/cyclic_state_machine.py)

```python
def create_state_machine_workflow():
    """Order processing state machine with cycles."""
    cycle_builder = CycleBuilder()
    workflow = cycle_builder.create_workflow(
        "order_state_machine",
        "Order processing with state transitions"
    )

    # State manager
    state_manager = PythonCodeNode(
        name="state_manager",
        code='''
# Define state transitions
state_transitions = {
    'new': ['validated', 'rejected'],
    'validated': ['payment_pending', 'cancelled'],
    'payment_pending': ['paid', 'payment_failed', 'cancelled'],
    'payment_failed': ['payment_pending', 'cancelled'],  # Can retry
    'paid': ['processing', 'refunded'],
    'processing': ['shipped', 'failed'],
    'shipped': ['delivered', 'returned'],
    'delivered': ['completed'],
    'returned': ['refunded'],
    'refunded': ['completed'],
    'failed': ['cancelled'],
    'rejected': ['completed'],
    'cancelled': ['completed'],
    'completed': []  # Terminal state
}

# Get current state
current_state = order.get('state', 'new')
order_id = order.get('order_id')

# Check if terminal state
is_terminal = current_state == 'completed'

result = {
    'order_id': order_id,
    'current_state': current_state,
    'possible_transitions': state_transitions.get(current_state, []),
    'is_terminal': is_terminal,
    'order_data': order
}
'''
    )
    cycle_builder.add_cycle_node("state_manager", state_manager)

    # State processor - handles business logic for each state
    state_processor = PythonCodeNode(
        name="state_processor",
        code='''
import random
from datetime import datetime

# Process based on current state
order = state_info['order_data']
current_state = state_info['current_state']
new_state = current_state
state_metadata = {}

if current_state == 'new':
    # Validate order
    is_valid = order.get('total_amount', 0) > 0 and order.get('items', [])
    new_state = 'validated' if is_valid else 'rejected'
    state_metadata['validation_time'] = datetime.now().isoformat()

elif current_state == 'validated':
    # Initiate payment
    new_state = 'payment_pending'
    state_metadata['payment_initiated'] = datetime.now().isoformat()

elif current_state == 'payment_pending':
    # Simulate payment processing
    payment_success = random.random() > 0.1  # 90% success rate
    new_state = 'paid' if payment_success else 'payment_failed'
    state_metadata['payment_attempt'] = datetime.now().isoformat()

    if payment_success:
        state_metadata['payment_id'] = f"PAY-{random.randint(1000, 9999)}"

elif current_state == 'paid':
    # Start order processing
    new_state = 'processing'
    state_metadata['processing_started'] = datetime.now().isoformat()

elif current_state == 'processing':
    # Simulate processing completion
    processing_success = random.random() > 0.05  # 95% success rate
    new_state = 'shipped' if processing_success else 'failed'
    state_metadata['processed_at'] = datetime.now().isoformat()

    if processing_success:
        state_metadata['tracking_number'] = f"TRACK-{random.randint(100000, 999999)}"

elif current_state == 'shipped':
    # Simulate delivery
    delivered = random.random() > 0.1  # 90% delivery rate
    new_state = 'delivered' if delivered else 'returned'
    state_metadata['shipping_update'] = datetime.now().isoformat()

elif current_state in ['delivered', 'returned', 'failed', 'rejected', 'cancelled']:
    # Move to completed
    new_state = 'completed'
    state_metadata['completed_at'] = datetime.now().isoformat()

# Update order with new state
updated_order = {
    **order,
    'state': new_state,
    'previous_state': current_state,
    'state_history': order.get('state_history', []) + [{
        'from': current_state,
        'to': new_state,
        'timestamp': datetime.now().isoformat(),
        'metadata': state_metadata
    }]
}

result = {
    'updated_order': updated_order,
    'state_changed': new_state != current_state,
    'new_state': new_state
}
'''
    )
    cycle_builder.add_cycle_node("state_processor", state_processor)

    # Terminal state checker
    terminal_checker = SwitchNode(
        id="terminal_checker",
        condition="new_state == 'completed'"
    )
    cycle_builder.add_cycle_node("terminal_checker", terminal_checker)

    # Connect state machine cycle
    cycle_builder.connect_cycle_nodes("state_manager", "state_processor",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("state_processor", "terminal_checker",
                                     # mapping removed)

    # Exit when terminal state reached
    cycle_builder.set_cycle_exit_condition("terminal_checker", exit_on="true_output")

    # Continue cycle if not terminal
    cycle_builder.connect_cycle_nodes("terminal_checker", "state_manager",
                                     output_key="false_output",
                                     # mapping removed)

    # Safety limit
    cycle_builder.set_max_iterations(20)

    return workflow

```

### Feedback Loop with Learning
**Script**: [scripts/cyclic_feedback_learning.py](scripts/cyclic_feedback_learning.py)

```python
def create_feedback_learning_workflow():
    """Adaptive system that learns from feedback."""
    cycle_builder = CycleBuilder()
    workflow = cycle_builder.create_workflow(
        "feedback_learning",
        "Adaptive recommendation system"
    )

    # Recommendation generator
    recommender = PythonCodeNode(
        name="recommender",
        code='''
import numpy as np

# Initialize or get model weights
if 'model_weights' not in globals():
    model_weights = np.random.randn(10, 5) * 0.1  # 10 features, 5 items
    user_feedback_history = []
    iteration = 0
else:
    model_weights = np.array(learning_state['model_weights'])
    user_feedback_history = learning_state['feedback_history']
    iteration = learning_state['iteration'] + 1

# Get user features (simulated)
user_features = np.random.randn(10)

# Generate recommendations
scores = user_features @ model_weights
recommendations = np.argsort(scores)[::-1][:3]  # Top 3 items

result = {
    'recommendations': recommendations.tolist(),
    'scores': scores.tolist(),
    'user_features': user_features.tolist(),
    'model_weights': model_weights.tolist(),
    'iteration': iteration
}
'''
    )
    cycle_builder.add_cycle_node("recommender", recommender)

    # Simulate user interaction and feedback
    feedback_collector = PythonCodeNode(
        name="feedback_collector",
        code='''
import random

# Simulate user feedback on recommendations
recommendations = recommendation_data['recommendations']
feedback = []

for item_id in recommendations:
    # Simulate click/no-click (binary feedback)
    # Higher scored items more likely to be clicked
    score = recommendation_data['scores'][item_id]
    click_probability = 1 / (1 + np.exp(-score))  # Sigmoid
    clicked = random.random() < click_probability

    feedback.append({
        'item_id': item_id,
        'clicked': clicked,
        'score': score,
        'probability': click_probability
    })

result = {
    'feedback': feedback,
    'positive_feedback_rate': sum(f['clicked'] for f in feedback) / len(feedback),
    'user_features': recommendation_data['user_features']
}
'''
    )
    cycle_builder.add_cycle_node("feedback_collector", feedback_collector)

    # Update model based on feedback
    model_updater = PythonCodeNode(
        name="model_updater",
        code='''

# Update model weights based on feedback
model_weights = np.array(recommendation_data['model_weights'])
user_features = np.array(feedback_data['user_features'])
feedback = feedback_data['feedback']

# Simple gradient update based on feedback
learning_rate = 0.01
for fb in feedback:
    item_id = fb['item_id']
    clicked = fb['clicked']
    predicted = fb['probability']

    # Gradient of log loss
    error = clicked - predicted
    gradient = np.outer(user_features, np.eye(5)[item_id]) * error

    # Update weights
    model_weights += learning_rate * gradient

# Track performance
feedback_history = learning_state.get('feedback_history', [])
feedback_history.append(feedback_data['positive_feedback_rate'])

# Keep only last 100 feedback points
if len(feedback_history) > 100:
    feedback_history = feedback_history[-100:]

# Check if performance is improving
recent_performance = np.mean(feedback_history[-10:]) if len(feedback_history) >= 10 else 0
overall_performance = np.mean(feedback_history) if feedback_history else 0

result = {
    'model_weights': model_weights.tolist(),
    'feedback_history': feedback_history,
    'recent_performance': recent_performance,
    'overall_performance': overall_performance,
    'iteration': recommendation_data['iteration'],
    'is_improving': recent_performance > overall_performance
}
'''
    )
    cycle_builder.add_cycle_node("model_updater", model_updater)

    # Convergence checker
    convergence_checker = SwitchNode(
        id="convergence_checker",
        condition="recent_performance > 0.7 or iteration >= 100"
    )
    cycle_builder.add_cycle_node("convergence_checker", convergence_checker)

    # Connect feedback loop
    cycle_builder.connect_cycle_nodes("recommender", "feedback_collector",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("feedback_collector", "model_updater",
                                     # mapping removed)
    cycle_builder.connect_cycle_nodes("model_updater", "convergence_checker",
                                     # mapping removed)

    # Exit when performance is good enough
    cycle_builder.set_cycle_exit_condition("convergence_checker", exit_on="true_output")

    # Continue learning
    cycle_builder.connect_cycle_nodes("convergence_checker", "recommender",
                                     output_key="false_output",
                                     # mapping removed)

    return workflow

```

## 🎯 Common Use Cases

### 1. Retry Mechanisms
- API calls with backoff
- Database connection retries
- File processing with recovery
- Service availability checks

### 2. Optimization Algorithms
- Gradient descent
- Genetic algorithms
- Hyperparameter tuning
- A/B test optimization

### 3. State Machines
- Order processing workflows
- Approval chains
- Multi-step wizards
- Game state management

### 4. Feedback Systems
- Recommendation engines
- Control systems
- Quality improvement loops
- Learning algorithms

## 📊 Best Practices

### 1. **Always Set Exit Conditions**
```python
# GOOD: Clear exit condition
cycle_builder.set_cycle_exit_condition(
    "convergence_checker",
    exit_on="true_output"
)

# GOOD: Maximum iteration limit
cycle_builder.set_max_iterations(1000)

```

### 2. **Track Cycle State**
```python
# GOOD: Maintain state across iterations
state = {
    'iteration': iteration,
    'best_result': best_result,
    'history': history[-100:]  # Keep bounded history
}

```

### 3. **Monitor Progress**
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

# GOOD: Log cycle metrics
cycle_profiler = CycleProfiler()
profiler_data = cycle_profiler.profile_workflow(workflow)
print(f"Iterations: {profiler_data['total_iterations']}")
print(f"Avg iteration time: {profiler_data['avg_iteration_time']}")

```

### 4. **Handle Infinite Loops**
```python
# GOOD: Multiple termination conditions
condition = """
converged or
iteration >= max_iterations or
time_elapsed > max_time or
no_improvement_count > patience
"""

```

## 🔗 Related Examples

- **Examples Directory**: `/examples/cycle_patterns/`
- **Basic Cycles**: `/examples/workflow_examples/workflow_cyclic_examples.py`
- **Advanced Patterns**: `/examples/cycle_patterns/comprehensive_error_testing.py`
- **Production Examples**: `/examples/cycle_patterns/phase_5_3_production_example.py`

## ⚠️ Common Pitfalls

1. **Missing Exit Conditions**
   - Always define when to exit the cycle
   - Set maximum iteration limits as safety

2. **Unbounded State Growth**
   - Keep cycle state bounded in size
   - Clear unnecessary history periodically

3. **Performance Degradation**
   - Monitor iteration times
   - Watch for memory leaks in state

4. **Complex Dependencies**
   - Keep cycle logic simple and clear
   - Avoid deeply nested cycles

---

*Cyclic workflows enable powerful iterative patterns. Use them for optimization, learning, and any process that requires repetition with refinement.*
