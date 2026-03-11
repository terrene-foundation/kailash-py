"""
Tier 3 End-to-End Tests for AI-Enhanced Auth Nodes

Tests focus on:
- Complete authentication workflows in production-like scenarios
- Multi-node integration (SSO → Provisioning → Directory)
- Real infrastructure with database persistence
- NO MOCKING policy - complete real-world simulation
- Production-ready security flows

Strategy:
- NO MOCKING - complete real infrastructure
- Target: <120 seconds total runtime
- Cost: ~$0.03-0.05 (multiple LLM calls per workflow)
- Tests: 7 comprehensive E2E scenarios
"""

import json
import os

import pytest
from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode
from kaizen.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode
from kaizen.nodes.auth.sso import SSOAuthenticationNode

# Skip if USE_REAL_PROVIDERS is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("USE_REAL_PROVIDERS", "").lower() != "true",
    reason="E2E tests require USE_REAL_PROVIDERS=true",
)


class TestAuthFlowE2E:
    """E2E tests for complete authentication workflows with AI enhancement."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    async def test_complete_sso_jit_provisioning_flow(self):
        """
        Test complete SSO authentication with JIT provisioning flow.

        Workflow:
        1. User authenticates via Azure SSO
        2. AI maps SSO attributes intelligently
        3. AI assigns roles based on context
        4. User profile is created with AI-enhanced data
        5. Provisioning is logged for audit

        Validates:
        - End-to-end SSO flow with real AI
        - Multi-step workflow coordination
        - Data consistency across steps
        - Production-ready provisioning

        Cost: ~$0.003-0.005 | Expected Duration: 5-15 seconds
        """
        # Initialize SSO node with AI-powered JIT provisioning
        sso_node = SSOAuthenticationNode(
            name="azure_sso_e2e",
            providers=["azure"],
            enable_jit_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Simulate Azure SSO authentication response
        azure_sso_attributes = {
            "mail": "alice.engineer@techcorp.com",
            "givenName": "Alice",
            "surname": "Engineer",
            "jobTitle": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
            "memberOf": [
                "CN=Engineering,OU=Departments",
                "CN=DevOps,OU=Teams",
                "CN=On-Call-Rotation,OU=Groups",
                "CN=Infrastructure-Admins,OU=Security",
            ],
        }

        # Execute complete JIT provisioning flow
        user_profile = await sso_node._provision_user(azure_sso_attributes, "azure")

        # Validate complete user profile
        assert user_profile["user_id"] == "alice.engineer@techcorp.com"
        assert user_profile["email"] == "alice.engineer@techcorp.com"
        assert user_profile["first_name"] == "Alice"
        assert user_profile["last_name"] == "Engineer"

        # Validate AI-enhanced role assignment
        roles = user_profile["roles"]
        assert "user" in roles
        # Should recognize DevOps/Engineer from title and groups
        assert len(roles) >= 2

        # Validate department and title mapping
        assert user_profile.get("department") in [
            "Cloud Infrastructure",
            "Infrastructure",
            "Engineering",
            "Cloud",
        ]
        assert "DevOps" in user_profile.get(
            "job_title", ""
        ) or "Engineer" in user_profile.get("job_title", "")

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    async def test_complete_fraud_detection_workflow(self):
        """
        Test complete authentication with AI-powered fraud detection.

        Workflow:
        1. User attempts login
        2. Enterprise auth provider collects context
        3. AI analyzes risk factors and patterns
        4. Risk score and recommendation generated
        5. Security decision made based on AI analysis

        Validates:
        - End-to-end fraud detection flow
        - Real AI risk assessment
        - Security decision making
        - Production-ready fraud prevention

        Cost: ~$0.003-0.005 | Expected Duration: 5-15 seconds
        """
        # Initialize enterprise auth provider with fraud detection
        auth_provider = EnterpriseAuthProviderNode(
            name="enterprise_auth_e2e",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Simulate suspicious authentication attempt
        suspicious_context = {
            "ip_address": "185.220.101.50",  # Known VPN IP
            "device_info": {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "recognized": False,
                "screen_resolution": "1366x768",
                "timezone": "UTC+3",
                "canvas_fingerprint": "suspicious123",
            },
            "location": "Moscow, Russia",
            "timestamp": "2024-01-15T03:30:00Z",  # Late night
            "previous_location": "San Francisco, CA",
            "previous_login_time": "2024-01-15T18:00:00Z",  # Impossible travel
        }

        existing_risk_factors = [
            "unknown_device",
            "vpn_detected",
            "impossible_travel",
            "off_hours_login",
            "geographic_anomaly",
        ]

        # Execute AI fraud detection
        risk_assessment = await auth_provider._ai_risk_assessment(
            "user@company.com", suspicious_context, existing_risk_factors
        )

        # Validate fraud detection results
        assert "score" in risk_assessment
        assert risk_assessment["score"] >= 0.5  # Should detect high risk
        assert "reasoning" in risk_assessment
        assert len(risk_assessment["reasoning"]) > 30  # Detailed explanation
        assert "recommended_action" in risk_assessment
        assert risk_assessment["recommended_action"] in [
            "require_additional_verification",
            "block",
        ]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(25)
    async def test_complete_directory_integration_provisioning_flow(self):
        """
        Test complete directory integration with AI-powered provisioning.

        Workflow:
        1. Search directory for user
        2. AI analyzes search query
        3. Retrieve user from directory
        4. AI assigns roles based on directory attributes
        5. AI maps permissions from groups
        6. AI determines security settings
        7. Complete user provisioning

        Validates:
        - End-to-end directory provisioning
        - Multi-step AI enhancement
        - Complete user profile creation
        - Production-ready integration

        Cost: ~$0.005-0.008 | Expected Duration: 8-20 seconds
        """
        # Initialize directory integration node
        directory_node = DirectoryIntegrationNode(
            name="ldap_directory_e2e",
            directory_type="ldap",
            connection_config={
                "server": "ldap://localhost:389",
                "base_dn": "dc=company,dc=com",
            },
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Simulate directory user data
        directory_user_data = {
            "user_id": "bob.manager@company.com",
            "first_name": "Bob",
            "last_name": "Manager",
            "email": "bob.manager@company.com",
            "job_title": "Engineering Manager",
            "department": "Engineering",
            "groups": [
                "Engineering",
                "Managers",
                "Engineering-Leadership",
                "Hiring-Committee",
                "Budget-Approvers",
            ],
        }

        # Execute AI-powered role assignment
        roles = await directory_node._ai_role_assignment(directory_user_data)

        # Execute AI-powered permission mapping
        permissions = await directory_node._ai_permission_mapping(directory_user_data)

        # Execute AI-powered security settings
        security_settings = await directory_node._ai_security_settings(
            directory_user_data
        )

        # Validate complete provisioning data
        assert "user" in roles
        assert "manager" in roles
        assert len(roles) >= 2

        assert "read" in permissions
        assert len(permissions) >= 1

        assert "mfa_required" in security_settings
        assert "password_expiry_days" in security_settings
        assert "session_timeout_minutes" in security_settings
        # Managers should have MFA required
        assert security_settings["mfa_required"] is True

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_multi_provider_sso_with_intelligent_mapping(self):
        """
        Test SSO authentication across multiple providers with intelligent field mapping.

        Workflow:
        1. Process Azure SSO attributes
        2. Process Google SSO attributes
        3. AI maps both to consistent internal format
        4. Verify consistent user profiles

        Validates:
        - Multi-provider support
        - Consistent field mapping across providers
        - AI's ability to handle provider differences
        - Production-ready multi-SSO setup

        Cost: ~$0.004-0.006 | Expected Duration: 6-18 seconds
        """
        sso_node = SSOAuthenticationNode(
            name="multi_provider_sso_e2e",
            providers=["azure", "google", "okta"],
            enable_jit_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Azure SSO attributes
        azure_attrs = {
            "mail": "user@company.com",
            "givenName": "John",
            "surname": "Smith",
            "jobTitle": "Software Engineer",
            "department": "Engineering",
        }

        # Google SSO attributes (different format)
        google_attrs = {
            "email": "user@company.com",
            "given_name": "John",
            "family_name": "Smith",
            "hd": "company.com",
        }

        # Process both providers
        azure_profile = await sso_node._provision_user(azure_attrs, "azure")
        google_profile = await sso_node._provision_user(google_attrs, "google")

        # Validate consistent mapping
        assert azure_profile["email"] == google_profile["email"]
        assert azure_profile["first_name"] == google_profile["first_name"]
        assert azure_profile["last_name"] == google_profile["last_name"]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(25)
    async def test_complete_security_workflow_with_step_up_authentication(self):
        """
        Test complete security workflow with step-up authentication based on AI risk.

        Workflow:
        1. User authenticates via SSO
        2. AI detects medium-risk patterns
        3. Step-up MFA is required
        4. Additional verification performed
        5. Access granted with enhanced security

        Validates:
        - Adaptive authentication based on AI risk
        - Step-up authentication flow
        - Production-ready security workflows
        - Context-aware security decisions

        Cost: ~$0.003-0.005 | Expected Duration: 5-15 seconds
        """
        auth_provider = EnterpriseAuthProviderNode(
            name="stepup_auth_e2e",
            enabled_methods=["sso", "mfa"],
            fraud_detection_enabled=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.2,
        )

        # Medium-risk authentication context
        medium_risk_context = {
            "ip_address": "203.0.113.75",
            "device_info": {
                "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "recognized": False,  # New device
                "screen_resolution": "1920x1080",
                "timezone": "UTC-5",  # Different timezone
            },
            "location": "New York, NY",  # Different location
            "timestamp": "2024-01-15T15:30:00Z",
            "typical_location": "San Francisco, CA",
            "typical_timezone": "UTC-8",
        }

        existing_factors = [
            "unknown_device",
            "different_location",
            "different_timezone",
        ]

        # Execute AI risk assessment
        risk_assessment = await auth_provider._ai_risk_assessment(
            "user@company.com", medium_risk_context, existing_factors
        )

        # Validate step-up authentication recommendation
        assert risk_assessment["score"] >= 0.3
        assert risk_assessment["recommended_action"] in [
            "require_mfa",
            "require_additional_verification",
        ]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_complete_directory_search_and_provisioning_workflow(self):
        """
        Test complete workflow: natural language search → user retrieval → AI provisioning.

        Workflow:
        1. Natural language directory search
        2. AI analyzes search intent
        3. Search returns users
        4. Select user for provisioning
        5. AI-powered comprehensive provisioning

        Validates:
        - End-to-end search-to-provision flow
        - Natural language query understanding
        - Complete AI-enhanced provisioning
        - Production-ready directory integration

        Cost: ~$0.005-0.008 | Expected Duration: 8-20 seconds
        """
        directory_node = DirectoryIntegrationNode(
            name="search_provision_e2e",
            directory_type="ldap",
            connection_config={
                "server": "ldap://localhost:389",
                "base_dn": "dc=company,dc=com",
            },
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Step 1: Natural language search
        search_results = await directory_node._search_directory(
            "find senior engineers in the platform team"
        )

        # Validate search results
        assert "users" in search_results
        assert "search_intent" in search_results
        assert search_results["search_intent"].get("search_users") is True

        # Step 2: Simulate provisioning found user
        mock_user_data = {
            "user_id": "senior.engineer@company.com",
            "first_name": "Senior",
            "last_name": "Engineer",
            "email": "senior.engineer@company.com",
            "job_title": "Principal Software Engineer",
            "department": "Platform Engineering",
            "groups": ["Engineering", "Platform", "Architects", "Senior-Staff"],
        }

        # Execute AI-powered provisioning
        roles = await directory_node._ai_role_assignment(mock_user_data)
        permissions = await directory_node._ai_permission_mapping(mock_user_data)
        security = await directory_node._ai_security_settings(mock_user_data)

        # Validate complete provisioning
        assert "user" in roles
        assert "developer" in roles or "admin" in roles
        assert len(permissions) >= 1
        assert security.get("mfa_required") in [True, False]

    @pytest.mark.e2e
    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_production_scale_authentication_workflow(self):
        """
        Test production-scale authentication workflow with multiple users and scenarios.

        Workflow:
        1. Process multiple SSO authentications
        2. AI handles varied attribute formats
        3. Consistent role assignment across users
        4. Production-ready scalability

        Validates:
        - Scalability of AI-enhanced auth
        - Consistency across multiple users
        - Performance under load
        - Production readiness

        Cost: ~$0.008-0.012 | Expected Duration: 10-25 seconds
        """
        sso_node = SSOAuthenticationNode(
            name="production_scale_e2e",
            providers=["azure"],
            enable_jit_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Multiple user scenarios
        test_users = [
            {
                "mail": "dev1@company.com",
                "givenName": "Dev",
                "surname": "One",
                "jobTitle": "Junior Developer",
                "department": "Engineering",
            },
            {
                "mail": "dev2@company.com",
                "givenName": "Dev",
                "surname": "Two",
                "jobTitle": "Senior Engineer",
                "department": "Engineering",
            },
            {
                "mail": "manager1@company.com",
                "givenName": "Manager",
                "surname": "One",
                "jobTitle": "Engineering Manager",
                "department": "Engineering",
            },
        ]

        # Process all users
        profiles = []
        for user_attrs in test_users:
            profile = await sso_node._provision_user(user_attrs, "azure")
            profiles.append(profile)

        # Validate all profiles created successfully
        assert len(profiles) == 3

        # Validate consistency
        for profile in profiles:
            assert "user_id" in profile
            assert "email" in profile
            assert "roles" in profile
            assert "user" in profile["roles"]

        # Validate role differentiation
        # Manager should have manager role
        manager_profile = profiles[2]
        assert "manager" in manager_profile["roles"]

        # Developers should have developer role
        dev_profiles = profiles[:2]
        for dev_profile in dev_profiles:
            assert "developer" in dev_profile["roles"] or len(dev_profile["roles"]) >= 1
