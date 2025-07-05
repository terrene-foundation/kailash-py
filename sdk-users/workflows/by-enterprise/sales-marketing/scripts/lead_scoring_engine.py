#!/usr/bin/env python3
"""
Lead Scoring Engine - Enterprise Sales Workflow
===============================================

AI-powered lead scoring and qualification system that automatically
prioritizes leads based on behavior, demographics, and engagement.

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
from kailash.nodes.api import RestClientNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import SQLDatabaseNode
from kailash.nodes.logic import MergeNode
from kailash.runtime.local import LocalRuntime


def create_lead_scoring_workflow() -> Workflow:
    """Create enterprise lead scoring and routing workflow."""
    workflow = Workflow(
        workflow_id="lead_scoring_001",
        name="enterprise_lead_scoring",
        description="AI-powered lead scoring and qualification system",
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
    """Add multiple lead data sources."""

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

    # Marketing automation data
    marketing_data = RestClientNode(
        id="marketing_data",
        url="${MARKETING_API}/leads/engagement",
        method="GET",
        headers={"Authorization": "Bearer ${MARKETING_API_KEY}"},
    )
    workflow.add_node("marketing_data", marketing_data)

    # Website behavior data
    behavior_tracker = PythonCodeNode(
        name="behavior_tracker",
        code="""
import random
from datetime import datetime, timedelta

# Simulate website behavior data
# In production, this would come from analytics API
behavior_data = []

# Get lead emails from CRM data
lead_emails = [lead.get('email') for lead in crm_data.get('data', [])]

for email in lead_emails[:100]:  # Limit for demo
    # Generate behavior metrics
    sessions = random.randint(1, 20)
    page_views = sessions * random.randint(3, 15)

    behaviors = {
        'email': email,
        'total_sessions': sessions,
        'total_page_views': page_views,
        'avg_session_duration': random.uniform(30, 600),  # seconds
        'pages_visited': {
            'pricing': random.random() > 0.5,
            'features': random.random() > 0.3,
            'case_studies': random.random() > 0.6,
            'contact': random.random() > 0.7,
            'demo_request': random.random() > 0.8
        },
        'content_downloads': random.randint(0, 5),
        'webinar_attendance': random.randint(0, 3),
        'last_visit': (datetime.now() - timedelta(days=random.randint(0, 30))).isoformat(),
        'device_types': ['desktop', 'mobile'] if random.random() > 0.5 else ['desktop'],
        'referral_source': random.choice(['organic', 'paid_search', 'social', 'email', 'direct'])
    }

    behavior_data.append(behaviors)

result = {
    'behavior_metrics': behavior_data,
    'tracking_period': '30_days',
    'data_quality': 'high'
}
""",
    )
    workflow.add_node("behavior_tracker", behavior_tracker)
    workflow.connect("crm_leads", "behavior_tracker", mapping={"data": "crm_data"})

    # Email engagement data
    email_engagement = PythonCodeNode(
        name="email_engagement",
        code="""
# Simulate email engagement data
engagement_data = []

for email in lead_emails[:100]:
    engagement = {
        'email': email,
        'emails_sent': random.randint(5, 50),
        'emails_opened': random.randint(0, 30),
        'emails_clicked': random.randint(0, 15),
        'open_rate': random.uniform(0, 0.6),
        'click_rate': random.uniform(0, 0.3),
        'last_open_date': (datetime.now() - timedelta(days=random.randint(0, 60))).isoformat(),
        'last_click_date': (datetime.now() - timedelta(days=random.randint(0, 90))).isoformat(),
        'unsubscribed': random.random() > 0.95,
        'email_preferences': {
            'frequency': random.choice(['daily', 'weekly', 'monthly']),
            'topics': random.sample(['product_updates', 'industry_news', 'tips', 'webinars'],
                                  k=random.randint(1, 4))
        }
    }
    engagement_data.append(engagement)

