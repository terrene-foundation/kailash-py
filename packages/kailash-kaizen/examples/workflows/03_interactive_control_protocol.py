"""
Interactive Control Protocol Agent

This example shows:
- How to set up bidirectional communication with ControlProtocol
- How agents can ask users questions during execution
- How agents can request approval for dangerous operations
- How agents can report progress for long-running tasks
- How to use different transports (CLI in this example)

Prerequisites:
- OPENAI_API_KEY in .env file
- pip install kailash-kaizen python-dotenv
"""

import asyncio
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Step 1: Load environment
load_dotenv()

from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import (  # For automated demo
    InMemoryTransport,
)

# Step 2: Import Kaizen components
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


# Step 3: Define signature for interactive tasks
class InteractiveTaskSignature(Signature):
    """Signature for interactive task execution."""

    task_description: str = InputField(description="Description of the task")
    result: str = OutputField(description="Task execution result")
    steps_completed: int = OutputField(description="Number of steps completed")


# Step 4: Configuration
@dataclass
class InteractiveAgentConfig:
    """Configuration for interactive agent."""

    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.5
    max_tokens: int = 1000


# Step 5: Create interactive agent
class InteractiveAgent(BaseAgent):
    """
    Agent with bidirectional communication capabilities.

    This agent can:
    - Ask users questions during execution
    - Request approval for dangerous operations
    - Report progress for long-running tasks
    """

    def __init__(
        self,
        config: InteractiveAgentConfig,
        control_protocol: ControlProtocol,
    ):
        """
        Initialize interactive agent.

        Args:
            config: Agent configuration
            control_protocol: Bidirectional communication protocol
        """
        super().__init__(
            config=config,
            signature=InteractiveTaskSignature(),
            control_protocol=control_protocol,  # Enable interactive communication
        )

    async def execute_with_user_guidance(self, task: str) -> dict:
        """
        Execute a task with user guidance.

        This demonstrates:
        1. Asking user for clarification
        2. Requesting approval for operations
        3. Reporting progress

        Args:
            task: Task description

        Returns:
            dict with execution results
        """
        print(f"\n🎯 Task: {task}")
        print("=" * 80)

        # Step 1: Ask user for preferences
        print("\n💬 Step 1: Asking user for preferences...")
        response = await self.ask_user_question(
            question="Which output format would you like?",
            options=["JSON", "Markdown", "Plain Text"],
            default="Plain Text",
        )

        output_format = response.get("selected_option", "Plain Text")
        print(f"✓ User selected: {output_format}")

        # Step 2: Report progress (start)
        print("\n📊 Step 2: Starting task execution...")
        await self.report_progress(
            message="Initializing task...",
            percentage=0.0,
            metadata={"stage": "initialization", "format": output_format},
        )

        # Step 3: Request approval for write operation
        print("\n🔐 Step 3: Requesting approval for write operation...")
        approval_details = {
            "operation": "write_file",
            "danger_level": "MEDIUM",
            "file_path": "/tmp/test_output.txt",
            "reason": "Writing task results to file",
        }

        approved = await self.request_approval(
            message="About to write results to file. Approve?", details=approval_details
        )

        if not approved:
            print("❌ User denied approval")
            return {"error": "Operation denied by user"}

        print("✓ User approved operation")

        # Step 4: Report progress (mid-point)
        print("\n📊 Step 4: Processing data...")
        await self.report_progress(
            message="Processing data...",
            percentage=0.5,
            metadata={"stage": "processing"},
        )

        # Simulate some work
        await asyncio.sleep(1)

        # Step 5: Execute the write operation
        print("\n💾 Step 5: Writing results...")
        result = await self.execute_tool(
            "write_file",
            {
                "path": "/tmp/test_output.txt",
                "content": f"Task: {task}\nFormat: {output_format}\nStatus: Completed",
            },
        )

        if not result.success:
            print(f"❌ Failed to write file: {result.error}")
            return {"error": result.error}

        print("✓ File written successfully")

        # Step 6: Report progress (completion)
        print("\n📊 Step 6: Finalizing...")
        await self.report_progress(
            message="Task completed!",
            percentage=1.0,
            metadata={"stage": "completed", "output_file": "/tmp/test_output.txt"},
        )

        return {
            "task": task,
            "format": output_format,
            "output_file": "/tmp/test_output.txt",
            "steps_completed": 6,
            "status": "success",
        }


