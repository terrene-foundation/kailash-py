"""
Performance benchmark for ToolApprovalManager.

Measures:
1. Prompt generation latency (target: <50ms)
2. Approval request latency with mocked protocol (target: <100ms)

Run: python benchmarks/approval_manager_benchmark.py
"""

import asyncio
import time
from unittest.mock import AsyncMock

from kaizen.core.autonomy.control.types import ControlResponse
from kaizen.core.autonomy.permissions.approval_manager import ToolApprovalManager
from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode


def benchmark_prompt_generation():
    """Benchmark prompt generation for different tool types."""
    print("\n" + "=" * 70)
    print("BENCHMARK 1: Prompt Generation Latency")
    print("=" * 70)

    # Setup
    mock_protocol = AsyncMock()
    manager = ToolApprovalManager(mock_protocol)

    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=10.0)
    context.budget_used = 5.0

    # Test cases
    test_cases = [
        ("Bash", {"command": "ls -la"}),
        ("Write", {"file_path": "/test.txt", "content": "hello"}),
        ("Read", {"file_path": "/data.json"}),
        ("CustomTool", {"param1": "value1", "param2": "value2"}),
    ]

    results = []

    for tool_name, tool_input in test_cases:
        # Warmup
        for _ in range(10):
            manager._generate_approval_prompt(tool_name, tool_input, context)

        # Benchmark
        iterations = 1000
        start = time.perf_counter()

        for _ in range(iterations):
            prompt = manager._generate_approval_prompt(tool_name, tool_input, context)

        end = time.perf_counter()
        avg_latency_ms = ((end - start) / iterations) * 1000

        results.append((tool_name, avg_latency_ms))

        # Verify prompt contains key info
        assert len(prompt) > 0
        assert tool_name in prompt or tool_name.lower() in prompt.lower()

        print(f"  {tool_name:15s}: {avg_latency_ms:8.4f} ms/prompt (1000 iterations)")

    # Summary
    max_latency = max(r[1] for r in results)
    avg_latency = sum(r[1] for r in results) / len(results)

    print(f"\n  Average: {avg_latency:.4f} ms")
    print(f"  Max:     {max_latency:.4f} ms")
    print("  Target:  <50 ms")

    if max_latency < 50:
        print(f"  Result:  ✅ PASS (max {max_latency:.4f} ms < 50 ms)")
    else:
        print(f"  Result:  ❌ FAIL (max {max_latency:.4f} ms >= 50 ms)")

    return max_latency < 50


async def benchmark_approval_request():
    """Benchmark approval request flow with mocked protocol."""
    print("\n" + "=" * 70)
    print("BENCHMARK 2: Approval Request Latency (Mocked Protocol)")
    print("=" * 70)

    # Setup mock protocol
    mock_protocol = AsyncMock()
    mock_response = ControlResponse(
        request_id="test-123", data={"approved": True, "action": "once"}
    )

    # Simulate fast protocol response (10ms)
    async def mock_send_request(*args, **kwargs):
        await asyncio.sleep(0.01)  # 10ms delay
        return mock_response

    mock_protocol.send_request = AsyncMock(side_effect=mock_send_request)

    manager = ToolApprovalManager(mock_protocol)

    context = ExecutionContext(mode=PermissionMode.DEFAULT, budget_limit=20.0)
    context.budget_used = 8.0

    # Warmup
    for _ in range(5):
        await manager.request_approval("Bash", {"command": "ls"}, context)

    # Benchmark
    iterations = 100
    start = time.perf_counter()

    for _ in range(iterations):
        approved = await manager.request_approval("Bash", {"command": "ls"}, context)
        assert approved is True

    end = time.perf_counter()
    avg_latency_ms = ((end - start) / iterations) * 1000

    print(f"  Iterations:       {iterations}")
    print(f"  Average latency:  {avg_latency_ms:.4f} ms/request")
    print("  Target:           <100 ms")

    if avg_latency_ms < 100:
        print(f"  Result:           ✅ PASS ({avg_latency_ms:.4f} ms < 100 ms)")
    else:
        print(f"  Result:           ❌ FAIL ({avg_latency_ms:.4f} ms >= 100 ms)")

    return avg_latency_ms < 100


def main():
    """Run all benchmarks."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 12 + "ToolApprovalManager Performance Benchmark" + " " * 15 + "║")
    print("╚" + "=" * 68 + "╝")

    # Run benchmarks
    result1 = benchmark_prompt_generation()
    result2 = asyncio.run(benchmark_approval_request())

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Prompt Generation:    {'✅ PASS' if result1 else '❌ FAIL'}")
    print(f"  Approval Request:     {'✅ PASS' if result2 else '❌ FAIL'}")
    print(
        f"  Overall:              {'✅ ALL PASS' if (result1 and result2) else '❌ SOME FAIL'}"
    )
    print()

    return 0 if (result1 and result2) else 1


if __name__ == "__main__":
    exit(main())
