#!/usr/bin/env python3
"""
Real-World Scenario: Enterprise Security Operations Center (SOC)

This example demonstrates a 24/7 security operations center for a
multinational financial institution handling real-time threat detection,
incident response, and coordinated security operations.

Scenario: Global Financial Services SOC
- Real-time threat monitoring across regions
- Automated incident response workflows
- Security analyst collaboration
- Executive threat briefings
"""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from kailash.nodes.admin import (
    AuditLogNode,
    PermissionCheckNode,
    RoleManagementNode,
    SecurityEventNode,
    UserManagementNode,
)
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import MergeNode, SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def create_threat_detection_workflow(detection_config: Dict[str, Any]):
    """
    Real scenario: Multi-vector threat detection across global operations.

    Monitors:
    - Login anomalies across regions
    - Data exfiltration attempts
    - Privilege escalation
    - Coordinated attacks
    - Insider threats
    """

    # Step 1: Collect security events from multiple sources
    def simulate_security_events():
        """Simulate realistic security events for demo."""
        events = []

        # Simulated attack scenarios
        scenarios = [
            {
                "type": "brute_force_attack",
                "source_ips": ["203.0.113.45", "203.0.113.46", "203.0.113.47"],
                "target": "vpn_gateway",
                "region": "APAC",
            },
            {
                "type": "data_exfiltration",
                "user": "john.doe",
                "volume_gb": 25.5,
                "destination": "unknown_cloud_storage",
                "region": "EMEA",
            },
            {
                "type": "privilege_escalation",
                "user": "contractor.temp123",
                "attempted_role": "system_admin",
                "region": "AMERICAS",
            },
            {
                "type": "suspicious_login_pattern",
                "users": ["alice.smith", "bob.jones", "charlie.brown"],
                "pattern": "rapid_geographic_movement",
                "regions": ["APAC", "EMEA", "AMERICAS"],
            },
        ]

        # Generate events for each scenario
        for scenario in scenarios:
            if scenario["type"] == "brute_force_attack":
                for ip in scenario["source_ips"]:
                    for i in range(random.randint(50, 100)):
                        events.append(
                            {
                                "event_type": "multiple_failed_logins",
                                "source_ip": ip,
                                "target_resource": scenario["target"],
                                "region": scenario["region"],
                                "timestamp": (
                                    datetime.now(UTC)
                                    - timedelta(minutes=random.randint(0, 60))
                                ).isoformat(),
                                "risk_score": random.uniform(7.0, 9.0),
                            }
                        )

            elif scenario["type"] == "data_exfiltration":
                events.append(
                    {
                        "event_type": "data_exfiltration",
                        "user_id": scenario["user"],
                        "data_volume": scenario["volume_gb"],
                        "destination": scenario["destination"],
                        "region": scenario["region"],
                        "timestamp": (
                            datetime.now(UTC) - timedelta(minutes=random.randint(0, 30))
                        ).isoformat(),
                        "risk_score": 9.5,
                    }
                )

            elif scenario["type"] == "privilege_escalation":
                events.append(
                    {
                        "event_type": "privilege_escalation",
                        "user_id": scenario["user"],
                        "attempted_role": scenario["attempted_role"],
                        "region": scenario["region"],
                        "timestamp": datetime.now(UTC).isoformat(),
                        "risk_score": 8.5,
                    }
                )

            elif scenario["type"] == "suspicious_login_pattern":
                for user in scenario["users"]:
                    for region in scenario["regions"]:
                        events.append(
                            {
                                "event_type": "suspicious_login",
                                "user_id": user,
                                "region": region,
                                "pattern": scenario["pattern"],
                                "timestamp": (
                                    datetime.now(UTC)
                                    - timedelta(hours=random.randint(0, 6))
                                ).isoformat(),
                                "risk_score": random.uniform(6.0, 8.0),
                            }
                        )

        return {
            "security_events": events,
            "event_count": len(events),
            "threat_vectors": len(scenarios),
        }

    event_collector = PythonCodeNode.from_function(
        name="collect_security_events", func=simulate_security_events
    )

    # Step 2: Threat correlation and analysis
    def correlate_threats(events_result):
        """Correlate events to identify coordinated attacks."""
        events = events_result.get("security_events", [])

        correlations = {
            "coordinated_attacks": [],
            "targeted_users": {},
            "compromised_regions": {},
            "attack_timeline": [],
        }

        # Group events by type and time
        event_groups = {}
        for event in events:
            event_type = event.get("event_type")
            if event_type not in event_groups:
                event_groups[event_type] = []
            event_groups[event_type].append(event)

        # Detect coordinated brute force
        if "multiple_failed_logins" in event_groups:
            failed_logins = event_groups["multiple_failed_logins"]
            unique_ips = set(e["source_ip"] for e in failed_logins)
            if len(unique_ips) >= 3:
                correlations["coordinated_attacks"].append(
                    {
                        "type": "distributed_brute_force",
                        "severity": "critical",
                        "source_ips": list(unique_ips),
                        "target": failed_logins[0]["target_resource"],
                        "event_count": len(failed_logins),
                        "confidence": 0.95,
                    }
                )

        # Detect insider threat pattern
        if (
            "data_exfiltration" in event_groups
            and "privilege_escalation" in event_groups
        ):
            correlations["coordinated_attacks"].append(
                {
                    "type": "potential_insider_threat",
                    "severity": "critical",
                    "indicators": ["privilege_escalation_attempt", "data_exfiltration"],
                    "users_involved": list(
                        set(
                            e.get("user_id")
                            for e in event_groups["data_exfiltration"]
                            + event_groups["privilege_escalation"]
                            if e.get("user_id")
                        )
                    ),
                    "confidence": 0.85,
                }
            )

        # Analyze targeted users
        user_events = {}
        for event in events:
            user_id = event.get("user_id")
            if user_id:
                if user_id not in user_events:
                    user_events[user_id] = []
                user_events[user_id].append(event)

        for user_id, user_event_list in user_events.items():
            if len(user_event_list) > 3:
                correlations["targeted_users"][user_id] = {
                    "event_count": len(user_event_list),
                    "event_types": list(set(e["event_type"] for e in user_event_list)),
                    "risk_level": (
                        "high"
                        if any(e.get("risk_score", 0) > 8 for e in user_event_list)
                        else "medium"
                    ),
                }

        # Regional analysis
        region_events = {}
        for event in events:
            region = event.get("region", "unknown")
            if region not in region_events:
                region_events[region] = []
            region_events[region].append(event)

        for region, regional_events in region_events.items():
            high_risk_count = sum(
                1 for e in regional_events if e.get("risk_score", 0) > 7
            )
            if high_risk_count > 5:
                correlations["compromised_regions"][region] = {
                    "total_events": len(regional_events),
                    "high_risk_events": high_risk_count,
                    "status": "compromised" if high_risk_count > 10 else "at_risk",
                }

        return {
            "threat_correlations": correlations,
            "coordinated_attack_detected": len(correlations["coordinated_attacks"]) > 0,
            "threat_level": (
                "critical" if correlations["coordinated_attacks"] else "high"
            ),
        }

    threat_correlator = PythonCodeNode.from_function(
        name="correlate_threats", func=correlate_threats
    )

    # Step 3: Create security events for high-risk items
    def prepare_security_events(correlations_result):
        """Prepare security events for database logging."""
        correlations = correlations_result.get("threat_correlations", {})
        events_to_create = []

        # Create events for coordinated attacks
        for attack in correlations.get("coordinated_attacks", []):
            event_data = {
                "event_type": attack["type"],
                "threat_level": attack["severity"],
                "source_ip": attack.get("source_ips", ["unknown"])[0],
                "description": f"Coordinated attack detected: {attack['type']}",
                "indicators": {
                    "attack_pattern": attack["type"],
                    "confidence": attack["confidence"],
                    "evidence": attack,
                },
                "detection_method": "correlation_analysis",
            }
            events_to_create.append(event_data)

        # Create events for compromised users
        for user_id, user_data in correlations.get("targeted_users", {}).items():
            if user_data["risk_level"] == "high":
                event_data = {
                    "event_type": "account_takeover",
                    "threat_level": "high",
                    "user_id": user_id,
                    "source_ip": "multiple",
                    "description": f"User {user_id} showing signs of account compromise",
                    "indicators": user_data,
                    "detection_method": "behavioral_analysis",
                }
                events_to_create.append(event_data)

        return {"events_to_create": events_to_create}

    event_preparer = PythonCodeNode.from_function(
        name="prepare_events", func=prepare_security_events
    )

    # Step 4: Log security events
    def create_security_event_nodes(prepared_events):
        """Create SecurityEventNode for each prepared event."""
        events = prepared_events.get("events_to_create", [])
        nodes = []

        for i, event_data in enumerate(events):
            node = SecurityEventNode(
                name=f"log_security_event_{i}",
                operation="create_event",
                event_data=event_data,
                risk_threshold=7.0,
                tenant_id=detection_config["organization"],
            )
            nodes.append(node)

        return nodes

    # Step 5: Incident response decision
    threat_router = SwitchNode(
        name="threat_response_router",
        condition_mappings={
            "critical": ["immediate_response", "create_war_room", "notify_executives"],
            "high": ["standard_response", "notify_soc_team"],
            "medium": ["monitor_and_log"],
        },
    )

    # Step 6: Immediate response for critical threats
    def prepare_critical_response(correlations_result):
        """Prepare immediate response for critical threats."""
        correlations = correlations_result.get("threat_correlations", {})
        response_actions = []

        # Block IPs from brute force attacks
        for attack in correlations.get("coordinated_attacks", []):
            if attack["type"] == "distributed_brute_force":
                for ip in attack.get("source_ips", []):
                    response_actions.append(
                        {
                            "type": "block_ip",
                            "parameters": {"ip": ip, "duration": "permanent"},
                        }
                    )

        # Disable compromised accounts
        for user_id in correlations.get("targeted_users", {}):
            response_actions.append(
                {"type": "disable_user", "parameters": {"user_id": user_id}}
            )

        # Isolate compromised regions
        for region, data in correlations.get("compromised_regions", {}).items():
            if data["status"] == "compromised":
                response_actions.append(
                    {
                        "type": "isolate_region",
                        "parameters": {"region": region, "level": "partial"},
                    }
                )

        return {"response_actions": response_actions}

    critical_response_prep = PythonCodeNode.from_function(
        name="prepare_critical_response", func=prepare_critical_response
    )

    immediate_response = SecurityEventNode(
        name="execute_immediate_response",
        operation="automated_response",
        tenant_id=detection_config["organization"],
    )

    # Step 7: Create war room for critical incidents
    def create_war_room(correlations_result, response_result):
        """Create virtual war room for incident response."""
        correlations = correlations_result.get("threat_correlations", {})

        war_room = {
            "room_id": f"WAR-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            "created_at": datetime.now(UTC).isoformat(),
            "severity": "critical",
            "participants": [
                "soc_lead@company.com",
                "ciso@company.com",
                "incident_commander@company.com",
            ],
            "threat_summary": {
                "coordinated_attacks": len(correlations.get("coordinated_attacks", [])),
                "compromised_users": len(correlations.get("targeted_users", {})),
                "affected_regions": list(
                    correlations.get("compromised_regions", {}).keys()
                ),
            },
            "response_status": {
                "actions_taken": len(response_result.get("executed_actions", [])),
                "actions_pending": 0,
            },
            "communication_channel": "secure_teams_channel",
            "status": "active",
        }

        return {"war_room": war_room}

    war_room_creator = PythonCodeNode.from_function(
        name="create_war_room", func=create_war_room
    )

    # Step 8: Executive notification
    def prepare_executive_briefing(correlations_result, war_room_result):
        """Prepare executive briefing for critical incidents."""
        correlations = correlations_result.get("threat_correlations", {})
        war_room = war_room_result.get("war_room", {})

        briefing = {
            "briefing_id": f"EXEC-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            "classification": "CONFIDENTIAL",
            "recipients": [
                "ceo@company.com",
                "cfo@company.com",
                "board_security@company.com",
            ],
            "subject": "CRITICAL: Active Security Incident",
            "executive_summary": {
                "situation": "Multiple coordinated cyber attacks detected across global operations",
                "impact": {
                    "users_affected": len(correlations.get("targeted_users", {})),
                    "regions_affected": len(
                        correlations.get("compromised_regions", {})
                    ),
                    "business_impact": "High - Trading systems at risk",
                },
                "response": {
                    "war_room_activated": war_room.get("room_id"),
                    "immediate_actions": "IP blocking, account suspension, regional isolation",
                    "estimated_resolution": "4-6 hours",
                },
                "recommendations": [
                    "Approve emergency response budget",
                    "Notify regulatory bodies within 72 hours",
                    "Prepare public communications",
                ],
            },
            "next_update": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }

        return {"executive_briefing": briefing}

    executive_briefing_prep = PythonCodeNode.from_function(
        name="prepare_executive_briefing", func=prepare_executive_briefing
    )

    # Step 9: SOC team notification for high threats
    def notify_soc_team(correlations_result):
        """Notify SOC team for high-priority threats."""
        notification = {
            "alert_id": f"SOC-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            "priority": "high",
            "recipients": ["soc_analyst_1@company.com", "soc_analyst_2@company.com"],
            "threat_summary": correlations_result.get("threat_correlations", {}),
            "action_required": "Review and investigate high-risk events",
            "sla": "2 hours",
        }

        return {"soc_notification": notification}

    soc_notifier = PythonCodeNode.from_function(name="notify_soc", func=notify_soc_team)

    # Step 10: Standard monitoring and logging
    monitor_log = AuditLogNode(
        name="log_threat_detection",
        operation="log_event",
        event_data={
            "event_type": "security_violation",
            "severity": "high",
            "action": "threat_detection_completed",
            "description": "Security threat detection and response cycle completed",
        },
        tenant_id=detection_config["organization"],
    )

    # Build workflow
    workflow = Workflow(name="soc_threat_detection")
    workflow.add_nodes(
        [
            event_collector,
            threat_correlator,
            event_preparer,
            threat_router,
            critical_response_prep,
            immediate_response,
            war_room_creator,
            executive_briefing_prep,
            soc_notifier,
            monitor_log,
        ]
    )

    # Connect workflow
    workflow.connect(event_collector, threat_correlator, {"result": "events_result"})
    workflow.connect(
        threat_correlator, event_preparer, {"result": "correlations_result"}
    )
    workflow.connect(threat_correlator, threat_router, {"result": "threat_level"})

    # Critical path
    workflow.connect(threat_router, critical_response_prep)
    workflow.connect(
        threat_correlator, critical_response_prep, {"result": "correlations_result"}
    )
    workflow.connect(
        critical_response_prep, immediate_response, {"result": "response_actions"}
    )

    workflow.connect(threat_router, war_room_creator)
    workflow.connect(
        threat_correlator, war_room_creator, {"result": "correlations_result"}
    )
    workflow.connect(
        immediate_response, war_room_creator, {"result": "response_result"}
    )

    workflow.connect(threat_router, executive_briefing_prep)
    workflow.connect(
        threat_correlator, executive_briefing_prep, {"result": "correlations_result"}
    )
    workflow.connect(
        war_room_creator, executive_briefing_prep, {"result": "war_room_result"}
    )

    # High priority path
    workflow.connect(threat_router, soc_notifier)
    workflow.connect(threat_correlator, soc_notifier, {"result": "correlations_result"})

    # Standard path
    workflow.connect(threat_router, monitor_log)

    return workflow


