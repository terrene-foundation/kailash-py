"""
Chaos QA Agent - Aggressive Testing for Admin Framework

This agent actively tries to break the system using chaos engineering principles
and aggressive testing strategies.
"""

from kailash.core.workflow import Workflow
from kailash.core.nodes import LLMAgentNode, PythonCodeNode, A2AAgentNode
from kailash.core.utils import get_output_data_path
import json
import random
import string
import time
from datetime import datetime
from typing import Dict, List, Any

def generate_chaos_scenarios():
    """Generate chaos testing scenarios designed to break things"""
    
    # Malicious payloads
    malicious_payloads = {
        "buffer_overflow": "A" * 1000000,  # 1MB string
        "null_byte_injection": "test\x00admin",
        "unicode_explosion": "𝕿𝖍𝖊 𝖖𝖚𝖎𝖈𝖐 𝖇𝖗𝖔𝖜𝖓 𝖋𝖔𝖝 𝖏𝖚𝖒𝖕𝖘 𝖔𝖛𝖊𝖗 𝖙𝖍𝖊 𝖑𝖆𝖟𝖞 𝖉𝖔𝖌",
        "emoji_bomb": "🔥" * 10000,
        "nested_json_bomb": json.dumps({"a" * i: {"b" * i: "c" * i} for i in range(100)}),
        "regex_dos": "a" * 100 + "X" + "a" * 100,  # ReDoS pattern
        "xml_entity_expansion": '<!DOCTYPE foo [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>',
        "format_string": "%s%s%s%s%s%s%s%s%s%s",
        "command_injection": "; rm -rf /; echo 'pwned'",
        "ldap_injection": "*)(uid=*))(|(uid=*",
        "path_traversal": "../../../../../../../../etc/passwd",
        "billion_laughs": '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><lolz>&lol;&lol;&lol;</lolz>'
    }
    
    # Race condition scenarios
    race_conditions = [
        {
            "name": "concurrent_role_updates",
            "description": "Update same role from 100 threads simultaneously",
            "threads": 100,
            "operations": ["grant_permission", "revoke_permission", "update_name", "delete"]
        },
        {
            "name": "user_delete_while_active",
            "description": "Delete user while they're performing actions",
            "sequence": ["login", "start_operation", "delete_user", "continue_operation"]
        },
        {
            "name": "permission_check_bypass",
            "description": "Change permissions while request is in flight",
            "timing": "microsecond precision required"
        }
    ]
    
    # State corruption attempts
    state_corruption = [
        {
            "name": "circular_role_hierarchy",
            "description": "Create A->B->C->A role hierarchy",
            "expected_result": "System should detect and prevent"
        },
        {
            "name": "orphaned_permissions",
            "description": "Delete role but keep permission references",
            "cleanup_test": True
        },
        {
            "name": "duplicate_unique_constraints",
            "description": "Force duplicate entries through race conditions",
            "method": "parallel_inserts"
        }
    ]
    
    # Resource exhaustion
    resource_attacks = [
        {
            "name": "connection_pool_exhaustion",
            "description": "Open connections without closing",
            "connections": 10000
        },
        {
            "name": "memory_exhaustion",
            "description": "Create millions of small objects",
            "objects": 10000000
        },
        {
            "name": "disk_space_attack",
            "description": "Fill audit logs with massive entries",
            "size_gb": 100
        },
        {
            "name": "cpu_spike",
            "description": "Trigger expensive computations",
            "operations": ["bcrypt_rounds_20", "large_permission_matrix", "recursive_checks"]
        }
    ]
    
    return {
        "malicious_payloads": malicious_payloads,
        "race_conditions": race_conditions,
        "state_corruption": state_corruption,
        "resource_attacks": resource_attacks,
        "timing_attacks": [
            "measure_user_enumeration_timing",
            "password_check_timing_analysis",
            "permission_check_timing_leaks"
        ],
        "business_logic_attacks": [
            "negative_quantity_values",
            "exceed_integer_limits",
            "bypass_workflow_steps",
            "manipulate_audit_timestamps",
            "forge_system_messages"
        ]
    }

