"""
State manager for checkpoint orchestration.

Manages checkpoint operations: save, load, resume, fork, list, cleanup.
"""

import copy
import logging
from typing import TYPE_CHECKING

from .storage import FilesystemStorage, StorageBackend
from .types import AgentState, CheckpointMetadata, StateSnapshot

if TYPE_CHECKING:
    from kaizen.core.autonomy.hooks.manager import HookManager

logger = logging.getLogger(__name__)


class StateManager:
    """
    Orchestrates checkpoint operations for agent state persistence.

    Provides high-level API for checkpoint/resume/fork operations.
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        checkpoint_frequency: int = 10,  # Every N steps
        checkpoint_interval: float = 60.0,  # OR every M seconds
        retention_count: int = 100,  # Keep last N checkpoints
        hook_manager: "HookManager | None" = None,  # Optional hooks integration
    ):
        """
        Initialize state manager.

        Args:
            storage: Storage backend (defaults to FilesystemStorage)
            checkpoint_frequency: Checkpoint every N steps
            checkpoint_interval: Checkpoint every M seconds
            retention_count: Maximum checkpoints to keep per agent
            hook_manager: Optional HookManager for checkpoint hooks
        """
        self.storage = storage or FilesystemStorage()
        self.checkpoint_frequency = checkpoint_frequency
        self.checkpoint_interval = checkpoint_interval
        self.retention_count = retention_count
        self.hook_manager = hook_manager

        # Tracking for should_checkpoint logic
        self._last_checkpoint_step: dict[str, int] = {}
        self._last_checkpoint_time: dict[str, float] = {}

    def should_checkpoint(
        self, agent_id: str, current_step: int, current_time: float
    ) -> bool:
        """
        Determine if checkpoint is needed based on frequency and interval.

        Args:
            agent_id: ID of agent
            current_step: Current step number
            current_time: Current time (seconds since epoch)

        Returns:
            True if checkpoint should be created
        """
        # Check frequency (every N steps)
        last_step = self._last_checkpoint_step.get(agent_id, 0)
        if current_step - last_step >= self.checkpoint_frequency:
            return True

        # Check interval (every M seconds)
        last_time = self._last_checkpoint_time.get(agent_id, 0.0)
        if current_time - last_time >= self.checkpoint_interval:
            return True

        return False

    async def save_checkpoint(
        self,
        state: AgentState,
        force: bool = False,
    ) -> str:
        """
        Save agent state as checkpoint (TODO-168 Day 4).

        Triggers PRE_CHECKPOINT_SAVE and POST_CHECKPOINT_SAVE hooks if enabled.

        Args:
            state: Agent state to checkpoint
            force: Force checkpoint even if not needed

        Returns:
            checkpoint_id of saved checkpoint

        Raises:
            IOError: If save fails
        """
        import time

        current_time = time.time()

        # Update tracking
        self._last_checkpoint_step[state.agent_id] = state.step_number
        self._last_checkpoint_time[state.agent_id] = current_time

        # Trigger PRE_CHECKPOINT_SAVE hook
        if self.hook_manager:
            try:
                from kaizen.core.autonomy.hooks.types import HookEvent

                await self.hook_manager.trigger(
                    HookEvent.PRE_CHECKPOINT_SAVE,
                    data={
                        "agent_id": state.agent_id,
                        "step_number": state.step_number,
                        "status": state.status,
                        "timestamp": current_time,
                    },
                    agent_id=state.agent_id,
                )
            except Exception as e:
                logger.warning(f"PRE_CHECKPOINT_SAVE hook failed: {e}")

        # Save checkpoint
        checkpoint_id = await self.storage.save(state)

        logger.info(
            f"Checkpoint created: {checkpoint_id} "
            f"(agent={state.agent_id}, step={state.step_number})"
        )

        # Trigger POST_CHECKPOINT_SAVE hook
        if self.hook_manager:
            try:
                from kaizen.core.autonomy.hooks.types import HookEvent

                await self.hook_manager.trigger(
                    HookEvent.POST_CHECKPOINT_SAVE,
                    data={
                        "agent_id": state.agent_id,
                        "checkpoint_id": checkpoint_id,
                        "step_number": state.step_number,
                        "status": state.status,
                        "timestamp": current_time,
                    },
                    agent_id=state.agent_id,
                )
            except Exception as e:
                logger.warning(f"POST_CHECKPOINT_SAVE hook failed: {e}")

        # Cleanup old checkpoints (async, don't block)
        try:
            await self.cleanup_old_checkpoints(state.agent_id)
        except Exception as e:
            logger.warning(f"Checkpoint cleanup failed: {e}")

        return checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> AgentState:
        """
        Load checkpoint by ID.

        Args:
            checkpoint_id: ID of checkpoint to load

        Returns:
            AgentState restored from checkpoint

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """
        state = await self.storage.load(checkpoint_id)
        logger.info(f"Checkpoint restored: {checkpoint_id}")
        return state

    async def resume_from_latest(self, agent_id: str) -> AgentState | None:
        """
        Resume from latest checkpoint for agent.

        Args:
            agent_id: ID of agent to resume

        Returns:
            Latest AgentState, or None if no checkpoints exist
        """
        checkpoints = await self.storage.list_checkpoints(agent_id=agent_id)

        if not checkpoints:
            logger.info(f"No checkpoints found for agent: {agent_id}")
            return None

        # Load latest checkpoint (list is sorted newest first)
        latest = checkpoints[0]
        state = await self.storage.load(latest.checkpoint_id)

        logger.info(
            f"Resumed from latest checkpoint: {latest.checkpoint_id} "
            f"(step={latest.step_number})"
        )

        return state

    async def fork_from_checkpoint(self, checkpoint_id: str) -> AgentState:
        """
        Create new state branched from checkpoint.

        Creates a copy of the checkpoint with a new checkpoint_id and
        parent_checkpoint_id set to the original.

        Args:
            checkpoint_id: ID of checkpoint to fork from

        Returns:
            New AgentState with updated IDs

        Raises:
            FileNotFoundError: If checkpoint doesn't exist
        """
        # Load original checkpoint
        original_state = await self.storage.load(checkpoint_id)

        # Create fork (deep copy to avoid mutations)
        forked_state = copy.deepcopy(original_state)

        # Update IDs
        import uuid

        forked_state.checkpoint_id = f"ckpt_{uuid.uuid4().hex[:12]}"
        forked_state.parent_checkpoint_id = checkpoint_id

        # Save forked checkpoint
        await self.storage.save(forked_state)

        logger.info(
            f"Forked checkpoint: {checkpoint_id} → {forked_state.checkpoint_id}"
        )

        return forked_state

    async def list_checkpoints(
        self, agent_id: str | None = None
    ) -> list[CheckpointMetadata]:
        """
        List all checkpoints (optionally filtered by agent_id).

        Args:
            agent_id: Filter checkpoints for specific agent (None = all)

        Returns:
            List of checkpoint metadata sorted by timestamp (newest first)
        """
        return await self.storage.list_checkpoints(agent_id=agent_id)

    async def cleanup_old_checkpoints(self, agent_id: str) -> int:
        """
        Delete checkpoints beyond retention_count.

        Keeps the latest N checkpoints for the agent.

        Args:
            agent_id: ID of agent

        Returns:
            Number of checkpoints deleted

        Raises:
            IOError: If deletion fails
        """
        checkpoints = await self.storage.list_checkpoints(agent_id=agent_id)

        if len(checkpoints) <= self.retention_count:
            return 0

        # Delete oldest checkpoints
        to_delete = checkpoints[self.retention_count :]
        deleted_count = 0

        for checkpoint in to_delete:
            try:
                await self.storage.delete(checkpoint.checkpoint_id)
                deleted_count += 1
            except Exception as e:
                logger.error(
                    f"Failed to delete checkpoint {checkpoint.checkpoint_id}: {e}"
                )

        logger.info(f"Cleaned up {deleted_count} old checkpoints for agent: {agent_id}")

        return deleted_count

    async def get_checkpoint_tree(self, agent_id: str) -> dict[str, list[str]]:
        """
        Return parent-child checkpoint relationships.

        Useful for visualizing checkpoint forks and lineage.

        Args:
            agent_id: ID of agent

        Returns:
            Dictionary mapping checkpoint_id to list of child checkpoint_ids
        """
        checkpoints = await self.storage.list_checkpoints(agent_id=agent_id)

        # Build parent → children mapping
        tree: dict[str, list[str]] = {}

        for checkpoint in checkpoints:
            parent_id = checkpoint.parent_checkpoint_id

            if parent_id:
                if parent_id not in tree:
                    tree[parent_id] = []
                tree[parent_id].append(checkpoint.checkpoint_id)

        return tree

    def create_snapshot(
        self, state: AgentState, reason: str = "manual"
    ) -> StateSnapshot:
        """
        Create immutable snapshot of state.

        Useful for debugging and inspection without modifying checkpoints.

        Args:
            state: Agent state to snapshot
            reason: Reason for snapshot (for auditing)

        Returns:
            StateSnapshot with copied state
        """
        snapshot = StateSnapshot(
            state=copy.deepcopy(state),
            snapshot_reason=reason,
        )

        logger.debug(f"Created snapshot: {state.checkpoint_id} (reason={reason})")

        return snapshot


# Export all public types
__all__ = [
    "StateManager",
]
