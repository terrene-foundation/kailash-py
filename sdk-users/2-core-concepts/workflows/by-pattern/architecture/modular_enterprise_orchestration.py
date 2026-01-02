#!/usr/bin/env python3
"""
Modular Enterprise Orchestration - Production Business Solution

Enterprise microservices orchestration with hierarchical workflow composition:
1. Modular business service architecture with reusable workflow components
2. Multi-tier enterprise application orchestration (API → Service → Data layers)
3. Dynamic service composition with runtime parameter injection
4. Enterprise service mesh integration with monitoring and governance
5. Cross-functional business process automation with compliance tracking
6. Production-ready error handling and service resilience patterns

Business Value:
- Modular architecture reduces development time and increases code reusability
- Service orchestration enables complex business processes across departments
- Dynamic composition allows rapid adaptation to changing business requirements
- Enterprise governance ensures compliance and operational visibility
- Microservices patterns improve scalability and maintainability
- Production monitoring provides real-time service health and performance insights

Key Features:
- WorkflowNode for hierarchical service composition and microservices orchestration
- PythonCodeNode for business logic implementation with enterprise patterns
- Multi-level service abstraction (Core → Composite → Application → Business)
- LocalRuntime with enterprise monitoring, security, and compliance
- Dynamic parameter mapping for flexible service configuration
- Production-ready service mesh patterns with monitoring and governance
"""

import json
import logging
import random
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

# Add examples directory to path for utils import
examples_dir = project_root / "examples"
sys.path.insert(0, str(examples_dir))

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.writers import JSONWriterNode
from kailash.nodes.logic.operations import WorkflowNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.graph import Workflow

from examples.utils.paths import get_data_dir

# Configure enterprise-focused logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# CORE BUSINESS SERVICE LAYER - Foundational microservices
# ============================================================================


@register_node()
class CustomerDataServiceNode(Node):
    """Core customer data service - foundational microservice."""

    def get_parameters(self):
        return {
            "customer_count": NodeParameter(
                name="customer_count",
                type=int,
                required=False,
                default=50,
                description="Number of customers to process",
            ),
            "include_analytics": NodeParameter(
                name="include_analytics",
                type=bool,
                required=False,
                default=True,
                description="Include customer analytics data",
            ),
        }

    def run(self, customer_count=50, include_analytics=True):
        """Generate enterprise customer data with business intelligence."""

        # Simulate customer data service
        customers = []
        customer_tiers = ["Bronze", "Silver", "Gold", "Platinum"]
        industries = ["Technology", "Healthcare", "Finance", "Manufacturing", "Retail"]
        regions = ["North America", "Europe", "Asia Pacific", "Latin America"]

        for i in range(customer_count):
            customer_tier = random.choice(customer_tiers)

            # Business logic for customer value based on tier
            if customer_tier == "Platinum":
                base_value = random.uniform(50000, 200000)
                satisfaction_score = random.uniform(8.5, 10.0)
            elif customer_tier == "Gold":
                base_value = random.uniform(20000, 50000)
                satisfaction_score = random.uniform(7.0, 9.0)
            elif customer_tier == "Silver":
                base_value = random.uniform(5000, 20000)
                satisfaction_score = random.uniform(6.0, 8.0)
            else:  # Bronze
                base_value = random.uniform(1000, 5000)
                satisfaction_score = random.uniform(5.0, 7.5)

            customer = {
                "customer_id": f"CUST_{10000 + i:05d}",
                "customer_name": f"Customer Corp {i+1}",
                "tier": customer_tier,
                "industry": random.choice(industries),
                "region": random.choice(regions),
                "annual_value": round(base_value, 2),
                "satisfaction_score": round(satisfaction_score, 1),
                "contract_start": (
                    datetime.now() - timedelta(days=random.randint(30, 1095))
                ).strftime("%Y-%m-%d"),
                "is_active": random.choice([True, True, True, False]),  # 75% active
                "service_id": str(uuid.uuid4()),
            }

            if include_analytics:
                customer["analytics"] = {
                    "engagement_score": round(random.uniform(1, 10), 1),
                    "churn_risk": (
                        "high"
                        if satisfaction_score < 6.0
                        else "medium" if satisfaction_score < 8.0 else "low"
                    ),
                    "lifetime_value_prediction": round(
                        base_value * random.uniform(1.5, 3.0), 2
                    ),
                    "last_interaction": (
                        datetime.now() - timedelta(days=random.randint(1, 90))
                    ).strftime("%Y-%m-%d"),
                }

            customers.append(customer)

        # Service metadata
        service_metadata = {
            "service_name": "customer_data_service",
            "version": "v2.1.0",
            "processed_at": datetime.now().isoformat(),
            "total_customers": len(customers),
            "active_customers": len([c for c in customers if c["is_active"]]),
            "tier_distribution": {
                tier: len([c for c in customers if c["tier"] == tier])
                for tier in customer_tiers
            },
        }

        return {"customers": customers, "service_metadata": service_metadata}


