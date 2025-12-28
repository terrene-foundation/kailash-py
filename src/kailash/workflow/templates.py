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
from typing import Any

from ..nodes.code import PythonCodeNode
from . import Workflow


@dataclass
class CycleTemplate:
    """Configuration for a cycle template."""

    name: str
    description: str
    nodes: list[str]
    convergence_condition: str | None = None
    max_iterations: int = 100
    timeout: float | None = None
    parameters: dict[str, Any] | None = None


class CycleTemplates:
    """Collection of pre-built cycle templates for common patterns."""

    @staticmethod
    def optimization_cycle(
        workflow: Workflow,
        processor_node: str,
        evaluator_node: str,
        convergence: str = "quality > 0.9",
        max_iterations: int = 50,
        cycle_id: str | None = None,
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
            # Use timestamp with milliseconds for ID generation to ensure uniqueness
            cycle_id = f"optimization_cycle_{int(time.time() * 1000)}"

        # Connect processor to evaluator
        workflow.connect(processor_node, evaluator_node)

        # Close the cycle with convergence condition using new API
        workflow.create_cycle(cycle_id).connect(
            evaluator_node, processor_node
        ).max_iterations(max_iterations).converge_when(convergence).build()

        return cycle_id

    @staticmethod
    def retry_cycle(
        workflow: Workflow,
        target_node: str,
        max_retries: int = 3,
        backoff_strategy: str = "exponential",
        success_condition: str = "success == True",
        cycle_id: str | None = None,
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
        cycle_id: str | None = None,
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
        cycle_id: str | None = None,
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
        cycle_id: str | None = None,
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
        total_items: int | None = None,
        cycle_id: str | None = None,
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


class BusinessWorkflowTemplates:
    """Pre-built templates for common business workflow patterns."""

    @staticmethod
    def investment_data_pipeline(
        workflow: Workflow,
        data_source: str = "market_data",
        processor: str = "portfolio_analyzer",
        validator: str = "risk_assessor",
        output: str = "investment_report",
    ) -> str:
        """
        Create a complete investment data processing pipeline.

        Args:
            workflow: Target workflow
            data_source: Node that fetches market/portfolio data
            processor: Node that analyzes investment data
            validator: Node that validates risk metrics
            output: Node that generates investment reports

        Returns:
            str: Pipeline identifier
        """
        # Add data fetching node if not exists
        if data_source not in workflow.nodes:
            from kailash.nodes.data import HTTPRequestNode

            workflow.add_node(
                data_source,
                HTTPRequestNode(
                    name=data_source,
                    url="https://api.example.com/market-data",
                    method="GET",
                ),
            )

        # Add portfolio analysis node if not exists
        if processor not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            analysis_code = """
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Process investment data
data = market_data if 'market_data' in locals() else {}
portfolio_value = data.get('portfolio_value', 1000000)
positions = data.get('positions', [])

# Calculate key metrics
total_return = sum(pos.get('return_pct', 0) * pos.get('weight', 0) for pos in positions)
volatility = np.std([pos.get('return_pct', 0) for pos in positions])
sharpe_ratio = total_return / volatility if volatility > 0 else 0

# Risk assessment
risk_level = 'LOW' if volatility < 0.1 else 'MEDIUM' if volatility < 0.2 else 'HIGH'

result = {
    'portfolio_value': portfolio_value,
    'total_return': total_return,
    'volatility': volatility,
    'sharpe_ratio': sharpe_ratio,
    'risk_level': risk_level,
    'positions_count': len(positions),
    'analysis_date': datetime.now().isoformat()
}
"""
            workflow.add_node(
                processor, PythonCodeNode(name=processor, code=analysis_code)
            )

        # Add risk validation node if not exists
        if validator not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            validation_code = """
# Risk validation and compliance checks
analysis = result if 'result' in locals() else {}

# Risk limits and compliance
max_volatility = 0.25
max_single_position = 0.10
min_diversification = 5

# Validate metrics
volatility_ok = analysis.get('volatility', 0) <= max_volatility
diversification_ok = analysis.get('positions_count', 0) >= min_diversification
risk_acceptable = analysis.get('risk_level') in ['LOW', 'MEDIUM']

# Generate warnings
warnings = []
if not volatility_ok:
    warnings.append(f"Portfolio volatility {analysis.get('volatility', 0):.2%} exceeds limit {max_volatility:.2%}")
if not diversification_ok:
    warnings.append(f"Insufficient diversification: {analysis.get('positions_count', 0)} positions (min {min_diversification})")
if not risk_acceptable:
    warnings.append(f"Risk level {analysis.get('risk_level')} may be too high")

validation_result = {
    'validated': len(warnings) == 0,
    'warnings': warnings,
    'compliance_score': (int(volatility_ok) + int(diversification_ok) + int(risk_acceptable)) / 3,
    'validation_date': analysis.get('analysis_date'),
    'risk_metrics': analysis
}
"""
            workflow.add_node(
                validator, PythonCodeNode(name=validator, code=validation_code)
            )

        # Add report generation node if not exists
        if output not in workflow.nodes:
            from kailash.nodes.data import JSONWriterNode
            from kailash.utils.data_paths import get_output_data_path

            workflow.add_node(
                output,
                JSONWriterNode(
                    name=output,
                    file_path=get_output_data_path("investment_report.json"),
                ),
            )

        # Connect the pipeline
        workflow.connect(data_source, processor)
        workflow.connect(processor, validator, {"result": "result"})
        workflow.connect(validator, output, {"validation_result": "data"})

        return "investment_pipeline"

    @staticmethod
    def document_ai_workflow(
        workflow: Workflow,
        document_reader: str = "pdf_reader",
        text_processor: str = "ai_analyzer",
        extractor: str = "data_extractor",
        output: str = "structured_data",
    ) -> str:
        """
        Create a document AI processing workflow.

        Args:
            workflow: Target workflow
            document_reader: Node that reads documents
            text_processor: Node that processes text with AI
            extractor: Node that extracts structured data
            output: Node that saves extracted data

        Returns:
            str: Workflow identifier
        """
        # Add document reader if not exists
        if document_reader not in workflow.nodes:
            from kailash.nodes.data import DirectoryReaderNode
            from kailash.utils.data_paths import get_input_data_path

            workflow.add_node(
                document_reader,
                DirectoryReaderNode(
                    name=document_reader,
                    directory_path=get_input_data_path("documents"),
                    file_types=[".pdf", ".docx", ".txt"],
                ),
            )

        # Add AI text processor if not exists
        if text_processor not in workflow.nodes:
            from kaizen.nodes.ai import LLMAgentNode

            workflow.add_node(
                text_processor,
                LLMAgentNode(
                    name=text_processor,
                    model="llama3.2",
                    prompt_template="""
Analyze the following document and extract key information:

Document: {document_content}

Please extract:
1. Document type (contract, invoice, report, etc.)
2. Key dates mentioned
3. Important entities (people, companies, amounts)
4. Main topics or subjects
5. Any action items or deadlines

Provide the response in JSON format with these fields:
- document_type
- dates
- entities
- topics
- action_items
""",
                    base_url="http://localhost:11434",
                ),
            )

        # Add data extractor if not exists
        if extractor not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            extraction_code = """
import json
import re
from datetime import datetime

# Process AI analysis result
ai_response = response if 'response' in locals() else ""
document_info = files if 'files' in locals() else []

# Try to parse JSON from AI response
try:
    # Extract JSON from response (handle cases where AI adds extra text)
    json_match = re.search(r'\\{.*\\}', ai_response, re.DOTALL)
    if json_match:
        extracted_data = json.loads(json_match.group())
    else:
        # Fallback if no JSON found
        extracted_data = {"raw_response": ai_response}
except:
    extracted_data = {"raw_response": ai_response}

# Add metadata
extracted_data.update({
    'extraction_date': datetime.now().isoformat(),
    'document_count': len(document_info) if isinstance(document_info, list) else 1,
    'processing_status': 'completed'
})

# Structure the final result
result = {
    'extracted_data': extracted_data,
    'source_documents': document_info,
    'processing_metadata': {
        'extraction_method': 'ai_analysis',
        'model_used': 'llama3.2',
        'processing_date': datetime.now().isoformat()
    }
}
"""
            workflow.add_node(
                extractor, PythonCodeNode(name=extractor, code=extraction_code)
            )

        # Add output writer if not exists
        if output not in workflow.nodes:
            from kailash.nodes.data import JSONWriterNode
            from kailash.utils.data_paths import get_output_data_path

            workflow.add_node(
                output,
                JSONWriterNode(
                    name=output,
                    file_path=get_output_data_path("extracted_document_data.json"),
                ),
            )

        # Connect the workflow
        workflow.connect(document_reader, text_processor, {"files": "document_content"})
        workflow.connect(
            text_processor, extractor, {"response": "response", "files": "files"}
        )
        workflow.connect(extractor, output, {"result": "data"})

        return "document_ai_pipeline"

    @staticmethod
    def api_integration_pattern(
        workflow: Workflow,
        auth_node: str = "api_auth",
        data_fetcher: str = "api_client",
        transformer: str = "data_transformer",
        validator: str = "response_validator",
        output: str = "api_output",
    ) -> str:
        """
        Create a robust API integration pattern with auth, retry, and validation.

        Args:
            workflow: Target workflow
            auth_node: Node that handles API authentication
            data_fetcher: Node that fetches data from API
            transformer: Node that transforms API responses
            validator: Node that validates responses
            output: Node that outputs processed data

        Returns:
            str: Integration identifier
        """
        # Add OAuth2 authentication if not exists
        if auth_node not in workflow.nodes:
            from kailash.nodes.api import OAuth2Node

            workflow.add_node(
                auth_node,
                OAuth2Node(
                    name=auth_node,
                    client_id="${API_CLIENT_ID}",
                    client_secret="${API_CLIENT_SECRET}",
                    token_url="https://api.example.com/oauth/token",
                    scope="read write",
                ),
            )

        # Add API client with retry logic if not exists
        if data_fetcher not in workflow.nodes:
            from kailash.nodes.api import HTTPRequestNode

            workflow.add_node(
                data_fetcher,
                HTTPRequestNode(
                    name=data_fetcher,
                    url="https://api.example.com/data",
                    method="GET",
                    timeout=30,
                    retry_count=3,
                ),
            )

        # Add data transformer if not exists
        if transformer not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            transform_code = """
import json
from datetime import datetime

# Transform API response data
response_data = response if 'response' in locals() else {}
token_info = token if 'token' in locals() else {}

# Handle different response formats
if isinstance(response_data, str):
    try:
        response_data = json.loads(response_data)
    except:
        response_data = {"raw_response": response_data}

# Transform data structure
transformed_data = {
    'api_data': response_data,
    'request_metadata': {
        'timestamp': datetime.now().isoformat(),
        'authenticated': bool(token_info.get('access_token')),
        'token_expires': token_info.get('expires_at'),
        'data_source': 'external_api'
    },
    'data_quality': {
        'record_count': len(response_data) if isinstance(response_data, list) else 1,
        'has_errors': 'error' in str(response_data).lower(),
        'response_size_kb': len(str(response_data)) / 1024
    }
}

result = transformed_data
"""
            workflow.add_node(
                transformer, PythonCodeNode(name=transformer, code=transform_code)
            )

        # Add response validator if not exists
        if validator not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            validation_code = """
# Validate API response and transformed data
data = result if 'result' in locals() else {}

# Validation checks
api_data = data.get('api_data', {})
metadata = data.get('request_metadata', {})
quality = data.get('data_quality', {})

validation_results = {
    'data_present': bool(api_data),
    'authenticated_request': metadata.get('authenticated', False),
    'no_errors': not quality.get('has_errors', True),
    'reasonable_size': quality.get('response_size_kb', 0) > 0,
    'recent_data': True  # Could add timestamp validation
}

# Overall validation
all_valid = all(validation_results.values())
validation_score = sum(validation_results.values()) / len(validation_results)

validated_result = {
    'validation_passed': all_valid,
    'validation_score': validation_score,
    'validation_details': validation_results,
    'validated_data': data if all_valid else None,
    'validation_timestamp': metadata.get('timestamp')
}
"""
            workflow.add_node(
                validator, PythonCodeNode(name=validator, code=validation_code)
            )

        # Add output node if not exists
        if output not in workflow.nodes:
            from kailash.nodes.data import JSONWriterNode
            from kailash.utils.data_paths import get_output_data_path

            workflow.add_node(
                output,
                JSONWriterNode(
                    name=output,
                    file_path=get_output_data_path("api_integration_result.json"),
                ),
            )

        # Connect the integration pattern
        workflow.connect(auth_node, data_fetcher, {"token": "auth_header"})
        workflow.connect(
            data_fetcher, transformer, {"response": "response", "token": "token"}
        )
        workflow.connect(transformer, validator, {"result": "result"})
        workflow.connect(validator, output, {"validated_result": "data"})

        return "api_integration"

    @staticmethod
    def data_processing_pipeline(
        workflow: Workflow,
        data_reader: str = "data_reader",
        cleaner: str = "data_cleaner",
        enricher: str = "data_enricher",
        aggregator: str = "data_aggregator",
        writer: str = "data_writer",
    ) -> str:
        """
        Create a comprehensive data processing pipeline.

        Args:
            workflow: Target workflow
            data_reader: Node that reads raw data
            cleaner: Node that cleans and validates data
            enricher: Node that enriches data with additional information
            aggregator: Node that aggregates and summarizes data
            writer: Node that writes processed data

        Returns:
            str: Pipeline identifier
        """
        # Add data reader if not exists
        if data_reader not in workflow.nodes:
            from kailash.nodes.data import CSVReaderNode
            from kailash.utils.data_paths import get_input_data_path

            workflow.add_node(
                data_reader,
                CSVReaderNode(
                    name=data_reader, file_path=get_input_data_path("raw_data.csv")
                ),
            )

        # Add data cleaner if not exists
        if cleaner not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            cleaning_code = """
import pandas as pd
import numpy as np
from datetime import datetime

# Clean and validate data
data = data if 'data' in locals() else []

# Convert to DataFrame for easier processing
if isinstance(data, list) and data:
    df = pd.DataFrame(data)
elif isinstance(data, dict):
    df = pd.DataFrame([data])
else:
    df = pd.DataFrame()

# Data cleaning operations
if not df.empty:
    # Remove duplicates
    original_count = len(df)
    df = df.drop_duplicates()
    duplicates_removed = original_count - len(df)

    # Handle missing values
    numeric_columns = df.select_dtypes(include=[np.number]).columns
    df[numeric_columns] = df[numeric_columns].fillna(df[numeric_columns].mean())

    # Remove outliers (3 standard deviations)
    for col in numeric_columns:
        mean = df[col].mean()
        std = df[col].std()
        df = df[abs(df[col] - mean) <= 3 * std]

    # Standardize text fields
    text_columns = df.select_dtypes(include=['object']).columns
    for col in text_columns:
        df[col] = df[col].astype(str).str.strip().str.title()

    cleaned_data = df.to_dict('records')
else:
    cleaned_data = []
    duplicates_removed = 0

result = {
    'cleaned_data': cleaned_data,
    'cleaning_stats': {
        'original_records': len(data) if isinstance(data, list) else 1,
        'cleaned_records': len(cleaned_data),
        'duplicates_removed': duplicates_removed,
        'cleaning_date': datetime.now().isoformat()
    }
}
"""
            workflow.add_node(cleaner, PythonCodeNode(name=cleaner, code=cleaning_code))

        # Add data enricher if not exists
        if enricher not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            enrichment_code = """
import pandas as pd
from datetime import datetime

# Enrich data with additional calculated fields
clean_result = result if 'result' in locals() else {}
cleaned_data = clean_result.get('cleaned_data', [])

if cleaned_data:
    df = pd.DataFrame(cleaned_data)

    # Add calculated fields
    if 'amount' in df.columns:
        df['amount_category'] = pd.cut(df['amount'],
                                     bins=[0, 100, 1000, 10000, float('inf')],
                                     labels=['Small', 'Medium', 'Large', 'Enterprise'])

    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.month
        df['quarter'] = df['date'].dt.quarter

    # Add data quality scores
    df['completeness_score'] = (df.count(axis=1) / len(df.columns))
    df['data_quality'] = pd.cut(df['completeness_score'],
                               bins=[0, 0.5, 0.8, 1.0],
                               labels=['Poor', 'Fair', 'Good'])

    enriched_data = df.to_dict('records')
else:
    enriched_data = []

result = {
    'enriched_data': enriched_data,
    'enrichment_stats': {
        'records_enriched': len(enriched_data),
        'fields_added': ['amount_category', 'year', 'month', 'quarter', 'completeness_score', 'data_quality'],
        'enrichment_date': datetime.now().isoformat()
    },
    'original_stats': clean_result.get('cleaning_stats', {})
}
"""
            workflow.add_node(
                enricher, PythonCodeNode(name=enricher, code=enrichment_code)
            )

        # Add aggregator if not exists
        if aggregator not in workflow.nodes:
            from kailash.nodes.code import PythonCodeNode

            aggregation_code = """
import pandas as pd
from datetime import datetime

# Aggregate and summarize enriched data
enrich_result = result if 'result' in locals() else {}
enriched_data = enrich_result.get('enriched_data', [])

if enriched_data:
    df = pd.DataFrame(enriched_data)

    # Calculate summary statistics
    summary_stats = {}

    # Numeric summaries
    numeric_cols = df.select_dtypes(include=['number']).columns
    for col in numeric_cols:
        summary_stats[col] = {
            'mean': df[col].mean(),
            'median': df[col].median(),
            'std': df[col].std(),
            'min': df[col].min(),
            'max': df[col].max(),
            'count': df[col].count()
        }

    # Categorical summaries
    categorical_cols = df.select_dtypes(include=['object', 'category']).columns
    category_summaries = {}
    for col in categorical_cols:
        if col not in ['data_quality', 'amount_category']:  # Skip our generated categories
            category_summaries[col] = df[col].value_counts().to_dict()

    # Data quality summary
    quality_summary = {
        'total_records': len(df),
        'complete_records': (df['completeness_score'] == 1.0).sum(),
        'quality_distribution': df['data_quality'].value_counts().to_dict() if 'data_quality' in df.columns else {},
        'average_completeness': df['completeness_score'].mean() if 'completeness_score' in df.columns else 1.0
    }

    aggregated_result = {
        'summary_statistics': summary_stats,
        'category_summaries': category_summaries,
        'quality_summary': quality_summary,
        'aggregation_date': datetime.now().isoformat()
    }
else:
    aggregated_result = {
        'summary_statistics': {},
        'category_summaries': {},
        'quality_summary': {'total_records': 0},
        'aggregation_date': datetime.now().isoformat()
    }

result = {
    'aggregated_results': aggregated_result,
    'processed_data': enriched_data,
    'processing_pipeline': {
        'original_stats': enrich_result.get('original_stats', {}),
        'enrichment_stats': enrich_result.get('enrichment_stats', {}),
        'aggregation_stats': {
            'fields_summarized': len(aggregated_result['summary_statistics']),
            'categories_analyzed': len(aggregated_result['category_summaries'])
        }
    }
}
"""
            workflow.add_node(
                aggregator, PythonCodeNode(name=aggregator, code=aggregation_code)
            )

        # Add data writer if not exists
        if writer not in workflow.nodes:
            from kailash.nodes.data import JSONWriterNode
            from kailash.utils.data_paths import get_output_data_path

            workflow.add_node(
                writer,
                JSONWriterNode(
                    name=writer,
                    file_path=get_output_data_path("processed_data_results.json"),
                ),
            )

        # Connect the pipeline
        workflow.connect(data_reader, cleaner, {"data": "data"})
        workflow.connect(cleaner, enricher, {"result": "result"})
        workflow.connect(enricher, aggregator, {"result": "result"})
        workflow.connect(aggregator, writer, {"result": "data"})

        return "data_processing_pipeline"


# Convenience methods to add to Workflow class
def add_optimization_cycle(
    self,
    processor_node: str,
    evaluator_node: str,
    convergence: str = "quality > 0.9",
    max_iterations: int = 50,
    cycle_id: str | None = None,
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
    cycle_id: str | None = None,
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
    cycle_id: str | None = None,
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
    cycle_id: str | None = None,
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
    cycle_id: str | None = None,
) -> str:
    """Add a numerical convergence cycle to this workflow."""
    return CycleTemplates.convergence_cycle(
        self, processor_node, tolerance, max_iterations, cycle_id
    )


def add_batch_processing_cycle(
    self,
    processor_node: str,
    batch_size: int = 100,
    total_items: int | None = None,
    cycle_id: str | None = None,
) -> str:
    """Add a batch processing cycle to this workflow."""
    return CycleTemplates.batch_processing_cycle(
        self, processor_node, batch_size, total_items, cycle_id
    )


# Business workflow convenience methods
def add_investment_pipeline(
    self,
    data_source: str = "market_data",
    processor: str = "portfolio_analyzer",
    validator: str = "risk_assessor",
    output: str = "investment_report",
) -> str:
    """Add an investment data processing pipeline to this workflow."""
    return BusinessWorkflowTemplates.investment_data_pipeline(
        self, data_source, processor, validator, output
    )


def add_document_ai_workflow(
    self,
    document_reader: str = "pdf_reader",
    text_processor: str = "ai_analyzer",
    extractor: str = "data_extractor",
    output: str = "structured_data",
) -> str:
    """Add a document AI processing workflow to this workflow."""
    return BusinessWorkflowTemplates.document_ai_workflow(
        self, document_reader, text_processor, extractor, output
    )


def add_api_integration_pattern(
    self,
    auth_node: str = "api_auth",
    data_fetcher: str = "api_client",
    transformer: str = "data_transformer",
    validator: str = "response_validator",
    output: str = "api_output",
) -> str:
    """Add an API integration pattern to this workflow."""
    return BusinessWorkflowTemplates.api_integration_pattern(
        self, auth_node, data_fetcher, transformer, validator, output
    )


def add_data_processing_pipeline(
    self,
    data_reader: str = "data_reader",
    cleaner: str = "data_cleaner",
    enricher: str = "data_enricher",
    aggregator: str = "data_aggregator",
    writer: str = "data_writer",
) -> str:
    """Add a data processing pipeline to this workflow."""
    return BusinessWorkflowTemplates.data_processing_pipeline(
        self, data_reader, cleaner, enricher, aggregator, writer
    )


# Add convenience methods to Workflow class
Workflow.add_optimization_cycle = add_optimization_cycle
Workflow.add_retry_cycle = add_retry_cycle
Workflow.add_data_quality_cycle = add_data_quality_cycle
Workflow.add_learning_cycle = add_learning_cycle
Workflow.add_convergence_cycle = add_convergence_cycle
Workflow.add_batch_processing_cycle = add_batch_processing_cycle

# Add business workflow methods to Workflow class
Workflow.add_investment_pipeline = add_investment_pipeline
Workflow.add_document_ai_workflow = add_document_ai_workflow
Workflow.add_api_integration_pattern = add_api_integration_pattern
Workflow.add_data_processing_pipeline = add_data_processing_pipeline