result = {'email_metrics': engagement_data}
""",
    )
    workflow.add_node("email_engagement", email_engagement)

    # Merge all lead data
    lead_merger = MergeNode(id="lead_merger", merge_strategy="combine_dict")
    workflow.add_node("lead_merger", lead_merger)

    workflow.connect("crm_leads", "lead_merger", mapping={"data": "crm_data"})
    workflow.connect(
        "marketing_data", "lead_merger", mapping={"response": "marketing_data"}
    )
    workflow.connect(
        "behavior_tracker", "lead_merger", mapping={"result": "behavior_data"}
    )
    workflow.connect(
        "email_engagement", "lead_merger", mapping={"result": "email_data"}
    )


def add_enrichment_pipeline(workflow: Workflow):
    """Add lead enrichment with external data."""

    lead_enricher = PythonCodeNode(
        name="lead_enricher",
        code='''
# Enrich leads with additional data
all_lead_data = merged_data
crm_leads = all_lead_data.get('crm_data', [])
behaviors = {b['email']: b for b in all_lead_data.get('behavior_data', {}).get('behavior_metrics', [])}
email_metrics = {e['email']: e for e in all_lead_data.get('email_data', {}).get('email_metrics', [])}

enriched_leads = []

for lead in crm_leads:
    email = lead.get('email', '')

    # Create enriched lead record
    enriched_lead = lead.copy()

    # Add behavioral data
    if email in behaviors:
        enriched_lead['behavior'] = behaviors[email]
    else:
        enriched_lead['behavior'] = {
            'total_sessions': 0,
            'total_page_views': 0,
            'engagement_level': 'none'
        }

    # Add email engagement
    if email in email_metrics:
        enriched_lead['email_engagement'] = email_metrics[email]
    else:
        enriched_lead['email_engagement'] = {
            'open_rate': 0,
            'click_rate': 0,
            'engagement_level': 'none'
        }

    # Add firmographic enrichment (simulated)
    if enriched_lead.get('company'):
        enriched_lead['firmographics'] = {
            'industry': enriched_lead.get('industry', 'Unknown'),
            'company_size': enriched_lead.get('company_size', 'Unknown'),
            'annual_revenue': enriched_lead.get('annual_revenue', 0),
            'technology_stack': simulate_tech_stack(),
            'growth_stage': random.choice(['startup', 'growth', 'enterprise']),
            'market_segment': random.choice(['smb', 'mid_market', 'enterprise'])
        }

    # Calculate days since last activity
    last_activity = enriched_lead.get('last_activity_date')
    if last_activity:
        last_activity_date = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
        days_inactive = (datetime.now() - last_activity_date).days
        enriched_lead['days_since_activity'] = days_inactive
    else:
        enriched_lead['days_since_activity'] = 999

    # Add enrichment metadata
    enriched_lead['enrichment_timestamp'] = datetime.now().isoformat()
    enriched_lead['data_completeness'] = calculate_completeness(enriched_lead)

    enriched_leads.append(enriched_lead)

def simulate_tech_stack():
    """Simulate technology stack detection."""
    possible_tech = ['Salesforce', 'HubSpot', 'AWS', 'Azure', 'Slack', 'Office365', 'Google Workspace']
    return random.sample(possible_tech, k=random.randint(2, 5))

def calculate_completeness(lead):
    """Calculate data completeness score."""
    required_fields = ['email', 'first_name', 'last_name', 'company', 'job_title', 'phone']
    filled_fields = sum(1 for field in required_fields if lead.get(field))
    return filled_fields / len(required_fields)

result = {
    'enriched_leads': enriched_leads,
    'enrichment_summary': {
        'total_enriched': len(enriched_leads),
        'avg_completeness': sum(l['data_completeness'] for l in enriched_leads) / len(enriched_leads) if enriched_leads else 0
    }
}
''',
    )
    workflow.add_node("lead_enricher", lead_enricher)
    workflow.connect("lead_merger", "lead_enricher", mapping={"merged": "merged_data"})


def add_scoring_engine(workflow: Workflow):
    """Add multi-dimensional lead scoring engine."""

    scoring_engine = PythonCodeNode(
        name="scoring_engine",
        code="""
