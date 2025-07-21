#!/usr/bin/env python3
"""
Phase 5.3 Simple Production Example

Demonstrates production-ready cycle patterns without external dependencies
that might conflict with PythonCodeNode security restrictions.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

# Import templates to add convenience methods to Workflow class
from kailash import Workflow
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime


def clean_text(data=None, iteration=None, quality_score=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    import re

    # Handle input data
    try:
        text = data.get("text", "") if isinstance(data, dict) else str(data)
        iteration = iteration
    except:
        # First iteration
        text = "  Hello,   WORLD!  This is a TEST...   with BAD formatting!!!  "
        iteration = 0

    iteration += 1
    print(f"\\nText Cleaning Iteration {iteration}")
    print(f"Input: '{text}'")

    # Perform cleaning operations
    cleaned = text

    # 1. Strip whitespace
    cleaned = cleaned.strip()

    # 2. Normalize spaces
    cleaned = re.sub(r"\\s+", " ", cleaned)

    # 3. Fix punctuation spacing
    cleaned = re.sub(r"\\s+([.,!?])", r"\\1", cleaned)
    cleaned = re.sub(r"([.,!?])([A-Za-z])", r"\\1 \\2", cleaned)

    # 4. Normalize case (if too much uppercase)
    words = cleaned.split()
    uppercase_count = sum(1 for w in words if w.isupper() and len(w) > 1)
    if uppercase_count > len(words) * 0.3:  # More than 30% uppercase
        cleaned = " ".join(w.capitalize() if w.isupper() else w for w in words)

    # Calculate quality improvement
    original_issues = 0
    if text != text.strip():
        original_issues += 1
    if "  " in text:
        original_issues += 1
    if uppercase_count > len(words) * 0.3:
        original_issues += 1

    quality_score = 1.0 - (original_issues * 0.25)
    quality_score = max(0.0, min(1.0, quality_score))

    print(f"Output: '{cleaned}'")
    print(f"Quality Score: {quality_score:.2f}")

    result = {
        "text": cleaned,
        "quality_score": quality_score,
        "iteration": iteration,
        "improvements": original_issues,
    }

    return result


def validate_text(data=None, iteration=None, quality_score=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""

    # Get cleaned text and metadata
    try:
        if isinstance(data, dict):
            text = data.get("text", "")
            quality_score = data.get("quality_score", 0.0)
            iteration = data.get("iteration", 0)
        else:
            text = str(data)
            quality_score = 0.0
            iteration = 0
    except:
        text = ""
        quality_score = 0.0
        iteration = 0

    print(f"\\nValidating Text - Iteration {iteration}")

    # Validation checks
    issues = []

    # 1. Check for multiple spaces
    if "  " in text:
        issues.append("Multiple consecutive spaces found")

    # 2. Check for leading/trailing whitespace
    if text != text.strip():
        issues.append("Leading or trailing whitespace")

    # 3. Check punctuation spacing
    if re.search(r"\\s[.,!?]", text):
        issues.append("Space before punctuation")

    # 4. Check for excessive uppercase
    words = text.split()
    uppercase_words = [w for w in words if w.isupper() and len(w) > 1]
    if len(uppercase_words) > len(words) * 0.2:
        issues.append(f"Excessive uppercase words: {len(uppercase_words)}")

    # 5. Check for empty content
    if not text or not text.strip():
        issues.append("Empty or whitespace-only content")

    # Calculate final quality
    validation_score = 1.0 - (len(issues) * 0.2)
    validation_score = max(0.0, min(1.0, validation_score))

    final_quality = (quality_score + validation_score) / 2
    is_acceptable = final_quality >= 0.9 and len(issues) == 0

    print(f"Validation Score: {validation_score:.2f}")
    print(f"Issues Found: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")
    print(f"Final Quality: {final_quality:.2f}")
    print(f"Acceptable: {is_acceptable}")

    result = {
        "text": text,
        "quality_score": final_quality,
        "is_acceptable": is_acceptable,
        "iteration": iteration,
        "issues": issues,
    }

    return result


def calculator(iteration=None, **kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # Newton's method for calculating square root
    value = kwargs.get("value")
    target_value = kwargs.get("target_value")

    if value is None or target_value is None:
        # First iteration - calculate sqrt(10)
        x = 5.0  # Initial guess
        target = 10.0
        iteration = 0
    else:
        x = value
        target = target_value
        iteration = iteration if iteration is not None else 0

    iteration += 1

    # Newton's method: x_new = 0.5 * (x + target/x)
    x_new = 0.5 * (x + target / x)
    difference = abs(x_new - x)
    relative_error = difference / x if x != 0 else float("inf")

    # Check convergence
    converged = difference < 0.0001

    print(f"\\nIteration {iteration}: x = {x_new:.6f}")
    print(f"Difference: {difference:.6f}")
    print(f"Relative Error: {relative_error:.6f}")
    print(f"Converged: {converged}")

    # Verify result
    actual_sqrt = x_new * x_new
    print(f"x² = {actual_sqrt:.6f} (target: {target})")

    result = {
        "value": x_new,
        "target_value": target,
        "iteration": iteration,
        "difference": difference,
        "converged": converged,
        "accuracy": 1.0 - abs(actual_sqrt - target) / target,
    }

    return result


def process_batch(**kwargs):
    """Auto-converted from PythonCodeNode string code."""
    # Batch processing logic
    batch_number = kwargs.get("batch_number", 0)
    start_index = kwargs.get("start_index", 0)
    items_processed = kwargs.get("items_processed", 0)

    batch_number += 1
    batch_size = 10
    end_index = start_index + batch_size

    # Simulate processing items
    print(f"\\nProcessing Batch {batch_number}")
    print(f"Items {start_index} to {end_index - 1}")

    processed_items = []
    for i in range(start_index, end_index):
        # Simulate some processing
        item = f"item_{i:03d}"
        processed_value = i * 2 + 1
        processed_items.append(
            {"id": item, "original": i, "processed": processed_value}
        )
        print(f"  Processed {item}: {i} → {processed_value}")

    # Update counters
    items_processed += len(processed_items)
    total_items = 50  # Process 50 items total
    all_processed = items_processed >= total_items

    progress = (items_processed / total_items) * 100
    print(f"Progress: {progress:.1f}% ({items_processed}/{total_items})")

    result = {
        "batch_number": batch_number,
        "start_index": end_index,  # Next batch starts here
        "items_processed": items_processed,
        "all_processed": all_processed,
        "batch_data": processed_items,
        "progress": progress,
    }

    return result


def create_text_processing_workflow():
    """Create a text processing workflow with quality improvement cycle."""
    print("\n📝 Creating Text Processing Workflow")
    print("=" * 50)

    workflow = Workflow("text_processing", "Text Processing with Quality Cycle")

    # Text cleaner node
    workflow.add_node(
        "text_cleaner",
        PythonCodeNode.from_function(func=clean_text, name="text_cleaner"),
    )

    # Text validator node
    workflow.add_node(
        "text_validator",
        PythonCodeNode.from_function(func=validate_text, name="text_validator"),
    )

    # Create data quality cycle
    cycle_id = workflow.add_data_quality_cycle(
        cleaner_node="text_cleaner",
        validator_node="text_validator",
        quality_threshold=0.9,
        max_iterations=5,
    )

    print(f"✅ Created data quality cycle: {cycle_id}")

    return workflow


def create_calculation_workflow():
    """Create a numerical calculation workflow with convergence."""
    print("\n🔢 Creating Calculation Workflow")
    print("=" * 50)

    workflow = Workflow("calculation", "Iterative Calculation with Convergence")

    # Add calculator node (Newton's method for square root)
    workflow.add_node(
        "calculator",
        PythonCodeNode.from_function(func=calculator, name="calculator"),
    )

    # Create convergence cycle
    cycle_id = workflow.add_convergence_cycle(
        processor_node="calculator", tolerance=0.0001, max_iterations=20
    )

    print(f"✅ Created convergence cycle: {cycle_id}")

    return workflow


def create_batch_workflow():
    """Create a batch processing workflow."""
    print("\n📦 Creating Batch Processing Workflow")
    print("=" * 50)

    workflow = Workflow("batch_processing", "Batch Processing Example")

    # Add batch processor
    workflow.add_node(
        "batch_processor",
        PythonCodeNode.from_function(func=process_batch, name="batch_processor"),
    )

    # Create batch processing cycle
    cycle_id = workflow.add_batch_processing_cycle(
        processor_node="batch_processor", batch_size=10, total_items=50
    )

    print(f"✅ Created batch processing cycle: {cycle_id}")

    return workflow


def main():
    """Run simple production examples."""
    print("🚀 PHASE 5.3: SIMPLE PRODUCTION EXAMPLES")
    print("🚀 Demonstrating cycle patterns without external dependencies")
    print("=" * 60)

    runtime = LocalRuntime()

    # 1. Text Processing Example
    text_workflow = create_text_processing_workflow()
    print("\n▶️ Executing Text Processing Workflow...")
    try:
        results, run_id = runtime.execute(text_workflow)

        if "text_validator" in results:
            final = results["text_validator"].get("result", {})
            print("\n✅ Text processing completed!")
            print(f"   Final text: '{final.get('text', '')}'")
            print(f"   Quality: {final.get('quality_score', 0):.2f}")
            print(f"   Iterations: {final.get('iteration', 0)}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 2. Calculation Example
    calc_workflow = create_calculation_workflow()
    print("\n▶️ Executing Calculation Workflow...")
    try:
        results, run_id = runtime.execute(calc_workflow)

        if "calculator" in results:
            final = results["calculator"].get("result", {})
            print("\n✅ Calculation completed!")
            print(f"   √10 ≈ {final.get('value', 0):.6f}")
            print(f"   Iterations: {final.get('iteration', 0)}")
            print(f"   Accuracy: {final.get('accuracy', 0):.1%}")
    except Exception as e:
        print(f"❌ Error: {e}")

    # 3. Batch Processing Example
    batch_workflow = create_batch_workflow()
    print("\n▶️ Executing Batch Processing Workflow...")
    try:
        results, run_id = runtime.execute(batch_workflow)

        if "batch_processor" in results:
            final = results["batch_processor"].get("result", {})
            print("\n✅ Batch processing completed!")
            print(f"   Total items: {final.get('items_processed', 0)}")
            print(f"   Batches: {final.get('batch_number', 0)}")
            print(f"   Progress: {final.get('progress', 0):.1f}%")
    except Exception as e:
        print(f"❌ Error: {e}")

    print("\n" + "=" * 60)
    print("🎉 SIMPLE PRODUCTION EXAMPLES COMPLETE")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
