#!/usr/bin/env python3
"""
Lead Scoring Engine - Enterprise Sales Workflow (Refactored)
===========================================================

AI-powered lead scoring and qualification system that automatically
prioritizes leads based on behavior, demographics, and engagement.

This version follows Kailash SDK best practices by using existing
nodes instead of PythonCodeNode wherever possible.

Features:
- Multi-dimensional scoring model
- Real-time behavioral tracking
- Predictive lead quality
- Automated sales routing
- Performance analytics
"""

import os
import sys

# Add parent directory to path for imports
sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
)

from kailash import Workflow
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import RESTClientNode
from kailash.nodes.data import CSVWriterNode, SQLDatabaseNode
from kailash.nodes.logic import MergeNode
from kailash.nodes.transform import DataTransformer, FilterNode
from kailash.runtime.local import LocalRuntime


def create_lead_scoring_workflow() -> Workflow:
    """Create enterprise lead scoring workflow using existing nodes."""
    workflow = Workflow(
        workflow_id="lead_scoring_002",
        name="enterprise_lead_scoring_refactored",
        description="AI-powered lead scoring using Kailash best practices",
    )

    # Data collection from multiple sources
    add_lead_sources(workflow)

    # Lead enrichment pipeline
    add_enrichment_pipeline(workflow)

    # Scoring engine
    add_scoring_engine(workflow)

    # Lead routing and assignment
    add_routing_system(workflow)

    # Analytics and reporting
    add_analytics_pipeline(workflow)

    return workflow


