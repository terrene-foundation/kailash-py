"""
Complete Phase 3 Lifecycle Management Demo.

Demonstrates integration of all three Phase 3 systems:
1. Hooks System - Event-driven monitoring
2. State Persistence - Checkpoint/resume/fork
3. Interrupt Mechanism - Graceful shutdown

This example shows a realistic autonomous agent with:
- Automatic checkpointing every 5 steps
- Cost tracking with budget limits
- Timeout protection
- Signal handling (Ctrl+C)
- Comprehensive logging via hooks
- Graceful shutdown with checkpoint preservation
"""

import asyncio
import tempfile
import time
from pathlib import Path

from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookManager, HookResult
from kaizen.core.autonomy.hooks.builtin import (
    CostTrackingHook,
    LoggingHook,
    PerformanceProfilerHook,
)
from kaizen.core.autonomy.interrupts import (
    BudgetInterruptHandler,
    InterruptManager,
    InterruptSource,
    TimeoutInterruptHandler,
)
from kaizen.core.autonomy.state import AgentState, FilesystemStorage, StateManager


async def simulate_agent_work(step: int) -> dict:
    """Simulate agent doing work with random cost/latency"""
    import random

    await asyncio.sleep(random.uniform(0.1, 0.3))  # Simulate work

    return {
        "step": step,
        "result": f"Completed step {step}",
        "cost_usd": random.uniform(0.01, 0.05),  # Simulated LLM cost
        "success": True,
    }


