"""
Comprehensive QA Test Suite for Admin Framework

This runs all QA agents in sequence to thoroughly test the admin system.
"""

import json
import os
from datetime import datetime

from chaos_qa_agent import create_chaos_qa_workflow
from interactive_qa_agent import create_interactive_qa_workflow

# Import our QA workflows
from qa_llm_agent_test import create_qa_agent_workflow

from examples.utils.data_paths import ensure_output_dir_exists, get_output_data_path
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode, WorkflowNode
from kailash.workflow import Workflow, WorkflowBuilder


def create_test_summary_node():
    """Create a node that summarizes all test results"""

    def summarize_test_results(
        qa_agent_results=None, interactive_results=None, chaos_results=None, **kwargs
    ):
        """Summarize results from all test suites"""

        # Get results from all test suites
        qa_results = qa_agent_results or {}
        interactive_results = interactive_results or {}
        chaos_results = chaos_results or {}

        # Extract key metrics
        summary = {
            "test_date": datetime.now().isoformat(),
            "test_suites_run": 3,
            "overall_status": "FAILED",
            "test_metrics": {
                "qa_agent": {
                    "status": "completed" if qa_results else "failed",
                    "issues_found": qa_results.get("total_issues", 0),
                },
                "interactive": {
                    "status": "completed" if interactive_results else "failed",
                    "tests_run": interactive_results.get("summary", {}).get("total", 0),
                    "tests_passed": interactive_results.get("summary", {}).get(
                        "passed", 0
                    ),
                    "tests_failed": interactive_results.get("summary", {}).get(
                        "failed", 0
                    ),
                    "pass_rate": 0,
                },
                "chaos": {
                    "status": "completed" if chaos_results else "failed",
                    "attacks_executed": chaos_results.get("metrics", {}).get(
                        "total_attacks", 0
                    ),
                    "exploits_found": chaos_results.get("metrics", {}).get(
                        "successful_exploits", 0
                    ),
                    "security_grade": chaos_results.get("metrics", {}).get(
                        "security_grade", "?"
                    ),
                    "chaos_score": chaos_results.get("metrics", {}).get(
                        "chaos_score", 0
                    ),
                },
            },
            "critical_findings": [],
            "recommendations": [],
        }

        # Calculate interactive pass rate
        if summary["test_metrics"]["interactive"]["tests_run"] > 0:
            summary["test_metrics"]["interactive"]["pass_rate"] = (
                summary["test_metrics"]["interactive"]["tests_passed"]
                / summary["test_metrics"]["interactive"]["tests_run"]
                * 100
            )

        # Determine overall status
        all_completed = all(
            suite["status"] == "completed" for suite in summary["test_metrics"].values()
        )

        high_pass_rate = summary["test_metrics"]["interactive"]["pass_rate"] >= 80
        good_security = summary["test_metrics"]["chaos"]["security_grade"] in ["A", "B"]
        few_exploits = summary["test_metrics"]["chaos"]["exploits_found"] < 5

        if all_completed and high_pass_rate and good_security and few_exploits:
            summary["overall_status"] = "PASSED"
        elif all_completed and high_pass_rate:
            summary["overall_status"] = "PASSED_WITH_WARNINGS"
        else:
            summary["overall_status"] = "FAILED"

        # Add critical findings
        if summary["test_metrics"]["chaos"]["exploits_found"] > 0:
            summary["critical_findings"].append(
                f"Security vulnerabilities found: {summary['test_metrics']['chaos']['exploits_found']} exploits"
            )

        if summary["test_metrics"]["interactive"]["pass_rate"] < 70:
            summary["critical_findings"].append(
                f"Low test pass rate: {summary['test_metrics']['interactive']['pass_rate']:.1f}%"
            )

        if summary["test_metrics"]["chaos"]["security_grade"] in ["D", "F"]:
            summary["critical_findings"].append(
                f"Poor security grade: {summary['test_metrics']['chaos']['security_grade']}"
            )

        # Add recommendations
        summary["recommendations"].extend(
            [
                "Review and fix all failed test cases",
                "Address security vulnerabilities immediately",
                "Implement additional input validation",
                "Add comprehensive error handling",
                "Enhance authentication mechanisms",
                "Improve audit logging coverage",
                "Set up continuous security monitoring",
                "Create automated regression testing",
                "Implement proper rate limiting",
                "Add data encryption at rest and in transit",
                "Establish backup and recovery procedures",
                "Conduct regular penetration testing",
                "Establish security incident response procedures",
            ]
        )

        # Generate comprehensive report
        report_lines = [
            "# 📊 COMPREHENSIVE QA TEST SUITE REPORT",
            "",
            f"**Generated**: {summary['test_date']}",
            f"**Overall Status**: {summary['overall_status']}",
            "",
            "## Test Suite Summary",
            "",
            "### 1. QA Agent Analysis",
            f"- **Status**: {summary['test_metrics']['qa_agent']['status']}",
            f"- **Issues Found**: {summary['test_metrics']['qa_agent']['issues_found']}",
            "",
            "### 2. Interactive Testing",
            f"- **Status**: {summary['test_metrics']['interactive']['status']}",
            f"- **Tests Run**: {summary['test_metrics']['interactive']['tests_run']}",
            f"- **Pass Rate**: {summary['test_metrics']['interactive']['pass_rate']:.1f}%",
            f"- **Failed Tests**: {summary['test_metrics']['interactive']['tests_failed']}",
            "",
            "### 3. Chaos Testing",
            f"- **Status**: {summary['test_metrics']['chaos']['status']}",
            f"- **Security Grade**: {summary['test_metrics']['chaos']['security_grade']}",
            f"- **Chaos Score**: {summary['test_metrics']['chaos']['chaos_score']:.1f}%",
            f"- **Exploits Found**: {summary['test_metrics']['chaos']['exploits_found']}",
            "",
            "## Critical Findings",
            "",
        ]

        for finding in summary["critical_findings"]:
            report_lines.append(f"- ⚠️  {finding}")

        report_lines.extend(["", "## Recommendations", ""])

        for i, rec in enumerate(summary["recommendations"], 1):
            report_lines.append(f"{i}. {rec}")

        report = "\n".join(report_lines)

        production_status = (
            "ready for production"
            if summary["overall_status"] == "PASSED"
            else "NOT ready for production"
        )
        status_message = (
            "🎉 Congratulations! The system passed comprehensive QA testing."
            if summary["overall_status"] == "PASSED"
            else "❌ Critical issues must be resolved before deployment."
        )

        report += f"""

## Next Steps

Based on the test results, the admin framework is {production_status}.

{status_message}

---
*Full detailed reports available in individual test suite outputs*
"""

        return {"result": {"summary": summary, "report": report}}

    return PythonCodeNode.from_function(
        name="test_summary_generator", func=summarize_test_results
    )


