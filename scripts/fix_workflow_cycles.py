#!/usr/bin/env python3
"""Fix all workflow.connect(cycle=True) deprecation warnings."""

import os
import re
from pathlib import Path


def extract_multiline_call(content, start_pos):
    """Extract a complete function call that may span multiple lines."""
    depth = 0
    in_string = False
    string_char = None
    pos = start_pos

    while pos < len(content):
        char = content[pos]

        if not in_string:
            if char in "\"'":
                in_string = True
                string_char = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return content[start_pos : pos + 1]
        else:
            if char == string_char and content[pos - 1] != "\\":
                in_string = False
                string_char = None

        pos += 1

    return None


def fix_cycle_connects(content):
    """Fix all cycle connects in content."""
    lines = content.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line starts a workflow.connect with cycle=True
        if "workflow.connect(" in line:
            # Find the complete call
            start = content.find(line)
            call_match = extract_multiline_call(
                content, content.find("workflow.connect(", start)
            )

            if call_match and "cycle=True" in call_match:
                # Parse the call
                # Extract arguments
                args_start = call_match.find("(") + 1
                args_end = call_match.rfind(")")
                args_content = call_match[args_start:args_end]

                # Parse components
                source = None
                target = None
                mapping = None
                max_iterations = "10"
                convergence_check = None
                cycle_id = None

                # Extract source and target (first two args)
                parts = []
                current = ""
                depth = 0
                in_string = False
                string_char = None

                for char in args_content:
                    if not in_string:
                        if char in "\"'":
                            in_string = True
                            string_char = char
                        elif char in "({[":
                            depth += 1
                        elif char in ")}]":
                            depth -= 1
                        elif char == "," and depth == 0:
                            parts.append(current.strip())
                            current = ""
                            continue
                    else:
                        if (
                            char == string_char
                            and len(current) > 0
                            and current[-1] != "\\"
                        ):
                            in_string = False
                    current += char

                if current.strip():
                    parts.append(current.strip())

                # Process parts
                for j, part in enumerate(parts):
                    if j == 0:
                        source = part.strip()
                    elif j == 1:
                        target = part.strip()
                    elif "mapping=" in part:
                        mapping = part.split("mapping=", 1)[1].strip()
                    elif part.strip().startswith("{"):
                        mapping = part.strip()
                    elif "max_iterations=" in part:
                        max_iterations = part.split("max_iterations=", 1)[1].strip()
                    elif "convergence_check=" in part:
                        convergence_check = (
                            part.split("convergence_check=", 1)[1].strip().strip('"')
                        )
                    elif "cycle_id=" in part:
                        cycle_id = part.split("cycle_id=", 1)[1].strip().strip('"')

                # Generate cycle_id if not provided
                if not cycle_id:
                    src = source.strip("\"'") if source else "node"
                    tgt = target.strip("\"'") if target else "node"
                    cycle_id = f"cycle_{src}_to_{tgt}".replace("-", "_").replace(
                        " ", "_"
                    )

                # Build new call
                indent = line[: len(line) - len(line.lstrip())]
                new_call = f'{indent}workflow.create_cycle("{cycle_id}")\\'

                if mapping:
                    new_call += (
                        f"\n{indent}    .connect({source}, {target}, {mapping})\\"
                    )
                else:
                    new_call += f"\n{indent}    .connect({source}, {target})\\"

                new_call += f"\n{indent}    .max_iterations({max_iterations})\\"

                if convergence_check:
                    new_call += f'\n{indent}    .converge_when("{convergence_check}")\\'

                new_call += f"\n{indent}    .build()"

                # Skip lines that were part of the old call
                old_lines = call_match.count("\n")
                result_lines.append(new_call)
                i += old_lines
            else:
                result_lines.append(line)
        else:
            result_lines.append(line)

        i += 1

    return "\n".join(result_lines)


def process_file(filepath):
    """Process a single file."""
    print(f"Processing {filepath.name}...")

    with open(filepath, "r") as f:
        content = f.read()

    if "cycle=True" not in content:
        print("  No deprecated cycles found")
        return False

    fixed_content = fix_cycle_connects(content)

    with open(filepath, "w") as f:
        f.write(fixed_content)

    # Count remaining
    remaining = fixed_content.count("cycle=True")
    if remaining > 0:
        print(f"  ⚠️  {remaining} cycle=True occurrences remain (manual fix needed)")
    else:
        print("  ✅ All deprecated cycles fixed")

    return True


def main():
    """Main entry point."""
    workflows_dir = Path("tests/integration/workflows")

    files = list(workflows_dir.glob("*.py"))
    files.sort()

    print("Fixing workflow deprecation warnings...\n")

    fixed_count = 0
    for filepath in files:
        if process_file(filepath):
            fixed_count += 1

    print(f"\nProcessed {len(files)} files, fixed {fixed_count}")


if __name__ == "__main__":
    main()
