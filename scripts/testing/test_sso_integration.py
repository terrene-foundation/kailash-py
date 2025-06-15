#!/usr/bin/env python3
"""
SSO Integration Test Suite

Comprehensive tests for Single Sign-On (SSO) integration including:
- SAML 2.0
- OAuth 2.0 / OpenID Connect
- Azure AD
- Google Workspace
- Okta
- Custom IdP integration
"""

import asyncio
import base64
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
import pytest

from kailash.nodes.auth.directory_integration import DirectoryIntegrationNode
from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode
from kailash.nodes.auth.session_management import SessionManagementNode

# Import SSO and auth nodes
from kailash.nodes.auth.sso import SSOAuthenticationNode
from kailash.nodes.security.audit_log import AuditLogNode
from kailash.runtime.local import LocalRuntime

# Import workflow components
from kailash.workflow import WorkflowBuilder


class TestSAMLIntegration:
    """Test suite for SAML 2.0 SSO integration."""

    @pytest.fixture
    def mock_saml_response(self):
        """Generate mock SAML response."""
        saml_response = """
        <samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
                       ID="response123" Version="2.0"
                       IssueInstant="2024-01-15T10:00:00Z">
            <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
                https://idp.company.com
            </saml:Issuer>
            <samlp:Status>
                <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
            </samlp:Status>
            <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
                <saml:Subject>
                    <saml:NameID Format="urn:oasis:names:tc:SAML:2.0:nameid-format:emailAddress">
                        john.doe@company.com
                    </saml:NameID>
                </saml:Subject>
                <saml:AttributeStatement>
                    <saml:Attribute Name="email">
                        <saml:AttributeValue>john.doe@company.com</saml:AttributeValue>
                    </saml:Attribute>
                    <saml:Attribute Name="firstName">
                        <saml:AttributeValue>John</saml:AttributeValue>
                    </saml:Attribute>
                    <saml:Attribute Name="lastName">
                        <saml:AttributeValue>Doe</saml:AttributeValue>
                    </saml:Attribute>
                    <saml:Attribute Name="groups">
                        <saml:AttributeValue>Engineering</saml:AttributeValue>
                        <saml:AttributeValue>Developers</saml:AttributeValue>
                    </saml:Attribute>
                </saml:AttributeStatement>
            </saml:Assertion>
        </samlp:Response>
        """
        return base64.b64encode(saml_response.encode()).decode()

    @pytest.mark.asyncio
    async def test_saml_sso_flow(self, mock_saml_response):
        """Test complete SAML SSO flow."""
        print("\n🔐 Testing SAML SSO Flow...")

        sso_node = SSOAuthenticationNode(
            providers=["saml"],
            saml_settings={
                "entity_id": "terrene-foundation-app",
                "sso_url": "https://idp.company.com/saml/sso",
                "slo_url": "https://idp.company.com/saml/slo",
                "x509_cert": """-----BEGIN CERTIFICATE-----
MIICmzCCAYMCBgF4...example...
-----END CERTIFICATE-----""",
                "attribute_mapping": {
                    "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
                    "name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
                    "groups": "http://schemas.xmlsoap.org/claims/Group",
                },
            },
        )

        # Step 1: Initiate SAML authentication
        init_result = await sso_node.execute_async(
            action="initiate",
            provider="saml",
            redirect_uri="https://app.company.com/auth/saml/callback",
            relay_state="origin=/dashboard",
        )

        assert init_result["success"] is True
        assert init_result["provider"] == "saml"
        assert "sso_url" in init_result
        assert "saml_request" in init_result
        assert "request_id" in init_result

        # Verify SAML request structure
        saml_request = base64.b64decode(init_result["saml_request"]).decode()
        assert "<samlp:AuthnRequest" in saml_request
        assert init_result["request_id"] in saml_request

        # Step 2: Process SAML response
        callback_result = await sso_node.execute_async(
            action="callback",
            provider="saml",
            saml_response=mock_saml_response,
            relay_state="origin=/dashboard",
        )

        assert callback_result["success"] is True
        assert callback_result["authenticated"] is True
        assert "user_attributes" in callback_result
        assert callback_result["user_attributes"]["email"] == "john.doe@company.com"
        assert "groups" in callback_result["user_attributes"]

        # Step 3: Create session from SAML attributes
        session_result = await sso_node.execute_async(
            action="create_session",
            provider="saml",
            user_attributes=callback_result["user_attributes"],
            remember_me=True,
        )

        assert session_result["success"] is True
        assert "session_id" in session_result
        assert "expires_at" in session_result

        print("✅ SAML SSO Flow test passed")

    @pytest.mark.asyncio
    async def test_saml_single_logout(self):
        """Test SAML Single Logout (SLO) flow."""
        print("\n🚪 Testing SAML Single Logout...")

        sso_node = SSOAuthenticationNode(
            providers=["saml"],
            saml_settings={
                "entity_id": "kailash-app",
                "slo_url": "https://idp.company.com/saml/slo",
                "slo_binding": "HTTP-POST",
            },
        )

        # Initiate logout
        logout_result = await sso_node.execute_async(
            action="logout",
            provider="saml",
            session_id="session_123",
            name_id="john.doe@company.com",
            session_index="idx_456",
        )

        assert logout_result["success"] is True
        assert "logout_request" in logout_result
        assert "logout_url" in logout_result

        # Process logout response
        logout_response = await sso_node.execute_async(
            action="process_logout_response",
            provider="saml",
            saml_response="base64_encoded_logout_response",
        )

        assert logout_response["success"] is True
        assert logout_response["logged_out"] is True

        print("✅ SAML Single Logout test passed")

    @pytest.mark.asyncio
    async def test_saml_metadata_generation(self):
        """Test SAML metadata generation."""
        print("\n📄 Testing SAML Metadata Generation...")

        sso_node = SSOAuthenticationNode(
            providers=["saml"],
            saml_settings={
                "entity_id": "terrene-foundation",
                "assertion_consumer_service_url": "https://app.company.com/saml/acs",
                "single_logout_service_url": "https://app.company.com/saml/sls",
                "name_id_format": "urn:oasis:names:tc:SAML:2.0:nameid-format:emailAddress",
                "x509_cert": "cert_data",
                "contact_person": {
                    "technical": {"name": "Tech Support", "email": "tech@company.com"}
                },
            },
        )

        # Generate metadata
        metadata_result = await sso_node.execute_async(
            action="generate_metadata", provider="saml"
        )

        assert metadata_result["success"] is True
        assert "metadata_xml" in metadata_result

        # Parse and validate metadata
        metadata = metadata_result["metadata_xml"]
        assert "<EntityDescriptor" in metadata
        assert 'entityID="terrene-foundation"' in metadata
        assert "<SPSSODescriptor" in metadata
        assert "<AssertionConsumerService" in metadata

        print("✅ SAML Metadata Generation test passed")


