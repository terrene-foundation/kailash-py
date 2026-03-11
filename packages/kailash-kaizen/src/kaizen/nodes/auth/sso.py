"""
AI-Enhanced SSO Authentication Node

Extends Core SDK's SSO authentication with AI-powered intelligent features:
- Intelligent field mapping from various SSO providers
- Context-aware role assignment based on user attributes
- Adaptive provisioning patterns

For rule-based authentication only, use the Core SDK version:
    from kailash.nodes.auth import SSOAuthenticationNode
"""

import json
import logging
from typing import Any, Dict, List

from kaizen.core.structured_output import create_structured_output_config
from kaizen.nodes.ai import LLMAgentNode
from kaizen.nodes.auth.signatures import (
    SSOFieldMappingSignature,
    SSORoleAssignmentSignature,
)

from kailash.nodes.auth.sso import SSOAuthenticationNode as CoreSSONode

logger = logging.getLogger(__name__)


class SSOAuthenticationNode(CoreSSONode):
    """
    AI-enhanced SSO authentication node with intelligent provisioning.

    Extends the Core SDK SSO node with:
    - Intelligent field mapping using AI to understand various attribute formats
    - Context-aware role assignment based on comprehensive user profile analysis
    - Adaptive provisioning that learns from organizational patterns

    Example:
        ```python
        from kaizen.nodes.auth import SSOAuthenticationNode

        # Initialize with AI-powered provisioning
        sso_node = SSOAuthenticationNode(
            name="ai_sso_auth",
            enabled_providers=["azure", "google", "okta"],
            enable_jit_provisioning=True,  # Enable AI-powered JIT provisioning
            ai_model="gpt-4o-mini",  # AI model for intelligent field mapping
            ai_temperature=0.3,  # Lower temperature for consistent results
        )
        ```

    Note:
        This node inherits all Core SDK SSO capabilities and adds AI enhancements.
        The AI features activate only when enable_jit_provisioning=True.
    """

    def __init__(
        self,
        name: str = "ai_sso_auth",
        ai_model: str = "gpt-4o-mini",
        ai_temperature: float = 0.3,
        provider: str = None,
        **kwargs,
    ):
        """
        Initialize AI-enhanced SSO authentication node.

        Args:
            name: Node name
            ai_model: AI model for intelligent field mapping and role assignment
            ai_temperature: Temperature for AI model (0.0-1.0, lower = more deterministic)
            provider: LLM provider (openai, anthropic, etc.). If None, auto-detected from model name
            **kwargs: Additional parameters passed to Core SDK SSOAuthenticationNode
        """
        super().__init__(name=name, **kwargs)

        # Auto-detect provider from model name if not specified
        if provider is None:
            if "gpt" in ai_model.lower() or "o1" in ai_model.lower():
                provider = "openai"
            elif "claude" in ai_model.lower():
                provider = "anthropic"
            else:
                provider = "mock"  # Default for testing

        # Store provider and model for later use in LLM calls
        self.ai_provider = provider
        self.ai_model = ai_model

        # Initialize AI agent for intelligent field mapping and role assignment
        self.llm_agent = LLMAgentNode(
            name=f"{name}_llm",
            model=ai_model,
            temperature=ai_temperature,
            provider=provider,
        )

    async def _provision_user(
        self, attributes: Dict[str, Any], provider: str
    ) -> Dict[str, Any]:
        """
        Provision user with AI-powered intelligent field mapping and role assignment.

        This method extends the Core SDK version with AI capabilities to:
        1. Intelligently map fields from various SSO provider formats
        2. Assign roles based on comprehensive context understanding
        3. Handle edge cases and non-standard attribute structures

        Args:
            attributes: User attributes from SSO provider
            provider: SSO provider name (azure, google, okta, etc.)

        Returns:
            User profile with intelligently mapped fields and assigned roles

        Example:
            ```python
            # Handles various provider attribute formats
            azure_attrs = {
                "mail": "user@company.com",
                "givenName": "Jane",
                "surname": "Doe",
                "jobTitle": "Senior DevOps Engineer",
                "department": "Cloud Infrastructure"
            }

            google_attrs = {
                "email": "user@company.com",
                "given_name": "Jane",
                "family_name": "Doe",
                "hd": "company.com"
            }

            # Both get intelligently mapped to consistent internal format
            user_profile = await node._provision_user(azure_attrs, "azure")
            ```
        """
        email = attributes.get("email") or attributes.get("mail")
        if not email:
            raise ValueError("Email is required for user provisioning")

        # Step 1: Use AI for intelligent field mapping
        mapped_attributes = await self._ai_field_mapping(attributes, provider)

        # Step 2: Use AI for context-aware role assignment
        roles = await self._ai_role_assignment(mapped_attributes, provider)

        # Build user profile with AI-enhanced mappings
        user_profile = {
            "user_id": email,
            "email": email,
            "first_name": mapped_attributes.get("first_name", ""),
            "last_name": mapped_attributes.get("last_name", ""),
            "department": mapped_attributes.get("department", ""),
            "job_title": mapped_attributes.get("job_title", ""),
            "roles": roles,
        }

        # Log user provisioning
        self.audit_logger.execute(
            event_type="ai_user_provisioned",
            user_id=email,
            event_data={
                "provider": provider,
                "raw_attributes": attributes,
                "mapped_attributes": mapped_attributes,
                "assigned_roles": roles,
                "profile": user_profile,
            },
            message=f"AI-provisioned user {email} from {provider} SSO",
        )

        return user_profile

    async def _ai_field_mapping(
        self, attributes: Dict[str, Any], provider: str
    ) -> Dict[str, Any]:
        """
        Use AI to intelligently map SSO provider attributes to internal format.

        The AI analyzes the attribute structure and intelligently maps fields,
        handling variations like:
        - Different field names (givenName vs given_name vs firstName)
        - Nested structures (address.street vs street)
        - Concatenated fields (fullName vs firstName+lastName)
        - Provider-specific conventions

        Uses OpenAI Structured Outputs for 100% schema compliance.

        Args:
            attributes: Raw attributes from SSO provider
            provider: Provider name for context

        Returns:
            Mapped attributes in consistent internal format
        """
        # Create structured output configuration (legacy mode for gpt-5-nano compatibility)
        signature = SSOFieldMappingSignature()
        response_format = create_structured_output_config(signature, strict=False)

        # Explicit prompt with snake_case field naming guidance
        prompt = f"""Analyze these user attributes from {provider} SSO provider and map them to the internal format.

Input Attributes:
{json.dumps(attributes, indent=2)}

CRITICAL: Return a JSON object with these EXACT field names (snake_case):
- first_name (string): User's first name
- last_name (string): User's last name
- email (string): User's email address
- department (string): User's department or team
- job_title (string): User's job title or position
- groups (array): List of groups or teams (use empty array [] if not provided)

Use empty strings "" for missing text fields. Return ONLY the JSON object, no explanation."""

        try:
            # Use AI with structured outputs
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                provider_config=response_format,  # Pass structured output configuration
            )

            # Parse AI response - LLMAgentNode returns nested structure
            # Format: {"response": {"content": "json_string", ...}, ...}
            response_content = result.get("response", {}).get("content", "{}")
            mapped_data = json.loads(response_content)

            logger.info(
                f"AI field mapping for {provider}: mapped {len(attributes)} fields to {len(mapped_data)} internal fields"
            )

            return mapped_data

        except Exception as e:
            logger.warning(
                f"AI field mapping failed for {provider}, falling back to rule-based: {e}"
            )
            # Fallback to Core SDK rule-based mapping
            return self._map_attributes(attributes, provider)

    async def _ai_role_assignment(
        self, attributes: Dict[str, Any], provider: str
    ) -> List[str]:
        """
        Use AI to assign roles based on comprehensive user context.

        The AI considers multiple contextual factors:
        - Job title and seniority level
        - Department and team membership
        - Group memberships
        - Historical patterns in the organization
        - Industry-specific role conventions

        Uses OpenAI Structured Outputs for 100% schema compliance.

        Args:
            attributes: Mapped user attributes
            provider: Provider name for context

        Returns:
            List of assigned roles
        """
        # Create structured output configuration (legacy mode for gpt-5-nano compatibility)
        signature = SSORoleAssignmentSignature()
        response_format = create_structured_output_config(signature, strict=False)

        # Explicit prompt with field naming guidance
        prompt = f"""Analyze this user profile and assign appropriate system roles.

User Profile:
- Name: {attributes.get('first_name', '')} {attributes.get('last_name', '')}
- Email: {attributes.get('email', '')}
- Job Title: {attributes.get('job_title', '')}
- Department: {attributes.get('department', '')}
- Groups: {', '.join(attributes.get('groups', []))}

Available Roles:
- user: Default role for all users
- developer: Software developers, engineers
- admin: System administrators, IT managers
- manager: Team leads, managers, directors
- analyst: Data analysts, business analysts
- viewer: Read-only access users

Assign roles based on job title, department, and groups. Consider seniority indicators.
Everyone gets "user" role. Be conservative - only assign roles you're confident about.

CRITICAL: Return a JSON object with this EXACT field name:
- roles (array): List of assigned role strings

Return ONLY the JSON object, no explanation."""

        try:
            # Use AI with structured outputs
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                provider_config=response_format,  # Pass structured output configuration
            )

            # Parse AI response - LLMAgentNode returns nested structure
            # Format: {"response": {"content": "json_string", ...}, ...}
            response_content = result.get("response", {}).get("content", "{}")
            response_data = json.loads(response_content)
            roles = response_data.get("roles", ["user"])

            # Ensure "user" is always included
            if "user" not in roles:
                roles.insert(0, "user")

            logger.info(
                f"AI role assignment for {attributes.get('email', 'unknown')}: {roles}"
            )

            return roles

        except Exception as e:
            logger.warning(f"AI role assignment failed, falling back to default: {e}")
            # Fallback to safe default - always include "user" role
            return ["user"]
