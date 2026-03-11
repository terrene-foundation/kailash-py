"""
AI-Enhanced Directory Integration Node

Extends Core SDK's directory integration with AI-powered intelligent features:
- Intelligent search query understanding and analysis
- Advanced user provisioning with contextual role assignment
- Smart attribute mapping from various directory formats

For rule-based directory integration only, use the Core SDK version:
    from kailash.nodes.auth import DirectoryIntegrationNode
"""

import json
import logging
from typing import Any, Dict, List

from kaizen.nodes.ai import LLMAgentNode

from kailash.nodes.auth.directory_integration import (
    DirectoryIntegrationNode as CoreDirectoryIntegrationNode,
)

logger = logging.getLogger(__name__)


class DirectoryIntegrationNode(CoreDirectoryIntegrationNode):
    """
    AI-enhanced directory integration node with intelligent search and provisioning.

    Extends the Core SDK directory integration with:
    - AI-powered search query understanding (natural language to LDAP filters)
    - Intelligent user provisioning with contextual role assignment
    - Smart attribute mapping handling various directory formats
    - Advanced search intent analysis

    Example:
        ```python
        from kaizen.nodes.auth import DirectoryIntegrationNode

        # Initialize with AI-powered features
        directory = DirectoryIntegrationNode(
            name="ai_directory",
            directory_type="ldap",
            auto_provisioning=True,  # Enable AI-powered provisioning
            ai_model="gpt-4o-mini",  # AI model for intelligent analysis
            ai_temperature=0.3,  # Higher temperature for creative search
        )
        ```

    Note:
        This node inherits all Core SDK directory capabilities and adds AI enhancements.
        The AI features activate when processing natural language queries or provisioning users.
    """

    def __init__(
        self,
        name: str = "ai_directory",
        ai_model: str = "gpt-4o-mini",
        ai_temperature: float = 0.3,
        provider: str = None,
        **kwargs,
    ):
        """
        Initialize AI-enhanced directory integration node.

        Args:
            name: Node name
            ai_model: AI model for intelligent search and provisioning
            ai_temperature: Temperature for AI model (0.0-1.0, higher = more creative)
            provider: LLM provider (openai, anthropic, etc.). If None, auto-detected from model name
            **kwargs: Additional parameters passed to Core SDK DirectoryIntegrationNode
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

        # Initialize AI agent for intelligent search and provisioning
        self.llm_agent = LLMAgentNode(
            name=f"{name}_llm",
            model=ai_model,
            temperature=ai_temperature,
            provider=provider,
        )

    async def _search_directory(
        self,
        query: str,
        filters: Dict[str, Any] = None,
        attributes: List[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Search directory with AI-powered query understanding.

        This method extends the Core SDK version with AI capabilities to:
        1. Understand natural language search queries
        2. Convert complex queries into appropriate directory filters
        3. Intelligently determine search scope (users, groups, or both)
        4. Optimize search attributes based on query intent

        Args:
            query: Natural language or structured search query
            filters: Additional structured filters
            attributes: Specific attributes to retrieve
            **kwargs: Additional search parameters

        Returns:
            Search results with users and groups

        Example:
            ```python
            # Natural language queries work intelligently:

            # Find users by role
            result = await node._search_directory(
                "find all developers in the engineering department"
            )

            # Complex queries with multiple conditions
            result = await node._search_directory(
                "show me managers who have admin access and work in finance"
            )

            # Email-based search
            result = await node._search_directory("jane.doe@company.com")

            # Group membership queries
            result = await node._search_directory(
                "list all users in the DevOps team"
            )
            ```
        """
        search_results = {"users": [], "groups": [], "total": 0}

        # Use AI to analyze search intent
        search_intent = await self._ai_search_analysis(query, filters)

        # Build search filters combining AI insights and provided filters
        search_filters = self._build_search_filters(query, search_intent, filters)
        search_filters["search_term"] = query

        # Search users
        if search_intent.get("search_users", True):
            users = await self._simulate_directory_search(
                "users", search_filters, attributes
            )
            search_results["users"] = users

        # Search groups
        if search_intent.get("search_groups", False):
            groups = await self._simulate_directory_search(
                "groups", search_filters, attributes
            )
            search_results["groups"] = [self._map_directory_group(g) for g in groups]

        search_results["total"] = len(search_results["users"]) + len(
            search_results["groups"]
        )
        search_results["query"] = query
        search_results["search_intent"] = search_intent
        search_results["entries"] = search_results["users"] + search_results["groups"]

        return search_results

    async def _ai_search_analysis(
        self, query: str, filters: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Use AI to analyze search query and determine optimal search strategy.

        The AI analyzes natural language queries to understand:
        - Search targets (users, groups, or both)
        - Relevant attributes to search
        - Filter conditions to apply
        - Search optimization strategies

        Args:
            query: Search query (natural language or structured)
            filters: Additional provided filters

        Returns:
            Search intent with targets, attributes, and filter suggestions

        Example:
            ```python
            # Query: "find developers in engineering with admin access"
            search_intent = await node._ai_search_analysis(
                "find developers in engineering with admin access"
            )
            # Returns:
            # {
            #   "search_users": True,
            #   "search_groups": False,
            #   "search_attributes": ["cn", "mail", "title", "department", "memberOf"],
            #   "filters": {
            #     "title": ["developer", "engineer"],
            #     "department": "engineering",
            #     "groups": ["admin", "administrator"]
            #   },
            #   "reasoning": "Query targets users with developer role in engineering department"
            # }
            ```
        """
        prompt = f"""Analyze this directory search query and determine the optimal search strategy.

Query: "{query}"

Additional Context:
{f"Provided filters: {json.dumps(filters, indent=2)}" if filters else "No additional filters"}

Determine:
1. search_users: Should we search for users? (boolean)
2. search_groups: Should we search for groups? (boolean)
3. search_attributes: Which LDAP attributes should we search? (list)
   Available attributes:
   - Basic: cn, uid, mail, displayName, sAMAccountName
   - User: givenName, sn, title, department, telephoneNumber
   - Group: ou, description, memberOf, member
4. filters: What filter conditions should be applied? (dict)
   Examples: {{"department": "engineering", "title": ["developer", "engineer"]}}
5. reasoning: Brief explanation of the search strategy (string)

Search Query Intent Examples:
- "john.doe@company.com" → Search users by email attribute
- "find all developers" → Search users where title contains "developer"
- "show managers in finance" → Search users where title="manager" AND department="finance"
- "DevOps team" → Search groups where cn="DevOps"
- "users with admin access" → Search users where memberOf contains "admin"

Return ONLY a JSON object with these fields. No explanation outside the JSON.

Example output:
{{
  "search_users": true,
  "search_groups": false,
  "search_attributes": ["cn", "mail", "title", "department", "memberOf"],
  "filters": {{
    "title": ["developer", "engineer"],
    "department": "engineering"
  }},
  "reasoning": "Query targets users with developer/engineer titles in engineering department"
}}
"""

        try:
            # Use AI to analyze search intent
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,  # OpenAI API compatibility: use max_completion_tokens for gpt-5-nano models
            )

            # Parse AI response - extract content from LLM response
            # Format: {"content": "json_string", "role": "assistant", ...}
            response_content = result.get("content", "{}")
            search_intent = json.loads(response_content)

            logger.info(
                f"AI search analysis for '{query}': "
                f"users={search_intent.get('search_users')}, "
                f"groups={search_intent.get('search_groups')}, "
                f"attributes={len(search_intent.get('search_attributes', []))}"
            )

            return search_intent

        except Exception as e:
            logger.warning(
                f"AI search analysis failed for '{query}', falling back to default: {e}"
            )
            # Fallback to safe default - search for users with basic attributes
            return {
                "search_users": True,
                "search_groups": False,
                "search_attributes": ["cn", "mail", "uid"],
                "filters": {},
                "reasoning": "Using default search configuration due to AI failure",
            }

    async def _provision_user(
        self, user_id: str, attributes: List[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """
        Provision user with AI-powered intelligent role assignment.

        This method extends the Core SDK version with AI capabilities to:
        1. Analyze user profile comprehensively (job title, department, groups, attributes)
        2. Assign roles based on contextual understanding
        3. Determine appropriate permissions intelligently
        4. Configure security settings based on user context

        Args:
            user_id: User identifier
            attributes: Specific attributes to retrieve
            **kwargs: Additional provisioning parameters

        Returns:
            Provisioning result with AI-enhanced role assignments

        Example:
            ```python
            # AI analyzes complete user context for intelligent provisioning
            result = await node._provision_user("john.doe@company.com")

            # User profile:
            # - Job Title: "Senior DevOps Engineer"
            # - Department: "Cloud Infrastructure"
            # - Groups: ["Engineering", "DevOps", "On-Call-Rotation"]

            # AI assigns roles:
            # - user (default)
            # - developer (from job title)
            # - engineer (from department + title)
            # - on_call (from groups)

            # And determines security settings:
            # - mfa_required: True (on-call + infrastructure access)
            # - session_timeout: 240 minutes (shorter for privileged access)
            # - password_expiry: 60 days (shorter for infrastructure team)
            ```
        """
        if not self.auto_provisioning:
            raise ValueError("Auto-provisioning is disabled")

        # Get user from directory
        user_result = await self._get_user(user_id, attributes)

        if not user_result.get("found"):
            raise ValueError(f"User {user_id} not found in directory")

        user_data = user_result["user"]

        # Use AI for intelligent role assignment
        roles = await self._ai_role_assignment(user_data)

        # Use AI for intelligent permission mapping
        permissions = await self._ai_permission_mapping(user_data)

        # Use AI for security settings determination
        security_settings = await self._ai_security_settings(user_data)

        # Build provisioning data
        provisioning_data = {
            "user_id": user_id,
            "roles": roles,
            "permissions": permissions,
            "settings": security_settings,
            "status": "active",
        }

        # Log user provisioning with AI metadata
        await self.audit_logger.execute_async(
            action="ai_user_provisioned_from_directory",
            user_id=user_id,
            details={
                "directory_type": self.directory_type,
                "directory_data": user_data,
                "provisioning_data": provisioning_data,
                "ai_enhanced": True,
            },
        )

        return {
            "user_id": user_id,
            "provisioned": True,
            "user_data": user_data,
            "provisioning_data": provisioning_data,
        }

    async def _ai_role_assignment(self, user_data: Dict[str, Any]) -> List[str]:
        """
        Use AI to assign roles based on comprehensive user context.

        The AI analyzes multiple contextual factors:
        - Job title and seniority indicators
        - Department and organizational structure
        - Group memberships and teams
        - Combined signals from all attributes

        Args:
            user_data: User attributes from directory

        Returns:
            List of assigned roles
        """
        prompt = f"""Analyze this user profile from directory and assign appropriate system roles.

User Profile:
- User ID: {user_data.get('user_id', '')}
- Name: {user_data.get('first_name', '')} {user_data.get('last_name', '')}
- Email: {user_data.get('email', '')}
- Job Title: {user_data.get('job_title', '')}
- Department: {user_data.get('department', '')}
- Groups: {', '.join(user_data.get('groups', []))}

Available Roles:
- user: Default role for all users (ALWAYS include)
- developer: Software developers, engineers, programmers
- admin: System administrators, IT managers, infrastructure team
- manager: Team leads, managers, directors, VPs
- analyst: Data analysts, business analysts, researchers
- viewer: Read-only access users, contractors, temporary staff
- devops: DevOps engineers, SRE, cloud infrastructure
- security: Security team, InfoSec, compliance officers
- support: Customer support, help desk, technical support

Role Assignment Rules:
1. ALWAYS include "user" as base role
2. Assign roles based on job title keywords (developer, engineer, manager, etc.)
3. Consider seniority indicators (Senior, Lead, Principal, Staff)
4. Analyze group memberships for team-specific roles
5. Be comprehensive but conservative - only assign roles you're confident about
6. Multiple roles are expected for complex profiles

Return ONLY a JSON array of role strings. No explanation needed.

Example output:
["user", "developer", "devops", "manager"]
"""

        try:
            # Use AI to assign roles
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,  # OpenAI API compatibility: use max_completion_tokens for gpt-5-nano models
            )

            # Parse AI response - extract content from LLM response
            # Format: {"content": "json_string", "role": "assistant", ...}
            response_content = result.get("content", "[]")
            roles = json.loads(response_content)

            # Ensure "user" is always included
            if "user" not in roles:
                roles.insert(0, "user")

            logger.info(
                f"AI role assignment for {user_data.get('email', 'unknown')}: {roles}"
            )

            return roles

        except Exception as e:
            logger.warning(f"AI role assignment failed, falling back to default: {e}")
            # Fallback to safe default - always include "user" role
            return ["user"]

    async def _ai_permission_mapping(self, user_data: Dict[str, Any]) -> List[str]:
        """
        Use AI to map directory groups to system permissions.

        Args:
            user_data: User attributes from directory

        Returns:
            List of permissions
        """
        prompt = f"""Map directory groups to system permissions for this user.

User Groups: {', '.join(user_data.get('groups', []))}
Job Title: {user_data.get('job_title', '')}
Department: {user_data.get('department', '')}

Available Permissions:
- read: Read access to resources
- write: Write/modify access
- delete: Delete access
- admin: Administrative operations
- deploy: Deployment operations
- monitor: Monitoring and observability
- audit: Audit log access

Permission Mapping Guidelines:
1. Base permissions on group memberships
2. Consider job title for additional context
3. Security groups (admin, security) get broader permissions
4. Developer groups get read, write, deploy, monitor
5. Manager roles get read, admin, audit
6. Support roles get read, monitor

Return ONLY a JSON array of permission strings.

Example output:
["read", "write", "deploy", "monitor"]
"""

        try:
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,  # OpenAI API compatibility: use max_completion_tokens for gpt-5-nano models
            )

            # Parse AI response - extract content from LLM response
            # Format: {"content": "json_string", "role": "assistant", ...}
            response_content = result.get("content", "[]")
            permissions = json.loads(response_content)

            # Ensure basic read permission
            if "read" not in permissions:
                permissions.insert(0, "read")

            return permissions

        except Exception as e:
            logger.warning(f"AI permission mapping failed, using defaults: {e}")
            # Fallback to safe default - read-only permission
            return ["read"]

    async def _ai_security_settings(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use AI to determine security settings based on user context.

        Args:
            user_data: User attributes from directory

        Returns:
            Security settings configuration
        """
        prompt = f"""Determine appropriate security settings for this user.

User Profile:
- Job Title: {user_data.get('job_title', '')}
- Department: {user_data.get('department', '')}
- Groups: {', '.join(user_data.get('groups', []))}

Security Settings to Determine:
1. mfa_required: Should MFA be mandatory? (boolean)
   - True for: admin, manager, infrastructure, security, finance roles
   - False for: standard users, contractors, viewers
2. password_expiry_days: Password expiration period (int: 30, 60, 90, 180)
   - 30-60 days: High privilege users (admin, security, infrastructure)
   - 90 days: Standard users
   - 180 days: Read-only, contractors
3. session_timeout_minutes: Session timeout (int: 60, 240, 480, 1440)
   - 60-240 minutes: High privilege users
   - 480 minutes: Standard users (8 hours)
   - 1440 minutes: Low privilege users (24 hours)

Return ONLY a JSON object with these three fields.

Example output:
{{
  "mfa_required": true,
  "password_expiry_days": 60,
  "session_timeout_minutes": 240
}}
"""

        try:
            result = await self.llm_agent.async_run(
                provider=self.ai_provider,
                model=self.ai_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=2000,  # OpenAI API compatibility: use max_completion_tokens for gpt-5-nano models
            )

            # Parse AI response - extract content from LLM response
            # Format: {"content": "json_string", "role": "assistant", ...}
            response_content = result.get("content", "{}")
            settings = json.loads(response_content)

            return settings

        except Exception as e:
            logger.warning(f"AI security settings failed, using defaults: {e}")
            # Fallback to safe defaults
            return {
                "mfa_required": False,
                "password_expiry_days": 90,
                "session_timeout_minutes": 480,
            }