class TestOAuth2Integration:
    """Test suite for OAuth 2.0 / OpenID Connect integration."""

    @pytest.fixture
    def mock_oauth_tokens(self):
        """Generate mock OAuth tokens."""
        return {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
            "refresh_token": "refresh_token_123456",
            "id_token": jwt.encode(
                {
                    "sub": "user123",
                    "email": "john.doe@company.com",
                    "name": "John Doe",
                    "iat": int(datetime.now(UTC).timestamp()),
                    "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
                },
                "secret",
                algorithm="HS256",
            ),
            "token_type": "Bearer",
            "expires_in": 3600,
        }

    @pytest.mark.asyncio
    async def test_oauth2_authorization_code_flow(self, mock_oauth_tokens):
        """Test OAuth 2.0 authorization code flow."""
        print("\n🔑 Testing OAuth 2.0 Authorization Code Flow...")

        sso_node = SSOAuthenticationNode(
            providers=["oauth2"],
            oauth_settings={
                "client_id": "kailash_client_123",
                "client_secret": "secret_456",
                "authorization_endpoint": "https://auth.provider.com/authorize",
                "token_endpoint": "https://auth.provider.com/token",
                "userinfo_endpoint": "https://auth.provider.com/userinfo",
                "scopes": ["openid", "profile", "email"],
                "response_type": "code",
                "pkce_enabled": True,
            },
        )

        # Step 1: Generate authorization URL
        auth_result = await sso_node.execute_async(
            action="initiate",
            provider="oauth2",
            redirect_uri="https://app.company.com/auth/callback",
            state="random_state_123",
            nonce="random_nonce_456",
        )

        assert auth_result["success"] is True
        assert "auth_url" in auth_result
        assert "state" in auth_result
        assert "code_verifier" in auth_result  # PKCE

        # Parse auth URL
        parsed_url = urlparse(auth_result["auth_url"])
        params = parse_qs(parsed_url.query)

        assert params["client_id"][0] == "kailash_client_123"
        assert params["response_type"][0] == "code"
        assert "code_challenge" in params  # PKCE
        assert params["state"][0] == "random_state_123"

        # Step 2: Handle callback with authorization code
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=mock_oauth_tokens
            )

            callback_result = await sso_node.execute_async(
                action="callback",
                provider="oauth2",
                code="auth_code_789",
                state="random_state_123",
                code_verifier=auth_result["code_verifier"],
            )

        assert callback_result["success"] is True
        assert "access_token" in callback_result
        assert "id_token" in callback_result
        assert "user_info" in callback_result

        # Step 3: Refresh token
        refresh_result = await sso_node.execute_async(
            action="refresh_token",
            provider="oauth2",
            refresh_token=mock_oauth_tokens["refresh_token"],
        )

        assert refresh_result["success"] is True
        assert "access_token" in refresh_result

        print("✅ OAuth 2.0 Authorization Code Flow test passed")

    @pytest.mark.asyncio
    async def test_openid_connect_flow(self):
        """Test OpenID Connect flow with ID token validation."""
        print("\n🆔 Testing OpenID Connect Flow...")

        sso_node = SSOAuthenticationNode(
            providers=["oidc"],
            oidc_settings={
                "issuer": "https://auth.provider.com",
                "client_id": "kailash_oidc_client",
                "client_secret": "oidc_secret",
                "discovery_endpoint": "https://auth.provider.com/.well-known/openid-configuration",
                "validate_id_token": True,
                "verify_signature": True,
                "required_claims": ["email", "name"],
            },
        )

        # Mock discovery document
        discovery_doc = {
            "issuer": "https://auth.provider.com",
            "authorization_endpoint": "https://auth.provider.com/authorize",
            "token_endpoint": "https://auth.provider.com/token",
            "userinfo_endpoint": "https://auth.provider.com/userinfo",
            "jwks_uri": "https://auth.provider.com/jwks",
        }

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value=discovery_doc
            )

            # Auto-discover endpoints
            discover_result = await sso_node.execute_async(
                action="discover", provider="oidc"
            )

        assert discover_result["success"] is True
        assert discover_result["endpoints"]["issuer"] == "https://auth.provider.com"

        # Test ID token validation
        id_token_claims = {
            "sub": "user123",
            "email": "john.doe@company.com",
            "name": "John Doe",
            "iss": "https://auth.provider.com",
            "aud": "kailash_oidc_client",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(UTC).timestamp()),
        }

        validate_result = await sso_node.execute_async(
            action="validate_id_token",
            provider="oidc",
            id_token=jwt.encode(id_token_claims, "secret", algorithm="HS256"),
            nonce="expected_nonce",
        )

        assert validate_result["success"] is True
        assert validate_result["valid"] is True
        assert validate_result["claims"]["email"] == "john.doe@company.com"

        print("✅ OpenID Connect Flow test passed")


