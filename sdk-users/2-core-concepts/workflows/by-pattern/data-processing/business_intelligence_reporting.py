#!/usr/bin/env python3
"""
Business Intelligence & Reporting Workflows - Production Business Solution

Enterprise business intelligence and automated reporting workflows for executive decision-making:
1. Multi-source data aggregation and KPI calculation
2. Automated executive dashboard generation with real-time insights
3. Trend analysis and predictive analytics for business forecasting
4. Exception reporting and alert generation for business anomalies
5. Regulatory compliance reporting with audit trails
6. Performance benchmarking against industry standards

Business Value:
- Executive dashboards provide real-time visibility into business performance
- Automated reporting reduces manual effort and increases reporting frequency
- Trend analysis enables proactive business decision-making
- Exception reporting identifies risks and opportunities before they impact results
- Compliance reporting ensures regulatory adherence and reduces audit costs
- Performance benchmarking drives competitive advantage and optimization

Key Features:
- Multi-dimensional business metrics calculation with drill-down capabilities
- PythonCodeNode for advanced analytics and statistical modeling
- Automated report generation with professional formatting
- LocalRuntime with enterprise monitoring and performance tracking
- Real-time exception detection and alerting system
- Comprehensive audit trails for regulatory compliance
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import CSVWriterNode, JSONWriterNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure business-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def create_business_data_generator():
    """Create a node that generates comprehensive business data for BI analysis."""

    def generate_business_metrics(
        months_back: Optional[int] = None,
        departments: Optional[List[str]] = None,
        include_anomalies: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Generate comprehensive business data for executive reporting."""

        # Set defaults
        if months_back is None:
            months_back = 12
        if departments is None:
            departments = [
                "Sales",
                "Marketing",
                "Operations",
                "Customer Success",
                "Finance",
                "HR",
            ]
        if include_anomalies is None:
            include_anomalies = True

        # Generate time series data
        end_date = datetime.now()
        dates = [end_date - timedelta(days=30 * i) for i in range(months_back)]
        dates.reverse()

        business_data = []

        for date in dates:
            for dept in departments:
                # Base metrics with realistic trends
                month_factor = 1 + 0.1 * np.sin(
                    2 * np.pi * date.month / 12
                )  # Seasonal pattern

                if dept == "Sales":
                    revenue = random.uniform(800000, 1200000) * month_factor
                    leads = random.randint(200, 400)
                    conversion_rate = random.uniform(0.15, 0.25)
                    customer_acquisition_cost = random.uniform(150, 300)
                elif dept == "Marketing":
                    revenue = random.uniform(50000, 150000) * month_factor
                    leads = random.randint(1000, 2000)
                    conversion_rate = random.uniform(0.05, 0.12)
                    customer_acquisition_cost = random.uniform(80, 200)
                elif dept == "Operations":
                    revenue = random.uniform(200000, 400000) * month_factor
                    leads = random.randint(50, 100)
                    conversion_rate = random.uniform(0.3, 0.5)
                    customer_acquisition_cost = random.uniform(50, 150)
                else:  # Support departments
                    revenue = random.uniform(100000, 300000) * month_factor
                    leads = random.randint(20, 80)
                    conversion_rate = random.uniform(0.1, 0.3)
                    customer_acquisition_cost = random.uniform(100, 250)

                # Add anomalies for exception reporting
                if include_anomalies and random.random() < 0.1:  # 10% chance of anomaly
                    if random.choice([True, False]):  # Positive anomaly
                        revenue *= random.uniform(1.5, 2.0)
                        conversion_rate *= random.uniform(1.3, 1.8)
                    else:  # Negative anomaly
                        revenue *= random.uniform(0.3, 0.7)
                        conversion_rate *= random.uniform(0.5, 0.8)

                # Calculate derived metrics
                customers_acquired = int(leads * conversion_rate)
                total_acquisition_cost = customers_acquired * customer_acquisition_cost
                roi = (
                    (revenue - total_acquisition_cost) / total_acquisition_cost
                    if total_acquisition_cost > 0
                    else 0
                )

                record = {
                    "report_date": date.strftime("%Y-%m-%d"),
                    "department": dept,
                    "revenue": float(round(revenue, 2)),
                    "leads_generated": int(leads),
                    "customers_acquired": int(customers_acquired),
                    "conversion_rate": float(round(conversion_rate, 4)),
                    "customer_acquisition_cost": float(
                        round(customer_acquisition_cost, 2)
                    ),
                    "total_acquisition_cost": float(round(total_acquisition_cost, 2)),
                    "roi": float(round(roi, 4)),
                    "month_name": date.strftime("%B"),
                    "quarter": f"Q{(date.month-1)//3 + 1}",
                    "year": int(date.year),
                }
                business_data.append(record)

        # Calculate summary statistics
        total_revenue = sum(r["revenue"] for r in business_data)
        total_customers = sum(r["customers_acquired"] for r in business_data)
        avg_conversion_rate = np.mean([r["conversion_rate"] for r in business_data])

        summary_stats = {
            "total_revenue": float(round(total_revenue, 2)),
            "total_customers_acquired": int(total_customers),
            "average_conversion_rate": float(round(avg_conversion_rate, 4)),
            "total_records": int(len(business_data)),
            "date_range": {
                "start": dates[0].strftime("%Y-%m-%d"),
                "end": dates[-1].strftime("%Y-%m-%d"),
            },
            "departments_included": departments,
        }

        return {
            "business_data": business_data,
            "summary_statistics": summary_stats,
            "data_generation_timestamp": datetime.now().isoformat(),
        }

    return PythonCodeNode.from_function(
        func=generate_business_metrics,
        name="business_data_generator",
        description="Generate comprehensive business data for BI analysis",
    )


