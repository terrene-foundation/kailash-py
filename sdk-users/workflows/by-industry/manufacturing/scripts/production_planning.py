"""
Production Planning Workflow

This workflow demonstrates production planning optimization for manufacturing:
1. Reads machine schedules, capacity data, and order information
2. Analyzes production capacity and bottlenecks
3. Optimizes production scheduling and resource allocation
4. Generates Gantt charts and production timelines
5. Provides capacity utilization analysis and recommendations

Real-world use case: Manufacturing production planning system that optimizes
machine utilization, schedules orders efficiently, and identifies capacity
constraints to maximize throughput and minimize delays.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the src directory to the path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../src"))
)

from kailash.nodes import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.workflow import Workflow

# Define data path utilities inline
project_root = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../../../")
)


def get_input_data_path(relative_path):
    return os.path.join(project_root, "data", "inputs", relative_path)


def get_output_data_path(relative_path):
    return os.path.join(project_root, "data", "outputs", relative_path)


def ensure_output_dir_exists():
    output_dir = os.path.join(
        project_root, "data", "outputs", "manufacturing", "production"
    )
    os.makedirs(output_dir, exist_ok=True)


def analyze_production_capacity(schedule_data):
    """Analyze production capacity and identify bottlenecks."""
    from collections import defaultdict

    # Group by machine and analyze utilization
    machine_analysis = defaultdict(list)

    for task in schedule_data:
        machine_id = task["machine_id"]
        machine_type = task["machine_type"]

        # Parse times
        start_time = datetime.fromisoformat(task["start_time"])
        end_time = datetime.fromisoformat(task["end_time"])
        duration = (end_time - start_time).total_seconds() / 3600  # Hours

        setup_time = int(task["setup_time_minutes"]) / 60  # Convert to hours
        run_time = int(task["run_time_minutes"]) / 60
        quantity = int(task["quantity"])

        machine_analysis[machine_id].append(
            {
                "machine_type": machine_type,
                "order_id": task["order_id"],
                "product_id": task["product_id"],
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "setup_time": setup_time,
                "run_time": run_time,
                "quantity": quantity,
                "priority": task["priority"],
            }
        )

    # Calculate machine utilization and metrics
    capacity_analysis = []

    for machine_id, tasks in machine_analysis.items():
        # Sort tasks by start time
        tasks.sort(key=lambda x: x["start_time"])

        # Calculate utilization metrics
        total_scheduled_time = sum(task["duration"] for task in tasks)
        total_setup_time = sum(task["setup_time"] for task in tasks)
        total_run_time = sum(task["run_time"] for task in tasks)
        total_quantity = sum(task["quantity"] for task in tasks)

        # Assume 16-hour production day (2 shifts)
        available_hours_per_day = 16
        utilization_rate = (total_scheduled_time / available_hours_per_day) * 100

        # Calculate efficiency metrics
        setup_efficiency = (
            (total_run_time / total_scheduled_time) * 100
            if total_scheduled_time > 0
            else 0
        )
        throughput_per_hour = (
            total_quantity / total_scheduled_time if total_scheduled_time > 0 else 0
        )

        # Identify bottlenecks and gaps
        gaps = []
        if len(tasks) > 1:
            for i in range(len(tasks) - 1):
                gap_start = tasks[i]["end_time"]
                gap_end = tasks[i + 1]["start_time"]
                gap_duration = (gap_end - gap_start).total_seconds() / 3600
                if gap_duration > 0.5:  # Gaps larger than 30 minutes
                    gaps.append(
                        {
                            "start": gap_start.isoformat(),
                            "end": gap_end.isoformat(),
                            "duration_hours": round(gap_duration, 2),
                        }
                    )

        # Determine capacity status
        if utilization_rate > 95:
            capacity_status = "OVERLOADED"
        elif utilization_rate > 85:
            capacity_status = "HIGH_UTILIZATION"
        elif utilization_rate > 70:
            capacity_status = "OPTIMAL"
        elif utilization_rate > 50:
            capacity_status = "UNDERUTILIZED"
        else:
            capacity_status = "SEVERELY_UNDERUTILIZED"

        machine_analysis_result = {
            "machine_id": machine_id,
            "machine_type": tasks[0]["machine_type"],
            "capacity_metrics": {
                "total_scheduled_hours": round(total_scheduled_time, 2),
                "available_hours": available_hours_per_day,
                "utilization_rate": round(utilization_rate, 2),
                "setup_time_hours": round(total_setup_time, 2),
                "run_time_hours": round(total_run_time, 2),
                "setup_efficiency": round(setup_efficiency, 2),
                "throughput_per_hour": round(throughput_per_hour, 2),
            },
            "production_metrics": {
                "total_orders": len(tasks),
                "total_quantity": total_quantity,
                "high_priority_orders": sum(
                    1 for task in tasks if task["priority"] == "high"
                ),
                "medium_priority_orders": sum(
                    1 for task in tasks if task["priority"] == "medium"
                ),
                "low_priority_orders": sum(
                    1 for task in tasks if task["priority"] == "low"
                ),
            },
            "schedule_analysis": {
                "first_job_start": tasks[0]["start_time"].isoformat(),
                "last_job_end": tasks[-1]["end_time"].isoformat(),
                "schedule_gaps": gaps,
                "total_gap_time": sum(gap["duration_hours"] for gap in gaps),
            },
            "capacity_status": capacity_status,
            "bottleneck_risk": (
                "HIGH"
                if utilization_rate > 90
                else "MEDIUM" if utilization_rate > 80 else "LOW"
            ),
        }

        capacity_analysis.append(machine_analysis_result)

    return capacity_analysis


def optimize_production_schedule(capacity_analysis):
    """Generate optimized production schedule and recommendations."""

    optimization_results = {
        "optimization_timestamp": datetime.now().isoformat(),
        "overall_analysis": {},
        "machine_optimizations": [],
        "recommendations": [],
        "capacity_improvements": [],
    }

    # Overall factory analysis
    total_machines = len(capacity_analysis)
    overloaded_machines = sum(
        1 for m in capacity_analysis if m["capacity_status"] == "OVERLOADED"
    )
    underutilized_machines = sum(
        1 for m in capacity_analysis if "UNDERUTILIZED" in m["capacity_status"]
    )

    avg_utilization = (
        sum(m["capacity_metrics"]["utilization_rate"] for m in capacity_analysis)
        / total_machines
    )
    total_gap_time = sum(
        m["schedule_analysis"]["total_gap_time"] for m in capacity_analysis
    )

    optimization_results["overall_analysis"] = {
        "total_machines": total_machines,
        "average_utilization": round(avg_utilization, 2),
        "overloaded_machines": overloaded_machines,
        "underutilized_machines": underutilized_machines,
        "total_gap_time_hours": round(total_gap_time, 2),
        "factory_efficiency_score": round(
            max(0, 100 - (overloaded_machines * 20) - (underutilized_machines * 10)), 1
        ),
    }

    # Analyze each machine for optimization opportunities
    for machine in capacity_analysis:
        machine_id = machine["machine_id"]
        utilization = machine["capacity_metrics"]["utilization_rate"]
        gap_time = machine["schedule_analysis"]["total_gap_time"]
        setup_efficiency = machine["capacity_metrics"]["setup_efficiency"]

        optimizations = []

        # Setup optimization
        if setup_efficiency < 80:
            optimizations.append(
                {
                    "type": "SETUP_OPTIMIZATION",
                    "description": f"Reduce setup time - current efficiency {setup_efficiency:.1f}%",
                    "potential_improvement": f'Could save {(100-setup_efficiency)/100 * machine["capacity_metrics"]["setup_time_hours"]:.1f} hours',
                    "implementation": "Implement SMED (Single-Minute Exchange of Die) principles",
                }
            )

        # Gap reduction
        if gap_time > 2:
            optimizations.append(
                {
                    "type": "SCHEDULE_OPTIMIZATION",
                    "description": f"Reduce schedule gaps - current total {gap_time:.1f} hours",
                    "potential_improvement": f"Could improve utilization by {(gap_time/16)*100:.1f}%",
                    "implementation": "Reschedule jobs to minimize gaps, batch similar products",
                }
            )

        # Capacity balancing
        if utilization > 95:
            optimizations.append(
                {
                    "type": "LOAD_BALANCING",
                    "description": f"Machine overloaded at {utilization:.1f}% utilization",
                    "potential_improvement": "Redistribute work to other machines",
                    "implementation": "Move some orders to underutilized machines or add shifts",
                }
            )
        elif utilization < 50:
            optimizations.append(
                {
                    "type": "CAPACITY_UTILIZATION",
                    "description": f"Machine underutilized at {utilization:.1f}%",
                    "potential_improvement": "Opportunity to take on additional work",
                    "implementation": "Reassign work from overloaded machines or increase order volume",
                }
            )

        optimization_results["machine_optimizations"].append(
            {
                "machine_id": machine_id,
                "current_utilization": utilization,
                "optimization_opportunities": optimizations,
                "priority": (
                    "HIGH"
                    if utilization > 95 or utilization < 30
                    else "MEDIUM" if utilization > 90 or utilization < 50 else "LOW"
                ),
            }
        )

    # Generate overall recommendations
    if overloaded_machines > 0:
        optimization_results["recommendations"].append(
            {
                "category": "IMMEDIATE",
                "title": "Address Machine Overload",
                "description": f"{overloaded_machines} machines are overloaded (>95% utilization)",
                "actions": [
                    "Redistribute orders to underutilized machines",
                    "Consider adding overtime shifts",
                    "Expedite setup time reduction initiatives",
                    "Review order priorities and deadlines",
                ],
            }
        )

    if underutilized_machines > 0:
        optimization_results["recommendations"].append(
            {
                "category": "STRATEGIC",
                "title": "Optimize Underutilized Capacity",
                "description": f"{underutilized_machines} machines are underutilized",
                "actions": [
                    "Cross-train operators for machine flexibility",
                    "Move work from bottleneck machines",
                    "Consider maintenance during low-utilization periods",
                    "Evaluate potential for additional orders",
                ],
            }
        )

    if total_gap_time > 10:
        optimization_results["recommendations"].append(
            {
                "category": "EFFICIENCY",
                "title": "Reduce Schedule Gaps",
                "description": f"{total_gap_time:.1f} hours of gaps identified across all machines",
                "actions": [
                    "Implement better job sequencing algorithms",
                    "Batch similar products to reduce setup",
                    "Use gaps for preventive maintenance",
                    "Consider smaller batch sizes for better flow",
                ],
            }
        )

    # Capacity improvement suggestions
    optimization_results["capacity_improvements"] = [
        {
            "improvement": "Setup Time Reduction",
            "impact": "Could increase capacity by 10-15%",
            "investment": "Medium - Training and tooling improvements",
            "timeline": "3-6 months",
        },
        {
            "improvement": "Advanced Scheduling Software",
            "impact": "Could improve utilization by 5-10%",
            "investment": "High - Software and training",
            "timeline": "6-12 months",
        },
        {
            "improvement": "Operator Cross-Training",
            "impact": "Increased flexibility and reduced bottlenecks",
            "investment": "Low - Training time",
            "timeline": "1-3 months",
        },
    ]

    return optimization_results


def create_production_planning_workflow():
    """Create the production planning workflow."""

    workflow = Workflow(workflow_id="production-planning", name="Production Planning")

    # Add nodes
    workflow.add_node(
        "ScheduleDataReader",
        CSVReaderNode(
            file_path=get_input_data_path("manufacturing/machine_schedule.csv")
        ),
    )

    workflow.add_node(
        "CapacityAnalyzer",
        PythonCodeNode.from_function(
            func=analyze_production_capacity, input_mapping={"schedule_data": "data"}
        ),
    )

    workflow.add_node(
        "ScheduleOptimizer",
        PythonCodeNode.from_function(
            func=optimize_production_schedule,
            input_mapping={"capacity_analysis": "result"},
        ),
    )

    # Write outputs
    ensure_output_dir_exists()
    workflow.add_node(
        "CapacityAnalysisWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/production/capacity_analysis.json"
            )
        ),
    )

    workflow.add_node(
        "OptimizationReportWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/production/optimization_report.json"
            )
        ),
    )

    # Connect the workflow
    workflow.connect(
        "ScheduleDataReader", "CapacityAnalyzer", {"data": "schedule_data"}
    )
    workflow.connect("CapacityAnalyzer", "CapacityAnalysisWriter", {"result": "data"})
    workflow.connect(
        "CapacityAnalyzer", "ScheduleOptimizer", {"result": "capacity_analysis"}
    )
    workflow.connect(
        "ScheduleOptimizer", "OptimizationReportWriter", {"result": "data"}
    )

    workflow.validate()
    return workflow


def main():
    """Execute the production planning workflow."""
    print("=" * 80)
    print("Production Planning Workflow - Manufacturing")
    print("=" * 80)

    workflow = create_production_planning_workflow()

    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    result = runtime.execute(workflow)

    # Extract outputs from tuple result
    outputs, error = result if isinstance(result, tuple) else (result, None)

    print("\n📊 Production Planning Analysis Summary:")

    # Get the optimization report from ScheduleOptimizer result
    optimization_report = outputs.get("ScheduleOptimizer", {}).get("result", {})

    if optimization_report:
        overall = optimization_report.get("overall_analysis", {})
        print(
            f"  Factory Efficiency Score: {overall.get('factory_efficiency_score', 0)}%"
        )
        print(
            f"  Average Machine Utilization: {overall.get('average_utilization', 0)}%"
        )
        print(f"  Overloaded Machines: {overall.get('overloaded_machines', 0)}")
        print(f"  Underutilized Machines: {overall.get('underutilized_machines', 0)}")
        print(f"  Total Gap Time: {overall.get('total_gap_time_hours', 0)} hours")

        recommendations = optimization_report.get("recommendations", [])
        if recommendations:
            print("\n📋 Key Recommendations:")
            for rec in recommendations[:3]:
                print(f"  🎯 [{rec['category']}] {rec['title']}")
                print(f"     {rec['description']}")

    print(f"\n✅ Reports saved to: {get_output_data_path('manufacturing/production/')}")

    if error:
        print(f"\n❌ Workflow had errors: {error}")
    else:
        print("\n✅ Workflow completed successfully!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
