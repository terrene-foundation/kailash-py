#!/usr/bin/env python3
"""
Debug A2A node execution to understand why it's failing.
"""

import asyncio
import os

from dotenv import load_dotenv

from kailash.nodes.ai.a2a import A2AAgentNode, SharedMemoryPoolNode

load_dotenv()


async def debug_a2a():
    print("🔍 DEBUGGING A2A NODE EXECUTION")
    print(f"   OpenAI API Key: {os.getenv('OPENAI_API_KEY')[:10]}...")
    print("=" * 60)

    # Create memory pool
    memory_pool = SharedMemoryPoolNode()

    # Create A2A agent
    a2a_agent = A2AAgentNode()

    try:
        result = a2a_agent.execute(
            agent_id="test_agent",
            agent_role="researcher",
            memory_pool=memory_pool,
            provider="openai",
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "As a researcher, analyze: What is AI?"}
            ],
            temperature=0.7,
            max_tokens=800,
            use_llm_insight_extraction=True,
        )

        print("✅ SUCCESS:")
        print(f"   Result Keys: {list(result.keys())}")
        print(f"   Success: {result.get('success', 'N/A')}")
        print(f"   Error: {result.get('error', 'None')}")
        print(
            f"   Response: {result.get('response', {}).get('content', 'No content')[:100]}..."
        )

    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        print(f"   Type: {type(e)}")


if __name__ == "__main__":
    asyncio.run(debug_a2a())