def create_kpi_calculator():
    """Create a node that calculates executive KPIs and performance metrics."""

    def calculate_executive_kpis(business_data: List[Dict]) -> Dict[str, Any]:
        """Calculate comprehensive KPIs for executive dashboard."""

        df = pd.DataFrame(business_data)

        # Convert date column for time-based analysis
        df["report_date"] = pd.to_datetime(df["report_date"])
        df = df.sort_values("report_date")

        # Current month vs previous month comparison
        current_month = df["report_date"].max().month
        current_year = df["report_date"].max().year
        prev_month = current_month - 1 if current_month > 1 else 12
        prev_year = current_year if current_month > 1 else current_year - 1

        current_data = df[
            (df["report_date"].dt.month == current_month)
            & (df["report_date"].dt.year == current_year)
        ]
        previous_data = df[
            (df["report_date"].dt.month == prev_month)
            & (df["report_date"].dt.year == prev_year)
        ]

        # Calculate KPIs
        kpis = {}

        # Revenue KPIs
        current_revenue = current_data["revenue"].sum()
        previous_revenue = previous_data["revenue"].sum()
        revenue_growth = (
            ((current_revenue - previous_revenue) / previous_revenue * 100)
            if previous_revenue > 0
            else 0
        )

        kpis["revenue"] = {
            "current_month": float(round(current_revenue, 2)),
            "previous_month": float(round(previous_revenue, 2)),
            "growth_rate": float(round(revenue_growth, 2)),
            "growth_status": "positive" if revenue_growth > 0 else "negative",
        }

        # Customer Acquisition KPIs
        current_customers = current_data["customers_acquired"].sum()
        previous_customers = previous_data["customers_acquired"].sum()
        customer_growth = (
            ((current_customers - previous_customers) / previous_customers * 100)
            if previous_customers > 0
            else 0
        )

        kpis["customer_acquisition"] = {
            "current_month": int(current_customers),
            "previous_month": int(previous_customers),
            "growth_rate": float(round(customer_growth, 2)),
            "growth_status": "positive" if customer_growth > 0 else "negative",
        }

        # Conversion Rate KPIs
        current_conversion = current_data["conversion_rate"].mean()
        previous_conversion = previous_data["conversion_rate"].mean()
        conversion_change = (
            ((current_conversion - previous_conversion) / previous_conversion * 100)
            if previous_conversion > 0
            else 0
        )

        kpis["conversion_rate"] = {
            "current_month": float(round(current_conversion, 4)),
            "previous_month": float(round(previous_conversion, 4)),
            "change_rate": float(round(conversion_change, 2)),
            "performance_status": "improving" if conversion_change > 0 else "declining",
        }

        # Department Performance Analysis
        dept_performance = (
            df.groupby("department")
            .agg(
                {
                    "revenue": "sum",
                    "customers_acquired": "sum",
                    "conversion_rate": "mean",
                    "roi": "mean",
                }
            )
            .round(2)
        )

        # Identify top and bottom performers
        top_revenue_dept = dept_performance["revenue"].idxmax()
        bottom_revenue_dept = dept_performance["revenue"].idxmin()

        kpis["department_performance"] = {
            "top_revenue_department": {
                "name": str(top_revenue_dept),
                "revenue": float(dept_performance.loc[top_revenue_dept, "revenue"]),
            },
            "lowest_revenue_department": {
                "name": str(bottom_revenue_dept),
                "revenue": float(dept_performance.loc[bottom_revenue_dept, "revenue"]),
            },
            "department_summary": {
                str(k): {str(k2): float(v2) for k2, v2 in v.items()}
                for k, v in dept_performance.to_dict("index").items()
            },
        }

        # Quarterly Analysis
        quarterly_data = (
            df.groupby(["year", "quarter"])
            .agg(
                {
                    "revenue": "sum",
                    "customers_acquired": "sum",
                    "conversion_rate": "mean",
                }
            )
            .round(2)
        )

        kpis["quarterly_trends"] = {
            str(k): {str(k2): float(v2) for k2, v2 in v.items()}
            for k, v in quarterly_data.to_dict("index").items()
        }

        # Overall Business Health Score (0-100)
        health_factors = {
            "revenue_growth": float(
                min(max(revenue_growth / 10, -10), 10)
            ),  # -10 to 10 range
            "customer_growth": float(min(max(customer_growth / 10, -10), 10)),
            "conversion_performance": float(min(max(conversion_change / 5, -10), 10)),
            "roi_average": float(min(max(df["roi"].mean() * 10, -10), 10)),
        }

        health_score = 50 + sum(health_factors.values()) * 2.5  # Base 50 + factors
        health_score = max(0, min(100, health_score))  # Clamp to 0-100

        kpis["business_health"] = {
            "overall_score": float(round(health_score, 1)),
            "health_factors": health_factors,
            "health_status": (
                "excellent"
                if health_score > 80
                else (
                    "good"
                    if health_score > 60
                    else "fair" if health_score > 40 else "poor"
                )
            ),
        }

        return {
            "executive_kpis": kpis,
            "calculation_timestamp": datetime.now().isoformat(),
            "data_period": f"{df['report_date'].min().strftime('%Y-%m-%d')} to {df['report_date'].max().strftime('%Y-%m-%d')}",
        }

    return PythonCodeNode.from_function(
        func=calculate_executive_kpis,
        name="kpi_calculator",
        description="Calculate executive KPIs and performance metrics",
    )


