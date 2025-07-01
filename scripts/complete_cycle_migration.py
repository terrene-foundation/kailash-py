#!/usr/bin/env python3
"""Complete migration of all workflow tests to new CycleBuilder API."""

import re
from pathlib import Path


def extract_connect_call(content, start_pos):
    """Extract a complete workflow.connect call."""
    # Find the matching closing parenthesis
    depth = 0
    pos = start_pos
    while pos < len(content):
        if content[pos] == "(":
            depth += 1
        elif content[pos] == ")":
            depth -= 1
            if depth == 0:
                return content[start_pos : pos + 1], pos + 1
        pos += 1
    return None, start_pos


def parse_connect_args(call_text):
    """Parse arguments from a workflow.connect call."""
    # Remove workflow.connect( and closing )
    args_text = call_text[len("workflow.connect(") : -1]

    # Parse the arguments
    result = {
        "source": None,
        "target": None,
        "mapping": None,
        "max_iterations": "10",
        "convergence_check": None,
        "cycle_id": None,
    }

    # Split by lines and parse
    lines = args_text.split("\n")
    current_arg = []
    arg_index = 0
    in_dict = False
    dict_depth = 0

    for line in lines:
        stripped = line.strip()

        # Track dict depth
        dict_depth += stripped.count("{") - stripped.count("}")
        if dict_depth > 0:
            in_dict = True
        elif dict_depth == 0 and in_dict:
            in_dict = False

        # Accumulate current argument
        current_arg.append(line)

        # Check if this completes an argument
        if not in_dict and stripped.endswith(","):
            arg_text = "\n".join(current_arg)
            arg_text = arg_text.strip().rstrip(",")

            # Determine what this argument is
            if "mapping=" in arg_text:
                result["mapping"] = arg_text.split("mapping=", 1)[1].strip()
            elif "max_iterations=" in arg_text:
                result["max_iterations"] = arg_text.split("max_iterations=", 1)[
                    1
                ].strip()
            elif "convergence_check=" in arg_text:
                result["convergence_check"] = (
                    arg_text.split("convergence_check=", 1)[1].strip().strip('"')
                )
            elif "cycle_id=" in arg_text:
                result["cycle_id"] = (
                    arg_text.split("cycle_id=", 1)[1].strip().strip('"')
                )
            elif "cycle=True" not in arg_text:
                # Positional arguments
                if result["source"] is None:
                    result["source"] = arg_text.strip()
                elif result["target"] is None:
                    result["target"] = arg_text.strip()
                elif result["mapping"] is None and arg_text.strip().startswith("{"):
                    result["mapping"] = arg_text.strip()

            current_arg = []

    # Handle last argument
    if current_arg:
        arg_text = "\n".join(current_arg).strip()
        if "cycle_id=" in arg_text:
            result["cycle_id"] = arg_text.split("cycle_id=", 1)[1].strip().strip('"')

    # Generate cycle_id if not provided
    if not result["cycle_id"]:
        src = result["source"].strip('"') if result["source"] else "node"
        tgt = result["target"].strip('"') if result["target"] else "node"
        result["cycle_id"] = f"cycle_{src}_to_{tgt}".replace("-", "_")

    return result


def convert_to_cycle_builder(args, indent="        "):
    """Convert parsed args to CycleBuilder API call."""
    lines = [f'{indent}workflow.create_cycle("{args["cycle_id"]}")\\']

    if args["mapping"]:
        lines.append(
            f'{indent}    .connect({args["source"]}, {args["target"]}, {args["mapping"]})\\'
        )
    else:
        lines.append(f'{indent}    .connect({args["source"]}, {args["target"]})\\')

    lines.append(f'{indent}    .max_iterations({args["max_iterations"]})\\')

    if args["convergence_check"]:
        lines.append(f'{indent}    .converge_when("{args["convergence_check"]}")\\')

    lines.append(f"{indent}    .build()")

    return "\n".join(lines)


def process_file(filepath):
    """Process a single file to convert all cycle=True calls."""
    print(f"\nProcessing {filepath.name}...")

    with open(filepath, "r") as f:
        content = f.read()

    if "cycle=True" not in content:
        print("  No cycle=True found")
        return False

    # Process all workflow.connect calls with cycle=True
    result = []
    pos = 0
    changes = 0

    while pos < len(content):
        # Find next workflow.connect
        connect_pos = content.find("workflow.connect(", pos)
        if connect_pos == -1:
            result.append(content[pos:])
            break

        # Add content before this call
        result.append(content[pos:connect_pos])

        # Extract the full call
        call_text, next_pos = extract_connect_call(content, connect_pos)

        if call_text and "cycle=True" in call_text:
            # This is a cycle call - convert it
            args = parse_connect_args(call_text)

            # Determine indent from the original call
            line_start = content.rfind("\n", 0, connect_pos) + 1
            indent = content[line_start:connect_pos]

            # Convert to new API
            new_call = convert_to_cycle_builder(args, indent)
            result.append(new_call)
            changes += 1
        else:
            # Not a cycle call, keep as is
            result.append(call_text)

        pos = next_pos

    if changes > 0:
        new_content = "".join(result)
        with open(filepath, "w") as f:
            f.write(new_content)
        print(f"  ✅ Converted {changes} cycle calls")

        # Verify
        remaining = new_content.count("cycle=True")
        if remaining > 0:
            print(f"  ⚠️  Warning: {remaining} cycle=True still remain")
    else:
        print("  No changes made")

    return changes > 0


def main():
    """Process all workflow test files."""
    workflows_dir = Path("tests/integration/workflows")

    files = [
        "test_convergence_safety.py",
        "test_core_cycle_execution.py",
        "test_cycle_core.py",
        "test_cyclic_examples.py",
        "test_cyclic_workflows.py",
    ]

    total_changes = 0
    for filename in files:
        filepath = workflows_dir / filename
        if filepath.exists():
            if process_file(filepath):
                total_changes += 1
        else:
            print(f"❌ File not found: {filename}")

    print(f"\n✅ Updated {total_changes} files")

    # Final check
    print("\nFinal verification:")
    for filename in files:
        filepath = workflows_dir / filename
        if filepath.exists():
            with open(filepath, "r") as f:
                content = f.read()
            count = content.count("cycle=True")
            if count > 0:
                print(f"  ⚠️  {filename}: {count} cycle=True remaining")
            else:
                print(f"  ✅ {filename}: clean")


if __name__ == "__main__":
    main()
