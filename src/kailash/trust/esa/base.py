# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Enterprise System Agent (ESA) Base Implementation.

Provides the base class for all Enterprise System Agents, which act as
trust-aware proxy agents for legacy enterprise systems.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from kailash.trust.chain import (
    ActionResult,
    AuthorityType,
    CapabilityType,
    VerificationLevel,
)
from kailash.trust.esa.exceptions import (
    ESAAuthorizationError,
    ESACapabilityNotFoundError,
    ESADelegationError,
    ESAError,
    ESANotEstablishedError,
    ESAOperationError,
)
from kailash.trust.exceptions import (
    DelegationError,
    TrustChainNotFoundError,
    VerificationFailedError,
)
from kailash.trust.operations import CapabilityRequest, TrustOperations


@dataclass
class SystemConnectionInfo:
    """
    Connection information for an enterprise system.

    Attributes:
        endpoint: System endpoint (URL, connection string, etc.)
        credentials: Credentials for system access (stored securely)
        connection_params: Additional connection parameters
        timeout_seconds: Connection timeout in seconds
        retry_attempts: Number of retry attempts on failure
    """

    endpoint: str
    credentials: Optional[Dict[str, str]] = None
    connection_params: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_attempts: int = 3


@dataclass
class SystemMetadata:
    """
    Metadata about an enterprise system.

    Attributes:
        system_type: Type of system (postgresql, rest_api, soap, etc.)
        version: System version
        vendor: System vendor
        description: Human-readable description
        tags: Searchable tags for discovery
        compliance_tags: Compliance requirements (e.g., ["PCI-DSS", "HIPAA"])
        custom_metadata: Additional custom metadata
    """

    system_type: str
    version: Optional[str] = None
    vendor: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    compliance_tags: List[str] = field(default_factory=list)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CapabilityMetadata:
    """
    Metadata about an ESA capability.

    Attributes:
        capability: Capability name (e.g., "read_transactions")
        description: Human-readable description
        capability_type: Type of capability
        parameters: Expected parameters with types and descriptions
        return_type: Return type description
        constraints: Default constraints for this capability
        examples: Usage examples
    """

    capability: str
    description: str
    capability_type: CapabilityType
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    return_type: Optional[str] = None
    constraints: List[str] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class OperationRequest:
    """
    Request for an ESA operation.

    Attributes:
        operation: Operation to execute
        parameters: Operation parameters
        requesting_agent_id: Agent requesting the operation
        context: Additional context (e.g., task_id, parent_operation_id)
        timeout_override: Override default timeout
    """

    operation: str
    parameters: Dict[str, Any]
    requesting_agent_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    timeout_override: Optional[int] = None


@dataclass
class OperationResult:
    """
    Result of an ESA operation.

    Attributes:
        success: Whether operation succeeded
        result: Operation result data
        error: Error message if failed
        audit_anchor_id: ID of audit record
        duration_ms: Execution duration in milliseconds
        metadata: Additional metadata (e.g., rows_affected, cache_hit)
    """

    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    audit_anchor_id: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ESAConfig:
    """
    Configuration for an Enterprise System Agent.

    Attributes:
        enable_capability_discovery: Auto-discover capabilities on establishment
        verification_level: Trust verification level for operations
        auto_audit: Automatically audit all operations
        cache_capabilities: Cache discovered capabilities
        capability_cache_ttl_seconds: TTL for capability cache
        enable_constraint_validation: Validate constraints before execution
        max_delegation_depth: Maximum delegation chain depth
    """

    enable_capability_discovery: bool = True
    verification_level: VerificationLevel = VerificationLevel.STANDARD
    auto_audit: bool = True
    cache_capabilities: bool = True
    capability_cache_ttl_seconds: int = 3600  # 1 hour
    enable_constraint_validation: bool = True
    max_delegation_depth: int = 5