class TestProviderSpecificIntegrations:
    """Test suite for specific provider integrations."""

    @pytest.mark.asyncio
    async def test_azure_ad_integration(self):
        """Test Azure Active Directory integration."""
        print("\n☁️ Testing Azure AD Integration...")

        sso_node = SSOAuthenticationNode(
            providers=["azure"],
            azure_settings={
                "tenant_id": "company.onmicrosoft.com",
                "client_id": "azure_app_123",
                "client_secret": "azure_secret",
                "authority": "https://login.microsoftonline.com/company.onmicrosoft.com",
                "scopes": ["User.Read", "GroupMember.Read.All"],
                "graph_endpoint": "https://graph.microsoft.com/v1.0",
                "enable_conditional_access": True,
            },
        )

        # Test Azure-specific features
        azure_result = await sso_node.execute_async(
            action="initiate",
            provider="azure",
            redirect_uri="https://app.company.com/auth/azure/callback",
            prompt="select_account",
            domain_hint="company.com",
        )

        assert azure_result["success"] is True
        assert "tenant_id" in azure_result["auth_url"]

        # Test group membership retrieval
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.json = AsyncMock(
                return_value={
                    "value": [
                        {"displayName": "Engineering", "id": "group1"},
                        {"displayName": "Developers", "id": "group2"},
                    ]
                }
            )

            groups_result = await sso_node.execute_async(
                action="get_user_groups",
                provider="azure",
                access_token="azure_access_token",
            )

        assert groups_result["success"] is True
        assert len(groups_result["groups"]) == 2
        assert groups_result["groups"][0]["displayName"] == "Engineering"

        print("✅ Azure AD Integration test passed")

    @pytest.mark.asyncio
    async def test_google_workspace_integration(self):
        """Test Google Workspace integration."""
        print("\n🔷 Testing Google Workspace Integration...")

        sso_node = SSOAuthenticationNode(
            providers=["google"],
            google_settings={
                "client_id": "google_client.apps.googleusercontent.com",
                "client_secret": "google_secret",
                "hosted_domain": "company.com",  # Restrict to company domain
                "access_type": "offline",  # Get refresh token
                "scopes": [
                    "openid",
                    "email",
                    "profile",
                    "https://www.googleapis.com/auth/admin.directory.user.readonly",
                ],
            },
        )

        # Test Google-specific parameters
        google_result = await sso_node.execute_async(
            action="initiate",
            provider="google",
            redirect_uri="https://app.company.com/auth/google/callback",
            login_hint="user@company.com",
            include_granted_scopes=True,
        )

        assert google_result["success"] is True
        assert "hd=company.com" in google_result["auth_url"]
        assert "access_type=offline" in google_result["auth_url"]

        # Test domain verification
        verify_result = await sso_node.execute_async(
            action="verify_domain", provider="google", email="user@company.com"
        )

        assert verify_result["success"] is True
        assert verify_result["domain_verified"] is True

        print("✅ Google Workspace Integration test passed")

    @pytest.mark.asyncio
    async def test_okta_integration(self):
        """Test Okta integration."""
        print("\n🔶 Testing Okta Integration...")

        sso_node = SSOAuthenticationNode(
            providers=["okta"],
            okta_settings={
                "domain": "company.okta.com",
                "client_id": "okta_client_123",
                "client_secret": "okta_secret",
                "authorization_server_id": "default",
                "enable_mfa": True,
                "inline_hooks": ["password_import", "token_inline"],
            },
        )

        # Test Okta authorization
        okta_result = await sso_node.execute_async(
            action="initiate",
            provider="okta",
            redirect_uri="https://app.company.com/auth/okta/callback",
            session_token="okta_session_token",  # From Okta Authentication API
        )

        assert okta_result["success"] is True
        assert "company.okta.com" in okta_result["auth_url"]

        # Test Okta user profile enrichment
        profile_result = await sso_node.execute_async(
            action="get_user_profile",
            provider="okta",
            access_token="okta_access_token",
            include_custom_attributes=True,
        )

        assert profile_result["success"] is True
        assert "profile" in profile_result

        # Test Okta MFA challenge
        mfa_result = await sso_node.execute_async(
            action="mfa_challenge",
            provider="okta",
            factor_id="factor_123",
            state_token="state_token_456",
        )

        assert mfa_result["success"] is True
        assert "challenge" in mfa_result

        print("✅ Okta Integration test passed")


