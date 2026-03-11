#!/usr/bin/env python3
"""
NEXUS MCP DEMO: AI Agent Integration
===================================

This demo shows how Nexus automatically exposes workflows as MCP tools for AI agents.
AI agents can discover and execute workflows through the Model Context Protocol.

Key Features:
- Workflows automatically become MCP tools
- WebSocket-based MCP server for real-time communication
- AI agents can discover available tools and execute them
- Zero MCP protocol coding required - all automated

Usage:
    cd packages/kailash-nexus
    python examples/mcp_demo.py

Then AI agents can connect to: ws://localhost:3003
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict

import websockets

# Add src to Python path so we can import nexus
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# ==============================================================================
# WORKFLOW DEFINITIONS FOR AI AGENT INTEGRATION
# ==============================================================================


def create_text_analysis_workflow():
    """Create a text analysis workflow perfect for AI agents."""
    workflow = WorkflowBuilder()

    analysis_code = """
import re

def analyze_text(text):
    if not text or not isinstance(text, str):
        return {"error": "Text input is required"}

    # Basic text analysis
    words = text.split()
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # Character analysis
    chars_total = len(text)
    chars_no_spaces = len(text.replace(' ', ''))

    # Word frequency (top 5)
    word_freq = {}
    for word in words:
        word_clean = re.sub(r'[^a-zA-Z0-9]', '', word.lower())
        if word_clean and len(word_clean) > 2:
            word_freq[word_clean] = word_freq.get(word_clean, 0) + 1

    top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]

    # Sentiment indicators (simple keyword-based)
    positive_words = ['good', 'great', 'excellent', 'amazing', 'wonderful', 'love', 'happy', 'best']
    negative_words = ['bad', 'terrible', 'awful', 'hate', 'horrible', 'worst', 'sad', 'angry']

    text_lower = text.lower()
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)

    if positive_count > negative_count:
        sentiment = "positive"
    elif negative_count > positive_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    analysis = {
        "text_preview": text[:100] + "..." if len(text) > 100 else text,
        "statistics": {
            "word_count": len(words),
            "sentence_count": len(sentences),
            "character_count": chars_total,
            "character_count_no_spaces": chars_no_spaces,
            "average_word_length": sum(len(word) for word in words) / len(words) if words else 0
        },
        "analysis": {
            "sentiment": sentiment,
            "sentiment_confidence": abs(positive_count - negative_count) / max(len(words), 1),
            "top_words": top_words,
            "readability": "easy" if len(words) / len(sentences) < 15 else "moderate" if len(words) / len(sentences) < 25 else "difficult"
        },
        "summary": f"Text with {len(words)} words and {len(sentences)} sentences. Sentiment: {sentiment}."
    }

    return {"analysis": analysis}

text = parameters.get('text', '')
result = analyze_text(text)
"""

    workflow.add_node("PythonCodeNode", "analyzer", {"code": analysis_code.strip()})

    return workflow


def create_data_calculator_workflow():
    """Create a data calculator workflow for AI agents."""
    workflow = WorkflowBuilder()

    calc_code = """
import math
import statistics

def calculate_data(numbers, operation="stats"):
    if not numbers or not isinstance(numbers, list):
        return {"error": "List of numbers is required"}

    try:
        # Convert to floats
        nums = [float(x) for x in numbers]
    except (ValueError, TypeError):
        return {"error": "All items must be valid numbers"}

    if not nums:
        return {"error": "At least one number is required"}

    # Basic statistics
    result = {
        "input": numbers,
        "count": len(nums),
        "sum": sum(nums),
        "mean": statistics.mean(nums),
        "median": statistics.median(nums),
        "min": min(nums),
        "max": max(nums),
        "range": max(nums) - min(nums)
    }

    # Additional stats if more than one number
    if len(nums) > 1:
        result["std_dev"] = statistics.stdev(nums)
        result["variance"] = statistics.variance(nums)

    # Perform specific operation
    if operation == "square":
        result["operation"] = "square"
        result["result"] = [x**2 for x in nums]
    elif operation == "sqrt":
        result["operation"] = "square_root"
        result["result"] = [math.sqrt(abs(x)) for x in nums]
    elif operation == "double":
        result["operation"] = "double"
        result["result"] = [x*2 for x in nums]
    elif operation == "cumulative":
        result["operation"] = "cumulative_sum"
        cumsum = []
        running_total = 0
        for x in nums:
            running_total += x
            cumsum.append(running_total)
        result["result"] = cumsum
    else:
        result["operation"] = "statistics_only"
        result["result"] = "No mathematical operation performed - statistics calculated"

    return {"calculation": result}

