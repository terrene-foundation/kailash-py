#!/usr/bin/env python3
"""
Refactor PythonCodeNode string code blocks to use .from_function() pattern.

This script:
1. Finds PythonCodeNode instances with multi-line string code blocks (>3 lines)
2. Extracts the code and converts it to a function
3. Moves imports to function level (to avoid conflicts)
4. Replaces the PythonCodeNode with .from_function() pattern
5. Formats the code using black (if available)
"""

import re
import sys
from pathlib import Path

# Try to import black
try:
    import black

    HAS_BLACK = True
except ImportError:
    HAS_BLACK = False
    print("Warning: black not installed. Code formatting will be skipped.")
    print("Install with: pip install black")


def extract_node_info(
    match_text: str,
) -> tuple[str | None, str | None, list[str]]:
    """Extract node name, code, and other parameters from PythonCodeNode text."""
    # Extract name
    name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', match_text)
    name = name_match.group(1) if name_match else None

    # Extract code (handling triple quotes)
    code_match = re.search(r'code\s*=\s*"""(.*?)"""', match_text, re.DOTALL)
    if not code_match:
        code_match = re.search(r"code\s*=\s*'''(.*?)'''", match_text, re.DOTALL)

    code = code_match.group(1) if code_match else ""

    # Extract other parameters more carefully
    other_params = []

    # Remove the code section to avoid parsing it
    text_without_code = match_text
    if code_match:
        text_without_code = (
            match_text[: code_match.start()] + match_text[code_match.end() :]
        )

    # Find parameters after removing code
    param_pattern = r'(\w+)\s*=\s*(["\'][^"\']*["\']|[^,\)]+)'
    for param_match in re.finditer(param_pattern, text_without_code):
        param_name = param_match.group(1)
        param_value = param_match.group(2).strip()
        if param_name not in ["name", "code"] and param_name != "PythonCodeNode":
            other_params.append(f"{param_name}={param_value}")

    return name, code, other_params


def generate_function_name(node_name: str | None, index: int) -> str:
    """Generate a function name based on node name."""
    if node_name:
        # Convert node_name to function name
        base_name = node_name.replace("_node", "").replace("Node", "")

        # Apply conversions based on patterns
        conversions = {
            "_processor": ("process_", "_processor"),
            "_validator": ("validate_", "_validator"),
            "_generator": ("generate_", "_generator"),
            "_checker": ("check_", "_checker"),
            "_cleaner": ("clean_", "_cleaner"),
            "_loader": ("load_", "_loader"),
            "_trainer": ("train_", "_trainer"),
            "_evaluator": ("evaluate_", "_evaluator"),
            "_aggregator": ("aggregate_", "_aggregator"),
            "_transformer": ("transform_", "_transformer"),
        }

        for suffix, (prefix, to_remove) in conversions.items():
            if base_name.endswith(suffix):
                return prefix + base_name.replace(to_remove, "").replace("_", "")

        # Default: just use the base name
        return base_name.replace("-", "_").replace(" ", "_")
    else:
        return f"process_data_{index}"


def create_function_from_code(func_name: str, code: str) -> str:
    """Create a function definition from code string."""
    lines = code.strip().split("\n")

    # Analyze code for parameters and return values
    has_input_data = "input_data" in code
    has_data = re.search(r"\bdata\b(?!\s*=)", code) is not None
    has_result = "result =" in code
    has_output = "output =" in code

    # Collect imports to move inside function
    imports = []
    body_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(line)
        else:
            body_lines.append(line)

    # Build function
    func_parts = [f"def {func_name}("]

    # Add parameters
    params = []
    if has_input_data:
        params.append("input_data: dict")
    elif has_data:
        params.append("data=None")

    # Check for other common parameters in the code
    param_patterns = [
        (r"\b(iteration)\b(?!\s*=)", "iteration=None"),
        (r"\b(quality_score)\b(?!\s*=)", "quality_score=None"),
        (r"\b(model)\b(?!\s*=)", "model=None"),
        (r"\b(scaler)\b(?!\s*=)", "scaler=None"),
        (r"\b(epoch)\b(?!\s*=)", "epoch=None"),
        (r"\b(attempt)\b(?!\s*=)", "attempt=None"),
    ]

    for pattern, param in param_patterns:
        if re.search(pattern, code):
            params.append(param)

    params.append("**kwargs")
    func_parts[0] += ", ".join(params) + "):"

    # Add docstring
    func_parts.append('    """Auto-converted from PythonCodeNode string code."""')

    # Add imports inside function
    if imports:
        for imp in imports:
            func_parts.append(f"    {imp.strip()}")
        func_parts.append("    ")

    # Add body with proper indentation
    if body_lines:
        # Find minimum indentation
        non_empty_lines = [line for line in body_lines if line.strip()]
        if non_empty_lines:
            min_indent = min(len(line) - len(line.lstrip()) for line in non_empty_lines)
        else:
            min_indent = 0

        for line in body_lines:
            if line.strip():
                # Remove original indent and add function indent
                dedented = line[min_indent:] if len(line) > min_indent else line
                func_parts.append(f"    {dedented}")
            else:
                func_parts.append("")

    # Add return statement
    func_parts.append("    ")
    if has_result:
        func_parts.append("    return result")
    elif has_output:
        func_parts.append("    return output")
    else:
        # Try to find what should be returned
        for line in reversed(body_lines):
            if "=" in line and not line.strip().startswith("#"):
                var_name = line.split("=")[0].strip()
                if var_name and not var_name.startswith("_"):
                    func_parts.append(f"    return {var_name}")
                    break
        else:
            func_parts.append("    return {}")

    return "\n".join(func_parts)


