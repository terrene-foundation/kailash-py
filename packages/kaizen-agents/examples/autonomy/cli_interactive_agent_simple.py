#!/usr/bin/env python3
"""
Simple CLI Interactive Agent Example

Demonstrates the Control Protocol with a minimal file processor agent that:
1. Asks the user which file to process
2. Requests approval before processing
3. Reports progress during execution

Usage:
    python examples/autonomy/cli_interactive_agent_simple.py

Requirements:
    - Ollama installed and running (or change to "openai"/"anthropic")
    - llama3.2:latest model available (or change to your model)

Time to run: ~1 minute
"""

from dataclasses import dataclass

import anyio
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature

# ============================================
# 1. Define Signature
# ============================================


class FileProcessorSignature(Signature):
    """Agent's input/output schema."""

    file_path: str = InputField(description="Path to file to process")
    operation: str = InputField(description="Operation to perform")
    result: str = OutputField(description="Processing result")


# ============================================
# 2. Define Config
# ============================================


@dataclass
class FileProcessorConfig:
    """Agent configuration."""

    llm_provider: str = "ollama"  # Change to "openai" or "anthropic" if needed
    model: str = "llama3.2:latest"  # Change to your model
    temperature: float = 0.7


# ============================================
# 3. Create Interactive Agent
# ============================================


class InteractiveFileProcessor(BaseAgent):
    """An agent that interacts with the user during processing."""

    async def process_interactively(self, available_files: list[str]):
        """
        Main processing workflow with user interaction.

        Args:
            available_files: List of file paths user can choose from

        Returns:
            dict: Processing result with status and summary
        """
        print("\n" + "=" * 60)
        print("INTERACTIVE FILE PROCESSOR")
        print("=" * 60 + "\n")

        # Step 1: Ask user which file to process
        print("📋 STEP 1: File Selection")
        selected_file = await self.ask_user_question(
            question="Which file would you like me to process?",
            options=available_files,
            timeout=30.0,
        )

        print(f"\n✅ Selected: {selected_file}\n")

        # Step 2: Request approval before processing
        print("🔐 STEP 2: Request Approval")
        approved = await self.request_approval(
            action=f"Analyze and summarize {selected_file}",
            details={
                "file": selected_file,
                "operation": "analyze and summarize content",
                "estimated_time": "30 seconds",
                "will_modify_file": False,
                "llm_provider": self.config.llm_provider,
                "model": self.config.model,
            },
            timeout=60.0,
        )

        if not approved:
            print("\n❌ Operation cancelled by user\n")
            return {"status": "cancelled", "reason": "User denied approval"}

        print("\n✅ Approval granted\n")

        # Step 3: Report progress while processing
        print("⚙️  STEP 3: Processing")
        await self.report_progress("Starting analysis...")

        # Run the actual LLM processing
        print("🤖 Calling LLM for analysis...")
        result = self.run(
            file_path=selected_file, operation="analyze and summarize the content"
        )

        await self.report_progress("Analysis complete!", percentage=100.0)

        # Extract the result
        summary = self.extract_str(
            result, "result", default="Could not generate summary"
        )

        print("\n" + "=" * 60)
        print("PROCESSING COMPLETE")
        print("=" * 60)

        return {"status": "success", "file": selected_file, "summary": summary}


# ============================================
# 4. Main Function
# ============================================


async def main():
    """Run the interactive file processor."""

    print("\n" + "=" * 60)
    print("CLI INTERACTIVE AGENT EXAMPLE")
    print("=" * 60)
    print("\nThis example demonstrates:")
    print("  • Asking user questions")
    print("  • Requesting approval before actions")
    print("  • Reporting progress during execution")
    print("\n" + "=" * 60 + "\n")

    # Setup: Create transport for terminal interaction
    transport = CLITransport()
    await transport.connect()

    # Setup: Create control protocol
    protocol = ControlProtocol(transport)

    # Setup: Create agent with control protocol enabled
    agent = InteractiveFileProcessor(
        config=FileProcessorConfig(),
        control_protocol=protocol,  # This enables interactive methods!
    )

    # Run: Start protocol and execute agent
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)  # Start message handling

        # Execute your interactive workflow
        result = await agent.process_interactively(
            available_files=[
                "data/sales_2024.csv",
                "docs/quarterly_report.pdf",
                "logs/system_events.txt",
            ]
        )

        # Display final result
        print("\n" + "=" * 60)
        print("FINAL RESULT")
        print("=" * 60)
        print(f"\nStatus: {result['status']}")

        if result["status"] == "success":
            print(f"File: {result['file']}")
            print(f"\nSummary:\n{result['summary']}")
        else:
            print(f"Reason: {result['reason']}")

        print("\n" + "=" * 60 + "\n")

        await protocol.stop()  # Stop message handling

    # Cleanup
    await transport.close()

    print("✨ Example complete!\n")


# ============================================
# 5. Entry Point
# ============================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Starting Interactive Agent...")
    print("=" * 60)

    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user (Ctrl+C)\n")
    except Exception as e:
        print(f"\n\n❌ Error: {e}\n")
        raise
