"""
Quality Control Workflow

This workflow demonstrates quality control processing for manufacturing:
1. Reads production metrics from multiple lines
2. Calculates Six Sigma control limits
3. Identifies defect patterns and trends
4. Generates control charts and statistical analysis
5. Provides root cause analysis and recommendations

Real-world use case: Manufacturing quality assurance system that monitors
production lines, detects quality issues early, and provides actionable
recommendations to maintain production standards.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add the src directory to the path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../src"))
)

from typing import Any

from kailash.nodes import PythonCodeNode
from kailash.nodes.base import NodeParameter
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.workflow import Workflow

# Define data path utilities inline
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../../")
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def get_input_data_path(relative_path):
    """Get the full path for input data files."""
    return os.path.join(project_root, "data", "inputs", relative_path)


def get_output_data_path(relative_path):
    """Get the full path for output data files."""
    return os.path.join(project_root, "data", "outputs", relative_path)


def ensure_output_dir_exists():
    """Ensure output directory exists."""
    output_dir = os.path.join(
        project_root, "data", "outputs", "manufacturing", "quality"
    )
    os.makedirs(output_dir, exist_ok=True)


def calculate_six_sigma_metrics(production_data):
    """
    Calculate Six Sigma control limits and quality metrics.
    Returns the metrics list directly so PythonCodeNode can wrap it in {"result": metrics}.
    """
    from collections import defaultdict

    import numpy as np
    import pandas as pd

    # Convert to DataFrame
    df = pd.DataFrame(production_data)

    # Calculate metrics by production line
    line_metrics = defaultdict(dict)

    for line in df["production_line"].unique():
        line_data = df[df["production_line"] == line]

        # Convert string values to float for calculations
        efficiency = [float(x) for x in line_data["efficiency_percent"]]
        defect_rate = [
            float(x) / float(y) * 100
            for x, y in zip(line_data["defect_count"], line_data["units_produced"])
        ]
        cycle_time = [float(x) for x in line_data["cycle_time_seconds"]]

        # Calculate control limits (±3 sigma)
        efficiency_mean = np.mean(efficiency)
        efficiency_std = np.std(efficiency, ddof=1)
        efficiency_ucl = efficiency_mean + (3 * efficiency_std)
        efficiency_lcl = efficiency_mean - (3 * efficiency_std)

        defect_rate_mean = np.mean(defect_rate)
        defect_rate_std = np.std(defect_rate, ddof=1)
        defect_rate_ucl = defect_rate_mean + (3 * defect_rate_std)
        defect_rate_lcl = max(0, defect_rate_mean - (3 * defect_rate_std))

        cycle_time_mean = np.mean(cycle_time)
        cycle_time_std = np.std(cycle_time, ddof=1)
        cycle_time_ucl = cycle_time_mean + (3 * cycle_time_std)
        cycle_time_lcl = cycle_time_mean - (3 * cycle_time_std)

        # Calculate process capability (Cp and Cpk)
        # Assuming specification limits for demonstration
        efficiency_spec_lower = 85.0
        efficiency_spec_upper = 98.0
        cp_efficiency = (efficiency_spec_upper - efficiency_spec_lower) / (
            6 * efficiency_std
        )

        cpk_lower = (efficiency_mean - efficiency_spec_lower) / (3 * efficiency_std)
        cpk_upper = (efficiency_spec_upper - efficiency_mean) / (3 * efficiency_std)
        cpk_efficiency = min(cpk_lower, cpk_upper)

        # Identify out-of-control points
        out_of_control = []
        for i, row in line_data.iterrows():
            eff = float(row["efficiency_percent"])
            dr = float(row["defect_count"]) / float(row["units_produced"]) * 100
            ct = float(row["cycle_time_seconds"])

            issues = []
            if eff > efficiency_ucl or eff < efficiency_lcl:
                issues.append(f"Efficiency out of control: {eff:.1f}%")
            if dr > defect_rate_ucl:
                issues.append(f"Defect rate high: {dr:.2f}%")
            if ct > cycle_time_ucl or ct < cycle_time_lcl:
                issues.append(f"Cycle time out of control: {ct:.1f}s")

            if issues:
                out_of_control.append(
                    {
                        "date": row["date"],
                        "shift": row["shift"],
                        "operator_id": row["operator_id"],
                        "issues": issues,
                    }
                )

        line_metrics[line] = {
            "line_id": line,
            "sample_size": len(line_data),
            "efficiency": {
                "mean": round(efficiency_mean, 2),
                "std": round(efficiency_std, 2),
                "ucl": round(efficiency_ucl, 2),
                "lcl": round(efficiency_lcl, 2),
                "current": round(efficiency[-1], 2),
            },
            "defect_rate": {
                "mean": round(defect_rate_mean, 3),
                "std": round(defect_rate_std, 3),
                "ucl": round(defect_rate_ucl, 3),
                "lcl": round(defect_rate_lcl, 3),
                "current": round(defect_rate[-1], 3),
            },
            "cycle_time": {
                "mean": round(cycle_time_mean, 2),
                "std": round(cycle_time_std, 2),
                "ucl": round(cycle_time_ucl, 2),
                "lcl": round(cycle_time_lcl, 2),
                "current": round(cycle_time[-1], 2),
            },
            "process_capability": {
                "cp_efficiency": round(cp_efficiency, 3),
                "cpk_efficiency": round(cpk_efficiency, 3),
                "status": (
                    "excellent"
                    if cpk_efficiency >= 1.67
                    else "adequate" if cpk_efficiency >= 1.33 else "poor"
                ),
            },
            "out_of_control_points": out_of_control,
            "quality_score": round(
                max(
                    0,
                    100 - (defect_rate_mean * 10) - max(0, (cycle_time_mean - 45) * 2),
                ),
                1,
            ),
        }

    return list(line_metrics.values())


def analyze_defect_patterns(six_sigma_data):
    """
    Analyze defect patterns and identify trends.
    Returns the patterns dict directly so PythonCodeNode can wrap it in {"result": patterns}.
    """
    patterns = {
        "analysis_timestamp": datetime.now().isoformat(),
        "line_analysis": [],
        "overall_trends": {},
        "recommendations": [],
    }

    # Analyze each production line
    for line_data in six_sigma_data:
        line_id = line_data["line_id"]

        # Analyze defect patterns
        defect_issues = []
        efficiency_issues = []
        cycle_time_issues = []

        # Check for systematic issues
        if line_data["defect_rate"]["current"] > line_data["defect_rate"]["ucl"]:
            defect_issues.append("Defect rate exceeds upper control limit")

        if line_data["efficiency"]["current"] < line_data["efficiency"]["lcl"]:
            efficiency_issues.append("Efficiency below lower control limit")

        if line_data["cycle_time"]["current"] > line_data["cycle_time"]["ucl"]:
            cycle_time_issues.append("Cycle time exceeds upper control limit")

        # Process capability analysis
        capability_status = line_data["process_capability"]["status"]
        if capability_status == "poor":
            efficiency_issues.append("Process capability below acceptable levels")

        # Operator performance analysis
        operator_issues = {}
        for point in line_data["out_of_control_points"]:
            operator = point["operator_id"]
            if operator not in operator_issues:
                operator_issues[operator] = []
            operator_issues[operator].extend(point["issues"])

        line_analysis = {
            "line_id": line_id,
            "quality_score": line_data["quality_score"],
            "capability_status": capability_status,
            "defect_issues": defect_issues,
            "efficiency_issues": efficiency_issues,
            "cycle_time_issues": cycle_time_issues,
            "operator_performance": operator_issues,
            "out_of_control_count": len(line_data["out_of_control_points"]),
            "priority": (
                "high"
                if line_data["quality_score"] < 80
                else "medium" if line_data["quality_score"] < 90 else "low"
            ),
        }

        patterns["line_analysis"].append(line_analysis)

    # Overall trend analysis
    quality_scores = [line["quality_score"] for line in six_sigma_data]
    patterns["overall_trends"] = {
        "average_quality_score": round(sum(quality_scores) / len(quality_scores), 1),
        "lines_needing_attention": sum(1 for score in quality_scores if score < 85),
        "best_performing_line": max(six_sigma_data, key=lambda x: x["quality_score"])[
            "line_id"
        ],
        "worst_performing_line": min(six_sigma_data, key=lambda x: x["quality_score"])[
            "line_id"
        ],
    }

    # Generate recommendations
    for line_analysis in patterns["line_analysis"]:
        if line_analysis["priority"] == "high":
            patterns["recommendations"].append(
                {
                    "line_id": line_analysis["line_id"],
                    "priority": "IMMEDIATE",
                    "actions": [
                        "Stop production and investigate root causes",
                        "Review operator training and procedures",
                        "Inspect equipment for wear or malfunction",
                        "Implement corrective actions before restart",
                    ],
                }
            )
        elif line_analysis["priority"] == "medium":
            patterns["recommendations"].append(
                {
                    "line_id": line_analysis["line_id"],
                    "priority": "SCHEDULED",
                    "actions": [
                        "Schedule maintenance during next planned downtime",
                        "Review process parameters and adjust if needed",
                        "Provide additional operator training",
                        "Monitor closely for further degradation",
                    ],
                }
            )

    return patterns


def generate_quality_report(pattern_analysis):
    """
    Generate comprehensive quality control report.
    Returns the report dict directly so PythonCodeNode can wrap it in {"result": report}.
    """
    report = {
        "report_timestamp": datetime.now().isoformat(),
        "executive_summary": {
            "overall_status": "good",
            "lines_analyzed": len(pattern_analysis["line_analysis"]),
            "lines_needing_attention": pattern_analysis["overall_trends"][
                "lines_needing_attention"
            ],
            "average_quality_score": pattern_analysis["overall_trends"][
                "average_quality_score"
            ],
        },
        "detailed_analysis": pattern_analysis,
        "action_plan": {
            "immediate_actions": [],
            "scheduled_actions": [],
            "monitoring_plan": [],
        },
        "kpi_dashboard": {"quality_metrics": [], "trend_indicators": []},
    }

    # Determine overall status
    avg_score = pattern_analysis["overall_trends"]["average_quality_score"]
    if avg_score >= 90:
        report["executive_summary"]["overall_status"] = "excellent"
    elif avg_score >= 85:
        report["executive_summary"]["overall_status"] = "good"
    elif avg_score >= 75:
        report["executive_summary"]["overall_status"] = "acceptable"
    else:
        report["executive_summary"]["overall_status"] = "poor"

    # Build action plan
    for rec in pattern_analysis["recommendations"]:
        if rec["priority"] == "IMMEDIATE":
            report["action_plan"]["immediate_actions"].append(
                {"line": rec["line_id"], "actions": rec["actions"]}
            )
        else:
            report["action_plan"]["scheduled_actions"].append(
                {"line": rec["line_id"], "actions": rec["actions"]}
            )

    # Monitoring plan
    report["action_plan"]["monitoring_plan"] = [
        "Daily quality score tracking for all production lines",
        "Weekly Six Sigma control chart review",
        "Monthly process capability assessment",
        "Quarterly operator performance evaluation",
    ]

    # KPI Dashboard
    for line in pattern_analysis["line_analysis"]:
        report["kpi_dashboard"]["quality_metrics"].append(
            {
                "line_id": line["line_id"],
                "quality_score": line["quality_score"],
                "capability_status": line["capability_status"],
                "out_of_control_points": line["out_of_control_count"],
            }
        )

    report["kpi_dashboard"]["trend_indicators"] = [
        f"Best performing line: {pattern_analysis['overall_trends']['best_performing_line']}",
        f"Worst performing line: {pattern_analysis['overall_trends']['worst_performing_line']}",
        f"Lines requiring attention: {pattern_analysis['overall_trends']['lines_needing_attention']}",
    ]

    return report


def create_quality_control_workflow():
    """Create the quality control workflow."""

    # Create workflow
    workflow = Workflow(workflow_id="quality-control", name="Quality Control")

    # Add nodes

    # 1. Read production metrics
    workflow.add_node(
        "ProductionDataReader",
        CSVReaderNode(
            file_path=get_input_data_path("manufacturing/production_metrics.csv")
        ),
    )

    # 2. Calculate Six Sigma metrics
    workflow.add_node(
        "SixSigmaCalculator",
        PythonCodeNode.from_function(
            func=calculate_six_sigma_metrics, input_mapping={"production_data": "data"}
        ),
    )

    # 3. Analyze defect patterns
    workflow.add_node(
        "DefectPatternAnalyzer",
        PythonCodeNode.from_function(
            func=analyze_defect_patterns, input_mapping={"six_sigma_data": "result"}
        ),
    )

    # 4. Generate quality report
    workflow.add_node(
        "QualityReportGenerator",
        PythonCodeNode.from_function(
            func=generate_quality_report, input_mapping={"pattern_analysis": "result"}
        ),
    )

    # 5. Write Six Sigma data
    ensure_output_dir_exists()
    workflow.add_node(
        "SixSigmaDataWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/quality/six_sigma_analysis.json"
            )
        ),
    )

    # 6. Write pattern analysis
    workflow.add_node(
        "PatternAnalysisWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/quality/defect_pattern_analysis.json"
            )
        ),
    )

    # 7. Write quality report
    workflow.add_node(
        "QualityReportWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/quality/quality_control_report.json"
            )
        ),
    )

    # Connect the workflow
    workflow.connect(
        "ProductionDataReader", "SixSigmaCalculator", {"data": "production_data"}
    )
    workflow.connect("SixSigmaCalculator", "SixSigmaDataWriter", {"result": "data"})
    workflow.connect(
        "SixSigmaCalculator", "DefectPatternAnalyzer", {"result": "six_sigma_data"}
    )
    workflow.connect(
        "DefectPatternAnalyzer", "PatternAnalysisWriter", {"result": "data"}
    )
    workflow.connect(
        "DefectPatternAnalyzer",
        "QualityReportGenerator",
        {"result": "pattern_analysis"},
    )
    workflow.connect(
        "QualityReportGenerator", "QualityReportWriter", {"result": "data"}
    )

    # Validate workflow
    workflow.validate()

    return workflow


def main():
    """Execute the quality control workflow."""
    print("=" * 80)
    print("Quality Control Workflow - Manufacturing")
    print("=" * 80)

    # Create and run workflow
    workflow = create_quality_control_workflow()

    # Execute workflow
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    result = runtime.execute(workflow)

    # Extract outputs from tuple result
    outputs, error = result if isinstance(result, tuple) else (result, None)

    print("\n📊 Quality Control Analysis Summary:")

    # Get the quality report from QualityReportGenerator result
    quality_report = outputs.get("QualityReportGenerator", {}).get("result", {})

    if quality_report:
        summary = quality_report.get("executive_summary", {})
        print(f"  Overall Status: {summary.get('overall_status', 'unknown').upper()}")
        print(f"  Lines Analyzed: {summary.get('lines_analyzed', 0)}")
        print(f"  Lines Needing Attention: {summary.get('lines_needing_attention', 0)}")
        print(f"  Average Quality Score: {summary.get('average_quality_score', 0)}%")

        # Show action plan
        action_plan = quality_report.get("action_plan", {})
        immediate_actions = action_plan.get("immediate_actions", [])
        scheduled_actions = action_plan.get("scheduled_actions", [])

        if immediate_actions:
            print("\n🚨 IMMEDIATE ACTIONS REQUIRED:")
            for action in immediate_actions:
                print(
                    f"  - {action['line']}: {len(action['actions'])} critical actions"
                )

        if scheduled_actions:
            print("\n📅 SCHEDULED ACTIONS:")
            for action in scheduled_actions:
                print(
                    f"  - {action['line']}: {len(action['actions'])} improvement actions"
                )

        # Show KPIs
        kpis = quality_report.get("kpi_dashboard", {}).get("quality_metrics", [])
        if kpis:
            print("\n📈 Line Performance:")
            for kpi in kpis:
                status_icon = (
                    "🟢"
                    if kpi["quality_score"] >= 90
                    else "🟡" if kpi["quality_score"] >= 80 else "🔴"
                )
                print(
                    f"  {status_icon} {kpi['line_id']}: {kpi['quality_score']}% (Capability: {kpi['capability_status']})"
                )

    print(f"\n✅ Reports saved to: {get_output_data_path('manufacturing/quality/')}")

    if error:
        print(f"\n❌ Workflow had errors: {error}")
    else:
        print("\n✅ Workflow completed successfully!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