def create_comprehensive_qa_workflow():
    """Create a workflow that runs all QA test suites"""
    wb = WorkflowBuilder(name="comprehensive_admin_qa_suite")

    # Create workflow nodes for each test suite
    qa_agent_suite = WorkflowNode(
        name="qa_agent_test_suite", workflow=create_qa_agent_workflow()
    )

    interactive_suite = WorkflowNode(
        name="interactive_test_suite", workflow=create_interactive_qa_workflow()
    )

    chaos_suite = WorkflowNode(
        name="chaos_test_suite", workflow=create_chaos_qa_workflow()
    )

    # Add test suite nodes
    wb.add_node(qa_agent_suite)
    wb.add_node(interactive_suite)
    wb.add_node(chaos_suite)

    # Extract results from each suite
    qa_results_extractor = PythonCodeNode(
        name="extract_qa_results",
        code="""
# Extract QA agent results
merge_results = input_data.get("merge_test_results", {})
qa_report = merge_results.get("qa_report", {})

result = {
    "total_issues": qa_report.get("data", {}).get("total_issues", 0),
    "severity_summary": qa_report.get("data", {}).get("severity_summary", {}),
    "report": qa_report.get("report", "No report available")
}
""",
    )

    interactive_results_extractor = PythonCodeNode(
        name="extract_interactive_results",
        code="""
# Extract interactive test results
report_data = input_data.get("report_generator", {})

result = {
    "summary": report_data.get("summary", {}),
    "report": report_data.get("report", "No report available")
}
""",
    )

    chaos_results_extractor = PythonCodeNode(
        name="extract_chaos_results",
        code="""
# Extract chaos test results
chaos_report = input_data.get("chaos_report_generator", {})

result = {
    "metrics": chaos_report.get("metrics", {}),
    "report": chaos_report.get("report", "No report available")
}
""",
    )

    wb.add_node(qa_results_extractor)
    wb.add_node(interactive_results_extractor)
    wb.add_node(chaos_results_extractor)

    # Connect extractors to test suites
    wb.connect(qa_agent_suite.name, qa_results_extractor.name, {"result": "input_data"})
    wb.connect(
        interactive_suite.name,
        interactive_results_extractor.name,
        {"result": "input_data"},
    )
    wb.connect(chaos_suite.name, chaos_results_extractor.name, {"result": "input_data"})

    # Merge all results
    merge_all_results = MergeNode(name="merge_all_test_results")
    wb.add_node(merge_all_results)

    wb.connect(
        qa_results_extractor.name,
        merge_all_results.name,
        {"result": "qa_agent_results"},
    )
    wb.connect(
        interactive_results_extractor.name,
        merge_all_results.name,
        {"result": "interactive_results"},
    )
    wb.connect(
        chaos_results_extractor.name,
        merge_all_results.name,
        {"result": "chaos_results"},
    )

    # Generate final summary
    summary_generator = create_test_summary_node()
    wb.add_node(summary_generator)

    wb.connect(
        merge_all_results.name, summary_generator.name, {"merged_output": "input_data"}
    )

    # Save reports to files
    report_saver = PythonCodeNode(
        name="save_test_reports",
        code="""
import json
import os
from datetime import datetime

# Create output directory
from examples.utils.data_paths import get_output_data_path, ensure_output_dir_exists
output_dir = str(ensure_output_dir_exists("admin_qa_tests"))

# Extract data
summary_data = input_data.get("summary", {})
qa_results = input_data.get("qa_agent_results", {})
interactive_results = input_data.get("interactive_results", {})
chaos_results = input_data.get("chaos_results", {})

# Save comprehensive summary
with open(f"{output_dir}/test_summary.json", "w") as f:
    json.dump(summary_data, f, indent=2)

# Save comprehensive report
with open(f"{output_dir}/comprehensive_report.md", "w") as f:
    f.write(input_data.get("report", "No report generated"))

# Save individual reports
with open(f"{output_dir}/qa_agent_report.md", "w") as f:
    f.write(qa_results.get("report", "No QA agent report"))

with open(f"{output_dir}/interactive_test_report.md", "w") as f:
    f.write(interactive_results.get("report", "No interactive test report"))

with open(f"{output_dir}/chaos_test_report.md", "w") as f:
    f.write(chaos_results.get("report", "No chaos test report"))

result = {
    "output_directory": output_dir,
    "files_saved": [
        "test_summary.json",
        "comprehensive_report.md",
        "qa_agent_report.md",
        "interactive_test_report.md",
        "chaos_test_report.md"
    ]
}
""",
    )

    wb.add_node(report_saver)

    # Connect summary to saver (include all data)
    merge_final = MergeNode(name="merge_for_saving")
    wb.add_node(merge_final)

    wb.connect(summary_generator.name, merge_final.name, {"result": "summary_data"})
    wb.connect(
        merge_all_results.name, merge_final.name, {"merged_output": "all_results"}
    )

    final_merge = PythonCodeNode(
        name="prepare_final_data",
        code="""
summary_data = input_data.get("summary_data", {})
all_results = input_data.get("all_results", {})

result = {
    **summary_data,
    **all_results
}
""",
    )
    wb.add_node(final_merge)

    wb.connect(merge_final.name, final_merge.name, {"merged_output": "input_data"})
    wb.connect(final_merge.name, report_saver.name, {"result": "input_data"})

    return wb.build()