class TestSSOWorkflowIntegration:
    """Test SSO integration in complete workflows."""

    @pytest.mark.asyncio
    async def test_sso_with_jit_provisioning(self):
        """Test SSO with Just-In-Time (JIT) user provisioning."""
        print("\n⚡ Testing SSO with JIT Provisioning...")

        # Create workflow
        builder = WorkflowBuilder()

        # Add SSO authentication node
        sso_auth = builder.add_node(
            "SSOAuthenticationNode",
            node_id="sso_auth",
            config={"providers": ["saml"], "action": "authenticate"},
        )

        # Add user lookup node
        user_lookup = builder.add_node(
            "UserManagementNode",
            node_id="user_lookup",
            config={"operation": "find_by_email"},
        )

        # Add JIT provisioning node
        jit_provision = builder.add_node(
            "UserManagementNode",
            node_id="jit_provision",
            config={
                "operation": "create",
                "auto_assign_roles": True,
                "role_mapping": {
                    "Engineering": ["developer", "team_member"],
                    "Management": ["manager", "approver"],
                },
            },
        )

        # Add session creation
        create_session = builder.add_node(
            "SessionManagementNode",
            node_id="create_session",
            config={"max_sessions": 3, "track_devices": True},
        )

        # Add audit logging
        audit = builder.add_node(
            "AuditLogNode",
            node_id="audit",
            config={
                "action": "sso_login",
                "compliance_tags": ["authentication", "provisioning"],
            },
        )

        # Connect nodes with conditional routing
        builder.add_connection(sso_auth, "user_attributes", user_lookup, "email")
        builder.add_conditional_connection(
            user_lookup, "user_exists", {"true": create_session, "false": jit_provision}
        )
        builder.add_connection(jit_provision, "user_id", create_session, "user_id")
        builder.add_connection(create_session, "session", audit, "details")

        # Build and run workflow
        workflow = builder.build()
        runtime = LocalRuntime(enable_async=True)

        # Test with new user (JIT provisioning)
        result = await runtime.execute_async(
            workflow,
            initial_inputs={
                "saml_response": "encoded_saml_response",
                "user_attributes": {
                    "email": "new.user@company.com",
                    "name": "New User",
                    "groups": ["Engineering"],
                },
            },
        )

        assert result is not None
        assert "jit_provision" in result  # User was provisioned
        assert "create_session" in result
        assert "audit" in result

        print("✅ SSO with JIT Provisioning test passed")

    @pytest.mark.asyncio
    async def test_multi_provider_sso_fallback(self):
        """Test multi-provider SSO with fallback."""
        print("\n🔄 Testing Multi-Provider SSO Fallback...")

        # Create enterprise auth with multiple providers
        enterprise_auth = EnterpriseAuthProviderNode(
            enabled_methods=["sso"],
            sso_providers=["okta", "azure", "google"],
            fallback_enabled=True,
            fallback_order=["okta", "azure", "google", "directory"],
        )

        # Test primary provider failure with fallback
        result = await enterprise_auth.execute_async(
            action="authenticate",
            auth_method="sso",
            preferred_provider="okta",
            fallback_on_error=True,
            credentials={"sso_token": "invalid_token"},
            user_id="user@company.com",
        )

        # Should attempt fallback providers
        assert result["success"] is True
        assert "fallback_attempted" in result
        assert result["final_provider"] != "okta"  # Used fallback

        print("✅ Multi-Provider SSO Fallback test passed")

    @pytest.mark.asyncio
    async def test_sso_session_federation(self):
        """Test SSO session federation across multiple apps."""
        print("\n🌐 Testing SSO Session Federation...")

        sso_node = SSOAuthenticationNode(
            providers=["saml"],
            enable_federation=True,
            federation_settings={
                "session_store": "shared",
                "apps": ["app1", "app2", "app3"],
                "token_exchange_enabled": True,
            },
        )

        # Create federated session
        fed_result = await sso_node.execute_async(
            action="create_federated_session",
            provider="saml",
            user_attributes={"email": "user@company.com", "name": "Test User"},
            participating_apps=["app1", "app2"],
            session_duration=timedelta(hours=8),
        )

        assert fed_result["success"] is True
        assert "federation_token" in fed_result
        assert len(fed_result["app_tokens"]) == 2

        # Test cross-app token validation
        validate_result = await sso_node.execute_async(
            action="validate_federation_token",
            federation_token=fed_result["federation_token"],
            requesting_app="app2",
        )

        assert validate_result["success"] is True
        assert validate_result["valid"] is True
        assert validate_result["app_authorized"] is True

        # Test adding app to federation
        add_app_result = await sso_node.execute_async(
            action="add_app_to_federation",
            federation_token=fed_result["federation_token"],
            app_id="app3",
            user_consent=True,
        )

        assert add_app_result["success"] is True
        assert "app3" in add_app_result["participating_apps"]

        print("✅ SSO Session Federation test passed")

    @pytest.mark.asyncio
    async def test_sso_security_monitoring(self):
        """Test SSO security monitoring and anomaly detection."""
        print("\n🛡️ Testing SSO Security Monitoring...")

        # Create monitoring workflow
        builder = WorkflowBuilder()

        # Add nodes for security monitoring
        sso_auth = builder.add_node(
            "SSOAuthenticationNode",
            node_id="sso_auth",
            config={"providers": ["saml", "oauth2"]},
        )

        risk_assessment = builder.add_node(
            "ABACPermissionEvaluatorNode",
            node_id="risk_assessment",
            config={"ai_reasoning": True, "check_context": True},
        )

        threat_detection = builder.add_node(
            "ThreatDetectionNode",
            node_id="threat_detection",
            config={
                "detection_rules": ["impossible_travel", "unusual_provider"],
                "real_time": True,
            },
        )

        security_event = builder.add_node(
            "SecurityEventNode",
            node_id="security_event",
            config={"severity_threshold": "MEDIUM", "enable_alerting": True},
        )

        # Connect nodes
        builder.add_connection(sso_auth, "auth_context", risk_assessment, "context")
        builder.add_connection(
            risk_assessment, "risk_score", threat_detection, "risk_context"
        )
        builder.add_connection(
            threat_detection, "threats", security_event, "event_details"
        )

        # Build and test workflow
        workflow = builder.build()
        runtime = LocalRuntime(enable_async=True)

        # Test with suspicious login
        result = await runtime.execute(
            workflow,
            parameters={
                "provider": "oauth2",
                "user_id": "user@company.com",
                "auth_context": {
                    "ip_address": "185.220.101.50",  # Tor exit node
                    "location": "Russia",
                    "previous_location": "USA",
                    "time_since_last_login": 3600,  # 1 hour
                },
            },
        )

        assert result is not None
        assert "threat_detection" in result
        assert len(result["threat_detection"]["threats"]) > 0
        assert "security_event" in result

        print("✅ SSO Security Monitoring test passed")


