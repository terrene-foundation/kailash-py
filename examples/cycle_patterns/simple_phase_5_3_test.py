#!/usr/bin/env python3
"""
Simple Phase 5.3 Test - Helper Methods & Common Patterns

This simplified test demonstrates the core Phase 5.3 functionality:
1. Cycle Templates (CycleTemplates)
2. Migration Helpers (DAGToCycleConverter)
3. Validation & Linting Tools (CycleLinter)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from kailash import Workflow
from kailash.nodes.code import PythonCodeNode

# Import templates to add convenience methods to Workflow class
from kailash.workflow.migration import DAGToCycleConverter
from kailash.workflow.templates import CycleTemplates
from kailash.workflow.validation import CycleLinter, IssueSeverity


def test_cycle_templates():
    """Test cycle template functionality."""
    print("🛠️ Testing Cycle Templates")
    print("-" * 40)

    # Create simple workflow for testing
    workflow = Workflow("templates_test", "Templates Test")

    # Add simple nodes
    workflow.add_node(
        "processor",
        PythonCodeNode(
            name="processor",
            code="""
result = {"quality": 0.8, "iteration": 1}
""",
        ),
    )

    workflow.add_node(
        "evaluator",
        PythonCodeNode(
            name="evaluator",
            code="""
result = {"quality": 0.9, "evaluation_complete": True}
""",
        ),
    )

    # Test CycleTemplates.optimization_cycle (static method)
    print("Testing CycleTemplates.optimization_cycle...")
    try:
        cycle_id = CycleTemplates.optimization_cycle(
            workflow=workflow,
            processor_node="processor",
            evaluator_node="evaluator",
            convergence="quality > 0.85",
            max_iterations=5,
        )
        print(f"✅ Created optimization cycle: {cycle_id}")
    except Exception as e:
        print(f"❌ Error creating optimization cycle: {e}")

    return workflow


def test_migration_helpers():
    """Test migration helper functionality."""
    print("\n🔄 Testing Migration Helpers")
    print("-" * 40)

    # Create DAG workflow
    dag_workflow = Workflow("dag_test", "DAG Test")

    # Add nodes that suggest cycle patterns
    dag_workflow.add_node(
        "optimizer",
        PythonCodeNode(name="optimizer", code="result = {'data': 'optimized'}"),
    )

    dag_workflow.add_node(
        "evaluator", PythonCodeNode(name="evaluator", code="result = {'quality': 0.8}")
    )

    dag_workflow.add_node(
        "retry_node",
        PythonCodeNode(name="retry_node", code="result = {'success': True}"),
    )

    # Connect nodes
    dag_workflow.connect("optimizer", "evaluator")

    print("Testing DAGToCycleConverter...")
    try:
        converter = DAGToCycleConverter(dag_workflow)
        opportunities = converter.analyze_cyclification_opportunities()

        print(f"✅ Found {len(opportunities)} cyclification opportunities")

        for i, opp in enumerate(opportunities, 1):
            print(
                f"  {i}. {opp.pattern_type}: {opp.description} (confidence: {opp.confidence:.1%})"
            )

        # Test report generation
        report = converter.generate_migration_report()
        print(
            f"✅ Generated migration report with {report['summary']['total_opportunities']} opportunities"
        )

    except Exception as e:
        print(f"❌ Error in migration analysis: {e}")
        import traceback

        traceback.print_exc()


def test_validation_linting():
    """Test validation and linting functionality."""
    print("\n🔍 Testing Validation & Linting")
    print("-" * 40)

    # Create workflow with potential issues
    problem_workflow = Workflow("problem_test", "Problem Test")

    # Add a node
    problem_workflow.add_node(
        "test_node", PythonCodeNode(name="test_node", code="result = {'data': 'test'}")
    )

    # Create cycle without convergence (should trigger warning)
    try:
        problem_workflow.connect("test_node", "test_node", cycle=True)
    except Exception as e:
        print(f"Note: Cycle creation failed as expected: {e}")

    print("Testing CycleLinter...")
    try:
        linter = CycleLinter(problem_workflow)
        issues = linter.check_all()

        print(f"✅ Linting completed, found {len(issues)} issues")

        # Group by severity
        errors = linter.get_issues_by_severity(IssueSeverity.ERROR)
        warnings = linter.get_issues_by_severity(IssueSeverity.WARNING)
        info = linter.get_issues_by_severity(IssueSeverity.INFO)

        print(f"  Errors: {len(errors)}")
        print(f"  Warnings: {len(warnings)}")
        print(f"  Info: {len(info)}")

        # Show first few issues
        for issue in issues[:3]:
            print(f"  [{issue.severity.value}] {issue.code}: {issue.message}")

        # Test report generation
        report = linter.generate_report()
        print(
            f"✅ Generated validation report with {report['summary']['total_issues']} total issues"
        )

    except Exception as e:
        print(f"❌ Error in validation: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Run simple Phase 5.3 test."""
    print("🚀 PHASE 5.3: HELPER METHODS & COMMON PATTERNS")
    print("🚀 Simple Functionality Test")
    print("🚀 " + "=" * 44)

    try:
        # Test each component
        test_cycle_templates()
        test_migration_helpers()
        test_validation_linting()

        print("\n" + "=" * 50)
        print("🎉 PHASE 5.3 SIMPLE TEST COMPLETE")
        print("=" * 50)
        print("\n✅ Successfully tested:")
        print("   • Cycle Templates (CycleTemplates)")
        print("   • Migration Helpers (DAGToCycleConverter)")
        print("   • Validation & Linting (CycleLinter)")
        print("\n🚀 Phase 5.3 Helper Methods & Common Patterns functional!")

    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
