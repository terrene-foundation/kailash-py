#!/usr/bin/env python3
"""
Phase 5.3 Helper Methods & Common Patterns - Comprehensive Example

This example demonstrates all the helper methods and common patterns
implemented in Phase 5.3:

1. Cycle Templates (CycleTemplates)
2. Migration Helpers (DAGToCycleConverter)
3. Validation & Linting Tools (CycleLinter)

Run this example to see all Phase 5.3 features in action.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Import templates to add convenience methods to Workflow class
from kailash.workflow.migration import DAGToCycleConverter
from kailash.workflow.validation import CycleLinter, IssueSeverity


def clean_data(data=None, iteration=None, quality_score=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import random

    try:
        data_quality = quality_score
        iteration = iteration
    except NameError:
        data_quality = 0.3  # Start with poor quality
        iteration = 0

    iteration += 1

    # Simulate data cleaning improvements
    improvement = random.uniform(0.05, 0.12)
    data_quality += improvement
    data_quality = min(1.0, data_quality)

    print(f"Data cleaning iteration {iteration}: quality = {data_quality:.3f}")

    result = {
        "cleaned_data": f"cleaned_dataset_v{iteration}",
        "quality_score": data_quality,
        "iteration": iteration,
    }

    return result


def validate_quality(data=None, iteration=None, quality_score=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import random

    # Validate data quality
    quality_score = data.get("quality_score", 0.0) if isinstance(data, dict) else 0.0
    iteration = data.get("iteration", 0) if isinstance(data, dict) else 0

    # Perform validation checks
    validation_penalty = random.uniform(
        0.0, 0.05
    )  # Small quality reduction during validation
    final_quality = max(0.0, quality_score - validation_penalty)

    is_acceptable = final_quality >= 0.95

    print(f"Quality validation: {final_quality:.3f} (acceptable: {is_acceptable})")

    result = {
        "quality_score": final_quality,
        "is_acceptable": is_acceptable,
        "iteration": iteration,
        "validation_complete": True,
    }

    return result


def train_model(model=None, epoch=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import math
    import random

    try:
        accuracy = accuracy
        epoch = epoch
    except NameError:
        accuracy = 0.1  # Start with low accuracy
        epoch = 0

    epoch += 1

    # Simulate model training with learning curve

    # Learning curve: rapid improvement initially, then plateaus
    progress = 1 - math.exp(-epoch / 10)
    base_accuracy = 0.1 + 0.85 * progress

    # Add some noise
    noise = random.uniform(-0.02, 0.02)
    accuracy = max(0.0, min(1.0, base_accuracy + noise))

    print(f"Training epoch {epoch}: accuracy = {accuracy:.4f}")

    result = {
        "accuracy": accuracy,
        "epoch": epoch,
        "model_weights": f"model_epoch_{epoch}.pkl",
    }

    return result


def evaluate_model(data=None, model=None, epoch=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import random

    # Evaluate model performance
    accuracy = data.get("accuracy", 0.0) if isinstance(data, dict) else 0.0
    epoch = data.get("epoch", 0) if isinstance(data, dict) else 0

    # Validation accuracy is typically slightly lower than training
    validation_accuracy = accuracy * random.uniform(0.92, 0.98)

    print(f"Validation accuracy: {validation_accuracy:.4f}")

    result = {
        "accuracy": validation_accuracy,
        "epoch": epoch,
        "validation_complete": True,
    }

    return result


def numerical_solver(iteration=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import math

    try:
        value = value
        iteration = iteration
    except NameError:
        value = 10.0  # Starting value
        iteration = 0

    iteration += 1

    # Simulate numerical convergence (e.g., Newton's method)

    # Simple convergence to sqrt(2) ≈ 1.414
    target = math.sqrt(2)

    # Newton's method for x^2 = 2
    if iteration == 1:
        value = 1.5  # Initial guess
    else:
        value = 0.5 * (value + 2.0 / value)

    difference = abs(value - target)
    converged = difference < 0.001

    print(f"Iteration {iteration}: value = {value:.6f}, diff = {difference:.6f}")

    result = {"value": value, "iteration": iteration, "converged": converged}

    return result


def process_batch(**kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import time

    # Get batch information
    start_index = start_index if "start_index" in locals() else 0
    batch_size = batch_size if "batch_size" in locals() else 10
    batch_number = batch_number if "batch_number" in locals() else 1

    end_index = start_index + batch_size

    # Simulate processing batch
    print(f"Processing batch {batch_number}: items {start_index}-{end_index-1}")

    # Simulate some processing time
    time.sleep(0.1)

    # Determine if all batches are processed (for demo, stop after 5 batches)
    total_items = 50
    items_processed = end_index
    all_processed = items_processed >= total_items

    print(f"Processed {items_processed}/{total_items} items")

    result = {
        "batch_number": batch_number,
        "items_processed": items_processed,
        "all_processed": all_processed,
        "processed_data": f"batch_{batch_number}_results",
    }

    return result


def demonstrate_cycle_templates():
    """Demonstrate all cycle template patterns."""
    print("=" * 60)
    print("🛠️  PHASE 5.3: CYCLE TEMPLATES DEMONSTRATION")
    print("=" * 60)

    # Create workflow for demonstrating templates
    workflow = Workflow("cycle_templates_demo", "Cycle Templates Demo")

    # 1. Optimization Cycle Template
    print("\n1️⃣ Optimization Cycle Template")
    print("-" * 40)

    # Define optimizer function (better IDE support)
    def optimize_solution(quality=None, iteration=None, **kwargs):
        """Simulate optimization improvement."""
        import random

        if quality is None:
            quality = 0.0
        if iteration is None:
            iteration = 0

        iteration += 1

        # Simulate optimization improvement
        quality += random.uniform(0.05, 0.15)
        quality = min(1.0, quality)  # Cap at 1.0

        print(f"Optimization iteration {iteration}: quality = {quality:.3f}")

        return {
            "quality": quality,
            "iteration": iteration,
            "data": f"optimized_solution_{iteration}",
        }

    # Add processor and evaluator nodes using from_function
    workflow.add_node(
        "optimizer",
        PythonCodeNode.from_function(
            func=optimize_solution,
            name="optimizer",
            description="Simulate optimization improvement",
        ),
    )

    # Define evaluator function (better IDE support)
    def evaluate_solution(data=None, **kwargs):
        """Evaluate the optimized solution."""
        import random

        # In a real scenario, 'data' would come from the optimizer node
        # For demo, handle missing data gracefully
        if data is None:
            quality = 0.5  # Starting quality
            iteration = 0
        elif isinstance(data, dict):
            quality = data.get("quality", 0.0)
            iteration = data.get("iteration", 0)
        else:
            quality = 0.0
            iteration = 0

        # Add some evaluation noise
        evaluated_quality = quality + random.uniform(-0.02, 0.02)
        evaluated_quality = max(0.0, min(1.0, evaluated_quality))

        print(f"Evaluation result: {evaluated_quality:.3f}")

        return {
            "quality": evaluated_quality,
            "iteration": iteration,
            "evaluation_complete": True,
        }

    workflow.add_node(
        "evaluator",
        PythonCodeNode.from_function(
            func=evaluate_solution,
            name="evaluator",
            description="Evaluate the optimized solution",
        ),
    )

    # Use optimization cycle template
    opt_cycle_id = workflow.add_optimization_cycle(
        processor_node="optimizer",
        evaluator_node="evaluator",
        convergence="quality > 0.9",
        max_iterations=20,
    )
    print(f"✅ Created optimization cycle: {opt_cycle_id}")

    # 2. Retry Cycle Template
    print("\n2️⃣ Retry Cycle Template")
    print("-" * 40)

    # Define unreliable API function (better IDE support)
    def simulate_unreliable_api(attempt=None, **kwargs):
        """Simulate API that fails 70% of the time initially, improves with retries."""
        import random

        # Get retry attempt info
        if attempt is None:
            attempt = 1

        # Simulate API that fails 70% of the time initially, improves with retries
        failure_rate = max(0.1, 0.7 - (attempt * 0.15))
        success = random.random() > failure_rate

        if success:
            print(f"✅ API call succeeded on attempt {attempt}")
            return {
                "success": True,
                "data": f"api_response_attempt_{attempt}",
                "attempt": attempt,
            }
        else:
            print(f"❌ API call failed on attempt {attempt}")
            return {
                "success": False,
                "error": f"API timeout on attempt {attempt}",
                "attempt": attempt,
            }

    workflow.add_node(
        "unreliable_api",
        PythonCodeNode.from_function(
            func=simulate_unreliable_api,
            name="unreliable_api",
            description="Simulate API with retry logic",
        ),
    )

    retry_cycle_id = workflow.add_retry_cycle(
        target_node="unreliable_api",
        max_retries=5,
        backoff_strategy="exponential",
        success_condition="success == True",
    )
    print(f"✅ Created retry cycle: {retry_cycle_id}")

    # 3. Data Quality Cycle Template
    print("\n3️⃣ Data Quality Cycle Template")
    print("-" * 40)

    workflow.add_node(
        "data_cleaner",
        PythonCodeNode.from_function(func=clean_data, name="data_cleaner"),
    )

    workflow.add_node(
        "quality_validator",
        PythonCodeNode.from_function(func=validate_quality, name="quality_validator"),
    )

    quality_cycle_id = workflow.add_data_quality_cycle(
        cleaner_node="data_cleaner",
        validator_node="quality_validator",
        quality_threshold=0.95,
        max_iterations=15,
    )
    print(f"✅ Created data quality cycle: {quality_cycle_id}")

    # 4. Learning Cycle Template
    print("\n4️⃣ Learning Cycle Template")
    print("-" * 40)

    workflow.add_node(
        "model_trainer",
        PythonCodeNode.from_function(func=train_model, name="model_trainer"),
    )

    workflow.add_node(
        "model_evaluator",
        PythonCodeNode.from_function(func=evaluate_model, name="model_evaluator"),
    )

    learning_cycle_id = workflow.add_learning_cycle(
        trainer_node="model_trainer",
        evaluator_node="model_evaluator",
        target_accuracy=0.95,
        max_epochs=30,
        early_stopping_patience=5,
    )
    print(f"✅ Created learning cycle: {learning_cycle_id}")

    # 5. Convergence Cycle Template
    print("\n5️⃣ Convergence Cycle Template")
    print("-" * 40)

    workflow.add_node(
        "numerical_solver",
        PythonCodeNode.from_function(func=numerical_solver, name="numerical_solver"),
    )

    convergence_cycle_id = workflow.add_convergence_cycle(
        processor_node="numerical_solver", tolerance=0.001, max_iterations=20
    )
    print(f"✅ Created convergence cycle: {convergence_cycle_id}")

    # 6. Batch Processing Cycle Template
    print("\n6️⃣ Batch Processing Cycle Template")
    print("-" * 40)

    workflow.add_node(
        "batch_processor",
        PythonCodeNode.from_function(func=process_batch, name="batch_processor"),
    )

    batch_cycle_id = workflow.add_batch_processing_cycle(
        processor_node="batch_processor", batch_size=10, total_items=50
    )
    print(f"✅ Created batch processing cycle: {batch_cycle_id}")

    print("\n🎉 Created 6 different cycle templates successfully!")

    # Execute a sample cycle to demonstrate
    print("\n🚀 Executing optimization cycle example...")
    runtime = LocalRuntime()
    try:
        results, run_id = runtime.execute(
            workflow, parameters={"optimizer": {"quality": 0.1, "iteration": 0}}
        )

        final_result = results.get("evaluator", {})
        if isinstance(final_result, dict) and "result" in final_result:
            final_quality = final_result["result"].get("quality", 0)
            final_iteration = final_result["result"].get("iteration", 0)
            print(
                f"✅ Optimization completed: quality = {final_quality:.3f} in {final_iteration} iterations"
            )
        else:
            print("✅ Cycle execution completed successfully")
    except Exception as e:
        print(f"⚠️ Execution error (expected in demo): {e}")

    return workflow


def demonstrate_migration_helpers():
    """Demonstrate DAG to cycle migration helpers."""
    print("\n" + "=" * 60)
    print("🔄 PHASE 5.3: MIGRATION HELPERS DEMONSTRATION")
    print("=" * 60)

    # Create a sample DAG workflow that could benefit from cyclification
    dag_workflow = Workflow("dag_example", "DAG Example for Migration")

    # Add nodes that look like they could be cycles
    dag_workflow.add_node(
        "data_processor", PythonCodeNode(name="data_processor", code="# Process data")
    )
    dag_workflow.add_node(
        "quality_checker",
        PythonCodeNode(name="quality_checker", code="# Check quality"),
    )
    dag_workflow.add_node(
        "api_caller", PythonCodeNode(name="api_caller", code="# Call API")
    )
    dag_workflow.add_node(
        "retry_handler", PythonCodeNode(name="retry_handler", code="# Handle retries")
    )
    dag_workflow.add_node(
        "optimizer", PythonCodeNode(name="optimizer", code="# Optimize solution")
    )
    dag_workflow.add_node(
        "evaluator", PythonCodeNode(name="evaluator", code="# Evaluate quality")
    )
    dag_workflow.add_node(
        "batch_reader", PythonCodeNode(name="batch_reader", code="# Read batch")
    )
    dag_workflow.add_node(
        "convergence_checker",
        PythonCodeNode(name="convergence_checker", code="# Check convergence"),
    )

    # Connect nodes in patterns that suggest cycles
    dag_workflow.connect("data_processor", "quality_checker")
    dag_workflow.connect("api_caller", "retry_handler")
    dag_workflow.connect("optimizer", "evaluator")
    dag_workflow.connect("batch_reader", "data_processor")
    dag_workflow.connect("convergence_checker", "optimizer")

    print("🔍 Analyzing DAG workflow for cyclification opportunities...")

    # Create migration converter
    converter = DAGToCycleConverter(dag_workflow)

    # Analyze opportunities
    opportunities = converter.analyze_cyclification_opportunities()

    print(f"\n📊 Found {len(opportunities)} cyclification opportunities:")
    print("-" * 50)

    for i, opp in enumerate(opportunities, 1):
        print(f"{i}. {opp.pattern_type.upper()}")
        print(f"   Nodes: {', '.join(opp.nodes)}")
        print(f"   Confidence: {opp.confidence:.1%}")
        print(f"   Description: {opp.description}")
        print(f"   Suggested convergence: {opp.suggested_convergence}")
        print(f"   Estimated benefit: {opp.estimated_benefit}")
        print(f"   Complexity: {opp.implementation_complexity}")
        print()

    # Generate detailed suggestions
    print("💡 Generating detailed implementation suggestions...")
    suggestions = converter.generate_detailed_suggestions()

    if suggestions:
        print("\n📋 Detailed suggestions for top opportunity:")
        print("-" * 50)
        top_suggestion = suggestions[0]

        print(f"Pattern: {top_suggestion.opportunity.pattern_type}")
        print(f"Expected outcome: {top_suggestion.expected_outcome}")
        print("\nImplementation steps:")
        for step in top_suggestion.implementation_steps:
            print(f"  • {step}")

        print("\nCode example:")
        print(top_suggestion.code_example)

        print("Risks to consider:")
        for risk in top_suggestion.risks:
            print(f"  ⚠️ {risk}")

    # Generate comprehensive migration report
    print("\n📈 Generating comprehensive migration report...")
    report = converter.generate_migration_report()

    print("\n📊 Migration Report Summary:")
    print("-" * 30)
    summary = report["summary"]
    print(f"Total opportunities: {summary['total_opportunities']}")
    print(f"High confidence: {summary['high_confidence']}")
    print(f"Medium confidence: {summary['medium_confidence']}")
    print(f"Low confidence: {summary['low_confidence']}")

    print("\nPattern distribution:")
    for pattern, count in summary["pattern_distribution"].items():
        print(f"  {pattern}: {count}")

    print("\nRecommendations:")
    for rec in report["recommendations"]:
        print(f"  💡 {rec}")

    print("\nSuggested implementation order:")
    for item in report["implementation_order"][:3]:  # Show top 3
        print(
            f"  {item['priority']}. {item['pattern_type']} (confidence: {item['confidence']:.1%})"
        )
        print(f"     {item['justification']}")

    # Demonstrate automatic conversion
    if opportunities:
        print("\n🔧 Demonstrating automatic conversion...")
        top_opportunity = opportunities[0]

        try:
            if len(top_opportunity.nodes) >= 2:
                cycle_id = converter.convert_to_cycle(
                    nodes=top_opportunity.nodes[:2],
                    convergence_strategy="quality_improvement",
                    max_iterations=10,
                )
                print(f"✅ Successfully converted to cycle: {cycle_id}")
            else:
                print(
                    "ℹ️ Single-node opportunity - conversion would require different strategy"
                )
        except Exception as e:
            print(f"⚠️ Conversion error (expected in demo): {e}")

    return converter


def demonstrate_validation_linting():
    """Demonstrate cycle validation and linting tools."""
    print("\n" + "=" * 60)
    print("🔍 PHASE 5.3: VALIDATION & LINTING DEMONSTRATION")
    print("=" * 60)

    # Create a workflow with various issues for linting
    problematic_workflow = Workflow(
        "problematic_cycles", "Problematic Cycles for Linting"
    )

    # 1. Cycle without convergence condition (should trigger warning)
    problematic_workflow.add_node(
        "no_convergence",
        PythonCodeNode(name="no_convergence", code="result = {'data': 'processed'}"),
    )
    # This will fail as expected - cycles need max_iterations or convergence_check
    try:
        problematic_workflow.connect("no_convergence", "no_convergence", cycle=True)
    except Exception as e:
        print(f"Expected error for cycle without config: {e}")
        # Fix it by adding max_iterations
        problematic_workflow.connect(
            "no_convergence", "no_convergence", cycle=True, max_iterations=10
        )

    # 2. Cycle with potentially infinite loop
    problematic_workflow.add_node(
        "infinite_risk",
        PythonCodeNode(name="infinite_risk", code="result = {'done': False}"),
    )  # Never True
    problematic_workflow.connect(
        "infinite_risk",
        "infinite_risk",
        cycle=True,
        max_iterations=100000,  # Very high
        convergence_check="done == True",
    )  # Never achieved

    # 3. Cycle without safety limits
    problematic_workflow.add_node(
        "no_safety", PythonCodeNode(name="no_safety", code="result = {'value': 1}")
    )
    problematic_workflow.connect(
        "no_safety", "no_safety", cycle=True, convergence_check="value > 0.9"
    )  # No timeout/memory limit

    # 4. Cycle with identity parameter mapping
    problematic_workflow.add_node(
        "bad_mapping",
        PythonCodeNode(name="bad_mapping", code="result = {'count': count + 1}"),
    )
    problematic_workflow.connect(
        "bad_mapping",
        "bad_mapping",
        cycle=True,
        mapping={"count": "count"},  # Identity mapping (wrong)
        max_iterations=10,
    )

    # 5. Expensive operation in cycle
    problematic_workflow.add_node(
        "expensive_api_call",
        PythonCodeNode(
            name="expensive_api_call",
            code="import time; time.sleep(1); result = {'data': 'api_result'}",
        ),
    )
    problematic_workflow.connect(
        "expensive_api_call", "expensive_api_call", cycle=True, max_iterations=100
    )  # Expensive operation repeated many times

    # 6. PythonCodeNode with unsafe parameter access
    problematic_workflow.add_node(
        "unsafe_params",
        PythonCodeNode(
            name="unsafe_params",
            code="""
