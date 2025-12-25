#!/usr/bin/env python3
"""
Enterprise SSO and Authentication Demo

Comprehensive demonstration of enterprise authentication features:
- Single Sign-On (SSO) with multiple providers
- Directory Integration (LDAP, Active Directory)
- Multi-Factor Authentication (MFA)
- Risk-based adaptive authentication
- Session management
- Social login integration
- API key authentication
- JWT token authentication
- Passwordless authentication (WebAuthn simulation)

This demo exceeds Django's basic authentication by providing:
- Enterprise-grade SSO with 7+ providers
- AI-powered risk assessment
- Adaptive multi-factor authentication
- Real-time fraud detection
- Comprehensive audit trails
- Session security with device tracking
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode
from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode
from kailash.nodes.auth.mfa import MultiFactorAuthNode
from kailash.nodes.auth.session_management import SessionManagementNode
from kailash.nodes.auth.sso import SSOAuthenticationNode
from kailash.nodes.code import PythonCodeNode

from examples.utils.paths import get_output_data_path


async def setup_enterprise_auth() -> Dict[str, Any]:
    """Setup enterprise authentication provider with multiple methods."""
    print("🔐 Setting up Enterprise Authentication Provider...")

    # Configure SSO providers
    sso_config = {
        "providers": ["saml", "oauth2", "oidc", "azure", "google", "okta"],
        "saml_settings": {
            "entity_id": "kailash-admin",
            "sso_url": "https://company.okta.com/app/kailash/sso/saml",
            "x509_cert": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
        },
        "oauth_settings": {
            "azure_client_id": "12345678-1234-1234-1234-123456789abc",
            "azure_tenant_id": "company.onmicrosoft.com",
            "google_client_id": "123456789-abcdef.apps.googleusercontent.com",
            "okta_domain": "company.okta.com",
            "okta_client_id": "0oa123456789abcdef123",
        },
    }

    # Configure directory integration
    directory_config = {
        "directory_type": "ldap",
        "connection_config": {
            "server": "ldap://company.com:389",
            "base_dn": "DC=company,DC=com",
            "user_dn": "OU=Users,DC=company,DC=com",
            "group_dn": "OU=Groups,DC=company,DC=com",
        },
        "auto_provisioning": True,
    }

    # Configure MFA
    mfa_config = {
        "methods": ["totp", "sms", "email", "webauthn"],
        "backup_codes": True,
        "session_timeout": timedelta(hours=8),
    }

    # Configure session management
    session_config = {
        "max_sessions": 5,
        "idle_timeout": timedelta(minutes=30),
        "track_devices": True,
    }

    # Create enterprise auth provider
    enterprise_auth = EnterpriseAuthProviderNode(
        name="enterprise_auth_demo",
        enabled_methods=[
            "sso",
            "directory",
            "mfa",
            "passwordless",
            "social",
            "api_key",
            "jwt",
        ],
        primary_method="sso",
        fallback_methods=["directory", "mfa"],
        sso_config=sso_config,
        directory_config=directory_config,
        mfa_config=mfa_config,
        session_config=session_config,
        risk_assessment_enabled=True,
        adaptive_auth_enabled=True,
        fraud_detection_enabled=True,
        compliance_mode="strict",
        max_login_attempts=3,
        lockout_duration=timedelta(minutes=15),
    )

    return {
        "enterprise_auth": enterprise_auth,
        "sso_config": sso_config,
        "directory_config": directory_config,
        "mfa_config": mfa_config,
        "session_config": session_config,
    }


async def demonstrate_sso_authentication(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate SSO authentication with multiple providers."""
    print("\n🌐 Demonstrating SSO Authentication...")

    sso_results = []

    # 1. SAML 2.0 Authentication
    print("  📋 Testing SAML 2.0 authentication...")
    saml_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="sso",
        credentials={
            "provider": "saml",
            "request_data": {
                "SAMLResponse": "PHNhbWxwOlJlc3BvbnNlIC4uLg==",  # Base64 encoded SAML response
                "RelayState": "dashboard",
            },
        },
        user_id="john.doe@company.com",
        risk_context={
            "ip_address": "192.168.1.100",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
            "device_info": {
                "device_type": "desktop",
                "os": "Windows",
                "browser": "Chrome",
            },
        },
    )
    sso_results.append({"provider": "saml", "result": saml_auth})

    # 2. Azure AD Authentication
    print("  🏢 Testing Azure AD authentication...")
    azure_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="sso",
        credentials={
            "provider": "azure",
            "request_data": {
                "code": "azure_auth_code_12345",
                "state": "azure_state_token",
            },
        },
        user_id="jane.smith@company.com",
        risk_context={
            "ip_address": "10.0.0.50",
            "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1",
            "device_info": {
                "device_type": "laptop",
                "os": "macOS",
                "browser": "Safari",
            },
        },
    )
    sso_results.append({"provider": "azure", "result": azure_auth})

    # 3. Google Workspace Authentication
    print("  🌟 Testing Google Workspace authentication...")
    google_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="sso",
        credentials={
            "provider": "google",
            "request_data": {
                "code": "google_auth_code_67890",
                "state": "google_state_token",
            },
        },
        user_id="mike.johnson@company.com",
        risk_context={
            "ip_address": "203.0.113.10",  # External IP for higher risk
            "user_agent": "Mozilla/5.0 (Android 12; Mobile) Chrome/120.0",
            "device_info": {
                "device_type": "mobile",
                "os": "Android",
                "browser": "Chrome",
            },
        },
    )
    sso_results.append({"provider": "google", "result": google_auth})

    # 4. Okta Authentication
    print("  🎯 Testing Okta authentication...")
    okta_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="sso",
        credentials={
            "provider": "okta",
            "request_data": {
                "code": "okta_auth_code_abcdef",
                "state": "okta_state_token",
            },
        },
        user_id="sarah.wilson@company.com",
        risk_context={
            "ip_address": "192.168.1.200",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/120.0",
            "device_info": {
                "device_type": "desktop",
                "os": "Windows",
                "browser": "Edge",
            },
        },
    )
    sso_results.append({"provider": "okta", "result": okta_auth})

    return {
        "sso_providers_tested": len(sso_results),
        "successful_auths": sum(
            1 for r in sso_results if r["result"].get("authenticated")
        ),
        "results": sso_results,
    }