import numpy as np
from datetime import datetime

# Multi-dimensional lead scoring
enriched_leads = enrichment_data.get('enriched_leads', [])
scored_leads = []

# Scoring weights (configurable)
weights = {
    'behavioral': 0.35,
    'demographic': 0.25,
    'firmographic': 0.20,
    'engagement': 0.20
}

for lead in enriched_leads:
    # Initialize scores
    behavioral_score = 0
    demographic_score = 0
    firmographic_score = 0
    engagement_score = 0

    # 1. Behavioral Scoring
    behavior = lead.get('behavior', {})

    # Page visits scoring
    if behavior.get('pages_visited', {}).get('pricing'):
        behavioral_score += 20
    if behavior.get('pages_visited', {}).get('demo_request'):
        behavioral_score += 30
    if behavior.get('pages_visited', {}).get('case_studies'):
        behavioral_score += 15

    # Session engagement
    sessions = behavior.get('total_sessions', 0)
    if sessions > 10:
        behavioral_score += 25
    elif sessions > 5:
        behavioral_score += 15
    elif sessions > 2:
        behavioral_score += 10

    # Content engagement
    downloads = behavior.get('content_downloads', 0)
    behavioral_score += min(downloads * 5, 20)

    # Webinar attendance
    webinars = behavior.get('webinar_attendance', 0)
    behavioral_score += min(webinars * 10, 30)

    # 2. Demographic Scoring
    job_title = lead.get('job_title', '').lower()

    # Decision maker titles
    if any(title in job_title for title in ['ceo', 'cto', 'vp', 'director', 'head of']):
        demographic_score += 40
    elif any(title in job_title for title in ['manager', 'lead', 'senior']):
        demographic_score += 25
    else:
        demographic_score += 10

    # Lead source quality
    source_scores = {
        'website': 20,
        'webinar': 30,
        'referral': 35,
        'event': 25,
        'content': 20,
        'paid': 15,
        'other': 10
    }
    lead_source = lead.get('lead_source', 'other').lower()
    demographic_score += source_scores.get(lead_source, 10)

    # 3. Firmographic Scoring
    firmographics = lead.get('firmographics', {})

    # Company size scoring
    company_size = firmographics.get('company_size', 'Unknown')
    size_scores = {
        'enterprise': 40,
        '1000+': 35,
        '100-1000': 30,
        '10-100': 20,
        '1-10': 10,
        'Unknown': 5
    }
    firmographic_score += size_scores.get(company_size, 5)

    # Industry fit (customize based on ICP)
    target_industries = ['technology', 'finance', 'healthcare', 'retail']
    industry = firmographics.get('industry', '').lower()
    if any(target in industry for target in target_industries):
        firmographic_score += 30
    else:
        firmographic_score += 10

    # Growth stage
    growth_scores = {
        'enterprise': 30,
        'growth': 35,
        'startup': 20
    }
    growth_stage = firmographics.get('growth_stage', 'unknown')
    firmographic_score += growth_scores.get(growth_stage, 10)

    # 4. Engagement Scoring
    email_eng = lead.get('email_engagement', {})

    # Email engagement rates
    open_rate = email_eng.get('open_rate', 0)
    click_rate = email_eng.get('click_rate', 0)

    if open_rate > 0.4:
        engagement_score += 30
    elif open_rate > 0.2:
        engagement_score += 20
    elif open_rate > 0.1:
        engagement_score += 10

    if click_rate > 0.2:
        engagement_score += 35
    elif click_rate > 0.1:
        engagement_score += 25
    elif click_rate > 0.05:
        engagement_score += 15

    # Recency scoring
    days_inactive = lead.get('days_since_activity', 999)
    if days_inactive <= 7:
        engagement_score += 35
    elif days_inactive <= 14:
        engagement_score += 25
    elif days_inactive <= 30:
        engagement_score += 15
    else:
        engagement_score += 0

    # Calculate weighted total score
    total_score = (
        behavioral_score * weights['behavioral'] +
        demographic_score * weights['demographic'] +
        firmographic_score * weights['firmographic'] +
        engagement_score * weights['engagement']
    )

    # Normalize to 0-100
    total_score = min(100, max(0, total_score))

    # Determine lead grade
    if total_score >= 80:
        grade = 'A'
        priority = 'hot'
    elif total_score >= 60:
        grade = 'B'
        priority = 'warm'
    elif total_score >= 40:
        grade = 'C'
        priority = 'cool'
    else:
        grade = 'D'
        priority = 'cold'

    # Add scoring to lead
    lead['lead_score'] = {
        'total_score': round(total_score, 2),
        'grade': grade,
        'priority': priority,
        'behavioral_score': round(behavioral_score, 2),
        'demographic_score': round(demographic_score, 2),
        'firmographic_score': round(firmographic_score, 2),
        'engagement_score': round(engagement_score, 2),
        'scoring_timestamp': datetime.now().isoformat(),
        'scoring_version': '2.1.0'
    }

    # Add sales readiness indicators
    lead['sales_indicators'] = {
        'ready_for_contact': total_score >= 60,
        'needs_nurturing': total_score >= 30 and total_score < 60,
        'not_qualified': total_score < 30,
        'fast_mover': days_inactive <= 7 and behavioral_score >= 50,
        'at_risk': days_inactive > 30 and total_score >= 40
    }

    scored_leads.append(lead)

