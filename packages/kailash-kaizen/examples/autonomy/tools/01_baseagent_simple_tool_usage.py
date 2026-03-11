"""
Simple Tool Usage with BaseAgent

Demonstrates basic tool calling with BaseAgent using MCP (Model Context Protocol).

Key Concepts:
    - BaseAgent MCP auto-connect (12 builtin tools automatically available)
    - MCP tool discovery with filtering
    - MCP tool execution
    - Tool naming convention: mcp__<serverName>__<toolName>

Example Output:
    $ python examples/autonomy/tools/01_baseagent_simple_tool_usage.py

    Available MCP tools: 12
    Tool: mcp__kaizen_builtin__read_file - Read file contents [LOW]
    Tool: mcp__kaizen_builtin__write_file - Write content to file [MEDIUM]
    Tool: mcp__kaizen_builtin__file_exists - Check if file exists [SAFE]

    Reading file: /tmp/test_data.txt
    File content: Hello from BaseAgent MCP integration!
    File size: 42 bytes
"""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class FileProcessorSignature(Signature):
    """Signature for file processing agent."""

    task: str = InputField(description="File processing task to perform")
    result: str = OutputField(description="Processing result")


@dataclass
class FileProcessorConfig:
    """Configuration for file processor agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.0


class FileProcessorAgent(BaseAgent):
    """Agent that processes files using MCP tool calling."""

    def __init__(self, config: FileProcessorConfig):
        # MCP auto-connect: BaseAgent automatically connects to kaizen_builtin MCP server
        # This provides 12 builtin tools (file operations, HTTP, bash, web)
        super().__init__(
            config=config,
            signature=FileProcessorSignature(),
            # No mcp_servers parameter = auto-connect to kaizen_builtin
        )


async def main():
    """Demonstrate simple MCP tool usage with BaseAgent."""
    print("\n" + "=" * 80)
    print("BaseAgent MCP Tool Usage Example")
    print("=" * 80 + "\n")

    # Step 1: Create agent (MCP auto-connects to kaizen_builtin)
    config = FileProcessorConfig()
    agent = FileProcessorAgent(config=config)

    # Step 2: Verify MCP support is enabled
    assert agent.has_mcp_support(), "MCP support should be enabled"
    print("✓ MCP auto-connected to kaizen_builtin server\n")

    # Step 3: Discover available MCP tools
    all_tools = await agent.discover_mcp_tools()
    print(f"Available MCP tools: {len(all_tools)}")

    # Show file-related tools (first 5)
    file_tools = [t for t in all_tools if "file" in t["name"]]
    for tool in file_tools[:5]:
        print(f"  - {tool['name']}: {tool['description']}")
    print()

    # Step 4: Create test file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
        test_content = "Hello from BaseAgent MCP integration!"
        f.write(test_content)
        test_file = f.name

    try:
        # Step 5: Use MCP tool to read file
        # MCP tool naming: mcp__<serverName>__<toolName>
        print(f"Reading file: {test_file}")
        result = await agent.execute_mcp_tool(
            "mcp__kaizen_builtin__read_file",
            {"path": test_file},
        )

        # Step 6: Handle result
        if result.get("success"):
            content = result.get("content", result.get("result", {}).get("content", ""))
            print(f"File content: {content}")

            # File size from stat
            file_size = Path(test_file).stat().st_size
            print(f"File size: {file_size} bytes\n")
        else:
            error = result.get("error", "Unknown error")
            print(f"Tool execution failed: {error}\n")

        # Step 7: Demonstrate file_exists tool (SAFE - auto-approved)
        print("Checking file existence...")
        exists_result = await agent.execute_mcp_tool(
            "mcp__kaizen_builtin__file_exists",
            {"path": test_file},
        )

        if exists_result.get("success"):
            print(f"  exists: {exists_result.get('exists', True)}")
            print("  SAFE tool (auto-approved by kaizen_builtin)\n")

    finally:
        # Cleanup
        Path(test_file).unlink()
        print("=" * 80)
        print("Example completed successfully!")
        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