class EnterpriseSystemAgent(ABC):
    """
    Base class for Enterprise System Agents.

    ESAs are specialized proxy agents that bridge AI agents with legacy
    enterprise systems. They provide:

    1. Trust Inheritance: Established by SYSTEM authority type
    2. Capability Discovery: Auto-discover capabilities from system metadata
    3. Request Proxying: Validate, proxy, and audit all requests
    4. Capability Delegation: Delegate capabilities to agents with constraints

    Subclasses must implement:
    - discover_capabilities(): Discover capabilities from system
    - execute_operation(): Execute operation on the underlying system
    - validate_connection(): Validate system connection

    Example:
        class DatabaseESA(EnterpriseSystemAgent):
            async def discover_capabilities(self) -> List[str]:
                tables = await self.db.get_tables()
                return [f"read_{table}" for table in tables]

            async def execute_operation(
                self,
                operation: str,
                parameters: Dict[str, Any]
            ) -> Any:
                # Execute database operation
                return await self.db.execute(operation, parameters)

            async def validate_connection(self) -> bool:
                return await self.db.ping()

        # Usage
        esa = DatabaseESA(
            system_id="db-finance-001",
            system_name="Finance Database",
            trust_ops=trust_ops,
            connection_info=SystemConnectionInfo(
                endpoint="postgresql://...",
            ),
        )
        await esa.establish_trust(authority_id="org-acme")
        result = await esa.execute(
            operation="read_transactions",
            parameters={"limit": 100},
            requesting_agent_id="agent-001",
        )
    """

    def __init__(
        self,
        system_id: str,
        system_name: str,
        trust_ops: TrustOperations,
        connection_info: SystemConnectionInfo,
        metadata: Optional[SystemMetadata] = None,
        config: Optional[ESAConfig] = None,
    ):
        """
        Initialize Enterprise System Agent.

        Args:
            system_id: Unique identifier for the system
            system_name: Human-readable system name
            trust_ops: TrustOperations instance for trust management
            connection_info: System connection information
            metadata: System metadata (optional)
            config: ESA configuration (optional, uses defaults)
        """
        self.system_id = system_id
        self.system_name = system_name
        self.trust_ops = trust_ops
        self.connection_info = connection_info
        self.metadata = metadata or SystemMetadata(system_type="unknown")
        self.config = config or ESAConfig()

        # Trust state
        self._established = False
        self._agent_id = f"esa-{system_id}"

        # Capability cache
        self._capabilities: List[str] = []
        self._capability_metadata: Dict[str, CapabilityMetadata] = {}
        self._capability_cache_time: Optional[datetime] = None

        # Statistics
        self._operation_count = 0
        self._success_count = 0
        self._failure_count = 0

    @property
    def agent_id(self) -> str:
        """Get the ESA's agent ID."""
        return self._agent_id

    @property
    def is_established(self) -> bool:
        """Check if ESA trust is established."""
        return self._established

    @property
    def capabilities(self) -> List[str]:
        """Get list of available capabilities."""
        return self._capabilities.copy()

    # =========================================================================
    # Trust Establishment
    # =========================================================================

    async def establish_trust(
        self,
        authority_id: str,
        additional_constraints: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> None:
        """
        Establish trust for this ESA via SYSTEM authority.

        This operation:
        1. Validates system connection
        2. Discovers capabilities (if enabled)
        3. Creates trust chain via TrustOperations.establish()
        4. Caches capability metadata

        Args:
            authority_id: Organizational authority granting trust
            additional_constraints: Additional constraints beyond defaults
            expires_at: Optional expiration datetime

        Raises:
            ESAConnectionError: If system connection fails
            TrustError: If trust establishment fails
        """
        # 1. Validate system connection
        if not await self.validate_connection():
            from kailash.trust.esa.exceptions import ESAConnectionError

            raise ESAConnectionError(
                system_id=self.system_id,
                endpoint=self.connection_info.endpoint,
                reason="System connection validation failed",
            )

        # 2. Discover capabilities
        if self.config.enable_capability_discovery:
            self._capabilities = await self.discover_capabilities()
            self._capability_cache_time = datetime.now(timezone.utc)

        # 3. Build capability requests
        capability_requests = []
        for capability in self._capabilities:
            # Get capability metadata if available
            cap_meta = self._capability_metadata.get(capability)
            cap_type = cap_meta.capability_type if cap_meta else CapabilityType.ACCESS
            cap_constraints = cap_meta.constraints if cap_meta else []

            capability_requests.append(
                CapabilityRequest(
                    capability=capability,
                    capability_type=cap_type,
                    constraints=cap_constraints,
                    scope={
                        "system_id": self.system_id,
                        "system_type": self.metadata.system_type,
                    },
                )
            )

        # Add default ESA capabilities
        default_capabilities = [
            CapabilityRequest(
                capability="esa_system_access",
                capability_type=CapabilityType.ACCESS,
                constraints=[],
                scope={"system_id": self.system_id},
            )
        ]

        # 4. Establish trust via TrustOperations
        # ESAs use SYSTEM authority type (not ORGANIZATION)
        constraints = additional_constraints or []
        constraints.extend(
            [
                "esa_proxy_only",  # ESA can only proxy, not initiate
                "full_audit_required",  # All operations must be audited
            ]
        )

        chain = await self.trust_ops.establish(
            agent_id=self._agent_id,
            authority_id=authority_id,
            capabilities=default_capabilities + capability_requests,
            constraints=constraints,
            metadata={
                "agent_type": "esa",
                "system_id": self.system_id,
                "system_name": self.system_name,
                "system_type": self.metadata.system_type,
                "endpoint": self.connection_info.endpoint,
                "capabilities_discovered": len(self._capabilities),
            },
            expires_at=expires_at,
        )

        self._established = True

    # =========================================================================
    # Abstract Methods (Subclasses Must Implement)
    # =========================================================================

    @abstractmethod
    async def discover_capabilities(self) -> List[str]:
        """
        Discover capabilities from the underlying system.

        This method should introspect the system to determine available
        operations. For example:
        - Database: Discover tables, views, functions
        - REST API: Parse OpenAPI/Swagger spec
        - SOAP: Parse WSDL

        Returns:
            List of capability names (e.g., ["read_users", "write_transactions"])

        Note:
            Subclasses should also populate self._capability_metadata with
            CapabilityMetadata for each discovered capability.
        """
        pass

    @abstractmethod
    async def execute_operation(
        self,
        operation: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """
        Execute an operation on the underlying system.

        This method performs the actual system interaction (database query,
        API call, etc.). It should NOT perform trust verification or auditing,
        as these are handled by the execute() method.

        Args:
            operation: Operation to execute
            parameters: Operation parameters

        Returns:
            Operation result (type depends on operation)

        Raises:
            ESAOperationError: If operation fails
        """
        pass

    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate connection to the underlying system.

        This method should perform a lightweight check to ensure the system
        is accessible and credentials are valid.

        Returns:
            True if connection is valid, False otherwise
        """
        pass

    # =========================================================================
    # Operation Execution
    # =========================================================================

    async def execute(
        self,
        operation: str,
        parameters: Dict[str, Any],
        requesting_agent_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> OperationResult:
        """
        Execute an operation with full trust verification and audit.

        This is the main entry point for ESA operations. It performs:
        1. ESA establishment check
        2. Capability verification
        3. Trust verification for requesting agent
        4. Constraint validation
        5. Operation execution
        6. Result auditing

        Args:
            operation: Operation to execute
            parameters: Operation parameters
            requesting_agent_id: Agent requesting the operation
            context: Additional context (optional)

        Returns:
            OperationResult with success status and data

        Raises:
            ESANotEstablishedError: If ESA trust not established
            ESACapabilityNotFoundError: If operation not available
            ESAAuthorizationError: If agent not authorized
            ESAOperationError: If operation execution fails
        """
        start_time = datetime.now(timezone.utc)
        context = context or {}

        # 1. Check ESA is established
        if not self._established:
            raise ESANotEstablishedError(self.system_id)

        # 2. Verify operation is available
        if operation not in self._capabilities:
            raise ESACapabilityNotFoundError(
                capability=operation,
                system_id=self.system_id,
                available_capabilities=self._capabilities,
            )

        # 3. Verify requesting agent has trust for this operation
        try:
            verification = await self.trust_ops.verify(
                agent_id=requesting_agent_id,
                action=operation,
                resource=self.system_id,
                level=self.config.verification_level,
                context={
                    **context,
                    "esa_system_id": self.system_id,
                    "esa_system_type": self.metadata.system_type,
                },
            )

            if not verification.valid:
                raise ESAAuthorizationError(
                    requesting_agent_id=requesting_agent_id,
                    operation=operation,
                    system_id=self.system_id,
                    reason=verification.reason or "Trust verification failed",
                    required_capability=operation,
                )

        except TrustChainNotFoundError:
            raise ESAAuthorizationError(
                requesting_agent_id=requesting_agent_id,
                operation=operation,
                system_id=self.system_id,
                reason="No trust chain found for agent",
                required_capability=operation,
            )

        # 4. Execute operation
        operation_result = None
        operation_error = None
        action_result = ActionResult.SUCCESS

        try:
            self._operation_count += 1
            operation_result = await self.execute_operation(operation, parameters)
            self._success_count += 1

        except Exception as e:
            self._failure_count += 1
            action_result = ActionResult.FAILURE
            operation_error = str(e)
            raise ESAOperationError(
                operation=operation,
                system_id=self.system_id,
                reason=operation_error,
                original_error=e,
            )

        finally:
            # 5. Audit the operation (even if it failed)
            duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            if self.config.auto_audit:
                audit_anchor = await self.trust_ops.audit(
                    agent_id=requesting_agent_id,
                    action=operation,
                    resource=self.system_id,
                    result=action_result,
                    context={
                        **context,
                        "esa_system_id": self.system_id,
                        "esa_agent_id": self._agent_id,
                        "operation": operation,
                        "parameters": parameters,
                        "duration_ms": duration_ms,
                        "error": operation_error,
                    },
                    parent_anchor_id=context.get("parent_anchor_id"),
                )

                return OperationResult(
                    success=action_result == ActionResult.SUCCESS,
                    result=operation_result,
                    error=operation_error,
                    audit_anchor_id=audit_anchor.id,
                    duration_ms=duration_ms,
                    metadata={
                        "verification_level": self.config.verification_level.value,
                        "capability_used": verification.capability_used,
                    },
                )
            else:
                return OperationResult(
                    success=action_result == ActionResult.SUCCESS,
                    result=operation_result,
                    error=operation_error,
                    duration_ms=duration_ms,
                )

    # =========================================================================
    # Capability Delegation
    # =========================================================================

    async def delegate_capability(
        self,
        capability: str,
        delegatee_id: str,
        task_id: str,
        additional_constraints: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Delegate a capability to another agent.

        This allows the ESA to grant temporary access to specific capabilities
        for other agents, with additional constraints.

        Args:
            capability: Capability to delegate
            delegatee_id: Agent receiving the capability
            task_id: Task identifier for scoping
            additional_constraints: Additional constraints (tightening only)
            expires_at: Optional expiration datetime

        Returns:
            Delegation ID

        Raises:
            ESANotEstablishedError: If ESA trust not established
            ESACapabilityNotFoundError: If capability not available
            ESADelegationError: If delegation fails
        """
        # 1. Check ESA is established
        if not self._established:
            raise ESANotEstablishedError(self.system_id)

        # 2. Verify capability exists
        if capability not in self._capabilities:
            raise ESACapabilityNotFoundError(
                capability=capability,
                system_id=self.system_id,
                available_capabilities=self._capabilities,
            )

        # 3. Delegate via TrustOperations
        try:
            delegation = await self.trust_ops.delegate(
                delegator_id=self._agent_id,
                delegatee_id=delegatee_id,
                task_id=task_id,
                capabilities=[capability],
                additional_constraints=additional_constraints or [],
                expires_at=expires_at,
                metadata={
                    "delegator_type": "esa",
                    "esa_system_id": self.system_id,
                    "esa_system_type": self.metadata.system_type,
                },
            )

            return delegation.id

        except DelegationError as e:
            raise ESADelegationError(
                capability=capability,
                delegatee_id=delegatee_id,
                system_id=self.system_id,
                reason=str(e),
            ) from e

    # =========================================================================
    # Capability Management
    # =========================================================================

    async def refresh_capabilities(self) -> List[str]:
        """
        Refresh capabilities from the system.

        Re-discovers capabilities and updates the capability cache.

        Returns:
            Updated list of capabilities

        Raises:
            ESANotEstablishedError: If ESA trust not established
        """
        if not self._established:
            raise ESANotEstablishedError(self.system_id)

        self._capabilities = await self.discover_capabilities()
        self._capability_cache_time = datetime.now(timezone.utc)

        return self._capabilities.copy()

    def get_capability_metadata(self, capability: str) -> Optional[CapabilityMetadata]:
        """
        Get metadata for a specific capability.

        Args:
            capability: Capability name

        Returns:
            CapabilityMetadata if available, None otherwise
        """
        return self._capability_metadata.get(capability)

    def is_capability_cached(self) -> bool:
        """
        Check if capability cache is still valid.

        Returns:
            True if cache is valid, False if expired or not cached
        """
        if not self._capability_cache_time or not self.config.cache_capabilities:
            return False

        cache_age = (datetime.now(timezone.utc) - self._capability_cache_time).total_seconds()
        return cache_age < self.config.capability_cache_ttl_seconds

    # =========================================================================
    # Statistics and Monitoring
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get ESA operation statistics.

        Returns:
            Dictionary with operation counts and success rates
        """
        success_rate = 0.0
        if self._operation_count > 0:
            success_rate = self._success_count / self._operation_count

        return {
            "system_id": self.system_id,
            "system_name": self.system_name,
            "established": self._established,
            "capabilities_count": len(self._capabilities),
            "operation_count": self._operation_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "success_rate": success_rate,
            "cache_valid": self.is_capability_cached(),
        }

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a comprehensive health check.

        Returns:
            Dictionary with health status and details
        """
        health = {
            "healthy": True,
            "system_id": self.system_id,
            "established": self._established,
            "checks": {},
        }

        # Check connection
        try:
            connection_ok = await self.validate_connection()
            health["checks"]["connection"] = {
                "status": "ok" if connection_ok else "failed",
                "endpoint": self.connection_info.endpoint,
            }
            if not connection_ok:
                health["healthy"] = False
        except Exception as e:
            health["checks"]["connection"] = {"status": "error", "error": str(e)}
            health["healthy"] = False

        # Check trust chain
        if self._established:
            try:
                chain = await self.trust_ops.trust_store.get_chain(self._agent_id)
                health["checks"]["trust_chain"] = {
                    "status": "ok",
                    "expired": chain.is_expired(),
                    "capabilities_count": len(chain.capabilities),
                }
                if chain.is_expired():
                    health["healthy"] = False
            except TrustChainNotFoundError:
                health["checks"]["trust_chain"] = {"status": "not_found"}
                health["healthy"] = False
        else:
            health["checks"]["trust_chain"] = {"status": "not_established"}

        # Check capability cache
        health["checks"]["capability_cache"] = {
            "cached": self.is_capability_cached(),
            "count": len(self._capabilities),
            "last_updated": (self._capability_cache_time.isoformat() if self._capability_cache_time else None),
        }

        # Add statistics
        health["statistics"] = self.get_statistics()

        return health
