#!/usr/bin/env python3
"""
Enterprise Threat Detection Example

Demonstrates the ThreatDetectionNode with AI-powered analysis using Ollama.
This example shows real-time threat detection, pattern analysis, and automated response.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Dict, List

from kailash.nodes.code import PythonCodeNode
from kailash.nodes.security.threat_detection import ThreatDetectionNode

from examples.utils.paths import get_output_data_path


async def create_realistic_security_events() -> List[Dict[str, Any]]:
    """Create realistic security events for testing."""

    # Brute force attack pattern
    brute_force_events = []
    for i in range(8):
        brute_force_events.append(
            {
                "type": "login",
                "user": "admin",
                "ip": "192.168.1.100",
                "failed": True,
                "timestamp": datetime.now(UTC).isoformat(),
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "location": "Unknown",
            }
        )

    # Privilege escalation attempts
    privilege_events = [
        {
            "type": "command",
            "user": "user123",
            "command": "sudo su -",
            "unauthorized": True,
            "ip": "192.168.1.101",
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "type": "access",
            "user": "user123",
            "resource": "admin_panel",
            "unauthorized": True,
            "ip": "192.168.1.101",
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]

    # Data exfiltration indicators
    exfiltration_events = [
        {
            "type": "data_transfer",
            "user": "employee456",
            "size_bytes": 500 * 1024 * 1024,  # 500MB
            "destination": "external_server",
            "timestamp": datetime.now(UTC).isoformat(),
            "unusual_hours": True,
        },
        {
            "type": "data_access",
            "user": "employee456",
            "data_type": "customer_database",
            "records_accessed": 10000,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]

    # Insider threat patterns
    insider_events = [
        {
            "type": "access",
            "user": "contractor789",
            "resource": "financial_reports",
            "unusual": True,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "type": "access",
            "user": "contractor789",
            "resource": "employee_records",
            "unusual": True,
            "timestamp": datetime.now(UTC).isoformat(),
        },
        {
            "type": "access",
            "user": "contractor789",
            "resource": "strategic_plans",
            "unusual": True,
            "timestamp": datetime.now(UTC).isoformat(),
        },
    ]

    # Anomalous behavior
    anomaly_events = [
        {
            "type": "login",
            "user": "manager456",
            "ip": "10.0.0.200",  # Different IP range
            "timestamp": datetime.now(UTC).isoformat(),
            "location": "Foreign Country",
            "anomalous": True,
        }
    ]

    all_events = (
        brute_force_events
        + privilege_events
        + exfiltration_events
        + insider_events
        + anomaly_events
    )
    return all_events


async def setup_ollama():
    """Setup Ollama container for AI analysis."""
    print("🐳 Setting up Ollama for AI threat analysis...")

    setup_code = """
import subprocess
import time