# Direct parameter access without try/except (will fail on first iteration)
current_value = previous_value + 1  # NameError on first iteration
result = {"value": current_value}
""",
        ),
    )
    problematic_workflow.connect(
        "unsafe_params",
        "unsafe_params",
        cycle=True,
        mapping={"result.value": "previous_value"},
        max_iterations=5,
    )

    print("🔍 Running comprehensive cycle validation...")

    # Create linter and run all checks
    linter = CycleLinter(problematic_workflow)
    issues = linter.check_all()

    print(f"\n🚨 Found {len(issues)} validation issues:")
    print("=" * 50)

    # Display issues by severity
    errors = linter.get_issues_by_severity(IssueSeverity.ERROR)
    warnings = linter.get_issues_by_severity(IssueSeverity.WARNING)
    info = linter.get_issues_by_severity(IssueSeverity.INFO)

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        print("-" * 20)
        for error in errors:
            print(f"  [{error.code}] {error.message}")
            if error.node_id:
                print(f"      Node: {error.node_id}")
            if error.cycle_id:
                print(f"      Cycle: {error.cycle_id}")
            if error.suggestion:
                print(f"      💡 Suggestion: {error.suggestion}")
            print()

    if warnings:
        print(f"\n⚠️ WARNINGS ({len(warnings)}):")
        print("-" * 20)
        for warning in warnings:
            print(f"  [{warning.code}] {warning.message}")
            if warning.node_id:
                print(f"      Node: {warning.node_id}")
            if warning.cycle_id:
                print(f"      Cycle: {warning.cycle_id}")
            if warning.suggestion:
                print(f"      💡 Suggestion: {warning.suggestion}")
            print()

    if info:
        print(f"\nℹ️ INFORMATION ({len(info)}):")
        print("-" * 20)
        for info_item in info:
            print(f"  [{info_item.code}] {info_item.message}")
            if info_item.suggestion:
                print(f"      💡 Suggestion: {info_item.suggestion}")
            print()

    # Display issues by category
    print("\n📊 Issues by Category:")
    print("-" * 25)
    categories = set(issue.category for issue in issues)
    for category in sorted(categories):
        category_issues = linter.get_issues_by_category(category)
        print(f"  {category}: {len(category_issues)} issues")

    # Generate comprehensive report
    print("\n📋 Generating comprehensive validation report...")
    report = linter.generate_report()

    print("\n📈 Validation Report Summary:")
    print("-" * 30)
    summary = report["summary"]
    print(f"Total issues: {summary['total_issues']}")
    print(f"Errors: {summary['errors']}")
    print(f"Warnings: {summary['warnings']}")
    print(f"Info: {summary['info']}")
    print(f"Affected cycles: {summary['affected_cycles']}")

    print("\nTop recommendations:")
    for rec in report["recommendations"]:
        print(f"  🎯 {rec}")

    # Demonstrate issue filtering
    print("\n🔍 Demonstrating issue filtering...")
    convergence_issues = linter.get_issues_by_category("convergence")
    print(f"Convergence issues: {len(convergence_issues)}")

    performance_issues = linter.get_issues_by_category("performance")
    print(f"Performance issues: {len(performance_issues)}")

    safety_issues = linter.get_issues_by_category("safety")
    print(f"Safety issues: {len(safety_issues)}")

    return linter


def main():
    """Run comprehensive Phase 5.3 demonstration."""
    print("🚀 PHASE 5.3: HELPER METHODS & COMMON PATTERNS")
    print("🚀 Comprehensive Feature Demonstration")
    print("🚀 " + "=" * 54)

    try:
        # 1. Demonstrate cycle templates
        demonstrate_cycle_templates()

        # 2. Demonstrate migration helpers
        demonstrate_migration_helpers()

        # 3. Demonstrate validation and linting
        demonstrate_validation_linting()

        print("\n" + "=" * 60)
        print("🎉 PHASE 5.3 DEMONSTRATION COMPLETE")
        print("=" * 60)
        print("\n✅ Successfully demonstrated:")
        print("   • 6 Cycle Template patterns")
        print("   • DAG to Cycle migration analysis")
        print("   • Comprehensive workflow validation")
        print("   • Automated issue detection and suggestions")
        print("\n🚀 Phase 5.3 Helper Methods & Common Patterns ready for production!")

    except Exception as e:
        print(f"\n❌ Error during demonstration: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
