"""
Supply Chain Optimization Workflow

This workflow demonstrates supply chain optimization for manufacturing:
1. Reads multiple supply chain data sources (inventory, suppliers, demand)
2. Analyzes supplier performance and reliability
3. Optimizes inventory levels and reorder points
4. Generates supplier scorecards and recommendations
5. Creates supply chain risk assessment and mitigation plans

Real-world use case: Manufacturing supply chain management system that
optimizes inventory, evaluates suppliers, and minimizes supply risks
while maintaining production continuity.
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
        project_root, "data", "outputs", "manufacturing", "supply_chain"
    )
    os.makedirs(output_dir, exist_ok=True)


def analyze_inventory_optimization(inventory_data):
    """
    Analyze inventory levels and optimize reorder points.
    """
    import statistics

    optimized_inventory = []

    for item in inventory_data:
        # Calculate safety stock and reorder points
        current_stock = float(item["current_stock"])
        min_stock = float(item["min_stock"])
        max_stock = float(item["max_stock"])
        lead_time = int(item["lead_time_days"])
        unit_cost = float(item["unit_cost"])

        # Calculate inventory metrics
        stock_ratio = current_stock / max_stock
        days_of_supply = current_stock / (min_stock / 7)  # Assuming weekly minimum

        # Determine reorder recommendations
        if current_stock <= min_stock:
            reorder_urgency = "IMMEDIATE"
            reorder_quantity = max_stock - current_stock
        elif current_stock <= (min_stock * 1.5):
            reorder_urgency = "HIGH"
            reorder_quantity = max_stock - current_stock
        elif current_stock <= (min_stock * 2):
            reorder_urgency = "MEDIUM"
            reorder_quantity = max_stock - current_stock
        else:
            reorder_urgency = "LOW"
            reorder_quantity = 0

        # Calculate economic order quantity (simplified)
        annual_demand = min_stock * 52  # Rough estimate
        ordering_cost = 50  # Assumed ordering cost
        holding_cost_rate = 0.2  # 20% holding cost
        eoq = (
            (2 * annual_demand * ordering_cost) / (unit_cost * holding_cost_rate)
        ) ** 0.5

        # Optimize reorder point based on lead time and demand variability
        avg_daily_demand = min_stock / 7
        safety_stock = (
            avg_daily_demand * lead_time * 0.5
        )  # Simple safety stock calculation
        optimal_reorder_point = (avg_daily_demand * lead_time) + safety_stock

        optimization_data = {
            "material_id": item["material_id"],
            "material_name": item["material_name"],
            "category": item["category"],
            "current_metrics": {
                "current_stock": current_stock,
                "stock_ratio": round(stock_ratio, 3),
                "days_of_supply": round(days_of_supply, 1),
                "unit_cost": unit_cost,
            },
            "optimization_results": {
                "eoq": round(eoq, 0),
                "optimal_reorder_point": round(optimal_reorder_point, 0),
                "safety_stock": round(safety_stock, 0),
                "reorder_urgency": reorder_urgency,
                "recommended_order_quantity": (
                    round(reorder_quantity, 0) if reorder_quantity > 0 else 0
                ),
            },
            "cost_analysis": {
                "current_inventory_value": round(current_stock * unit_cost, 2),
                "optimal_inventory_value": round(optimal_reorder_point * unit_cost, 2),
                "potential_savings": (
                    round((current_stock - optimal_reorder_point) * unit_cost, 2)
                    if current_stock > optimal_reorder_point
                    else 0
                ),
            },
            "supplier_id": item["supplier_id"],
            "lead_time_days": lead_time,
            "status": (
                "critical"
                if reorder_urgency == "IMMEDIATE"
                else "attention" if reorder_urgency == "HIGH" else "normal"
            ),
        }

        optimized_inventory.append(optimization_data)

    return optimized_inventory


def evaluate_supplier_performance(supplier_data, inventory_data):
    """
    Evaluate supplier performance and generate scorecards.
    """
    supplier_evaluations = []

    # Create lookup for inventory by supplier
    inventory_by_supplier = {}
    for item in inventory_data:
        supplier_id = item["supplier_id"]
        if supplier_id not in inventory_by_supplier:
            inventory_by_supplier[supplier_id] = []
        inventory_by_supplier[supplier_id].append(item)

    for supplier in supplier_data:
        supplier_id = supplier["supplier_id"]

        # Basic performance metrics
        on_time_rate = float(supplier["on_time_delivery_rate"])
        quality_score = float(supplier["quality_score"])
        lead_time = float(supplier["average_lead_time_days"])
        cost_index = float(supplier["cost_index"])
        total_orders = int(supplier["total_orders_2024"])
        rejected_shipments = int(supplier["rejected_shipments"])

        # Calculate derived metrics
        rejection_rate = (
            (rejected_shipments / total_orders * 100) if total_orders > 0 else 0
        )
        reliability_score = (on_time_rate + quality_score) / 2

        # Calculate weighted performance score
        # Weights: On-time (30%), Quality (30%), Cost (20%), Reliability (20%)
        performance_score = (
            on_time_rate * 0.3
            + quality_score * 0.3
            + (100 - ((cost_index - 1.0) * 100)) * 0.2  # Lower cost index is better
            + (100 - rejection_rate) * 0.2
        )

        # Risk assessment
        risk_factors = []
        risk_level = "LOW"

        if on_time_rate < 90:
            risk_factors.append("Poor delivery performance")
        if quality_score < 95:
            risk_factors.append("Quality issues")
        if rejection_rate > 5:
            risk_factors.append("High rejection rate")
        if cost_index > 1.15:
            risk_factors.append("High cost premium")
        if lead_time > 21:
            risk_factors.append("Long lead times")

        if len(risk_factors) >= 3:
            risk_level = "HIGH"
        elif len(risk_factors) >= 1:
            risk_level = "MEDIUM"

        # Supplier category and recommendations
        if performance_score >= 95:
            supplier_category = "STRATEGIC"
            recommendations = [
                "Expand partnership",
                "Negotiate better terms",
                "Increase order volume",
            ]
        elif performance_score >= 85:
            supplier_category = "PREFERRED"
            recommendations = [
                "Maintain current relationship",
                "Monitor performance",
                "Consider for strategic growth",
            ]
        elif performance_score >= 75:
            supplier_category = "ACCEPTABLE"
            recommendations = [
                "Develop improvement plan",
                "Increase monitoring",
                "Consider alternatives",
            ]
        else:
            supplier_category = "NEEDS_IMPROVEMENT"
            recommendations = [
                "Immediate performance review",
                "Develop strict improvement plan",
                "Source alternatives",
            ]

        # Count items supplied
        items_supplied = len(inventory_by_supplier.get(supplier_id, []))
        total_inventory_value = sum(
            float(item["current_stock"]) * float(item["unit_cost"])
            for item in inventory_by_supplier.get(supplier_id, [])
        )

        evaluation = {
            "supplier_id": supplier_id,
            "supplier_name": supplier["supplier_name"],
            "category": supplier["category"],
            "performance_metrics": {
                "on_time_delivery_rate": on_time_rate,
                "quality_score": quality_score,
                "average_lead_time_days": lead_time,
                "cost_index": cost_index,
                "rejection_rate": round(rejection_rate, 2),
                "reliability_score": round(reliability_score, 2),
                "overall_performance_score": round(performance_score, 2),
            },
            "business_metrics": {
                "total_orders_2024": total_orders,
                "rejected_shipments": rejected_shipments,
                "items_supplied": items_supplied,
                "total_inventory_value": round(total_inventory_value, 2),
            },
            "risk_assessment": {
                "risk_level": risk_level,
                "risk_factors": risk_factors,
                "risk_score": round(len(risk_factors) * 25, 1),  # Simple risk scoring
            },
            "supplier_category": supplier_category,
            "recommendations": recommendations,
            "next_review_date": (datetime.now() + timedelta(days=90)).isoformat()[:10],
        }

        supplier_evaluations.append(evaluation)

    return supplier_evaluations


def generate_supply_chain_report(inventory_optimization, supplier_evaluations):
    """
    Generate comprehensive supply chain optimization report.
    """
    # Calculate summary metrics
    total_items = len(inventory_optimization)
    critical_items = sum(
        1 for item in inventory_optimization if item["status"] == "critical"
    )
    attention_items = sum(
        1 for item in inventory_optimization if item["status"] == "attention"
    )

    total_suppliers = len(supplier_evaluations)
    strategic_suppliers = sum(
        1 for s in supplier_evaluations if s["supplier_category"] == "STRATEGIC"
    )
    needs_improvement_suppliers = sum(
        1 for s in supplier_evaluations if s["supplier_category"] == "NEEDS_IMPROVEMENT"
    )

    # Calculate potential savings
    total_potential_savings = sum(
        item["cost_analysis"]["potential_savings"]
        for item in inventory_optimization
        if item["cost_analysis"]["potential_savings"] > 0
    )

    # Generate recommendations
    immediate_actions = []
    strategic_actions = []

    # Inventory recommendations
    for item in inventory_optimization:
        if item["optimization_results"]["reorder_urgency"] == "IMMEDIATE":
            immediate_actions.append(
                {
                    "type": "INVENTORY",
                    "item": item["material_name"],
                    "action": f"Immediate reorder of {item['optimization_results']['recommended_order_quantity']} units",
                    "impact": f"Prevent stockout - ${item['cost_analysis']['current_inventory_value']:,.2f} at risk",
                }
            )

    # Supplier recommendations
    for supplier in supplier_evaluations:
        if supplier["risk_assessment"]["risk_level"] == "HIGH":
            immediate_actions.append(
                {
                    "type": "SUPPLIER",
                    "supplier": supplier["supplier_name"],
                    "action": "Immediate supplier performance review required",
                    "impact": f"${supplier['business_metrics']['total_inventory_value']:,.2f} inventory at risk",
                }
            )
        elif supplier["supplier_category"] == "STRATEGIC":
            strategic_actions.append(
                {
                    "type": "STRATEGIC",
                    "supplier": supplier["supplier_name"],
                    "action": "Explore expanded partnership opportunities",
                    "impact": "Strengthen supply chain resilience",
                }
            )

    report = {
        "report_timestamp": datetime.now().isoformat(),
        "executive_summary": {
            "total_inventory_items": total_items,
            "critical_items_requiring_attention": critical_items,
            "items_needing_monitoring": attention_items,
            "total_suppliers": total_suppliers,
            "strategic_suppliers": strategic_suppliers,
            "suppliers_needing_improvement": needs_improvement_suppliers,
            "potential_cost_savings": round(total_potential_savings, 2),
            "overall_supply_chain_health": (
                "good" if critical_items < (total_items * 0.1) else "needs_attention"
            ),
        },
        "inventory_analysis": {
            "optimization_summary": {
                "items_analyzed": total_items,
                "immediate_reorders_needed": sum(
                    1
                    for item in inventory_optimization
                    if item["optimization_results"]["reorder_urgency"] == "IMMEDIATE"
                ),
                "high_priority_reorders": sum(
                    1
                    for item in inventory_optimization
                    if item["optimization_results"]["reorder_urgency"] == "HIGH"
                ),
                "total_inventory_value": round(
                    sum(
                        item["cost_analysis"]["current_inventory_value"]
                        for item in inventory_optimization
                    ),
                    2,
                ),
            },
            "critical_items": [
                item for item in inventory_optimization if item["status"] == "critical"
            ][:10],
        },
        "supplier_analysis": {
            "performance_summary": {
                "strategic_suppliers": strategic_suppliers,
                "preferred_suppliers": sum(
                    1
                    for s in supplier_evaluations
                    if s["supplier_category"] == "PREFERRED"
                ),
                "acceptable_suppliers": sum(
                    1
                    for s in supplier_evaluations
                    if s["supplier_category"] == "ACCEPTABLE"
                ),
                "needs_improvement_suppliers": needs_improvement_suppliers,
                "average_performance_score": round(
                    sum(
                        s["performance_metrics"]["overall_performance_score"]
                        for s in supplier_evaluations
                    )
                    / len(supplier_evaluations),
                    2,
                ),
            },
            "top_performers": sorted(
                supplier_evaluations,
                key=lambda x: x["performance_metrics"]["overall_performance_score"],
                reverse=True,
            )[:5],
            "high_risk_suppliers": [
                s
                for s in supplier_evaluations
                if s["risk_assessment"]["risk_level"] == "HIGH"
            ],
        },
        "action_plan": {
            "immediate_actions": immediate_actions[:10],  # Top 10 most critical
            "strategic_actions": strategic_actions[:5],  # Top 5 strategic opportunities
            "next_review_cycle": (datetime.now() + timedelta(days=30)).isoformat()[:10],
        },
        "kpi_dashboard": {
            "inventory_kpis": {
                "stockout_risk_items": critical_items,
                "optimal_inventory_ratio": round(
                    (total_items - critical_items - attention_items)
                    / total_items
                    * 100,
                    1,
                ),
                "potential_savings_percentage": round(
                    total_potential_savings
                    / sum(
                        item["cost_analysis"]["current_inventory_value"]
                        for item in inventory_optimization
                    )
                    * 100,
                    2,
                ),
            },
            "supplier_kpis": {
                "supplier_reliability": round(
                    sum(
                        s["performance_metrics"]["reliability_score"]
                        for s in supplier_evaluations
                    )
                    / len(supplier_evaluations),
                    1,
                ),
                "strategic_supplier_ratio": round(
                    strategic_suppliers / total_suppliers * 100, 1
                ),
                "high_risk_supplier_count": sum(
                    1
                    for s in supplier_evaluations
                    if s["risk_assessment"]["risk_level"] == "HIGH"
                ),
            },
        },
    }

    return report


def create_supply_chain_optimization_workflow():
    """Create the supply chain optimization workflow."""

    # Create workflow
    workflow = Workflow(
        workflow_id="supply-chain-optimization", name="Supply Chain Optimization"
    )

    # Add nodes

    # 1. Read inventory data
    workflow.add_node(
        "InventoryDataReader",
        CSVReaderNode(
            file_path=get_input_data_path("manufacturing/inventory_levels.csv")
        ),
    )

    # 2. Read supplier data
    workflow.add_node(
        "SupplierDataReader",
        CSVReaderNode(
            file_path=get_input_data_path("manufacturing/supplier_performance.csv")
        ),
    )

    # 3. Analyze inventory optimization
    workflow.add_node(
        "InventoryOptimizer",
        PythonCodeNode.from_function(
            func=analyze_inventory_optimization,
            input_mapping={"inventory_data": "data"},
        ),
    )

    # 4. Evaluate supplier performance
    workflow.add_node(
        "SupplierEvaluator",
        PythonCodeNode.from_function(func=evaluate_supplier_performance),
    )

    # 5. Generate supply chain report
    workflow.add_node(
        "SupplyChainReportGenerator",
        PythonCodeNode.from_function(func=generate_supply_chain_report),
    )

    # 6. Write inventory optimization data
    ensure_output_dir_exists()
    workflow.add_node(
        "InventoryOptimizationWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/supply_chain/inventory_optimization.json"
            )
        ),
    )

    # 7. Write supplier evaluations
    workflow.add_node(
        "SupplierEvaluationWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/supply_chain/supplier_evaluations.json"
            )
        ),
    )

    # 8. Write supply chain report
    workflow.add_node(
        "SupplyChainReportWriter",
        JSONWriterNode(
            file_path=get_output_data_path(
                "manufacturing/supply_chain/supply_chain_report.json"
            )
        ),
    )

    # Connect the workflow
    workflow.connect(
        "InventoryDataReader", "InventoryOptimizer", {"data": "inventory_data"}
    )
    workflow.connect(
        "InventoryOptimizer", "InventoryOptimizationWriter", {"result": "data"}
    )

    # Supplier evaluation needs both supplier data and inventory data
    workflow.connect(
        "SupplierDataReader", "SupplierEvaluator", {"data": "supplier_data"}
    )
    workflow.connect(
        "InventoryDataReader", "SupplierEvaluator", {"data": "inventory_data"}
    )
    workflow.connect(
        "SupplierEvaluator", "SupplierEvaluationWriter", {"result": "data"}
    )

    # Report generation needs both optimization and evaluation results
    workflow.connect(
        "InventoryOptimizer",
        "SupplyChainReportGenerator",
        {"result": "inventory_optimization"},
    )
    workflow.connect(
        "SupplierEvaluator",
        "SupplyChainReportGenerator",
        {"result": "supplier_evaluations"},
    )
    workflow.connect(
        "SupplyChainReportGenerator", "SupplyChainReportWriter", {"result": "data"}
    )

    # Validate workflow
    workflow.validate()

    return workflow


def main():
    """Execute the supply chain optimization workflow."""
    print("=" * 80)
    print("Supply Chain Optimization Workflow - Manufacturing")
    print("=" * 80)

    # Create and run workflow
    workflow = create_supply_chain_optimization_workflow()

    # Execute workflow
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    result = runtime.execute(workflow)

    # Extract outputs from tuple result
    outputs, error = result if isinstance(result, tuple) else (result, None)

    print("\n📊 Supply Chain Optimization Summary:")

    # Get the supply chain report
    supply_chain_report = outputs.get("SupplyChainReportGenerator", {}).get(
        "result", {}
    )

    if supply_chain_report:
        summary = supply_chain_report.get("executive_summary", {})
        print(
            f"  Overall Supply Chain Health: {summary.get('overall_supply_chain_health', 'unknown').upper()}"
        )
        print(f"  Total Inventory Items: {summary.get('total_inventory_items', 0)}")
        print(
            f"  Critical Items Requiring Attention: {summary.get('critical_items_requiring_attention', 0)}"
        )
        print(f"  Total Suppliers: {summary.get('total_suppliers', 0)}")
        print(f"  Strategic Suppliers: {summary.get('strategic_suppliers', 0)}")
        print(
            f"  Potential Cost Savings: ${summary.get('potential_cost_savings', 0):,.2f}"
        )

        # Show immediate actions
        action_plan = supply_chain_report.get("action_plan", {})
        immediate_actions = action_plan.get("immediate_actions", [])

        if immediate_actions:
            print("\n🚨 IMMEDIATE ACTIONS REQUIRED:")
            for action in immediate_actions[:5]:  # Show top 5
                print(
                    f"  - [{action['type']}] {action.get('item', action.get('supplier', 'Unknown'))}"
                )
                print(f"    Action: {action['action']}")
                print(f"    Impact: {action['impact']}")

        # Show KPIs
        kpis = supply_chain_report.get("kpi_dashboard", {})
        inventory_kpis = kpis.get("inventory_kpis", {})
        supplier_kpis = kpis.get("supplier_kpis", {})

        print("\n📈 Key Performance Indicators:")
        print("  📦 Inventory:")
        print(
            f"    - Optimal Inventory Ratio: {inventory_kpis.get('optimal_inventory_ratio', 0)}%"
        )
        print(
            f"    - Stockout Risk Items: {inventory_kpis.get('stockout_risk_items', 0)}"
        )
        print(
            f"    - Potential Savings: {inventory_kpis.get('potential_savings_percentage', 0)}%"
        )

        print("  🏭 Suppliers:")
        print(
            f"    - Supplier Reliability: {supplier_kpis.get('supplier_reliability', 0)}%"
        )
        print(
            f"    - Strategic Supplier Ratio: {supplier_kpis.get('strategic_supplier_ratio', 0)}%"
        )
        print(
            f"    - High Risk Suppliers: {supplier_kpis.get('high_risk_supplier_count', 0)}"
        )

    print(
        f"\n✅ Reports saved to: {get_output_data_path('manufacturing/supply_chain/')}"
    )

    if error:
        print(f"\n❌ Workflow had errors: {error}")
    else:
        print("\n✅ Workflow completed successfully!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
