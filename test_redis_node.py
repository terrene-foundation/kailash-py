#!/usr/bin/env python3
"""Test RedisNode registration and basic functionality."""

from kailash.nodes.base import NodeRegistry
from kailash.nodes.data import RedisNode

# Check if RedisNode is registered
print(
    "Available nodes:",
    [name for name in NodeRegistry._registry.keys() if "Redis" in name],
)

# Try to create a RedisNode
try:
    node = RedisNode(operation="get", key="test")
    print("RedisNode created successfully")
except Exception as e:
    print(f"Error creating RedisNode: {e}")

# Try to get it from registry
try:
    node_class = NodeRegistry.get("RedisNode")
    print(f"Got RedisNode class from registry: {node_class}")
except Exception as e:
    print(f"Error getting RedisNode from registry: {e}")
