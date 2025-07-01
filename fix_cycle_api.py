#!/usr/bin/env python3
"""Fix deprecated workflow.connect(cycle=True) usage in tests."""

import re
from pathlib import Path


def fix_workflow_cycles(filepath):
    """Fix deprecated cycle API in a file."""
    with open(filepath, "r") as f:
        content = f.read()

    # Find all workflow.connect calls with cycle=True
    pattern = r"workflow\.connect\(((?:[^(){}]|\{[^}]*\})*)\s*,\s*cycle=True[^)]*\)"

    def fix_connect(match):
        full_match = match.group(0)
        args_text = match.group(1)

        # Extract components from the connect call
        # Parse arguments (handle nested dicts/mappings)
        parts = []
        current = ""
        depth = 0
        in_quotes = False
        quote_char = None

        for char in args_text:
            if char in "\"'":
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
            elif not in_quotes:
                if char in "{[(":
                    depth += 1
                elif char in "}])":
                    depth -= 1
                elif char == "," and depth == 0:
                    parts.append(current.strip())
                    current = ""
                    continue
            current += char
        if current.strip():
            parts.append(current.strip())

        # Extract source, target, mapping
        source = parts[0] if len(parts) > 0 else ""
        target = parts[1] if len(parts) > 1 else ""
        mapping = parts[2] if len(parts) > 2 else "{}"

        # Remove "mapping=" prefix if present
        if mapping.startswith("mapping="):
            mapping = mapping[8:].strip()

        # Extract additional parameters from original match
        max_iterations = "10"  # default
        convergence_check = None
        cycle_id = None

        # Search for parameters after cycle=True
        params_section = full_match.split("cycle=True")[1]

        # Extract max_iterations
        max_iter_match = re.search(r"max_iterations=(\d+)", params_section)
        if max_iter_match:
            max_iterations = max_iter_match.group(1)

        # Extract convergence_check
        convergence_match = re.search(r'convergence_check="([^"]+)"', params_section)
        if convergence_match:
            convergence_check = convergence_match.group(1)

        # Extract cycle_id
        cycle_id_match = re.search(r'cycle_id="([^"]+)"', params_section)
        if cycle_id_match:
            cycle_id = cycle_id_match.group(1)
        else:
            # Generate cycle_id from source and target
            src = source.strip("\"'")
            tgt = target.strip("\"'")
            cycle_id = f"cycle_{src}_to_{tgt}".replace(".", "_")

        # Build new API call
        result = f'workflow.create_cycle("{cycle_id}")'
        result += f".connect({source}, {target}, {mapping})"
        result += f".max_iterations({max_iterations})"

        if convergence_check:
            result += f'.converge_when("{convergence_check}")'

        result += ".build()"

        return result

    # Apply fixes
    fixed_content = re.sub(
        pattern, fix_connect, content, flags=re.MULTILINE | re.DOTALL
    )

    if fixed_content != content:
        with open(filepath, "w") as f:
            f.write(fixed_content)
        return True
    return False


def main():
    """Fix all workflow deprecation warnings."""
    workflows_dir = Path("tests/integration/workflows")

    files = [
        "test_convergence_basic.py",
        "test_convergence_safety.py",
        "test_core_cycle_execution.py",
        "test_cycle_core.py",
        "test_cyclic_examples.py",
        "test_cyclic_workflows.py",
    ]

    print("Fixing workflow deprecation warnings...")
    fixed = 0

    for filename in files:
        filepath = workflows_dir / filename
        if filepath.exists():
            if fix_workflow_cycles(filepath):
                print(f"✅ Fixed: {filename}")
                fixed += 1
            else:
                print(f"  No changes: {filename}")
        else:
            print(f"❌ Not found: {filename}")

    print(f"\nFixed {fixed} files")


if __name__ == "__main__":
    main()
