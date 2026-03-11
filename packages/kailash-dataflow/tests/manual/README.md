# Manual Tests Directory

This directory contains standalone tests that can be run without pytest. These are useful for debugging, demonstrating bugs, and validating fixes in isolation.

## Available Tests

### test_listnode_filter_standalone.py

**Purpose**: Demonstrates the ListNode filter operator bug

**What it does**:
- Creates a SQLite database with test data using DIRECT SQL
- Tests all filter operators ($ne, $nin, $in, $eq) using DataFlow ListNode
- Compares DataFlow results to ground truth SQL queries
- Clearly shows where DataFlow deviates from expected SQL behavior

**How to run**:
```bash
cd /path/to/kailash_dataflow/packages/kailash-dataflow
python tests/manual/test_listnode_filter_standalone.py
```

**Expected output (with bug)**:
```
STANDALONE TEST: ListNode Filter Bug
======================================================================
Testing all filter operators against ground truth SQL queries
No pytest, no fixtures - just pure Python, SQLite, and DataFlow

Test Database: /tmp/tmpXXXX/test.db

Setting up test data with DIRECT SQL...
✓ Created 5 test records with direct SQL

... (tests run) ...

TEST SUMMARY
======================================================================
❌ FAIL: Empty Filter
❌ FAIL: Implicit Equality
❌ FAIL: $eq Operator
❌ FAIL: $in Operator
❌ FAIL: $ne Operator
❌ FAIL: $nin Operator
❌ FAIL: Multiple Conditions

Total: 0/7 tests passed
```

**What this proves**:
- Ground truth SQL returns correct counts (2, 3, 1, 4, etc.)
- DataFlow ListNode returns 0 records for ALL filter operations
- The bug affects all filter types, not just $ne and $nin

**Exit codes**:
- `0`: All tests passed (bug is fixed)
- `1`: One or more tests failed (bug still exists)

## Why Standalone Tests?

Standalone tests are valuable for:

1. **Bug Reproduction**: Minimal, isolated reproduction of issues
2. **No Dependencies**: Can be run without pytest, fixtures, or complex setup
3. **Easy Debugging**: Simple to step through with debuggers
4. **Documentation**: Serves as executable documentation of the bug
5. **Validation**: Can be used to verify fixes independently

## Creating New Standalone Tests

When creating a new standalone test:

1. **Keep it simple**: Only stdlib + dataflow imports
2. **Direct setup**: Use direct SQL or minimal DataFlow API
3. **Clear output**: Print what's being tested and what failed
4. **Exit codes**: Use sys.exit(0) for pass, sys.exit(1) for fail
5. **Self-contained**: Should work on any machine with Python + dataflow

Example template:
```python
#!/usr/bin/env python3
"""
Standalone test for <feature/bug name>.

Run as: python test_<name>_standalone.py

Demonstrates <what it proves>.
"""

import sys
from pathlib import Path

# Add dataflow to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dataflow import DataFlow

def test_feature():
    """Test description."""
    # Setup
    db = DataFlow(":memory:")

    # Test
    result = do_something()

    # Validate
    if result == expected:
        print("✅ PASS")
        return True
    else:
        print(f"❌ FAIL: Expected {expected}, got {result}")
        return False

def main():
    """Run all tests."""
    print("STANDALONE TEST: <Name>")

    results = []
    results.append(test_feature())

    passed = sum(results)
    total = len(results)

    print(f"\nTotal: {passed}/{total} tests passed")

    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
```

## Integration with Main Test Suite

While standalone tests are useful for debugging, they should NOT replace proper integration/e2e tests:

- Standalone tests: Quick validation, bug demonstration
- Integration tests (tests/integration/): Real infrastructure, comprehensive scenarios
- E2E tests (tests/e2e/): Complete workflows, production scenarios

Always ensure both standalone AND proper tests exist for critical functionality.