@register_node()
class FinancialDataServiceNode(Node):
    """Core financial data service - handles revenue and financial metrics."""

    def get_parameters(self):
        return {
            "customers": NodeParameter(
                name="customers",
                type=list,
                required=False,
                description="Customer data for financial analysis",
            ),
            "include_forecasting": NodeParameter(
                name="include_forecasting",
                type=bool,
                required=False,
                default=True,
                description="Include financial forecasting",
            ),
        }

    def run(self, customers=None, include_forecasting=True):
        """Process financial data and generate revenue metrics."""

        if customers is None:
            customers = []

        financial_data = []
        total_revenue = 0
        total_forecasted_revenue = 0

        for customer in customers:
            # Calculate financial metrics per customer
            annual_value = customer.get("annual_value", 0)
            monthly_revenue = annual_value / 12

            # Simulate actual vs forecasted performance
            actual_performance = random.uniform(0.8, 1.2)  # 80% to 120% of expected
            actual_monthly = monthly_revenue * actual_performance

            financial_record = {
                "customer_id": customer.get("customer_id"),
                "tier": customer.get("tier"),
                "annual_contract_value": annual_value,
                "monthly_revenue": round(monthly_revenue, 2),
                "actual_monthly_revenue": round(actual_monthly, 2),
                "performance_vs_forecast": round(actual_performance, 3),
                "payment_status": random.choice(
                    ["current", "current", "current", "overdue"]
                ),  # 75% current
                "billing_cycle": random.choice(["monthly", "quarterly", "annual"]),
                "currency": "USD",
            }

            if include_forecasting:
                # 12-month revenue forecast
                forecast_trend = random.uniform(0.95, 1.15)  # -5% to +15% growth
                forecasted_annual = annual_value * forecast_trend

                financial_record["forecasting"] = {
                    "forecasted_annual_revenue": round(forecasted_annual, 2),
                    "growth_rate_prediction": round((forecast_trend - 1) * 100, 1),
                    "confidence_level": round(random.uniform(0.7, 0.95), 2),
                    "forecast_horizon_months": 12,
                }
                total_forecasted_revenue += forecasted_annual

            financial_data.append(financial_record)
            total_revenue += actual_monthly * 12  # Annualized

        # Financial service summary
        service_summary = {
            "total_annual_revenue": round(total_revenue, 2),
            "average_customer_value": (
                round(total_revenue / len(customers), 2) if customers else 0
            ),
            "total_forecasted_revenue": round(total_forecasted_revenue, 2),
            "revenue_growth_projection": (
                round(
                    (
                        (
                            total_forecasted_revenue
                            - sum(c.get("annual_value", 0) for c in customers)
                        )
                        / sum(c.get("annual_value", 0) for c in customers)
                        * 100
                    ),
                    1,
                )
                if customers
                else 0
            ),
            "overdue_customers": len(
                [f for f in financial_data if f["payment_status"] == "overdue"]
            ),
            "service_processed_at": datetime.now().isoformat(),
        }

        return {"financial_data": financial_data, "financial_summary": service_summary}


