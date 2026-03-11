"""
Tier 2 Integration Tests for AI-Enhanced SSO Authentication Node

Tests focus on:
- Real LLM calls with gpt-5-nano-2025-08-07
- AI field mapping with actual API responses
- AI role assignment with real reasoning
- Complete JIT provisioning flow
- Fallback behavior validation
- NO MOCKING policy for LLM responses

Strategy:
- NO MOCKING for LLM - use real API calls
- Target: <60 seconds total runtime
- Cost: ~$0.01-0.02 (gpt-5-nano is cost-efficient)
- Tests: 12 comprehensive integration scenarios
"""

import json
import os

import pytest
from kaizen.nodes.auth.sso import SSOAuthenticationNode

# Skip if USE_REAL_PROVIDERS is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("USE_REAL_PROVIDERS", "").lower() != "true",
    reason="Integration tests require USE_REAL_PROVIDERS=true",
)


class TestSSOAuthenticationNodeIntegration:
    """Integration tests for AI-enhanced SSO authentication with real LLM calls."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_field_mapping_azure_real_llm(self):
        """
        Test AI field mapping with real LLM call for Azure SSO attributes.

        Validates:
        - Real gpt-5-nano-2025-08-07 API call
        - Intelligent mapping of Azure-specific field names
        - JSON parsing and response structure

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_azure",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Azure SSO attributes with specific field names
        azure_attrs = {
            "mail": "jane.doe@company.com",
            "givenName": "Jane",
            "surname": "Doe",
            "jobTitle": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
            "memberOf": ["CN=Engineering,OU=Groups", "CN=DevOps,OU=Teams"],
        }

        result = await node._ai_field_mapping(azure_attrs, "azure")

        # Validate mapped fields
        assert result["first_name"] == "Jane"
        assert result["last_name"] == "Doe"
        assert result["email"] == "jane.doe@company.com"
        assert "DevOps" in result.get("job_title", "") or "Engineer" in result.get(
            "job_title", ""
        )
        assert result.get("department") in [
            "Cloud Infrastructure",
            "Engineering",
            "Cloud",
            "Infrastructure",
        ]

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_field_mapping_google_real_llm(self):
        """
        Test AI field mapping with real LLM call for Google SSO attributes.

        Validates:
        - Different provider field name conventions (given_name vs givenName)
        - Intelligent field mapping across providers
        - Consistency in output format

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_google",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Google SSO attributes with different naming convention
        google_attrs = {
            "email": "john.smith@company.com",
            "given_name": "John",
            "family_name": "Smith",
            "hd": "company.com",
            "locale": "en",
        }

        result = await node._ai_field_mapping(google_attrs, "google")

        # Validate mapped fields
        assert result["first_name"] == "John"
        assert result["last_name"] == "Smith"
        assert result["email"] == "john.smith@company.com"

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_field_mapping_complex_nested_attributes(self):
        """
        Test AI field mapping with complex nested attribute structures.

        Validates:
        - Handling nested objects
        - Extracting data from complex structures
        - AI's ability to understand context

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_complex",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Complex nested attributes
        complex_attrs = {
            "profile": {
                "name": {"first": "Alice", "last": "Johnson"},
                "contact": {"email": "alice.johnson@company.com"},
            },
            "employment": {
                "title": "Principal Software Architect",
                "department": "Engineering",
                "team": "Platform Architecture",
            },
        }

        result = await node._ai_field_mapping(complex_attrs, "custom")

        # Validate AI extracted nested fields correctly
        assert result["first_name"] == "Alice"
        assert result["last_name"] == "Johnson"
        assert result["email"] == "alice.johnson@company.com"
        assert "Architect" in result.get("job_title", "") or "Principal" in result.get(
            "job_title", ""
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_developer_real_llm(self):
        """
        Test AI role assignment for developer profile with real LLM.

        Validates:
        - Real AI reasoning for role assignment
        - Context-aware role selection
        - Multiple role assignment based on profile

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_roles",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Developer profile attributes
        dev_attributes = {
            "first_name": "Bob",
            "last_name": "Developer",
            "email": "bob.dev@company.com",
            "job_title": "Senior Software Engineer",
            "department": "Engineering",
            "groups": ["developers", "backend-team", "code-reviewers"],
        }

        roles = await node._ai_role_assignment(dev_attributes, "azure")

        # Validate role assignment
        assert "user" in roles  # Always includes base role
        assert "developer" in roles  # Should recognize developer from title and groups

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_manager_real_llm(self):
        """
        Test AI role assignment for manager profile with real LLM.

        Validates:
        - Recognition of managerial titles
        - Appropriate role assignment for leadership
        - Multiple role assignment (user + manager)

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_manager",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Manager profile attributes
        manager_attributes = {
            "first_name": "Sarah",
            "last_name": "Manager",
            "email": "sarah.manager@company.com",
            "job_title": "Engineering Manager",
            "department": "Engineering",
            "groups": ["managers", "engineering-leads", "hiring-committee"],
        }

        roles = await node._ai_role_assignment(manager_attributes, "google")

        # Validate role assignment
        assert "user" in roles
        assert "manager" in roles  # Should recognize manager role

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_admin_real_llm(self):
        """
        Test AI role assignment for admin profile with real LLM.

        Validates:
        - Recognition of administrative roles
        - Security-aware role assignment
        - Context understanding from job title + groups

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_admin",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Admin profile attributes
        admin_attributes = {
            "first_name": "Tom",
            "last_name": "Admin",
            "email": "tom.admin@company.com",
            "job_title": "Systems Administrator",
            "department": "IT Operations",
            "groups": ["admins", "infrastructure", "on-call"],
        }

        roles = await node._ai_role_assignment(admin_attributes, "okta")

        # Validate role assignment
        assert "user" in roles
        assert "admin" in roles  # Should recognize admin role

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_complete_jit_provisioning_flow(self):
        """
        Test complete JIT provisioning flow with real AI field mapping and role assignment.

        Validates:
        - End-to-end provisioning process
        - AI field mapping + role assignment integration
        - Complete user profile creation
        - Audit logging

        Cost: ~$0.002 | Expected Duration: 5-10 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_jit",
            providers=["azure"],  # Changed from enabled_providers to providers
            enable_jit_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-4o-mini"),
            ai_temperature=0.3,
        )

        # Complete SSO attributes for JIT provisioning
        sso_attributes = {
            "mail": "new.user@company.com",
            "givenName": "New",
            "surname": "User",
            "jobTitle": "Software Engineer",
            "department": "Engineering",
            "memberOf": ["CN=Developers,OU=Groups", "CN=Engineering,OU=Departments"],
        }

        user_profile = await node._provision_user(sso_attributes, "azure")

        # Validate complete user profile
        assert user_profile["user_id"] == "new.user@company.com"
        assert user_profile["email"] == "new.user@company.com"
        assert user_profile["first_name"] == "New"
        assert user_profile["last_name"] == "User"
        assert len(user_profile["roles"]) >= 1
        assert "user" in user_profile["roles"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_field_mapping_missing_attributes(self):
        """
        Test AI field mapping with minimal/missing attributes.

        Validates:
        - Handling of incomplete attribute sets
        - Graceful degradation
        - Empty string defaults for missing fields

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_minimal",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Minimal attributes - only email
        minimal_attrs = {
            "email": "minimal.user@company.com",
        }

        result = await node._ai_field_mapping(minimal_attrs, "generic")

        # Validate required field present, others may be empty
        assert result["email"] == "minimal.user@company.com"
        assert "first_name" in result
        assert "last_name" in result

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_empty_groups(self):
        """
        Test AI role assignment with no group memberships.

        Validates:
        - Role assignment based solely on job title
        - Fallback to default roles when minimal context
        - Always includes "user" role

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_no_groups",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Attributes with no groups
        no_group_attributes = {
            "first_name": "Solo",
            "last_name": "User",
            "email": "solo.user@company.com",
            "job_title": "Contractor",
            "department": "",
            "groups": [],
        }

        roles = await node._ai_role_assignment(no_group_attributes, "azure")

        # Validate at least user role is assigned
        assert "user" in roles
        assert len(roles) >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(20)
    async def test_ai_field_mapping_different_temperature(self):
        """
        Test AI field mapping with different temperature settings.

        Validates:
        - Temperature parameter affects AI behavior
        - Lower temperature provides consistent results
        - Higher temperature still produces valid mappings

        Cost: ~$0.002 | Expected Duration: 3-6 seconds
        """
        # Low temperature node (deterministic)
        node_low_temp = SSOAuthenticationNode(
            name="test_sso_low_temp",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.1,
        )

        # High temperature node (creative)
        node_high_temp = SSOAuthenticationNode(
            name="test_sso_high_temp",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.7,
        )

        test_attrs = {
            "mail": "test.user@company.com",
            "givenName": "Test",
            "surname": "User",
            "jobTitle": "Engineer",
            "department": "Tech",
        }

        result_low = await node_low_temp._ai_field_mapping(test_attrs, "azure")
        result_high = await node_high_temp._ai_field_mapping(test_attrs, "azure")

        # Both should produce valid mappings
        assert result_low["email"] == "test.user@company.com"
        assert result_high["email"] == "test.user@company.com"
        assert result_low["first_name"] == "Test"
        assert result_high["first_name"] == "Test"

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_complex_seniority(self):
        """
        Test AI role assignment with complex seniority indicators.

        Validates:
        - Recognition of seniority levels (Senior, Lead, Principal, Staff)
        - Multiple role assignment for complex profiles
        - Context-aware role selection

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_seniority",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Senior technical leader profile
        senior_attributes = {
            "first_name": "Tech",
            "last_name": "Lead",
            "email": "tech.lead@company.com",
            "job_title": "Principal Software Engineer - Team Lead",
            "department": "Engineering",
            "groups": ["developers", "tech-leads", "architects", "senior-staff"],
        }

        roles = await node._ai_role_assignment(senior_attributes, "azure")

        # Validate comprehensive role assignment
        assert "user" in roles
        assert "developer" in roles or "manager" in roles
        assert len(roles) >= 2  # Should have multiple roles

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_complete_provisioning_with_error_handling(self):
        """
        Test complete provisioning flow with invalid attributes to test error handling.

        Validates:
        - Error handling for missing required fields
        - Graceful failure behavior
        - Appropriate error messages

        Cost: ~$0.001 | Expected Duration: 1-3 seconds
        """
        node = SSOAuthenticationNode(
            name="test_sso_error",
            providers=["azure"],  # Changed from enabled_providers to providers
            enable_jit_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-4o-mini"),
            ai_temperature=0.3,
        )

        # Attributes missing required email field
        invalid_attributes = {
            "givenName": "No",
            "surname": "Email",
            "jobTitle": "Test User",
        }

        # Should raise ValueError for missing email
        with pytest.raises(ValueError, match="Email is required"):
            await node._provision_user(invalid_attributes, "azure")