async def demonstrate_directory_integration(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate LDAP/Active Directory integration."""
    print("\n📁 Demonstrating Directory Integration...")

    directory_results = []

    # 1. LDAP Authentication
    print("  🔍 Testing LDAP authentication...")
    ldap_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="directory",
        credentials={"username": "bob.davis", "password": "SecurePassword123!"},
        risk_context={
            "ip_address": "192.168.2.100",
            "device_info": {"device_type": "desktop", "os": "Linux"},
        },
    )
    directory_results.append({"method": "ldap_auth", "result": ldap_auth})

    # 2. Directory User Search
    print("  🔎 Testing directory user search...")
    directory_node = enterprise_auth.directory_node
    user_search = await directory_node.execute_async(
        action="search", query="engineering", filters={"department": "Engineering"}
    )
    directory_results.append({"method": "user_search", "result": user_search})

    # 3. Directory Sync
    print("  🔄 Testing directory synchronization...")
    sync_result = await directory_node.execute_async(
        action="sync", sync_type="incremental"
    )
    directory_results.append({"method": "directory_sync", "result": sync_result})

    # 4. User Provisioning
    print("  👤 Testing user provisioning...")
    provision_result = await directory_node.execute_async(
        action="provision",
        user_id="new.employee",
        attributes=["mail", "givenName", "sn", "department"],
    )
    directory_results.append({"method": "user_provision", "result": provision_result})

    return {
        "directory_operations": len(directory_results),
        "successful_operations": sum(
            1 for r in directory_results if r["result"].get("success")
        ),
        "results": directory_results,
    }


async def demonstrate_adaptive_authentication(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate adaptive authentication based on risk assessment."""
    print("\n🎯 Demonstrating Adaptive Authentication...")

    adaptive_scenarios = []

    # Scenario 1: Low Risk - Normal Authentication
    print("  ✅ Testing low-risk authentication...")
    low_risk_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="directory",
        credentials={"username": "regular.user", "password": "password123"},
        risk_context={
            "ip_address": "192.168.1.50",  # Corporate IP
            "timestamp": "2024-01-15T14:30:00Z",  # Business hours
            "device_info": {
                "device_type": "desktop",
                "os": "Windows",
                "recognized": True,
            },
        },
    )
    adaptive_scenarios.append(
        {"scenario": "low_risk", "expected_factors": 1, "result": low_risk_auth}
    )

    # Scenario 2: Medium Risk - Requires MFA
    print("  ⚠️ Testing medium-risk authentication...")
    medium_risk_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="directory",
        credentials={
            "username": "manager.user",
            "password": "password123",
            "mfa_code": "123456",  # Provide MFA code
        },
        risk_context={
            "ip_address": "203.0.113.25",  # External IP
            "timestamp": "2024-01-15T14:30:00Z",
            "device_info": {
                "device_type": "laptop",
                "os": "macOS",
                "recognized": False,  # Unknown device
            },
        },
    )
    adaptive_scenarios.append(
        {"scenario": "medium_risk", "expected_factors": 2, "result": medium_risk_auth}
    )

    # Scenario 3: High Risk - Multiple Factors Required
    print("  🚨 Testing high-risk authentication...")
    high_risk_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="directory",
        credentials={
            "username": "admin.user",
            "password": "password123",
            "mfa_code": "789012",
            "webauthn_data": {
                "authenticatorData": "base64_auth_data",
                "signature": "base64_signature",
                "clientDataJSON": "base64_client_data",
            },
        },
        risk_context={
            "ip_address": "198.51.100.10",  # Foreign IP
            "timestamp": "2024-01-15T02:00:00Z",  # Off hours
            "location": "Unknown Country",
            "device_info": {
                "device_type": "mobile",
                "os": "iOS",
                "recognized": False,
                "jailbroken": False,
            },
        },
    )
    adaptive_scenarios.append(
        {"scenario": "high_risk", "expected_factors": 3, "result": high_risk_auth}
    )

    # Scenario 4: Critical Risk - Blocked
    print("  🛑 Testing critical-risk authentication (should be blocked)...")
    critical_risk_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="directory",
        credentials={"username": "suspicious.user", "password": "password123"},
        risk_context={
            "ip_address": "192.0.2.100",  # Known malicious IP (simulation)
            "timestamp": "2024-01-15T03:00:00Z",  # Very late hours
            "location": "High-risk Country",
            "device_info": {
                "device_type": "mobile",
                "os": "Android",
                "recognized": False,
                "rooted": True,  # Compromised device
            },
        },
    )
    adaptive_scenarios.append(
        {
            "scenario": "critical_risk",
            "expected_factors": 0,  # Should be blocked
            "result": critical_risk_auth,
        }
    )

    return {
        "adaptive_scenarios": len(adaptive_scenarios),
        "successful_auths": sum(
            1 for s in adaptive_scenarios if s["result"].get("authenticated")
        ),
        "blocked_attempts": sum(
            1 for s in adaptive_scenarios if not s["result"].get("success")
        ),
        "scenarios": adaptive_scenarios,
    }


