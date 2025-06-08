"""
Pre-Built Workflow Templates for Common Cyclic Patterns.

This module provides a comprehensive collection of pre-built cycle templates
and patterns that dramatically simplify the creation of common workflow
structures. It eliminates boilerplate code and ensures best practices are
followed automatically for standard cyclic workflow patterns.

Design Philosophy:
    Provides curated, battle-tested templates for common cycle patterns,
    reducing development time and ensuring optimal configurations. Each
    template encapsulates best practices and proven patterns for specific
    use cases with sensible defaults and customization options.

Key Features:
    - Pre-built templates for common patterns
    - Automatic best-practice configuration
    - Customizable parameters with validation
    - Generated helper nodes for complex patterns
    - Workflow class extensions for seamless integration

Template Categories:
    - Optimization Cycles: Iterative improvement patterns
    - Retry Cycles: Error recovery and fault tolerance
    - Data Quality Cycles: Iterative data cleaning and validation
    - Learning Cycles: Machine learning training patterns
    - Convergence Cycles: Numerical convergence patterns
    - Batch Processing Cycles: Large dataset processing patterns

Core Components:
    - CycleTemplate: Configuration dataclass for templates
    - CycleTemplates: Static factory methods for template creation
    - Generated helper nodes for pattern-specific logic
    - Workflow class extensions for direct integration

Automatic Optimizations:
    - Pattern-specific convergence conditions
    - Appropriate safety limits and timeouts
    - Optimal iteration limits for each pattern
    - Memory management for data-intensive patterns
    - Error handling and recovery strategies

Upstream Dependencies:
    - Core workflow and node implementations
    - PythonCodeNode for generated helper logic
    - SwitchNode for conditional routing patterns
    - Convergence and safety systems

Downstream Consumers:
    - Workflow builders and automation tools
    - Template-based workflow generation systems
    - Development tools and IDEs
    - Educational and training materials

Examples:
    Optimization cycle template:

    >>> from kailash.workflow.templates import CycleTemplates
    >>> workflow = Workflow("optimization", "Quality Optimization")
    >>> workflow.add_node("processor", ProcessorNode())
    >>> workflow.add_node("evaluator", EvaluatorNode())
    >>> cycle_id = CycleTemplates.optimization_cycle(
    ...     workflow,
    ...     processor_node="processor",
    ...     evaluator_node="evaluator",
    ...     convergence="quality > 0.95",
    ...     max_iterations=100
    ... )

    Retry cycle with backoff:

    >>> cycle_id = CycleTemplates.retry_cycle(
    ...     workflow,
    ...     target_node="api_call",
    ...     max_retries=5,
    ...     backoff_strategy="exponential",
    ...     success_condition="success == True"
    ... )

    Direct workflow integration:

    >>> # Templates extend Workflow class
    >>> workflow = Workflow("ml_training", "Model Training")
    >>> cycle_id = workflow.add_learning_cycle(
    ...     trainer_node="trainer",
    ...     evaluator_node="evaluator",
    ...     target_accuracy=0.98,
    ...     early_stopping_patience=10
    ... )

    Custom template configuration:

    >>> # Numerical convergence with custom tolerance
    >>> cycle_id = workflow.add_convergence_cycle(
    ...     processor_node="newton_raphson",
    ...     tolerance=0.0001,
            max_iterations=1000
        )

        # Batch processing for large datasets
        cycle_id = workflow.add_batch_processing_cycle(
            processor_node="data_processor",
            batch_size=1000,
            total_items=1000000
        )

See Also:
    - :mod:`kailash.workflow.cycle_config` for advanced configuration
    - :mod:`kailash.workflow.cycle_builder` for custom cycle creation
    - :doc:`/examples/patterns` for comprehensive pattern examples
"""

import math
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..nodes.code import PythonCodeNode
from . import Workflow


@dataclass
class CycleTemplate:
    """Configuration for a cycle template."""

    name: str
    description: str
    nodes: List[str]
    convergence_condition: Optional[str] = None
    max_iterations: int = 100
    timeout: Optional[float] = None
    parameters: Optional[Dict[str, Any]] = None


