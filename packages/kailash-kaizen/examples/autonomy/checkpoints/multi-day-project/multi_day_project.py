"""
Multi-Day Project Agent - Checkpoint with Compression & Forking.

This example demonstrates:
1. Long-running project with daily checkpoints
2. Checkpoint compression (50%+ size reduction)
3. Retention policy (automatic cleanup of old checkpoints)
4. Fork checkpoint for experimentation (create independent branch)
5. State restoration from any checkpoint
6. Progress tracking across days
7. Budget tracking with Ollama (FREE - $0.00)
8. Hooks integration for progress metrics

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    python multi_day_project.py

    The agent will:
    - Simulate 3-day software project
    - Create daily checkpoints with compression
    - Fork checkpoint for experimental approach
    - Continue main branch independently
    - Demonstrate checkpoint compression and retention
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.core.autonomy.hooks import (
    BaseHook,
    HookContext,
    HookEvent,
    HookManager,
    HookResult,
)
from kaizen.core.autonomy.state import AgentState, FilesystemStorage, StateManager
from kaizen.signatures import InputField, OutputField, Signature

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ProjectSignature(Signature):
    """Signature for project task execution."""

    day: int = InputField(description="Day of project (1-3)")
    task_name: str = InputField(description="Name of task to execute")
    task_result: str = OutputField(
        description="Result of task execution with deliverables"
    )
    completion_status: str = OutputField(
        description="Status: complete, in_progress, blocked"
    )
    dependencies: List[str] = OutputField(description="List of task dependencies")


class ProgressMetricsHook(BaseHook):
    """
    Custom hook to track project progress and checkpoint metrics.

    Records:
    - Daily progress (tasks completed per day)
    - Checkpoint compression ratios
    - Storage efficiency
    - Fork operations
    """

    def __init__(self):
        super().__init__(name="progress_metrics_hook")
        self.daily_progress: Dict[int, List[str]] = {}
        self.checkpoint_stats: List[Dict[str, Any]] = []
        self.fork_operations: List[Dict[str, Any]] = []

    def supported_events(self) -> List[HookEvent]:
        """Hook into POST_AGENT_LOOP and POST_CHECKPOINT_SAVE."""
        return [HookEvent.POST_AGENT_LOOP, HookEvent.POST_CHECKPOINT_SAVE]

    async def handle(self, context: HookContext) -> HookResult:
        """Record progress and checkpoint metrics."""
        try:
            if context.event_type == HookEvent.POST_AGENT_LOOP:
                # Track daily progress
                day = context.data.get("day")
                task = context.data.get("task_name")
                if day and task:
                    if day not in self.daily_progress:
                        self.daily_progress[day] = []
                    self.daily_progress[day].append(task)

            elif context.event_type == HookEvent.POST_CHECKPOINT_SAVE:
                # Track checkpoint metrics
                checkpoint_id = context.data.get("checkpoint_id")
                compressed_size = context.data.get("compressed_size_bytes", 0)
                uncompressed_size = context.data.get("uncompressed_size_bytes", 0)

                if uncompressed_size > 0:
                    compression_ratio = (
                        1.0 - (compressed_size / uncompressed_size)
                    ) * 100

                    self.checkpoint_stats.append(
                        {
                            "checkpoint_id": checkpoint_id,
                            "compressed_size_kb": compressed_size / 1024,
                            "uncompressed_size_kb": uncompressed_size / 1024,
                            "compression_ratio": compression_ratio,
                        }
                    )

                    logger.info(
                        f"Checkpoint {checkpoint_id} compressed: {compression_ratio:.1f}%"
                    )

            return HookResult(success=True)

        except Exception as e:
            logger.error(f"Error in progress metrics hook: {e}")
            return HookResult(success=False, error=str(e))

    def get_summary(self) -> Dict[str, Any]:
        """Get project progress summary."""
        total_tasks = sum(len(tasks) for tasks in self.daily_progress.values())
        avg_compression = (
            sum(stat["compression_ratio"] for stat in self.checkpoint_stats)
            / len(self.checkpoint_stats)
            if self.checkpoint_stats
            else 0
        )

        return {
            "total_tasks_completed": total_tasks,
            "daily_breakdown": {
                day: len(tasks) for day, tasks in self.daily_progress.items()
            },
            "total_checkpoints": len(self.checkpoint_stats),
            "average_compression_ratio": f"{avg_compression:.1f}%",
            "total_forks": len(self.fork_operations),
        }


class ProjectAgent:
    """
    Multi-day project agent with checkpoint forking capabilities.

    Simulates 3-day software project with:
    - Daily checkpoints for progress tracking
    - Fork for experimental approach
    - Independent main and experiment branches
    - Automatic checkpoint compression and retention
    """

    def __init__(self, checkpoint_dir: Path = Path("./project_checkpoints")):
        """Initialize project agent with checkpoint support."""
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup hooks for progress metrics
        self.hook_manager = HookManager()
        self.progress_hook = ProgressMetricsHook()
        self.hook_manager.register_hook(self.progress_hook)

        # Setup state manager with compression
        storage = FilesystemStorage(
            base_dir=str(self.checkpoint_dir),
            compress=True,  # Enable gzip compression
        )

        self.state_manager = StateManager(
            storage=storage,
            checkpoint_frequency=5,  # More frequent for demo
            retention_count=20,  # Keep last 20 checkpoints
            hook_manager=self.hook_manager,
        )

        # Configure autonomous agent
        config = AutonomousConfig(
            llm_provider="ollama",
            model="llama3.1:8b-instruct-q8_0",
            temperature=0.5,
            max_cycles=30,  # 30 tasks total
            checkpoint_frequency=5,
            resume_from_checkpoint=True,
        )

        self.agent = BaseAutonomousAgent(
            config=config,
            signature=ProjectSignature(),
            state_manager=self.state_manager,
            hook_manager=self.hook_manager,
        )

        # Project tasks by day
        self.project_tasks = {
            1: ["Design system architecture", "Setup development environment"],
            2: ["Implement data layer", "Implement business logic", "Write unit tests"],
            3: [
                "Add user authentication",
                "Add data validation",
                "Create API documentation",
            ],
        }

    async def work_on_project(self, day: int, branch: str = "main") -> Dict[str, Any]:
        """
        Execute project tasks for a given day.

        Args:
            day: Day of project (1-3)
            branch: Branch name ("main" or "experiment")

        Returns:
            Dict with completion status and checkpoint info
        """
        logger.info(f"\n{'=' * 60}")
        logger.info(f"{'═══ DAY ' + str(day) + ' ═══':^60}")
        if branch != "main":
            logger.info(f"{'BRANCH: ' + branch:^60}")
        logger.info(f"{'=' * 60}\n")

        tasks = self.project_tasks.get(day, [])
        logger.info(f"TASKS: {', '.join(tasks)}")

        completed_tasks = []
        step_number = (day - 1) * 10  # Offset for day

        for i, task in enumerate(tasks):
            step_number += 1
            logger.info(f"\nSTEP {step_number}: {task}")

            # Simulate task execution
            start_time = time.time()
            await asyncio.sleep(0.15)  # 150ms per task
            elapsed = time.time() - start_time

            logger.info(f"→ Completed in {elapsed:.2f}s")
            completed_tasks.append(task)

            # Automatic checkpoint every 5 steps
            if step_number % 5 == 0:
                current_state = AgentState(
                    agent_id=f"project_agent_{branch}",
                    step_number=step_number,
                    status="running",
                    conversation_history=[],
                    memory_contents={
                        "day": day,
                        "branch": branch,
                        "completed_tasks": completed_tasks,
                    },
                    budget_spent_usd=0.0,
                )

                checkpoint_id = await self.state_manager.save_checkpoint(current_state)
                logger.info(f"→ Checkpoint saved: {checkpoint_id}")

        # Save final checkpoint for the day
        final_state = AgentState(
            agent_id=f"project_agent_{branch}",
            step_number=step_number,
            status="completed",
            conversation_history=[],
            memory_contents={
                "day": day,
                "branch": branch,
                "completed_tasks": completed_tasks,
            },
            budget_spent_usd=0.0,
        )

        final_checkpoint_id = await self.state_manager.save_checkpoint(
            final_state, force=True
        )

        logger.info(f"\nDAY {day} COMPLETE: {len(completed_tasks)} tasks finished")
        logger.info(f"→ Final checkpoint: {final_checkpoint_id}")

        return {
            "day": day,
            "branch": branch,
            "tasks_completed": len(completed_tasks),
            "checkpoint_id": final_checkpoint_id,
        }

    async def fork_and_experiment(self, parent_checkpoint_id: str) -> Dict[str, Any]:
        """
        Fork from parent checkpoint to create experimental branch.

        Args:
            parent_checkpoint_id: Checkpoint ID to fork from

        Returns:
            Dict with fork info and new checkpoint ID
        """
        logger.info(f"\n{'=' * 60}")
        logger.info("FORKING CHECKPOINT FOR EXPERIMENTATION")
        logger.info(f"{'=' * 60}\n")

        logger.info(f"→ Forking from checkpoint: {parent_checkpoint_id}")

        # Load parent checkpoint
        parent_state = await self.state_manager.load_checkpoint(parent_checkpoint_id)

        # Create forked state with new agent_id (independent branch)
        forked_state = AgentState(
            agent_id="project_agent_experiment",  # New agent ID
            step_number=parent_state.step_number,
            status="running",
            conversation_history=parent_state.conversation_history.copy(),
            memory_contents={
                **parent_state.memory_contents,
                "branch": "experiment",
                "forked_from": parent_checkpoint_id,
            },
            budget_spent_usd=parent_state.budget_spent_usd,
            parent_checkpoint_id=parent_checkpoint_id,  # Track parent
        )

        # Save forked checkpoint
        fork_checkpoint_id = await self.state_manager.save_checkpoint(
            forked_state, force=True
        )

        logger.info(f"→ Fork created: {fork_checkpoint_id}")
        logger.info("→ Experiment branch is now independent\n")

        # Track fork operation
        self.progress_hook.fork_operations.append(
            {
                "parent_checkpoint_id": parent_checkpoint_id,
                "fork_checkpoint_id": fork_checkpoint_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

        return {
            "parent_checkpoint_id": parent_checkpoint_id,
            "fork_checkpoint_id": fork_checkpoint_id,
            "branch": "experiment",
        }


async def main():
    """Run multi-day project simulation with checkpoint forking."""
    logger.info("\n" + "=" * 70)
    logger.info("MULTI-DAY PROJECT SIMULATION")
    logger.info("=" * 70)
    logger.info("\nThis example demonstrates:")
    logger.info("  1. Daily progress checkpoints")
    logger.info("  2. Checkpoint compression (50%+ reduction)")
    logger.info("  3. Fork checkpoint for experimentation")
    logger.info("  4. Independent branch development")
    logger.info("  5. Retention policy (keep last 20 checkpoints)")
    logger.info("\n")

    agent = ProjectAgent()

    # Day 1: Initial development
    day1_result = await agent.work_on_project(day=1, branch="main")
    day1_checkpoint = day1_result["checkpoint_id"]

    # Day 2: Continue main branch
    day2_result = await agent.work_on_project(day=2, branch="main")
    day2_checkpoint = day2_result["checkpoint_id"]

    # Fork from Day 2 for experimentation
    fork_result = await agent.fork_and_experiment(day2_checkpoint)

    # Day 3: Experiment branch (try alternative approach)
    logger.info(f"{'=' * 60}")
    logger.info("DAY 3 - EXPERIMENT BRANCH")
    logger.info(f"{'=' * 60}\n")

    experiment_tasks = {
        3: ["Experiment with alternative authentication", "Test new approach"]
    }
    agent.project_tasks.update(experiment_tasks)

    experiment_result = await agent.work_on_project(day=3, branch="experiment")

    # Day 3: Main branch (continue original plan)
    logger.info(f"\n{'=' * 60}")
    logger.info("DAY 3 - MAIN BRANCH")
    logger.info(f"{'=' * 60}\n")

    main_tasks = {
        3: [
            "Add user authentication",
            "Add data validation",
            "Create API documentation",
        ]
    }
    agent.project_tasks.update(main_tasks)

    day3_result = await agent.work_on_project(day=3, branch="main")

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("FINAL PROJECT STATISTICS")
    logger.info("=" * 70)

    summary = agent.progress_hook.get_summary()
    logger.info("\nMain Branch:")
    logger.info("- Total days: 3")
    logger.info("- Total tasks: 8 (day 1: 2, day 2: 3, day 3: 3)")
    logger.info(f"- Final checkpoint: {day3_result['checkpoint_id']}")

    logger.info("\nExperiment Branch:")
    logger.info("- Forked from: Day 2 checkpoint")
    logger.info("- Tasks tested: 2 (alternative approaches)")
    logger.info(f"- Final checkpoint: {experiment_result['checkpoint_id']}")

    logger.info("\nCheckpoint Statistics:")
    logger.info(f"- Total checkpoints: {summary['total_checkpoints']}")
    logger.info(f"- Average compression: {summary['average_compression_ratio']}")
    logger.info(f"- Total forks: {summary['total_forks']}")
    logger.info("- Budget spent: $0.00 (Ollama - FREE)")

    # List all checkpoints
    logger.info("\nCheckpoint Files:")
    checkpoints = list(agent.checkpoint_dir.glob("*.jsonl.gz"))
    for ckpt in sorted(checkpoints)[-10:]:  # Show last 10
        size_kb = ckpt.stat().st_size / 1024
        logger.info(f"  - {ckpt.name} ({size_kb:.1f} KB)")

    logger.info("\n" + "=" * 70)
    logger.info("PROJECT COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
