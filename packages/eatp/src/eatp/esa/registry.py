# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
ESA Registry for managing Enterprise System Agents.

Provides centralized registration, discovery, and health monitoring for ESAs.
"""

import asyncio
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from eatp.esa.base import (
    EnterpriseSystemAgent,
    ESAConfig,
    SystemConnectionInfo,
    SystemMetadata,
)
from eatp.esa.exceptions import (
    ESAConnectionError,
    ESAError,
    ESANotEstablishedError,
)
from eatp.exceptions import TrustError
from eatp.operations import TrustOperations


class SystemType(str, Enum):
    """Enumeration of enterprise system types."""

    DATABASE = "database"
    REST_API = "rest_api"
    FILE_SYSTEM = "file_system"
    MESSAGE_QUEUE = "message_queue"
    CLOUD_SERVICE = "cloud_service"
    SOAP_SERVICE = "soap_service"
    LDAP = "ldap"
    EMAIL_SERVER = "email_server"
    UNKNOWN = "unknown"


@dataclass
class ESARegistration:
    """
    Registration record for an ESA.

    Attributes:
        esa_id: Unique identifier for the registered ESA
        esa: The EnterpriseSystemAgent instance
        registered_at: Registration timestamp
        last_health_check: Last successful health check timestamp
        health_status: Current health status ("healthy", "unhealthy", "unknown")
        registration_metadata: Additional metadata about the registration
    """

    esa_id: str
    esa: EnterpriseSystemAgent
    registered_at: datetime
    last_health_check: Optional[datetime] = None
    health_status: str = "unknown"
    registration_metadata: Dict[str, Any] = field(default_factory=dict)


class ESAStore(ABC):
    """
    Abstract base class for ESA persistence.

    Implementations can provide different storage backends (filesystem, database, etc.)
    for persisting ESA configurations and state.
    """

    @abstractmethod
    async def save(self, esa_id: str, esa_data: Dict[str, Any]) -> None:
        """
        Save ESA data to persistent storage.

        Args:
            esa_id: ESA identifier
            esa_data: Serialized ESA configuration and state

        Raises:
            ESAError: If save operation fails
        """
        pass

    @abstractmethod
    async def load(self, esa_id: str) -> Optional[Dict[str, Any]]:
        """
        Load ESA data from persistent storage.

        Args:
            esa_id: ESA identifier

        Returns:
            Serialized ESA data or None if not found

        Raises:
            ESAError: If load operation fails
        """
        pass

    @abstractmethod
    async def delete(self, esa_id: str) -> bool:
        """
        Delete ESA data from persistent storage.

        Args:
            esa_id: ESA identifier

        Returns:
            True if deleted, False if not found

        Raises:
            ESAError: If delete operation fails
        """
        pass

    @abstractmethod
    async def list_all(self) -> List[str]:
        """
        List all ESA identifiers in storage.

        Returns:
            List of ESA identifiers

        Raises:
            ESAError: If list operation fails
        """
        pass


class InMemoryESAStore(ESAStore):
    """
    In-memory ESA store implementation.

    Simple dictionary-based storage for development and testing.
    Not suitable for production use as data is lost on restart.
    """

    def __init__(self):
        """Initialize in-memory store."""
        self._storage: Dict[str, Dict[str, Any]] = {}

    async def save(self, esa_id: str, esa_data: Dict[str, Any]) -> None:
        """Save ESA data to memory."""
        self._storage[esa_id] = esa_data.copy()

    async def load(self, esa_id: str) -> Optional[Dict[str, Any]]:
        """Load ESA data from memory."""
        return self._storage.get(esa_id)

    async def delete(self, esa_id: str) -> bool:
        """Delete ESA data from memory."""
        if esa_id in self._storage:
            del self._storage[esa_id]
            return True
        return False

    async def list_all(self) -> List[str]:
        """List all ESA identifiers in memory."""
        return list(self._storage.keys())


class ESARegistryError(ESAError):
    """Raised when ESA registry operations fail."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize registry error.

        Args:
            message: Human-readable error message
            details: Additional context
        """
        super().__init__(message, details)


class ESAAlreadyRegisteredError(ESARegistryError):
    """Raised when attempting to register an ESA that's already registered."""

    def __init__(self, esa_id: str):
        """
        Initialize already registered error.

        Args:
            esa_id: ESA identifier that's already registered
        """
        super().__init__(
            f"ESA '{esa_id}' is already registered", details={"esa_id": esa_id}
        )
        self.esa_id = esa_id