async def main():
    print("=" * 60)
    print("Phase 3 Lifecycle Management Demo")
    print("=" * 60)

    # Setup temporary directory for checkpoints
    with tempfile.TemporaryDirectory() as temp_dir:
        checkpoint_dir = Path(temp_dir) / "checkpoints"
        checkpoint_dir.mkdir()

        print(f"\n📁 Checkpoint directory: {checkpoint_dir}")

        # 1. Setup Hooks System
        print("\n🔧 Setting up Hooks System...")
        hook_manager = HookManager()

        # Register built-in hooks
        hook_manager.register_hook(LoggingHook(log_level="INFO"))
        hook_manager.register_hook(CostTrackingHook())
        hook_manager.register_hook(PerformanceProfilerHook())

        # Custom hook to log checkpoints
        async def checkpoint_logger(context: HookContext) -> HookResult:
            checkpoint_id = context.data.get("checkpoint_id")
            step = context.data.get("step")
            print(f"✓ Checkpoint saved: {checkpoint_id} (step {step})")
            return HookResult(success=True)

        hook_manager.register(HookEvent.POST_CHECKPOINT_SAVE, checkpoint_logger)

        print("  ✓ Registered 4 hooks (logging, cost, performance, checkpoint)")

        # 2. Setup State Persistence
        print("\n💾 Setting up State Persistence...")
        storage = FilesystemStorage(base_dir=checkpoint_dir)
        state_manager = StateManager(
            storage=storage,
            checkpoint_frequency=5,  # Every 5 steps
            max_checkpoints_per_agent=10,  # Keep last 10
        )

        print("  ✓ Checkpoint frequency: every 5 steps")
        print("  ✓ Retention: keep 10 most recent")

        # 3. Setup Interrupt Mechanism
        print("\n🛑 Setting up Interrupt Mechanism...")
        interrupt_manager = InterruptManager()

        # Install signal handlers (Ctrl+C)
        interrupt_manager.install_signal_handlers()
        print("  ✓ Signal handlers installed (Ctrl+C to gracefully stop)")

        # Setup timeout (30 seconds for demo)
        timeout_handler = TimeoutInterruptHandler(
            interrupt_manager=interrupt_manager,
            timeout_seconds=30.0,
            warning_threshold=0.8,  # Warn at 24s
        )

        # Setup budget ($2 limit for demo)
        budget_handler = BudgetInterruptHandler(
            interrupt_manager=interrupt_manager,
            budget_usd=2.0,
            warning_threshold=0.8,  # Warn at $1.60
        )

        print("  ✓ Timeout: 30 seconds")
        print("  ✓ Budget: $2.00")

        # 4. Create initial agent state
        print("\n🤖 Creating initial agent state...")
        agent_state = AgentState(
            agent_id="demo_agent",
            step_number=0,
            status="running",
            metadata={"demo": "phase_3_lifecycle"},
        )

        print(f"  ✓ Agent ID: {agent_state.agent_id}")
        print(f"  ✓ Checkpoint ID: {agent_state.checkpoint_id}")

        # 5. Main agent execution loop
        print("\n" + "=" * 60)
        print("Starting Agent Execution")
        print("=" * 60)
        print("Press Ctrl+C to trigger graceful shutdown\n")

        try:
            # Start timeout monitoring in background
            async with asyncio.create_task_group() as tg:
                tg.start_soon(timeout_handler.start)

                # Agent loop
                max_steps = 100
                for step in range(max_steps):
                    # Check for interrupt
                    if interrupt_manager.is_interrupted():
                        print(f"\n⚠️  Interrupt detected at step {step}")
                        break

                    # Trigger PRE_AGENT_LOOP hook
                    await hook_manager.trigger(
                        HookEvent.PRE_AGENT_LOOP,
                        agent_id=agent_state.agent_id,
                        data={"step": step},
                    )

                    # Simulate agent work
                    result = await simulate_agent_work(step)

                    # Update state
                    agent_state.step_number = step + 1
                    agent_state.conversation_history.append(
                        {"step": step, "result": result["result"]}
                    )

                    # Track cost
                    cost = result["cost_usd"]
                    agent_state.budget_spent_usd += cost
                    budget_handler.track_cost(cost)

                    # Trigger POST_AGENT_LOOP hook with cost info
                    await hook_manager.trigger(
                        HookEvent.POST_AGENT_LOOP,
                        agent_id=agent_state.agent_id,
                        data={"step": step + 1, "cost_usd": cost, "result": result},
                    )

                    # Print progress every step
                    print(
                        f"Step {step + 1:3d}/{max_steps}: "
                        f"${cost:.4f} (total: ${agent_state.budget_spent_usd:.4f})"
                    )

                    # Check if should checkpoint
                    if state_manager.should_checkpoint(
                        agent_id=agent_state.agent_id,
                        current_step=step + 1,
                        current_time=time.time(),
                    ):
                        # Trigger PRE_CHECKPOINT_SAVE hook
                        await hook_manager.trigger(
                            HookEvent.PRE_CHECKPOINT_SAVE,
                            agent_id=agent_state.agent_id,
                            data={"step": step + 1},
                        )

                        # Save checkpoint
                        checkpoint_id = await state_manager.save_checkpoint(
                            agent_state, force=False
                        )

                        # Trigger POST_CHECKPOINT_SAVE hook
                        await hook_manager.trigger(
                            HookEvent.POST_CHECKPOINT_SAVE,
                            agent_id=agent_state.agent_id,
                            data={"checkpoint_id": checkpoint_id, "step": step + 1},
                        )

                    # Check for interrupt again (may have been triggered during work)
                    if interrupt_manager.is_interrupted():
                        print(f"\n⚠️  Interrupt detected at step {step + 1}")
                        break

                # Cancel timeout handler
                tg.cancel_scope.cancel()

        except* asyncio.CancelledError:
            print("\n⚠️  Timeout monitoring cancelled")

        # 6. Graceful shutdown
        print("\n" + "=" * 60)
        print("Graceful Shutdown")
        print("=" * 60)

        if interrupt_manager.is_interrupted():
            # Get interrupt reason
            reason = interrupt_manager._interrupt_reason
            print("\n📋 Interrupt Details:")
            print(f"  Source: {reason.source.value}")
            print(f"  Mode: {reason.mode.value}")
            print(f"  Message: {reason.message}")

            if reason.source == InterruptSource.BUDGET:
                print("\n💰 Budget Status:")
                print(f"  Budget: ${budget_handler.budget_usd:.2f}")
                print(f"  Spent: ${budget_handler.get_current_cost():.2f}")
                print(
                    f"  Overage: ${budget_handler.get_current_cost() - budget_handler.budget_usd:.2f}"
                )

            # Execute shutdown with final checkpoint
            print("\n💾 Saving final checkpoint...")
            status = await interrupt_manager.execute_shutdown(
                state_manager=state_manager, agent_state=agent_state
            )

            print(f"  ✓ Checkpoint ID: {status.checkpoint_id}")
            print(f"  ✓ Can resume: {status.can_resume()}")

        else:
            # Normal completion
            print("\n✅ Agent completed successfully!")
            agent_state.status = "completed"
            final_checkpoint = await state_manager.save_checkpoint(
                agent_state, force=True
            )
            print(f"  ✓ Final checkpoint: {final_checkpoint}")

        # 7. Display statistics
        print("\n" + "=" * 60)
        print("Session Statistics")
        print("=" * 60)

        # Hook stats
        print("\n📊 Hook Statistics:")
        hook_stats = hook_manager.get_hook_stats()
        print(f"  Total triggers: {hook_stats['total_triggers']}")
        print(f"  Successes: {hook_stats['total_successes']}")
        print(f"  Failures: {hook_stats['total_failures']}")

        # Cost tracking
        cost_hook = [
            h
            for h in hook_manager._hooks[HookEvent.POST_AGENT_LOOP]
            if isinstance(h[1], CostTrackingHook)
        ]
        if cost_hook:
            print("\n💰 Cost Tracking:")
            print(f"  Total: ${agent_state.budget_spent_usd:.4f}")

        # Performance profiling
        perf_hook = [
            h
            for h in hook_manager._hooks[HookEvent.POST_AGENT_LOOP]
            if isinstance(h[1], PerformanceProfilerHook)
        ]
        if perf_hook:
            print("\n⚡ Performance:")
            print(f"  Total steps: {agent_state.step_number}")

        # Checkpoint listing
        print("\n📁 Checkpoint Listing:")
        checkpoints = await state_manager.list_checkpoints(agent_id="demo_agent")
        print(f"  Total checkpoints: {len(checkpoints)}")

        for i, ckpt in enumerate(checkpoints[:5], 1):  # Show first 5
            print(
                f"  {i}. {ckpt.checkpoint_id[:12]}... "
                f"(step {ckpt.step_number}, {ckpt.status})"
            )

        # 8. Demonstrate resume capability
        if checkpoints:
            print("\n" + "=" * 60)
            print("Resume Capability Demonstration")
            print("=" * 60)

            latest_checkpoint = checkpoints[0]
            print(
                f"\n🔄 Loading latest checkpoint: {latest_checkpoint.checkpoint_id[:12]}..."
            )

            resumed_state = await state_manager.load_checkpoint(
                latest_checkpoint.checkpoint_id
            )

            print(f"  ✓ Agent ID: {resumed_state.agent_id}")
            print(f"  ✓ Step: {resumed_state.step_number}")
            print(f"  ✓ Status: {resumed_state.status}")
            print(f"  ✓ Budget spent: ${resumed_state.budget_spent_usd:.4f}")
            print(
                f"  ✓ Conversation history: {len(resumed_state.conversation_history)} entries"
            )

            print(f"\n💡 Agent can be resumed from step {resumed_state.step_number}")

        # 9. Demonstrate fork capability
        if checkpoints and len(checkpoints) >= 2:
            print("\n" + "=" * 60)
            print("Fork Capability Demonstration")
            print("=" * 60)

            # Fork from earlier checkpoint
            fork_from = checkpoints[1]  # Second most recent
            print(f"\n🔀 Forking from checkpoint: {fork_from.checkpoint_id[:12]}...")

            forked_state = await state_manager.fork_from_checkpoint(
                fork_from.checkpoint_id
            )

            print(f"  ✓ New checkpoint ID: {forked_state.checkpoint_id[:12]}...")
            print(f"  ✓ Parent: {forked_state.parent_checkpoint_id[:12]}...")
            print(f"  ✓ Step: {forked_state.step_number}")

            print("\n💡 Fork created - independent execution branch available")

        # Cleanup
        interrupt_manager.uninstall_signal_handlers()

        print("\n" + "=" * 60)
        print("Demo Complete!")
        print("=" * 60)
        print("\n✅ All Phase 3 systems demonstrated successfully")
        print(f"📁 Checkpoints saved in: {checkpoint_dir}")
        print("\n💡 Key Takeaways:")
        print("  • Hooks provide event-driven monitoring")
        print("  • State persistence enables checkpoint/resume/fork")
        print("  • Interrupts ensure graceful shutdown")
        print("  • All three systems integrate seamlessly")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Ctrl+C detected - demo interrupted")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