# Calculate scoring statistics
score_distribution = {'A': 0, 'B': 0, 'C': 0, 'D': 0}
for lead in scored_leads:
    grade = lead['lead_score']['grade']
    score_distribution[grade] += 1

result = {
    'scored_leads': scored_leads,
    'scoring_summary': {
        'total_scored': len(scored_leads),
        'score_distribution': score_distribution,
        'avg_score': sum(l['lead_score']['total_score'] for l in scored_leads) / len(scored_leads) if scored_leads else 0,
        'hot_leads': sum(1 for l in scored_leads if l['lead_score']['priority'] == 'hot'),
        'sales_ready': sum(1 for l in scored_leads if l['sales_indicators']['ready_for_contact'])
    }
}
""",
    )
    workflow.add_node("scoring_engine", scoring_engine)
    workflow.connect(
        "lead_enricher", "scoring_engine", mapping={"result": "enrichment_data"}
    )


def add_routing_system(workflow: Workflow):
    """Add intelligent lead routing and assignment."""

    # Lead router
    lead_router = PythonCodeNode(
        name="lead_router",
        code="""
# Intelligent lead routing based on score and criteria
scored_leads = scoring_data.get('scored_leads', [])

# Define sales team structure (simulated)
sales_teams = {
    'enterprise': {
        'reps': ['john.smith', 'sarah.jones', 'mike.wilson'],
        'capacity': 50,
        'specialties': ['enterprise', 'technology', 'finance']
    },
    'mid_market': {
        'reps': ['alice.brown', 'bob.davis', 'carol.white'],
        'capacity': 75,
        'specialties': ['growth', 'retail', 'healthcare']
    },
    'smb': {
        'reps': ['david.lee', 'emma.taylor', 'frank.martin'],
        'capacity': 100,
        'specialties': ['startup', 'small_business']
    }
}

# Track assignments
assignments = []
routing_errors = []

# Current rep workload (simulated)
rep_workload = {rep: random.randint(10, 40) for team in sales_teams.values() for rep in team['reps']}