class ESANotFoundError(ESARegistryError):
    """Raised when an ESA is not found in the registry."""

    def __init__(self, esa_id: str):
        """
        Initialize not found error.

        Args:
            esa_id: ESA identifier that was not found
        """
        super().__init__(
            f"ESA '{esa_id}' not found in registry", details={"esa_id": esa_id}
        )
        self.esa_id = esa_id


class ESARegistry:
    """
    Registry for managing Enterprise System Agents.

    The ESARegistry provides centralized management for ESAs including:
    - Registration and deregistration
    - Trust chain verification
    - Health monitoring
    - System type-based lookup
    - Auto-discovery from connection strings

    Example:
        >>> # Initialize registry
        >>> registry = ESARegistry(trust_ops=trust_ops)
        >>> await registry.initialize()
        >>>
        >>> # Register an ESA
        >>> esa = DatabaseESA(...)
        >>> esa_id = await registry.register(esa)
        >>>
        >>> # Auto-discover and register from connection string
        >>> esa = await registry.discover_and_register(
        ...     "postgresql://user:pass@host:5432/db"
        ... )
        >>>
        >>> # Retrieve ESA
        >>> esa = await registry.get(esa_id)
        >>>
        >>> # List ESAs by type
        >>> db_esas = await registry.list_by_type(SystemType.DATABASE)
        >>>
        >>> # Health monitoring
        >>> health = await registry.get_health_status(esa_id)
    """

    def __init__(
        self,
        trust_operations: TrustOperations,
        store: Optional[ESAStore] = None,
        enable_health_monitoring: bool = True,
        health_check_interval_seconds: int = 300,  # 5 minutes
    ):
        """
        Initialize ESA Registry.

        Args:
            trust_operations: TrustOperations instance for trust management
            store: Optional ESAStore for persistence (uses in-memory if not provided)
            enable_health_monitoring: Enable automatic health monitoring
            health_check_interval_seconds: Interval for automatic health checks
        """
        self.trust_ops = trust_operations
        self.store = store or InMemoryESAStore()
        self.enable_health_monitoring = enable_health_monitoring
        self.health_check_interval = health_check_interval_seconds

        # In-memory registry (always maintained regardless of persistence)
        self._registrations: Dict[str, ESARegistration] = {}

        # Type index for fast lookups
        self._type_index: Dict[SystemType, List[str]] = {
            system_type: [] for system_type in SystemType
        }

        # Health monitoring state
        self._health_check_task: Optional[asyncio.Task] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the registry.

        Loads persisted ESAs (if store configured) and starts health monitoring.
        """
        if self._initialized:
            return

        # Load persisted ESAs from store
        try:
            esa_ids = await self.store.list_all()
            for esa_id in esa_ids:
                # Note: Loading ESAs from store would require serialization/deserialization
                # This is a placeholder for future implementation
                pass
        except Exception as e:
            # Non-fatal - continue with empty registry
            pass

        # Start health monitoring if enabled
        if self.enable_health_monitoring:
            self._health_check_task = asyncio.create_task(
                self._health_monitoring_loop()
            )

        self._initialized = True

    async def shutdown(self) -> None:
        """
        Shutdown the registry.

        Cancels health monitoring and cleans up resources.
        """
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        self._initialized = False

    async def register(
        self,
        esa: EnterpriseSystemAgent,
        verify_trust_chain: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register an ESA in the registry.

        This operation:
        1. Validates the ESA is established (if verify_trust_chain=True)
        2. Verifies trust chain integrity
        3. Registers ESA in the registry
        4. Indexes by system type
        5. Persists to store (if configured)

        Args:
            esa: EnterpriseSystemAgent to register
            verify_trust_chain: Verify trust chain before registration
            metadata: Additional registration metadata

        Returns:
            ESA identifier (esa.system_id)

        Raises:
            ESAAlreadyRegisteredError: If ESA already registered
            ESANotEstablishedError: If ESA trust not established
            TrustError: If trust chain verification fails
        """
        esa_id = esa.system_id
        metadata = metadata or {}

        # 1. Check if already registered
        if esa_id in self._registrations:
            raise ESAAlreadyRegisteredError(esa_id)

        # 2. Verify ESA is established
        if verify_trust_chain:
            if not esa.is_established:
                raise ESANotEstablishedError(esa_id)

            # Verify trust chain exists and is valid
            try:
                chain = await self.trust_ops.trust_store.get_chain(esa.agent_id)
                if chain.is_expired():
                    raise TrustError(f"Trust chain for ESA '{esa_id}' is expired")
            except Exception as e:
                raise TrustError(
                    f"Trust chain verification failed for ESA '{esa_id}': {str(e)}"
                )

        # 3. Create registration record
        registration = ESARegistration(
            esa_id=esa_id,
            esa=esa,
            registered_at=datetime.now(timezone.utc),
            registration_metadata=metadata,
        )

        # 4. Add to registry
        self._registrations[esa_id] = registration

        # 5. Index by system type
        system_type = self._detect_system_type(esa.metadata.system_type)
        if esa_id not in self._type_index[system_type]:
            self._type_index[system_type].append(esa_id)

        # 6. Persist to store
        try:
            await self.store.save(
                esa_id,
                {
                    "system_id": esa.system_id,
                    "system_name": esa.system_name,
                    "system_type": esa.metadata.system_type,
                    "endpoint": esa.connection_info.endpoint,
                    "registered_at": registration.registered_at.isoformat(),
                    "metadata": metadata,
                },
            )
        except Exception as e:
            # Non-fatal - continue without persistence
            pass

        return esa_id

    async def get(self, esa_id: str) -> EnterpriseSystemAgent:
        """
        Retrieve an ESA by ID.

        Args:
            esa_id: ESA identifier

        Returns:
            EnterpriseSystemAgent instance

        Raises:
            ESANotFoundError: If ESA not found
        """
        registration = self._registrations.get(esa_id)
        if not registration:
            raise ESANotFoundError(esa_id)

        return registration.esa

    async def list_by_type(
        self,
        system_type: SystemType,
        include_unhealthy: bool = True,
    ) -> List[EnterpriseSystemAgent]:
        """
        List all ESAs of a specific type.

        Args:
            system_type: System type to filter by
            include_unhealthy: Include ESAs with unhealthy status

        Returns:
            List of EnterpriseSystemAgent instances
        """
        esa_ids = self._type_index.get(system_type, [])
        esas = []

        for esa_id in esa_ids:
            registration = self._registrations.get(esa_id)
            if registration:
                # Filter by health status if requested
                if not include_unhealthy and registration.health_status == "unhealthy":
                    continue
                esas.append(registration.esa)

        return esas

    async def list_all(
        self,
        include_unhealthy: bool = True,
    ) -> List[EnterpriseSystemAgent]:
        """
        List all registered ESAs.

        Args:
            include_unhealthy: Include ESAs with unhealthy status

        Returns:
            List of EnterpriseSystemAgent instances
        """
        esas = []

        for registration in self._registrations.values():
            # Filter by health status if requested
            if not include_unhealthy and registration.health_status == "unhealthy":
                continue
            esas.append(registration.esa)

        return esas

    async def discover_and_register(
        self,
        connection_string: str,
        authority_id: str,
        system_name: Optional[str] = None,
        config: Optional[ESAConfig] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
    ) -> EnterpriseSystemAgent:
        """
        Auto-discover system type and register ESA from connection string.

        This convenience method:
        1. Parses connection string to detect system type
        2. Creates appropriate ESA subclass (if available)
        3. Establishes trust
        4. Registers in registry

        Args:
            connection_string: System connection string (e.g., "postgresql://...")
            authority_id: Authority to establish trust from
            system_name: Optional human-readable system name
            config: Optional ESA configuration
            additional_metadata: Additional metadata for the system

        Returns:
            Registered EnterpriseSystemAgent

        Raises:
            ESAError: If discovery or registration fails

        Note:
            This is a basic implementation that creates a generic ESA.
            Production implementations would create specific ESA subclasses
            (DatabaseESA, RestAPIESA, etc.) based on system type.
        """
        additional_metadata = additional_metadata or {}

        # 1. Detect system type from connection string
        system_type = self._detect_system_type_from_connection(connection_string)

        # 2. Parse connection info
        connection_info = SystemConnectionInfo(
            endpoint=connection_string,
            credentials=additional_metadata.get("credentials"),
            connection_params=additional_metadata.get("connection_params", {}),
        )

        # 3. Create system metadata
        metadata = SystemMetadata(
            system_type=system_type.value,
            version=additional_metadata.get("version"),
            vendor=additional_metadata.get("vendor"),
            description=additional_metadata.get("description"),
            tags=additional_metadata.get("tags", []),
            compliance_tags=additional_metadata.get("compliance_tags", []),
        )

        # 4. Generate system ID
        system_id = f"esa-{system_type.value}-{uuid4().hex[:8]}"
        if not system_name:
            system_name = f"{system_type.value.replace('_', ' ').title()} ESA"

        # 5. Create generic ESA (in production, would create specific subclass)
        # Note: This requires a concrete ESA implementation
        # For now, we raise an error indicating manual ESA creation is needed
        raise ESAError(
            f"Auto-discovery requires a concrete ESA implementation for {system_type.value}. "
            f"Please create and register an ESA manually."
        )

        # Future implementation would look like:
        # esa = self._create_esa_for_type(
        #     system_type=system_type,
        #     system_id=system_id,
        #     system_name=system_name,
        #     connection_info=connection_info,
        #     metadata=metadata,
        #     config=config,
        # )
        #
        # # 6. Establish trust
        # await esa.establish_trust(authority_id=authority_id)
        #
        # # 7. Register
        # await self.register(esa)
        #
        # return esa

    async def unregister(self, esa_id: str) -> bool:
        """
        Unregister an ESA from the registry.

        This operation:
        1. Removes ESA from registry
        2. Removes from type index
        3. Deletes from persistent store

        Args:
            esa_id: ESA identifier to unregister

        Returns:
            True if unregistered, False if not found
        """
        # 1. Check if registered
        registration = self._registrations.get(esa_id)
        if not registration:
            return False

        # 2. Remove from type index
        system_type = self._detect_system_type(registration.esa.metadata.system_type)
        if esa_id in self._type_index[system_type]:
            self._type_index[system_type].remove(esa_id)

        # 3. Remove from registry
        del self._registrations[esa_id]

        # 4. Delete from store
        try:
            await self.store.delete(esa_id)
        except Exception:
            # Non-fatal - continue
            pass

        return True

    async def get_health_status(self, esa_id: str) -> Dict[str, Any]:
        """
        Get detailed health status for an ESA.

        Args:
            esa_id: ESA identifier

        Returns:
            Health status dictionary

        Raises:
            ESANotFoundError: If ESA not found
        """
        registration = self._registrations.get(esa_id)
        if not registration:
            raise ESANotFoundError(esa_id)

        # Perform health check
        health = await registration.esa.health_check()

        # Update registration
        registration.last_health_check = datetime.now(timezone.utc)
        registration.health_status = "healthy" if health["healthy"] else "unhealthy"

        return health

    async def get_all_health_statuses(self) -> Dict[str, Dict[str, Any]]:
        """
        Get health status for all registered ESAs.

        Returns:
            Dictionary mapping esa_id to health status
        """
        statuses = {}

        for esa_id in self._registrations.keys():
            try:
                statuses[esa_id] = await self.get_health_status(esa_id)
            except Exception as e:
                statuses[esa_id] = {
                    "healthy": False,
                    "error": str(e),
                    "system_id": esa_id,
                }

        return statuses

    def _detect_system_type(self, system_type_str: str) -> SystemType:
        """
        Detect SystemType enum from string.

        Args:
            system_type_str: System type as string

        Returns:
            SystemType enum value
        """
        system_type_str = system_type_str.lower()

        # Direct mapping
        for st in SystemType:
            if st.value == system_type_str:
                return st

        # Fuzzy matching
        if (
            "database" in system_type_str
            or "postgresql" in system_type_str
            or "mysql" in system_type_str
            or "sqlite" in system_type_str
            or "mongodb" in system_type_str
            or "sql" in system_type_str
        ):
            return SystemType.DATABASE

        if (
            "rest" in system_type_str
            or "api" in system_type_str
            or "http" in system_type_str
        ):
            return SystemType.REST_API

        if "soap" in system_type_str or "wsdl" in system_type_str:
            return SystemType.SOAP_SERVICE

        if (
            "file" in system_type_str
            or "fs" in system_type_str
            or "storage" in system_type_str
        ):
            return SystemType.FILE_SYSTEM

        if (
            "queue" in system_type_str
            or "mq" in system_type_str
            or "kafka" in system_type_str
            or "rabbitmq" in system_type_str
            or "sqs" in system_type_str
        ):
            return SystemType.MESSAGE_QUEUE

        if (
            "cloud" in system_type_str
            or "aws" in system_type_str
            or "azure" in system_type_str
            or "gcp" in system_type_str
        ):
            return SystemType.CLOUD_SERVICE

        if (
            "ldap" in system_type_str
            or "active directory" in system_type_str
            or "ad" in system_type_str
        ):
            return SystemType.LDAP

        if (
            "email" in system_type_str
            or "smtp" in system_type_str
            or "imap" in system_type_str
        ):
            return SystemType.EMAIL_SERVER

        return SystemType.UNKNOWN

    def _detect_system_type_from_connection(self, connection_string: str) -> SystemType:
        """
        Detect system type from connection string.

        Args:
            connection_string: Connection string to analyze

        Returns:
            Detected SystemType
        """
        conn_lower = connection_string.lower()

        # Database connection strings
        if (
            re.match(r"^postgresql://", conn_lower)
            or re.match(r"^postgres://", conn_lower)
            or re.match(r"^mysql://", conn_lower)
            or re.match(r"^sqlite://", conn_lower)
            or re.match(r"^mongodb://", conn_lower)
            or re.match(r"^oracle://", conn_lower)
            or re.match(r"^mssql://", conn_lower)
        ):
            return SystemType.DATABASE

        # REST API endpoints
        if re.match(r"^https?://", conn_lower):
            return SystemType.REST_API

        # File system paths
        if (
            re.match(r"^file://", conn_lower)
            or re.match(r"^/", conn_lower)
            or re.match(r"^[a-z]:\\", conn_lower, re.IGNORECASE)
        ):
            return SystemType.FILE_SYSTEM

        # Message queue connections
        if (
            re.match(r"^amqp://", conn_lower)
            or re.match(r"^kafka://", conn_lower)
            or re.match(r"^sqs://", conn_lower)
        ):
            return SystemType.MESSAGE_QUEUE

        # LDAP
        if re.match(r"^ldaps?://", conn_lower):
            return SystemType.LDAP

        # Email
        if re.match(r"^smtp://", conn_lower) or re.match(r"^imaps?://", conn_lower):
            return SystemType.EMAIL_SERVER

        return SystemType.UNKNOWN

    async def _health_monitoring_loop(self) -> None:
        """
        Background task for periodic health monitoring.

        Runs continuously, checking health of all registered ESAs
        at the configured interval.
        """
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)

                # Check health for all ESAs
                for esa_id in list(self._registrations.keys()):
                    try:
                        await self.get_health_status(esa_id)
                    except Exception:
                        # Continue to next ESA on error
                        pass

            except asyncio.CancelledError:
                break
            except Exception:
                # Log error and continue
                pass

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get registry statistics.

        Returns:
            Dictionary with registry statistics
        """
        total = len(self._registrations)
        healthy = sum(
            1 for r in self._registrations.values() if r.health_status == "healthy"
        )
        unhealthy = sum(
            1 for r in self._registrations.values() if r.health_status == "unhealthy"
        )
        unknown = total - healthy - unhealthy

        # Count by type
        by_type = {}
        for system_type, esa_ids in self._type_index.items():
            if esa_ids:
                by_type[system_type.value] = len(esa_ids)

        return {
            "total_registered": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "unknown": unknown,
            "by_type": by_type,
            "health_monitoring_enabled": self.enable_health_monitoring,
        }
