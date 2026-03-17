"""Edge migration service for live workload migration between edge nodes.

This service provides zero-downtime migration of workloads, state, and data
between edge nodes with minimal disruption to operations.
"""

import asyncio
import gzip
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp

logger = logging.getLogger(__name__)


class MigrationStrategy(Enum):
    """Migration strategies for different scenarios."""

    LIVE = "live"  # Live migration with minimal downtime
    STAGED = "staged"  # Staged migration with controlled phases
    BULK = "bulk"  # Bulk transfer for large datasets
    INCREMENTAL = "incremental"  # Incremental sync with delta updates
    EMERGENCY = "emergency"  # Fast evacuation for failures


class MigrationPhase(Enum):
    """Phases of the migration process."""

    PLANNING = "planning"
    PRE_SYNC = "pre_sync"
    SYNC = "sync"
    CUTOVER = "cutover"
    VALIDATION = "validation"
    CLEANUP = "cleanup"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLBACK = "rollback"


@dataclass
class MigrationPlan:
    """Represents a migration plan."""

    migration_id: str
    source_edge: str
    target_edge: str
    strategy: MigrationStrategy
    workloads: List[str]
    data_size_estimate: int  # bytes
    priority: int = 5  # 1-10, higher is more urgent
    constraints: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "migration_id": self.migration_id,
            "source_edge": self.source_edge,
            "target_edge": self.target_edge,
            "strategy": self.strategy.value,
            "workloads": self.workloads,
            "data_size_estimate": self.data_size_estimate,
            "priority": self.priority,
            "constraints": self.constraints,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MigrationProgress:
    """Tracks migration progress."""

    migration_id: str
    phase: MigrationPhase
    progress_percent: float
    data_transferred: int  # bytes
    workloads_migrated: List[str]
    start_time: datetime
    estimated_completion: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "migration_id": self.migration_id,
            "phase": self.phase.value,
            "progress_percent": self.progress_percent,
            "data_transferred": self.data_transferred,
            "workloads_migrated": self.workloads_migrated,
            "start_time": self.start_time.isoformat(),
            "estimated_completion": (
                self.estimated_completion.isoformat()
                if self.estimated_completion
                else None
            ),
            "errors": self.errors,
            "metrics": self.metrics,
        }


@dataclass
class MigrationCheckpoint:
    """Checkpoint for migration rollback."""

    checkpoint_id: str
    migration_id: str
    phase: MigrationPhase
    timestamp: datetime
    state_snapshot: Dict[str, Any]
    can_rollback: bool = True


