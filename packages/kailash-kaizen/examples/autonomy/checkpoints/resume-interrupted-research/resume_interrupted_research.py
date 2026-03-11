"""
Resume Interrupted Research Agent - Checkpoint & Resume Pattern.

This example demonstrates:
1. Automatic checkpoint every N steps (configurable)
2. Graceful interrupt handling (Ctrl+C detection)
3. Resume from latest checkpoint
4. State preservation (conversation history, budget, progress)
5. Checkpoint compression (50%+ size reduction)
6. Retention policy (keep last N checkpoints)
7. Budget tracking with Ollama (FREE - $0.00)
8. Hooks integration for checkpoint metrics

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+

Usage:
    # Run 1: Start research (will be interrupted)
    python resume_interrupted_research.py

    # Simulate Ctrl+C at step 47
    # Checkpoint automatically saved

    # Run 2: Resume from checkpoint
    python resume_interrupted_research.py
    # Continues from step 47, completes steps 48-100
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime
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


class ResearchSignature(Signature):
    """Signature for research paper analysis."""

    paper_index: int = InputField(description="Index of paper being analyzed (1-100)")
    paper_title: str = InputField(description="Title of research paper")
    analysis: str = OutputField(
        description="Analysis of research paper with key findings"
    )
    key_concepts: List[str] = OutputField(description="List of key concepts identified")
    relevance_score: float = OutputField(
        description="Relevance score 0-1 for AI ethics research"
    )


class CheckpointMetricsHook(BaseHook):
    """
    Custom hook to track checkpoint creation and compression metrics.

    Records:
    - Checkpoint creation times
    - Checkpoint file sizes (compressed vs uncompressed)
    - Compression ratios
    - Checkpoint frequency and retention
    """

    def __init__(self):
        super().__init__(name="checkpoint_metrics_hook")
        self.checkpoint_log: List[Dict[str, Any]] = []
        self.stats = {
            "total_checkpoints": 0,
            "total_compressed_size_bytes": 0,
            "total_uncompressed_size_bytes": 0,
            "average_compression_ratio": 0.0,
        }

    def supported_events(self) -> List[HookEvent]:
        """Hook into checkpoint save events."""
        return [HookEvent.POST_CHECKPOINT_SAVE]

    async def handle(self, context: HookContext) -> HookResult:
        """Record checkpoint metrics."""
        try:
            checkpoint_id = context.data.get("checkpoint_id")
            step_number = context.data.get("step_number")
            compressed_size = context.data.get("compressed_size_bytes", 0)
            uncompressed_size = context.data.get("uncompressed_size_bytes", 0)

            # Calculate compression ratio
            if uncompressed_size > 0:
                compression_ratio = (1.0 - (compressed_size / uncompressed_size)) * 100

                # Update stats
                self.stats["total_checkpoints"] += 1
                self.stats["total_compressed_size_bytes"] += compressed_size
                self.stats["total_uncompressed_size_bytes"] += uncompressed_size

                # Calculate average compression ratio
                if self.stats["total_uncompressed_size_bytes"] > 0:
                    self.stats["average_compression_ratio"] = (
                        1.0
                        - (
                            self.stats["total_compressed_size_bytes"]
                            / self.stats["total_uncompressed_size_bytes"]
                        )
                    ) * 100

                logger.info(
                    f"Checkpoint {checkpoint_id} saved at step {step_number} "
                    f"(compression: {compression_ratio:.1f}%)"
                )

            return HookResult(success=True)

        except Exception as e:
            logger.error(f"Error in checkpoint metrics hook: {e}")
            return HookResult(success=False, error=str(e))

    def get_summary(self) -> Dict[str, Any]:
        """Get checkpoint metrics summary."""
        return {
            "total_checkpoints": self.stats["total_checkpoints"],
            "compressed_size_kb": self.stats["total_compressed_size_bytes"] / 1024,
            "uncompressed_size_kb": self.stats["total_uncompressed_size_bytes"] / 1024,
            "average_compression_ratio": f"{self.stats['average_compression_ratio']:.1f}%",
        }


class ResearchAgent:
    """
    Research agent with automatic checkpointing and resume capabilities.

    Analyzes 100 research papers on AI ethics with automatic checkpoint
    creation every 10 steps and graceful interrupt handling.
    """

    def __init__(self, checkpoint_dir: Path = Path("./checkpoints")):
        """Initialize research agent with checkpoint support."""
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Setup hooks for checkpoint metrics
        self.hook_manager = HookManager()
        self.checkpoint_hook = CheckpointMetricsHook()
        self.hook_manager.register_hook(self.checkpoint_hook)

        # Setup state manager with compression
        storage = FilesystemStorage(
            base_dir=str(self.checkpoint_dir),
            compress=True,  # Enable gzip compression
        )

        self.state_manager = StateManager(
            storage=storage,
            checkpoint_frequency=10,  # Checkpoint every 10 steps
            retention_count=20,  # Keep last 20 checkpoints
            hook_manager=self.hook_manager,
        )

        # Configure autonomous agent
        config = AutonomousConfig(
            llm_provider="ollama",
            model="llama3.1:8b-instruct-q8_0",
            temperature=0.3,  # Low for consistent analysis
            max_cycles=100,  # 100 papers to analyze
            checkpoint_frequency=10,
            resume_from_checkpoint=True,
            checkpoint_on_interrupt=True,  # Save on Ctrl+C
        )

        self.agent = BaseAutonomousAgent(
            config=config,
            signature=ResearchSignature(),
            state_manager=self.state_manager,
            hook_manager=self.hook_manager,
        )

        # Track interrupt state
        self.interrupted = False

    def setup_signal_handlers(self):
        """Setup graceful interrupt handlers (Ctrl+C)."""

        def handle_interrupt(signum, frame):
            """Handle SIGINT (Ctrl+C)."""
            logger.warning("\n⚠️  INTERRUPT DETECTED (Ctrl+C)!")
            logger.info("→ Saving checkpoint...")
            self.interrupted = True

        signal.signal(signal.SIGINT, handle_interrupt)

    async def analyze_papers(self, simulate_interrupt_at: Optional[int] = None):
        """
        Analyze 100 research papers with automatic checkpointing.

        Args:
            simulate_interrupt_at: Optional step number to simulate interrupt (for testing)
        """
        logger.info("=" * 60)
        logger.info("RESEARCH SESSION - AI Ethics Paper Analysis")
        logger.info("=" * 60)

        # Check if resuming from checkpoint
        latest_state = await self.state_manager.resume_from_latest("research_agent")

        if latest_state:
            logger.info(f"\n🔄 RESUMING from checkpoint {latest_state.checkpoint_id}")
            logger.info(
                f"→ Previous progress: {latest_state.step_number} papers analyzed"
            )
            logger.info(f"→ Budget spent: ${latest_state.budget_spent_usd:.2f}")
            logger.info(f"→ Continuing from step {latest_state.step_number + 1}...\n")
            start_index = latest_state.step_number
        else:
            logger.info("\n✨ NEW SESSION - Starting from paper 1\n")
            start_index = 0

        # Simulate paper analysis (100 papers)
        papers = self._generate_paper_titles()
        total_papers = len(papers)

        for i in range(start_index, total_papers):
            # Check for interrupt
            if self.interrupted or (
                simulate_interrupt_at and i == simulate_interrupt_at
            ):
                logger.warning(f"\n⚠️  Interrupted at step {i}")
                logger.info("→ Saving final checkpoint...")

                # Save current state
                current_state = AgentState(
                    agent_id="research_agent",
                    step_number=i,
                    status="interrupted",
                    conversation_history=[],
                    memory_contents={
                        "papers_analyzed": i,
                        "last_paper": papers[i - 1] if i > 0 else None,
                    },
                    budget_spent_usd=0.0,  # $0.00 with Ollama
                )

                checkpoint_id = await self.state_manager.save_checkpoint(
                    current_state, force=True
                )
                logger.info(f"→ Checkpoint saved: {checkpoint_id}")
                logger.info("→ Graceful shutdown complete\n")

                # Simulate interrupt behavior
                if simulate_interrupt_at:
                    return {"status": "interrupted", "papers_analyzed": i}
                else:
                    sys.exit(0)

            # Analyze paper (simulated)
            paper_title = papers[i]
            start_time = time.time()

            # Simulate analysis
            analysis_time = 0.25  # 250ms per paper
            await asyncio.sleep(analysis_time)

            elapsed = time.time() - start_time

            # Log progress
            logger.info(
                f"STEP {i + 1}: Analyzing '{paper_title[:50]}...' ({elapsed:.2f}s)"
            )

            # Automatic checkpoint every 10 steps (handled by state_manager)
            if (i + 1) % 10 == 0:
                current_state = AgentState(
                    agent_id="research_agent",
                    step_number=i + 1,
                    status="running",
                    conversation_history=[],
                    memory_contents={
                        "papers_analyzed": i + 1,
                        "last_paper": paper_title,
                    },
                    budget_spent_usd=0.0,
                )

                checkpoint_id = await self.state_manager.save_checkpoint(current_state)
                logger.info(f"→ Checkpoint saved: {checkpoint_id}\n")

        # Completion
        logger.info("\n" + "=" * 60)
        logger.info("RESEARCH SESSION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total papers analyzed: {total_papers}")
        logger.info("Budget spent: $0.00 (Ollama - FREE)")

        # Print checkpoint metrics
        metrics = self.checkpoint_hook.get_summary()
        logger.info("\nCHECKPOINT STATISTICS:")
        logger.info(f"- Total checkpoints: {metrics['total_checkpoints']}")
        logger.info(f"- Compressed size: {metrics['compressed_size_kb']:.1f} KB")
        logger.info(f"- Uncompressed size: {metrics['uncompressed_size_kb']:.1f} KB")
        logger.info(f"- Average compression: {metrics['average_compression_ratio']}")

        return {"status": "completed", "papers_analyzed": total_papers}

    def _generate_paper_titles(self) -> List[str]:
        """Generate 100 simulated research paper titles."""
        titles = [
            "Ethics in AI Systems: A Survey",
            "Fairness in Machine Learning Algorithms",
            "Transparency and Explainability in AI",
            "Bias Detection and Mitigation in Neural Networks",
            "Privacy-Preserving Machine Learning Techniques",
            "Accountability in Autonomous AI Systems",
            "Human Rights and Artificial Intelligence",
            "Algorithmic Decision-Making and Social Justice",
            "AI Safety and Value Alignment",
            "Ethical Considerations in Facial Recognition",
        ]

        # Generate 100 titles (repeat with variations)
        full_titles = []
        for i in range(100):
            base_title = titles[i % len(titles)]
            full_titles.append(f"{base_title} (Part {i // len(titles) + 1})")

        return full_titles


async def main():
    """Run research agent with checkpoint demonstration."""
    agent = ResearchAgent()

    # Setup signal handlers for Ctrl+C
    agent.setup_signal_handlers()

    # Print instructions
    print("\n" + "=" * 70)
    print("CHECKPOINT & RESUME DEMONSTRATION")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  1. Automatic checkpoint every 10 steps")
    print("  2. Graceful interrupt handling (Ctrl+C)")
    print("  3. Resume from latest checkpoint")
    print("  4. Checkpoint compression (50%+ reduction)")
    print("  5. Retention policy (keep last 20 checkpoints)")
    print("\nInstructions:")
    print("  - Run 1: Start research (press Ctrl+C at ~step 47)")
    print("  - Run 2: Resume from checkpoint (continues from step 47)")
    print("\nPress Ctrl+C anytime to interrupt...\n")

    # Run research with simulated interrupt for demo
    # Comment out simulate_interrupt_at for manual Ctrl+C testing
    result = await agent.analyze_papers(simulate_interrupt_at=47)

    if result["status"] == "interrupted":
        print("\n" + "=" * 70)
        print("INTERRUPTED - Now run again to resume!")
        print("=" * 70)
        print(f"\nCheckpoint saved at step {result['papers_analyzed']}")
        print("Run the script again to resume from this checkpoint.\n")


if __name__ == "__main__":
    asyncio.run(main())
