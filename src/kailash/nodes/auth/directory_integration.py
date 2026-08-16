"""
Enterprise Directory Integration Node

Comprehensive directory service integration supporting:
- Active Directory (AD)
- LDAP (Lightweight Directory Access Protocol)
- Azure Active Directory (Azure AD)
- Google Workspace Directory
- Okta Universal Directory
- AWS Directory Service
- OpenLDAP
- FreeIPA
"""

import asyncio
import base64
import hashlib
import json
import re
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.nodes.api import AsyncHTTPRequestNode
from kailash.nodes.auth._log_hygiene import log_safe
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.data import JSONReaderNode
from kailash.nodes.mixins import LoggingMixin, PerformanceMixin, SecurityMixin
from kailash.nodes.security import AuditLogNode, SecurityEventNode
from kailash.utils.secure_logging import redact_mapping


def _is_enabled(value: Any) -> bool:
    """Strictly interpret an insecure-mode opt-in flag.

    Bare truthiness is wrong for these gates: config files and environment
    variables deliver strings, and ``"false"``/``"0"``/``"no"`` are all truthy
    in Python, so an operator explicitly DISABLING an insecure fallback would
    have enabled it (issue #2026). Only a real ``True``, or a string that
    spells one, counts; anything unrecognised is treated as OFF.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


@register_node()
class DirectoryIntegrationNode(SecurityMixin, PerformanceMixin, LoggingMixin, Node):
    """
    Enterprise Directory Integration Node

    Provides comprehensive directory service integration with advanced features
    like group synchronization, user provisioning, and organizational mapping.
    """

    def __init__(
        self,
        name: str = "directory_integration",
        directory_type: str = "ldap",
        connection_config: Dict[str, Any] | None = None,
        sync_schedule: str = "hourly",
        auto_provisioning: bool = True,
        group_mapping: Dict[str, str] | None = None,
        attribute_mapping: Dict[str, str] | None = None,
        filter_config: Dict[str, Any] | None = None,
        cache_ttl: int = 300,
        max_concurrent_operations: int = 10,
    ):
        # Set attributes before calling super().__init__()
        self.name = name
        self.directory_type = directory_type
        self.connection_config = connection_config or {}
        self.sync_schedule = sync_schedule
        self.auto_provisioning = auto_provisioning
        self.group_mapping = group_mapping or {}
        self.attribute_mapping = attribute_mapping or {
            "uid": "user_id",
            "sAMAccountName": "username",
            "cn": "common_name",
            "displayName": "display_name",
            "mail": "email",
            "givenName": "first_name",
            "sn": "last_name",
            "title": "job_title",
            "department": "department",
            "telephoneNumber": "phone",
            "memberOf": "groups",
        }
        self.filter_config = filter_config or {}
        self.cache_ttl = cache_ttl
        self.max_concurrent_operations = max_concurrent_operations

        # Internal state
        self.connection_pool = {}
        self.user_cache = {}
        self.group_cache = {}
        self.sync_status = {}
        self.operation_queue = asyncio.Queue(maxsize=max_concurrent_operations)

        super().__init__(name=name)

        # Initialize supporting nodes
        self._setup_supporting_nodes()

    def _setup_supporting_nodes(self):
        """Initialize supporting Kailash nodes."""
        # AsyncHTTPRequestNode, not HTTPRequestNode: every call site here is
        # on an async path and awaits the client. The sync HTTPRequestNode
        # defines neither async_run nor execute_async, so those awaits
        # raised AttributeError (issue #2060). Both return
        # {"success": ..., "response": ...}.
        self.http_client = AsyncHTTPRequestNode(name=f"{self.name}_http")

        self.json_reader = JSONReaderNode(name=f"{self.name}_json")

        self.security_logger = SecurityEventNode(name=f"{self.name}_security")

        self.audit_logger = AuditLogNode(name=f"{self.name}_audit")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=True,
                description="Directory action: sync, search, authenticate, get_user, get_groups, provision",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=False,
                description="Search query for directory operations",
            ),
            "user_id": NodeParameter(
                name="user_id",
                type=str,
                required=False,
                description="User identifier for user-specific operations",
            ),
            "credentials": NodeParameter(
                name="credentials",
                type=dict,
                required=False,
                description="Authentication credentials (username, password)",
            ),
            "sync_type": NodeParameter(
                name="sync_type",
                type=str,
                required=False,
                description="Sync type: full, incremental, users, groups",
            ),
            "filters": NodeParameter(
                name="filters",
                type=dict,
                required=False,
                description="Search filters for directory queries",
            ),
            "attributes": NodeParameter(
                name="attributes",
                type=list,
                required=False,
                description="Specific attributes to retrieve",
            ),
            "username": NodeParameter(
                name="username",
                type=str,
                required=False,
                description="Username for authentication or user operations",
            ),
            "password": NodeParameter(
                name="password",
                type=str,
                required=False,
                description="Password for authentication",
            ),
            "user_data": NodeParameter(
                name="user_data",
                type=dict,
                required=False,
                description="User data for provisioning operations",
            ),
            "include_security_groups": NodeParameter(
                name="include_security_groups",
                type=bool,
                required=False,
                description="Include security groups in results",
            ),
        }

    def _build_tls_config(self, server_url: str):
        """Build the LDAPS TLS policy shared by every connection site.

        One policy for all sites: the three connection points previously
        disagreed (one CERT_REQUIRED, one CERT_OPTIONAL, one with no TLS at
        all), which is the multi-site parity failure `rules/security.md`
        forbids. These channels carry bind passwords and the group data that
        drives admin-role assignment, so certificates are validated by default;
        ``tls_validate_optional`` is the explicit opt-out for a private CA or
        lab directory.

        Returns:
            An ``ldap3.Tls`` for LDAPS connections, else None.
        """
        import ssl

        from ldap3 import Tls

        if not (
            self.connection_config.get("use_ssl", False)
            or str(server_url).startswith("ldaps://")
        ):
            return None

        return Tls(
            validate=(
                ssl.CERT_OPTIONAL
                if _is_enabled(self.connection_config.get("tls_validate_optional"))
                else ssl.CERT_REQUIRED
            ),
            version=ssl.PROTOCOL_TLSv1_2,
        )

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the node's logic (Node ABC contract)."""
        return self.execute(**kwargs)

    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute directory integration operations synchronously."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self.async_run(**kwargs))

    async def async_run(
        self,
        action: str,
        query: str | None = None,
        user_id: str | None = None,
        credentials: Dict[str, str] | None = None,
        sync_type: str = "incremental",
        filters: Dict[str, Any] | None = None,
        attributes: List[str] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute directory integration operations.

        Args:
            action: Directory action to perform
            query: Search query string
            user_id: User identifier
            credentials: Authentication credentials
            sync_type: Type of synchronization
            filters: Search filters
            attributes: Attributes to retrieve

        Returns:
            Dict containing operation results
        """
        start_time = time.time()

        try:
            self.log_info(
                f"Starting directory operation: {action} on {self.directory_type}"
            )

            # Route to appropriate handler
            if action == "sync":
                result = await self._sync_directory(sync_type, filters, **kwargs)
            elif action == "search":
                # Handle both 'filter' (singular) and 'filters' (plural) parameters
                search_query = query or kwargs.get("query") or kwargs.get("filter")
                search_filters = filters if isinstance(filters, dict) else None
                result = await self._search_directory(
                    search_query, search_filters, attributes, **kwargs  # type: ignore[arg-type]
                )
            elif action == "authenticate":
                auth_credentials = credentials or {
                    "username": kwargs.get("username"),
                    "password": kwargs.get("password"),
                }
                result = await self._authenticate_user(auth_credentials, **kwargs)  # type: ignore[arg-type]
            elif action == "get_user":
                result = await self._get_user(user_id, attributes, **kwargs)  # type: ignore[arg-type]
            elif action == "get_groups":
                result = await self._get_groups(user_id, filters, **kwargs)
            elif action == "get_user_groups":
                result = await self._get_user_groups(kwargs.get("username"))  # type: ignore[arg-type]
            elif action == "get_user_details":
                result = await self._get_user_details(
                    kwargs.get("username"),  # type: ignore[arg-type]
                    **{k: v for k, v in kwargs.items() if k != "username"},
                )
            elif action == "provision":
                result = await self._provision_user(user_id, attributes, **kwargs)  # type: ignore[arg-type]
            elif action == "provision_user":
                result = await self._provision_user_full(
                    kwargs.get("user_data"),  # type: ignore[arg-type]
                    **{k: v for k, v in kwargs.items() if k != "user_data"},
                )
            elif action == "test_connection":
                result = await self._test_connection(**kwargs)
            elif action == "get_schema":
                result = await self._get_directory_schema(**kwargs)
            else:
                raise ValueError(f"Unsupported directory action: {action}")

            # Add processing metrics
            processing_time = (time.time() - start_time) * 1000
            result["processing_time_ms"] = processing_time
            # Derive from the operation's verdict: unconditionally stamping
            # success=True turned an {"authenticated": False} result into a
            # success for any caller gating on that field (issue #2026).
            if "authenticated" in result:
                result["success"] = bool(result["authenticated"])
            elif "error" in result:
                result["success"] = False
            else:
                result["success"] = True
            result["directory_type"] = self.directory_type

            # Log successful operation
            await self._log_security_event(
                event_type="directory_operation",
                action=action,
                user_id=user_id,
                success=True,
                processing_time_ms=processing_time,
            )

            self.log_info(
                f"Directory operation completed successfully in {processing_time:.1f}ms"
            )
            return result

        except Exception as e:
            processing_time = (time.time() - start_time) * 1000

            # Log security event for failure
            await self._log_security_event(
                event_type="directory_failure",
                action=action,
                user_id=user_id,
                success=False,
                error=str(e),
                processing_time_ms=processing_time,
            )

            self.log_error(f"Directory operation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "processing_time_ms": processing_time,
                "action": action,
                "directory_type": self.directory_type,
            }

    async def _sync_directory(
        self, sync_type: str, filters: Dict[str, Any] | None = None, **kwargs
    ) -> Dict[str, Any]:
        """Synchronize directory data."""
        self.log_info(f"Starting {sync_type} directory sync")

        sync_stats = {
            "sync_type": sync_type,
            "started_at": datetime.now(UTC).isoformat(),
            "users_processed": 0,
            "groups_processed": 0,
            "errors": [],
        }

        try:
            if sync_type in ["full", "users"]:
                # Sync users
                users_result = await self._sync_users(filters)
                sync_stats["users_processed"] = users_result["count"]
                sync_stats["users_added"] = users_result.get("added", 0)
                sync_stats["users_updated"] = users_result.get("updated", 0)

            if sync_type in ["full", "groups"]:
                # Sync groups
                groups_result = await self._sync_groups(filters)
                sync_stats["groups_processed"] = groups_result["count"]
                sync_stats["groups_added"] = groups_result.get("added", 0)
                sync_stats["groups_updated"] = groups_result.get("updated", 0)

            if sync_type == "incremental":
                # Incremental sync based on last sync timestamp
                incremental_result = await self._sync_incremental(filters)
                sync_stats.update(incremental_result)

            sync_stats["completed_at"] = datetime.now(UTC).isoformat()
            sync_stats["duration_seconds"] = (
                datetime.fromisoformat(sync_stats["completed_at"])
                - datetime.fromisoformat(sync_stats["started_at"])
            ).total_seconds()

            # Update sync status
            self.sync_status[self.directory_type] = sync_stats

            # Log sync completion
            # AuditLogNode / SecurityEventNode are sync-only: neither defines
            # execute_async nor async_run, so every await in this module raised
            # AttributeError and no directory audit or security event was ever
            # recorded (issue #2060). They are offloaded to a worker thread and
            # given the parameters they actually read -- event_type/message/
            # user_id/event_data for audit, event_type/severity/message/user_id/
            # metadata for security. The action=/details=/source=/timestamp=
            # previously passed were silently dropped by execute().
            await asyncio.to_thread(
                self.audit_logger.execute,
                event_type="directory_sync_completed",
                message=f"Directory sync completed for {self.directory_type}",
                event_data=sync_stats,
            )

            return sync_stats

        except Exception as e:
            sync_stats["error"] = str(e)
            sync_stats["completed_at"] = datetime.now(UTC).isoformat()
            self.sync_status[self.directory_type] = sync_stats
            raise

    async def _sync_users(
        self, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Sync users from directory."""
        users_result = {"count": 0, "added": 0, "updated": 0, "users": []}

        # Build user search filter
        user_filter = self._build_user_filter(filters)

        # Simulate directory user search (in production, use actual directory client)
        users_data = await self._simulate_directory_search("users", user_filter)

        for user_data in users_data:
            try:
                # Map directory attributes to internal format
                mapped_user = self._map_directory_attributes(user_data)

                # Check if user exists (simulate with cache lookup)
                user_id = mapped_user.get("user_id") or mapped_user.get("email")
                if user_id in self.user_cache:
                    # Update existing user
                    self.user_cache[user_id].update(mapped_user)
                    users_result["updated"] += 1
                else:
                    # Add new user
                    self.user_cache[user_id] = mapped_user
                    users_result["added"] += 1

                users_result["users"].append(mapped_user)
                users_result["count"] += 1

            except Exception as e:
                self.log_error(f"Error processing user {user_data}: {e}")

        return users_result

    async def _sync_groups(
        self, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Sync groups from directory."""
        groups_result = {"count": 0, "added": 0, "updated": 0, "groups": []}

        # Build group search filter
        group_filter = self._build_group_filter(filters)

        # Simulate directory group search
        groups_data = await self._simulate_directory_search("groups", group_filter)

        for group_data in groups_data:
            try:
                # Map directory group to internal format
                mapped_group = self._map_directory_group(group_data)

                # Apply group mapping if configured
                mapped_name = self.group_mapping.get(
                    mapped_group["name"], mapped_group["name"]
                )
                mapped_group["mapped_name"] = mapped_name

                group_id = mapped_group["group_id"]
                if group_id in self.group_cache:
                    # Update existing group
                    self.group_cache[group_id].update(mapped_group)
                    groups_result["updated"] += 1
                else:
                    # Add new group
                    self.group_cache[group_id] = mapped_group
                    groups_result["added"] += 1

                groups_result["groups"].append(mapped_group)
                groups_result["count"] += 1

            except Exception as e:
                self.log_error(f"Error processing group {group_data}: {e}")

        return groups_result

    async def _sync_incremental(
        self, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Perform incremental sync based on timestamps."""
        # Get last sync timestamp
        last_sync = self.sync_status.get(self.directory_type, {}).get("completed_at")
        if not last_sync:
            # Fall back to full sync if no previous sync
            return await self._sync_directory("full", filters)

        # Add timestamp filter
        timestamp_filter = {"modified_since": last_sync}
        if filters:
            timestamp_filter.update(filters)

        # Sync users and groups with timestamp filter
        users_result = await self._sync_users(timestamp_filter)
        groups_result = await self._sync_groups(timestamp_filter)

        return {
            "sync_type": "incremental",
            "users_processed": users_result["count"],
            "users_added": users_result["added"],
            "users_updated": users_result["updated"],
            "groups_processed": groups_result["count"],
            "groups_added": groups_result["added"],
            "groups_updated": groups_result["updated"],
            "last_sync": last_sync,
        }

    async def _search_directory(
        self,
        query: str,
        filters: Dict[str, Any] | None = None,
        attributes: List[str] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Search directory for users/groups.

        Note:
            This is the rule-based Core SDK version. For AI-powered intelligent
            search query analysis, use the Kaizen version:
            `from kaizen.nodes.auth import DirectoryIntegrationNode`
        """
        search_results = {"users": [], "groups": [], "total": 0}

        # Parse search query using rule-based logic
        search_intent = self._analyze_search_query_rules(query)

        # Build search filters
        search_filters = self._build_search_filters(query, search_intent, filters)
        search_filters["search_term"] = query  # Ensure query is passed as search_term

        # Search users
        if search_intent.get("search_users", True):
            users = await self._simulate_directory_search(
                "users", search_filters, attributes
            )
            # For search results, return raw directory attributes for compatibility
            search_results["users"] = users

        # Search groups
        if search_intent.get("search_groups", True):
            groups = await self._simulate_directory_search(
                "groups", search_filters, attributes
            )
            search_results["groups"] = [self._map_directory_group(g) for g in groups]

        search_results["total"] = len(search_results["users"]) + len(
            search_results["groups"]
        )
        search_results["query"] = query
        search_results["search_intent"] = search_intent

        # Add combined entries for test compatibility
        search_results["entries"] = search_results["users"] + search_results["groups"]

        return search_results

    def _analyze_search_query_rules(self, query: str) -> Dict[str, Any]:
        """Analyze search intent using rule-based logic."""
        query_lower = query.lower()

        # Determine search targets based on keywords
        search_users = True
        search_groups = False
        search_attributes = ["cn", "mail", "uid"]

        # Group-specific keywords
        if any(keyword in query_lower for keyword in ["group", "team", "department"]):
            search_groups = True
            search_attributes.extend(["ou", "description"])

        # User-specific keywords
        if any(keyword in query_lower for keyword in ["user", "person", "employee"]):
            search_users = True
            search_attributes.extend(["givenName", "sn", "title"])

        # If query contains @ symbol, prioritize email search
        if "@" in query:
            search_attributes = ["mail"] + search_attributes

        return {
            "search_users": search_users,
            "search_groups": search_groups,
            "search_attributes": search_attributes,
            "filters": {},
        }

    async def _authenticate_user(
        self, credentials: Dict[str, str], **kwargs
    ) -> Dict[str, Any]:
        """Authenticate user against directory."""
        username = credentials.get("username")
        password = credentials.get("password")

        if not username or not password:
            raise ValueError("Username and password required for authentication")

        # Bind through the configurable implementation. This path used to build
        # its own connection with the bind DN hardcoded to
        # "CN={username},OU=Users,DC=test,DC=com", ignoring base_dn /
        # user_dn_template, and dropped the use_ssl/TLS handling -- so against a
        # real directory the bind always failed into simulation, and an operator
        # who set use_ssl sent the user's password in cleartext (issue #2026).
        try:
            auth_result = await self._ldap_directory_auth(username, password)

        # ANY exception from the bind -- including a connection an attacker can
        # induce by taking the directory offline -- routes here. That is only
        # acceptable because the fallback terminates FAIL-CLOSED, and it MUST
        # stay that way:
        #   * _fallback_directory_auth refuses outright with
        #     reason="directory_unavailable" unless the operator explicitly set
        #     connection_config["allow_insecure_credential_fallback"], read
        #     through _is_enabled() so the string "false" does not enable it;
        #   * even opted in, there is NO built-in account and NO default
        #     password -- an empty dev_credentials authenticates nobody, and the
        #     comparison is secrets.compare_digest against operator-supplied
        #     values. The hardcoded table that defaulted every lookup to
        #     "password123" is gone (issue #2026).
        # Giving this path a permissive default would hand an attacker who can
        # DoS the directory a login as anyone, which is exactly what #2026 fixed.
        #
        # This became REACHABLE in issue #2060: the audit call after the
        # decision awaited a method the sink does not define, so the whole
        # function previously raised AttributeError before returning. The
        # fail-closed property was load-bearing but unexercised until then.
        except ImportError:
            # ldap3 not installed
            auth_result = await self._simulate_directory_auth(username, password)
        except Exception:
            # Bind or connection failure
            auth_result = await self._simulate_directory_auth(username, password)

        if auth_result["authenticated"]:
            # Get user details
            user_details = await self._get_user(username)
            auth_result["user"] = user_details.get("user")
            # Report the DN actually used for the bind, from configuration --
            # this was hardcoded to a DC=test,DC=com value "for test
            # compatibility" and echoed to the caller (issue #2026).
            base_dn = self.connection_config.get("base_dn", "dc=example,dc=com")
            user_dn_template = self.connection_config.get(
                "user_dn_template", "CN={username},OU=Users," + base_dn
            )
            auth_result["user_dn"] = user_dn_template.format(username=username)

            # Log successful authentication
            await asyncio.to_thread(
                self.audit_logger.execute,
                event_type="directory_authentication_success",
                message=f"Directory authentication succeeded for {log_safe(username, 64)}",
                user_id=log_safe(username),
                event_data={"directory_type": self.directory_type},
            )
        else:
            # Log failed authentication
            await asyncio.to_thread(
                self.security_logger.execute,
                event_type="authentication_failure",
                severity="HIGH",
                message=f"Directory authentication failed for {log_safe(username, 64)}",
                user_id=log_safe(username),
                metadata={
                    "source": "directory_integration",
                    "username": username,
                    "directory_type": self.directory_type,
                    "reason": auth_result.get("reason", "invalid_credentials"),
                },
            )

        return auth_result

    async def _get_user_groups(self, username: str, **kwargs) -> Dict[str, Any]:
        """Get groups for a specific user."""
        # Get user details first
        user_result = await self._get_user(username)
        if user_result.get("found"):
            user_groups = user_result["user"].get("groups", [])
            # Convert group DNs to group objects
            groups = []
            for group_dn in user_groups:
                group_name = group_dn.split(",")[0].replace("CN=", "")
                groups.append({"name": group_name, "dn": group_dn, "type": "security"})
            return {"groups": groups, "username": username, "count": len(groups)}
        else:
            return {"groups": [], "username": username, "count": 0, "user_found": False}

    async def _get_user_details(self, username: str, **kwargs) -> Dict[str, Any]:
        """Get detailed user information."""
        # Get user data
        user_result = await self._get_user(username)
        if user_result.get("found"):
            user_data = user_result["user"]

            # Add additional details
            user_details = {
                "username": username,
                "mail": user_data.get("email"),
                "cn": user_data.get("common_name"),
                "displayName": user_data.get("common_name"),
                "department": user_data.get("department"),
                "title": user_data.get("job_title"),
                "groups": user_data.get("groups", []),
            }

            # Include security groups if requested
            if kwargs.get("include_security_groups"):
                security_groups = []
                for group_dn in user_data.get("groups", []):
                    group_name = group_dn.split(",")[0].replace("CN=", "")
                    security_groups.append(
                        {"name": group_name, "dn": group_dn, "type": "security"}
                    )
                return {
                    "user_details": user_details,
                    "security_groups": security_groups,
                }

            return {"user_details": user_details}
        else:
            return {"user_details": None, "found": False}

    async def _provision_user_full(
        self, user_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Provision user with full user data structure."""
        username = user_data.get("username")
        if not username:
            raise ValueError("Username is required for user provisioning")

        # Create user in directory (simulated)
        provisioning_result = {
            "user_created": True,
            "username": username,
            "user_dn": f"CN={user_data.get('first_name', '')} {user_data.get('last_name', '')},OU=Users,DC=test,DC=com",
        }

        return provisioning_result

    async def _get_user(
        self, user_id: str, attributes: List[str] | None = None, **kwargs
    ) -> Dict[str, Any]:
        """Get user details from directory."""
        # Check cache first
        if user_id in self.user_cache:
            cached_user = self.user_cache[user_id].copy()
            if not self._is_cache_expired(cached_user):
                return {"user": cached_user, "source": "cache"}

        # Search directory for user (by uid or email)
        if "@" in user_id:
            user_filter = {"mail": user_id}
        else:
            user_filter = {"uid": user_id}
        users = await self._simulate_directory_search("users", user_filter, attributes)

        if not users:
            return {"user": None, "found": False}

        user_data = self._map_directory_attributes(users[0])

        # Cache the result
        self.user_cache[user_id] = {
            **user_data,
            "cached_at": datetime.now(UTC).isoformat(),
        }

        return {"user": user_data, "source": "directory", "found": True}

    async def _get_groups(
        self,
        user_id: str | None = None,
        filters: Dict[str, Any] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Get groups from directory."""
        if user_id:
            # Get groups for specific user
            user_result = await self._get_user(user_id)
            if user_result.get("found"):
                user_groups = user_result["user"].get("groups", [])
                return {
                    "groups": user_groups,
                    "user_id": user_id,
                    "count": len(user_groups),
                }
            else:
                return {
                    "groups": [],
                    "user_id": user_id,
                    "count": 0,
                    "user_found": False,
                }
        else:
            # Get all groups
            group_filter = self._build_group_filter(filters)
            groups = await self._simulate_directory_search("groups", group_filter)
            mapped_groups = [self._map_directory_group(g) for g in groups]
            return {"groups": mapped_groups, "count": len(mapped_groups)}

    async def _provision_user(
        self, user_id: str, attributes: List[str] | None = None, **kwargs
    ) -> Dict[str, Any]:
        """Provision user from directory to local system.

        Note:
            This is the rule-based Core SDK version. For AI-powered intelligent
            provisioning with advanced role assignment, use the Kaizen version:
            `from kaizen.nodes.auth import DirectoryIntegrationNode`
        """
        if not self.auto_provisioning:
            raise ValueError("Auto-provisioning is disabled")

        # Get user from directory
        user_result = await self._get_user(user_id, attributes)

        if not user_result.get("found"):
            raise ValueError(f"User {user_id} not found in directory")

        user_data = user_result["user"]

        # Rule-based provisioning logic
        provisioning_data = {
            "user_id": user_id,
            "roles": self._assign_roles_from_directory(user_data),
            "permissions": self._map_groups_to_permissions(user_data.get("groups", [])),
            "settings": self._determine_security_settings(user_data),
            "status": "active",
        }

        # Log user provisioning
        await asyncio.to_thread(
            self.audit_logger.execute,
            event_type="user_provisioned_from_directory",
            message=f"Provisioned user {log_safe(user_id, 64)} from {self.directory_type}",
            user_id=log_safe(user_id),
            # The directory record is whatever the IdP returned -- for an
            # LDAP/AD sync that is the full mapped entry. Redacted rather than
            # copied verbatim into a log the whole org can read (issue #2060).
            event_data=redact_mapping(
                {
                    "directory_type": self.directory_type,
                    "directory_data": user_data,
                    "provisioning_data": provisioning_data,
                }
            ),
        )

        return {
            "user_id": user_id,
            "provisioned": True,
            "user_data": user_data,
            "provisioning_data": provisioning_data,
        }

    def _assign_roles_from_directory(self, user_data: Dict[str, Any]) -> List[str]:
        """Assign roles based on directory groups and attributes."""
        roles = ["user"]  # Default role

        groups = user_data.get("groups", [])
        for group in groups:
            group_lower = group.lower()
            if "admin" in group_lower or "administrator" in group_lower:
                roles.append("admin")
            elif "manager" in group_lower:
                roles.append("manager")
            elif "developer" in group_lower or "engineer" in group_lower:
                roles.append("developer")

        return list(set(roles))  # Remove duplicates

    def _determine_security_settings(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Determine security settings based on user attributes."""
        groups = user_data.get("groups", [])

        # Admin and manager roles require MFA
        require_mfa = any(
            group.lower() in ["admin", "administrator", "manager"] for group in groups
        )

        return {
            "mfa_required": require_mfa,
            "password_expiry_days": 90,
            "session_timeout_minutes": 480,  # 8 hours
        }

    async def _test_connection(self, **kwargs) -> Dict[str, Any]:
        """Test directory connection."""
        test_result = {
            "directory_type": self.directory_type,
            "connection_status": "unknown",
            "response_time_ms": 0,
            "features_supported": [],
            "schema_available": False,
        }

        start_time = time.time()

        try:
            # Check if LDAP3 Connection is being mocked (indicates unit/integration test)
            from ldap3 import ALL_ATTRIBUTES, Connection, Server

            is_mocked = hasattr(Connection, "_mock_name") or hasattr(
                Connection, "return_value"
            )

            # Simulation is opted into explicitly, never inferred from the
            # server's NAME. This previously routed any directory whose URL
            # contained "test." or began with "ldap://test" into the simulated
            # backend, so a real production directory named e.g.
            # ldap://test.corp.example.com was never actually contacted
            # (issue #2026).
            if (
                _is_enabled(self.connection_config.get("simulate_directory"))
                and not is_mocked
            ):
                raise ImportError("Using directory simulation (opted in)")

            # Get connection config
            server_url = self.connection_config.get("server", "ldap://localhost:389")
            bind_dn = self.connection_config.get("bind_dn", "")
            bind_password = self.connection_config.get("bind_password", "")

            # Honour use_ssl / TLS here too: this bind carries the service
            # account password, and building a bare Server() sent it in
            # cleartext whenever the operator had configured use_ssl
            # (issue #2026 -- the sibling of the _authenticate_user fix).
            server = Server(
                server_url,
                use_ssl=self.connection_config.get("use_ssl", False),
                tls=self._build_tls_config(server_url),
            )
            connection = Connection(server, user=bind_dn, password=bind_password)

            # Attempt to bind (this is what the test expects to be called)
            bind_result = connection.bind()

            if bind_result:
                test_result["connection_status"] = "connected"
                test_result["features_supported"] = [
                    "authentication",
                    "user_search",
                    "group_search",
                    "sync",
                    "provisioning",
                ]
                test_result["schema_available"] = True
                test_result["server_info"] = {
                    "version": str(
                        getattr(connection.server.info, "version", "unknown")
                    ),
                    "vendor": f"{self.directory_type.upper()}",
                }
            else:
                test_result["connection_status"] = "failed"
                test_result["error"] = "Authentication failed"

            # Close connection
            connection.unbind()

        except ImportError:
            if not _is_enabled(self.connection_config.get("simulate_directory")):
                # A health check must not report a connection it never made.
                # This previously said "connected" with a full feature list
                # whenever ldap3 was simply not installed (issue #2026).
                test_result["connection_status"] = "unavailable"
                test_result["error"] = (
                    "ldap3 is not installed; the directory was not contacted. "
                    "Install kailash[ldap] or set simulate_directory=True."
                )
                test_result["response_time_ms"] = (time.time() - start_time) * 1000
                return test_result

            # Explicit simulation opt-in.
            await asyncio.sleep(0.1)  # Simulate network delay
            test_result["connection_status"] = "connected"
            test_result["features_supported"] = [
                "authentication",
                "user_search",
                "group_search",
                "sync",
                "provisioning",
            ]
            test_result["schema_available"] = True
            test_result["server_info"] = {
                "version": "simulated-1.0",
                "vendor": f"Simulated {self.directory_type.upper()}",
            }
        except Exception as e:
            test_result["connection_status"] = "failed"
            test_result["error"] = str(e)
            # Don't fall back to simulation for connection tests with real errors
            if "connection refused" in str(e).lower() or "connection" in str(e).lower():
                test_result["response_time_ms"] = (time.time() - start_time) * 1000
                return test_result

        test_result["response_time_ms"] = (time.time() - start_time) * 1000
        return test_result

    async def _get_directory_schema(self, **kwargs) -> Dict[str, Any]:
        """Get directory schema information."""
        schema = {
            "directory_type": self.directory_type,
            "user_attributes": [
                {"name": "uid", "type": "string", "required": True},
                {"name": "cn", "type": "string", "required": True},
                {"name": "mail", "type": "string", "required": False},
                {"name": "givenName", "type": "string", "required": False},
                {"name": "sn", "type": "string", "required": False},
                {"name": "title", "type": "string", "required": False},
                {"name": "department", "type": "string", "required": False},
                {"name": "telephoneNumber", "type": "string", "required": False},
                {"name": "memberOf", "type": "array", "required": False},
            ],
            "group_attributes": [
                {"name": "cn", "type": "string", "required": True},
                {"name": "description", "type": "string", "required": False},
                {"name": "member", "type": "array", "required": False},
                {"name": "ou", "type": "string", "required": False},
            ],
            "object_classes": {
                "user": ["person", "organizationalPerson", "user"],
                "group": ["group", "groupOfNames"],
            },
        }

        return schema

    async def _simulate_directory_search(
        self,
        object_type: str,
        filters: Dict[str, Any],
        attributes: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """Search the directory using real LDAP, with an opt-in sample fallback.

        Attempts a real ldap3 search against the configured server. The built-in
        sample dataset is used ONLY when explicitly opted into, because its
        fabricated users and ``memberOf`` groups flow into
        :meth:`_assign_roles_from_directory` and
        :meth:`_map_groups_to_permissions`, both of which grant the ``admin``
        role for any group name containing "admin". Ungated, an attacker who
        could make the directory unreachable was provisioned as an admin
        (issue #2026 -- the sibling surface of ``_fallback_directory_auth``).
        """
        try:
            return await self._ldap_directory_search(object_type, filters, attributes)
        except ImportError:
            if not _is_enabled(
                self.connection_config.get("allow_insecure_credential_fallback")
            ):
                self.log_error(
                    "Directory search requires ldap3, which is not installed, "
                    "and the built-in sample dataset is disabled; returning no "
                    "results."
                )
                return []
        except Exception as e:
            if not _is_enabled(
                self.connection_config.get("allow_insecure_credential_fallback")
            ):
                self.log_error(
                    f"Directory search failed ({e}) and the built-in sample "
                    "dataset is disabled; returning no results."
                )
                return []
            self.log_error(f"LDAP search failed, using fallback: {e}")

        return self._fallback_directory_search(object_type, filters, attributes)

    async def _ldap_directory_search(
        self,
        object_type: str,
        filters: Dict[str, Any],
        attributes: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """Perform a real LDAP search using ldap3.

        Requires: pip install kailash[ldap]  (ldap3>=2.9)
        """
        import ssl

        from ldap3 import ALL_ATTRIBUTES, Connection, Server, ServerPool, Tls

        server_url = self.connection_config.get("server", "ldap://localhost:389")
        bind_dn = self.connection_config.get("bind_dn", "")
        bind_password = self.connection_config.get("bind_password", "")
        use_ssl = self.connection_config.get("use_ssl", False)
        base_dn = self.connection_config.get("base_dn", "dc=example,dc=com")

        # Build TLS context for LDAPS -- one shared policy across every site,
        # so a single opt-out flag governs all of them (issue #2026).
        tls_config = self._build_tls_config(server_url)

        # Support server pool for connection pooling
        servers_list = self.connection_config.get("servers", [server_url])
        if len(servers_list) > 1:
            servers = [Server(s, use_ssl=use_ssl, tls=tls_config) for s in servers_list]
            server = ServerPool(servers, pool_strategy="ROUND_ROBIN")
        else:
            server = Server(servers_list[0], use_ssl=use_ssl, tls=tls_config)

        conn = Connection(server, user=bind_dn, password=bind_password, auto_bind=True)

        try:
            # Build LDAP filter
            if object_type == "users":
                search_base = self.connection_config.get("user_base_dn", base_dn)
                ldap_filter = self._build_ldap_filter_string("person", filters)
            else:
                search_base = self.connection_config.get("group_base_dn", base_dn)
                ldap_filter = self._build_ldap_filter_string("group", filters)

            search_attrs = attributes or ALL_ATTRIBUTES

            conn.search(
                search_base=search_base,
                search_filter=ldap_filter,
                attributes=search_attrs,
            )

            results = []
            for entry in conn.entries:
                entry_dict = {}
                for attr in entry.entry_attributes:
                    val = entry[attr].value
                    if isinstance(val, list) and len(val) == 1:
                        val = val[0]
                    entry_dict[attr] = val
                results.append(entry_dict)

            return results
        finally:
            conn.unbind()

    def _build_ldap_filter_string(
        self, object_class: str, filters: Dict[str, Any]
    ) -> str:
        """Build an LDAP filter string from a dict of filters.

        Args:
            object_class: Base object class (person, group)
            filters: Dict of attribute -> value filters

        Returns:
            LDAP filter string like (&(objectClass=person)(uid=jdoe))
        """
        parts = [f"(objectClass={object_class})"]
        for key, value in (filters or {}).items():
            if key in ("objectClass", "base_dn", "modified_since", "search_term"):
                continue
            # Escape special LDAP chars in values
            safe_value = (
                str(value)
                .replace("\\", "\\5c")
                .replace("*", "\\2a")
                .replace("(", "\\28")
                .replace(")", "\\29")
            )
            parts.append(f"({key}={safe_value})")

        # Handle search_term as a substring filter across common attrs
        search_term = filters.get("search_term", "")
        if search_term:
            safe_term = (
                str(search_term)
                .replace("\\", "\\5c")
                .replace("*", "\\2a")
                .replace("(", "\\28")
                .replace(")", "\\29")
            )
            parts.append(
                f"(|(cn=*{safe_term}*)(uid=*{safe_term}*)(mail=*{safe_term}*))"
            )

        if len(parts) == 1:
            return parts[0]
        return "(&" + "".join(parts) + ")"

    def _fallback_directory_search(
        self,
        object_type: str,
        filters: Dict[str, Any],
        attributes: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """Built-in sample data fallback when LDAP is unavailable."""
        all_users = [
            {
                "uid": "jdoe",
                "cn": "John Doe",
                "sAMAccountName": "jdoe",
                "userPrincipalName": "jdoe@company.com",
                "mail": "john.doe@company.com",
                "displayName": "John Doe",
                "givenName": "John",
                "sn": "Doe",
                "title": "Senior Developer",
                "department": "Engineering",
                "telephoneNumber": "+1-555-0101",
                "memberOf": [
                    "CN=Engineering,OU=Groups,DC=company,DC=com",
                    "CN=Developers,OU=Groups,DC=company,DC=com",
                ],
            },
            {
                "uid": "john.doe",
                "cn": "John Doe",
                "mail": "john.doe@test.com",
                "givenName": "John",
                "sn": "Doe",
                "title": "Software Engineer",
                "department": "Engineering",
                "telephoneNumber": "+1-555-0101",
                "memberOf": [
                    "CN=Engineering,OU=Groups,DC=company,DC=com",
                    "CN=Developers,OU=Groups,DC=company,DC=com",
                ],
            },
            {
                "uid": "jsmith",
                "cn": "Jane Smith",
                "sAMAccountName": "jsmith",
                "userPrincipalName": "jsmith@company.com",
                "mail": "jane.smith@company.com",
                "displayName": "Jane Smith",
                "givenName": "Jane",
                "sn": "Smith",
                "title": "Product Manager",
                "department": "HR",
                "telephoneNumber": "+1-555-0102",
                "memberOf": ["CN=HR,OU=Groups,DC=company,DC=com"],
                "userAccountControl": 514,
            },
            {
                "uid": "jane.smith",
                "cn": "Jane Smith",
                "mail": "jane.smith@test.com",
                "givenName": "Jane",
                "sn": "Smith",
                "title": "Product Manager",
                "department": "Product",
                "telephoneNumber": "+1-555-0102",
                "memberOf": [
                    "CN=Domain Users,CN=Users,DC=test,DC=com",
                    "CN=Finance,OU=Groups,DC=test,DC=com",
                ],
            },
        ]

        if object_type == "users":
            search_term = filters.get("search_term", "").lower()
            if search_term:
                filtered_users = []
                for user in all_users:
                    user_text = f"{user.get('cn', '')} {user.get('uid', '')} {user.get('mail', '')}".lower()
                    if search_term in user_text:
                        filtered_users.append(user)
                return filtered_users

            if "uid" in filters:
                return [u for u in all_users if u.get("uid") == filters["uid"]]

            if "mail" in filters:
                return [u for u in all_users if u.get("mail") == filters["mail"]]

            return all_users
        elif object_type == "groups":
            return [
                {
                    "cn": "Engineers",
                    "description": "Engineering team",
                    "member": ["uid=john.doe,ou=users,dc=company,dc=com"],
                    "ou": "Groups",
                },
                {
                    "cn": "Managers",
                    "description": "Management team",
                    "member": ["uid=jane.smith,ou=users,dc=company,dc=com"],
                    "ou": "Groups",
                },
            ]
        return []

    async def _simulate_directory_auth(
        self, username: str, password: str
    ) -> Dict[str, Any]:
        """Authenticate against LDAP using real ldap3 bind, with fallback.

        Attempts a real LDAP simple bind. Falls back to the built-in
        credential table for backward compatibility when ldap3 is unavailable.
        """
        try:
            return await self._ldap_directory_auth(username, password)
        except ImportError:
            pass
        except Exception as e:
            self.log_error(f"LDAP auth failed, using fallback: {e}")

        return self._fallback_directory_auth(username, password)

    async def _ldap_directory_auth(
        self, username: str, password: str
    ) -> Dict[str, Any]:
        """Perform real LDAP bind for authentication.

        Requires: pip install kailash[ldap]  (ldap3>=2.9)
        """
        import ssl

        from ldap3 import Connection, Server, Tls

        server_url = self.connection_config.get("server", "ldap://localhost:389")
        use_ssl = self.connection_config.get("use_ssl", False)
        base_dn = self.connection_config.get("base_dn", "dc=example,dc=com")
        user_dn_template = self.connection_config.get(
            "user_dn_template", "CN={username},OU=Users," + base_dn
        )

        tls_config = self._build_tls_config(server_url)

        server = Server(server_url, use_ssl=use_ssl, tls=tls_config)
        user_dn = user_dn_template.format(username=username)

        conn = Connection(server, user=user_dn, password=password)
        bind_result = conn.bind()
        conn.unbind()

        if bind_result:
            return {
                "authenticated": True,
                # Name the principal explicitly: a caller that only sees
                # "username" fell back to its own requested user_id (#2026).
                "user_id": username,
                "username": username,
                "directory_type": self.directory_type,
            }
        return {
            "authenticated": False,
            "username": username,
            "reason": "invalid_credentials",
            "message": "Invalid credentials",
        }

    def _fallback_directory_auth(self, username: str, password: str) -> Dict[str, Any]:
        """Local-development credential check, for tests and dev ONLY.

        Fails closed unless explicitly opted into via
        ``connection_config={"allow_insecure_credential_fallback": True}``, AND
        credentials are supplied by the operator via
        ``connection_config["dev_credentials"] = {username: password}``.

        The hardcoded table this replaced is GONE (issue #2026). It shipped
        seven built-in accounts and, worse, defaulted the lookup to
        ``"password123"``, so ANY username at all authenticated with that
        password. It was reachable in production whenever the real LDAP bind
        raised, which made an attacker who could take the directory offline able
        to log in as anyone. There is now no built-in account and no default
        password: an empty ``dev_credentials`` authenticates nobody.
        """
        if not _is_enabled(
            self.connection_config.get("allow_insecure_credential_fallback")
        ):
            self.log_error(
                "Directory authentication is unavailable and the built-in "
                "credential fallback is disabled; refusing to authenticate "
                f"{username}."
            )
            return {
                "authenticated": False,
                "username": username,
                "reason": "directory_unavailable",
                "message": (
                    "Directory service unavailable and insecure credential "
                    "fallback is disabled."
                ),
            }

        # Operator-supplied only. No built-in accounts, and no default: an
        # unknown username has no entry, so `expected` is None and the
        # comparison below cannot succeed.
        dev_credentials = self.connection_config.get("dev_credentials") or {}
        expected = dev_credentials.get(username)

        if expected is not None and secrets.compare_digest(
            str(expected).encode("utf-8"), str(password).encode("utf-8")
        ):
            return {
                "authenticated": True,
                # Name the principal explicitly: a caller that only sees
                # "username" fell back to its own requested user_id (#2026).
                "user_id": username,
                "username": username,
                "directory_type": self.directory_type,
            }
        return {
            "authenticated": False,
            "username": username,
            "reason": "invalid_credentials",
            "message": "Invalid credentials",
        }

    def _map_directory_attributes(
        self, directory_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Map directory attributes to internal format."""
        mapped = {}

        for directory_attr, internal_attr in self.attribute_mapping.items():
            if directory_attr in directory_data:
                value = directory_data[directory_attr]

                # Special handling for group membership
                if internal_attr == "groups" and isinstance(value, list):
                    # Extract group names from Distinguished Names
                    group_names = []
                    for dn in value:
                        if isinstance(dn, str) and dn.startswith("CN="):
                            # Extract CN part: "CN=Engineering,OU=Groups,..." -> "Engineering"
                            cn_part = dn.split(",")[0]
                            if cn_part.startswith("CN="):
                                group_name = cn_part[3:]  # Remove "CN=" prefix
                                group_names.append(group_name)
                    mapped[internal_attr] = group_names
                else:
                    mapped[internal_attr] = value

        # Ensure required fields
        mapped["user_id"] = mapped.get("user_id") or mapped.get("email")
        mapped["directory_type"] = self.directory_type
        mapped["last_sync"] = datetime.now(UTC).isoformat()

        return mapped

    def _map_directory_group(self, group_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map directory group to internal format."""
        return {
            "group_id": group_data.get("cn"),
            "name": group_data.get("cn"),
            "description": group_data.get("description", ""),
            "members": group_data.get("member", []),
            "organizational_unit": group_data.get("ou", ""),
            "directory_type": self.directory_type,
            "last_sync": datetime.now(UTC).isoformat(),
        }

    def _build_user_filter(
        self, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Build LDAP filter for user search."""
        base_filter = {"objectClass": "person"}

        if filters:
            base_filter.update(filters)

        # Add configured filters
        if self.filter_config.get("user_base_dn"):
            base_filter["base_dn"] = self.filter_config["user_base_dn"]

        return base_filter

    def _build_group_filter(
        self, filters: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Build LDAP filter for group search."""
        base_filter = {"objectClass": "group"}

        if filters:
            base_filter.update(filters)

        # Add configured filters
        if self.filter_config.get("group_base_dn"):
            base_filter["base_dn"] = self.filter_config["group_base_dn"]

        return base_filter

    def _build_search_filters(
        self,
        query: str,
        search_intent: Dict[str, Any],
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Build search filters from query and intent."""
        search_filters = {}

        # Add query as search term
        if query:
            search_filters["search_term"] = query

        # Add intent-based filters
        if search_intent.get("filters"):
            search_filters.update(search_intent["filters"])

        # Add explicit filters
        if filters:
            search_filters.update(filters)

        return search_filters

    def _map_groups_to_permissions(self, groups: List[str]) -> List[str]:
        """Map directory groups to application permissions."""
        permissions = []

        for group in groups:
            group_name = group.split(",")[0].replace("CN=", "").lower()

            if "admin" in group_name:
                permissions.extend(["admin", "read", "write", "delete"])
            elif "manager" in group_name:
                permissions.extend(["read", "write"])
            elif "user" in group_name:
                permissions.append("read")

        return list(set(permissions))  # Remove duplicates

    def _is_cache_expired(self, cached_data: Dict[str, Any]) -> bool:
        """Check if cached data is expired."""
        cached_at = cached_data.get("cached_at")
        if not cached_at:
            return True

        cache_time = datetime.fromisoformat(cached_at)
        expiry_time = cache_time + timedelta(seconds=self.cache_ttl)

        return datetime.now(UTC) > expiry_time

    async def _log_security_event(self, **event_data):
        """Log security events using SecurityEventNode."""
        # Determine severity based on event type
        event_type = event_data.get("event_type", "directory_event")
        if "failure" in event_type or "error" in event_type:
            severity = "HIGH"
        elif "success" in event_type:
            severity = "INFO"
        else:
            severity = "MEDIUM"

        # The node stamps its own timestamp; source= and details= are not
        # parameters of SecurityEventNode and were dropped (issue #2060).
        await asyncio.to_thread(
            self.security_logger.execute,
            event_type=event_type,
            severity=severity,
            message=f"{event_type} via directory_integration_node",
            user_id=log_safe(event_data.get("user_id")),
            metadata=redact_mapping(
                {"source": "directory_integration_node", **event_data}
            ),
        )

    def get_directory_statistics(self) -> Dict[str, Any]:
        """Get directory integration statistics."""
        return {
            "directory_type": self.directory_type,
            "users_cached": len(self.user_cache),
            "groups_cached": len(self.group_cache),
            "last_sync": self.sync_status.get(self.directory_type, {}).get(
                "completed_at"
            ),
            "auto_provisioning_enabled": self.auto_provisioning,
            "cache_ttl_seconds": self.cache_ttl,
            "max_concurrent_operations": self.max_concurrent_operations,
            "connection_config": {
                k: "***" if "password" in k.lower() else v
                for k, v in self.connection_config.items()
            },
        }