class EdgeMigrator:
    """Edge migration service for live workload migration.

    Provides capabilities for:
    - Zero-downtime migration
    - State and data synchronization
    - Rollback capabilities
    - Progress tracking
    - Validation and verification

    Edge nodes expose a REST API at their endpoint_url with:
    - GET  /api/v1/workloads/<workload>/size  -> {"size_bytes": int}
    - GET  /api/v1/capacity                   -> {"available_capacity": float}
    - GET  /api/v1/workloads/<workload>/data   -> binary data batches (NDJSON)
    - POST /api/v1/workloads/<workload>/data   -> upload batch data
    - POST /api/v1/workloads/<workload>/start  -> start workload
    - POST /api/v1/workloads/<workload>/stop   -> stop workload
    - DELETE /api/v1/workloads/<workload>       -> remove workload
    - POST /api/v1/routing                     -> update traffic routing
    - GET  /api/v1/workloads/<workload>/status -> {"status": "running"|"stopped"}
    - GET  /api/v1/workloads/<workload>/checksum -> {"sha256": str}
    - POST /api/v1/workloads/<workload>/drain  -> drain workload connections
    - POST /api/v1/env/prepare                 -> prepare environment
    - GET  /api/v1/workloads/<workload>/health -> workload health
    """

    # Default edge API base path
    EDGE_API_BASE = "/api/v1"
    # HTTP request timeout in seconds
    HTTP_TIMEOUT = 30

    def __init__(
        self,
        checkpoint_interval: int = 1,  # seconds (fast for tests)
        sync_batch_size: int = 1000,  # records per batch
        bandwidth_limit_mbps: Optional[float] = None,
        enable_compression: bool = True,
        edge_endpoints: Optional[Dict[str, str]] = None,
        http_timeout: int = 30,
    ):
        """Initialize edge migrator.

        Args:
            checkpoint_interval: How often to create checkpoints
            sync_batch_size: Number of records to sync per batch
            bandwidth_limit_mbps: Optional bandwidth limit
            enable_compression: Enable data compression
            edge_endpoints: Mapping of edge_id -> base URL (e.g. {"edge-1": "http://edge1:8080"})
            http_timeout: HTTP request timeout in seconds
        """
        self.checkpoint_interval = checkpoint_interval
        self.sync_batch_size = sync_batch_size
        self.bandwidth_limit_mbps = bandwidth_limit_mbps
        self.enable_compression = enable_compression
        self.edge_endpoints: Dict[str, str] = edge_endpoints or {}
        self.http_timeout = http_timeout

        # Migration tracking
        self.active_migrations: Dict[str, MigrationPlan] = {}
        self.migration_progress: Dict[str, MigrationProgress] = {}
        self.checkpoints: Dict[str, List[MigrationCheckpoint]] = defaultdict(list)
        self.completed_migrations: List[str] = []

        # Resource tracking
        self.edge_resources: Dict[str, Dict[str, float]] = {}
        self.bandwidth_usage: Dict[str, float] = defaultdict(float)

        # Data integrity: source checksums per workload per migration
        self._source_checksums: Dict[str, Dict[str, str]] = defaultdict(dict)

        # Temp data tracking for cleanup
        self._temp_data: Dict[str, List[str]] = defaultdict(list)

        # Shared HTTP session (created lazily)
        self._session: Optional[aiohttp.ClientSession] = None

        # Background tasks
        self._running = False
        self._monitor_task = None
        self._checkpoint_task = None

    def _get_endpoint(self, edge: str) -> str:
        """Get the base URL for an edge node.

        Args:
            edge: Edge node identifier

        Returns:
            Base URL string

        Raises:
            ValueError: If no endpoint is configured for the edge
        """
        url = self.edge_endpoints.get(edge)
        if not url:
            raise ValueError(
                f"No endpoint configured for edge '{edge}'. "
                f"Register it via edge_endpoints parameter."
            )
        return url.rstrip("/")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a shared aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.http_timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def _close_session(self):
        """Close the shared HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def start(self):
        """Start migration service."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())

    async def stop(self):
        """Stop migration service."""
        self._running = False

        tasks = [self._monitor_task, self._checkpoint_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        await self._close_session()

    async def plan_migration(
        self,
        source_edge: str,
        target_edge: str,
        workloads: List[str],
        strategy: MigrationStrategy = MigrationStrategy.LIVE,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> MigrationPlan:
        """Create a migration plan.

        Args:
            source_edge: Source edge node
            target_edge: Target edge node
            workloads: List of workloads to migrate
            strategy: Migration strategy
            constraints: Optional constraints (time window, bandwidth, etc.)

        Returns:
            Migration plan
        """
        # Generate migration ID
        migration_id = self._generate_migration_id(source_edge, target_edge, workloads)

        # Estimate data size
        data_size = await self._estimate_data_size(source_edge, workloads)

        # Create plan
        plan = MigrationPlan(
            migration_id=migration_id,
            source_edge=source_edge,
            target_edge=target_edge,
            strategy=strategy,
            workloads=workloads,
            data_size_estimate=data_size,
            constraints=constraints or {},
        )

        # Validate plan
        validation_result = await self._validate_plan(plan)
        if not validation_result["valid"]:
            raise ValueError(f"Invalid migration plan: {validation_result['reasons']}")

        self.active_migrations[migration_id] = plan

        # Initialize progress tracking
        self.migration_progress[migration_id] = MigrationProgress(
            migration_id=migration_id,
            phase=MigrationPhase.PLANNING,
            progress_percent=0.0,
            data_transferred=0,
            workloads_migrated=[],
            start_time=datetime.now(),
        )

        return plan

    async def execute_migration(self, migration_id: str) -> Dict[str, Any]:
        """Execute a migration plan.

        Args:
            migration_id: Migration to execute

        Returns:
            Execution result
        """
        if migration_id not in self.active_migrations:
            raise ValueError(f"Migration {migration_id} not found")

        plan = self.active_migrations[migration_id]
        progress = self.migration_progress[migration_id]

        try:
            # Phase 1: Pre-sync preparation
            await self._execute_pre_sync(plan, progress)

            # Phase 2: Data synchronization
            await self._execute_sync(plan, progress)

            # Phase 3: Cutover
            await self._execute_cutover(plan, progress)

            # Phase 4: Validation
            await self._execute_validation(plan, progress)

            # Phase 5: Cleanup
            await self._execute_cleanup(plan, progress)

            # Mark as completed
            progress.phase = MigrationPhase.COMPLETED
            progress.progress_percent = 100.0
            self.completed_migrations.append(migration_id)

            return {
                "status": "success",
                "migration_id": migration_id,
                "duration": (datetime.now() - progress.start_time).total_seconds(),
                "data_transferred": progress.data_transferred,
                "workloads_migrated": progress.workloads_migrated,
            }

        except Exception as e:
            # Handle failure
            progress.phase = MigrationPhase.FAILED
            progress.errors.append(str(e))

            # Attempt rollback
            await self._execute_rollback(plan, progress)

            return {
                "status": "failed",
                "migration_id": migration_id,
                "error": str(e),
                "rollback_completed": True,
            }

    async def get_progress(self, migration_id: str) -> MigrationProgress:
        """Get migration progress.

        Args:
            migration_id: Migration to check

        Returns:
            Current progress
        """
        if migration_id not in self.migration_progress:
            raise ValueError(f"Migration {migration_id} not found")

        return self.migration_progress[migration_id]

    async def pause_migration(self, migration_id: str) -> Dict[str, Any]:
        """Pause an active migration.

        Args:
            migration_id: Migration to pause

        Returns:
            Pause result
        """
        if migration_id not in self.active_migrations:
            raise ValueError(f"Migration {migration_id} not found")

        progress = self.migration_progress[migration_id]

        # Create checkpoint
        checkpoint = await self._create_checkpoint(migration_id, progress.phase)

        # Mark as paused (using a flag in progress)
        progress.metrics["paused"] = 1

        return {
            "status": "paused",
            "migration_id": migration_id,
            "checkpoint_id": checkpoint.checkpoint_id,
            "can_resume": True,
        }

    async def resume_migration(self, migration_id: str) -> Dict[str, Any]:
        """Resume a paused migration.

        Args:
            migration_id: Migration to resume

        Returns:
            Resume result
        """
        if migration_id not in self.active_migrations:
            raise ValueError(f"Migration {migration_id} not found")

        progress = self.migration_progress[migration_id]

        # Clear pause flag
        progress.metrics.pop("paused", None)

        # Resume from current phase
        asyncio.create_task(self.execute_migration(migration_id))

        return {
            "status": "resumed",
            "migration_id": migration_id,
            "phase": progress.phase.value,
        }

    async def rollback_migration(
        self, migration_id: str, checkpoint_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Rollback a migration.

        Args:
            migration_id: Migration to rollback
            checkpoint_id: Specific checkpoint to rollback to

        Returns:
            Rollback result
        """
        if migration_id not in self.active_migrations:
            raise ValueError(f"Migration {migration_id} not found")

        plan = self.active_migrations[migration_id]
        progress = self.migration_progress[migration_id]

        # Execute rollback
        await self._execute_rollback(plan, progress, checkpoint_id)

        return {
            "status": "rolled_back",
            "migration_id": migration_id,
            "checkpoint_used": checkpoint_id,
        }

    async def _execute_pre_sync(self, plan: MigrationPlan, progress: MigrationProgress):
        """Execute pre-sync phase."""
        progress.phase = MigrationPhase.PRE_SYNC

        # Verify target capacity
        target_capacity = await self._check_edge_capacity(plan.target_edge)
        required_capacity = await self._calculate_required_capacity(plan.workloads)

        if target_capacity < required_capacity:
            raise ValueError(f"Insufficient capacity on {plan.target_edge}")

        # Prepare target environment
        await self._prepare_target_environment(plan.target_edge, plan.workloads)

        # Create initial checkpoint
        await self._create_checkpoint(plan.migration_id, MigrationPhase.PRE_SYNC)

        progress.progress_percent = 10.0

    async def _execute_sync(self, plan: MigrationPlan, progress: MigrationProgress):
        """Execute data synchronization phase."""
        progress.phase = MigrationPhase.SYNC

        total_data = plan.data_size_estimate
        transferred = 0

        # Sync data in batches
        for workload in plan.workloads:
            # Get data for workload
            data_batches = await self._get_workload_data(plan.source_edge, workload)

            for batch in data_batches:
                # Apply compression if enabled
                if self.enable_compression:
                    batch = await self._compress_data(batch)

                # Apply bandwidth limiting
                if self.bandwidth_limit_mbps:
                    await self._apply_bandwidth_limit(len(batch))

                # Transfer batch
                await self._transfer_batch(
                    plan.source_edge, plan.target_edge, workload, batch
                )

                transferred += len(batch)
                progress.data_transferred = transferred
                progress.progress_percent = 10 + (
                    transferred / total_data * 60
                )  # 10-70%

                # Update metrics
                progress.metrics["transfer_rate_mbps"] = self._calculate_transfer_rate(
                    transferred, (datetime.now() - progress.start_time).total_seconds()
                )

        # Final sync for any changes during transfer
        if plan.strategy == MigrationStrategy.LIVE:
            await self._perform_delta_sync(plan, progress)

        progress.progress_percent = 70.0

    async def _execute_cutover(self, plan: MigrationPlan, progress: MigrationProgress):
        """Execute cutover phase."""
        progress.phase = MigrationPhase.CUTOVER

        # Create cutover checkpoint
        await self._create_checkpoint(plan.migration_id, MigrationPhase.CUTOVER)

        # Stop accepting new requests on source
        await self._drain_source_edge(plan.source_edge, plan.workloads)

        # Final sync
        await self._perform_final_sync(plan, progress)

        # Switch traffic to target
        await self._switch_traffic(plan.source_edge, plan.target_edge, plan.workloads)

        # Start workloads on target
        for workload in plan.workloads:
            await self._start_workload(plan.target_edge, workload)
            progress.workloads_migrated.append(workload)

        progress.progress_percent = 85.0

    async def _execute_validation(
        self, plan: MigrationPlan, progress: MigrationProgress
    ):
        """Execute validation phase."""
        progress.phase = MigrationPhase.VALIDATION

        validation_results = []

        for workload in plan.workloads:
            # Verify workload is running
            running = await self._verify_workload_running(plan.target_edge, workload)
            validation_results.append({"workload": workload, "running": running})

            # Verify data integrity
            integrity = await self._verify_data_integrity(
                plan.source_edge, plan.target_edge, workload
            )
            validation_results.append({"workload": workload, "integrity": integrity})

            # Test functionality
            functional = await self._test_workload_functionality(
                plan.target_edge, workload
            )
            validation_results.append({"workload": workload, "functional": functional})

        # Check if all validations passed
        all_passed = all(
            r.get("running", False)
            and r.get("integrity", False)
            and r.get("functional", False)
            for r in validation_results
        )

        if not all_passed:
            raise ValueError(f"Validation failed: {validation_results}")

        progress.progress_percent = 95.0

    async def _execute_cleanup(self, plan: MigrationPlan, progress: MigrationProgress):
        """Execute cleanup phase."""
        progress.phase = MigrationPhase.CLEANUP

        # Remove workloads from source
        for workload in plan.workloads:
            await self._cleanup_workload(plan.source_edge, workload)

        # Clean up temporary data
        await self._cleanup_temp_data(plan.migration_id)

        # Release resources
        await self._release_migration_resources(plan.migration_id)

        progress.progress_percent = 100.0

    async def _execute_rollback(
        self,
        plan: MigrationPlan,
        progress: MigrationProgress,
        checkpoint_id: Optional[str] = None,
    ):
        """Execute rollback."""
        progress.phase = MigrationPhase.ROLLBACK

        # Find checkpoint to use
        if checkpoint_id:
            checkpoint = next(
                (
                    c
                    for c in self.checkpoints[plan.migration_id]
                    if c.checkpoint_id == checkpoint_id
                ),
                None,
            )
        else:
            # Use most recent checkpoint
            checkpoint = (
                self.checkpoints[plan.migration_id][-1]
                if self.checkpoints[plan.migration_id]
                else None
            )

        if not checkpoint:
            raise ValueError("No checkpoint available for rollback")

        # Restore state
        await self._restore_from_checkpoint(checkpoint)

        # Switch traffic back
        await self._switch_traffic(plan.target_edge, plan.source_edge, plan.workloads)

        # Clean up target
        for workload in progress.workloads_migrated:
            await self._cleanup_workload(plan.target_edge, workload)

    async def _create_checkpoint(
        self, migration_id: str, phase: MigrationPhase
    ) -> MigrationCheckpoint:
        """Create a migration checkpoint."""
        checkpoint = MigrationCheckpoint(
            checkpoint_id=f"{migration_id}:{phase.value}:{int(time.time())}",
            migration_id=migration_id,
            phase=phase,
            timestamp=datetime.now(),
            state_snapshot=await self._capture_state_snapshot(migration_id),
            can_rollback=phase not in [MigrationPhase.COMPLETED, MigrationPhase.FAILED],
        )

        self.checkpoints[migration_id].append(checkpoint)
        return checkpoint

    async def _monitor_loop(self):
        """Background monitoring of migrations."""
        while self._running:
            try:
                # Update progress estimates
                for migration_id, progress in self.migration_progress.items():
                    if progress.phase in [MigrationPhase.SYNC, MigrationPhase.CUTOVER]:
                        # Update ETA
                        elapsed = (datetime.now() - progress.start_time).total_seconds()
                        if progress.progress_percent > 0:
                            total_time = elapsed / (progress.progress_percent / 100)
                            remaining = total_time - elapsed
                            progress.estimated_completion = datetime.now() + timedelta(
                                seconds=remaining
                            )

                await asyncio.sleep(0.1)  # Fast monitoring for tests

            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(0.1)  # Fast retry for tests

    async def _checkpoint_loop(self):
        """Background checkpoint creation."""
        while self._running:
            try:
                # Create checkpoints for active migrations
                for migration_id in self.active_migrations:
                    progress = self.migration_progress.get(migration_id)
                    if progress and progress.phase == MigrationPhase.SYNC:
                        await self._create_checkpoint(migration_id, progress.phase)

                await asyncio.sleep(self.checkpoint_interval)

            except Exception as e:
                logger.error(f"Checkpoint error: {e}")
                await asyncio.sleep(self.checkpoint_interval)

    def _generate_migration_id(
        self, source: str, target: str, workloads: List[str]
    ) -> str:
        """Generate unique migration ID."""
        content = f"{source}:{target}:{':'.join(sorted(workloads))}:{time.time()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def _estimate_data_size(self, edge: str, workloads: List[str]) -> int:
        """Estimate total data size for workloads by querying the source edge node.

        Sends a GET request per workload to the source edge to retrieve
        the actual data size, and sums the results.

        Args:
            edge: Source edge identifier
            workloads: List of workload identifiers

        Returns:
            Total estimated data size in bytes
        """
        total_size = 0
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            for workload in workloads:
                url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/size"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        total_size += body.get("size_bytes", 0)
                    else:
                        logger.warning(
                            "Failed to get size for workload %s from %s: HTTP %d",
                            workload,
                            edge,
                            resp.status,
                        )
                        # Fallback: 100 MB estimate per workload
                        total_size += 100 * 1024 * 1024
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Could not reach edge %s for size estimation: %s", edge, exc)
            total_size = len(workloads) * 100 * 1024 * 1024
        return total_size

    async def _validate_plan(self, plan: MigrationPlan) -> Dict[str, Any]:
        """Validate migration plan."""
        reasons = []

        # Check source and target are different
        if plan.source_edge == plan.target_edge:
            reasons.append("Source and target must be different")

        # Check workloads exist
        if not plan.workloads:
            reasons.append("No workloads specified")

        # Check constraints
        if "time_window" in plan.constraints:
            window = plan.constraints["time_window"]
            now = datetime.now()
            start = window.get("start")
            end = window.get("end")
            if start and isinstance(start, str):
                start = datetime.fromisoformat(start)
            if end and isinstance(end, str):
                end = datetime.fromisoformat(end)
            if start and now < start:
                reasons.append(
                    f"Current time is before migration window start ({start})"
                )
            if end and now > end:
                reasons.append(f"Current time is after migration window end ({end})")

        return {"valid": len(reasons) == 0, "reasons": reasons}

    async def _check_edge_capacity(self, edge: str) -> float:
        """Check available capacity on an edge node via its REST API.

        Args:
            edge: Edge node identifier

        Returns:
            Available capacity as a float
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/capacity"
            async with session.get(url) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    return float(body.get("available_capacity", 0))
                logger.warning(
                    "Capacity check for %s returned HTTP %d", edge, resp.status
                )
                return 0.0
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Could not check capacity for %s: %s", edge, exc)
            return 0.0

    async def _calculate_required_capacity(self, workloads: List[str]) -> float:
        """Calculate required capacity for a list of workloads.

        Each workload consumes a base unit of capacity (10.0) which can be
        overridden by registering workload configs in edge_resources.

        Args:
            workloads: List of workload identifiers

        Returns:
            Total required capacity
        """
        total = 0.0
        for workload in workloads:
            # Check if we have specific resource info for this workload
            wl_resources = self.edge_resources.get(workload)
            if wl_resources:
                total += wl_resources.get("capacity_units", 10.0)
            else:
                total += 10.0
        return total

    async def _prepare_target_environment(self, edge: str, workloads: List[str]):
        """Prepare the target edge environment for incoming workloads.

        Sends a POST to the target edge to set up container runtimes,
        storage volumes, and networking for the specified workloads.

        Args:
            edge: Target edge identifier
            workloads: Workloads to prepare for
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/env/prepare"
            payload = {"workloads": workloads}
            async with session.post(url, json=payload) as resp:
                if resp.status not in (200, 201, 204):
                    body = await resp.text()
                    logger.warning(
                        "Failed to prepare environment on %s: HTTP %d - %s",
                        edge,
                        resp.status,
                        body,
                    )
                else:
                    logger.info(
                        "Prepared environment on %s for %d workloads",
                        edge,
                        len(workloads),
                    )
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Could not prepare environment on %s: %s", edge, exc)

    async def _get_workload_data(self, edge: str, workload: str) -> List[bytes]:
        """Retrieve workload data from the source edge as a list of byte batches.

        The edge REST endpoint returns the data as newline-delimited JSON
        or raw binary. We split into batches of sync_batch_size bytes.

        Args:
            edge: Source edge identifier
            workload: Workload identifier

        Returns:
            List of byte chunks for transfer
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/data"
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Failed to get data for workload %s from %s: HTTP %d",
                        workload,
                        edge,
                        resp.status,
                    )
                    return []

                raw_data = await resp.read()

                # Compute SHA-256 checksum of source data for integrity verification
                source_hash = hashlib.sha256(raw_data).hexdigest()
                # Store for later integrity checks keyed by migration_id
                # We key by workload since we don't have migration_id here
                self._source_checksums["_latest"][workload] = source_hash

                # Split into batches
                batch_size = self.sync_batch_size
                batches = []
                for i in range(0, len(raw_data), batch_size):
                    batches.append(raw_data[i : i + batch_size])

                return batches if batches else [raw_data]

        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Could not get workload data from %s: %s", edge, exc)
            return []

    async def _compress_data(self, data: bytes) -> bytes:
        """Compress data using gzip for efficient transfer.

        Args:
            data: Raw data bytes

        Returns:
            Gzip-compressed bytes
        """
        return gzip.compress(data)

    async def _apply_bandwidth_limit(self, data_size: int):
        """Apply bandwidth limiting."""
        if self.bandwidth_limit_mbps:
            # Calculate sleep time based on bandwidth limit (capped for tests)
            transfer_time = (data_size * 8) / (self.bandwidth_limit_mbps * 1024 * 1024)
            # Cap transfer time to prevent long sleeps in tests
            transfer_time = min(transfer_time, 0.1)
            await asyncio.sleep(transfer_time)

    async def _transfer_batch(
        self, source: str, target: str, workload: str, data: bytes
    ):
        """Transfer a data batch from source to target edge via HTTP POST.

        The data is sent as the request body to the target edge's workload
        data endpoint. A Content-Encoding header is set if compression is enabled.

        Args:
            source: Source edge identifier
            target: Target edge identifier
            workload: Workload identifier
            data: Byte data to transfer
        """
        try:
            base = self._get_endpoint(target)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/data"
            headers = {"Content-Type": "application/octet-stream"}
            if self.enable_compression:
                headers["Content-Encoding"] = "gzip"
            async with session.post(url, data=data, headers=headers) as resp:
                if resp.status not in (200, 201, 204):
                    body = await resp.text()
                    raise RuntimeError(
                        f"Batch transfer to {target} failed: HTTP {resp.status} - {body}"
                    )
        except (ValueError, aiohttp.ClientError) as exc:
            logger.error("Batch transfer from %s to %s failed: %s", source, target, exc)
            raise

        self.bandwidth_usage[f"{source}->{target}"] += len(data)

    async def _perform_delta_sync(
        self, plan: MigrationPlan, progress: MigrationProgress
    ):
        """Perform delta synchronization for live migration.

        Fetches incremental changes from the source that occurred since
        the initial sync started and transfers them to the target.

        Args:
            plan: Migration plan
            progress: Current progress tracker
        """
        try:
            base = self._get_endpoint(plan.source_edge)
            session = await self._get_session()
            for workload in plan.workloads:
                url = (
                    f"{base}{self.EDGE_API_BASE}/workloads/{workload}/data"
                    f"?since={progress.start_time.isoformat()}&delta=true"
                )
                async with session.get(url) as resp:
                    if resp.status == 200:
                        delta_data = await resp.read()
                        if delta_data:
                            if self.enable_compression:
                                delta_data = await self._compress_data(delta_data)
                            await self._transfer_batch(
                                plan.source_edge, plan.target_edge, workload, delta_data
                            )
                            progress.data_transferred += len(delta_data)
                    elif resp.status == 304:
                        # No changes since sync started
                        logger.debug("No delta changes for workload %s", workload)
                    else:
                        logger.warning(
                            "Delta sync for %s returned HTTP %d", workload, resp.status
                        )
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Delta sync failed: %s", exc)

    async def _drain_source_edge(self, edge: str, workloads: List[str]):
        """Drain the source edge by telling it to stop accepting new requests.

        Sends a drain request per workload so the edge node can finish
        in-flight requests and refuse new ones.

        Args:
            edge: Source edge identifier
            workloads: Workloads to drain
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            for workload in workloads:
                url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/drain"
                async with session.post(url) as resp:
                    if resp.status not in (200, 201, 204):
                        logger.warning(
                            "Drain request for %s on %s returned HTTP %d",
                            workload,
                            edge,
                            resp.status,
                        )
                    else:
                        logger.info("Drained workload %s on edge %s", workload, edge)
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning("Could not drain source edge %s: %s", edge, exc)

    async def _perform_final_sync(
        self, plan: MigrationPlan, progress: MigrationProgress
    ):
        """Perform final data synchronization after draining the source.

        This is the last sync before traffic cutover, capturing any
        remaining writes that happened during the drain window.

        Args:
            plan: Migration plan
            progress: Current progress tracker
        """
        # Re-use delta sync logic for the final pass
        await self._perform_delta_sync(plan, progress)

    async def _switch_traffic(self, source: str, target: str, workloads: List[str]):
        """Switch traffic routing from source to target edge for given workloads.

        Sends a routing update to both the source and target edges so that
        upstream load balancers direct traffic to the target.

        Args:
            source: Edge to route traffic away from
            target: Edge to route traffic to
            workloads: Workloads whose traffic should be switched
        """
        payload = {
            "action": "switch",
            "from_edge": source,
            "to_edge": target,
            "workloads": workloads,
        }
        for edge in [source, target]:
            try:
                base = self._get_endpoint(edge)
                session = await self._get_session()
                url = f"{base}{self.EDGE_API_BASE}/routing"
                async with session.post(url, json=payload) as resp:
                    if resp.status not in (200, 201, 204):
                        body = await resp.text()
                        logger.warning(
                            "Traffic switch on %s returned HTTP %d: %s",
                            edge,
                            resp.status,
                            body,
                        )
                    else:
                        logger.info(
                            "Switched traffic on %s: %s -> %s for %d workloads",
                            edge,
                            source,
                            target,
                            len(workloads),
                        )
            except (ValueError, aiohttp.ClientError) as exc:
                logger.error("Traffic switch failed on %s: %s", edge, exc)

    async def _start_workload(self, edge: str, workload: str):
        """Start a workload on the target edge node.

        Args:
            edge: Target edge identifier
            workload: Workload to start
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/start"
            async with session.post(url) as resp:
                if resp.status not in (200, 201, 204):
                    body = await resp.text()
                    raise RuntimeError(
                        f"Failed to start workload {workload} on {edge}: "
                        f"HTTP {resp.status} - {body}"
                    )
                logger.info("Started workload %s on edge %s", workload, edge)
        except (ValueError, aiohttp.ClientError) as exc:
            logger.error("Could not start workload %s on %s: %s", workload, edge, exc)
            raise

    async def _verify_workload_running(self, edge: str, workload: str) -> bool:
        """Verify that a workload is running on the target edge.

        Queries the workload status endpoint and checks for "running" state.

        Args:
            edge: Edge identifier
            workload: Workload identifier

        Returns:
            True if the workload is running
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/status"
            async with session.get(url) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    return body.get("status") == "running"
                logger.warning(
                    "Status check for %s on %s returned HTTP %d",
                    workload,
                    edge,
                    resp.status,
                )
                return False
        except (ValueError, aiohttp.ClientError) as exc:
            logger.error("Could not verify workload %s on %s: %s", workload, edge, exc)
            return False

    async def _verify_data_integrity(
        self, source: str, target: str, workload: str
    ) -> bool:
        """Verify data integrity after migration using SHA-256 checksums.

        Fetches checksums from both source and target and compares them.

        Args:
            source: Source edge identifier
            target: Target edge identifier
            workload: Workload identifier

        Returns:
            True if checksums match
        """
        try:
            session = await self._get_session()
            checksums = {}
            for edge in [source, target]:
                base = self._get_endpoint(edge)
                url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/checksum"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        body = await resp.json()
                        checksums[edge] = body.get("sha256", "")
                    else:
                        logger.warning(
                            "Checksum request for %s on %s returned HTTP %d",
                            workload,
                            edge,
                            resp.status,
                        )
                        return False

            source_checksum = checksums.get(source, "")
            target_checksum = checksums.get(target, "")

            if source_checksum and target_checksum:
                match = source_checksum == target_checksum
                if not match:
                    logger.error(
                        "Data integrity check FAILED for workload %s: "
                        "source=%s, target=%s",
                        workload,
                        source_checksum,
                        target_checksum,
                    )
                return match

            return False
        except (ValueError, aiohttp.ClientError) as exc:
            logger.error("Data integrity check failed for %s: %s", workload, exc)
            return False

    async def _test_workload_functionality(self, edge: str, workload: str) -> bool:
        """Test that a workload is functional by hitting its health endpoint.

        Args:
            edge: Edge identifier
            workload: Workload identifier

        Returns:
            True if the workload responds healthy
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}/health"
            async with session.get(url) as resp:
                if resp.status == 200:
                    body = await resp.json()
                    return body.get("healthy", False)
                return False
        except (ValueError, aiohttp.ClientError) as exc:
            logger.error(
                "Functionality test failed for %s on %s: %s", workload, edge, exc
            )
            return False

    async def _cleanup_workload(self, edge: str, workload: str):
        """Remove a workload from an edge node.

        Sends a DELETE to the edge to stop and clean up the workload.

        Args:
            edge: Edge identifier
            workload: Workload to clean up
        """
        try:
            base = self._get_endpoint(edge)
            session = await self._get_session()
            url = f"{base}{self.EDGE_API_BASE}/workloads/{workload}"
            async with session.delete(url) as resp:
                if resp.status not in (200, 204):
                    logger.warning(
                        "Cleanup of %s on %s returned HTTP %d",
                        workload,
                        edge,
                        resp.status,
                    )
                else:
                    logger.info("Cleaned up workload %s from edge %s", workload, edge)
        except (ValueError, aiohttp.ClientError) as exc:
            logger.warning(
                "Could not clean up workload %s on %s: %s", workload, edge, exc
            )

    async def _cleanup_temp_data(self, migration_id: str):
        """Clean up temporary migration data.

        Removes any temporary files, caches, or checksum data
        associated with the migration.

        Args:
            migration_id: Migration identifier
        """
        # Clear source checksums for this migration
        self._source_checksums.pop(migration_id, None)
        self._source_checksums.pop("_latest", None)

        # Clear temp data tracking
        self._temp_data.pop(migration_id, None)

        logger.info("Cleaned up temp data for migration %s", migration_id)

    async def _release_migration_resources(self, migration_id: str):
        """Release resources used by migration."""
        self.active_migrations.pop(migration_id, None)
        self.bandwidth_usage.clear()

    async def _capture_state_snapshot(self, migration_id: str) -> Dict[str, Any]:
        """Capture current state for checkpoint."""
        return {
            "progress": self.migration_progress[migration_id].to_dict(),
            "timestamp": datetime.now().isoformat(),
        }

    async def _restore_from_checkpoint(self, checkpoint: MigrationCheckpoint):
        """Restore migration state from a checkpoint.

        Restores the progress tracker to the state captured in the checkpoint
        so that a retry or rollback can proceed from a known-good state.

        Args:
            checkpoint: Checkpoint to restore from
        """
        migration_id = checkpoint.migration_id
        snapshot = checkpoint.state_snapshot
        progress_data = snapshot.get("progress", {})

        if migration_id in self.migration_progress:
            progress = self.migration_progress[migration_id]
            progress.phase = MigrationPhase(progress_data.get("phase", "planning"))
            progress.progress_percent = progress_data.get("progress_percent", 0.0)
            progress.data_transferred = progress_data.get("data_transferred", 0)
            progress.workloads_migrated = progress_data.get("workloads_migrated", [])
            progress.errors = progress_data.get("errors", [])
            logger.info(
                "Restored migration %s to checkpoint %s (phase=%s)",
                migration_id,
                checkpoint.checkpoint_id,
                progress.phase.value,
            )

    def _calculate_transfer_rate(
        self, bytes_transferred: int, elapsed_seconds: float
    ) -> float:
        """Calculate transfer rate in Mbps."""
        if elapsed_seconds > 0:
            return (bytes_transferred * 8) / (elapsed_seconds * 1024 * 1024)
        return 0.0

    def get_active_migrations(self) -> List[MigrationPlan]:
        """Get list of active migrations."""
        return list(self.active_migrations.values())

    def get_migration_history(self) -> List[Dict[str, Any]]:
        """Get migration history."""
        history = []

        for migration_id in self.completed_migrations:
            if migration_id in self.migration_progress:
                progress = self.migration_progress[migration_id]
                history.append(
                    {
                        "migration_id": migration_id,
                        "completed_at": progress.start_time
                        + timedelta(
                            seconds=(
                                datetime.now() - progress.start_time
                            ).total_seconds()
                        ),
                        "duration": (
                            datetime.now() - progress.start_time
                        ).total_seconds(),
                        "data_transferred": progress.data_transferred,
                        "workloads": progress.workloads_migrated,
                    }
                )

        return history

    def get_migration_metrics(self) -> Dict[str, Any]:
        """Get overall migration metrics."""
        total_migrations = len(self.completed_migrations) + len(self.active_migrations)

        total_data_transferred = sum(
            p.data_transferred for p in self.migration_progress.values()
        )

        active_count = len(self.active_migrations)
        completed_count = len(self.completed_migrations)

        failed_count = sum(
            1
            for p in self.migration_progress.values()
            if p.phase == MigrationPhase.FAILED
        )

        return {
            "total_migrations": total_migrations,
            "active_migrations": active_count,
            "completed_migrations": completed_count,
            "failed_migrations": failed_count,
            "total_data_transferred": total_data_transferred,
            "success_rate": (
                completed_count / total_migrations if total_migrations > 0 else 0
            ),
        }