@register_node()
class OperationsDataServiceNode(Node):
    """Core operations data service - handles operational metrics and KPIs."""

    def get_parameters(self):
        return {
            "customers": NodeParameter(
                name="customers",
                type=list,
                required=False,
                description="Customer data for operations analysis",
            ),
            "financial_data": NodeParameter(
                name="financial_data",
                type=list,
                required=False,
                description="Financial data for operational correlation",
            ),
        }

    def run(self, customers=None, financial_data=None):
        """Generate operational metrics and service performance data."""

        if customers is None:
            customers = []
        if financial_data is None:
            financial_data = []

        operational_metrics = []
        service_tickets = 0
        total_support_cost = 0

        for customer in customers:
            customer_id = customer.get("customer_id")
            tier = customer.get("tier", "Bronze")

            # Generate operational metrics per customer
            if tier == "Platinum":
                support_tickets = random.randint(5, 15)
                support_cost_per_ticket = random.uniform(200, 500)
                sla_compliance = random.uniform(95, 99)
            elif tier == "Gold":
                support_tickets = random.randint(3, 10)
                support_cost_per_ticket = random.uniform(150, 350)
                sla_compliance = random.uniform(90, 97)
            elif tier == "Silver":
                support_tickets = random.randint(1, 6)
                support_cost_per_ticket = random.uniform(100, 250)
                sla_compliance = random.uniform(85, 95)
            else:  # Bronze
                support_tickets = random.randint(0, 4)
                support_cost_per_ticket = random.uniform(80, 200)
                sla_compliance = random.uniform(80, 92)

            customer_support_cost = support_tickets * support_cost_per_ticket

            operational_record = {
                "customer_id": customer_id,
                "tier": tier,
                "support_tickets_monthly": support_tickets,
                "support_cost_monthly": round(customer_support_cost, 2),
                "sla_compliance_percentage": round(sla_compliance, 1),
                "avg_response_time_hours": round(random.uniform(1, 24), 1),
                "customer_success_score": round(random.uniform(6, 10), 1),
                "infrastructure_utilization": round(random.uniform(0.3, 0.9), 2),
                "api_calls_monthly": random.randint(1000, 50000),
                "uptime_percentage": round(random.uniform(98, 99.9), 2),
            }

            operational_metrics.append(operational_record)
            service_tickets += support_tickets
            total_support_cost += customer_support_cost

        # Operational service summary
        operations_summary = {
            "total_monthly_support_tickets": service_tickets,
            "total_monthly_support_cost": round(total_support_cost, 2),
            "average_sla_compliance": (
                round(
                    sum(o["sla_compliance_percentage"] for o in operational_metrics)
                    / len(operational_metrics),
                    1,
                )
                if operational_metrics
                else 0
            ),
            "average_response_time": (
                round(
                    sum(o["avg_response_time_hours"] for o in operational_metrics)
                    / len(operational_metrics),
                    1,
                )
                if operational_metrics
                else 0
            ),
            "total_api_calls": sum(o["api_calls_monthly"] for o in operational_metrics),
            "average_uptime": (
                round(
                    sum(o["uptime_percentage"] for o in operational_metrics)
                    / len(operational_metrics),
                    2,
                )
                if operational_metrics
                else 0
            ),
            "service_health_score": round(random.uniform(85, 98), 1),
            "operations_processed_at": datetime.now().isoformat(),
        }

        return {
            "operational_metrics": operational_metrics,
            "operations_summary": operations_summary,
        }


# ============================================================================
# COMPOSITE SERVICE LAYER - Business domain services
# ============================================================================