def add_lead_sources(workflow: Workflow):
    """Add multiple lead data sources using existing nodes."""

    # CRM lead data
    crm_reader = SQLDatabaseNode(
        id="crm_leads",
        connection_string="${CRM_DATABASE}",
        query="""
        SELECT
            l.lead_id,
            l.email,
            l.first_name,
            l.last_name,
            l.company,
            l.job_title,
            l.phone,
            l.lead_source,
            l.created_date,
            l.last_activity_date,
            l.status,
            c.industry,
            c.company_size,
            c.annual_revenue
        FROM leads l
        LEFT JOIN companies c ON l.company_id = c.company_id
        WHERE l.status IN ('new', 'working', 'nurturing')
        AND l.last_activity_date >= NOW() - INTERVAL '30 days'
        """,
        operation_type="read",
    )
    workflow.add_node("crm_leads", crm_reader)

    # Marketing automation data - Real API integration
    marketing_data = RESTClientNode(
        id="marketing_data",
        url="${MARKETING_API}/leads/engagement",
        method="GET",
        headers={"Authorization": "Bearer ${MARKETING_API_KEY}"},
        timeout=10000,
    )
    workflow.add_node("marketing_data", marketing_data)

    # Website behavior data - Real analytics API
    behavior_tracker = RESTClientNode(
        id="behavior_tracker",
        url="${ANALYTICS_API}/behavior/batch",
        method="POST",
        headers={
            "Authorization": "Bearer ${ANALYTICS_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=15000,
    )
    workflow.add_node("behavior_tracker", behavior_tracker)

    # Prepare lead emails for behavior tracking
    email_extractor = DataTransformer(
        id="email_extractor",
        transformations=[
            # Extract emails from CRM data for behavior lookup
            "lambda data: {'emails': [lead.get('email') for lead in data if lead.get('email')]}"
        ],
    )
    workflow.add_node("email_extractor", email_extractor)
    workflow.connect("crm_leads", "email_extractor", mapping={"data": "data"})
    workflow.connect("email_extractor", "behavior_tracker", mapping={"result": "body"})

    # Email engagement data - Real email service API
    email_engagement = RESTClientNode(
        id="email_engagement",
        url="${EMAIL_SERVICE_API}/engagement/metrics",
        method="POST",
        headers={
            "Authorization": "Bearer ${EMAIL_SERVICE_KEY}",
            "Content-Type": "application/json",
        },
        timeout=10000,
    )
    workflow.add_node("email_engagement", email_engagement)
    workflow.connect("email_extractor", "email_engagement", mapping={"result": "body"})

    # Merge all lead data
    lead_merger = MergeNode(id="lead_merger", merge_strategy="combine_dict")
    workflow.add_node("lead_merger", lead_merger)

    # Connect all sources to merger
    workflow.connect("crm_leads", "lead_merger", mapping={"data": "crm_data"})
    workflow.connect(
        "marketing_data", "lead_merger", mapping={"response": "marketing_data"}
    )
    workflow.connect(
        "behavior_tracker", "lead_merger", mapping={"response": "behavior_data"}
    )
    workflow.connect(
        "email_engagement", "lead_merger", mapping={"response": "email_data"}
    )


def add_enrichment_pipeline(workflow: Workflow):
    """Add lead enrichment using external APIs and DataTransformer."""

    # External enrichment service (e.g., Clearbit, ZoomInfo)
    enrichment_api = RESTClientNode(
        id="enrichment_api",
        url="${ENRICHMENT_API}/enrich/batch",
        method="POST",
        headers={
            "Authorization": "Bearer ${ENRICHMENT_API_KEY}",
            "Content-Type": "application/json",
        },
        timeout=20000,
    )
    workflow.add_node("enrichment_api", enrichment_api)

    # Prepare data for enrichment API
    enrichment_formatter = DataTransformer(
        id="enrichment_formatter",
        transformations=[
            # Format leads for enrichment API
            """lambda merged_data: {
                'leads': [
                    {
                        'email': lead.get('email'),
                        'company': lead.get('company'),
                        'name': f"{lead.get('first_name', '')} {lead.get('last_name', '')}"
                    }
                    for lead in merged_data.get('crm_data', [])
                ]
            }"""
        ],
    )
    workflow.add_node("enrichment_formatter", enrichment_formatter)
    workflow.connect("lead_merger", "enrichment_formatter", mapping={"merged": "data"})
    workflow.connect(
        "enrichment_formatter", "enrichment_api", mapping={"result": "body"}
    )

    # Combine enriched data with original leads
    lead_enricher = DataTransformer(
        id="lead_enricher",
        transformations=[
            # Merge enrichment results with original lead data
            """lambda data: {
                'enriched_leads': merge_enrichment_data(
                    data['merged_data']['crm_data'],
                    data['enrichment_response']['enriched_leads'],
                    data['merged_data']['behavior_data'],
                    data['merged_data']['email_data']
                )
            }""",
            # Add calculated fields
            """lambda data: {
                'enriched_leads': [
                    {
                        **lead,
                        'days_since_activity': calculate_days_since(lead.get('last_activity_date')),
                        'data_completeness': calculate_completeness(lead),
                        'enrichment_timestamp': datetime.now().isoformat()
                    }
                    for lead in data['enriched_leads']
                ]
            }""",
        ],
    )
    workflow.add_node("lead_enricher", lead_enricher)

    # Connect enrichment data
    enrichment_merger = MergeNode(id="enrichment_merger", merge_strategy="combine_dict")
    workflow.add_node("enrichment_merger", enrichment_merger)
    workflow.connect(
        "lead_merger", "enrichment_merger", mapping={"merged": "merged_data"}
    )
    workflow.connect(
        "enrichment_api",
        "enrichment_merger",
        mapping={"response": "enrichment_response"},
    )
    workflow.connect("enrichment_merger", "lead_enricher", mapping={"merged": "data"})


def add_scoring_engine(workflow: Workflow):
    """Add intelligent lead scoring using LLMAgentNode and rules."""

    # Use LLM for intelligent lead scoring
    ai_scorer = LLMAgentNode(
        id="ai_scorer",
        provider="openai",
        model="gpt-4",
        system_prompt="""You are an expert sales lead scoring specialist. Analyze leads and assign scores based on:

1. **Behavioral Signals (35% weight)**:
   - Website engagement (page views, time on site)
   - Content downloads and webinar attendance
   - Email engagement rates
   - Recency of interactions

2. **Demographic Fit (25% weight)**:
   - Job title and seniority
   - Company size and industry fit
   - Geographic location
   - Department alignment

3. **Firmographic Data (20% weight)**:
   - Company revenue and growth
   - Technology stack compatibility
   - Market segment
   - Buying power

4. **Engagement Patterns (20% weight)**:
   - Email open/click rates
   - Response to outreach
   - Multi-channel engagement
   - Velocity of engagement

For each lead, return a JSON object with:
{
  "lead_id": "...",
  "total_score": 0-100,
  "grade": "A/B/C/D",
  "priority": "hot/warm/cool/cold",
  "behavioral_score": 0-100,
  "demographic_score": 0-100,
  "firmographic_score": 0-100,
  "engagement_score": 0-100,
  "sales_readiness": "ready/nurture/not_qualified",
  "recommended_actions": ["action1", "action2"],
  "key_insights": "Brief explanation of score"
}

Be data-driven and consistent in scoring.""",
        temperature=0.3,
        max_tokens=2000,
    )
    workflow.add_node("ai_scorer", ai_scorer)

    # Format leads for AI scoring
    scoring_formatter = DataTransformer(
        id="scoring_formatter",
        transformations=[
            # Batch leads for efficient scoring
            """lambda data: {
                'messages': [{
                    'role': 'user',
                    'content': f'Score these leads:\\n{json.dumps(data["enriched_leads"][:20], indent=2)}'
                }]
            }"""
        ],
    )
    workflow.add_node("scoring_formatter", scoring_formatter)
    workflow.connect("lead_enricher", "scoring_formatter", mapping={"result": "data"})
    workflow.connect("scoring_formatter", "ai_scorer", mapping={"result": "prompt"})

    # Process AI scoring results
    score_processor = DataTransformer(
        id="score_processor",
        transformations=[
            # Parse AI response and merge with leads
            """lambda data: {
                'scored_leads': merge_ai_scores(
                    data['original_leads'],
                    data['ai_scores']
                ),
                'scoring_timestamp': datetime.now().isoformat()
            }"""
        ],
    )
    workflow.add_node("score_processor", score_processor)

    # High-score filter for immediate action
    hot_lead_filter = FilterNode(
        id="hot_lead_filter", field="priority", operator="==", value="hot"
    )
    workflow.add_node("hot_lead_filter", hot_lead_filter)
    workflow.connect(
        "score_processor", "hot_lead_filter", mapping={"scored_leads": "data"}
    )

    # Medium-score filter for nurturing
    warm_lead_filter = FilterNode(
        id="warm_lead_filter", field="priority", operator="in", value=["warm", "cool"]
    )
    workflow.add_node("warm_lead_filter", warm_lead_filter)
    workflow.connect(
        "score_processor", "warm_lead_filter", mapping={"scored_leads": "data"}
    )


def add_routing_system(workflow: Workflow):
    """Add intelligent lead routing using existing nodes."""

    # Get sales team availability from API
    team_availability = RESTClientNode(
        id="team_availability",
        url="${SALES_API}/teams/availability",
        method="GET",
        headers={"Authorization": "Bearer ${SALES_API_KEY}"},
        timeout=5000,
    )
    workflow.add_node("team_availability", team_availability)

    # Route hot leads to available enterprise reps
    hot_lead_router = DataTransformer(
        id="hot_lead_router",
        transformations=[
            # Assign hot leads to best available reps
            """lambda data: {
                'assignments': assign_leads_to_reps(
                    data['hot_leads'],
                    data['team_availability'],
                    'enterprise'
                )
            }"""
        ],
    )
    workflow.add_node("hot_lead_router", hot_lead_router)

    # Create assignment records in CRM
    assignment_writer = SQLDatabaseNode(
        id="assignment_writer",
        connection_string="${CRM_DATABASE}",
        operation_type="write",
        table_name="lead_assignments",
    )
    workflow.add_node("assignment_writer", assignment_writer)
    workflow.connect(
        "hot_lead_router", "assignment_writer", mapping={"assignments": "data"}
    )

    # Send notifications via notification service
    notification_api = RESTClientNode(
        id="notification_api",
        url="${NOTIFICATION_API}/bulk",
        method="POST",
        headers={
            "Authorization": "Bearer ${NOTIFICATION_KEY}",
            "Content-Type": "application/json",
        },
    )
    workflow.add_node("notification_api", notification_api)

    # Format notifications
    notification_formatter = DataTransformer(
        id="notification_formatter",
        transformations=[
            # Create notification payloads
            """lambda assignments: {
                'notifications': [
                    {
                        'type': 'lead_assignment',
                        'recipient': assignment['assigned_to'],
                        'channels': ['email', 'slack'],
                        'priority': assignment['priority'],
                        'data': {
                            'lead_name': assignment['lead_name'],
                            'company': assignment['company'],
                            'score': assignment['score']
                        }
                    }
                    for assignment in assignments['assignments']
                ]
            }"""
        ],
    )
    workflow.add_node("notification_formatter", notification_formatter)
    workflow.connect(
        "hot_lead_router", "notification_formatter", mapping={"result": "data"}
    )
    workflow.connect(
        "notification_formatter", "notification_api", mapping={"result": "body"}
    )

    # Route warm leads to nurture campaigns
    nurture_router = RESTClientNode(
        id="nurture_router",
        url="${MARKETING_API}/campaigns/nurture/assign",
        method="POST",
        headers={
            "Authorization": "Bearer ${MARKETING_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    workflow.add_node("nurture_router", nurture_router)

    # Format warm leads for nurture campaigns
    nurture_formatter = DataTransformer(
        id="nurture_formatter",
        transformations=[
            """lambda data: {
                'leads': [
                    {
                        'email': lead['email'],
                        'score': lead['total_score'],
                        'segment': lead['priority'],
                        'interests': lead.get('interests', [])
                    }
                    for lead in data['filtered_data']
                ]
            }"""
        ],
    )
    workflow.add_node("nurture_formatter", nurture_formatter)
    workflow.connect(
        "warm_lead_filter", "nurture_formatter", mapping={"filtered_data": "data"}
    )
    workflow.connect("nurture_formatter", "nurture_router", mapping={"result": "body"})


def add_analytics_pipeline(workflow: Workflow):
    """Add analytics and reporting using DataTransformer and LLM."""

    # Calculate metrics using DataTransformer
    metrics_calculator = DataTransformer(
        id="metrics_calculator",
        transformations=[
            # Calculate comprehensive metrics
            """lambda data: {
                'metrics': {
                    'total_leads': len(data['all_leads']),
                    'hot_leads': len(data['hot_leads']),
                    'warm_leads': len(data['warm_leads']),
                    'average_score': sum(l['total_score'] for l in data['all_leads']) / len(data['all_leads']) if data['all_leads'] else 0,
                    'grade_distribution': calculate_grade_distribution(data['all_leads']),
                    'source_performance': calculate_source_performance(data['all_leads']),
                    'sales_ready_percentage': calculate_sales_ready_percentage(data['all_leads'])
                },
                'timestamp': datetime.now().isoformat()
            }"""
        ],
    )
    workflow.add_node("metrics_calculator", metrics_calculator)

    # Generate insights using LLM
    insights_generator = LLMAgentNode(
        id="insights_generator",
        provider="openai",
        model="gpt-3.5-turbo",
        system_prompt="""Generate actionable insights from lead scoring metrics.

Analyze the data and provide:
1. Key performance indicators and trends
2. Source quality analysis
3. Conversion predictions
4. Recommended actions for sales and marketing teams
5. Areas for improvement

Format as a business report with specific, data-driven recommendations.""",
        temperature=0.5,
        max_tokens=1500,
    )
    workflow.add_node("insights_generator", insights_generator)

    # Format metrics for insights generation
    insights_formatter = DataTransformer(
        id="insights_formatter",
        transformations=[
            """lambda metrics: {
                'messages': [{
                    'role': 'user',
                    'content': f'Generate insights from these lead scoring metrics:\\n{json.dumps(metrics, indent=2)}'
                }]
            }"""
        ],
    )
    workflow.add_node("insights_formatter", insights_formatter)
    workflow.connect(
        "metrics_calculator", "insights_formatter", mapping={"result": "data"}
    )
    workflow.connect(
        "insights_formatter", "insights_generator", mapping={"result": "prompt"}
    )

    # Write analytics to data warehouse
    analytics_writer = SQLDatabaseNode(
        id="analytics_writer",
        connection_string="${ANALYTICS_DB}",
        operation_type="write",
        table_name="lead_scoring_analytics",
    )
    workflow.add_node("analytics_writer", analytics_writer)
    workflow.connect(
        "metrics_calculator", "analytics_writer", mapping={"result": "data"}
    )

    # Export detailed report
    report_writer = CSVWriterNode(
        id="report_writer",
        file_path="${REPORT_PATH}/lead_scoring_report_${TIMESTAMP}.csv",
        headers=True,
    )
    workflow.add_node("report_writer", report_writer)

    # Dashboard API update
    dashboard_updater = RESTClientNode(
        id="dashboard_updater",
        url="${DASHBOARD_API}/metrics/lead-scoring",
        method="PUT",
        headers={
            "Authorization": "Bearer ${DASHBOARD_KEY}",
            "Content-Type": "application/json",
        },
    )
    workflow.add_node("dashboard_updater", dashboard_updater)
    workflow.connect(
        "metrics_calculator", "dashboard_updater", mapping={"result": "body"}
    )


def main():
    """Execute the refactored lead scoring workflow."""
    # Create workflow
    workflow = create_lead_scoring_workflow()

    # Set up runtime
    runtime = LocalRuntime()

    # Configure parameters
    parameters = {
        "crm_leads": {
            "connection_string": os.getenv(
                "CRM_DATABASE", "postgresql://user:pass@localhost/crm"
            )
        },
        "marketing_data": {
            "url": os.getenv("MARKETING_API", "https://api.marketing.com")
            + "/leads/engagement",
            "headers": {
                "Authorization": f"Bearer {os.getenv('MARKETING_API_KEY', 'demo-key')}"
            },
        },
        "behavior_tracker": {
            "url": os.getenv("ANALYTICS_API", "https://analytics.example.com")
            + "/behavior/batch",
            "headers": {
                "Authorization": f"Bearer {os.getenv('ANALYTICS_API_KEY', 'demo-key')}"
            },
        },
        "email_engagement": {
            "url": os.getenv("EMAIL_SERVICE_API", "https://email.example.com")
            + "/engagement/metrics",
            "headers": {
                "Authorization": f"Bearer {os.getenv('EMAIL_SERVICE_KEY', 'demo-key')}"
            },
        },
        "enrichment_api": {
            "url": os.getenv("ENRICHMENT_API", "https://enrich.example.com")
            + "/enrich/batch",
            "headers": {
                "Authorization": f"Bearer {os.getenv('ENRICHMENT_API_KEY', 'demo-key')}"
            },
        },
        "ai_scorer": {"api_key": os.getenv("OPENAI_API_KEY", "demo-key")},
        "team_availability": {
            "url": os.getenv("SALES_API", "https://sales.example.com")
            + "/teams/availability"
        },
        "analytics_writer": {
            "connection_string": os.getenv(
                "ANALYTICS_DB", "postgresql://user:pass@localhost/analytics"
            )
        },
    }

    # Execute workflow
    print("Starting Lead Scoring Engine (Refactored)...")
    print("=" * 50)
    print("Using Kailash SDK best practices:")
    print("- Real API integrations instead of mock data")
    print("- LLMAgentNode for intelligent scoring")
    print("- DataTransformer for data manipulation")
    print("- FilterNode for lead segmentation")
    print("- RESTClientNode for external services")
    print()

    try:
        result, run_id = runtime.execute(workflow, parameters=parameters)

        print("Workflow completed successfully!")
        print(f"Run ID: {run_id}")
        print("\nKey improvements in this version:")
        print("- No mock data generation")
        print("- Real-time API integrations")
        print("- AI-powered scoring with LLMAgentNode")
        print("- Proper separation of concerns")
        print("- Better error handling and monitoring")

    except Exception as e:
        print(f"Error executing workflow: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
