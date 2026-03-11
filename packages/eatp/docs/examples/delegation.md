# Multi-Level Delegation

See `examples/multi_delegation.py` for the full runnable example.

Demonstrates 3-level delegation chains with progressive constraint tightening:

- Level 0: Root agent with full capabilities
- Level 1: Sub-agent with read_only constraint
- Level 2: Sub-sub-agent with read_only + max_100_records constraints