def create_customer_analytics_service():
    """Create composite customer analytics service from core services."""

    workflow = Workflow(
        workflow_id="customer_analytics_service",
        name="Customer Analytics Service",
        description="Composite service for comprehensive customer analytics",
    )

    # Add core services
    customer_service = CustomerDataServiceNode(name="customer_data_service")
    financial_service = FinancialDataServiceNode(name="financial_data_service")
    operations_service = OperationsDataServiceNode(name="operations_data_service")

    # Analytics aggregator
    def aggregate_customer_insights(
        customers: List[Dict],
        financial_data: List[Dict],
        operational_metrics: List[Dict],
    ) -> Dict[str, Any]:
        """Aggregate multi-dimensional customer insights."""

        customer_insights = []

        for customer in customers:
            customer_id = customer["customer_id"]

            # Find related financial and operational data
            financial_record = next(
                (f for f in financial_data if f["customer_id"] == customer_id), {}
            )
            operational_record = next(
                (o for o in operational_metrics if o["customer_id"] == customer_id), {}
            )

            # Calculate comprehensive customer score
            satisfaction = customer.get("satisfaction_score", 5)
            sla_compliance = operational_record.get("sla_compliance_percentage", 85)
            payment_status = financial_record.get("payment_status", "unknown")

            # Business health score calculation
            health_score = (
                (satisfaction / 10 * 30)  # 30% weight on satisfaction
                + (sla_compliance / 100 * 25)  # 25% weight on SLA
                + (25 if payment_status == "current" else 5)  # 25% weight on payment
                + (
                    20 if customer.get("is_active") else 0
                )  # 20% weight on active status
            )

            insight = {
                "customer_id": customer_id,
                "customer_name": customer["customer_name"],
                "tier": customer["tier"],
                "business_health_score": round(health_score, 1),
                "customer_summary": {
                    "annual_value": customer.get("annual_value", 0),
                    "satisfaction_score": satisfaction,
                    "churn_risk": customer.get("analytics", {}).get(
                        "churn_risk", "unknown"
                    ),
                    "is_active": customer.get("is_active", False),
                },
                "financial_summary": {
                    "monthly_revenue": financial_record.get(
                        "actual_monthly_revenue", 0
                    ),
                    "payment_status": payment_status,
                    "growth_prediction": financial_record.get("forecasting", {}).get(
                        "growth_rate_prediction", 0
                    ),
                },
                "operational_summary": {
                    "support_tickets": operational_record.get(
                        "support_tickets_monthly", 0
                    ),
                    "sla_compliance": sla_compliance,
                    "customer_success_score": operational_record.get(
                        "customer_success_score", 5
                    ),
                },
                "recommendations": [],
            }

            # Generate business recommendations
            if health_score < 50:
                insight["recommendations"].append(
                    "Priority: Customer at risk - immediate intervention required"
                )
            if financial_record.get("payment_status") == "overdue":
                insight["recommendations"].append(
                    "Financial: Follow up on overdue payments"
                )
            if customer.get("analytics", {}).get("churn_risk") == "high":
                insight["recommendations"].append(
                    "Retention: High churn risk - initiate retention campaign"
                )
            if operational_record.get("support_tickets_monthly", 0) > 10:
                insight["recommendations"].append(
                    "Operations: High support volume - review service delivery"
                )

            customer_insights.append(insight)

        # Service-level analytics
        service_analytics = {
            "total_customers_analyzed": len(customer_insights),
            "average_health_score": (
                round(
                    sum(c["business_health_score"] for c in customer_insights)
                    / len(customer_insights),
                    1,
                )
                if customer_insights
                else 0
            ),
            "high_value_customers": len(
                [
                    c
                    for c in customer_insights
                    if c["customer_summary"]["annual_value"] > 20000
                ]
            ),
            "at_risk_customers": len(
                [c for c in customer_insights if c["business_health_score"] < 50]
            ),
            "total_recommendations": sum(
                len(c["recommendations"]) for c in customer_insights
            ),
            "analytics_generated_at": datetime.now().isoformat(),
        }

        return {
            "customer_insights": customer_insights,
            "service_analytics": service_analytics,
        }

    analytics_aggregator = PythonCodeNode.from_function(
        func=aggregate_customer_insights,
        name="analytics_aggregator",
        description="Aggregate comprehensive customer insights from multiple services",
    )

    # Add nodes to workflow
    workflow.add_node("customer_service", customer_service)
    workflow.add_node("financial_service", financial_service)
    workflow.add_node("operations_service", operations_service)
    workflow.add_node("analytics_aggregator", analytics_aggregator)

    # Connect services
    workflow.connect(
        "customer_service", "financial_service", {"customers": "customers"}
    )
    workflow.connect(
        "customer_service", "operations_service", {"customers": "customers"}
    )
    workflow.connect(
        "financial_service", "operations_service", {"financial_data": "financial_data"}
    )

    # Connect to aggregator
    workflow.connect(
        "customer_service", "analytics_aggregator", {"customers": "customers"}
    )
    workflow.connect(
        "financial_service",
        "analytics_aggregator",
        {"financial_data": "financial_data"},
    )
    workflow.connect(
        "operations_service",
        "analytics_aggregator",
        {"operational_metrics": "operational_metrics"},
    )

    return workflow


