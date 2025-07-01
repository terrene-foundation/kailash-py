#!/usr/bin/env python3
"""Fix deprecated workflow.connect(cycle=True) usage in tests."""

import os
import re
from pathlib import Path


def fix_cycle_connect(content):
    """Convert deprecated workflow.connect() with cycle=True to new CycleBuilder API."""

    # Pattern to match workflow.connect with cycle=True
    pattern = r'workflow\.connect\(\s*([^,]+),\s*([^,]+),\s*(?:mapping=)?({[^}]+}|"[^"]+"|\w+),?\s*cycle=True,?\s*(?:max_iterations=(\d+),?\s*)?(?:convergence_check="([^"]+)",?\s*)?(?:cycle_id="([^"]+)",?\s*)?(?:initial_params=({[^}]+}),?\s*)?\)'

    def replace_connect(match):
        source = match.group(1).strip()
        target = match.group(2).strip()
        mapping = match.group(3).strip()
        max_iter = match.group(4) or "10"
        convergence = match.group(5) or ""
        cycle_id = match.group(6) or f"cycle_{source}_{target}".replace('"', "")
        initial_params = match.group(7) or None

        # Clean up quotes from cycle_id
        cycle_id = cycle_id.strip('"')

        # Build the new API call
        result = f'workflow.create_cycle("{cycle_id}")'
        result += f".connect({source}, {target}, {mapping})"
        result += f".max_iterations({max_iter})"

        if convergence:
            result += f'.converge_when("{convergence}")'

        if initial_params:
            result += f".with_initial_params({initial_params})"

        result += ".build()"

        return result

    # Replace all occurrences
    return re.sub(pattern, replace_connect, content, flags=re.MULTILINE | re.DOTALL)


def process_file(filepath):
    """Process a single file to fix deprecations."""
    with open(filepath, "r") as f:
        content = f.read()

    original = content
    content = fix_cycle_connect(content)

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        return True
    return False


def main():
    """Fix all workflow deprecation warnings in integration tests."""
    test_dir = Path("tests/integration/workflows")

    files_to_fix = [
        "test_convergence_basic.py",
        "test_convergence_safety.py",
        "test_core_cycle_execution.py",
        "test_cycle_core.py",
        "test_cyclic_examples.py",
        "test_cyclic_workflows.py",
    ]

    fixed_count = 0
    for filename in files_to_fix:
        filepath = test_dir / filename
        if filepath.exists():
            if process_file(filepath):
                print(f"Fixed: {filename}")
                fixed_count += 1
            else:
                print(f"No changes needed: {filename}")
        else:
            print(f"File not found: {filename}")

    print(f"\nTotal files fixed: {fixed_count}")


if __name__ == "__main__":
    main()