# Step 6: Automated demo using MemoryTransport
async def main():
    """
    Main async function demonstrating Control Protocol.

    Note: This example uses MemoryTransport with pre-programmed responses
    for automated demonstration. In production, you would use:
    - CLITransport for terminal interaction
    - HTTPTransport for web-based interaction
    - StdioTransport for subprocess communication
    """

    print("=" * 80)
    print("KAIZEN INTERACTIVE CONTROL PROTOCOL AGENT - Example 3")
    print("=" * 80)

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found")
        return

    # Create tool registry
    print("\n🔧 Setting up tool registry...")
    print(f"✓ Registered {registry.count()} builtin tools")

    # Create control protocol with InMemoryTransport
    # This allows us to pre-program responses for automated demo
    print("\n🔌 Setting up Control Protocol (InMemory Transport for demo)...")
    transport = InMemoryTransport()
    protocol = ControlProtocol(transport=transport)
    await protocol.start()
    print("✓ Control Protocol initialized")

    # Pre-program responses for the demo
    # In real usage, these would come from actual user input
    print("\n📝 Pre-programming demo responses...")

    # Response for question: "Which output format would you like?"
    transport.queue_response(
        {
            "type": "question_response",
            "data": {
                "selected_option": "Markdown",
                "timestamp": "2025-10-21T00:00:00Z",
            },
        }
    )

    # Response for approval request
    transport.queue_response(
        {
            "type": "approval_response",
            "data": {
                "approved": True,
                "reason": "User approved the write operation",
                "timestamp": "2025-10-21T00:00:01Z",
            },
        }
    )

    print("✓ Demo responses queued")

    # Create interactive agent
    config = InteractiveAgentConfig()
    agent = InteractiveAgent(config=config, control_protocol=protocol)
    print("✓ Interactive agent initialized")

    # Execute task with user guidance
    print("\n" + "=" * 80)
    print("EXECUTING INTERACTIVE TASK")
    print("=" * 80)

    result = await agent.execute_with_user_guidance(
        "Generate a report about Kaizen capabilities"
    )

    # Display results
    print("\n" + "=" * 80)
    print("EXECUTION RESULTS")
    print("=" * 80)

    if "error" not in result:
        print("\n✅ Task completed successfully!")
        print(f"\n  Task: {result['task']}")
        print(f"  Format: {result['format']}")
        print(f"  Output File: {result['output_file']}")
        print(f"  Steps Completed: {result['steps_completed']}")
        print(f"  Status: {result['status']}")
    else:
        print(f"\n❌ Task failed: {result['error']}")

    # Shutdown protocol
    await protocol.stop()

    print("\n" + "=" * 80)
    print("✓ Control Protocol example completed!")
    print("=" * 80)

    # Production usage notes
    print("\n" + "=" * 80)
    print("PRODUCTION USAGE NOTES")
    print("=" * 80)
    print(
        """
For real interactive usage, replace InMemoryTransport with:

1. CLI Transport (Terminal-based interaction):
   from kaizen.core.autonomy.control.transports import CLITransport
   transport = CLITransport()

2. HTTP/SSE Transport (Web-based interaction):
   from kaizen.core.autonomy.control.transports import HTTPTransport
   transport = HTTPTransport(host="0.0.0.0", port=8000)

3. stdio Transport (Subprocess communication):
   from kaizen.core.autonomy.control.transports import StdioTransport
   transport = StdioTransport()

The agent code remains the same - only the transport changes!
"""
    )


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
