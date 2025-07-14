#!/usr/bin/env python3
"""Fix remaining issues in CacheNode tests."""

import re
from pathlib import Path


def fix_remaining_cache_issues(file_path):
    """Fix remaining issues in CacheNode tests."""
    with open(file_path, "r") as f:
        content = f.read()

    original_content = content

    # Fix 1: Remove invalid assertions on node.id and node.metadata.name
    content = re.sub(
        r'named_node = CacheNode\(\)\s*\n\s*assert named_node\.id == "test_cache"\s*\n\s*assert named_node\.metadata\.name == "Test Cache"',
        r'named_node = CacheNode(id="test_cache", name="Test Cache")\n            assert named_node.id == "test_cache"\n            assert named_node.metadata.name == "Test Cache"',
        content,
        flags=re.MULTILINE,
    )

    # Fix 2: Fix execute calls that are missing backend parameter
    # For simple set/get without backend (should be memory)
    content = re.sub(
        r'node\.execute\(\s*operation="(set|get)"(,\s*key=)',
        r'node.execute(operation="\1", backend="memory"\2',
        content,
    )

    # Fix 3: Fix tests that mix memory and redis backends incorrectly
    # In test_memory_cache_set_and_get, change redis to memory
    content = re.sub(
        r'(# Test get\s*\n\s*result = node\.execute\(operation="get", backend=)"redis"',
        r'\1"memory"',
        content,
    )

    # Fix 4: Fix cache eviction tests - they should use memory backend
    # Fix all redis backends in eviction policy tests to memory
    eviction_tests = [
        "test_lru_eviction_policy",
        "test_lfu_eviction_policy",
        "test_fifo_eviction_policy",
    ]
    for test_name in eviction_tests:
        # Replace backend="redis" with backend="memory" within these test methods
        pattern = rf"(def {test_name}.*?)(def \w+|class \w+|\Z)"

        def replace_redis_to_memory(match):
            test_content = match.group(1)
            test_content = test_content.replace('backend="redis"', 'backend="memory"')
            return test_content + match.group(2)

        content = re.sub(pattern, replace_redis_to_memory, content, flags=re.DOTALL)

    # Fix 5: Fix Redis test to use redis backend
    # In test_redis_set_and_get
    content = re.sub(
        r'(# Test set\s*\n\s*result = node\.execute\(\s*\n\s*operation="set")(, key=)',
        r'\1, backend="redis"\2',
        content,
        flags=re.MULTILINE,
    )

    # Fix 6: Fix thread test get operations
    content = re.sub(
        r'(result = node\.execute\(\s*\n\s*operation="get")(, key=f"thread_)',
        r'\1, backend="memory"\2',
        content,
        flags=re.MULTILINE,
    )

    # Fix 7: Fix tag test set operation
    content = re.sub(
        r'(node\.execute\(\s*\n\s*operation="set")(, key="tag_2")',
        r'\1, backend="memory"\2',
        content,
        flags=re.MULTILINE,
    )

    # Fix 8: Fix time-based invalidation test - add TTL
    content = re.sub(
        r'node\.execute\(\s*\n\s*operation="set", key="timed_key", value="timed_value"\)',
        r'node.execute(\n                operation="set", backend="memory", key="timed_key", value="timed_value", ttl=2)',
        content,
    )

    # Fix 9: Fix dependency-based tests
    content = re.sub(
        r'node\.execute\(operation="(set|get|delete)", backend="redis", key="(parent_key|child_key)"',
        r'node.execute(operation="\1", backend="memory", key="\2"',
        content,
    )

    # Fix 10: Fix tests with mixed backends - ensure consistency
    # If a test uses memory for set, it should use memory for get
    content = re.sub(
        r'node\.execute\(operation="set", backend="memory", key="([^"]+)".*?\n.*?node\.execute\(operation="get", backend="redis", key="\1"',
        lambda m: m.group(0).replace('backend="redis"', 'backend="memory"'),
        content,
        flags=re.DOTALL,
    )

    # Fix 11: Fix invalid_action test
    content = re.sub(
        r'result = node\.execute\(operation="invalid_action", backend="redis", key="test"\)',
        r'result = node.execute(operation="invalid_action", backend="memory", key="test")',
        content,
    )

    # Fix 12: Fix warmup test operation name
    content = re.sub(r'operation="warmup_from_url"', r'operation="warmup"', content)

    if content != original_content:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Fix remaining CacheNode test issues."""
    test_file = Path("tests/unit/test_cache_node_comprehensive.py")

    if test_file.exists():
        print(f"Fixing remaining issues in {test_file}...")
        if fix_remaining_cache_issues(test_file):
            print("  Fixed remaining issues")
        else:
            print("  No changes needed")
    else:
        print(f"File not found: {test_file}")


if __name__ == "__main__":
    main()