def create_executive_reporting_service():
    """Create executive reporting service using customer analytics."""

    workflow = Workflow(
        workflow_id="executive_reporting_service",
        name="Executive Reporting Service",
        description="Executive-level reporting and dashboard service",
    )

    # Use customer analytics as a composed service
    analytics_service = create_customer_analytics_service()
    analytics_node = WorkflowNode(
        workflow=analytics_service,
        name="customer_analytics_service_node",
        description="Customer analytics microservice",
    )

    # Executive report generator
    def generate_executive_report(
        customer_insights: List[Dict], service_analytics: Dict
    ) -> Dict[str, Any]:
        """Generate executive-level business report."""

        # Executive KPIs
        total_customers = service_analytics.get("total_customers_analyzed", 0)
        high_value_customers = service_analytics.get("high_value_customers", 0)
        at_risk_customers = service_analytics.get("at_risk_customers", 0)
        avg_health_score = service_analytics.get("average_health_score", 0)

        # Revenue analysis
        total_annual_revenue = sum(
            c["customer_summary"]["annual_value"] for c in customer_insights
        )
        total_monthly_revenue = sum(
            c["financial_summary"]["monthly_revenue"] for c in customer_insights
        )

        # Customer segmentation
        tier_analysis = {}
        for insight in customer_insights:
            tier = insight["tier"]
            if tier not in tier_analysis:
                tier_analysis[tier] = {"count": 0, "revenue": 0, "avg_health": 0}
            tier_analysis[tier]["count"] += 1
            tier_analysis[tier]["revenue"] += insight["customer_summary"][
                "annual_value"
            ]
            tier_analysis[tier]["avg_health"] += insight["business_health_score"]

        # Calculate averages
        for tier_data in tier_analysis.values():
            if tier_data["count"] > 0:
                tier_data["avg_health"] = round(
                    tier_data["avg_health"] / tier_data["count"], 1
                )
                tier_data["revenue"] = round(tier_data["revenue"], 2)

        # Executive summary
        executive_summary = {
            "business_overview": {
                "total_customers": total_customers,
                "annual_revenue": round(total_annual_revenue, 2),
                "monthly_recurring_revenue": round(total_monthly_revenue, 2),
                "average_customer_health": avg_health_score,
            },
            "customer_portfolio": {
                "high_value_customers": high_value_customers,
                "at_risk_customers": at_risk_customers,
                "customer_health_distribution": {
                    "excellent": len(
                        [
                            c
                            for c in customer_insights
                            if c["business_health_score"] >= 80
                        ]
                    ),
                    "good": len(
                        [
                            c
                            for c in customer_insights
                            if 60 <= c["business_health_score"] < 80
                        ]
                    ),
                    "fair": len(
                        [
                            c
                            for c in customer_insights
                            if 40 <= c["business_health_score"] < 60
                        ]
                    ),
                    "poor": len(
                        [
                            c
                            for c in customer_insights
                            if c["business_health_score"] < 40
                        ]
                    ),
                },
            },
            "tier_analysis": tier_analysis,
            "key_insights": [
                f"Portfolio health score: {avg_health_score}/100",
                f"High-value customers represent {high_value_customers}/{total_customers} of portfolio",
                f"At-risk customers requiring attention: {at_risk_customers}",
                f"Monthly recurring revenue: ${total_monthly_revenue:,.2f}",
            ],
            "action_items": [],
        }

        # Generate action items
        if at_risk_customers > 0:
            executive_summary["action_items"].append(
                f"Customer Success: Address {at_risk_customers} at-risk customers"
            )

        if avg_health_score < 70:
            executive_summary["action_items"].append(
                "Strategic: Overall customer health below target - review service delivery"
            )

        churn_risk_high = len(
            [
                c
                for c in customer_insights
                if c["customer_summary"]["churn_risk"] == "high"
            ]
        )
        if churn_risk_high > 0:
            executive_summary["action_items"].append(
                f"Retention: Immediate action needed for {churn_risk_high} high churn-risk customers"
            )

        # Report metadata
        report_metadata = {
            "report_type": "executive_dashboard",
            "generated_at": datetime.now().isoformat(),
            "report_period": "current_month",
            "data_sources": [
                "customer_service",
                "financial_service",
                "operations_service",
            ],
            "service_version": "v1.0.0",
        }

        return {
            "executive_report": executive_summary,
            "report_metadata": report_metadata,
        }

    report_generator = PythonCodeNode.from_function(
        func=generate_executive_report,
        name="executive_report_generator",
        description="Generate executive business reports and dashboards",
    )

    # Add nodes to workflow
    workflow.add_node("analytics_service", analytics_node)
    workflow.add_node("report_generator", report_generator)

    # Connect analytics to report generator
    workflow.connect(
        "analytics_service",
        "report_generator",
        {
            "analytics_aggregator_customer_insights": "customer_insights",
            "analytics_aggregator_service_analytics": "service_analytics",
        },
    )

    return workflow


