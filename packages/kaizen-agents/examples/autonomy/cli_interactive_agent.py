#!/usr/bin/env python3
"""
CLI Interactive Agent Example

Demonstrates CLITransport usage for interactive CLI applications where
the agent can ask questions and request approvals during execution.

Architecture:
    1. Agent runs as main process
    2. Agent writes control requests to stdout
    3. User reads from stdout, types responses to stdin
    4. Agent reads responses from stdin
    5. Bidirectional communication enables autonomy

Usage:
    # Run agent (simulates autonomous agent asking questions)
    python examples/autonomy/cli_interactive_agent.py

    # The agent will prompt you with questions via control protocol
    # You respond by typing JSON responses

Example Session:
    Agent: {"request_id": "req_abc123", "type": "question", "data": {...}}
    User: {"request_id": "req_abc123", "data": {"answer": "yes"}, "error": null}

Key Concepts:
    - CLITransport for terminal-based communication
    - ControlProtocol for request/response pairing
    - Line-based JSON protocol
    - Interactive user input during agent execution

See Also:
    - ADR-011: Control Protocol Architecture
    - docs/guides/control-protocol-tutorial.md
"""

import json
import sys

import anyio
from kaizen.core.autonomy.control import (
    CLITransport,
    ControlProtocol,
    ControlRequest,
    ControlResponse,
)