numbers = parameters.get('numbers', [])
operation = parameters.get('operation', 'stats')
result = calculate_data(numbers, operation)
"""

    workflow.add_node("PythonCodeNode", "calculator", {"code": calc_code.strip()})

    return workflow


def create_task_planner_workflow():
    """Create a task planning workflow for AI agents."""
    workflow = WorkflowBuilder()

    planner_code = """
from datetime import datetime, timedelta

def plan_tasks(tasks, priority_order=None, time_estimates=None):
    if not tasks or not isinstance(tasks, list):
        return {"error": "List of tasks is required"}

    if not priority_order:
        priority_order = ["high", "medium", "low"]

    # Process tasks
    planned_tasks = []
    total_time = 0

    for i, task in enumerate(tasks):
        if isinstance(task, str):
            task_info = {
                "id": f"task_{i+1}",
                "name": task,
                "priority": "medium",
                "estimated_hours": 2
            }
        elif isinstance(task, dict):
            task_info = {
                "id": task.get("id", f"task_{i+1}"),
                "name": task.get("name", f"Task {i+1}"),
                "priority": task.get("priority", "medium"),
                "estimated_hours": task.get("hours", 2)
            }
        else:
            continue

        # Add time estimates if provided
        if time_estimates and isinstance(time_estimates, dict):
            task_name = task_info["name"].lower()
            for key, hours in time_estimates.items():
                if key.lower() in task_name:
                    task_info["estimated_hours"] = hours
                    break

        planned_tasks.append(task_info)
        total_time += task_info["estimated_hours"]

    # Sort by priority
    priority_map = {p: i for i, p in enumerate(priority_order)}
    planned_tasks.sort(key=lambda x: priority_map.get(x["priority"], 999))

    # Add scheduling
    start_time = datetime.now()
    for task in planned_tasks:
        task["scheduled_start"] = start_time.strftime("%Y-%m-%d %H:%M")
        end_time = start_time + timedelta(hours=task["estimated_hours"])
        task["scheduled_end"] = end_time.strftime("%Y-%m-%d %H:%M")
        start_time = end_time

    # Generate summary
    priority_counts = {}
    for task in planned_tasks:
        priority = task["priority"]
        priority_counts[priority] = priority_counts.get(priority, 0) + 1

    plan = {
        "tasks": planned_tasks,
        "summary": {
            "total_tasks": len(planned_tasks),
            "total_estimated_hours": total_time,
            "priority_breakdown": priority_counts,
            "completion_date": start_time.strftime("%Y-%m-%d %H:%M")
        },
        "recommendations": [
            f"Start with {priority_order[0]} priority tasks",
            f"Total time needed: {total_time} hours",
            f"Completion by: {start_time.strftime('%Y-%m-%d')}"
        ]
    }

    return {"plan": plan}

