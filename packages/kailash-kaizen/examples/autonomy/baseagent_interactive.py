#!/usr/bin/env python3
"""
BaseAgent with Control Protocol Integration

Demonstrates using BaseAgent with Control Protocol for interactive agent workflows.

This example shows:
1. Creating BaseAgent with ControlProtocol
2. Using ask_user_question() for user input
3. Using request_approval() for action confirmation
4. Interactive decision-making during agent execution

Usage:
    python examples/autonomy/baseagent_interactive.py

See Also:
    - src/kaizen/core/base_agent.py - BaseAgent implementation
    - src/kaizen/core/autonomy/control/ - Control Protocol implementation
"""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Add src to path for examples
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import anyio
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


# Define a simple task signature
class FileProcessorSignature(Signature):
    """Signature for file processing task."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


@dataclass
class FileProcessorConfig:
    """Simple config for file processor."""

    llm_provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7


async def interactive_agent_workflow():
    """
    Demonstrate BaseAgent with Control Protocol.

    Shows interactive workflow with user questions and approval requests.
    """
    print("=" * 70)
    print("BaseAgent + Control Protocol Integration Demo")
    print("=" * 70)
    print()

    # Setup Control Protocol with CLI transport
    transport = CLITransport()
    await transport.connect()

    protocol = ControlProtocol(transport)

    # Create BaseAgent with Control Protocol
    config = FileProcessorConfig()
    signature = FileProcessorSignature()

    async with anyio.create_task_group() as tg:
        # Start protocol
        await protocol.start(tg)

        # Create agent with control protocol
        agent = BaseAgent(config=config, signature=signature, control_protocol=protocol)

        print("✅ BaseAgent created with Control Protocol")
        print(f"📋 Agent ID: {agent.agent_id}")
        print()

        try:
            # Step 1: Ask user for input
            print("🤖 Agent: Asking user for file selection...")
            file_choice = await agent.ask_user_question(
                question="Which file should I process?",
                options=["data.csv", "report.pdf", "image.png"],
                timeout=30.0,
            )
            print(f"✅ User selected: {file_choice}")
            print()

            # Step 2: Ask for processing mode
            print("🤖 Agent: Asking user for processing mode...")
            mode = await agent.ask_user_question(
                question="Select processing mode:",
                options=["quick", "thorough", "custom"],
                timeout=30.0,
            )
            print(f"✅ User selected mode: {mode}")
            print()

            # Step 3: Request approval for action
            print("🤖 Agent: Requesting approval for file operation...")
            approved = await agent.request_approval(
                action=f"Process '{file_choice}' in '{mode}' mode",
                details={
                    "file": file_choice,
                    "mode": mode,
                    "estimated_time": "2 minutes",
                    "will_modify": True,
                },
                timeout=30.0,
            )

            if approved:
                print("✅ Operation approved by user")
                print(f"🔄 Processing {file_choice} in {mode} mode...")
                # Simulate processing
                await asyncio.sleep(1)
                print("✅ File processed successfully!")
            else:
                print("❌ Operation denied by user")
                print("⏹️  Cancelling workflow")

            print()
            print("🎉 Interactive workflow complete!")

        except TimeoutError as e:
            print(f"⏱️  Timeout: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback

            traceback.print_exc()
        finally:
            # Stop protocol
            await protocol.stop()

    # Close transport
    await transport.close()


async def main():
    """Main entry point."""
    print()
    print("This example demonstrates BaseAgent with Control Protocol.")
    print("The agent will ask you questions and request approval interactively.")
    print()
    print("Note: For this demo, you'll need to provide responses via stdin.")
    print("In a real application, responses would come from a UI or automation.")
    print()

    await interactive_agent_workflow()


if __name__ == "__main__":
    # Run with async
    asyncio.run(main())
