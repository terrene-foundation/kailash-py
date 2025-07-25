#!/usr/bin/env python3
"""
Test script to trigger the real A2A demo and capture step-by-step execution.
"""

import asyncio
import json
import time
from datetime import datetime

import requests


async def test_real_a2a_demo():
    """Test the real A2A demo with detailed tracing."""

    base_url = "http://localhost:8081"

    print("🔥 STARTING REAL A2A DEMO TEST")
    print(f"   Time: {datetime.now()}")
    print(f"   Base URL: {base_url}")
    print("=" * 80)

    # Test 1: Get agents
    try:
        agents_response = requests.get(f"{base_url}/api/agents")
        agents_data = agents_response.json()

        print("📋 AGENTS LOADED:")
        for agent in agents_data.get("agents", []):
            print(f"   - {agent['name']} ({agent['type']})")
            print(
                f"     Capabilities: {[cap['name'] for cap in agent['capabilities']]}"
            )
        print("=" * 80)

    except Exception as e:
        print(f"❌ Failed to get agents: {e}")
        return

    # Test 2: Execute real A2A task
    test_topic = "Analyze the impact of AI on healthcare productivity"
    agent_ids = [agent["id"] for agent in agents_data.get("agents", [])]

    print("🚀 TRIGGERING REAL A2A TASK:")
    print(f"   Topic: {test_topic}")
    print(f"   Selected Agents: {agent_ids}")
    print(f"   Start Time: {time.time()}")
    print("=" * 80)

    try:
        task_response = requests.post(
            f"{base_url}/api/task/real-a2a",
            json={"topic": test_topic, "agents_to_use": agent_ids},
            timeout=120,
        )  # 2 minute timeout

        task_result = task_response.json()

        print("✅ REAL A2A TASK COMPLETED:")
        print(f"   End Time: {time.time()}")
        print(f"   Success: {task_result.get('success', False)}")
        print(f"   Results Count: {len(task_result.get('results', []))}")

        # Show results for each agent
        for result in task_result.get("results", []):
            agent_name = result.get("agent_name")
            agent_result = result.get("result", {})

            print(f"\n📊 AGENT RESULT: {agent_name}")
            print(f"   Success: {agent_result.get('success', False)}")
            print(f"   Model: {agent_result.get('model', 'N/A')}")

            # Show A2A metadata (the real internals)
            a2a_metadata = agent_result.get("a2a_metadata", {})
            if a2a_metadata:
                print("   🔍 REAL A2A METADATA:")
                print(
                    f"      Shared Context Used: {a2a_metadata.get('shared_context_used', 0)}"
                )
                print(
                    f"      Insights Generated: {a2a_metadata.get('insights_generated', 0)}"
                )
                print(
                    f"      Memory Pool Active: {a2a_metadata.get('memory_pool_active', False)}"
                )
                print(
                    f"      Local Memory Size: {a2a_metadata.get('local_memory_size', 0)}"
                )

            # Show token usage (proof of real OpenAI call)
            usage = agent_result.get("usage", {})
            if usage:
                print("   💰 TOKEN USAGE (Real OpenAI):")
                print(f"      Prompt Tokens: {usage.get('prompt_tokens', 0)}")
                print(f"      Completion Tokens: {usage.get('completion_tokens', 0)}")
                print(f"      Total Tokens: {usage.get('total_tokens', 0)}")

            # Show actual response content
            response = agent_result.get("response", {})
            if response:
                content = response.get("content", "")[:200]
                print(f"   📝 RESPONSE PREVIEW: {content}...")

        print("=" * 80)
        print("🎉 REAL A2A DEMO TEST COMPLETE")

    except Exception as e:
        print(f"❌ Failed to execute A2A task: {e}")


if __name__ == "__main__":
    asyncio.run(test_real_a2a_demo())