async def simulate_agent_with_questions():
    """
    Simulate an autonomous agent that asks questions during execution.

    This demonstrates how an agent would use CLITransport and ControlProtocol
    to ask clarifying questions or request approvals.

    Flow:
        1. Connect transport
        2. Start control protocol
        3. Ask multiple questions
        4. Process user responses
        5. Complete task
        6. Stop protocol
    """
    print("=" * 60, file=sys.stderr)
    print("CLI Interactive Agent Example", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    # Create and connect transport
    transport = CLITransport()
    await transport.connect()

    print("[Agent] Transport connected (stdin/stdout)", file=sys.stderr)
    print("", file=sys.stderr)

    # Create protocol
    protocol = ControlProtocol(transport=transport)

    # Start protocol (launches background message reader)
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        print("[Agent] Control protocol started", file=sys.stderr)
        print("", file=sys.stderr)

        # Simulate agent asking questions during execution
        print("[Agent] Starting autonomous task...", file=sys.stderr)
        print("", file=sys.stderr)

        # Question 1: User confirmation
        print("[Agent] Need user confirmation to proceed...", file=sys.stderr)

        request1 = ControlRequest.create(
            type="question",
            data={"question": "Delete all temporary files?", "options": ["yes", "no"]},
        )

        print(f"[Agent] Sending request: {request1.request_id}", file=sys.stderr)
        print("", file=sys.stderr)

        # In a real CLI scenario, this would timeout waiting for user input
        # For demo purposes, we'll use a short timeout and handle it
        try:
            # Send request and wait for response
            response1 = await protocol.send_request(request1, timeout=30.0)

            print(f"[Agent] Received response: {response1.data}", file=sys.stderr)
            print("", file=sys.stderr)

            if response1.data.get("answer") == "yes":
                print("[Agent] User confirmed deletion. Proceeding...", file=sys.stderr)
            else:
                print("[Agent] User declined deletion. Skipping...", file=sys.stderr)

        except TimeoutError:
            print("[Agent] No response received. Using default: no", file=sys.stderr)

        print("", file=sys.stderr)

        # Question 2: Approval for risky action
        print("[Agent] Need approval for risky operation...", file=sys.stderr)

        request2 = ControlRequest.create(
            type="approval",
            data={
                "action": "modify_production_database",
                "details": {
                    "database": "production_db",
                    "operation": "UPDATE",
                    "affected_rows": 1500,
                },
            },
        )

        print(f"[Agent] Sending request: {request2.request_id}", file=sys.stderr)
        print("", file=sys.stderr)

        try:
            response2 = await protocol.send_request(request2, timeout=30.0)

            print(f"[Agent] Received response: {response2.data}", file=sys.stderr)
            print("", file=sys.stderr)

            if response2.data.get("approved"):
                print("[Agent] Operation approved. Executing...", file=sys.stderr)
            else:
                print("[Agent] Operation denied. Aborting...", file=sys.stderr)

        except TimeoutError:
            print("[Agent] No response received. Aborting for safety.", file=sys.stderr)

        print("", file=sys.stderr)
        print("[Agent] Task complete!", file=sys.stderr)

        # Stop protocol
        await protocol.stop()
        print("[Agent] Protocol stopped", file=sys.stderr)

    await transport.close()
    print("[Agent] Transport closed", file=sys.stderr)


async def simulate_cli_client_responder():
    """
    Simulate a CLI client that responds to agent requests.

    This would normally be a separate process or the user typing JSON responses.
    For demo purposes, this simulates automated responses.

    Flow:
        1. Read requests from stdin (agent's stdout)
        2. Parse JSON
        3. Generate response
        4. Write response to stdout (agent's stdin)

    Note:
        In a real scenario, this would be:
        - User typing JSON manually
        - A wrapper script handling I/O formatting
        - A GUI client reading from agent's stdout
    """
    print("=" * 60, file=sys.stderr)
    print("CLI Client Responder (Simulated)", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)

    print("[Client] Listening for agent requests...", file=sys.stderr)
    print("", file=sys.stderr)

    # In a real scenario, this would read from agent's stdout
    # For demo, we'll simulate reading from stdin
    async for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        print(f"[Client] Received request: {line}", file=sys.stderr)

        try:
            # Parse request
            request_data = json.loads(line)
            request_id = request_data.get("request_id")
            request_type = request_data.get("type")
            data = request_data.get("data", {})

            print(f"[Client] Request type: {request_type}", file=sys.stderr)
            print(f"[Client] Request ID: {request_id}", file=sys.stderr)

            # Generate response based on type
            if request_type == "question":
                question = data.get("question")
                print(f"[Client] Question: {question}", file=sys.stderr)

                # Auto-respond "yes"
                response = ControlResponse(
                    request_id=request_id, data={"answer": "yes"}
                )

            elif request_type == "approval":
                action = data.get("action")
                print(f"[Client] Approval requested for: {action}", file=sys.stderr)

                # Auto-approve
                response = ControlResponse(
                    request_id=request_id, data={"approved": True}
                )

            else:
                # Unknown type
                response = ControlResponse(
                    request_id=request_id,
                    data=None,
                    error=f"Unknown request type: {request_type}",
                )

            # Write response to stdout (agent's stdin)
            response_json = response.to_json()
            print(response_json, flush=True)  # stdout for agent to read

            print(f"[Client] Sent response: {response_json}", file=sys.stderr)
            print("", file=sys.stderr)

        except json.JSONDecodeError as e:
            print(f"[Client] Invalid JSON: {e}", file=sys.stderr)
            continue


def print_usage():
    """Print usage instructions."""
    print("=" * 60)
    print("CLI Interactive Agent Example")
    print("=" * 60)
    print()
    print("This example demonstrates CLITransport for interactive CLI agents.")
    print()
    print("Two modes:")
    print("  1. agent   - Run as autonomous agent (asks questions)")
    print("  2. client  - Run as CLI client (responds to questions)")
    print()
    print("Usage:")
    print("  # Mode 1: Agent")
    print("  python examples/autonomy/cli_interactive_agent.py agent")
    print()
    print("  # Mode 2: Client (responds automatically)")
    print("  python examples/autonomy/cli_interactive_agent.py client")
    print()
    print("Interactive Usage (Manual):")
    print("  # Run agent and type JSON responses manually:")
    print('  {"request_id": "req_abc", "data": {"answer": "yes"}, "error": null}')
    print()
    print("Pipeline Usage (Automated):")
    print("  # Run agent piped to client:")
    print("  python examples/autonomy/cli_interactive_agent.py agent | \\")
    print("    python examples/autonomy/cli_interactive_agent.py client")
    print()
    print("=" * 60)


async def main():
    """Main entry point."""
    import sys

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    mode = sys.argv[1].lower()

    if mode == "agent":
        await simulate_agent_with_questions()

    elif mode == "client":
        await simulate_cli_client_responder()

    elif mode == "help" or mode == "--help" or mode == "-h":
        print_usage()

    else:
        print(f"Error: Unknown mode '{mode}'", file=sys.stderr)
        print("", file=sys.stderr)
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\n[Interrupted] Exiting...", file=sys.stderr)
        sys.exit(0)
