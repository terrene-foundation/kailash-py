"""
Tool Chaining with BaseAgent MCP

Demonstrates executing multiple MCP tools in sequence.

Key Concepts:
    - Sequential MCP tool execution (manual chaining)
    - MCP tool naming: mcp__<serverName>__<toolName>
    - kaizen_builtin MCP server (12 builtin tools)
    - Error handling in tool sequences

Example Output:
    $ python examples/autonomy/tools/02_baseagent_tool_chain.py

    Executing tool chain with 4 operations...
    ✓ Tool 1: file_exists - Success
    ✓ Tool 2: write_file - Success
    ✓ Tool 3: read_file - Success
    ✓ Tool 4: delete_file - Success
"""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class DataProcessorSignature(Signature):
    """Signature for data processing agent."""

    operation: str = InputField(description="Data processing operation")
    result: str = OutputField(description="Operation result")


@dataclass
class DataProcessorConfig:
    """Configuration for data processor agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.0


class DataProcessorAgent(BaseAgent):
    """Agent that processes data using MCP tools in sequence."""

    def __init__(self, config: DataProcessorConfig):
        # MCP auto-connect: BaseAgent automatically connects to kaizen_builtin MCP server
        super().__init__(
            config=config,
            signature=DataProcessorSignature(),
        )


async def main():
    """Demonstrate MCP tool chaining with BaseAgent."""
    print("\n" + "=" * 80)
    print("BaseAgent MCP Tool Chain Example")
    print("=" * 80 + "\n")

    # Step 1: Create agent (MCP auto-connect)
    config = DataProcessorConfig()
    agent = DataProcessorAgent(config=config)

    # Step 2: Create temp file path
    temp_dir = tempfile.gettempdir()
    test_file = Path(temp_dir) / "chain_test.txt"

    try:
        # Step 3: Execute tool chain manually
        print("Executing tool chain with 4 operations...\n")

        # Define chain (manual sequential execution)
        chain = [
            ("file_exists", {"path": str(test_file)}, "Check if file exists"),
            (
                "write_file",
                {"path": str(test_file), "content": "Tool chain demonstration"},
                "Write file",
            ),
            ("read_file", {"path": str(test_file)}, "Read file back"),
            ("delete_file", {"path": str(test_file)}, "Delete file"),
        ]

        results = []

        # Step 4: Execute each tool in sequence
        for i, (tool_name, params, description) in enumerate(chain, 1):
            # MCP tool naming convention
            mcp_tool_name = f"mcp__kaizen_builtin__{tool_name}"

            print(f"Tool {i}: {description} ({tool_name})...", end=" ")

            try:
                result = await agent.execute_mcp_tool(mcp_tool_name, params)
                success = result.get("success", False)

                if success or "error" not in result:
                    print("✓ Success")
                    results.append(
                        {"tool": tool_name, "success": True, "result": result}
                    )
                else:
                    print(f"✗ Failed: {result.get('error')}")
                    results.append(
                        {
                            "tool": tool_name,
                            "success": False,
                            "error": result.get("error"),
                        }
                    )
                    # Stop on error
                    break

            except Exception as e:
                print(f"✗ Exception: {e}")
                results.append({"tool": tool_name, "success": False, "error": str(e)})
                break

        # Step 5: Show summary
        print("\n" + "=" * 80)
        success_count = sum(1 for r in results if r["success"])
        print(f"Tool chain completed: {success_count}/{len(chain)} tools successful")
        print("=" * 80 + "\n")

    finally:
        # Cleanup - remove file if it still exists
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    asyncio.run(main())