async def demonstrate_passwordless_and_social(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate passwordless and social authentication."""
    print("\n🚀 Demonstrating Passwordless & Social Authentication...")

    modern_auth_results = []

    # 1. WebAuthn/FIDO2 Authentication
    print("  🔐 Testing WebAuthn passwordless authentication...")
    webauthn_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="passwordless",
        credentials={
            "webauthn_data": {
                "authenticatorData": "base64_encoded_authenticator_data",
                "signature": "base64_encoded_signature",
                "clientDataJSON": "base64_encoded_client_data",
                "credentialId": "credential_id_12345",
            }
        },
        user_id="tech.lead@company.com",
        risk_context={
            "ip_address": "192.168.1.75",
            "device_info": {
                "device_type": "laptop",
                "os": "Windows",
                "webauthn_supported": True,
            },
        },
    )
    modern_auth_results.append({"method": "webauthn", "result": webauthn_auth})

    # 2. Google Social Login
    print("  🌟 Testing Google social authentication...")
    google_social = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="social",
        credentials={
            "social_provider": "google",
            "access_token": "ya29.google_access_token_example",
        },
        risk_context={
            "ip_address": "192.168.1.80",
            "device_info": {"device_type": "mobile", "os": "Android"},
        },
    )
    modern_auth_results.append({"method": "google_social", "result": google_social})

    # 3. Microsoft Social Login
    print("  🏢 Testing Microsoft social authentication...")
    microsoft_social = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="social",
        credentials={
            "social_provider": "microsoft",
            "access_token": "microsoft_access_token_example",
        },
        risk_context={
            "ip_address": "192.168.1.85",
            "device_info": {"device_type": "desktop", "os": "Windows"},
        },
    )
    modern_auth_results.append(
        {"method": "microsoft_social", "result": microsoft_social}
    )

    # 4. GitHub Social Login
    print("  🐙 Testing GitHub social authentication...")
    github_social = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="social",
        credentials={
            "social_provider": "github",
            "access_token": "ghp_github_token_example",
        },
        risk_context={
            "ip_address": "192.168.1.90",
            "device_info": {"device_type": "laptop", "os": "macOS"},
        },
    )
    modern_auth_results.append({"method": "github_social", "result": github_social})

    return {
        "modern_auth_methods": len(modern_auth_results),
        "successful_auths": sum(
            1 for r in modern_auth_results if r["result"].get("authenticated")
        ),
        "results": modern_auth_results,
    }


async def demonstrate_api_and_token_auth(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate API key and JWT token authentication."""
    print("\n🔑 Demonstrating API Key & Token Authentication...")

    token_auth_results = []

    # 1. API Key Authentication
    print("  🗝️ Testing API key authentication...")
    api_key_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="api_key",
        credentials={"api_key": "ak_1234567890abcdef_service_account"},
        risk_context={"ip_address": "192.168.1.100", "user_agent": "ServiceBot/1.0"},
    )
    token_auth_results.append({"method": "api_key", "result": api_key_auth})

    # 2. JWT Token Authentication
    print("  🎫 Testing JWT token authentication...")
    # Create a sample JWT token (simulation)
    import base64

    jwt_header = base64.b64encode(
        json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
    ).decode()
    jwt_payload = base64.b64encode(
        json.dumps(
            {
                "sub": "system.service@company.com",
                "iss": "kailash-auth",
                "exp": int(time.time()) + 3600,  # Expires in 1 hour
                "iat": int(time.time()),
                "roles": ["service", "read"],
            }
        ).encode()
    ).decode()
    jwt_signature = base64.b64encode(b"fake_signature_for_demo").decode()
    jwt_token = f"{jwt_header}.{jwt_payload}.{jwt_signature}"

    jwt_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="jwt",
        credentials={"jwt_token": jwt_token},
        risk_context={"ip_address": "192.168.1.105", "user_agent": "APIClient/2.0"},
    )
    token_auth_results.append({"method": "jwt", "result": jwt_auth})

    # 3. Certificate-based Authentication
    print("  📜 Testing certificate authentication...")
    cert_auth = await enterprise_auth.execute_async(
        action="authenticate",
        auth_method="certificate",
        credentials={
            "client_certificate": """-----BEGIN CERTIFICATE-----
MIICdTCCAd4CAQAwDQYJKoZIhvcNAQEEBQAwXzELMAkGA1UEBhMCVVM...
-----END CERTIFICATE-----"""
        },
        risk_context={"ip_address": "192.168.1.110", "user_agent": "CertClient/1.0"},
    )
    token_auth_results.append({"method": "certificate", "result": cert_auth})

    return {
        "token_auth_methods": len(token_auth_results),
        "successful_auths": sum(
            1 for r in token_auth_results if r["result"].get("authenticated")
        ),
        "results": token_auth_results,
    }


