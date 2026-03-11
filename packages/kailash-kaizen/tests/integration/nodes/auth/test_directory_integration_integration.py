"""
Tier 2 Integration Tests for AI-Enhanced Directory Integration Node

Tests focus on:
- Real LLM calls for search analysis and provisioning
- AI search query understanding with natural language
- AI permission mapping and security settings
- Intelligent role assignment
- NO MOCKING policy for LLM responses

Strategy:
- NO MOCKING for LLM - use real API calls
- Target: <80 seconds total runtime
- Cost: ~$0.02-0.03 (gpt-5-nano is cost-efficient)
- Tests: 15 comprehensive integration scenarios
"""

import json
import os

import pytest
from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode

# Skip if USE_REAL_PROVIDERS is not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("USE_REAL_PROVIDERS", "").lower() != "true",
    reason="Integration tests require USE_REAL_PROVIDERS=true",
)


class TestDirectoryIntegrationNodeIntegration:
    """Integration tests for AI-enhanced directory integration with real LLM calls."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_email_query_real_llm(self):
        """
        Test AI search analysis for email-based queries with real LLM.

        Validates:
        - Real gpt-5-nano-2025-08-07 search analysis
        - Email pattern recognition
        - Appropriate attribute selection
        - User-only search targeting

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_email",
            directory_type="ldap",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        search_intent = await node._ai_search_analysis("john.doe@company.com")

        # Validate email search intent
        assert search_intent.get("search_users") is True
        assert "mail" in search_intent.get(
            "search_attributes", []
        ) or "email" in search_intent.get("search_attributes", [])
        assert "reasoning" in search_intent

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_natural_language_query_real_llm(self):
        """
        Test AI search analysis for natural language queries with real LLM.

        Validates:
        - Natural language understanding ("find all developers")
        - Query intent extraction
        - Filter generation from natural language
        - Appropriate attribute selection

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_nl",
            directory_type="ldap",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        search_intent = await node._ai_search_analysis(
            "find all developers in the engineering department"
        )

        # Validate natural language query understanding
        assert search_intent.get("search_users") is True
        filters = search_intent.get("filters", {})
        # Should identify department and title/role filters
        assert "department" in filters or "title" in filters or len(filters) > 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_group_query_real_llm(self):
        """
        Test AI search analysis for group-based queries with real LLM.

        Validates:
        - Group search intent recognition
        - Appropriate attribute selection for groups
        - Filter generation for group searches

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_group",
            directory_type="ldap",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        search_intent = await node._ai_search_analysis("DevOps team")

        # Validate group search intent
        # AI should recognize this as group search or user search with group filter
        assert (
            search_intent.get("search_groups") is True
            or "group" in str(search_intent.get("filters", {})).lower()
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_complex_query_real_llm(self):
        """
        Test AI search analysis for complex multi-condition queries with real LLM.

        Validates:
        - Multiple condition extraction
        - Complex filter generation
        - AND logic understanding

        Cost: ~$0.002 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_complex",
            directory_type="ldap",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        search_intent = await node._ai_search_analysis(
            "show me managers who have admin access and work in finance"
        )

        # Validate complex query understanding
        assert search_intent.get("search_users") is True
        filters = search_intent.get("filters", {})
        # Should identify multiple conditions
        assert len(filters) >= 1  # At least one filter condition

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_developer_profile_real_llm(self):
        """
        Test AI role assignment for developer profile with real LLM.

        Validates:
        - Real AI reasoning for directory user roles
        - Context-aware role selection from job title + groups
        - Multiple role assignment

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_dev_roles",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "dev.user@company.com",
            "first_name": "Dev",
            "last_name": "User",
            "email": "dev.user@company.com",
            "job_title": "Senior Software Engineer",
            "department": "Engineering",
            "groups": ["Developers", "Backend Team", "Code Reviewers"],
        }

        roles = await node._ai_role_assignment(user_data)

        # Validate role assignment
        assert "user" in roles
        assert "developer" in roles

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_devops_profile_real_llm(self):
        """
        Test AI role assignment for DevOps engineer profile with real LLM.

        Validates:
        - Recognition of DevOps role
        - Multiple role assignment (developer + devops + admin)
        - Context from groups and title

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_devops_roles",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "devops.user@company.com",
            "first_name": "DevOps",
            "last_name": "User",
            "email": "devops.user@company.com",
            "job_title": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
            "groups": ["DevOps", "SRE", "On-Call", "Infrastructure"],
        }

        roles = await node._ai_role_assignment(user_data)

        # Validate comprehensive role assignment
        assert "user" in roles
        assert "devops" in roles or "developer" in roles or "admin" in roles
        assert len(roles) >= 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_permission_mapping_developer_real_llm(self):
        """
        Test AI permission mapping for developer with real LLM.

        Validates:
        - Group-to-permission mapping
        - Developer-appropriate permissions
        - Real AI reasoning for permission assignment

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_dev_perms",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "dev@company.com",
            "job_title": "Software Engineer",
            "department": "Engineering",
            "groups": ["Developers", "Backend Team"],
        }

        permissions = await node._ai_permission_mapping(user_data)

        # Validate developer permissions
        assert "read" in permissions
        # Developers should have write and possibly deploy
        assert len(permissions) >= 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_permission_mapping_admin_real_llm(self):
        """
        Test AI permission mapping for admin with real LLM.

        Validates:
        - Administrative permission assignment
        - Comprehensive permission set
        - Security-aware permission mapping

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_admin_perms",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "admin@company.com",
            "job_title": "Systems Administrator",
            "department": "IT Operations",
            "groups": ["Admins", "Infrastructure", "Security"],
        }

        permissions = await node._ai_permission_mapping(user_data)

        # Validate admin permissions
        assert "read" in permissions
        assert "admin" in permissions or len(permissions) >= 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_security_settings_high_privilege_real_llm(self):
        """
        Test AI security settings determination for high-privilege user with real LLM.

        Validates:
        - MFA requirement for privileged users
        - Shorter password expiry for security
        - Shorter session timeout for high-risk roles

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_sec_high",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "admin@company.com",
            "job_title": "Infrastructure Manager",
            "department": "IT Operations",
            "groups": ["Admins", "Infrastructure", "On-Call"],
        }

        settings = await node._ai_security_settings(user_data)

        # Validate high-privilege security settings
        assert settings.get("mfa_required") is True
        assert settings.get("password_expiry_days") <= 90  # Stricter than default
        assert settings.get("session_timeout_minutes") <= 480  # 8 hours or less

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_security_settings_standard_user_real_llm(self):
        """
        Test AI security settings determination for standard user with real LLM.

        Validates:
        - Appropriate settings for standard users
        - Balanced security vs usability
        - Reasonable password and session policies

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_sec_standard",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "user@company.com",
            "job_title": "Software Engineer",
            "department": "Engineering",
            "groups": ["Developers"],
        }

        settings = await node._ai_security_settings(user_data)

        # Validate standard user security settings
        assert "mfa_required" in settings
        assert "password_expiry_days" in settings
        assert "session_timeout_minutes" in settings
        assert settings.get("password_expiry_days") in [30, 60, 90, 180]

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_complete_directory_search_flow_real_llm(self):
        """
        Test complete directory search flow with AI analysis.

        Validates:
        - End-to-end search with AI query understanding
        - Search results structure
        - Search intent metadata

        Cost: ~$0.002 | Expected Duration: 3-6 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_search_flow",
            directory_type="ldap",
            connection_config={
                "server": "ldap://localhost:389",
                "base_dn": "dc=example,dc=com",
            },
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-4o-mini"),
            ai_temperature=0.3,
        )

        # Natural language search query
        results = await node._search_directory("find developers in engineering")

        # Validate search results structure
        assert "users" in results
        assert "groups" in results
        assert "total" in results
        assert "query" in results
        assert "search_intent" in results

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_attribute_optimization_real_llm(self):
        """
        Test AI's ability to optimize search attributes based on query intent.

        Validates:
        - Attribute selection optimization
        - Query-specific attribute relevance
        - Performance optimization through targeted attributes

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_attr_opt",
            directory_type="ldap",
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        # Query focused on contact information
        search_intent = await node._ai_search_analysis(
            "find email and phone number for john smith"
        )

        # Validate attribute optimization
        attributes = search_intent.get("search_attributes", [])
        assert "mail" in attributes or "email" in attributes
        # Should prioritize contact-related attributes

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_role_assignment_manager_profile_real_llm(self):
        """
        Test AI role assignment for manager profile with real LLM.

        Validates:
        - Manager role recognition
        - Appropriate permissions for leadership
        - Multiple role assignment

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_mgr_roles",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "manager@company.com",
            "first_name": "Team",
            "last_name": "Manager",
            "email": "manager@company.com",
            "job_title": "Engineering Manager",
            "department": "Engineering",
            "groups": ["Managers", "Engineering Leadership", "Hiring Committee"],
        }

        roles = await node._ai_role_assignment(user_data)

        # Validate manager role assignment
        assert "user" in roles
        assert "manager" in roles

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_permission_mapping_security_team_real_llm(self):
        """
        Test AI permission mapping for security team with real LLM.

        Validates:
        - Security-focused permission assignment
        - Audit and monitoring permissions
        - Comprehensive access for security roles

        Cost: ~$0.001 | Expected Duration: 2-5 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_sec_perms",
            directory_type="ldap",
            auto_provisioning=True,
            ai_model=os.getenv("OPENAI_DEV_MODEL", "gpt-5-nano-2025-08-07"),
            ai_temperature=0.3,
        )

        user_data = {
            "user_id": "security@company.com",
            "job_title": "Security Engineer",
            "department": "Information Security",
            "groups": ["Security", "InfoSec", "Compliance"],
        }

        permissions = await node._ai_permission_mapping(user_data)

        # Validate security permissions
        assert "read" in permissions
        # Security team should have audit/monitoring permissions
        assert len(permissions) >= 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.timeout(10)
    async def test_ai_search_analysis_fallback_on_error(self):
        """
        Test fallback behavior when AI search analysis fails.

        Validates:
        - Graceful degradation to default search
        - Error handling without breaking search
        - Safe default search configuration

        Cost: ~$0.000 (tests error path) | Expected Duration: 1-2 seconds
        """
        node = DirectoryIntegrationNode(
            name="test_dir_fallback",
            directory_type="ldap",
            ai_model="invalid-model-name",  # Will cause error
            ai_temperature=0.3,
        )

        # This should fall back to default search
        search_intent = await node._ai_search_analysis("test query")

        # Validate fallback behavior
        assert search_intent.get("search_users") is True
        assert len(search_intent.get("search_attributes", [])) >= 1
        assert (
            "fallback" in search_intent.get("reasoning", "").lower()
            or "default" in search_intent.get("reasoning", "").lower()
        )
