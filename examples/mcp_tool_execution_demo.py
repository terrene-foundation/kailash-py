#!/usr/bin/env python3
"""
Demonstration of MCP tool execution in LLMAgent.

This example shows how the LLMAgent can:
1. Discover tools from MCP servers
2. Execute tools when requested by the LLM
3. Handle multiple rounds of tool interactions
"""

from kailash.nodes.ai.llm_agent import LLMAgentNode


def main():
    """Run MCP tool execution demo."""
    # Create LLM agent
    agent = LLMAgentNode(name="tool_executor")

    # Define some example tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Perform mathematical calculations",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["add", "subtract", "multiply", "divide"],
                        },
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["operation", "a", "b"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather information for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"},
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "default": "celsius",
                        },
                    },
                    "required": ["location"],
                },
            },
        },
    ]

    # Example 1: Tool execution enabled (default)
    print("=== Example 1: Automatic Tool Execution ===")
    result = agent.execute(
        provider="mock",
        model="gpt-4",
        messages=[
            {
                "role": "user",
                "content": "Calculate 15 + 27 and then get the weather in Paris",
            }
        ],
        tools=tools,
        auto_execute_tools=True,  # Default is True
        tool_execution_config={
            "max_rounds": 3  # Allow up to 3 rounds of tool execution
        },
    )

    print(f"Success: {result['success']}")
    print(f"Tools available: {result['context']['tools_available']}")
    print(f"Tools executed: {result['context']['tools_executed']}")
    print(f"Response: {result['response']['content']}\n")

    # Example 2: Tool execution disabled
    print("=== Example 2: Tool Calls Without Execution ===")
    result = agent.execute(
        provider="mock",
        model="gpt-4",
        messages=[{"role": "user", "content": "Calculate 10 * 5"}],
        tools=tools,
        auto_execute_tools=False,  # Disable execution
    )

    print(f"Success: {result['success']}")
    print(f"Tools executed: {result['context']['tools_executed']}")
    if "tool_calls" in result["response"]:
        print(f"Tool calls returned: {len(result['response']['tool_calls'])}")
        for tool_call in result["response"]["tool_calls"]:
            print(f"  - Would call: {tool_call['function']['name']}")
    print()

    # Example 3: MCP server integration (mock)
    print("=== Example 3: MCP Server Tool Discovery ===")
    result = agent.execute(
        provider="mock",
        model="gpt-4",
        messages=[{"role": "user", "content": "Use MCP tools to create a report"}],
        mcp_servers=[
            {
                "name": "report-server",
                "transport": "stdio",
                "command": "echo",
                "args": ["mock-mcp-server"],
            }
        ],
        auto_discover_tools=True,
        auto_execute_tools=True,
    )

    print(f"Success: {result['success']}")
    print(f"MCP resources used: {result['context']['mcp_resources_used']}")
    print(f"Tools available: {result['context']['tools_available']}")

    # Example 4: Complex multi-step workflow
    print("\n=== Example 4: Multi-Step Tool Workflow ===")
    conversation = [
        {
            "role": "system",
            "content": "You are a helpful assistant with access to calculation and weather tools.",
        },
        {
            "role": "user",
            "content": "I'm planning a trip. Calculate my budget (500 + 300 + 150) and check the weather in London and Tokyo.",
        },
    ]

    result = agent.execute(
        provider="mock",
        model="gpt-4",
        messages=conversation,
        tools=tools,
        auto_execute_tools=True,
        tool_execution_config={
            "max_rounds": 5,  # May need multiple rounds
            "continue_on_error": True,  # Continue if a tool fails
        },
    )

    print(f"Success: {result['success']}")
    print(
        f"Tool execution rounds: {result['response'].get('tool_execution_rounds', 0)}"
    )
    print(f"Final response: {result['response']['content'][:200]}...")


if __name__ == "__main__":
    main()