def create_exception_detector():
    """Create a node that detects business anomalies and generates alerts."""

    def detect_business_exceptions(
        business_data: List[Dict],
        executive_kpis: Dict,
        alert_thresholds: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Detect business anomalies and generate executive alerts."""

        if alert_thresholds is None:
            alert_thresholds = {
                "revenue_decline_threshold": -10.0,  # % decline
                "conversion_rate_drop": -15.0,  # % drop
                "customer_acquisition_drop": -20.0,  # % drop
                "roi_threshold": 0.5,  # Minimum ROI
                "health_score_threshold": 40.0,  # Minimum health score
            }

        df = pd.DataFrame(business_data)
        alerts = []
        exceptions = []

        # Check revenue trends
        revenue_growth = (
            executive_kpis.get("executive_kpis", {})
            .get("revenue", {})
            .get("growth_rate", 0)
        )
        if revenue_growth < alert_thresholds["revenue_decline_threshold"]:
            alerts.append(
                {
                    "type": "revenue_decline",
                    "severity": "high",
                    "message": f"Revenue declined by {abs(revenue_growth):.1f}% month-over-month",
                    "current_value": float(revenue_growth),
                    "threshold": float(alert_thresholds["revenue_decline_threshold"]),
                    "recommended_action": "Review sales pipeline and market conditions",
                }
            )

        # Check conversion rate performance
        conversion_change = (
            executive_kpis.get("executive_kpis", {})
            .get("conversion_rate", {})
            .get("change_rate", 0)
        )
        if conversion_change < alert_thresholds["conversion_rate_drop"]:
            alerts.append(
                {
                    "type": "conversion_rate_drop",
                    "severity": "medium",
                    "message": f"Conversion rate dropped by {abs(conversion_change):.1f}%",
                    "current_value": float(conversion_change),
                    "threshold": float(alert_thresholds["conversion_rate_drop"]),
                    "recommended_action": "Analyze lead quality and sales process effectiveness",
                }
            )

        # Check customer acquisition trends
        customer_growth = (
            executive_kpis.get("executive_kpis", {})
            .get("customer_acquisition", {})
            .get("growth_rate", 0)
        )
        if customer_growth < alert_thresholds["customer_acquisition_drop"]:
            alerts.append(
                {
                    "type": "customer_acquisition_decline",
                    "severity": "high",
                    "message": f"Customer acquisition dropped by {abs(customer_growth):.1f}%",
                    "current_value": float(customer_growth),
                    "threshold": float(alert_thresholds["customer_acquisition_drop"]),
                    "recommended_action": "Increase marketing spend and review acquisition channels",
                }
            )

        # Check for ROI outliers by department
        for _, row in df.iterrows():
            if row["roi"] < alert_thresholds["roi_threshold"]:
                exceptions.append(
                    {
                        "type": "low_roi",
                        "department": row["department"],
                        "date": row["report_date"],
                        "roi_value": float(row["roi"]),
                        "message": f"{row['department']} department ROI below threshold",
                        "severity": "medium",
                    }
                )

        # Check overall business health
        health_score = (
            executive_kpis.get("executive_kpis", {})
            .get("business_health", {})
            .get("overall_score", 100)
        )
        if health_score < alert_thresholds["health_score_threshold"]:
            alerts.append(
                {
                    "type": "business_health_concern",
                    "severity": "high",
                    "message": f"Overall business health score is {health_score:.1f}",
                    "current_value": float(health_score),
                    "threshold": float(alert_thresholds["health_score_threshold"]),
                    "recommended_action": "Conduct comprehensive business review and implement improvement plan",
                }
            )

        # Statistical anomaly detection (simple Z-score approach)
        revenue_data = df["revenue"].values
        revenue_mean = np.mean(revenue_data)
        revenue_std = np.std(revenue_data)

        for _, row in df.iterrows():
            z_score = (
                abs((row["revenue"] - revenue_mean) / revenue_std)
                if revenue_std > 0
                else 0
            )
            if z_score > 2.5:  # More than 2.5 standard deviations
                exceptions.append(
                    {
                        "type": "revenue_anomaly",
                        "department": row["department"],
                        "date": row["report_date"],
                        "revenue": float(row["revenue"]),
                        "z_score": float(round(z_score, 2)),
                        "message": f"Unusual revenue pattern detected for {row['department']}",
                        "severity": "low" if z_score < 3 else "medium",
                    }
                )

        # Generate executive summary
        alert_summary = {
            "total_alerts": int(len(alerts)),
            "high_severity": int(len([a for a in alerts if a["severity"] == "high"])),
            "medium_severity": int(
                len([a for a in alerts if a["severity"] == "medium"])
            ),
            "low_severity": int(len([a for a in alerts if a["severity"] == "low"])),
            "requires_immediate_attention": bool(
                len([a for a in alerts if a["severity"] == "high"]) > 0
            ),
        }

        return {
            "alerts": alerts,
            "exceptions": exceptions,
            "alert_summary": alert_summary,
            "alert_thresholds_used": alert_thresholds,
            "detection_timestamp": datetime.now().isoformat(),
        }

    return PythonCodeNode.from_function(
        func=detect_business_exceptions,
        name="exception_detector",
        description="Detect business anomalies and generate executive alerts",
    )


def create_report_generator():
    """Create a node that generates executive reports and dashboards."""

    def generate_executive_report(
        executive_kpis: Dict, alert_data: Dict, report_type: str = "monthly_executive"
    ) -> Dict[str, Any]:
        """Generate comprehensive executive report with insights and recommendations."""

        kpis = executive_kpis.get("executive_kpis", {})
        alerts = alert_data.get("alerts", [])
        alert_summary = alert_data.get("alert_summary", {})

        # Executive Summary Section
        executive_summary = {
            "report_period": executive_kpis.get("data_period", "N/A"),
            "report_type": report_type,
            "business_health_score": kpis.get("business_health", {}).get(
                "overall_score", 0
            ),
            "key_highlights": [],
            "priority_actions": [],
        }

        # Analyze key metrics for highlights
        revenue_data = kpis.get("revenue", {})
        if revenue_data.get("growth_rate", 0) > 5:
            executive_summary["key_highlights"].append(
                f"Strong revenue growth of {revenue_data['growth_rate']:.1f}% month-over-month"
            )
        elif revenue_data.get("growth_rate", 0) < -5:
            executive_summary["key_highlights"].append(
                f"Revenue declined {abs(revenue_data['growth_rate']):.1f}% - requires attention"
            )

        customer_data = kpis.get("customer_acquisition", {})
        if customer_data.get("growth_rate", 0) > 10:
            executive_summary["key_highlights"].append(
                f"Excellent customer acquisition growth of {customer_data['growth_rate']:.1f}%"
            )

        # Generate priority actions based on alerts
        high_severity_alerts = [a for a in alerts if a["severity"] == "high"]
        for alert in high_severity_alerts[:3]:  # Top 3 priority actions
            executive_summary["priority_actions"].append(
                {
                    "issue": alert["type"],
                    "description": alert["message"],
                    "recommended_action": alert.get(
                        "recommended_action", "Review and investigate"
                    ),
                }
            )

        # Performance Dashboard Data
        dashboard_data = {
            "revenue_metrics": {
                "current_month_revenue": revenue_data.get("current_month", 0),
                "previous_month_revenue": revenue_data.get("previous_month", 0),
                "growth_rate": revenue_data.get("growth_rate", 0),
                "growth_trend": (
                    "positive" if revenue_data.get("growth_rate", 0) > 0 else "negative"
                ),
            },
            "customer_metrics": {
                "current_month_customers": customer_data.get("current_month", 0),
                "previous_month_customers": customer_data.get("previous_month", 0),
                "acquisition_growth": customer_data.get("growth_rate", 0),
                "acquisition_trend": (
                    "positive"
                    if customer_data.get("growth_rate", 0) > 0
                    else "negative"
                ),
            },
            "conversion_metrics": kpis.get("conversion_rate", {}),
            "department_performance": kpis.get("department_performance", {}),
            "business_health": kpis.get("business_health", {}),
        }

        # Risk Assessment
        risk_assessment = {
            "overall_risk_level": "low",
            "risk_factors": [],
            "mitigation_strategies": [],
        }

        if alert_summary.get("high_severity", 0) > 0:
            risk_assessment["overall_risk_level"] = "high"
            risk_assessment["risk_factors"].append(
                "Multiple high-severity business alerts detected"
            )
            risk_assessment["mitigation_strategies"].append(
                "Immediate executive review and action plan required"
            )
        elif alert_summary.get("medium_severity", 0) > 2:
            risk_assessment["overall_risk_level"] = "medium"
            risk_assessment["risk_factors"].append(
                "Several medium-severity issues requiring attention"
            )
            risk_assessment["mitigation_strategies"].append(
                "Schedule management review within 48 hours"
            )

        if kpis.get("business_health", {}).get("overall_score", 100) < 60:
            risk_assessment["risk_factors"].append(
                "Business health score below optimal range"
            )
            risk_assessment["mitigation_strategies"].append(
                "Implement comprehensive business improvement plan"
            )

        # Recommendations
        recommendations = {
            "immediate_actions": [],
            "strategic_initiatives": [],
            "performance_improvements": [],
        }

        # Generate recommendations based on performance
        if revenue_data.get("growth_rate", 0) < 0:
            recommendations["immediate_actions"].append(
                "Conduct sales pipeline review and accelerate deal closure"
            )
            recommendations["strategic_initiatives"].append(
                "Evaluate market positioning and competitive strategy"
            )

        if customer_data.get("growth_rate", 0) < 5:
            recommendations["performance_improvements"].append(
                "Optimize customer acquisition channels and increase marketing effectiveness"
            )

        conversion_rate = kpis.get("conversion_rate", {}).get("current_month", 0)
        if conversion_rate < 0.15:  # Below 15%
            recommendations["performance_improvements"].append(
                "Improve sales process and lead qualification to increase conversion rates"
            )

        # Final Report Structure
        executive_report = {
            "executive_summary": executive_summary,
            "dashboard_data": dashboard_data,
            "risk_assessment": risk_assessment,
            "recommendations": recommendations,
            "detailed_kpis": kpis,
            "alert_summary": alert_summary,
            "report_metadata": {
                "generated_at": datetime.now().isoformat(),
                "report_version": "1.0",
                "next_report_due": (datetime.now() + timedelta(days=30)).strftime(
                    "%Y-%m-%d"
                ),
            },
        }

        return {
            "executive_report": executive_report,
            "report_generation_successful": True,
            "report_size_kb": len(json.dumps(executive_report)) / 1024,
        }

    return PythonCodeNode.from_function(
        func=generate_executive_report,
        name="report_generator",
        description="Generate comprehensive executive reports and dashboards",
    )


def main():
    """Execute the business intelligence and reporting workflow."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    print("📊 Starting Business Intelligence & Reporting Workflows")
    print("=" * 70)

    # Create workflow
    print("📋 Creating business intelligence workflow...")
    workflow = Workflow(
        workflow_id="business_intelligence_reporting",
        name="business_intelligence_reporting",
        description="Enterprise business intelligence and automated reporting workflow",
    )

    # Add enterprise metadata
    workflow.metadata.update(
        {
            "version": "3.0.0",
            "report_type": "executive_dashboard",
            "stakeholders": ["CEO", "CFO", "COO", "VPs"],
            "compliance": {
                "sarbanes_oxley": True,
                "data_retention_years": 7,
                "financial_reporting": True,
            },
            "automation": {
                "schedule": "monthly",
                "distribution_list": ["executives@company.com", "board@company.com"],
                "alert_escalation": True,
            },
        }
    )

    # Create nodes
    data_generator = create_business_data_generator()
    kpi_calculator = create_kpi_calculator()
    exception_detector = create_exception_detector()
    report_generator = create_report_generator()

    # Output writers
    raw_data_writer = CSVWriterNode(
        file_path=str(data_dir / "business_metrics_raw.csv")
    )

    executive_report_writer = JSONWriterNode(
        file_path=str(data_dir / "executive_dashboard.json")
    )

    alerts_writer = JSONWriterNode(file_path=str(data_dir / "business_alerts.json"))

    # Add nodes to workflow
    workflow.add_node(
        node_id="data_generator",
        node_or_type=data_generator,
        config={
            "months_back": 12,
            "departments": [
                "Sales",
                "Marketing",
                "Operations",
                "Customer Success",
                "Finance",
            ],
            "include_anomalies": True,
        },
    )
    workflow.add_node(node_id="kpi_calculator", node_or_type=kpi_calculator)
    workflow.add_node(
        node_id="exception_detector",
        node_or_type=exception_detector,
        config={
            "alert_thresholds": {
                "revenue_decline_threshold": -10.0,
                "conversion_rate_drop": -15.0,
                "customer_acquisition_drop": -20.0,
                "roi_threshold": 0.5,
                "health_score_threshold": 40.0,
            }
        },
    )
    workflow.add_node(
        node_id="report_generator",
        node_or_type=report_generator,
        config={"report_type": "monthly_executive"},
    )
    workflow.add_node(node_id="raw_data_writer", node_or_type=raw_data_writer)
    workflow.add_node(
        node_id="executive_report_writer", node_or_type=executive_report_writer
    )
    workflow.add_node(node_id="alerts_writer", node_or_type=alerts_writer)

    # Connect nodes using dot notation
    workflow.connect(
        "data_generator", "kpi_calculator", {"result.business_data": "business_data"}
    )
    workflow.connect(
        "data_generator", "raw_data_writer", {"result.business_data": "data"}
    )
    workflow.connect(
        "kpi_calculator", "exception_detector", {"result": "executive_kpis"}
    )
    workflow.connect(
        "data_generator",
        "exception_detector",
        {"result.business_data": "business_data"},
    )
    workflow.connect("kpi_calculator", "report_generator", {"result": "executive_kpis"})
    workflow.connect("exception_detector", "report_generator", {"result": "alert_data"})
    workflow.connect("report_generator", "executive_report_writer", {"result": "data"})
    workflow.connect("exception_detector", "alerts_writer", {"result": "data"})

    # Validate workflow
    print("✅ Validating workflow...")
    try:
        workflow.validate()
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Execute workflow
    print("🚀 Executing business intelligence workflow...")

    try:
        # Use enterprise runtime with monitoring
        runner = LocalRuntime(debug=True, enable_monitoring=True, enable_audit=True)

        # Provide runtime parameters to ensure all required inputs are supplied
        runtime_params = {
            "data_generator": {
                "months_back": 12,
                "departments": [
                    "Sales",
                    "Marketing",
                    "Operations",
                    "Customer Success",
                    "Finance",
                ],
                "include_anomalies": True,
            },
            "exception_detector": {
                "alert_thresholds": {
                    "revenue_decline_threshold": -10.0,
                    "conversion_rate_drop": -15.0,
                    "customer_acquisition_drop": -20.0,
                    "roi_threshold": 0.5,
                    "health_score_threshold": 40.0,
                }
            },
            "report_generator": {"report_type": "monthly_executive"},
        }

        results, run_id = runner.execute(workflow, parameters=runtime_params)

        print("✓ Business intelligence workflow completed successfully!")
        print(f"  📊 Run ID: {run_id}")

        # Display executive dashboard results
        if "report_generator" in results:
            report_result = results["report_generator"]
            if isinstance(report_result, dict) and "result" in report_result:
                report_data = report_result["result"]

                if "executive_report" in report_data:
                    executive_report = report_data["executive_report"]

                    print("\n📈 Executive Dashboard Summary:")
                    print("-" * 50)

                    # Business Health Score
                    health_score = executive_report["dashboard_data"][
                        "business_health"
                    ]["overall_score"]
                    health_status = executive_report["dashboard_data"][
                        "business_health"
                    ]["health_status"]
                    print(
                        f"  🎯 Business Health Score: {health_score:.1f}/100 ({health_status.upper()})"
                    )

                    # Revenue Performance
                    revenue_metrics = executive_report["dashboard_data"][
                        "revenue_metrics"
                    ]
                    print(
                        f"  💰 Current Month Revenue: ${revenue_metrics['current_month_revenue']:,.2f}"
                    )
                    print(
                        f"  📊 Revenue Growth: {revenue_metrics['growth_rate']:+.1f}% MoM"
                    )

                    # Customer Metrics
                    customer_metrics = executive_report["dashboard_data"][
                        "customer_metrics"
                    ]
                    print(
                        f"  👥 Customers Acquired: {customer_metrics['current_month_customers']}"
                    )
                    print(
                        f"  📈 Customer Growth: {customer_metrics['acquisition_growth']:+.1f}% MoM"
                    )

                    # Key Highlights
                    highlights = executive_report["executive_summary"]["key_highlights"]
                    if highlights:
                        print("  ✨ Key Highlights:")
                        for highlight in highlights[:3]:
                            print(f"    • {highlight}")

                    # Priority Actions
                    priority_actions = executive_report["executive_summary"][
                        "priority_actions"
                    ]
                    if priority_actions:
                        print("  🚨 Priority Actions:")
                        for action in priority_actions[:2]:
                            print(f"    • {action['description']}")

        # Display alerts summary
        if "exception_detector" in results:
            alert_result = results["exception_detector"]
            if isinstance(alert_result, dict) and "result" in alert_result:
                alert_data = alert_result["result"]
                alert_summary = alert_data.get("alert_summary", {})

                print("\n🚨 Business Alerts Summary:")
                print("-" * 50)
                print(f"  • Total Alerts: {alert_summary.get('total_alerts', 0)}")
                print(f"  • High Severity: {alert_summary.get('high_severity', 0)}")
                print(f"  • Medium Severity: {alert_summary.get('medium_severity', 0)}")
                print(
                    f"  • Requires Immediate Attention: {'Yes' if alert_summary.get('requires_immediate_attention') else 'No'}"
                )

                # Show top alerts
                alerts = alert_data.get("alerts", [])
                if alerts:
                    print("  📋 Recent Alerts:")
                    for alert in alerts[:3]:
                        severity_icon = (
                            "🔴"
                            if alert["severity"] == "high"
                            else "🟡" if alert["severity"] == "medium" else "🟢"
                        )
                        print(f"    {severity_icon} {alert['message']}")

        print("\n📁 Generated Reports:")
        print(f"  • Executive Dashboard: {data_dir}/executive_dashboard.json")
        print(f"  • Business Alerts: {data_dir}/business_alerts.json")
        print(f"  • Raw Business Data: {data_dir}/business_metrics_raw.csv")

    except Exception as e:
        print(f"✗ Workflow execution failed: {e}")
        return 1

    print("\n🎉 Business Intelligence & Reporting completed!")
    print("📊 This workflow demonstrates:")
    print("  • Executive KPI calculation and trend analysis")
    print("  • Automated business exception detection")
    print("  • Comprehensive executive dashboard generation")
    print("  • Risk assessment and strategic recommendations")
    print("  • Regulatory compliance reporting capabilities")
    print("  • Real-time business health monitoring")

    return 0


if __name__ == "__main__":
    sys.exit(main())