for lead in scored_leads:
    try:
        # Determine team based on lead characteristics
        firmographics = lead.get('firmographics', {})
        market_segment = firmographics.get('market_segment', 'smb')
        lead_score = lead.get('lead_score', {})
        priority = lead_score.get('priority', 'cold')

        # Route hot leads to best available rep
        if priority == 'hot':
            # Find rep with lowest workload in appropriate team
            if market_segment == 'enterprise':
                team = 'enterprise'
            elif market_segment == 'mid_market':
                team = 'mid_market'
            else:
                team = 'smb'

            # Get team reps sorted by workload
            team_reps = sales_teams[team]['reps']
            available_reps = [(rep, rep_workload[rep]) for rep in team_reps]
            available_reps.sort(key=lambda x: x[1])

            assigned_rep = available_reps[0][0]
            rep_workload[assigned_rep] += 1

        else:
            # Route based on round-robin or rules
            team = market_segment if market_segment in sales_teams else 'smb'
            team_reps = sales_teams[team]['reps']
            # Simple round-robin
            assigned_rep = team_reps[len(assignments) % len(team_reps)]

        # Create assignment
        assignment = {
            'lead_id': lead.get('lead_id'),
            'email': lead.get('email'),
            'assigned_to': assigned_rep,
            'assigned_team': team,
            'assignment_reason': f'{priority} lead - {market_segment} segment',
            'priority': priority,
            'score': lead_score.get('total_score', 0),
            'assigned_at': datetime.now().isoformat(),
            'sla_hours': 4 if priority == 'hot' else 24 if priority == 'warm' else 72,
            'routing_rules': [
                f'Score: {lead_score.get("total_score", 0)}',
                f'Segment: {market_segment}',
                f'Priority: {priority}'
            ]
        }

        assignments.append(assignment)

        # Add assignment to lead
        lead['assignment'] = assignment

    except Exception as e:
        routing_errors.append({
            'lead_id': lead.get('lead_id'),
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        })

# Generate routing summary
routing_summary = {
    'total_routed': len(assignments),
    'routing_errors': len(routing_errors),
    'assignments_by_team': {},
    'assignments_by_priority': {},
    'avg_score_by_team': {}
}

for assignment in assignments:
    team = assignment['assigned_team']
    priority = assignment['priority']

    routing_summary['assignments_by_team'][team] = routing_summary['assignments_by_team'].get(team, 0) + 1
    routing_summary['assignments_by_priority'][priority] = routing_summary['assignments_by_priority'].get(priority, 0) + 1

result = {
    'routed_leads': scored_leads,
    'assignments': assignments,
    'routing_errors': routing_errors,
    'routing_summary': routing_summary,
    'rep_workload': rep_workload
}
""",
    )
    workflow.add_node("lead_router", lead_router)
    workflow.connect(
        "scoring_engine", "lead_router", mapping={"result": "scoring_data"}
    )

    # Notification sender
    notification_sender = PythonCodeNode(
        name="notification_sender",
        code="""
# Send notifications to sales reps
routing_data = routing_result
assignments = routing_data.get('assignments', [])
notifications = []

# Group assignments by rep
assignments_by_rep = {}
for assignment in assignments:
    rep = assignment['assigned_to']
    if rep not in assignments_by_rep:
        assignments_by_rep[rep] = []
    assignments_by_rep[rep].append(assignment)

# Create notifications
for rep, rep_assignments in assignments_by_rep.items():
    # Hot leads notification
    hot_leads = [a for a in rep_assignments if a['priority'] == 'hot']
    if hot_leads:
        notifications.append({
            'type': 'urgent',
            'recipient': rep,
            'channel': 'email,slack',
            'subject': f'🔥 {len(hot_leads)} Hot Leads Assigned',
            'message': f'You have {len(hot_leads)} hot leads requiring immediate attention.',
            'leads': hot_leads,
            'sent_at': datetime.now().isoformat()
        })

    # Daily summary
    notifications.append({
        'type': 'summary',
        'recipient': rep,
        'channel': 'email',
        'subject': f'Daily Lead Assignment Summary',
        'message': f'You have been assigned {len(rep_assignments)} new leads today.',
        'breakdown': {
            'hot': len([a for a in rep_assignments if a['priority'] == 'hot']),
            'warm': len([a for a in rep_assignments if a['priority'] == 'warm']),
            'cool': len([a for a in rep_assignments if a['priority'] == 'cool']),
            'cold': len([a for a in rep_assignments if a['priority'] == 'cold'])
        },
        'sent_at': datetime.now().isoformat()
    })