async def run_all_tests():
    """Run all SSO integration tests."""
    print("🔐 Starting SSO Integration Test Suite")
    print("=" * 80)

    test_suites = [
        ("SAML Integration", TestSAMLIntegration()),
        ("OAuth2 Integration", TestOAuth2Integration()),
        ("Provider Integrations", TestProviderSpecificIntegrations()),
        ("Workflow Integration", TestSSOWorkflowIntegration()),
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    for suite_name, test_suite in test_suites:
        print(f"\n📦 Running {suite_name} Tests...")
        print("-" * 60)

        # Get all test methods
        test_methods = [
            method
            for method in dir(test_suite)
            if method.startswith("test_") and callable(getattr(test_suite, method))
        ]

        for test_name in test_methods:
            total_tests += 1
            try:
                test_method = getattr(test_suite, test_name)

                # Get fixtures if method has them
                if (
                    hasattr(test_method, "__code__")
                    and test_method.__code__.co_argcount > 1
                ):
                    # Method expects fixtures
                    if hasattr(test_suite, "mock_saml_response"):
                        fixture = test_suite.mock_saml_response()
                        await test_method(fixture)
                    elif hasattr(test_suite, "mock_oauth_tokens"):
                        fixture = test_suite.mock_oauth_tokens()
                        await test_method(fixture)
                else:
                    await test_method()

                passed_tests += 1
            except Exception as e:
                print(f"❌ {test_name} failed: {str(e)}")
                import traceback

                traceback.print_exc()
                failed_tests += 1

    # Print summary
    print("\n" + "=" * 80)
    print("📊 Test Summary:")
    print(f"   • Total tests: {total_tests}")
    print(f"   • Passed: {passed_tests} ✅")
    print(f"   • Failed: {failed_tests} ❌")
    print(f"   • Success rate: {(passed_tests/total_tests*100):.1f}%")

    if failed_tests == 0:
        print("\n🎉 All SSO integration tests passed successfully!")
        print("✅ SAML 2.0 integration validated")
        print("✅ OAuth 2.0 / OpenID Connect validated")
        print("✅ Azure AD integration validated")
        print("✅ Google Workspace integration validated")
        print("✅ Okta integration validated")
        print("✅ JIT provisioning validated")
        print("✅ Multi-provider fallback validated")
        print("✅ Session federation validated")
        return True
    else:
        print(f"\n⚠️ {failed_tests} tests failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.execute(run_all_tests())
    exit(0 if success else 1)
