"""Edge state management for distributed stateful operations."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from kailash.edge.location import EdgeLocation
from kailash.nodes.base import NodeParameter, register_node

from .base import EdgeNode


class StateOperation(Enum):
    """Operations for state management."""

    GET = "get"
    SET = "set"
    UPDATE = "update"
    DELETE = "delete"
    INCREMENT = "increment"
    APPEND = "append"
    LOCK = "lock"
    UNLOCK = "unlock"


@register_node()
class EdgeStateMachine(EdgeNode):
    """Distributed state machine with global uniqueness guarantees.

    Similar to Cloudflare Durable Objects - ensures single instance
    globally for a given state ID with automatic edge affinity.
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "state_id": NodeParameter(
                name="state_id",
                type=str,
                required=True,
                description="Unique identifier for this state instance",
            ),
            "operation": NodeParameter(
                name="operation",
                type=str,
                default="get",
                required=False,
                description="State operation (get|set|update|delete|increment|append|lock|unlock)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="State key for operations",
            ),
            "value": NodeParameter(
                name="value",
                type=object,  # Can be any type
                required=False,
                description="Value to set/append",
            ),
            "update_fn": NodeParameter(
                name="update_fn",
                type=object,  # Will be validated as callable
                required=False,
                description="Update function for update operations",
            ),
            "increment": NodeParameter(
                name="increment",
                type=int,
                default=1,
                required=False,
                description="Amount to increment by",
            ),
            "lock_name": NodeParameter(
                name="lock_name",
                type=str,
                required=False,
                description="Name of lock to acquire/release",
            ),
            "timeout_ms": NodeParameter(
                name="timeout_ms",
                type=int,
                default=30000,
                required=False,
                description="Lock timeout in milliseconds",
            ),
            "lease_duration_ms": NodeParameter(
                name="lease_duration_ms",
                type=int,
                default=30000,
                required=False,
                description="Lease duration for global lock (ms)",
            ),
            "enable_persistence": NodeParameter(
                name="enable_persistence",
                type=bool,
                default=True,
                required=False,
                description="Whether to persist state to durable storage",
            ),
            "enable_replication": NodeParameter(
                name="enable_replication",
                type=bool,
                default=True,
                required=False,
                description="Whether to replicate state for availability",
            ),
        }

    # Class-level registry for global uniqueness
    _global_instances: Dict[str, "EdgeStateMachine"] = {}
    _global_locks: Dict[str, Dict[str, Any]] = {}

    def __init__(self, **config):
        """Initialize edge state machine."""
        self.state_id = config.get("state_id")
        if not self.state_id:
            raise ValueError("state_id is required for EdgeStateMachine")

        super().__init__(**config)

        # Instance state
        self.state_data: Dict[str, Any] = {}
        self.state_metadata: Dict[str, Any] = {
            "created_at": datetime.now(UTC).isoformat(),
            "version": 0,
            "last_modified": datetime.now(UTC).isoformat(),
            "access_count": 0,
        }

        # Locks and leases
        self.local_locks: Set[str] = set()
        self.lease_expiry: Optional[datetime] = None

        # Replication tracking
        self.replica_edges: List[EdgeLocation] = []
        self.is_primary = False
        self._background_tasks: List[asyncio.Task] = []

    async def initialize(self):
        """Initialize with global uniqueness check."""
        # Initialize parent edge infrastructure
        await super().initialize()

        # Ensure single global instance
        await self._ensure_single_instance()

        # Load persisted state if exists
        if self.config.get("enable_persistence", True):
            await self._load_persisted_state()

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute state operation."""
        operation = StateOperation(kwargs.get("operation", "get"))

        # Check if we're still the primary instance
        if not await self._verify_primary_status():
            # Redirect to current primary
            primary_edge = await self._find_primary_instance()
            return {
                "success": False,
                "redirect": True,
                "primary_edge": primary_edge.name if primary_edge else None,
                "message": "State instance has moved to different edge",
            }

        # Update access metadata
        self.state_metadata["access_count"] += 1
        self.state_metadata["last_accessed"] = datetime.now(UTC).isoformat()

        # Handle operation
        if operation == StateOperation.GET:
            return await self._handle_get(kwargs)
        elif operation == StateOperation.SET:
            return await self._handle_set(kwargs)
        elif operation == StateOperation.UPDATE:
            return await self._handle_update(kwargs)
        elif operation == StateOperation.DELETE:
            return await self._handle_delete(kwargs)
        elif operation == StateOperation.INCREMENT:
            return await self._handle_increment(kwargs)
        elif operation == StateOperation.APPEND:
            return await self._handle_append(kwargs)
        elif operation == StateOperation.LOCK:
            return await self._handle_lock(kwargs)
        elif operation == StateOperation.UNLOCK:
            return await self._handle_unlock(kwargs)
        else:
            raise ValueError(f"Unknown operation: {operation}")

    async def _ensure_single_instance(self):
        """Ensure only one instance exists globally for this state_id."""
        # Try to acquire global lock
        lock_acquired = await self._acquire_global_lock()

        if not lock_acquired:
            # Another instance exists
            existing_edge = await self._find_primary_instance()
            if existing_edge:
                raise RuntimeError(
                    f"State instance {self.state_id} already exists "
                    f"on edge {existing_edge.name}"
                )

        # Register as global instance
        EdgeStateMachine._global_instances[self.state_id] = self
        self.is_primary = True

        # Set edge affinity for this state
        self._set_edge_affinity()

    async def _acquire_global_lock(self) -> bool:
        """Acquire global lock for state_id."""
        lock_key = f"state:{self.state_id}"

        # Check if lock exists
        if lock_key in EdgeStateMachine._global_locks:
            lock_info = EdgeStateMachine._global_locks[lock_key]

            # Check if lock expired
            if datetime.now(UTC) < lock_info["expiry"]:
                return False

        # Acquire lock
        lease_duration_ms = self.config.get("lease_duration_ms", 30000)
        expiry = datetime.now(UTC) + timedelta(milliseconds=lease_duration_ms)

        EdgeStateMachine._global_locks[lock_key] = {
            "owner": self.current_edge.name if self.current_edge else "unknown",
            "expiry": expiry,
            "state_id": self.state_id,
        }

        self.lease_expiry = expiry

        # Start lease renewal task
        self._lease_renewal_task = asyncio.create_task(self._renew_lease())

        return True

    async def _renew_lease(self):
        """Periodically renew global lock lease."""
        lease_duration_ms = self.config.get("lease_duration_ms", 30000)
        renewal_interval = lease_duration_ms * 0.5 / 1000  # Renew at 50%

        while self.is_primary:
            await asyncio.sleep(renewal_interval)

            if self.is_primary and self.lease_expiry:
                # Extend lease
                self.lease_expiry = datetime.now(UTC) + timedelta(
                    milliseconds=lease_duration_ms
                )

                lock_key = f"state:{self.state_id}"
                if lock_key in EdgeStateMachine._global_locks:
                    EdgeStateMachine._global_locks[lock_key][
                        "expiry"
                    ] = self.lease_expiry

    def _set_edge_affinity(self):
        """Set edge affinity based on state_id hash."""
        # Use consistent hashing to determine preferred edge
        state_hash = hashlib.md5(self.state_id.encode()).hexdigest()
        hash_value = int(state_hash[:8], 16)

        # Get all edges and sort by name for consistency
        all_edges = sorted(self.edge_discovery.get_all_edges(), key=lambda e: e.name)

        if all_edges:
            # Select edge based on hash
            preferred_index = hash_value % len(all_edges)
            self.preferred_locations = [all_edges[preferred_index].name]

    async def _find_primary_instance(self) -> Optional[EdgeLocation]:
        """Find which edge hosts the primary instance."""
        # In production, this would query a distributed registry
        lock_key = f"state:{self.state_id}"

        if lock_key in EdgeStateMachine._global_locks:
            lock_info = EdgeStateMachine._global_locks[lock_key]
            edge_name = lock_info.get("owner")

            if edge_name:
                return self.edge_discovery.get_edge(edge_name)

        return None

    async def _verify_primary_status(self) -> bool:
        """Verify we're still the primary instance."""
        if not self.is_primary:
            return False

        # Check if lease is still valid
        if self.lease_expiry and datetime.now(UTC) > self.lease_expiry:
            self.is_primary = False
            return False

        return True

    async def _handle_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle GET operation."""
        key = params.get("key")

        if key:
            # Get specific key
            value = self.state_data.get(key)
            return {
                "success": True,
                "key": key,
                "value": value,
                "exists": key in self.state_data,
                "metadata": self.state_metadata,
            }
        else:
            # Get entire state
            return {
                "success": True,
                "state": self.state_data.copy(),
                "metadata": self.state_metadata,
            }

    async def _handle_set(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SET operation."""
        key = params.get("key")
        value = params.get("value")

        if not key:
            raise ValueError("SET requires 'key'")

        # Update state
        old_value = self.state_data.get(key)
        self.state_data[key] = value

        # Update metadata
        self.state_metadata["version"] += 1
        self.state_metadata["last_modified"] = datetime.now(UTC).isoformat()

        # Persist if enabled
        if self.config.get("enable_persistence", True):
            await self._persist_state()

        # Replicate if enabled
        if self.config.get("enable_replication", True):
            task = asyncio.create_task(self._replicate_state())
            self._background_tasks.append(task)

        return {
            "success": True,
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "version": self.state_metadata["version"],
        }

    async def _handle_update(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle UPDATE operation with function."""
        key = params.get("key")
        update_fn = params.get("update_fn")

        if not key or not callable(update_fn):
            raise ValueError("UPDATE requires 'key' and callable 'update_fn'")

        # Get current value
        current_value = self.state_data.get(key)

        # Apply update function
        try:
            new_value = update_fn(current_value)
        except Exception as e:
            return {"success": False, "error": f"Update function failed: {str(e)}"}

        # Update state
        self.state_data[key] = new_value

        # Update metadata
        self.state_metadata["version"] += 1
        self.state_metadata["last_modified"] = datetime.now(UTC).isoformat()

        # Persist and replicate
        if self.config.get("enable_persistence", True):
            await self._persist_state()

        if self.config.get("enable_replication", True):
            task = asyncio.create_task(self._replicate_state())
            self._background_tasks.append(task)

        return {
            "success": True,
            "key": key,
            "old_value": current_value,
            "new_value": new_value,
            "version": self.state_metadata["version"],
        }

    async def _handle_delete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle DELETE operation."""
        key = params.get("key")

        if not key:
            raise ValueError("DELETE requires 'key'")

        # Delete from state
        old_value = self.state_data.pop(key, None)

        # Update metadata
        self.state_metadata["version"] += 1
        self.state_metadata["last_modified"] = datetime.now(UTC).isoformat()

        # Persist and replicate
        if self.config.get("enable_persistence", True):
            await self._persist_state()

        if self.config.get("enable_replication", True):
            task = asyncio.create_task(self._replicate_state())
            self._background_tasks.append(task)

        return {
            "success": True,
            "key": key,
            "deleted": old_value is not None,
            "old_value": old_value,
            "version": self.state_metadata["version"],
        }

    async def _handle_increment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle INCREMENT operation for numeric values."""
        key = params.get("key")
        increment = params.get("increment", 1)

        if not key:
            raise ValueError("INCREMENT requires 'key'")

        # Get current value
        current_value = self.state_data.get(key, 0)

        # Validate numeric
        if not isinstance(current_value, (int, float)):
            return {
                "success": False,
                "error": f"Cannot increment non-numeric value: {type(current_value)}",
            }

        # Increment
        new_value = current_value + increment
        self.state_data[key] = new_value

        # Update metadata
        self.state_metadata["version"] += 1
        self.state_metadata["last_modified"] = datetime.now(UTC).isoformat()

        # Persist and replicate
        if self.config.get("enable_persistence", True):
            await self._persist_state()

        if self.config.get("enable_replication", True):
            task = asyncio.create_task(self._replicate_state())
            self._background_tasks.append(task)

        return {
            "success": True,
            "key": key,
            "old_value": current_value,
            "new_value": new_value,
            "increment": increment,
            "version": self.state_metadata["version"],
        }

    async def _handle_append(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle APPEND operation for list values."""
        key = params.get("key")
        value = params.get("value")

        if not key:
            raise ValueError("APPEND requires 'key'")

        # Get current value
        current_value = self.state_data.get(key, [])

        # Ensure it's a list
        if not isinstance(current_value, list):
            return {
                "success": False,
                "error": f"Cannot append to non-list value: {type(current_value)}",
            }

        # Append
        new_value = current_value + [value]
        self.state_data[key] = new_value

        # Update metadata
        self.state_metadata["version"] += 1
        self.state_metadata["last_modified"] = datetime.now(UTC).isoformat()

        # Persist and replicate
        if self.config.get("enable_persistence", True):
            await self._persist_state()

        if self.config.get("enable_replication", True):
            task = asyncio.create_task(self._replicate_state())
            self._background_tasks.append(task)

        return {
            "success": True,
            "key": key,
            "list_size": len(new_value),
            "appended_value": value,
            "version": self.state_metadata["version"],
        }

    async def _handle_lock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LOCK operation for distributed locking."""
        lock_name = params.get("lock_name")
        timeout_ms = params.get("timeout_ms", 5000)

        if not lock_name:
            raise ValueError("LOCK requires 'lock_name'")

        # Check if already locked
        if lock_name in self.local_locks:
            return {
                "success": False,
                "lock_name": lock_name,
                "error": "Lock already held",
            }

        # Acquire lock
        self.local_locks.add(lock_name)

        # Set up auto-release
        task = asyncio.create_task(self._auto_release_lock(lock_name, timeout_ms))
        self._background_tasks.append(task)

        return {
            "success": True,
            "lock_name": lock_name,
            "timeout_ms": timeout_ms,
            "holder": self.current_edge.name if self.current_edge else "unknown",
        }

    async def _handle_unlock(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle UNLOCK operation."""
        lock_name = params.get("lock_name")

        if not lock_name:
            raise ValueError("UNLOCK requires 'lock_name'")

        # Release lock
        released = lock_name in self.local_locks
        self.local_locks.discard(lock_name)

        return {"success": True, "lock_name": lock_name, "released": released}

    async def _auto_release_lock(self, lock_name: str, timeout_ms: int):
        """Auto-release lock after timeout."""
        await asyncio.sleep(timeout_ms / 1000)
        self.local_locks.discard(lock_name)

    async def _persist_state(self):
        """Persist state to durable storage."""
        # In production, this would write to distributed storage
        # For now, simulate with delay
        await asyncio.sleep(0.01)

        self.logger.debug(
            f"Persisted state for {self.state_id} "
            f"(version: {self.state_metadata['version']})"
        )

    async def _load_persisted_state(self):
        """Load state from durable storage."""
        # In production, this would read from distributed storage
        # For now, start with empty state
        pass

    async def _replicate_state(self):
        """Replicate state to backup edges."""
        if not self.config.get("enable_replication", True):
            return

        # Select replica edges if not already done
        if not self.replica_edges:
            await self._select_replica_edges()

        # Replicate to each edge
        replication_tasks = []
        for edge in self.replica_edges:
            replication_tasks.append(self._replicate_to_edge(edge))

        await asyncio.gather(*replication_tasks, return_exceptions=True)

    async def _select_replica_edges(self):
        """Select edges for state replication."""
        all_edges = self.edge_discovery.get_all_edges()

        # Remove current edge
        candidate_edges = [
            e
            for e in all_edges
            if e.name != (self.current_edge.name if self.current_edge else None)
        ]

        # Select based on different regions for availability
        regions_seen = set()
        for edge in candidate_edges:
            if edge.region not in regions_seen:
                self.replica_edges.append(edge)
                regions_seen.add(edge.region)

                if len(self.replica_edges) >= 2:  # Keep 2 replicas
                    break

    async def _replicate_to_edge(self, edge: EdgeLocation):
        """Replicate state to specific edge."""
        # In production, this would use edge-to-edge communication
        await asyncio.sleep(0.02)  # Simulate replication

        self.logger.debug(f"Replicated state {self.state_id} to edge {edge.name}")

    async def migrate_to_edge(
        self, target_edge: EdgeLocation, state_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Migrate state machine to different edge."""
        if not self.is_primary:
            return False

        try:
            # Transfer primary status
            self.is_primary = False

            # Update global registry
            lock_key = f"state:{self.state_id}"
            if lock_key in EdgeStateMachine._global_locks:
                EdgeStateMachine._global_locks[lock_key]["owner"] = target_edge.name

            # Persist final state
            await self._persist_state()

            # Clean up
            if self.state_id in EdgeStateMachine._global_instances:
                del EdgeStateMachine._global_instances[self.state_id]

            return True

        except Exception as e:
            self.logger.error(f"State migration failed: {e}")
            self.is_primary = True  # Restore primary status
            return False

    async def cleanup(self):
        """Cleanup resources including background tasks."""
        # Cancel lease renewal task if running
        if hasattr(self, "_lease_renewal_task") and self._lease_renewal_task:
            self._lease_renewal_task.cancel()
            try:
                await self._lease_renewal_task
            except asyncio.CancelledError:
                pass

        # Cancel all background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Mark as not primary to stop renewal loop
        self.is_primary = False