class CycleTemplates:
    """Collection of pre-built cycle templates for common patterns."""

    @staticmethod
    def optimization_cycle(
        workflow: Workflow,
        processor_node: str,
        evaluator_node: str,
        convergence: str = "quality > 0.9",
        max_iterations: int = 50,
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add an optimization cycle pattern to workflow.

        Creates a cycle where a processor generates solutions and an evaluator
        assesses quality, continuing until convergence criteria is met.

        Args:
            workflow: Target workflow
            processor_node: Node that generates/improves solutions
            evaluator_node: Node that evaluates solution quality
            convergence: Convergence condition (e.g., "quality > 0.9")
            max_iterations: Maximum iterations before stopping
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("optimization", "Optimization Example")
            >>> workflow.add_node("processor", PythonCodeNode(), code="...")
            >>> workflow.add_node("evaluator", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.optimization_cycle(
            ...     workflow, "processor", "evaluator",
            ...     convergence="quality > 0.95", max_iterations=100
            ... )
        """
        if cycle_id is None:
            cycle_id = f"optimization_cycle_{int(time.time())}"

        # Connect processor to evaluator
        workflow.connect(processor_node, evaluator_node)

        # Close the cycle with convergence condition
        workflow.connect(
            evaluator_node,
            processor_node,
            cycle=True,
            max_iterations=max_iterations,
            convergence_check=convergence,
            cycle_id=cycle_id,
        )

        return cycle_id

    @staticmethod
    def retry_cycle(
        workflow: Workflow,
        target_node: str,
        max_retries: int = 3,
        backoff_strategy: str = "exponential",
        success_condition: str = "success == True",
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add a retry cycle pattern to workflow.

        Creates a cycle that retries a node operation with configurable
        backoff strategy until success or max retries reached.

        Args:
            workflow: Target workflow
            target_node: Node to retry on failure
            max_retries: Maximum number of retry attempts
            backoff_strategy: Backoff strategy ("linear", "exponential", "fixed")
            success_condition: Condition that indicates success
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("retry", "Retry Example")
            >>> workflow.add_node("api_call", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.retry_cycle(
            ...     workflow, "api_call", max_retries=5,
            ...     backoff_strategy="exponential"
            ... )
        """
        if cycle_id is None:
            cycle_id = f"retry_cycle_{int(time.time())}"

        # Create retry controller node
        retry_controller_id = f"{target_node}_retry_controller"

        retry_code = f"""
import time
import random

# Initialize retry state
try:
    attempt = attempt
    backoff_time = backoff_time
except NameError:
    attempt = 0
    backoff_time = 1.0

attempt += 1

# Check if we should retry
should_retry = attempt <= {max_retries}
final_attempt = attempt >= {max_retries}

# Calculate backoff delay
if "{backoff_strategy}" == "exponential":
    backoff_time = min(60, 2 ** (attempt - 1))
elif "{backoff_strategy}" == "linear":
    backoff_time = attempt * 1.0
else:  # fixed
    backoff_time = 1.0

# Add jitter to prevent thundering herd
jitter = random.uniform(0.1, 0.3) * backoff_time
actual_delay = backoff_time + jitter

print(f"Retry attempt {{attempt}}/{max_retries}, delay: {{actual_delay:.2f}}s")

# Simulate delay (in real scenario, this would be handled by scheduler)
if attempt > 1:
    time.sleep(min(actual_delay, 5.0))  # Cap delay for examples

result = {{
    "attempt": attempt,
    "should_retry": should_retry,
    "final_attempt": final_attempt,
    "backoff_time": backoff_time,
    "retry_exhausted": attempt > {max_retries}
}}
"""

        workflow.add_node(
            retry_controller_id,
            PythonCodeNode(name=retry_controller_id, code=retry_code),
        )

        # Connect retry controller to target node
        workflow.connect(retry_controller_id, target_node)

        # Close the cycle with retry logic
        workflow.connect(
            target_node,
            retry_controller_id,
            cycle=True,
            max_iterations=max_retries + 1,
            convergence_check=f"({success_condition}) or (retry_exhausted == True)",
            cycle_id=cycle_id,
        )

        return cycle_id

    @staticmethod
    def data_quality_cycle(
        workflow: Workflow,
        cleaner_node: str,
        validator_node: str,
        quality_threshold: float = 0.95,
        max_iterations: int = 10,
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add a data quality improvement cycle to workflow.

        Creates a cycle where data is cleaned and validated iteratively
        until quality threshold is met.

        Args:
            workflow: Target workflow
            cleaner_node: Node that cleans/improves data
            validator_node: Node that validates data quality
            quality_threshold: Minimum quality score to achieve
            max_iterations: Maximum cleaning iterations
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("data_quality", "Data Quality Example")
            >>> workflow.add_node("cleaner", PythonCodeNode(), code="...")
            >>> workflow.add_node("validator", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.data_quality_cycle(
            ...     workflow, "cleaner", "validator", quality_threshold=0.98
            ... )
        """
        if cycle_id is None:
            cycle_id = f"data_quality_cycle_{int(time.time())}"

        # Connect cleaner to validator
        workflow.connect(cleaner_node, validator_node)

        # Close the cycle with quality threshold
        workflow.connect(
            validator_node,
            cleaner_node,
            cycle=True,
            max_iterations=max_iterations,
            convergence_check=f"quality_score >= {quality_threshold}",
            cycle_id=cycle_id,
        )

        return cycle_id

    @staticmethod
    def learning_cycle(
        workflow: Workflow,
        trainer_node: str,
        evaluator_node: str,
        target_accuracy: float = 0.95,
        max_epochs: int = 100,
        early_stopping_patience: int = 10,
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add a machine learning training cycle to workflow.

        Creates a cycle for iterative model training with early stopping
        based on validation performance.

        Args:
            workflow: Target workflow
            trainer_node: Node that trains the model
            evaluator_node: Node that evaluates model performance
            target_accuracy: Target accuracy to achieve
            max_epochs: Maximum training epochs
            early_stopping_patience: Epochs to wait without improvement
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("ml_training", "ML Training Example")
            >>> workflow.add_node("trainer", PythonCodeNode(), code="...")
            >>> workflow.add_node("evaluator", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.learning_cycle(
            ...     workflow, "trainer", "evaluator", target_accuracy=0.98
            ... )
        """
        if cycle_id is None:
            cycle_id = f"learning_cycle_{int(time.time())}"

        # Create early stopping controller
        early_stop_controller_id = f"{trainer_node}_early_stop"

        early_stop_code = f"""
# Initialize early stopping state
try:
    best_accuracy = best_accuracy
    epochs_without_improvement = epochs_without_improvement
    epoch = epoch
except NameError:
    best_accuracy = 0.0
    epochs_without_improvement = 0
    epoch = 0

epoch += 1

# Get current accuracy from evaluator
current_accuracy = accuracy if 'accuracy' in locals() else 0.0

# Check for improvement
if current_accuracy > best_accuracy:
    best_accuracy = current_accuracy
    epochs_without_improvement = 0
    improved = True
else:
    epochs_without_improvement += 1
    improved = False

# Determine if should continue training
target_reached = current_accuracy >= {target_accuracy}
early_stop = epochs_without_improvement >= {early_stopping_patience}
max_epochs_reached = epoch >= {max_epochs}

should_continue = not (target_reached or early_stop or max_epochs_reached)

print(f"Epoch {{epoch}}: accuracy={{current_accuracy:.4f}}, best={{best_accuracy:.4f}}")
if not improved:
    print(f"No improvement for {{epochs_without_improvement}} epochs")

result = {{
    "epoch": epoch,
    "current_accuracy": current_accuracy,
    "best_accuracy": best_accuracy,
    "epochs_without_improvement": epochs_without_improvement,
    "should_continue": should_continue,
    "target_reached": target_reached,
    "early_stopped": early_stop,
    "training_complete": not should_continue
}}
"""

        workflow.add_node(
            early_stop_controller_id,
            PythonCodeNode(name=early_stop_controller_id, code=early_stop_code),
        )

        # Connect the training cycle
        workflow.connect(trainer_node, evaluator_node)
        workflow.connect(evaluator_node, early_stop_controller_id)

        # Close the cycle with early stopping logic
        workflow.connect(
            early_stop_controller_id,
            trainer_node,
            cycle=True,
            max_iterations=max_epochs,
            convergence_check="training_complete == True",
            cycle_id=cycle_id,
        )

        return cycle_id

    @staticmethod
    def convergence_cycle(
        workflow: Workflow,
        processor_node: str,
        tolerance: float = 0.001,
        max_iterations: int = 1000,
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add a numerical convergence cycle to workflow.

        Creates a cycle that continues until successive iterations
        produce values within a specified tolerance.

        Args:
            workflow: Target workflow
            processor_node: Node that produces values to check for convergence
            tolerance: Maximum difference between iterations for convergence
            max_iterations: Maximum iterations before forced termination
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("convergence", "Convergence Example")
            >>> workflow.add_node("processor", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.convergence_cycle(
            ...     workflow, "processor", tolerance=0.0001
            ... )
        """
        if cycle_id is None:
            cycle_id = f"convergence_cycle_{int(time.time())}"

        # Create convergence checker node
        convergence_checker_id = f"{processor_node}_convergence_checker"

        convergence_code = f"""
import math

# Initialize convergence state
try:
    previous_value = previous_value
    iteration = iteration
except NameError:
    previous_value = None
    iteration = 0

iteration += 1

# Get current value (assume processor outputs 'value' field)
current_value = value if 'value' in locals() else 0.0

# Check convergence
if previous_value is not None:
    difference = abs(current_value - previous_value)
    converged = difference <= {tolerance}
    relative_change = difference / abs(previous_value) if previous_value != 0 else float('inf')
else:
    difference = float('inf')
    converged = False
    relative_change = float('inf')

print(f"Iteration {{iteration}}: value={{current_value:.6f}}, diff={{difference:.6f}}, converged={{converged}}")

result = {{
    "iteration": iteration,
    "current_value": current_value,
    "previous_value": previous_value,
    "difference": difference,
    "relative_change": relative_change,
    "converged": converged,
    "tolerance": {tolerance}
}}

# Update for next iteration
previous_value = current_value
"""

        workflow.add_node(
            convergence_checker_id,
            PythonCodeNode(name=convergence_checker_id, code=convergence_code),
        )

        # Connect processor to convergence checker
        workflow.connect(processor_node, convergence_checker_id)

        # Close the cycle with convergence condition
        workflow.connect(
            convergence_checker_id,
            processor_node,
            cycle=True,
            max_iterations=max_iterations,
            convergence_check="converged == True",
            cycle_id=cycle_id,
        )

        return cycle_id

    @staticmethod
    def batch_processing_cycle(
        workflow: Workflow,
        processor_node: str,
        batch_size: int = 100,
        total_items: Optional[int] = None,
        cycle_id: Optional[str] = None,
    ) -> str:
        """
        Add a batch processing cycle to workflow.

        Creates a cycle that processes data in batches, continuing
        until all items are processed.

        Args:
            workflow: Target workflow
            processor_node: Node that processes batches
            batch_size: Number of items to process per batch
            total_items: Total number of items to process (if known)
            cycle_id: Optional custom cycle identifier

        Returns:
            str: The cycle identifier for reference

        Example:
            >>> workflow = Workflow("batch", "Batch Processing Example")
            >>> workflow.add_node("processor", PythonCodeNode(), code="...")
            >>> cycle_id = CycleTemplates.batch_processing_cycle(
            ...     workflow, "processor", batch_size=50, total_items=1000
            ... )
        """
        if cycle_id is None:
            cycle_id = f"batch_cycle_{int(time.time())}"

        # Create batch controller node
        batch_controller_id = f"{processor_node}_batch_controller"

        batch_code = f"""
# Initialize batch state
try:
    batch_number = batch_number
    items_processed = items_processed
    start_index = start_index
except NameError:
    batch_number = 0
    items_processed = 0
    start_index = 0

batch_number += 1
end_index = start_index + {batch_size}

# Calculate progress
if {total_items} is not None:
    remaining_items = max(0, {total_items} - items_processed)
    actual_batch_size = min({batch_size}, remaining_items)
    progress_percentage = (items_processed / {total_items}) * 100
    all_processed = items_processed >= {total_items}
else:
    # If total unknown, rely on processor to indicate completion
    actual_batch_size = {batch_size}
    progress_percentage = None
    all_processed = False  # Will be determined by processor

print(f"Processing batch {{batch_number}}: items {{start_index}}-{{end_index-1}}")
if progress_percentage is not None:
    print(f"Progress: {{progress_percentage:.1f}}% ({{items_processed}}/{total_items})")

result = {{
    "batch_number": batch_number,
    "start_index": start_index,
    "end_index": end_index,
    "batch_size": actual_batch_size,
    "items_processed": items_processed,
    "all_processed": all_processed,
    "progress_percentage": progress_percentage
}}

# Update for next iteration
start_index = end_index
items_processed += actual_batch_size
"""

        workflow.add_node(
            batch_controller_id,
            PythonCodeNode(name=batch_controller_id, code=batch_code),
        )

        # Connect batch controller to processor
        workflow.connect(batch_controller_id, processor_node)

        # Calculate max iterations based on total items
        if total_items is not None:
            max_iterations = math.ceil(total_items / batch_size) + 1
        else:
            max_iterations = 1000  # Default upper bound

        # Close the cycle with completion condition
        workflow.connect(
            processor_node,
            batch_controller_id,
            cycle=True,
            max_iterations=max_iterations,
            convergence_check="all_processed == True",
            cycle_id=cycle_id,
        )

        return cycle_id


# Convenience methods to add to Workflow class
def add_optimization_cycle(
    self,
    processor_node: str,
    evaluator_node: str,
    convergence: str = "quality > 0.9",
    max_iterations: int = 50,
    cycle_id: Optional[str] = None,
) -> str:
    """Add an optimization cycle pattern to this workflow."""
    return CycleTemplates.optimization_cycle(
        self, processor_node, evaluator_node, convergence, max_iterations, cycle_id
    )


def add_retry_cycle(
    self,
    target_node: str,
    max_retries: int = 3,
    backoff_strategy: str = "exponential",
    success_condition: str = "success == True",
    cycle_id: Optional[str] = None,
) -> str:
    """Add a retry cycle pattern to this workflow."""
    return CycleTemplates.retry_cycle(
        self, target_node, max_retries, backoff_strategy, success_condition, cycle_id
    )


def add_data_quality_cycle(
    self,
    cleaner_node: str,
    validator_node: str,
    quality_threshold: float = 0.95,
    max_iterations: int = 10,
    cycle_id: Optional[str] = None,
) -> str:
    """Add a data quality improvement cycle to this workflow."""
    return CycleTemplates.data_quality_cycle(
        self, cleaner_node, validator_node, quality_threshold, max_iterations, cycle_id
    )


def add_learning_cycle(
    self,
    trainer_node: str,
    evaluator_node: str,
    target_accuracy: float = 0.95,
    max_epochs: int = 100,
    early_stopping_patience: int = 10,
    cycle_id: Optional[str] = None,
) -> str:
    """Add a machine learning training cycle to this workflow."""
    return CycleTemplates.learning_cycle(
        self,
        trainer_node,
        evaluator_node,
        target_accuracy,
        max_epochs,
        early_stopping_patience,
        cycle_id,
    )


def add_convergence_cycle(
    self,
    processor_node: str,
    tolerance: float = 0.001,
    max_iterations: int = 1000,
    cycle_id: Optional[str] = None,
) -> str:
    """Add a numerical convergence cycle to this workflow."""
    return CycleTemplates.convergence_cycle(
        self, processor_node, tolerance, max_iterations, cycle_id
    )


def add_batch_processing_cycle(
    self,
    processor_node: str,
    batch_size: int = 100,
    total_items: Optional[int] = None,
    cycle_id: Optional[str] = None,
) -> str:
    """Add a batch processing cycle to this workflow."""
    return CycleTemplates.batch_processing_cycle(
        self, processor_node, batch_size, total_items, cycle_id
    )


# Add convenience methods to Workflow class
Workflow.add_optimization_cycle = add_optimization_cycle
Workflow.add_retry_cycle = add_retry_cycle
Workflow.add_data_quality_cycle = add_data_quality_cycle
Workflow.add_learning_cycle = add_learning_cycle
Workflow.add_convergence_cycle = add_convergence_cycle
Workflow.add_batch_processing_cycle = add_batch_processing_cycle