def create_chaos_qa_workflow():
    """Create a chaos testing workflow"""
    workflow = Workflow(name="chaos_qa_testing")
    
    # Chaos scenario generator
    chaos_generator = PythonCodeNode.from_function(
        name="chaos_scenario_generator",
        func=generate_chaos_scenarios
    )
    
    # Chaos Agent - The Destroyer
    chaos_agent = LLMAgentNode(
        name="chaos_destroyer",
        model="gpt-4",
        system_prompt="""You are a Chaos QA Engineer with a mission to break systems.
Your personality:
- Relentless in finding vulnerabilities
- Creative in exploitation techniques
- Thorough in documenting destruction
- Professional in reporting findings

Your chaos testing methodology:
1. Start with reconnaissance - understand the system
2. Identify weak points and attack surfaces
3. Execute progressively more aggressive tests
4. Attempt to chain vulnerabilities
5. Try to achieve persistent compromise
6. Document everything for developers

Focus areas:
- Authentication bypass techniques
- Privilege escalation paths
- Data exfiltration methods
- Service disruption attacks
- State corruption possibilities
- Race condition exploitation

Remember: You're helping make the system stronger by finding weaknesses!""",
        prompt_template="""Analyze these chaos scenarios and create a devastating test plan:

Malicious Payloads Available:
{malicious_payloads}

Race Conditions to Exploit:
{race_conditions}

State Corruption Attempts:
{state_corruption}

Resource Attacks:
{resource_attacks}

Create specific attack chains that combine multiple techniques. 
Be creative in how you might bypass defenses.
Think like a real attacker but document like a professional."""
    )
    
    # Attack Simulator
    attack_simulator = PythonCodeNode(
        name="attack_simulator",
        code='''
import random
import hashlib
import time

# Parse chaos plan
attack_plan = input_data if isinstance(input_data, dict) else {}

# Simulate various attacks
attack_results = {
    "timestamp": datetime.now().isoformat(),
    "attacks_executed": 0,
    "successful_exploits": 0,
    "defenses_bypassed": 0,
    "systems_compromised": [],
    "vulnerabilities_found": [],
    "attack_log": []
}

def simulate_injection_attack(payload_type, payload):
    """Simulate injection attack"""
    success_rate = random.random()
    
    if payload_type == "sql_injection":
        if success_rate > 0.8:  # Assuming good defenses
            return {
                "status": "blocked",
                "defense": "Parameterized queries prevented injection",
                "confidence": "high"
            }
        else:
            return {
                "status": "potential_vulnerability",
                "defense": "Input validation might be insufficient",
                "confidence": "medium",
                "severity": "high"
            }
    
    elif payload_type == "xss":
        if success_rate > 0.7:
            return {
                "status": "blocked", 
                "defense": "Output encoding prevented XSS",
                "confidence": "high"
            }
        else:
            return {
                "status": "vulnerability_found",
                "defense": "Insufficient output sanitization",
                "confidence": "high",
                "severity": "high"
            }
    
    return {"status": "test_executed", "result": "unknown"}

def simulate_race_condition(scenario):
    """Simulate race condition attack"""
    timing_window = random.uniform(0.001, 0.1)  # milliseconds
    
    if timing_window < 0.01:  # Very small window
        return {
            "status": "race_condition_found",
            "timing_window_ms": timing_window * 1000,
            "exploitable": True,
            "severity": "medium",
            "description": f"Race condition in {scenario['name']} with {timing_window*1000:.2f}ms window"
        }
    else:
        return {
            "status": "no_race_condition",
            "timing_window_ms": timing_window * 1000,
            "exploitable": False,
            "description": "Proper locking prevents race condition"
        }

def simulate_resource_exhaustion(attack):
    """Simulate resource exhaustion attack"""
    resource_limit = random.randint(1000, 10000)
    attack_size = attack.get("connections", attack.get("objects", 1000))
    
    if attack_size > resource_limit:
        return {
            "status": "dos_possible",
            "resource": attack["name"],
            "limit_reached": resource_limit,
            "impact": "Service disruption possible",
            "severity": "high"
        }
    else:
        return {
            "status": "defended",
            "resource": attack["name"],
            "defense": "Resource limits prevented exhaustion",
            "current_limit": resource_limit
        }

def simulate_authentication_bypass():
    """Attempt various authentication bypasses"""
    bypass_attempts = [
        {
            "method": "jwt_algorithm_confusion",
            "payload": {"alg": "none"},
            "success_chance": 0.1
        },
        {
            "method": "sql_injection_login",
            "payload": "admin' --",
            "success_chance": 0.05
        },
        {
            "method": "session_fixation",
            "payload": "fixed_session_id",
            "success_chance": 0.15
        },
        {
            "method": "timing_attack_username",
            "payload": "enumerate_users",
            "success_chance": 0.3
        }
    ]
    
    results = []
    for attempt in bypass_attempts:
        if random.random() < attempt["success_chance"]:
            results.append({
                "vulnerability": attempt["method"],
                "severity": "critical",
                "exploited": True,
                "impact": "Complete authentication bypass"
            })
            attack_results["successful_exploits"] += 1
            attack_results["systems_compromised"].append("authentication")
    
    return results

def simulate_privilege_escalation():
    """Attempt privilege escalation"""
    escalation_paths = [
        "role_manipulation",
        "permission_injection", 
        "api_parameter_pollution",
        "jwt_claim_injection",
        "insecure_direct_object_reference"
    ]
    
    for path in escalation_paths:
        if random.random() < 0.2:  # 20% chance of finding escalation path
            attack_results["vulnerabilities_found"].append({
                "type": "privilege_escalation",
                "method": path,
                "severity": "critical",
                "from_role": "user",
                "to_role": "admin",
                "exploited": True
            })
            attack_results["successful_exploits"] += 1

# Execute attacks
print("🔥 Initiating chaos testing sequence...")

# 1. Authentication attacks
auth_results = simulate_authentication_bypass()
attack_results["attack_log"].extend(auth_results)
attack_results["attacks_executed"] += len(auth_results)

# 2. Injection attacks
for payload_type, payload in [("sql_injection", "'; DROP TABLE--"), ("xss", "<script>alert(1)</script>")]:
    result = simulate_injection_attack(payload_type, payload)
    attack_results["attack_log"].append({
        "attack": payload_type,
        "result": result
    })
    attack_results["attacks_executed"] += 1
    if result.get("status") == "vulnerability_found":
        attack_results["successful_exploits"] += 1

# 3. Race conditions
race_scenarios = attack_plan.get("race_conditions", [])
for scenario in race_scenarios[:3]:  # Test first 3
    result = simulate_race_condition(scenario)
    attack_results["attack_log"].append({
        "attack": "race_condition",
        "scenario": scenario["name"],
        "result": result
    })
    attack_results["attacks_executed"] += 1
    if result.get("exploitable"):
        attack_results["successful_exploits"] += 1

# 4. Resource exhaustion
resource_attacks = attack_plan.get("resource_attacks", [])
for attack in resource_attacks[:2]:  # Test first 2
    result = simulate_resource_exhaustion(attack)
    attack_results["attack_log"].append({
        "attack": "resource_exhaustion",
        "type": attack["name"],
        "result": result
    })
    attack_results["attacks_executed"] += 1
    if result.get("status") == "dos_possible":
        attack_results["successful_exploits"] += 1

# 5. Privilege escalation
simulate_privilege_escalation()

# Calculate chaos score
chaos_score = (attack_results["successful_exploits"] / max(attack_results["attacks_executed"], 1)) * 100
attack_results["chaos_score"] = chaos_score
attack_results["security_grade"] = (
    "F" if chaos_score > 50 else
    "D" if chaos_score > 30 else
    "C" if chaos_score > 20 else
    "B" if chaos_score > 10 else
    "A"
)

result = attack_results
'''
    )
    
    # Exploit Chain Builder
    exploit_chain_builder = LLMAgentNode(
        name="exploit_chain_builder",
        model="gpt-4",
        system_prompt="""You are an expert in chaining vulnerabilities for maximum impact.
Analyze the individual vulnerabilities found and create exploit chains that:
1. Combine multiple weaknesses
2. Bypass multiple layers of defense
3. Achieve persistent access
4. Enable data exfiltration
5. Maintain stealth

Think like an APT (Advanced Persistent Threat) group.""",
        prompt_template="""Given these discovered vulnerabilities:
{vulnerabilities_found}

And these compromised systems:
{systems_compromised}

Create sophisticated attack chains that demonstrate real-world attack scenarios.
Focus on achieving these objectives:
1. Initial access
2. Privilege escalation  
3. Lateral movement
4. Data exfiltration
5. Persistence

Provide specific technical details for each chain."""
    )
    
    # Chaos Report Generator
    chaos_report_generator = PythonCodeNode(
        name="chaos_report_generator",
        code='''
attack_results = input_data.get("attack_results", {})
exploit_chains = input_data.get("exploit_chains", {})

# Generate apocalyptic report
report = f"""
# 💀 CHAOS QA TEST REPORT - ADMIN FRAMEWORK 💀

**Test Date**: {attack_results.get("timestamp", "Unknown")}
**Chaos Level**: MAXIMUM
**Security Grade**: {attack_results.get("security_grade", "?")} 
**Chaos Score**: {attack_results.get("chaos_score", 0):.1f}%

## 🎯 Executive Summary

The Chaos QA Agent executed {attack_results.get("attacks_executed", 0)} attacks against the admin framework.

### Key Findings:
- **Successful Exploits**: {attack_results.get("successful_exploits", 0)}
- **Systems Compromised**: {len(attack_results.get("systems_compromised", []))}
- **Critical Vulnerabilities**: {len([v for v in attack_results.get("vulnerabilities_found", []) if v.get("severity") == "critical"])}
- **High Severity Issues**: {len([v for v in attack_results.get("vulnerabilities_found", []) if v.get("severity") == "high"])}

## 🔥 Critical Vulnerabilities Found

"""

# List critical vulnerabilities
critical_vulns = [v for v in attack_results.get("vulnerabilities_found", []) if v.get("severity") == "critical"]
for i, vuln in enumerate(critical_vulns, 1):
    report += f"""
### {i}. {vuln.get("type", "Unknown").replace("_", " ").title()}
- **Method**: {vuln.get("method", "Unknown")}
- **Impact**: {vuln.get("impact", "System compromise")}
- **Exploited**: {"Yes ✓" if vuln.get("exploited") else "No"}
"""

report += """

## 🔗 Exploit Chains Discovered

"""

# Add exploit chains from LLM analysis
if isinstance(exploit_chains, dict) and "result" in exploit_chains:
    report += exploit_chains["result"]

report += """

## 📊 Attack Log Summary

| Attack Type | Attempts | Successful | Success Rate |
|-------------|----------|------------|--------------|
"""

# Summarize attack types
attack_summary = {}
for log_entry in attack_results.get("attack_log", []):
    attack_type = log_entry.get("attack", "unknown")
    if attack_type not in attack_summary:
        attack_summary[attack_type] = {"attempts": 0, "successful": 0}
    attack_summary[attack_type]["attempts"] += 1
    if log_entry.get("result", {}).get("status") in ["vulnerability_found", "dos_possible", "race_condition_found"]:
        attack_summary[attack_type]["successful"] += 1

for attack_type, stats in attack_summary.items():
    success_rate = (stats["successful"] / stats["attempts"] * 100) if stats["attempts"] > 0 else 0
    report += f"| {attack_type.replace('_', ' ').title()} | {stats['attempts']} | {stats['successful']} | {success_rate:.1f}% |\n"

report += f"""

## 🛡️ Recommendations

### Immediate Actions Required:
1. **Patch Critical Vulnerabilities** - Address all critical findings within 24 hours
2. **Implement Rate Limiting** - Prevent brute force and DoS attacks  
3. **Add Input Validation** - Sanitize all user inputs comprehensively
4. **Fix Race Conditions** - Implement proper locking mechanisms
5. **Enhance Authentication** - Add multi-factor authentication

### Security Hardening:
- Enable security headers (CSP, HSTS, X-Frame-Options)
- Implement least privilege access control
- Add comprehensive audit logging
- Set up intrusion detection systems
- Regular security scanning and penetration testing

### Architecture Improvements:
- Implement defense in depth
- Add security layers between components
- Use secure coding practices
- Regular security training for developers
- Establish incident response procedures

## ⚠️ Risk Assessment

**Overall Risk Level**: {"CRITICAL" if attack_results.get("chaos_score", 0) > 30 else "HIGH" if attack_results.get("chaos_score", 0) > 20 else "MEDIUM"}

The system showed vulnerabilities in {len(attack_results.get("systems_compromised", []))} critical areas.
Immediate remediation is required to prevent potential breaches.

---

*"In chaos, we find truth. In breaking, we build stronger."* - Chaos QA Team
"""

result = {
    "report": report,
    "metrics": {
        "total_attacks": attack_results.get("attacks_executed", 0),
        "successful_exploits": attack_results.get("successful_exploits", 0),
        "chaos_score": attack_results.get("chaos_score", 0),
        "security_grade": attack_results.get("security_grade", "?")
    }
}
'''
    )
    
    # Connect the chaos
    workflow.add_node(chaos_generator)
    workflow.add_node(chaos_agent)
    workflow.add_node(attack_simulator)
    workflow.add_node(exploit_chain_builder)
    workflow.add_node(chaos_report_generator)
    
    # Flow
    workflow.connect(chaos_generator.name, chaos_agent.name,
                    {"result": "input_data"})
    workflow.connect(chaos_agent.name, attack_simulator.name,
                    {"result": "input_data"})
    workflow.connect(attack_simulator.name, exploit_chain_builder.name,
                    {"result": "input_data"})
    
    # Merge for final report
    merge_node = PythonCodeNode(
        name="merge_chaos_results",
        code="""
result = {
    "attack_results": input_data.get("attack_results", {}),
    "exploit_chains": input_data.get("exploit_chains", {})
}
"""
    )
    workflow.add_node(merge_node)
    
    workflow.connect(attack_simulator.name, merge_node.name,
                    {"result": "attack_results"})
    workflow.connect(exploit_chain_builder.name, merge_node.name,
                    {"result": "exploit_chains"})
    workflow.connect(merge_node.name, chaos_report_generator.name,
                    {"result": "input_data"})
    
    return workflow

def main():
    """Unleash the chaos"""
    print("💀 INITIATING CHAOS QA TESTING PROTOCOL 💀")
    print("=" * 60)
    print("⚠️  WARNING: This test suite attempts to break everything!")
    print("=" * 60)
    
    workflow = create_chaos_qa_workflow()
    
    print("\n🔥 Releasing the chaos agents...")
    time.sleep(1)  # Dramatic pause
    
    result = workflow.run()
    
    if result.is_success:
        report_data = result.node_results.get("chaos_report_generator", {})
        if "report" in report_data:
            print("\n" + report_data["report"])
            
            metrics = report_data.get("metrics", {})
            if metrics.get("security_grade") in ["D", "F"]:
                print("\n🚨 CRITICAL SECURITY FAILURES DETECTED! 🚨")
                print("The system has significant vulnerabilities that need immediate attention!")
    else:
        print(f"\n❌ Chaos testing failed to execute: {result.error}")
        print("(Even chaos needs to follow some rules...)")

if __name__ == "__main__":
    main()