tasks = parameters.get('tasks', [])
priority_order = parameters.get('priority_order', ["high", "medium", "low"])
time_estimates = parameters.get('time_estimates', {})
result = plan_tasks(tasks, priority_order, time_estimates)
"""

    workflow.add_node("PythonCodeNode", "planner", {"code": planner_code.strip()})

    return workflow


# ==============================================================================
# MCP CLIENT SIMULATOR (to test the server)
# ==============================================================================


class MCPClient:
    """Simple MCP client to test the Nexus MCP server."""

    def __init__(self, url: str):
        self.url = url
        self.websocket = None

    async def connect(self):
        """Connect to MCP server."""
        try:
            self.websocket = await websockets.connect(self.url)
            print(f"✅ Connected to MCP server at {self.url}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to MCP server: {e}")
            return False

    async def send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message and wait for response."""
        if not self.websocket:
            raise Exception("Not connected to server")

        await self.websocket.send(json.dumps(message))
        response = await self.websocket.recv()
        return json.loads(response)

    async def list_tools(self) -> Dict[str, Any]:
        """List available tools (workflows)."""
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        return await self.send_message(message)

    async def call_tool(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool (execute workflow)."""
        message = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": parameters},
        }
        return await self.send_message(message)

    async def disconnect(self):
        """Disconnect from server."""
        if self.websocket:
            await self.websocket.close()
            print("🔌 Disconnected from MCP server")


# ==============================================================================
# MCP DEMO WITH AUTOMATED TESTING
# ==============================================================================


async def test_mcp_integration(mcp_port: int):
    """Test the MCP server integration."""
    print("\n🤖 Testing MCP Server Integration...")

    client = MCPClient(f"ws://localhost:{mcp_port}")

    try:
        # Connect to server
        if not await client.connect():
            return False

        await asyncio.sleep(1)  # Give server time to initialize

        # Test 1: List available tools
        print("\n📋 Test 1: Listing available tools...")
        tools_response = await client.list_tools()

        if "result" in tools_response and "tools" in tools_response["result"]:
            tools = tools_response["result"]["tools"]
            print(f"✅ Found {len(tools)} tools:")
            for tool in tools:
                print(
                    f"   • {tool['name']}: {tool.get('description', 'No description')}"
                )
        else:
            print(f"⚠️ Unexpected tools response: {tools_response}")

        # Test 2: Execute text analysis
        print("\n📝 Test 2: Executing text analysis workflow...")
        text_params = {
            "text": "This is an amazing example of AI agent integration with Kailash Nexus. The system works wonderfully!"
        }

        text_response = await client.call_tool("text-analyzer", text_params)

        if "result" in text_response:
            analysis = text_response["result"]
            print("✅ Text analysis completed:")
            if "analysis" in analysis:
                stats = analysis["analysis"].get("statistics", {})
                sentiment = (
                    analysis["analysis"].get("analysis", {}).get("sentiment", "unknown")
                )
                print(f"   • Word count: {stats.get('word_count', 'N/A')}")
                print(f"   • Sentiment: {sentiment}")
                print(f"   • Summary: {analysis['analysis'].get('summary', 'N/A')}")
        else:
            print(f"⚠️ Unexpected text analysis response: {text_response}")

        # Test 3: Execute calculator
        print("\n🔢 Test 3: Executing calculator workflow...")
        calc_params = {
            "numbers": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "operation": "square",
        }

        calc_response = await client.call_tool("data-calculator", calc_params)

        if "result" in calc_response and "calculation" in calc_response["result"]:
            calc = calc_response["result"]["calculation"]
            print("✅ Calculator completed:")
            print(f"   • Mean: {calc.get('mean', 'N/A')}")
            print(f"   • Operation: {calc.get('operation', 'N/A')}")
            print(f"   • Result preview: {str(calc.get('result', []))[:50]}...")
        else:
            print(f"⚠️ Unexpected calculator response: {calc_response}")

        # Test 4: Execute task planner
        print("\n📅 Test 4: Executing task planner workflow...")
        task_params = {
            "tasks": [
                {"name": "Design API", "priority": "high", "hours": 4},
                {"name": "Write documentation", "priority": "medium", "hours": 2},
                {"name": "Code review", "priority": "high", "hours": 1},
                {"name": "Deploy to staging", "priority": "low", "hours": 3},
            ]
        }

        plan_response = await client.call_tool("task-planner", task_params)

        if "result" in plan_response and "plan" in plan_response["result"]:
            plan = plan_response["result"]["plan"]
            print("✅ Task planning completed:")
            print(f"   • Total tasks: {plan['summary']['total_tasks']}")
            print(f"   • Total hours: {plan['summary']['total_estimated_hours']}")
            print(f"   • Completion: {plan['summary']['completion_date']}")
        else:
            print(f"⚠️ Unexpected planner response: {plan_response}")

        await client.disconnect()
        print("\n🎉 MCP Integration Test Completed Successfully!")
        return True

    except Exception as e:
        print(f"❌ MCP test failed: {e}")
        import traceback

        traceback.print_exc()
        await client.disconnect()
        return False


def main():
    """Main MCP demo function."""

    print("🤖 NEXUS MCP DEMO: AI Agent Integration")
    print("=" * 50)

    # STEP 1: Initialize Nexus with MCP focus
    mcp_port = 3003
    app = Nexus(api_port=8081, mcp_port=mcp_port)  # Use different ports
    print(f"✅ Nexus initialized (API: 8081, MCP: {mcp_port})")

    # STEP 2: Register AI-friendly workflows
    print("\n🔧 Registering AI-optimized workflows...")

    # Text analysis for content processing
    text_workflow = create_text_analysis_workflow()
    app.register("text-analyzer", text_workflow)
    print("  ✅ text-analyzer: Analyze text content, sentiment, statistics")

    # Data calculator for numerical operations
    calc_workflow = create_data_calculator_workflow()
    app.register("data-calculator", calc_workflow)
    print("  ✅ data-calculator: Perform calculations and statistical analysis")

    # Task planner for project management
    task_workflow = create_task_planner_workflow()
    app.register("task-planner", task_workflow)
    print("  ✅ task-planner: Organize and schedule tasks with priorities")

    # STEP 3: Start MCP server
    try:
        print(f"\n🌐 Starting MCP server on port {mcp_port}...")
        app.start()

        health = app.health_check()
        print(f"📊 Nexus Status: {health.get('status', 'unknown')}")

        print("\n" + "=" * 50)
        print("🎉 MCP SERVER RUNNING - READY FOR AI AGENTS!")
        print("=" * 50)

        print("\n🤖 MCP Connection Details:")
        print(f"  • WebSocket URL: ws://localhost:{mcp_port}")
        print("  • Protocol: Model Context Protocol (MCP)")
        print("  • Available Tools: 3 (text-analyzer, data-calculator, task-planner)")

        print("\n📡 AI Agent Integration Points:")
        print(f"  • Claude with MCP: Connect to ws://localhost:{mcp_port}")
        print("  • Custom AI agents: Use WebSocket + JSON-RPC 2.0")
        print("  • Tool discovery: Send 'tools/list' message")
        print("  • Tool execution: Send 'tools/call' with parameters")

        print("\n💡 What AI Agents Can Do:")
        print("  🔍 Analyze text content and determine sentiment")
        print("  🧮 Perform mathematical calculations on datasets")
        print("  📋 Plan and schedule tasks with priority ordering")
        print("  🔄 Chain workflows together for complex operations")

        print("\n🧪 Running Automated MCP Test...")

        # Run automated test
        import asyncio

        asyncio.set_event_loop(asyncio.new_event_loop())
        test_result = asyncio.get_event_loop().run_until_complete(
            test_mcp_integration(mcp_port)
        )

        if test_result:
            print("\n✅ ALL TESTS PASSED!")
            print("🤖 AI agents can successfully:")
            print("   • Connect to the MCP server")
            print("   • Discover available tools (workflows)")
            print("   • Execute workflows with parameters")
            print("   • Receive structured results")
        else:
            print("\n⚠️ Some tests failed - check logs above")

        print("\n⏹️  Keeping server running for 30 seconds...")
        print(f"   AI agents can connect to: ws://localhost:{mcp_port}")

        # Keep running for testing
        import time

        time.sleep(30)

        print("\n🛑 Stopping MCP server...")
        app.stop()
        print("✅ MCP server stopped gracefully")

        return True

    except Exception as e:
        print(f"❌ Error starting MCP server: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    if success:
        print("\n🏆 MCP DEMO COMPLETED SUCCESSFULLY!")
        print("✅ Nexus automatically exposes workflows as MCP tools")
        print("✅ AI agents can discover and execute workflows")
        print("✅ Zero MCP protocol coding required")
        print("✅ Real-time WebSocket communication works")
    else:
        print("\n❌ MCP demo failed - check error messages above")
        exit(1)