result = {
    'notifications_sent': len(notifications),
    'notifications': notifications
}
""",
    )
    workflow.add_node("notification_sender", notification_sender)
    workflow.connect(
        "lead_router", "notification_sender", mapping={"result": "routing_result"}
    )


def add_analytics_pipeline(workflow: Workflow):
    """Add analytics and reporting for lead scoring performance."""

    analytics_processor = PythonCodeNode(
        name="analytics_processor",
        code="""
# Generate comprehensive analytics
routing_data = routing_result
scored_leads = routing_data.get('routed_leads', [])
assignments = routing_data.get('assignments', [])
scoring_summary = scoring_data.get('scoring_summary', {})

# Lead quality metrics
total_leads = len(scored_leads)
quality_metrics = {
    'total_leads': total_leads,
    'grade_distribution': scoring_summary.get('score_distribution', {}),
    'average_score': scoring_summary.get('avg_score', 0),
    'sales_ready_percentage': (scoring_summary.get('sales_ready', 0) / total_leads * 100) if total_leads > 0 else 0
}

# Engagement metrics
engagement_metrics = {
    'high_engagement': sum(1 for l in scored_leads if l.get('lead_score', {}).get('engagement_score', 0) > 60),
    'medium_engagement': sum(1 for l in scored_leads if 30 <= l.get('lead_score', {}).get('engagement_score', 0) <= 60),
    'low_engagement': sum(1 for l in scored_leads if l.get('lead_score', {}).get('engagement_score', 0) < 30)
}

# Source performance
source_performance = {}
for lead in scored_leads:
    source = lead.get('lead_source', 'unknown')
    score = lead.get('lead_score', {}).get('total_score', 0)

    if source not in source_performance:
        source_performance[source] = {
            'count': 0,
            'total_score': 0,
            'grades': {'A': 0, 'B': 0, 'C': 0, 'D': 0}
        }

    source_performance[source]['count'] += 1
    source_performance[source]['total_score'] += score
    grade = lead.get('lead_score', {}).get('grade', 'D')
    source_performance[source]['grades'][grade] += 1

# Calculate average scores by source
for source, data in source_performance.items():
    data['avg_score'] = data['total_score'] / data['count'] if data['count'] > 0 else 0

# Routing efficiency
routing_metrics = {
    'total_routed': len(assignments),
    'routing_success_rate': (len(assignments) / total_leads * 100) if total_leads > 0 else 0,
    'hot_leads_routed': sum(1 for a in assignments if a['priority'] == 'hot'),
    'avg_sla_hours': sum(a['sla_hours'] for a in assignments) / len(assignments) if assignments else 0
}

# Predictive metrics (simulated)
conversion_predictions = {
    'predicted_conversions': int(scoring_summary.get('hot_leads', 0) * 0.3 +
                                scoring_summary.get('sales_ready', 0) * 0.15),
    'predicted_revenue': scoring_summary.get('hot_leads', 0) * 50000 +
                        scoring_summary.get('sales_ready', 0) * 25000,
    'confidence_level': 0.75
}

# Create executive dashboard data
dashboard_data = {
    'timestamp': datetime.now().isoformat(),
    'lead_quality_metrics': quality_metrics,
    'engagement_metrics': engagement_metrics,
    'source_performance': source_performance,
    'routing_metrics': routing_metrics,
    'conversion_predictions': conversion_predictions,
    'key_insights': generate_insights(quality_metrics, engagement_metrics, source_performance)
}

