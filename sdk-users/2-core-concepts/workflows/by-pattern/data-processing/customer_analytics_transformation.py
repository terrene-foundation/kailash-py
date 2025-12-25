#!/usr/bin/env python3
"""
Customer Analytics Data Transformation - Production Business Solution

Comprehensive data transformation pipeline for customer analytics:
1. Advanced data cleaning with business rule validation
2. Feature engineering for customer lifetime value and segmentation
3. Real-time data quality monitoring and alerting
4. Customer behavioral analytics and scoring
5. Multi-dimensional aggregation for business intelligence
6. Data lineage tracking and governance compliance

Business Value:
- Customer segmentation for targeted marketing campaigns
- Lifetime value prediction drives pricing and retention strategies
- Data quality monitoring ensures reliable business decisions
- Behavioral analytics enable personalization and recommendations
- Automated feature engineering reduces time-to-insight
- Compliance tracking meets data governance requirements

Key Features:
- Production-grade data cleaning with comprehensive validation
- Auto-mapping parameters for seamless data flow
- LocalRuntime with enterprise monitoring and quality tracking
- Dot notation mapping for complex nested data structures
- Business intelligence dashboards and KPI tracking
- Real-time data quality scoring and alerting
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

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
from kailash.nodes.data.readers import CSVReaderNode
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
    """Create realistic customer data for demonstration."""

    def generate_customer_data(record_count: int = 500) -> Dict[str, Any]:
        """Generate realistic customer data with business patterns."""

        np.random.seed(42)  # Reproducible data

        # Customer segments with realistic distributions
        segments = ["Enterprise", "SMB", "Consumer", "Startup"]
        segment_weights = [0.15, 0.25, 0.45, 0.15]

        # Industry categories
        industries = [
            "Technology",
            "Healthcare",
            "Finance",
            "Retail",
            "Manufacturing",
            "Education",
        ]

        # Regions with realistic distribution
        regions = [
            "North America",
            "Europe",
            "Asia Pacific",
            "Latin America",
            "Middle East",
        ]
        region_weights = [0.35, 0.25, 0.25, 0.10, 0.05]

        customers = []

        for i in range(record_count):
            # Basic customer info
            customer_segment = np.random.choice(segments, p=segment_weights)
            region = np.random.choice(regions, p=region_weights)
            industry = np.random.choice(industries)

            # Age distribution varies by segment
            if customer_segment == "Enterprise":
                age = int(np.random.normal(45, 10))
            elif customer_segment == "SMB":
                age = int(np.random.normal(38, 8))
            elif customer_segment == "Startup":
                age = int(np.random.normal(32, 6))
            else:  # Consumer
                age = int(np.random.normal(35, 12))

            age = max(18, min(75, age))  # Constrain to realistic range

            # Income varies by segment and region
            base_income = {
                "Enterprise": 120000,
                "SMB": 80000,
                "Consumer": 55000,
                "Startup": 70000,
            }[customer_segment]

            # Regional income adjustments
            region_multiplier = {
                "North America": 1.2,
                "Europe": 1.0,
                "Asia Pacific": 0.8,
                "Latin America": 0.6,
                "Middle East": 0.9,
            }[region]

            income = int(
                np.random.normal(base_income * region_multiplier, base_income * 0.3)
            )
            income = max(25000, income)  # Minimum income

            # Purchase behavior varies by segment
            if customer_segment == "Enterprise":
                purchase_count = int(np.random.poisson(15))
                avg_purchase_value = np.random.normal(2500, 800)
            elif customer_segment == "SMB":
                purchase_count = int(np.random.poisson(8))
                avg_purchase_value = np.random.normal(800, 300)
            elif customer_segment == "Startup":
                purchase_count = int(np.random.poisson(5))
                avg_purchase_value = np.random.normal(400, 200)
            else:  # Consumer
                purchase_count = int(np.random.poisson(3))
                avg_purchase_value = np.random.normal(150, 75)

            avg_purchase_value = max(10, avg_purchase_value)  # Minimum purchase value

            # Days since last purchase (recency)
            days_since_last = int(np.random.exponential(45))
            days_since_last = min(365, days_since_last)  # Cap at 1 year

            # Support interactions
            support_tickets = int(np.random.poisson(purchase_count * 0.1))

            # Contract value (for B2B segments)
            if customer_segment in ["Enterprise", "SMB", "Startup"]:
                annual_contract_value = (
                    avg_purchase_value * purchase_count * random.uniform(0.8, 1.5)
                )
            else:
                annual_contract_value = 0

            customer = {
                "customer_id": f"CUST_{i+1000:04d}",
                "name": f"Customer {i+1}",
                "email": f"customer.{i+1}@{random.choice(['company', 'business', 'corp', 'inc', 'org'])}.com",
                "age": age,
                "income": income,
                "customer_segment": customer_segment,
                "industry": industry,
                "region": region,
                "purchase_count": purchase_count,
                "avg_purchase_value": round(avg_purchase_value, 2),
                "total_spent": round(purchase_count * avg_purchase_value, 2),
                "days_since_last_purchase": days_since_last,
                "support_tickets": support_tickets,
                "annual_contract_value": round(annual_contract_value, 2),
                "registration_date": (
                    datetime.now() - timedelta(days=random.randint(30, 1095))
                ).strftime("%Y-%m-%d"),
                "is_active": days_since_last <= 90,
                "satisfaction_score": round(random.uniform(1.0, 5.0), 1),
            }

            customers.append(customer)

        # Add some data quality issues for testing
        # Missing values
        for i in random.sample(range(len(customers)), min(20, len(customers) // 10)):
            customers[i]["income"] = None

        for i in random.sample(range(len(customers)), min(15, len(customers) // 15)):
            customers[i]["satisfaction_score"] = None

        # Duplicates
        if len(customers) > 50:
            for i in range(5):
                duplicate_idx = random.randint(0, len(customers) - 1)
                customers.append(customers[duplicate_idx].copy())

        # Invalid values
        if len(customers) > 10:
            customers[random.randint(0, 9)]["age"] = -5
            customers[random.randint(0, 9)]["age"] = 150
            customers[random.randint(0, 9)]["income"] = -50000

        return {"customers": customers}

    return PythonCodeNode.from_function(
        func=generate_customer_data,
        name="business_data_generator",
        description="Generates realistic customer data with business patterns",
    )


def create_advanced_data_cleaner():
    """Create advanced data cleaning with business rule validation."""

    def clean_customer_data(customers: List[Dict]) -> Dict[str, Any]:
        """Advanced data cleaning with business rule validation."""

        df = pd.DataFrame(customers)
        initial_count = len(df)

        cleaning_report = {
            "initial_count": initial_count,
            "duplicates_removed": 0,
            "invalid_records_removed": 0,
            "missing_values_imputed": {},
            "business_rule_violations": [],
            "data_quality_improvements": [],
        }

        # Remove exact duplicates
        df_before = len(df)
        df = df.drop_duplicates()
        cleaning_report["duplicates_removed"] = df_before - len(df)

        # Business rule validations
        business_violations = []

        # Age validation
        invalid_age = df[(df["age"] < 18) | (df["age"] > 100)]
        if len(invalid_age) > 0:
            business_violations.append(
                f"Removed {len(invalid_age)} customers with invalid age"
            )
            df = df[(df["age"] >= 18) & (df["age"] <= 100)]

        # Income validation
        invalid_income = df[df["income"] < 0]
        if len(invalid_income) > 0:
            business_violations.append(
                f"Fixed {len(invalid_income)} customers with negative income"
            )
            df.loc[df["income"] < 0, "income"] = df["income"].median()

        # Purchase validation
        invalid_purchases = df[df["purchase_count"] < 0]
        if len(invalid_purchases) > 0:
            business_violations.append(
                f"Fixed {len(invalid_purchases)} customers with negative purchase count"
            )
            df.loc[df["purchase_count"] < 0, "purchase_count"] = 0

        cleaning_report["business_rule_violations"] = business_violations
        cleaning_report["invalid_records_removed"] = (
            initial_count - len(df) - cleaning_report["duplicates_removed"]
        )

        # Intelligent missing value imputation
        imputation_report = {}

        # Income imputation based on segment and region
        if df["income"].isnull().sum() > 0:
            missing_before = df["income"].isnull().sum()

            # Group by segment and region for more accurate imputation
            for segment in df["customer_segment"].unique():
                for region in df["region"].unique():
                    mask = (
                        (df["customer_segment"] == segment)
                        & (df["region"] == region)
                        & df["income"].isnull()
                    )
                    if mask.sum() > 0:
                        # Use median income for same segment/region
                        segment_region_median = df[
                            (df["customer_segment"] == segment)
                            & (df["region"] == region)
                            & df["income"].notnull()
                        ]["income"].median()

                        if pd.notna(segment_region_median):
                            df.loc[mask, "income"] = segment_region_median
                        else:
                            # Fallback to overall median
                            df.loc[mask, "income"] = df["income"].median()

            imputation_report["income"] = (
                f"Imputed {missing_before} missing income values using segment/region-based approach"
            )

        # Satisfaction score imputation
        if df["satisfaction_score"].isnull().sum() > 0:
            missing_before = df["satisfaction_score"].isnull().sum()
            # Use segment-based median satisfaction
            for segment in df["customer_segment"].unique():
                mask = (df["customer_segment"] == segment) & df[
                    "satisfaction_score"
                ].isnull()
                if mask.sum() > 0:
                    segment_median = df[
                        (df["customer_segment"] == segment)
                        & df["satisfaction_score"].notnull()
                    ]["satisfaction_score"].median()

                    if pd.notna(segment_median):
                        df.loc[mask, "satisfaction_score"] = segment_median
                    else:
                        df.loc[mask, "satisfaction_score"] = 3.5  # Neutral default

            imputation_report["satisfaction_score"] = (
                f"Imputed {missing_before} missing satisfaction scores using segment-based approach"
            )

        cleaning_report["missing_values_imputed"] = imputation_report

        # Data standardization
        standardization_actions = []

        # Standardize email format
        df["email"] = df["email"].str.lower().str.strip()
        standardization_actions.append("Standardized email format to lowercase")

        # Standardize customer segment names
        df["customer_segment"] = df["customer_segment"].str.title()
        standardization_actions.append("Standardized customer segment names")

        # Ensure numeric precision
        numeric_columns = [
            "income",
            "avg_purchase_value",
            "total_spent",
            "annual_contract_value",
            "satisfaction_score",
        ]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                if col in [
                    "avg_purchase_value",
                    "total_spent",
                    "annual_contract_value",
                ]:
                    df[col] = df[col].round(2)
                elif col == "satisfaction_score":
                    df[col] = df[col].round(1)

        standardization_actions.append("Ensured numeric precision for financial fields")

        cleaning_report["data_quality_improvements"] = standardization_actions
        cleaning_report["final_count"] = len(df)
        cleaning_report["data_retention_rate"] = round(
            (len(df) / initial_count) * 100, 2
        )

        return {
            "cleaned_customers": df.to_dict(orient="records"),
            "cleaning_report": cleaning_report,
        }

    return PythonCodeNode.from_function(
        func=clean_customer_data,
        name="advanced_data_cleaner",
        description="Advanced data cleaning with business rule validation",
    )


def create_customer_feature_engineer():
    """Create advanced feature engineering for customer analytics."""

    def engineer_customer_features(cleaned_customers: List[Dict]) -> Dict[str, Any]:
        """Engineer advanced features for customer analytics and machine learning."""

        df = pd.DataFrame(cleaned_customers)
        features_created = []

        # Customer Lifetime Value (CLV) calculation
        # CLV = (Average Purchase Value) × (Purchase Frequency) × (Gross Margin) × (Lifespan)
        # Simplified version for demonstration
        purchase_frequency = df["purchase_count"] / (
            (datetime.now() - pd.to_datetime(df["registration_date"])).dt.days / 365.25
        )
        df["purchase_frequency_annual"] = purchase_frequency.round(2)

        # Estimated CLV (simplified calculation)
        df["estimated_clv"] = (
            df["avg_purchase_value"] * df["purchase_frequency_annual"] * 0.2 * 3
        ).round(
            2
        )  # 20% margin, 3 year lifespan
        features_created.append("estimated_clv")
        features_created.append("purchase_frequency_annual")

        # Customer segmentation based on RFM analysis
        # Recency (days since last purchase)
        df["recency_score"] = pd.qcut(
            df["days_since_last_purchase"],
            q=5,
            labels=[5, 4, 3, 2, 1],
            duplicates="drop",
        )

        # Frequency (purchase count)
        df["frequency_score"] = pd.qcut(
            df["purchase_count"], q=5, labels=[1, 2, 3, 4, 5], duplicates="drop"
        )

        # Monetary (total spent)
        df["monetary_score"] = pd.qcut(
            df["total_spent"], q=5, labels=[1, 2, 3, 4, 5], duplicates="drop"
        )

        # Combined RFM score
        df["rfm_score"] = (
            df["recency_score"].astype(str)
            + df["frequency_score"].astype(str)
            + df["monetary_score"].astype(str)
        )

        features_created.extend(
            ["recency_score", "frequency_score", "monetary_score", "rfm_score"]
        )

        # Customer value segments
        def categorize_customer_value(row):
            r, f, m = (
                int(row["recency_score"]),
                int(row["frequency_score"]),
                int(row["monetary_score"]),
            )
            if r >= 4 and f >= 4 and m >= 4:
                return "Champions"
            elif r >= 3 and f >= 3 and m >= 3:
                return "Loyal Customers"
            elif r >= 4 and f <= 2:
                return "New Customers"
            elif r <= 2 and f >= 3 and m >= 3:
                return "At Risk"
            elif r <= 2 and f <= 2:
                return "Lost Customers"
            else:
                return "Potential Loyalists"

        df["customer_value_segment"] = df.apply(categorize_customer_value, axis=1)
        features_created.append("customer_value_segment")

        # Age-based segments
        df["age_group"] = pd.cut(
            df["age"],
            bins=[0, 25, 35, 45, 55, 100],
            labels=["Gen Z", "Millennial", "Gen X Early", "Gen X Late", "Boomer+"],
        )
        features_created.append("age_group")

        # Income categories with regional adjustment
        df["income_category"] = pd.qcut(
            df["income"],
            q=4,
            labels=["Low Income", "Middle Income", "Upper Middle", "High Income"],
            duplicates="drop",
        )
        features_created.append("income_category")

        # Customer lifecycle stage
        days_since_registration = (
            datetime.now() - pd.to_datetime(df["registration_date"])
        ).dt.days

        def determine_lifecycle_stage(row):
            days_reg = (datetime.now() - pd.to_datetime(row["registration_date"])).days
            if days_reg <= 30:
                return "New"
            elif days_reg <= 180:
                return "Growing"
            elif row["is_active"]:
                return "Mature"
            elif row["days_since_last_purchase"] <= 180:
                return "Declining"
            else:
                return "Dormant"

        df["lifecycle_stage"] = df.apply(determine_lifecycle_stage, axis=1)
        features_created.append("lifecycle_stage")

        # Engagement score (composite metric)
        # Normalize metrics to 0-1 scale
        normalized_purchase_freq = (
            df["purchase_frequency_annual"] - df["purchase_frequency_annual"].min()
        ) / (
            df["purchase_frequency_annual"].max()
            - df["purchase_frequency_annual"].min()
        )
        normalized_satisfaction = (df["satisfaction_score"] - 1) / 4  # 1-5 scale to 0-1
        normalized_recency = 1 - (
            (df["days_since_last_purchase"] - df["days_since_last_purchase"].min())
            / (
                df["days_since_last_purchase"].max()
                - df["days_since_last_purchase"].min()
            )
        )

        df["engagement_score"] = (
            (normalized_purchase_freq * 0.4)
            + (normalized_satisfaction * 0.3)
            + (normalized_recency * 0.3)
        ).round(3)
        features_created.append("engagement_score")

        # Industry risk assessment
        industry_risk = {
            "Technology": "High Growth",
            "Healthcare": "Stable",
            "Finance": "Regulated",
            "Retail": "Volatile",
            "Manufacturing": "Cyclical",
            "Education": "Stable",
        }
        df["industry_risk_profile"] = df["industry"].map(industry_risk)
        features_created.append("industry_risk_profile")

        # Support burden indicator
        df["support_burden"] = (
            (df["support_tickets"] / df["purchase_count"]).fillna(0).round(3)
        )
        features_created.append("support_burden")

        # Churn risk prediction (simplified)
        def calculate_churn_risk(row):
            risk_score = 0

            # High risk factors
            if row["days_since_last_purchase"] > 90:
                risk_score += 30
            if row["satisfaction_score"] < 3:
                risk_score += 25
            if row["support_burden"] > 0.5:
                risk_score += 20
            if row["engagement_score"] < 0.3:
                risk_score += 15

            # Protective factors
            if row["customer_segment"] == "Enterprise":
                risk_score -= 15
            if row["annual_contract_value"] > 10000:
                risk_score -= 10

            risk_score = max(0, min(100, risk_score))  # Constrain to 0-100

            if risk_score >= 70:
                return "High Risk"
            elif risk_score >= 40:
                return "Medium Risk"
            else:
                return "Low Risk"

        df["churn_risk"] = df.apply(calculate_churn_risk, axis=1)
        features_created.append("churn_risk")

        # Feature engineering summary
        feature_summary = {
            "total_features_created": len(features_created),
            "feature_categories": {
                "financial": ["estimated_clv", "purchase_frequency_annual"],
                "behavioral": ["rfm_score", "engagement_score", "lifecycle_stage"],
                "demographic": ["age_group", "income_category"],
                "risk": ["churn_risk", "industry_risk_profile"],
                "operational": ["support_burden", "customer_value_segment"],
            },
            "features_created": features_created,
        }

        return {
            "enriched_customers": df.to_dict(orient="records"),
            "feature_summary": feature_summary,
        }

    return PythonCodeNode.from_function(
        func=engineer_customer_features,
        name="customer_feature_engineer",
        description="Engineer advanced features for customer analytics",
    )


def create_business_intelligence_aggregator():
    """Create business intelligence aggregations."""

    def create_business_aggregations(enriched_customers: List[Dict]) -> Dict[str, Any]:
        """Create comprehensive business intelligence aggregations."""

        df = pd.DataFrame(enriched_customers)

        aggregations = {}

        # Customer segment analysis
        segment_analysis = (
            df.groupby("customer_segment")
            .agg(
                {
                    "customer_id": "count",
                    "estimated_clv": ["mean", "sum", "std"],
                    "total_spent": ["mean", "sum"],
                    "engagement_score": "mean",
                    "satisfaction_score": "mean",
                    "annual_contract_value": "sum",
                }
            )
            .round(2)
        )

        segment_analysis.columns = [
            "_".join(col).strip() for col in segment_analysis.columns
        ]
        aggregations["segment_analysis"] = segment_analysis.reset_index().to_dict(
            orient="records"
        )

        # Regional performance
        regional_analysis = (
            df.groupby("region")
            .agg(
                {
                    "customer_id": "count",
                    "total_spent": "sum",
                    "estimated_clv": "mean",
                    "purchase_count": "mean",
                    "satisfaction_score": "mean",
                }
            )
            .round(2)
        )

        regional_analysis.columns = [
            "_".join(col).strip() for col in regional_analysis.columns
        ]
        aggregations["regional_analysis"] = regional_analysis.reset_index().to_dict(
            orient="records"
        )

        # Industry insights
        industry_analysis = (
            df.groupby("industry")
            .agg(
                {
                    "customer_id": "count",
                    "annual_contract_value": ["mean", "sum"],
                    "churn_risk": lambda x: (x == "High Risk").sum(),
                    "engagement_score": "mean",
                }
            )
            .round(2)
        )

        industry_analysis.columns = [
            "_".join(col).strip() for col in industry_analysis.columns
        ]
        aggregations["industry_analysis"] = industry_analysis.reset_index().to_dict(
            orient="records"
        )

        # Customer value segment distribution
        value_segment_dist = df["customer_value_segment"].value_counts().to_dict()
        aggregations["value_segment_distribution"] = value_segment_dist

        # Churn risk distribution
        churn_risk_dist = df["churn_risk"].value_counts().to_dict()
        aggregations["churn_risk_distribution"] = churn_risk_dist

        # Key business metrics
        business_metrics = {
            "total_customers": len(df),
            "total_revenue": df["total_spent"].sum(),
            "average_clv": df["estimated_clv"].mean(),
            "high_value_customers": len(
                df[df["customer_value_segment"] == "Champions"]
            ),
            "at_risk_customers": len(df[df["churn_risk"] == "High Risk"]),
            "average_satisfaction": df["satisfaction_score"].mean(),
            "average_engagement": df["engagement_score"].mean(),
            "enterprise_customers": len(df[df["customer_segment"] == "Enterprise"]),
            "total_contract_value": df["annual_contract_value"].sum(),
        }

        # Round numeric values
        for key, value in business_metrics.items():
            if isinstance(value, float):
                business_metrics[key] = round(value, 2)

        aggregations["business_metrics"] = business_metrics

        return {"business_aggregations": aggregations}

    return PythonCodeNode.from_function(
        func=create_business_aggregations,
        name="business_intelligence_aggregator",
        description="Create comprehensive business intelligence aggregations",
    )


def create_data_quality_monitor():
    """Create comprehensive data quality monitoring."""

    def monitor_data_quality(enriched_customers: List[Dict]) -> Dict[str, Any]:
        """Comprehensive data quality monitoring and scoring."""

        df = pd.DataFrame(enriched_customers)

        quality_report = {
            "timestamp": datetime.now().isoformat(),
            "total_records": len(df),
            "quality_dimensions": {},
            "alerts": [],
            "recommendations": [],
        }

        # Completeness Analysis
        completeness = {}
        critical_fields = ["customer_id", "email", "customer_segment", "estimated_clv"]

        for field in critical_fields:
            if field in df.columns:
                completeness[field] = {
                    "complete_count": df[field].notna().sum(),
                    "missing_count": df[field].isna().sum(),
                    "completeness_rate": (df[field].notna().sum() / len(df)) * 100,
                }

        overall_completeness = np.mean(
            [v["completeness_rate"] for v in completeness.values()]
        )
        quality_report["quality_dimensions"]["completeness"] = {
            "score": round(overall_completeness, 2),
            "field_analysis": completeness,
        }

        # Uniqueness Analysis
        uniqueness = {}
        unique_fields = ["customer_id", "email"]

        for field in unique_fields:
            if field in df.columns:
                unique_count = df[field].nunique()
                total_count = len(df)
                duplicate_count = total_count - unique_count

                uniqueness[field] = {
                    "unique_count": unique_count,
                    "duplicate_count": duplicate_count,
                    "uniqueness_rate": (unique_count / total_count) * 100,
                }

        overall_uniqueness = np.mean(
            [v["uniqueness_rate"] for v in uniqueness.values()]
        )
        quality_report["quality_dimensions"]["uniqueness"] = {
            "score": round(overall_uniqueness, 2),
            "field_analysis": uniqueness,
        }

        # Validity Analysis
        validity_issues = []

        # Age validation
        invalid_ages = len(df[(df["age"] < 18) | (df["age"] > 100)])
        if invalid_ages > 0:
            validity_issues.append(f"{invalid_ages} customers with invalid age")

        # Income validation
        invalid_income = len(df[df["income"] < 0])
        if invalid_income > 0:
            validity_issues.append(f"{invalid_income} customers with negative income")

        # Email validation (basic)
        invalid_emails = len(df[~df["email"].str.contains("@", na=False)])
        if invalid_emails > 0:
            validity_issues.append(
                f"{invalid_emails} customers with invalid email format"
            )

        validity_score = max(0, 100 - (len(validity_issues) / len(df)) * 100)
        quality_report["quality_dimensions"]["validity"] = {
            "score": round(validity_score, 2),
            "issues": validity_issues,
        }

        # Consistency Analysis
        consistency_issues = []

        # Check CLV consistency
        clv_inconsistent = len(
            df[(df["estimated_clv"] > 0) & (df["purchase_count"] == 0)]
        )
        if clv_inconsistent > 0:
            consistency_issues.append(
                f"{clv_inconsistent} customers with CLV but no purchases"
            )

        # Check segment consistency
        enterprise_low_value = len(
            df[(df["customer_segment"] == "Enterprise") & (df["total_spent"] < 1000)]
        )
        if enterprise_low_value > 0:
            consistency_issues.append(
                f"{enterprise_low_value} Enterprise customers with low total spend"
            )

        consistency_score = max(0, 100 - (len(consistency_issues) / len(df)) * 100)
        quality_report["quality_dimensions"]["consistency"] = {
            "score": round(consistency_score, 2),
            "issues": consistency_issues,
        }

        # Overall Quality Score
        dimension_scores = [
            quality_report["quality_dimensions"]["completeness"]["score"],
            quality_report["quality_dimensions"]["uniqueness"]["score"],
            quality_report["quality_dimensions"]["validity"]["score"],
            quality_report["quality_dimensions"]["consistency"]["score"],
        ]

        overall_quality_score = np.mean(dimension_scores)
        quality_report["overall_quality_score"] = round(overall_quality_score, 2)

        # Quality Alerts
        alerts = []
        if overall_quality_score < 90:
            alerts.append(
                {
                    "level": "WARNING",
                    "message": f"Overall data quality score ({overall_quality_score:.1f}%) below 90% threshold",
                    "action": "Review data quality issues and implement improvements",
                }
            )

        if quality_report["quality_dimensions"]["completeness"]["score"] < 95:
            alerts.append(
                {
                    "level": "WARNING",
                    "message": "Critical field completeness below 95%",
                    "action": "Investigate missing data sources and implement validation",
                }
            )

        if quality_report["quality_dimensions"]["uniqueness"]["score"] < 99:
            alerts.append(
                {
                    "level": "INFO",
                    "message": "Duplicate records detected",
                    "action": "Review deduplication processes",
                }
            )

        quality_report["alerts"] = alerts

        # Recommendations
        recommendations = []
        if overall_quality_score >= 95:
            recommendations.append(
                "Excellent data quality - maintain current processes"
            )
        elif overall_quality_score >= 85:
            recommendations.append("Good data quality - minor improvements needed")
        else:
            recommendations.append(
                "Data quality improvement required - implement comprehensive data governance"
            )

        quality_report["recommendations"] = recommendations

        # Quality trend (simulated)
        quality_report["quality_trend"] = {
            "current_score": overall_quality_score,
            "previous_score": overall_quality_score + random.uniform(-2, 2),
            "trend": "stable",  # In production, this would track historical scores
        }

        return {"quality_report": quality_report}

    return PythonCodeNode.from_function(
        func=monitor_data_quality,
        name="data_quality_monitor",
        description="Comprehensive data quality monitoring and scoring",
    )


def main():
    """Execute the comprehensive customer analytics transformation workflow."""

    # Create data directories
    data_dir = get_data_dir()
    data_dir.mkdir(exist_ok=True)
    output_dir = data_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    print("🔄 Starting Customer Analytics Data Transformation Workflow")
    print("=" * 80)

    # Create workflow with business focus
    print("📋 Creating customer analytics transformation workflow...")
    workflow = Workflow(
        workflow_id="customer_analytics_transformation",
        name="customer_analytics_transformation",
        description="Production customer analytics data transformation pipeline",
    )

    # Create nodes for comprehensive data transformation
    print("🔧 Creating transformation nodes...")

    # Data generation and processing nodes
    data_generator = create_business_data_generator()
    data_cleaner = create_advanced_data_cleaner()
    feature_engineer = create_customer_feature_engineer()
    bi_aggregator = create_business_intelligence_aggregator()
    quality_monitor = create_data_quality_monitor()

    # Add nodes to workflow
    workflow.add_node(node_id="data_generator", node_or_type=data_generator)
    workflow.add_node(node_id="data_cleaner", node_or_type=data_cleaner)
    workflow.add_node(node_id="feature_engineer", node_or_type=feature_engineer)
    workflow.add_node(node_id="bi_aggregator", node_or_type=bi_aggregator)
    workflow.add_node(node_id="quality_monitor", node_or_type=quality_monitor)

    # Connect nodes using dot notation for nested data access
    print("🔗 Connecting transformation pipeline...")

    # Data flow: generate → clean → engineer → aggregate & monitor
    workflow.connect(
        "data_generator", "data_cleaner", {"result.customers": "customers"}
    )
    workflow.connect(
        "data_cleaner",
        "feature_engineer",
        {"result.cleaned_customers": "cleaned_customers"},
    )
    workflow.connect(
        "feature_engineer",
        "bi_aggregator",
        {"result.enriched_customers": "enriched_customers"},
    )
    workflow.connect(
        "feature_engineer",
        "quality_monitor",
        {"result.enriched_customers": "enriched_customers"},
    )

    # Validate workflow
    print("✅ Validating transformation workflow...")
    try:
        validation_params = {"data_generator": {"record_count": 100}}
        workflow.validate(runtime_parameters=validation_params)
        print("✓ Workflow validation successful!")
    except Exception as e:
        print(f"✗ Workflow validation failed: {e}")
        return 1

    # Execute with enterprise runtime features
    print("🚀 Executing customer analytics transformation...")

    # Test scenarios with different data volumes
    test_scenarios = [
        {
            "name": "Small Dataset Analysis",
            "description": "Small dataset for rapid prototyping",
            "parameters": {"data_generator": {"record_count": 100}},
        },
        {
            "name": "Medium Dataset Analysis",
            "description": "Medium dataset for comprehensive analysis",
            "parameters": {"data_generator": {"record_count": 250}},
        },
    ]

    for i, scenario in enumerate(test_scenarios):
        print(f"\n📊 Scenario {i + 1}/2: {scenario['name']}")
        print("-" * 60)
        print(f"Description: {scenario['description']}")

        try:
            # Use enterprise runtime with monitoring
            runner = LocalRuntime(
                debug=True, enable_monitoring=True, enable_audit=False
            )

            results, run_id = runner.execute(
                workflow, parameters=scenario["parameters"]
            )

            print("✓ Customer analytics transformation completed successfully!")
            print(f"  📊 Run ID: {run_id}")

            # Business intelligence reporting
            if "bi_aggregator" in results:
                bi_result = results["bi_aggregator"]
                if isinstance(bi_result, dict) and "result" in bi_result:
                    aggregations = bi_result["result"]["business_aggregations"]
                    business_metrics = aggregations.get("business_metrics", {})

                    print("\n📈 Business Intelligence Summary:")
                    print(
                        f"  • Total Customers: {business_metrics.get('total_customers', 0):,}"
                    )
                    print(
                        f"  • Total Revenue: ${business_metrics.get('total_revenue', 0):,.2f}"
                    )
                    print(
                        f"  • Average CLV: ${business_metrics.get('average_clv', 0):,.2f}"
                    )
                    print(
                        f"  • Enterprise Customers: {business_metrics.get('enterprise_customers', 0)}"
                    )
                    print(
                        f"  • High Value Customers: {business_metrics.get('high_value_customers', 0)}"
                    )
                    print(
                        f"  • At Risk Customers: {business_metrics.get('at_risk_customers', 0)}"
                    )
                    print(
                        f"  • Average Satisfaction: {business_metrics.get('average_satisfaction', 0):.1f}/5.0"
                    )

            # Data quality reporting
            if "quality_monitor" in results:
                quality_result = results["quality_monitor"]
                if isinstance(quality_result, dict) and "result" in quality_result:
                    quality_report = quality_result["result"]["quality_report"]

                    print("\n📊 Data Quality Report:")
                    print(
                        f"  • Overall Quality Score: {quality_report.get('overall_quality_score', 0):.1f}%"
                    )

                    dimensions = quality_report.get("quality_dimensions", {})
                    print(
                        f"  • Completeness: {dimensions.get('completeness', {}).get('score', 0):.1f}%"
                    )
                    print(
                        f"  • Uniqueness: {dimensions.get('uniqueness', {}).get('score', 0):.1f}%"
                    )
                    print(
                        f"  • Validity: {dimensions.get('validity', {}).get('score', 0):.1f}%"
                    )
                    print(
                        f"  • Consistency: {dimensions.get('consistency', {}).get('score', 0):.1f}%"
                    )

                    alerts = quality_report.get("alerts", [])
                    if alerts:
                        print(f"  • Quality Alerts: {len(alerts)} alerts")
                        for alert in alerts[:2]:  # Show first 2 alerts
                            print(
                                f"    - {alert.get('level', 'INFO')}: {alert.get('message', 'No message')}"
                            )

            # Feature engineering summary
            if "feature_engineer" in results:
                feature_result = results["feature_engineer"]
                if isinstance(feature_result, dict) and "result" in feature_result:
                    feature_summary = feature_result["result"]["feature_summary"]
                    print("\n🔧 Feature Engineering Summary:")
                    print(
                        f"  • Total Features Created: {feature_summary.get('total_features_created', 0)}"
                    )

                    categories = feature_summary.get("feature_categories", {})
                    for category, features in categories.items():
                        print(f"  • {category.title()} Features: {len(features)}")

        except Exception as e:
            print(f"✗ Scenario execution failed: {e}")
            print(f"  Error Type: {type(e).__name__}")

    print("\n🎉 Customer Analytics Data Transformation completed!")
    print("📊 This workflow demonstrates production-ready patterns for:")
    print("  • Advanced data cleaning with business rule validation")
    print("  • Comprehensive feature engineering for ML and analytics")
    print("  • Real-time data quality monitoring and alerting")
    print("  • Business intelligence aggregations and KPI tracking")
    print("  • Customer segmentation and lifetime value modeling")

    return 0


if __name__ == "__main__":
    sys.exit(main())
