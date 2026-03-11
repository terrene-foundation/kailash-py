"""
HTTP Tool Usage with BaseAgent MCP

Demonstrates using MCP HTTP tools for API interactions.

Key Concepts:
    - HTTP tools via MCP (GET, POST, PUT, DELETE)
    - MCP tool naming: mcp__kaizen_builtin__http_get, etc.
    - kaizen_builtin MCP server provides HTTP tools

Example Output:
    $ python examples/autonomy/tools/03_baseagent_http_tools.py

    Available HTTP tools: 4
    Tool: mcp__kaizen_builtin__http_get - GET HTTP request
    Tool: mcp__kaizen_builtin__http_post - POST HTTP request

    Making GET request...
    Response status: 200
    Content preview: <!doctype html>...
"""

import asyncio
from dataclasses import dataclass

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class APIClientSignature(Signature):
    """Signature for API client agent."""

    request: str = InputField(description="API request to make")
    response: str = OutputField(description="API response")


@dataclass
class APIClientConfig:
    """Configuration for API client agent."""

    llm_provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.0


class APIClientAgent(BaseAgent):
    """Agent that makes API requests using MCP HTTP tools."""

    def __init__(self, config: APIClientConfig):
        # MCP auto-connect: BaseAgent automatically connects to kaizen_builtin MCP server
        super().__init__(
            config=config,
            signature=APIClientSignature(),
        )


async def main():
    """Demonstrate MCP HTTP tool usage with BaseAgent."""
    print("\n" + "=" * 80)
    print("BaseAgent MCP HTTP Tools Example")
    print("=" * 80 + "\n")

    # Step 1: Create agent (MCP auto-connect)
    config = APIClientConfig()
    agent = APIClientAgent(config=config)

    # Step 2: Discover available MCP tools
    all_tools = await agent.discover_mcp_tools()
    http_tools = [t for t in all_tools if "http" in t["name"]]

    print(f"Available HTTP tools: {len(http_tools)}")
    for tool in http_tools:
        print(f"  - {tool['name']}: {tool['description']}")
    print()

    # Step 3: Make GET request using MCP
    print("Making GET request to example.com...")
    try:
        result = await agent.execute_mcp_tool(
            "mcp__kaizen_builtin__http_get",
            {"url": "https://example.com", "timeout": 10},
        )

        if result.get("success") or "status_code" in result:
            status = result.get("status_code", 200)
            body = result.get("body", result.get("content", ""))
            print(f"Response status: {status}")
            print(f"Content preview: {body[:100] if body else '(no content)'}...\n")
        else:
            error = result.get("error", "Unknown error")
            print(f"Request failed: {error}\n")

    except Exception as e:
        print(f"Request exception: {e}\n")

    # Step 4: Show HTTP tool info
    print("HTTP Tool Information:")
    print("  mcp__kaizen_builtin__http_get    - GET requests (read-only)")
    print("  mcp__kaizen_builtin__http_post   - POST requests (create data)")
    print("  mcp__kaizen_builtin__http_put    - PUT requests (update data)")
    print("  mcp__kaizen_builtin__http_delete - DELETE requests (delete data)")
    print()

    print("=" * 80)
    print("HTTP tools demonstration completed!")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