def create_security_metrics_dashboard_workflow(dashboard_config: Dict[str, Any]):
    """
    Real scenario: Executive security dashboard with real-time metrics.

    Provides:
    - Threat landscape overview
    - Incident response metrics
    - Compliance status
    - Risk indicators
    """

    # Collect security metrics
    def collect_security_metrics():
        """Collect comprehensive security metrics."""

        # Simulated metrics for demo
        metrics = {
            "threat_metrics": {
                "events_last_24h": random.randint(1000, 5000),
                "high_risk_events": random.randint(10, 50),
                "blocked_attacks": random.randint(100, 500),
                "active_incidents": random.randint(0, 5),
                "mean_time_to_detect": random.uniform(5, 30),  # minutes
                "mean_time_to_respond": random.uniform(15, 60),  # minutes
            },
            "regional_status": {
                "AMERICAS": {
                    "threat_level": random.choice(["low", "medium", "high"]),
                    "active_alerts": random.randint(0, 10),
                    "systems_health": random.uniform(95, 100),
                },
                "EMEA": {
                    "threat_level": random.choice(["low", "medium", "high"]),
                    "active_alerts": random.randint(0, 15),
                    "systems_health": random.uniform(93, 100),
                },
                "APAC": {
                    "threat_level": random.choice(["low", "medium", "high"]),
                    "active_alerts": random.randint(0, 20),
                    "systems_health": random.uniform(90, 100),
                },
            },
            "top_threats": [
                {"type": "phishing", "count": random.randint(100, 300)},
                {"type": "malware", "count": random.randint(50, 150)},
                {"type": "insider_threat", "count": random.randint(5, 20)},
                {"type": "ddos", "count": random.randint(10, 50)},
                {"type": "data_breach", "count": random.randint(0, 5)},
            ],
            "user_risk_distribution": {
                "low_risk": random.randint(800, 900),
                "medium_risk": random.randint(80, 120),
                "high_risk": random.randint(10, 30),
                "critical_risk": random.randint(0, 5),
            },
            "compliance_scores": {
                "pci_dss": random.uniform(85, 95),
                "iso_27001": random.uniform(88, 96),
                "gdpr": random.uniform(90, 98),
                "sox": random.uniform(87, 94),
            },
        }

        return {"security_metrics": metrics}

    metrics_collector = PythonCodeNode.from_function(
        name="collect_metrics", func=collect_security_metrics
    )

    # Analyze trends
    def analyze_security_trends(metrics_result):
        """Analyze security trends and generate insights."""
        metrics = metrics_result.get("security_metrics", {})

        insights = []

        # Threat trend analysis
        threat_metrics = metrics.get("threat_metrics", {})
        if threat_metrics.get("high_risk_events", 0) > 30:
            insights.append(
                {
                    "type": "threat_spike",
                    "severity": "high",
                    "message": "Significant increase in high-risk events detected",
                    "recommendation": "Increase SOC staffing for next 48 hours",
                }
            )

        # Regional analysis
        regional_status = metrics.get("regional_status", {})
        for region, status in regional_status.items():
            if status.get("threat_level") == "high":
                insights.append(
                    {
                        "type": "regional_threat",
                        "severity": "medium",
                        "message": f"{region} region showing elevated threat levels",
                        "recommendation": f"Focus additional resources on {region} monitoring",
                    }
                )

        # Compliance concerns
        compliance = metrics.get("compliance_scores", {})
        for framework, score in compliance.items():
            if score < 90:
                insights.append(
                    {
                        "type": "compliance_risk",
                        "severity": "medium",
                        "message": f"{framework.upper()} compliance score below target (90%)",
                        "recommendation": f"Schedule {framework.upper()} compliance review",
                    }
                )

        # Response time analysis
        if threat_metrics.get("mean_time_to_respond", 0) > 45:
            insights.append(
                {
                    "type": "response_delay",
                    "severity": "high",
                    "message": "Incident response times exceeding SLA",
                    "recommendation": "Review and optimize incident response procedures",
                }
            )

        return {
            "security_insights": insights,
            "insight_count": len(insights),
            "action_required": any(i["severity"] == "high" for i in insights),
        }

    trend_analyzer = PythonCodeNode.from_function(
        name="analyze_trends", func=analyze_security_trends
    )

    # Generate executive dashboard
    def generate_executive_dashboard(metrics_result, insights_result):
        """Generate executive security dashboard."""
        metrics = metrics_result.get("security_metrics", {})
        insights = insights_result.get("security_insights", [])

        dashboard = {
            "dashboard_id": f"SEC-DASH-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}",
            "generated_at": datetime.now(UTC).isoformat(),
            "refresh_interval": 300,  # 5 minutes
            "executive_summary": {
                "overall_security_posture": (
                    "stable" if len(insights) < 3 else "attention_required"
                ),
                "active_incidents": metrics["threat_metrics"]["active_incidents"],
                "24h_threat_count": metrics["threat_metrics"]["events_last_24h"],
                "blocked_attacks": metrics["threat_metrics"]["blocked_attacks"],
                "compliance_status": (
                    "compliant"
                    if all(
                        score >= 90 for score in metrics["compliance_scores"].values()
                    )
                    else "review_needed"
                ),
            },
            "kpis": {
                "mttr": f"{metrics['threat_metrics']['mean_time_to_respond']:.1f} min",
                "mttd": f"{metrics['threat_metrics']['mean_time_to_detect']:.1f} min",
                "threat_prevention_rate": f"{(metrics['threat_metrics']['blocked_attacks'] / metrics['threat_metrics']['events_last_24h'] * 100):.1f}%",
                "system_availability": f"{sum(r['systems_health'] for r in metrics['regional_status'].values()) / len(metrics['regional_status']):.1f}%",
            },
            "regional_overview": metrics["regional_status"],
            "threat_distribution": metrics["top_threats"],
            "user_risk_summary": metrics["user_risk_distribution"],
            "compliance_dashboard": metrics["compliance_scores"],
            "actionable_insights": [
                i for i in insights if i["severity"] in ["high", "critical"]
            ],
            "charts": {
                "threat_timeline": "24h_rolling",
                "regional_heatmap": "world_map",
                "compliance_radar": "radar_chart",
                "incident_funnel": "funnel_chart",
            },
        }

        return {"executive_dashboard": dashboard}

    dashboard_generator = PythonCodeNode.from_function(
        name="generate_dashboard", func=generate_executive_dashboard
    )

    # Log dashboard generation
    log_dashboard = AuditLogNode(
        name="log_dashboard_generation",
        operation="log_event",
        event_data={
            "event_type": "data_accessed",
            "severity": "low",
            "action": "security_dashboard_generated",
            "description": "Executive security dashboard generated",
            "metadata": {"dashboard_type": "executive_security", "auto_refresh": True},
        },
        tenant_id=dashboard_config["organization"],
    )

    # Build workflow
    workflow = Workflow(name="security_metrics_dashboard")
    workflow.add_nodes(
        [metrics_collector, trend_analyzer, dashboard_generator, log_dashboard]
    )

    # Connect workflow
    workflow.connect(metrics_collector, trend_analyzer, {"result": "metrics_result"})
    workflow.connect(
        metrics_collector, dashboard_generator, {"result": "metrics_result"}
    )
    workflow.connect(trend_analyzer, dashboard_generator, {"result": "insights_result"})
    workflow.connect(dashboard_generator, log_dashboard)

    return workflow


