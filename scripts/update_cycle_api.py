#!/usr/bin/env python3
"""Update all workflow tests to use new CycleBuilder API."""

import re
from pathlib import Path

# Mapping of files and their cycle=True occurrences
UPDATES = {
    "test_convergence_safety.py": [
        (
            'workflow.connect(\n            "optimizer",\n            "optimizer",\n            mapping={\n                "result.value": "value",\n                "result.gradient": "gradient",\n            },\n            cycle=True,\n            max_iterations=10,\n            convergence_check="abs(gradient) < 0.01",\n            cycle_id="optimization_loop",\n        )',
            'workflow.create_cycle("optimization_loop")\\\n            .connect("optimizer", "optimizer", {\n                "result.value": "value",\n                "result.gradient": "gradient",\n            })\\\n            .max_iterations(10)\\\n            .converge_when("abs(gradient) < 0.01")\\\n            .build()',
        ),
    ],
    "test_core_cycle_execution.py": [
        # Add patterns for this file
    ],
    "test_cycle_core.py": [
        # Add patterns for this file
    ],
    "test_cyclic_examples.py": [
        # Add patterns for this file
    ],
    "test_cyclic_workflows.py": [
        # Add patterns for this file
    ],
}


def update_all_files():
    """Update all workflow test files."""
    workflows_dir = Path("tests/integration/workflows")

    # Get all Python files that need updating
    files_to_update = [
        "test_convergence_safety.py",
        "test_core_cycle_execution.py",
        "test_cycle_core.py",
        "test_cyclic_examples.py",
        "test_cyclic_workflows.py",
    ]

    for filename in files_to_update:
        filepath = workflows_dir / filename
        if not filepath.exists():
            print(f"❌ File not found: {filename}")
            continue

        print(f"\nProcessing {filename}...")

        with open(filepath, "r") as f:
            content = f.read()

        # Count cycle=True occurrences
        count = content.count("cycle=True")
        if count == 0:
            print("  ✅ Already updated (no cycle=True found)")
            continue

        print(f"  Found {count} cycle=True occurrences")

        # Generic pattern to replace workflow.connect with cycle=True
        # This handles multi-line calls
        pattern = r"workflow\.connect\(((?:[^(){}]|\{[^}]*\}|\([^)]*\))*?)\s*,\s*cycle=True((?:[^(){}]|\{[^}]*\}|\([^)]*\))*?)\)"

        def replace_cycle(match):
            full_match = match.group(0)
            before_cycle = match.group(1)
            after_cycle = match.group(2)

            # Extract components
            lines = (before_cycle + after_cycle).split("\n")

            # Find source, target, mapping
            source = None
            target = None
            mapping = None
            max_iterations = "10"
            convergence_check = None
            cycle_id = None

            # Simple extraction for common patterns
            parts = []
            for line in full_match.split("\n"):
                line = line.strip()
                if line and not line.startswith("workflow.connect("):
                    if line.endswith(","):
                        line = line[:-1]
                    parts.append(line.strip())

            # Parse parts
            i = 0
            while i < len(parts):
                part = parts[i]
                if '"' in part and source is None:
                    source = part.strip()
                elif '"' in part and target is None:
                    target = part.strip()
                elif "mapping=" in part or part.startswith("{"):
                    if "mapping=" in part:
                        mapping = part.split("mapping=", 1)[1].strip()
                    else:
                        # Multi-line mapping
                        mapping_lines = [part]
                        i += 1
                        while i < len(parts) and "}" not in parts[i - 1]:
                            mapping_lines.append(parts[i])
                            i += 1
                        mapping = "\n                ".join(mapping_lines)
                        i -= 1
                elif "max_iterations=" in part:
                    max_iterations = part.split("=", 1)[1].strip()
                elif "convergence_check=" in part:
                    convergence_check = part.split("=", 1)[1].strip().strip('"')
                elif "cycle_id=" in part:
                    cycle_id = part.split("=", 1)[1].strip().strip('"')
                i += 1

            # Generate cycle_id if needed
            if not cycle_id and source and target:
                src = source.strip('"')
                tgt = target.strip('"')
                cycle_id = f"cycle_{src}_to_{tgt}"
            elif not cycle_id:
                cycle_id = "cycle"

            # Build replacement
            indent = "        "  # Default indent
            result = f'{indent}workflow.create_cycle("{cycle_id}")\\'

            if source and target:
                if mapping and "{" in mapping:
                    result += f"\n{indent}    .connect({source}, {target}, {mapping})\\"
                else:
                    result += f"\n{indent}    .connect({source}, {target})\\"

            result += f"\n{indent}    .max_iterations({max_iterations})\\"

            if convergence_check:
                result += f'\n{indent}    .converge_when("{convergence_check}")\\'

            result += f"\n{indent}    .build()"

            return result

        # Apply replacements
        updated_content = re.sub(
            pattern, replace_cycle, content, flags=re.MULTILINE | re.DOTALL
        )

        # Write back
        with open(filepath, "w") as f:
            f.write(updated_content)

        # Verify
        remaining = updated_content.count("cycle=True")
        if remaining == 0:
            print("  ✅ Successfully updated all occurrences")
        else:
            print(f"  ⚠️  {remaining} occurrences remain (may need manual fix)")


def main():
    """Main entry point."""
    print("Updating workflow tests to use new CycleBuilder API...")
    update_all_files()
    print("\nDone!")


if __name__ == "__main__":
    main()