async def demonstrate_session_management(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate advanced session management."""
    print("\n📱 Demonstrating Session Management...")

    session_results = []

    # Create multiple sessions for different devices
    devices = [
        {"type": "desktop", "os": "Windows", "browser": "Chrome", "ip": "192.168.1.50"},
        {"type": "mobile", "os": "iOS", "browser": "Safari", "ip": "192.168.1.51"},
        {"type": "tablet", "os": "Android", "browser": "Chrome", "ip": "192.168.1.52"},
        {"type": "laptop", "os": "macOS", "browser": "Firefox", "ip": "192.168.1.53"},
    ]

    user_id = "multi.device@company.com"
    created_sessions = []

    # Create sessions for each device
    for i, device in enumerate(devices):
        print(f"  📲 Creating session for {device['type']} ({device['os']})...")

        # Authenticate user
        auth_result = await enterprise_auth.execute_async(
            action="authenticate",
            auth_method="directory",
            credentials={"username": "multi.device", "password": "password123"},
            user_id=user_id,
            risk_context={"ip_address": device["ip"], "device_info": device},
        )

        if auth_result.get("authenticated"):
            created_sessions.append(
                {
                    "session_id": auth_result.get("session_id"),
                    "device": device,
                    "auth_result": auth_result,
                }
            )

    session_results.append(
        {
            "operation": "create_sessions",
            "sessions_created": len(created_sessions),
            "sessions": created_sessions,
        }
    )

    # Validate sessions
    print("  ✅ Validating sessions...")
    for session in created_sessions:
        validation = await enterprise_auth.execute_async(
            action="validate", session_id=session["session_id"]
        )
        session["validation"] = validation

    # Get session status
    print("  📊 Getting session status...")
    session_status = await enterprise_auth.execute_async(
        action="get_methods", user_id=user_id
    )
    session_results.append({"operation": "session_status", "result": session_status})

    # Terminate one session
    if created_sessions:
        print("  🔚 Terminating oldest session...")
        oldest_session = created_sessions[0]
        logout_result = await enterprise_auth.execute_async(
            action="logout", user_id=user_id, session_id=oldest_session["session_id"]
        )
        session_results.append(
            {
                "operation": "logout_session",
                "session_terminated": oldest_session["session_id"],
                "result": logout_result,
            }
        )

    return {
        "session_operations": len(session_results),
        "active_sessions": len(created_sessions) - 1,  # Minus the terminated one
        "devices_tested": len(devices),
        "results": session_results,
    }


async def demonstrate_risk_assessment(
    enterprise_auth: EnterpriseAuthProviderNode,
) -> Dict[str, Any]:
    """Demonstrate AI-powered risk assessment."""
    print("\n🤖 Demonstrating AI-Powered Risk Assessment...")

    risk_scenarios = [
        {
            "name": "Normal Business Login",
            "context": {
                "ip_address": "192.168.1.100",
                "timestamp": "2024-01-15T14:00:00Z",
                "location": "Corporate Office",
                "device_info": {
                    "device_type": "desktop",
                    "os": "Windows",
                    "recognized": True,
                },
            },
            "expected_risk": "low",
        },
        {
            "name": "Remote Work Login",
            "context": {
                "ip_address": "203.0.113.50",
                "timestamp": "2024-01-15T09:30:00Z",
                "location": "Home Office",
                "device_info": {
                    "device_type": "laptop",
                    "os": "macOS",
                    "recognized": True,
                },
            },
            "expected_risk": "low-medium",
        },
        {
            "name": "Travel Login",
            "context": {
                "ip_address": "198.51.100.25",
                "timestamp": "2024-01-15T20:00:00Z",
                "location": "Different City",
                "device_info": {
                    "device_type": "mobile",
                    "os": "iOS",
                    "recognized": False,
                },
            },
            "expected_risk": "medium",
        },
        {
            "name": "Suspicious Login",
            "context": {
                "ip_address": "192.0.2.100",
                "timestamp": "2024-01-15T03:00:00Z",
                "location": "Foreign Country",
                "device_info": {
                    "device_type": "unknown",
                    "os": "Linux",
                    "recognized": False,
                },
            },
            "expected_risk": "high",
        },
    ]

    risk_assessments = []

    for scenario in risk_scenarios:
        print(f"  🎯 Assessing risk for: {scenario['name']}")

        risk_result = await enterprise_auth.execute_async(
            action="assess_risk",
            user_id="test.user@company.com",
            risk_context=scenario["context"],
        )

        risk_assessments.append(
            {
                "scenario": scenario["name"],
                "expected_risk": scenario["expected_risk"],
                "assessed_risk": risk_result.get("risk_level"),
                "risk_score": risk_result.get("risk_score"),
                "factors": risk_result.get("factors", []),
                "full_result": risk_result,
            }
        )

    return {
        "risk_scenarios_tested": len(risk_scenarios),
        "assessments": risk_assessments,
        "ai_risk_engine_available": True,
    }


async def save_demo_results(all_results: Dict[str, Any]):
    """Save comprehensive demo results."""
    print("\n💾 Saving Demo Results...")

    output_file = get_output_data_path("sso_enterprise_auth_demo_results.json")

    # Prepare comprehensive results
    demo_summary = {
        "demo_completed_at": datetime.now(UTC).isoformat(),
        "enterprise_auth_features": {
            "sso_providers": [
                "SAML 2.0",
                "Azure AD",
                "Google Workspace",
                "Okta",
                "OAuth 2.0",
                "OIDC",
            ],
            "directory_integration": ["LDAP", "Active Directory", "Azure AD"],
            "mfa_methods": ["TOTP", "SMS", "Email", "WebAuthn"],
            "modern_auth": ["WebAuthn", "FIDO2", "Social Login", "API Keys", "JWT"],
            "security_features": [
                "Risk Assessment",
                "Adaptive Auth",
                "Fraud Detection",
                "Session Management",
            ],
        },
        "performance_metrics": {
            "total_auth_attempts": sum(
                [
                    all_results["sso_demo"]["sso_providers_tested"],
                    all_results["directory_demo"]["directory_operations"],
                    all_results["adaptive_demo"]["adaptive_scenarios"],
                    all_results["modern_auth_demo"]["modern_auth_methods"],
                    all_results["token_auth_demo"]["token_auth_methods"],
                ]
            ),
            "successful_authentications": sum(
                [
                    all_results["sso_demo"]["successful_auths"],
                    all_results["directory_demo"]["successful_operations"],
                    all_results["adaptive_demo"]["successful_auths"],
                    all_results["modern_auth_demo"]["successful_auths"],
                    all_results["token_auth_demo"]["successful_auths"],
                ]
            ),
            "session_operations": all_results["session_demo"]["session_operations"],
            "risk_assessments": all_results["risk_demo"]["risk_scenarios_tested"],
        },
        "django_comparison": {
            "django_auth_methods": ["username/password", "social (with packages)"],
            "kailash_auth_methods": 8,
            "django_sso_support": "Limited (requires packages)",
            "kailash_sso_support": "Enterprise-grade built-in",
            "django_mfa_support": "Third-party packages only",
            "kailash_mfa_support": "Built-in with multiple methods",
            "django_risk_assessment": "None",
            "kailash_risk_assessment": "AI-powered adaptive",
            "django_session_tracking": "Basic",
            "kailash_session_tracking": "Advanced with device fingerprinting",
        },
        "detailed_results": all_results,
    }

    with open(output_file, "w") as f:
        json.dump(demo_summary, f, indent=2, default=str)

    print(f"✅ Results saved to: {output_file}")
    return output_file


async def main():
    """Main enterprise authentication demo."""
    print("🏢 Kailash Enterprise SSO & Authentication Demo")
    print("=" * 60)

    try:
        # Setup
        auth_setup = await setup_enterprise_auth()
        enterprise_auth = auth_setup["enterprise_auth"]

        # Run all demonstrations
        results = {}

        results["sso_demo"] = await demonstrate_sso_authentication(enterprise_auth)
        results["directory_demo"] = await demonstrate_directory_integration(
            enterprise_auth
        )
        results["adaptive_demo"] = await demonstrate_adaptive_authentication(
            enterprise_auth
        )
        results["modern_auth_demo"] = await demonstrate_passwordless_and_social(
            enterprise_auth
        )
        results["token_auth_demo"] = await demonstrate_api_and_token_auth(
            enterprise_auth
        )
        results["session_demo"] = await demonstrate_session_management(enterprise_auth)
        results["risk_demo"] = await demonstrate_risk_assessment(enterprise_auth)

        # Save results
        output_file = await save_demo_results(results)

        # Get final statistics
        auth_stats = enterprise_auth.get_auth_statistics()

        print("\n🎉 Enterprise Authentication Demo Completed!")
        print("=" * 60)
        print("📊 Demo Summary:")
        print("   • SSO Providers: 4 tested (SAML, Azure AD, Google, Okta)")
        print(
            f"   • Directory Operations: {results['directory_demo']['directory_operations']}"
        )
        print(
            f"   • Adaptive Auth Scenarios: {results['adaptive_demo']['adaptive_scenarios']}"
        )
        print(
            f"   • Modern Auth Methods: {results['modern_auth_demo']['modern_auth_methods']}"
        )
        print(
            f"   • Token Auth Methods: {results['token_auth_demo']['token_auth_methods']}"
        )
        print(
            f"   • Session Operations: {results['session_demo']['session_operations']}"
        )
        print(f"   • Risk Assessments: {results['risk_demo']['risk_scenarios_tested']}")
        print(f"   • Total Auth Attempts: {auth_stats['total_attempts']}")
        print(
            f"   • Success Rate: {auth_stats['successful_auths']}/{auth_stats['total_attempts']}"
        )

        print("\n🆚 Comparison with Django Admin:")
        print("   • Django: Basic username/password, limited SSO")
        print("   • Kailash: 8+ auth methods, enterprise SSO, AI risk assessment")
        print("   • Django: No built-in MFA or adaptive authentication")
        print("   • Kailash: Multi-method MFA, adaptive auth, fraud detection")

        print(f"\n📁 Detailed results: {output_file}")

        return 0

    except Exception as e:
        print(f"❌ Demo failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.execute(main())
    exit(exit_code)
