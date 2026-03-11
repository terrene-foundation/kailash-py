#!/usr/bin/env python3
"""
Standalone demonstration of the MCP integration bug and its fix.

This script demonstrates the exact error that occurs when using .get()
on OpenAI Pydantic models instead of attribute access.

Bug Report: 'ChatCompletionMessageFunctionToolCall' object has no attribute 'get'
Root Cause: OpenAI library returns Pydantic models, not dictionaries for function calls

Run this script to see:
1. The exact error that breaks MCP functionality
2. The working solution using attribute access
"""

import json

from openai.types.chat import ChatCompletionMessageToolCall


def demonstrate_bug():
    """Demonstrate the exact MCP integration bug."""
    print("🐛 DEMONSTRATING MCP INTEGRATION BUG")
    print("=" * 50)

    # Create a real OpenAI tool call (what the API actually returns)
    tool_call = ChatCompletionMessageToolCall(
        id="call_demo",
        type="function",
        function={"name": "demo_tool", "arguments": '{"param": "value"}'},
    )

    print(f"Tool call type: {type(tool_call)}")
    print(f"Tool call: {tool_call}")
    print(f"Has .get() method: {hasattr(tool_call, 'get')}")
    print(f"Has .model_dump() method: {hasattr(tool_call, 'model_dump')}")
    print()

    # This is what the current LLMAgentNode code tries to do (BROKEN)
    print("💥 BROKEN CODE (from LLMAgentNode lines 1860-1861):")
    print("tool_name = tool_call.get('function', {}).get('name', '')")

    try:
        tool_name = tool_call.get("function", {}).get("name", "")
        print(f"✅ Success: {tool_name}")
    except AttributeError as e:
        print(f"❌ ERROR: {e}")

    print()


def demonstrate_solution():
    """Demonstrate the working solution."""
    print("✅ DEMONSTRATING THE FIX")
    print("=" * 50)

    # Create the same tool call
    tool_call = ChatCompletionMessageToolCall(
        id="call_demo",
        type="function",
        function={"name": "demo_tool", "arguments": '{"param": "value"}'},
    )

    # SOLUTION 1: Use attribute access (RECOMMENDED)
    print("🔧 SOLUTION 1: Attribute access (recommended)")
    print("tool_name = tool_call.function.name")
    print("tool_args = json.loads(tool_call.function.arguments)")
    print("tool_id = tool_call.id")

    tool_name = tool_call.function.name
    tool_args = json.loads(tool_call.function.arguments)
    tool_id = tool_call.id

    print(f"✅ tool_name: {tool_name}")
    print(f"✅ tool_args: {tool_args}")
    print(f"✅ tool_id: {tool_id}")
    print()

    # SOLUTION 2: Use .model_dump() to convert to dict (ALTERNATIVE)
    print("🔧 SOLUTION 2: Convert to dict (alternative)")
    print("tool_dict = tool_call.model_dump()")
    print("tool_name = tool_dict['function']['name']")

    tool_dict = tool_call.model_dump()
    tool_name_dict = tool_dict["function"]["name"]
    tool_args_dict = json.loads(tool_dict["function"]["arguments"])

    print(f"✅ tool_name: {tool_name_dict}")
    print(f"✅ tool_args: {tool_args_dict}")
    print()


def demonstrate_affected_lines():
    """Show all the lines in LLMAgentNode that need fixing."""
    print("📍 AFFECTED LINES IN LLMAgentNode")
    print("=" * 50)

    affected_lines = [
        (
            "1860-1861",
            "_execute_mcp_tool_call",
            "tool_call.get('function', {}).get('name', '')",
        ),
        ("1866", "MCP tool lookup", "tool.get('function', {}).get('name')"),
        (
            "1874",
            "Server config extraction",
            "mcp_tool.get('function', {}).get('mcp_server_config', {})",
        ),
        ("1920", "MCP tool names dict", "tool.get('function', {}).get('name'): tool"),
        ("1925", "_process_tool_results", "tool_call.get('function', {}).get('name')"),
        (
            "1952",
            "Error handling",
            "tool_call.get('function', {}).get('name', 'unknown')",
        ),
    ]

    for line_num, method, broken_code in affected_lines:
        print(f"Line {line_num} ({method}):")
        print(f"  ❌ Broken: {broken_code}")

        if "tool_call.get" in broken_code:
            fixed_code = broken_code.replace(
                "tool_call.get('function', {})", "tool_call.function"
            )
            fixed_code = fixed_code.replace(".get('name')", ".name")
            fixed_code = fixed_code.replace(".get('name', '')", ".name")
            fixed_code = fixed_code.replace(".get('name', 'unknown')", ".name")
            print(f"  ✅ Fixed:  {fixed_code}")
        elif "tool.get" in broken_code:
            print(
                f"  ✅ Fixed:  {broken_code}"
            )  # These are actually fine since tool is a dict
        elif "mcp_tool.get" in broken_code:
            print(
                f"  ✅ Fixed:  {broken_code}"
            )  # These are fine since mcp_tool is a dict

        print()


def main():
    """Run the complete demonstration."""
    print("🔍 MCP INTEGRATION BUG DEMONSTRATION")
    print("OpenAI version with Pydantic models vs dictionary access")
    print("=" * 60)
    print()

    demonstrate_bug()
    print()
    demonstrate_solution()
    print()
    demonstrate_affected_lines()

    print("🎯 SUMMARY")
    print("=" * 50)
    print("❌ Problem: OpenAI library returns Pydantic models, not dictionaries")
    print("❌ Error: 'ChatCompletionMessageToolCall' object has no attribute 'get'")
    print(
        "✅ Solution: Use attribute access (tool_call.function.name) instead of .get()"
    )
    print("📍 Impact: 6 lines in LLMAgentNode need fixing for MCP integration")
    print()
    print("🧪 Run the comprehensive test:")
    print("pytest tests/integration/nodes/ai/test_llm_agent_mcp_pydantic_bug.py -v")


if __name__ == "__main__":
    main()