def main():
    """Run comprehensive QA test suite"""
    print("🚀 LAUNCHING COMPREHENSIVE QA TEST SUITE FOR ADMIN FRAMEWORK")
    print("=" * 70)
    print("This will run multiple test suites:")
    print("1. QA Agent Analysis - Strategic testing approach")
    print("2. Interactive Testing - Functional test execution")
    print("3. Chaos Testing - Security and stress testing")
    print("=" * 70)

    workflow = create_comprehensive_qa_workflow()

    print("\n⏳ Starting test execution (this may take several minutes)...")
    print("\n" + "." * 70)

    result = workflow.run()

    if result.is_success:
        # Get final results
        summary_data = result.node_results.get("test_summary_generator", {})
        save_results = result.node_results.get("save_test_reports", {})

        if "report" in summary_data:
            print("\n" + summary_data["report"])

        if save_results and "output_directory" in save_results:
            print(f"\n📁 Test reports saved to: {save_results['output_directory']}")
            print("\nFiles created:")
            for file in save_results.get("files_saved", []):
                print(f"  - {file}")

        # Show pass/fail status with emoji
        overall_status = summary_data.get("summary", {}).get(
            "overall_status", "UNKNOWN"
        )
        if overall_status == "PASSED":
            print(
                "\n✅ 🎉 ALL TESTS PASSED! The admin framework is ready for production! 🎉 ✅"
            )
        elif overall_status == "PASSED_WITH_WARNINGS":
            print("\n⚠️  Tests passed with warnings. Review findings before deployment.")
        else:
            print(
                "\n❌ TESTS FAILED! Critical issues must be resolved before deployment. ❌"
            )

    else:
        print(f"\n❌ Test suite execution failed: {result.error}")
        print("Please check the workflow configuration and try again.")


if __name__ == "__main__":
    main()