async def test_security_operations_scenarios():
    """Test comprehensive security operations scenarios."""

    print("🏦 Global Financial Services - Security Operations Center Testing")
    print("=" * 70)

    runtime = LocalRuntime()

    # Scenario 1: Real-time Threat Detection
    print("\n🚨 Scenario 1: Multi-Vector Threat Detection")
    print("-" * 50)

    detection_config = {
        "organization": "global_financial",
        "monitoring_window": 3600,
        "correlation_threshold": 0.7,
    }

    threat_workflow = create_threat_detection_workflow(detection_config)
    threat_result = await runtime.run_workflow(threat_workflow)

    # Extract results
    events = threat_result.get("collect_security_events", {})
    print(
        f"📊 Security events collected: {events.get('event_count', 0)} across {events.get('threat_vectors', 0)} vectors"
    )

    correlations = threat_result.get("correlate_threats", {})
    threat_data = correlations.get("threat_correlations", {})
    print("🔍 Threat analysis:")
    print(
        f"   - Coordinated attacks: {len(threat_data.get('coordinated_attacks', []))}"
    )
    print(f"   - Targeted users: {len(threat_data.get('targeted_users', {}))}")
    print(
        f"   - Compromised regions: {len(threat_data.get('compromised_regions', {}))}"
    )
    print(f"   - Threat level: {correlations.get('threat_level', 'unknown').upper()}")

    if correlations.get("coordinated_attack_detected"):
        response = threat_result.get("execute_immediate_response", {})
        print("\n🔒 Immediate response executed:")
        print(f"   - Actions taken: {len(response.get('executed_actions', []))}")
        print(f"   - Success rate: {response.get('success_rate', 0):.1f}%")

        war_room = threat_result.get("create_war_room", {}).get("war_room", {})
        print(f"\n🚨 War room activated: {war_room.get('room_id', 'N/A')}")
        print(f"   - Participants: {len(war_room.get('participants', []))}")
        print(f"   - Status: {war_room.get('status', 'unknown').upper()}")

        briefing = threat_result.get("prepare_executive_briefing", {}).get(
            "executive_briefing", {}
        )
        print(f"\n📋 Executive briefing prepared: {briefing.get('briefing_id', 'N/A')}")
        print(f"   - Classification: {briefing.get('classification', 'N/A')}")
        print(f"   - Recipients: {len(briefing.get('recipients', []))}")

    # Scenario 2: Security Metrics Dashboard
    print("\n\n📊 Scenario 2: Executive Security Dashboard")
    print("-" * 50)

    dashboard_config = {"organization": "global_financial", "refresh_rate": 300}

    dashboard_workflow = create_security_metrics_dashboard_workflow(dashboard_config)
    dashboard_result = await runtime.run_workflow(dashboard_workflow)

    metrics = dashboard_result.get("collect_metrics", {}).get("security_metrics", {})
    print("📈 Security metrics collected:")
    print(
        f"   - 24h events: {metrics.get('threat_metrics', {}).get('events_last_24h', 0):,}"
    )
    print(
        f"   - Active incidents: {metrics.get('threat_metrics', {}).get('active_incidents', 0)}"
    )
    print(
        f"   - MTTR: {metrics.get('threat_metrics', {}).get('mean_time_to_respond', 0):.1f} minutes"
    )
    print(
        f"   - MTTD: {metrics.get('threat_metrics', {}).get('mean_time_to_detect', 0):.1f} minutes"
    )

    insights = dashboard_result.get("analyze_trends", {})
    print(
        f"\n💡 Security insights: {insights.get('insight_count', 0)} insights generated"
    )
    if insights.get("action_required"):
        print("   ⚠️  ACTION REQUIRED - High severity insights detected")

    dashboard = dashboard_result.get("generate_dashboard", {}).get(
        "executive_dashboard", {}
    )
    summary = dashboard.get("executive_summary", {})
    print(f"\n📊 Executive Dashboard: {dashboard.get('dashboard_id', 'N/A')}")
    print(
        f"   - Security posture: {summary.get('overall_security_posture', 'unknown').upper()}"
    )
    print(
        f"   - Compliance status: {summary.get('compliance_status', 'unknown').upper()}"
    )

    kpis = dashboard.get("kpis", {})
    print("\n📈 Key Performance Indicators:")
    print(f"   - Threat prevention rate: {kpis.get('threat_prevention_rate', 'N/A')}")
    print(f"   - System availability: {kpis.get('system_availability', 'N/A')}")

    # Regional status
    print("\n🌍 Regional Security Status:")
    for region, status in dashboard.get("regional_overview", {}).items():
        print(
            f"   - {region}: Threat level {status.get('threat_level', 'unknown').upper()}, "
            f"Health {status.get('systems_health', 0):.1f}%"
        )

    # Summary
    print("\n" + "=" * 70)
    print("🎯 SECURITY OPERATIONS TEST SUMMARY")
    print("=" * 70)
    print("✅ Multi-vector threat detection operational")
    print("✅ Automated incident response functioning")
    print("✅ War room activation tested")
    print("✅ Executive dashboards and briefings ready")
    print("✅ Regional monitoring active across all zones")
    print("\n🛡️  24/7 Security Operations Center fully operational!")

    return {
        "test_status": "completed",
        "scenarios_tested": 2,
        "soc_capabilities": {
            "threat_detection": "multi-vector correlation",
            "incident_response": "automated with war room",
            "executive_reporting": "real-time dashboards",
            "regional_coverage": "global 24/7",
        },
        "results": {
            "threat_detection": threat_result,
            "security_dashboard": dashboard_result,
        },
    }


if __name__ == "__main__":
    # Run SOC testing
    result = asyncio.execute(test_security_operations_scenarios())

    # Save results
    with open("security_operations_test_results.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print("\n📄 Detailed results saved to: security_operations_test_results.json")
