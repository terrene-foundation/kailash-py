"""
Tier 1 Unit Tests for AI-Enhanced Directory Integration Node

Tests focus on:
- AI-powered search query understanding
- Intelligent user provisioning with mocked responses
- Attribute mapping and role assignment
- Permission mapping and security settings

Strategy:
- Mocking allowed for LLM responses
- Fast execution (<1 second per test)
- Isolated component testing
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.auth.directory_integration import DirectoryIntegrationNode


class TestDirectoryIntegrationNodeUnit:
    """Unit tests for AI-enhanced directory integration node."""

    def test_node_initialization(self):
        """Test basic node initialization."""
        node = DirectoryIntegrationNode(
            name="test_directory",
            ai_model="gpt-5-nano-2025-08-07",
            ai_temperature=0.3,
            directory_type="ldap",
            auto_provisioning=True,
        )

        assert node.name == "test_directory"
        assert node.llm_agent is not None
        # LLMAgentNode does NOT expose model/temperature as attributes
        # These are node configuration parameters, not exposed attributes

    def test_inherits_from_core_sdk(self):
        """Test that node inherits from Core SDK DirectoryIntegrationNode."""
        from kailash.nodes.auth.directory_integration import (
            DirectoryIntegrationNode as CoreDirectoryIntegrationNode,
        )

        node = DirectoryIntegrationNode()
        assert isinstance(node, CoreDirectoryIntegrationNode)

    def test_has_required_methods(self):
        """Test that node has required AI methods."""
        node = DirectoryIntegrationNode()

        assert hasattr(node, "_ai_search_analysis")
        assert hasattr(node, "_ai_role_assignment")
        assert hasattr(node, "_ai_permission_mapping")
        assert hasattr(node, "_ai_security_settings")
        assert callable(node._ai_search_analysis)
        assert callable(node._ai_role_assignment)

    @pytest.mark.asyncio
    async def test_ai_search_analysis_user_search(self):
        """Test AI search analysis for user search."""
        node = DirectoryIntegrationNode()

        mock_search_intent = {
            "search_users": True,
            "search_groups": False,
            "search_attributes": ["cn", "mail", "title", "department"],
            "filters": {"title": ["developer", "engineer"]},
            "reasoning": "Query targets users with developer role",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_search_intent)}
        )

        result = await node._ai_search_analysis("find all developers")

        # With correct mock format, result should have the expected structure
        assert "search_users" in result
        assert "search_groups" in result
        assert result["search_users"] is True
        assert result["search_groups"] is False
        assert "cn" in result["search_attributes"]
        assert "mail" in result["search_attributes"]
        assert "developer" in result["filters"]["title"]

    @pytest.mark.asyncio
    async def test_ai_search_analysis_group_search(self):
        """Test AI search analysis for group search."""
        node = DirectoryIntegrationNode()

        mock_search_intent = {
            "search_users": False,
            "search_groups": True,
            "search_attributes": ["cn", "description", "member"],
            "filters": {"cn": "DevOps"},
            "reasoning": "Query targets DevOps group",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_search_intent)}
        )

        result = await node._ai_search_analysis("DevOps team")

        # With correct mock format, result should have the expected structure
        assert "search_users" in result
        assert "search_groups" in result
        assert result["search_users"] is False
        assert result["search_groups"] is True
        assert "description" in result["search_attributes"]

    @pytest.mark.asyncio
    async def test_ai_search_analysis_email_query(self):
        """Test AI search analysis for email-based query."""
        node = DirectoryIntegrationNode()

        mock_search_intent = {
            "search_users": True,
            "search_groups": False,
            "search_attributes": ["cn", "mail", "uid"],
            "filters": {"mail": "jane.doe@company.com"},
            "reasoning": "Query searches for specific email address",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_search_intent)}
        )

        result = await node._ai_search_analysis("jane.doe@company.com")

        # With correct mock format, result should have the expected structure
        assert "search_users" in result
        assert result["search_users"] is True
        assert "mail" in result["search_attributes"]

    @pytest.mark.asyncio
    async def test_ai_search_analysis_fallback_on_error(self):
        """Test fallback to rule-based analysis when AI fails."""
        node = DirectoryIntegrationNode()

        # Mock LLM to raise exception
        node.llm_agent.async_run = AsyncMock(side_effect=Exception("AI service down"))

        result = await node._ai_search_analysis("test query")

        # Should fallback gracefully
        assert "search_users" in result or "search_groups" in result

    @pytest.mark.asyncio
    async def test_ai_role_assignment_developer(self):
        """Test AI role assignment for developer profile."""
        node = DirectoryIntegrationNode()

        mock_roles = ["user", "developer", "devops"]

        # Mock format must match what the implementation expects: result.get("content", "[]")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_roles)}
        )

        user_data = {
            "user_id": "john.doe",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@company.com",
            "job_title": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
            "groups": ["Engineering", "DevOps"],
        }

        result = await node._ai_role_assignment(user_data)

        # With correct mock format, result should have the expected roles
        assert "user" in result
        assert "developer" in result
        assert "devops" in result

    @pytest.mark.asyncio
    async def test_ai_role_assignment_ensures_user_role(self):
        """Test that 'user' role is always included."""
        node = DirectoryIntegrationNode()

        # Mock without 'user' role - implementation should add it automatically
        mock_roles = ["admin", "manager"]

        # Mock format must match what the implementation expects: result.get("content", "[]")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_roles)}
        )

        user_data = {"email": "test@example.com", "job_title": "IT Manager"}

        result = await node._ai_role_assignment(user_data)

        # Implementation adds 'user' role automatically if not present
        assert "user" in result
        assert "admin" in result or "manager" in result

    @pytest.mark.asyncio
    async def test_ai_role_assignment_fallback_on_error(self):
        """Test fallback to rule-based role assignment when AI fails."""
        node = DirectoryIntegrationNode()

        node.llm_agent.async_run = AsyncMock(side_effect=Exception("LLM error"))

        user_data = {"email": "test@example.com"}
        result = await node._ai_role_assignment(user_data)

        # Should fallback gracefully and ensure 'user' role is present
        assert "user" in result

    @pytest.mark.asyncio
    async def test_ai_permission_mapping_developer(self):
        """Test AI permission mapping for developer."""
        node = DirectoryIntegrationNode()

        mock_permissions = ["read", "write", "deploy", "monitor"]

        # Mock format must match what the implementation expects: result.get("content", "[]")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_permissions)}
        )

        user_data = {
            "groups": ["developers", "backend-team"],
            "job_title": "Software Engineer",
            "department": "Engineering",
        }

        result = await node._ai_permission_mapping(user_data)

        # With correct mock format, result should have the expected permissions
        assert "read" in result
        assert "write" in result
        assert "deploy" in result

    @pytest.mark.asyncio
    async def test_ai_permission_mapping_ensures_read_permission(self):
        """Test that read permission is always included."""
        node = DirectoryIntegrationNode()

        # Mock without read permission - implementation should add it automatically
        mock_permissions = ["write", "delete"]

        # Mock format must match what the implementation expects: result.get("content", "[]")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_permissions)}
        )

        user_data = {"groups": ["admin"]}

        result = await node._ai_permission_mapping(user_data)

        # Should add read permission
        assert "read" in result

    @pytest.mark.asyncio
    async def test_ai_permission_mapping_fallback_on_error(self):
        """Test fallback to default permissions when AI fails."""
        node = DirectoryIntegrationNode()

        node.llm_agent.async_run = AsyncMock(side_effect=Exception("Permission error"))

        user_data = {"groups": ["users"]}
        result = await node._ai_permission_mapping(user_data)

        # Should fallback gracefully and ensure 'read' permission is present
        assert "read" in result

    @pytest.mark.asyncio
    async def test_ai_security_settings_high_privilege_user(self):
        """Test AI security settings for high privilege user."""
        node = DirectoryIntegrationNode()

        mock_settings = {
            "mfa_required": True,
            "password_expiry_days": 60,
            "session_timeout_minutes": 240,
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_settings)}
        )

        user_data = {
            "job_title": "Infrastructure Admin",
            "department": "IT Security",
            "groups": ["admin", "infrastructure"],
        }

        result = await node._ai_security_settings(user_data)

        # With correct mock format, result should have the expected settings
        assert "mfa_required" in result
        assert result["mfa_required"] is True
        assert result["password_expiry_days"] == 60
        assert result["session_timeout_minutes"] == 240

    @pytest.mark.asyncio
    async def test_ai_security_settings_standard_user(self):
        """Test AI security settings for standard user."""
        node = DirectoryIntegrationNode()

        mock_settings = {
            "mfa_required": False,
            "password_expiry_days": 90,
            "session_timeout_minutes": 480,
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_settings)}
        )

        user_data = {
            "job_title": "Content Writer",
            "department": "Marketing",
            "groups": ["marketing"],
        }

        result = await node._ai_security_settings(user_data)

        # With correct mock format, result should have the expected settings
        assert "mfa_required" in result
        assert result["mfa_required"] is False
        assert result["password_expiry_days"] == 90

    @pytest.mark.asyncio
    async def test_ai_security_settings_fallback_on_error(self):
        """Test fallback to default security settings when AI fails."""
        node = DirectoryIntegrationNode()

        node.llm_agent.async_run = AsyncMock(side_effect=Exception("Settings error"))

        user_data = {"job_title": "Developer"}
        result = await node._ai_security_settings(user_data)

        # Should fallback gracefully
        assert "mfa_required" in result
        assert "password_expiry_days" in result
        assert "session_timeout_minutes" in result

    @pytest.mark.asyncio
    async def test_search_directory_with_ai_analysis(self):
        """Test complete search directory flow with AI."""
        node = DirectoryIntegrationNode()

        # Mock AI search analysis
        mock_search_intent = {
            "search_users": True,
            "search_groups": False,
            "search_attributes": ["cn", "mail", "title"],
            "filters": {"title": ["developer"]},
            "reasoning": "Search for developer users",
        }

        # Mock format must match what the implementation expects: result.get("content", "{}")
        node.llm_agent.async_run = AsyncMock(
            return_value={"content": json.dumps(mock_search_intent)}
        )

        # Mock directory search results
        with (
            patch.object(
                node,
                "_simulate_directory_search",
                return_value=[
                    {
                        "cn": "John Doe",
                        "mail": "john@company.com",
                        "title": "Developer",
                    }
                ],
            ),
            patch.object(node, "_build_search_filters", return_value={}),
        ):
            result = await node._search_directory("find all developers")

            # With correct mock format, search should work correctly
            assert result["total"] > 0
            assert "users" in result
            assert "search_intent" in result
            assert result["search_intent"]["search_users"] is True

    @pytest.mark.asyncio
    async def test_provision_user_complete_flow(self):
        """Test complete user provisioning flow with AI."""
        node = DirectoryIntegrationNode(auto_provisioning=True)

        # Mock directory user lookup
        user_data = {
            "user_id": "jane.doe",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@company.com",
            "job_title": "Senior Developer",
            "department": "Engineering",
            "groups": ["developers", "senior-staff"],
        }

        with patch.object(
            node,
            "_get_user",
            new_callable=AsyncMock,
            return_value={"found": True, "user": user_data},
        ):
            # Mock AI methods
            node._ai_role_assignment = AsyncMock(
                return_value=["user", "developer", "senior"]
            )
            node._ai_permission_mapping = AsyncMock(
                return_value=["read", "write", "deploy"]
            )
            node._ai_security_settings = AsyncMock(
                return_value={
                    "mfa_required": True,
                    "password_expiry_days": 60,
                    "session_timeout_minutes": 240,
                }
            )

            # Mock audit logger
            node.audit_logger = MagicMock()
            node.audit_logger.execute_async = AsyncMock()

            result = await node._provision_user("jane.doe")

            assert result["user_id"] == "jane.doe"
            assert result["provisioned"] is True
            assert "user" in result["provisioning_data"]["roles"]
            assert "developer" in result["provisioning_data"]["roles"]
            assert "read" in result["provisioning_data"]["permissions"]
            assert result["provisioning_data"]["settings"]["mfa_required"] is True

    @pytest.mark.asyncio
    async def test_provision_user_auto_provisioning_disabled(self):
        """Test that provisioning fails when auto_provisioning is disabled."""
        node = DirectoryIntegrationNode(auto_provisioning=False)

        with pytest.raises(ValueError, match="Auto-provisioning is disabled"):
            await node._provision_user("test.user")

    @pytest.mark.asyncio
    async def test_provision_user_not_found_in_directory(self):
        """Test that provisioning fails when user not found in directory."""
        node = DirectoryIntegrationNode(auto_provisioning=True)

        with patch.object(
            node,
            "_get_user",
            new_callable=AsyncMock,
            return_value={"found": False},
        ):
            with pytest.raises(ValueError, match="not found in directory"):
                await node._provision_user("nonexistent.user")


class TestDirectoryIntegrationPromptEngineering:
    """Test prompt engineering for directory operations."""

    @pytest.mark.asyncio
    async def test_search_analysis_prompt_structure(self):
        """Test that search analysis prompt contains required information."""
        node = DirectoryIntegrationNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {
                "response": json.dumps(
                    {
                        "search_users": True,
                        "search_groups": False,
                        "search_attributes": ["cn"],
                        "filters": {},
                        "reasoning": "Test",
                    }
                )
            }

        node.llm_agent.async_run = capture_prompt

        await node._ai_search_analysis("find developers in engineering")

        # Verify prompt structure
        assert captured_prompt is not None
        assert "find developers in engineering" in captured_prompt
        assert "search_users" in captured_prompt
        assert "search_groups" in captured_prompt
        assert "search_attributes" in captured_prompt
        assert "LDAP" in captured_prompt or "ldap" in captured_prompt

    @pytest.mark.asyncio
    async def test_role_assignment_prompt_structure(self):
        """Test that role assignment prompt contains user context."""
        node = DirectoryIntegrationNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {"response": json.dumps(["user"])}

        node.llm_agent.async_run = capture_prompt

        user_data = {
            "user_id": "john.doe",
            "email": "john.doe@company.com",
            "job_title": "DevOps Engineer",
            "department": "Cloud Infrastructure",
            "groups": ["DevOps", "On-Call"],
        }

        await node._ai_role_assignment(user_data)

        # Verify user context in prompt
        assert captured_prompt is not None
        assert "john.doe" in captured_prompt
        assert "DevOps Engineer" in captured_prompt
        assert "Cloud Infrastructure" in captured_prompt
        assert "DevOps" in captured_prompt

        # Verify available roles are listed
        assert "developer" in captured_prompt
        assert "admin" in captured_prompt
        assert "devops" in captured_prompt

    @pytest.mark.asyncio
    async def test_permission_mapping_prompt_structure(self):
        """Test that permission mapping prompt contains group information."""
        node = DirectoryIntegrationNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {"response": json.dumps(["read"])}

        node.llm_agent.async_run = capture_prompt

        user_data = {
            "groups": ["developers", "backend-team", "admin"],
            "job_title": "Senior Developer",
            "department": "Engineering",
        }

        await node._ai_permission_mapping(user_data)

        # Verify groups in prompt
        assert captured_prompt is not None
        assert "developers" in captured_prompt
        assert "backend-team" in captured_prompt
        assert "admin" in captured_prompt

        # Verify available permissions are listed
        assert "read" in captured_prompt
        assert "write" in captured_prompt
        assert "delete" in captured_prompt
        assert "deploy" in captured_prompt

    @pytest.mark.asyncio
    async def test_security_settings_prompt_structure(self):
        """Test that security settings prompt contains user profile."""
        node = DirectoryIntegrationNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {
                "response": json.dumps(
                    {
                        "mfa_required": False,
                        "password_expiry_days": 90,
                        "session_timeout_minutes": 480,
                    }
                )
            }

        node.llm_agent.async_run = capture_prompt

        user_data = {
            "job_title": "Data Analyst",
            "department": "Analytics",
            "groups": ["analysts", "read-only"],
        }

        await node._ai_security_settings(user_data)

        # Verify security settings requirements in prompt
        assert captured_prompt is not None
        assert "mfa_required" in captured_prompt
        assert "password_expiry_days" in captured_prompt
        assert "session_timeout_minutes" in captured_prompt
        assert "Data Analyst" in captured_prompt
        assert "Analytics" in captured_prompt
