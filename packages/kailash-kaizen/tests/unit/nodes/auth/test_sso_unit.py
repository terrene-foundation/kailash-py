"""
Tier 1 Unit Tests for AI-Enhanced SSO Authentication Node

Tests focus on:
- Individual AI method functionality with mocked LLM responses
- Fallback behavior when AI fails
- Parameter validation
- Inheritance from Core SDK node

Strategy:
- Mocking allowed for LLM responses
- Fast execution (<1 second per test)
- Isolated component testing
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kaizen.nodes.auth.sso import SSOAuthenticationNode


class TestSSOAuthenticationNodeUnit:
    """Unit tests for AI-enhanced SSO authentication node."""

    def test_node_initialization(self):
        """Test basic node initialization."""
        node = SSOAuthenticationNode(
            name="test_sso",
            ai_model="gpt-5-nano-2025-08-07",
            ai_temperature=0.3,
        )

        assert node.name == "test_sso"
        assert node.llm_agent is not None
        # LLMAgentNode does NOT expose model/temperature as attributes
        # These are node configuration parameters, not exposed attributes

    def test_inherits_from_core_sdk(self):
        """Test that node inherits from Core SDK SSOAuthenticationNode."""
        from kailash.nodes.auth.sso import SSOAuthenticationNode as CoreSSONode

        node = SSOAuthenticationNode()
        assert isinstance(node, CoreSSONode)

    def test_has_required_methods(self):
        """Test that node has required AI methods."""
        node = SSOAuthenticationNode()

        assert hasattr(node, "_ai_field_mapping")
        assert hasattr(node, "_ai_role_assignment")
        assert hasattr(node, "_provision_user")
        assert callable(node._ai_field_mapping)
        assert callable(node._ai_role_assignment)

    @pytest.mark.asyncio
    async def test_ai_field_mapping_success(self):
        """Test successful AI field mapping with mocked LLM response."""
        node = SSOAuthenticationNode()

        # Mock LLM response
        mock_mapped_data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@company.com",
            "department": "Engineering",
            "job_title": "Senior Software Engineer",
            "groups": ["developers", "backend-team"],
        }

        node.llm_agent.async_run = AsyncMock(
            return_value={"response": {"content": json.dumps(mock_mapped_data)}}
        )

        # Test Azure SSO attributes
        azure_attrs = {
            "mail": "jane.doe@company.com",
            "givenName": "Jane",
            "surname": "Doe",
            "jobTitle": "Senior Software Engineer",
            "department": "Engineering",
        }

        result = await node._ai_field_mapping(azure_attrs, "azure")

        assert result["first_name"] == "Jane"
        assert result["last_name"] == "Doe"
        assert result["email"] == "jane.doe@company.com"
        assert result["department"] == "Engineering"
        assert result["job_title"] == "Senior Software Engineer"

        # Verify LLM was called
        node.llm_agent.async_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_ai_field_mapping_fallback_on_error(self):
        """Test fallback to rule-based mapping when AI fails."""
        node = SSOAuthenticationNode()

        # Mock LLM to raise exception
        node.llm_agent.async_run = AsyncMock(side_effect=Exception("LLM API error"))

        attrs = {"email": "john.smith@company.com"}
        result = await node._ai_field_mapping(attrs, "google")

        # Should fallback gracefully
        # The implementation should handle errors without crashing
        assert "email" in result

    @pytest.mark.asyncio
    async def test_ai_field_mapping_handles_invalid_json(self):
        """Test handling of invalid JSON from LLM."""
        node = SSOAuthenticationNode()

        # Mock LLM to return invalid JSON
        node.llm_agent.async_run = AsyncMock(
            return_value={"response": "This is not valid JSON"}
        )

        attrs = {"email": "test@example.com"}
        result = await node._ai_field_mapping(attrs, "okta")

        # Should use fallback gracefully
        assert "email" in result

    @pytest.mark.asyncio
    async def test_ai_role_assignment_success(self):
        """Test successful AI role assignment."""
        node = SSOAuthenticationNode()

        # Mock LLM response - SSO expects {"roles": [...]} format
        # The implementation uses: response_data.get("roles", ["user"])
        mock_roles = {"roles": ["user", "developer", "manager"]}
        node.llm_agent.async_run = AsyncMock(
            return_value={"response": {"content": json.dumps(mock_roles)}}
        )

        attributes = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@company.com",
            "job_title": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
            "groups": ["engineering", "devops"],
        }

        result = await node._ai_role_assignment(attributes, "azure")

        # With correct mock format, result should have the expected roles
        assert "user" in result
        assert "developer" in result
        assert "manager" in result
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_ai_role_assignment_ensures_user_role(self):
        """Test that 'user' role is always included."""
        node = SSOAuthenticationNode()

        # Mock LLM response without 'user' role - SSO expects {"roles": [...]} format
        # The implementation uses: response_data.get("roles", ["user"])
        mock_roles = {"roles": ["developer", "admin"]}
        node.llm_agent.async_run = AsyncMock(
            return_value={"response": {"content": json.dumps(mock_roles)}}
        )

        attributes = {
            "email": "test@example.com",
            "job_title": "Developer",
        }

        result = await node._ai_role_assignment(attributes, "google")

        # Implementation adds 'user' role automatically if not present
        assert "user" in result
        assert "developer" in result

    @pytest.mark.asyncio
    async def test_ai_role_assignment_fallback_on_error(self):
        """Test fallback to rule-based role assignment when AI fails."""
        node = SSOAuthenticationNode()

        # Mock LLM to raise exception
        node.llm_agent.async_run = AsyncMock(side_effect=Exception("AI service down"))

        attributes = {"email": "test@example.com"}
        result = await node._ai_role_assignment(attributes, "okta")

        # Should fallback gracefully and ensure 'user' role is present
        assert "user" in result

    @pytest.mark.asyncio
    async def test_provision_user_complete_flow(self):
        """Test complete user provisioning flow with AI."""
        node = SSOAuthenticationNode()

        # Mock AI field mapping
        mock_mapped = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@company.com",
            "department": "Engineering",
            "job_title": "Software Engineer",
        }

        # Mock AI role assignment
        mock_roles = ["user", "developer"]

        node._ai_field_mapping = AsyncMock(return_value=mock_mapped)
        node._ai_role_assignment = AsyncMock(return_value=mock_roles)

        # Mock audit logger - the implementation uses execute(), not async_run()
        node.audit_logger = MagicMock()
        node.audit_logger.execute = MagicMock()

        attributes = {
            "email": "john.doe@company.com",
            "givenName": "John",
            "surname": "Doe",
        }

        result = await node._provision_user(attributes, "azure")

        # Verify profile structure
        assert result["user_id"] == "john.doe@company.com"
        assert result["email"] == "john.doe@company.com"
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"
        assert result["department"] == "Engineering"
        assert result["job_title"] == "Software Engineer"
        assert result["roles"] == ["user", "developer"]

        # Verify AI methods were called
        node._ai_field_mapping.assert_called_once_with(attributes, "azure")
        node._ai_role_assignment.assert_called_once_with(mock_mapped, "azure")

        # Verify audit logging - the implementation uses execute(), not async_run()
        node.audit_logger.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_provision_user_missing_email(self):
        """Test that provisioning fails without email."""
        node = SSOAuthenticationNode()

        attributes = {"givenName": "John", "surname": "Doe"}

        with pytest.raises(ValueError, match="Email is required"):
            await node._provision_user(attributes, "azure")

    @pytest.mark.asyncio
    async def test_provision_user_uses_mail_field(self):
        """Test that provisioning works with 'mail' field instead of 'email'."""
        node = SSOAuthenticationNode()

        # Mock AI methods
        node._ai_field_mapping = AsyncMock(
            return_value={
                "first_name": "Jane",
                "last_name": "Smith",
                "email": "jane.smith@company.com",
            }
        )
        node._ai_role_assignment = AsyncMock(return_value=["user"])
        node.audit_logger = MagicMock()
        node.audit_logger.async_run = AsyncMock()

        # Use 'mail' instead of 'email'
        attributes = {
            "mail": "jane.smith@company.com",
            "givenName": "Jane",
            "surname": "Smith",
        }

        result = await node._provision_user(attributes, "azure")

        assert result["email"] == "jane.smith@company.com"
        assert result["user_id"] == "jane.smith@company.com"

    @pytest.mark.asyncio
    async def test_ai_methods_with_various_providers(self):
        """Test that AI methods work with different SSO providers."""
        node = SSOAuthenticationNode()

        providers = ["azure", "google", "okta", "auth0", "ping"]

        for provider in providers:
            # Mock LLM response
            node.llm_agent.async_run = AsyncMock(
                return_value={
                    "response": json.dumps(
                        {
                            "first_name": "Test",
                            "last_name": "User",
                            "email": f"test@{provider}.com",
                        }
                    )
                }
            )

            attrs = {"email": f"test@{provider}.com"}
            result = await node._ai_field_mapping(attrs, provider)

            assert result["email"] == f"test@{provider}.com"

    def test_node_parameter_validation(self):
        """Test parameter validation for node initialization."""
        # Valid initialization with various temperatures
        node1 = SSOAuthenticationNode(ai_temperature=0.0)
        assert node1.llm_agent is not None

        node2 = SSOAuthenticationNode(ai_temperature=1.0)
        assert node2.llm_agent is not None

        # Temperature outside typical range (should still work but may not be optimal)
        node3 = SSOAuthenticationNode(ai_temperature=0.5)
        assert node3.llm_agent is not None


class TestSSOAuthenticationPromptEngineering:
    """Test prompt engineering and LLM interaction patterns."""

    @pytest.mark.asyncio
    async def test_field_mapping_prompt_structure(self):
        """Test that field mapping prompt contains required information."""
        node = SSOAuthenticationNode()

        # Capture the prompt sent to LLM
        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {"response": json.dumps({"email": "test@test.com"})}

        node.llm_agent.async_run = capture_prompt

        attrs = {
            "mail": "test@example.com",
            "givenName": "Test",
            "jobTitle": "Engineer",
        }

        await node._ai_field_mapping(attrs, "azure")

        # Verify prompt structure
        assert captured_prompt is not None
        assert "azure" in captured_prompt.lower()
        assert "first_name" in captured_prompt
        assert "last_name" in captured_prompt
        assert "email" in captured_prompt
        assert json.dumps(attrs, indent=2) in captured_prompt

    @pytest.mark.asyncio
    async def test_role_assignment_prompt_structure(self):
        """Test that role assignment prompt contains required information."""
        node = SSOAuthenticationNode()

        captured_prompt = None

        async def capture_prompt(**kwargs):
            nonlocal captured_prompt
            # Extract prompt from messages array

            messages = kwargs.get("messages", [])

            captured_prompt = messages[0]["content"] if messages else ""
            return {"response": json.dumps(["user"])}

        node.llm_agent.async_run = capture_prompt

        attrs = {
            "first_name": "Jane",
            "email": "jane@example.com",
            "job_title": "Senior DevOps Engineer",
            "department": "Cloud Infrastructure",
        }

        await node._ai_role_assignment(attrs, "azure")

        # Verify prompt contains user context
        assert captured_prompt is not None
        assert "Jane" in captured_prompt
        assert "jane@example.com" in captured_prompt
        assert "Senior DevOps Engineer" in captured_prompt
        assert "Cloud Infrastructure" in captured_prompt

        # Verify available roles are listed
        assert "user" in captured_prompt
        assert "developer" in captured_prompt
        assert "admin" in captured_prompt
        assert "manager" in captured_prompt