def setup():
    try:
        # Check if container exists
        result = subprocess.execute(
            ["docker", "ps", "-a", "--filter", "name=ollama", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30
        )

        if "ollama" not in result.stdout:
            print("Starting new Ollama container...")
            subprocess.execute([
                "docker", "run", "-d",
                "--name", "ollama",
                "-p", "11434:11434",
                "-v", "ollama:/root/.ollama",
                "ollama/ollama"
            ], check=True, timeout=60)
            time.sleep(15)
        else:
            print("Starting existing container...")
            subprocess.execute(["docker", "start", "ollama"], check=True, timeout=30)
            time.sleep(5)

        # Pull model
        print("Pulling llama3.2:3b model...")
        subprocess.execute([
            "docker", "exec", "ollama",
            "ollama", "pull", "llama3.2:3b"
        ], check=True, timeout=300)

        return {"result": "Ollama ready"}
    except Exception as e:
        return {"result": f"Setup failed: {e}"}
    """

    setup_node = PythonCodeNode.from_function(
        name="ollama_setup",
        func=lambda: exec(setup_code) or {"result": "Setup completed"},
    )

    result = await setup_node.execute_async()
    return result


async def main():
    """Main threat detection demonstration."""
    print("🔍 Enterprise Threat Detection Demo")
    print("=" * 50)

    try:
        # Setup Ollama
        await setup_ollama()

        # Create threat detection node
        print("\n🛡️ Initializing ThreatDetectionNode...")
        threat_detector = ThreatDetectionNode(
            name="enterprise_threat_detector",
            detection_rules=[
                "brute_force",
                "privilege_escalation",
                "data_exfiltration",
                "insider_threat",
                "anomalous_behavior",
            ],
            ai_model="ollama:llama3.2:3b",
            response_actions=["alert", "log"],
            real_time=True,
            severity_threshold="medium",
        )

        # Generate realistic security events
        print("\n📊 Generating realistic security events...")
        security_events = await create_realistic_security_events()
        print(f"   Created {len(security_events)} security events")

        # Analyze threats
        print("\n🔍 Running AI-powered threat analysis...")
        analysis_result = await threat_detector.execute_async(
            events=security_events,
            time_window=3600,  # 1 hour window
            context={
                "environment": "production",
                "sensitivity_level": "high",
                "organization": "enterprise_corp",
                "compliance_requirements": ["sox", "gdpr"],
            },
        )

        # Display results
        print("\n📈 Threat Analysis Results:")
        print(f"   • Events processed: {len(security_events)}")
        print(f"   • Threats detected: {len(analysis_result['threats'])}")
        print(
            f"   • Processing time: {analysis_result.get('processing_time_ms', 0):.1f}ms"
        )

        analysis = analysis_result.get("analysis", {})
        print(f"   • Rule-based detections: {analysis.get('rule_based_detections', 0)}")
        print(f"   • AI detections: {analysis.get('ai_detections', 0)}")
        print(f"   • Correlation matches: {analysis.get('correlation_matches', 0)}")
        print(
            f"   • Response actions taken: {len(analysis.get('response_actions_taken', []))}"
        )

        # Show detailed threat information
        print("\n🚨 Detected Threats:")
        for i, threat in enumerate(analysis_result["threats"][:5]):  # Show first 5
            print(
                f"   {i+1}. {threat.get('type', 'unknown').replace('_', ' ').title()}"
            )
            print(f"      • Severity: {threat.get('severity', 'unknown')}")
            print(f"      • Confidence: {threat.get('confidence', 0):.2f}")
            print(f"      • Description: {threat.get('description', 'No description')}")
            if threat.get("indicators"):
                print(f"      • Indicators: {', '.join(threat['indicators'])}")
            print()

        # Get detection statistics
        stats = threat_detector.get_detection_stats()
        print("📊 Detection Statistics:")
        print(f"   • Total events processed: {stats['total_events_processed']}")
        print(f"   • Average detection time: {stats['avg_detection_time_ms']:.1f}ms")
        print(f"   • AI model: {stats['ai_model']}")
        print(f"   • Real-time enabled: {stats['real_time_enabled']}")
        print(f"   • Performance target: {stats['performance_target_ms']}ms")

        # Save detailed results
        output_file = get_output_data_path("threat_detection_results.json")
        with open(output_file, "w") as f:
            json.dump(
                {
                    "demo_completed_at": datetime.now(UTC).isoformat(),
                    "analysis_result": analysis_result,
                    "detection_stats": stats,
                    "events_analyzed": len(security_events),
                    "configuration": {
                        "detection_rules": threat_detector.detection_rules,
                        "ai_model": threat_detector.ai_model,
                        "response_actions": threat_detector.response_actions,
                        "real_time": threat_detector.real_time,
                    },
                },
                f,
                indent=2,
            )

        print(f"\n💾 Detailed results saved to: {output_file}")
        print("\n✅ Threat Detection Demo completed successfully!")

        return analysis_result

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    asyncio.execute(main())