def refactor_file(file_path: Path) -> bool:
    """Refactor a single Python file."""
    print(f"\nProcessing {file_path}...")

    try:
        # Read the file
        with open(file_path) as f:
            content = f.read()

        # Pattern to match PythonCodeNode with triple-quoted strings
        pattern = r'PythonCodeNode\s*\([^)]*?code\s*=\s*""".*?"""[^)]*?\)'

        matches = list(re.finditer(pattern, content, re.DOTALL))

        if not matches:
            print("  No multi-line PythonCodeNode strings found.")
            return False

        # Process matches and check which ones have >3 lines
        replacements = []
        functions_to_add = []

        for i, match in enumerate(matches):
            match_text = match.group()
            name, code, other_params = extract_node_info(match_text)

            if code and len(code.strip().split("\n")) > 3:
                # Generate function name
                func_name = generate_function_name(name, i)

                # Create function
                func_def = create_function_from_code(func_name, code)
                functions_to_add.append(func_def)

                # Create replacement
                replacement = f'PythonCodeNode.from_function(\n        func={func_name},\n        name="{name}"'
                if other_params:
                    for param in other_params:
                        replacement += f",\n        {param}"
                replacement += "\n    )"

                replacements.append((match.start(), match.end(), replacement))
                newline_count = len(code.strip().split("\n"))
                print(f"  Found: {name} with {newline_count} lines of code")

        if not replacements:
            print("  No multi-line (>3) PythonCodeNode strings found.")
            return False

        # Apply replacements (in reverse order to maintain positions)
        new_content = content
        for start, end, replacement in reversed(replacements):
            new_content = new_content[:start] + replacement + new_content[end:]

        # Find where to insert functions
        lines = new_content.split("\n")
        insert_line = None

        # Look for the first function definition or class definition
        for i, line in enumerate(lines):
            if re.match(r"^(def |class )", line) or (
                "def create_" in line or "def test_" in line
            ):
                insert_line = i
                break

        if insert_line is None:
            # Insert after imports
            for i, line in enumerate(lines):
                if (
                    line.strip()
                    and not line.startswith("import")
                    and not line.startswith("from")
                    and not line.startswith("#")
                ):
                    insert_line = i
                    break

        # Insert functions
        if insert_line is not None:
            # Add functions before the insert line
            functions_text = "\n\n".join(functions_to_add)
            lines.insert(insert_line, "")
            lines.insert(insert_line, functions_text)
            lines.insert(insert_line, "")

        new_content = "\n".join(lines)

        # Format with black if available
        if HAS_BLACK:
            try:
                new_content = black.format_str(new_content, mode=black.FileMode())
            except Exception as e:
                print(f"  Warning: black formatting failed: {e}")

        # Write back
        with open(file_path, "w") as f:
            f.write(new_content)

        print(f"  ✓ Refactored {len(replacements)} PythonCodeNode instances")
        return True

    except Exception as e:
        print(f"  ✗ Error processing {file_path}: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python refactor-pythoncode-strings.py <directory_or_file>")
        print("\nThis script converts PythonCodeNode string code blocks to functions.")
        print("It will only convert multi-line code blocks (more than 3 lines).")
        print("\nExample:")
        print("  python refactor-pythoncode-strings.py examples/feature-tests/")
        print("  python refactor-pythoncode-strings.py examples/my_workflow.py")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_file():
        # Process single file
        success = refactor_file(target)
        sys.exit(0 if success else 1)
    elif target.is_dir():
        # Process directory
        files = list(target.rglob("*.py"))
        print(f"Found {len(files)} Python files to process")

        success_count = 0
        modified_files = []

        for file in files:
            if refactor_file(file):
                success_count += 1
                modified_files.append(file)

        print(f"\n{'=' * 60}")
        print("Refactoring complete!")
        print(f"Files processed: {len(files)}")
        print(f"Files modified: {success_count}")

        if modified_files:
            print("\nModified files:")
            for f in modified_files[:10]:
                print(f"  - {f}")
            if len(modified_files) > 10:
                print(f"  ... and {len(modified_files) - 10} more")

        sys.exit(0)
    else:
        print(f"Error: {target} is not a file or directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