# ============================================================================
# APPLICATION LAYER - Enterprise applications
# ============================================================================


def main():
    """Execute the modular enterprise orchestration workflow."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)

    print("🏢 Starting Modular Enterprise Orchestration")
    print("=" * 70)

    # Demonstrate multi-level service composition
    print("🔧 Creating multi-tier enterprise service architecture...")
    print("  📊 Layer 1: Core Services (Customer, Financial, Operations)")
    print("  🔀 Layer 2: Composite Services (Customer Analytics)")
    print("  📈 Layer 3: Application Services (Executive Reporting)")
    print("  🎯 Layer 4: Business Applications (Enterprise Dashboard)")

    # Create the enterprise application workflow
    enterprise_app = Workflow(
        workflow_id="enterprise_dashboard_application",
        name="Enterprise Dashboard Application",
        description="Multi-tier enterprise application with microservices orchestration",
    )

    # Add enterprise metadata
    enterprise_app.metadata.update(
        {
            "version": "3.0.0",
            "architecture": "microservices",
            "service_mesh": "istio",
            "deployment": "kubernetes",
            "compliance": {"soc2": True, "gdpr": True, "hipaa": False},
            "monitoring": {
                "observability": "prometheus_grafana",
                "logging": "elk_stack",
                "tracing": "jaeger",
            },
        }
    )

    # Use executive reporting service as the main application service
    executive_service = create_executive_reporting_service()
    executive_node = WorkflowNode(
        workflow=executive_service,
        name="executive_reporting_application",
        description="Executive reporting application service",
        input_mapping={
            "customer_count": {
                "node": "analytics_service",
                "parameter": "customer_service_customer_count",
                "type": int,
                "required": False,
                "default": 100,
                "description": "Number of customers to analyze",
            },
            "include_forecasting": {
                "node": "analytics_service",
                "parameter": "financial_service_include_forecasting",
                "type": bool,
                "required": False,
                "default": True,
                "description": "Include financial forecasting in analysis",
            },
        },
        output_mapping={
            "business_health": {
                "node": "report_generator",
                "output": "executive_report.business_overview.average_customer_health",
                "type": float,
                "description": "Overall business health score",
            },
            "monthly_revenue": {
                "node": "report_generator",
                "output": "executive_report.business_overview.monthly_recurring_revenue",
                "type": float,
                "description": "Monthly recurring revenue",
            },
            "at_risk_customers": {
                "node": "report_generator",
                "output": "executive_report.customer_portfolio.at_risk_customers",
                "type": int,
                "description": "Number of at-risk customers",
            },
        },
    )

    # Application audit logger
    def log_application_metrics(
        business_health: float, monthly_revenue: float, at_risk_customers: int
    ) -> Dict[str, Any]:
        """Log enterprise application metrics for monitoring."""

        # Application performance metrics
        app_metrics = {
            "application_name": "enterprise_dashboard",
            "execution_timestamp": datetime.now().isoformat(),
            "business_kpis": {
                "business_health_score": business_health,
                "monthly_recurring_revenue": monthly_revenue,
                "at_risk_customers": at_risk_customers,
                "health_status": (
                    "excellent"
                    if business_health >= 80
                    else "good" if business_health >= 70 else "needs_attention"
                ),
            },
            "service_performance": {
                "response_time_ms": random.randint(150, 500),
                "cpu_utilization": round(random.uniform(0.2, 0.7), 2),
                "memory_utilization": round(random.uniform(0.3, 0.8), 2),
                "api_calls_per_minute": random.randint(50, 200),
            },
            "compliance_status": {
                "data_governance": "compliant",
                "audit_trail_complete": True,
                "access_control_verified": True,
                "encryption_enabled": True,
            },
        }

        return {
            "application_metrics": app_metrics,
            "monitoring_status": "active",
            "compliance_verified": True,
        }

    audit_logger = PythonCodeNode.from_function(
        func=log_application_metrics,
        name="application_audit_logger",
        description="Log enterprise application metrics and compliance status",
    )

    # Output writers for different stakeholders
    executive_dashboard_writer = JSONWriterNode(
        file_path=str(data_dir / "executive_dashboard.json")
    )

    audit_log_writer = JSONWriterNode(
        file_path=str(data_dir / "application_audit_log.json")
    )

    # Add nodes to enterprise application
    enterprise_app.add_node("executive_service", executive_node)
    enterprise_app.add_node("audit_logger", audit_logger)
    enterprise_app.add_node("dashboard_writer", executive_dashboard_writer)
    enterprise_app.add_node("audit_writer", audit_log_writer)

    # Connect enterprise application components
    enterprise_app.connect(
        "executive_service",
        "audit_logger",
        {
            "business_health": "business_health",
            "monthly_revenue": "monthly_revenue",
            "at_risk_customers": "at_risk_customers",
        },
    )
    enterprise_app.connect(
        "executive_service",
        "dashboard_writer",
        {"report_generator_executive_report": "data"},
    )
    enterprise_app.connect("audit_logger", "audit_writer", {"result": "data"})

    # Validate enterprise application
    print("✅ Validating enterprise application architecture...")
    try:
        enterprise_app.validate()
        print("✓ Enterprise application validation successful!")
    except Exception as e:
        print(f"✗ Enterprise application validation failed: {e}")
        return 1

    # Execute enterprise application with different business scenarios
    test_scenarios = [
        {
            "name": "Small Business Portfolio",
            "description": "Small enterprise with focused customer base",
            "parameters": {
                "executive_service": {"customer_count": 25, "include_forecasting": True}
            },
        },
        {
            "name": "Mid-Market Enterprise",
            "description": "Mid-size enterprise with diverse customer portfolio",
            "parameters": {
                "executive_service": {"customer_count": 75, "include_forecasting": True}
            },
        },
        {
            "name": "Large Enterprise Portfolio",
            "description": "Large enterprise with extensive customer base",
            "parameters": {
                "executive_service": {
                    "customer_count": 150,
                    "include_forecasting": True,
                }
            },
        },
    ]

    print("🚀 Executing enterprise orchestration scenarios...")

    for i, scenario in enumerate(test_scenarios):
        print(f"\n📊 Scenario {i + 1}/3: {scenario['name']}")
        print("-" * 60)
        print(f"Description: {scenario['description']}")

        try:
            # Use enterprise runtime with full monitoring
            runner = LocalRuntime(
                debug=True,
                enable_monitoring=True,
                enable_audit=False,  # Using custom audit logger
                max_concurrency=5,
            )

            results, run_id = runner.execute(
                enterprise_app, parameters=scenario["parameters"]
            )

            print("✓ Enterprise orchestration completed successfully!")
            print(f"  🔧 Run ID: {run_id}")

            # Display executive dashboard results
            if "executive_service" in results:
                service_result = results["executive_service"]

                # Extract key business metrics
                business_health = service_result.get("business_health", 0)
                monthly_revenue = service_result.get("monthly_revenue", 0)
                at_risk_customers = service_result.get("at_risk_customers", 0)

                print("  📈 Executive Metrics:")
                print(f"    • Business Health Score: {business_health:.1f}/100")
                print(f"    • Monthly Recurring Revenue: ${monthly_revenue:,.2f}")
                print(f"    • At-Risk Customers: {at_risk_customers}")

                # Health status assessment
                if business_health >= 80:
                    print("    🟢 Status: Excellent business health")
                elif business_health >= 70:
                    print("    🟡 Status: Good business health")
                else:
                    print("    🔴 Status: Needs attention")

            # Display application performance
            if "audit_logger" in results:
                audit_result = results["audit_logger"]
                if isinstance(audit_result, dict) and "result" in audit_result:
                    app_metrics = audit_result["result"]["application_metrics"]
                    performance = app_metrics["service_performance"]

                    print("  ⚡ Application Performance:")
                    print(f"    • Response Time: {performance['response_time_ms']}ms")
                    print(
                        f"    • CPU Utilization: {performance['cpu_utilization']*100:.1f}%"
                    )
                    print(
                        f"    • Memory Utilization: {performance['memory_utilization']*100:.1f}%"
                    )
                    print(f"    • API Calls/min: {performance['api_calls_per_minute']}")

        except Exception as e:
            print(f"✗ Scenario execution failed: {e}")
            print(f"  Error Type: {type(e).__name__}")

    print("\n🎉 Modular Enterprise Orchestration completed!")
    print("📊 Architecture demonstrated:")
    print("  🏗️  Multi-tier microservices architecture (4 layers)")
    print("  🔄 Hierarchical workflow composition with WorkflowNode")
    print("  📈 Enterprise business intelligence and reporting")
    print("  🔒 Service mesh patterns with monitoring and governance")
    print("  📋 Production-ready compliance and audit logging")
    print("  ⚡ Dynamic service composition with parameter mapping")

    print("\n📁 Generated Enterprise Outputs:")
    print(f"  • Executive Dashboard: {data_dir}/executive_dashboard.json")
    print(f"  • Application Audit Log: {data_dir}/application_audit_log.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