def generate_insights(quality, engagement, sources):
    insights = []

    # Quality insights
    if quality['sales_ready_percentage'] > 30:
        insights.append({
            'type': 'positive',
            'message': f"{quality['sales_ready_percentage']:.1f}% of leads are sales-ready",
            'impact': 'high'
        })

    # Engagement insights
    high_eng_rate = engagement['high_engagement'] / quality['total_leads'] * 100 if quality['total_leads'] > 0 else 0
    if high_eng_rate > 25:
        insights.append({
            'type': 'positive',
            'message': f"{high_eng_rate:.1f}% of leads show high engagement",
            'impact': 'medium'
        })

    # Source insights
    best_source = max(sources.items(), key=lambda x: x[1]['avg_score'] if x[1]['count'] > 5 else 0)
    if best_source[1]['avg_score'] > 60:
        insights.append({
            'type': 'recommendation',
            'message': f"Increase investment in {best_source[0]} - highest quality leads",
            'impact': 'high'
        })

    return insights

result = {
    'analytics': dashboard_data,
    'export_ready': True,
    'report_format': 'executive_dashboard'
}
""",
    )
    workflow.add_node("analytics_processor", analytics_processor)
    workflow.connect(
        "lead_router", "analytics_processor", mapping={"result": "routing_result"}
    )
    workflow.connect(
        "scoring_engine", "analytics_processor", mapping={"result": "scoring_data"}
    )

    # Report writer
    report_writer = SQLDatabaseNode(
        id="report_writer",
        connection_string="${ANALYTICS_DB}",
        operation_type="write",
        table_name="lead_scoring_analytics",
        if_exists="append",
    )
    workflow.add_node("report_writer", report_writer)
    workflow.connect(
        "analytics_processor", "report_writer", mapping={"analytics": "data"}
    )


def main():
    """Execute the lead scoring workflow."""
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
        "report_writer": {
            "connection_string": os.getenv(
                "ANALYTICS_DB", "postgresql://user:pass@localhost/analytics"
            )
        },
    }

    # Execute workflow
    print("Starting Lead Scoring Engine...")
    print("=" * 50)

    try:
        result, run_id = runtime.execute(workflow, parameters=parameters)

        # Display results
        if result:
            analytics = result.get("analytics", {})
            quality_metrics = analytics.get("lead_quality_metrics", {})
            routing_metrics = analytics.get("routing_metrics", {})
            predictions = analytics.get("conversion_predictions", {})

            print("\nLead Quality Summary:")
            print("-" * 30)
            print(f"Total Leads Scored: {quality_metrics.get('total_leads', 0)}")
            print(f"Average Score: {quality_metrics.get('average_score', 0):.1f}")
            print(
                f"Sales Ready: {quality_metrics.get('sales_ready_percentage', 0):.1f}%"
            )

            print("\nGrade Distribution:")
            for grade, count in quality_metrics.get("grade_distribution", {}).items():
                print(f"  Grade {grade}: {count} leads")

            print("\nRouting Summary:")
            print(f"Total Routed: {routing_metrics.get('total_routed', 0)}")
            print(f"Hot Leads: {routing_metrics.get('hot_leads_routed', 0)}")

            print("\nPredictions:")
            print(
                f"Expected Conversions: {predictions.get('predicted_conversions', 0)}"
            )
            print(f"Predicted Revenue: ${predictions.get('predicted_revenue', 0):,.2f}")

            print("\nKey Insights:")
            for insight in analytics.get("key_insights", []):
                print(f"  [{insight['type'].upper()}] {insight['message']}")

            print("\nWorkflow completed successfully!")
            print(f"Run ID: {run_id}")

    except Exception as e:
        print(f"Error executing workflow: {str(e)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
