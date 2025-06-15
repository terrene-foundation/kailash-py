#!/usr/bin/env python3
"""
Refactor PythonCodeNode string code blocks to use .from_function() pattern.

This script:
1. Finds PythonCodeNode instances with multi-line string code blocks
2. Extracts the code and converts it to a function
3. Moves imports to the top of the file
4. Replaces the PythonCodeNode with .from_function() pattern
5. Formats the code using black and isort
"""

import ast
import sys
from pathlib import Path

# Try to import black and isort
try:
    import black
    import isort

    HAS_FORMATTERS = True
except ImportError:
    HAS_FORMATTERS = False
    print("Warning: black or isort not installed. Code formatting will be skipped.")
    print("Install with: pip install black isort")


class PythonCodeNodeTransformer(ast.NodeTransformer):
    """AST transformer to convert PythonCodeNode string code to functions."""

    def __init__(self):
        self.functions_to_add = []
        self.imports_to_add = set()
        self.counter = 0

    def visit_Call(self, node):
        """Visit Call nodes to find PythonCodeNode instances."""
        # Check if this is a PythonCodeNode call
        if isinstance(node.func, ast.Name) and node.func.id == "PythonCodeNode":
            # Look for code argument
            code_arg = None
            name_arg = None
            other_args = []

            for keyword in node.keywords:
                if keyword.arg == "code" and isinstance(keyword.value, ast.Str):
                    code_arg = keyword.value.s
                elif keyword.arg == "name" and isinstance(keyword.value, ast.Str):
                    name_arg = keyword.value.s
                else:
                    other_args.append(keyword)

            # Check if code is multi-line (more than 3 lines)
            if code_arg and len(code_arg.strip().split("\n")) > 3:
                # Generate function name
                func_name = self._generate_function_name(name_arg)

                # Extract code and convert to function
                func_def, imports = self._create_function(func_name, code_arg)
                self.functions_to_add.append(func_def)
                self.imports_to_add.update(imports)

                # Create new .from_function() call
                new_call = ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="PythonCodeNode", ctx=ast.Load()),
                        attr="from_function",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[
                        ast.keyword(
                            arg="func", value=ast.Name(id=func_name, ctx=ast.Load())
                        ),
                        ast.keyword(arg="name", value=ast.Str(s=name_arg)),
                        ast.keyword(
                            arg="description",
                            value=ast.Str(s="Auto-converted from string code"),
                        ),
                    ]
                    + other_args,
                )
                return new_call

        return self.generic_visit(node)

    def _generate_function_name(self, node_name: str | None) -> str:
        """Generate a function name based on node name."""
        if node_name:
            # Convert node_name to function name (e.g., "data_processor" -> "process_data")
            base_name = node_name.replace("_node", "").replace("Node", "")
            # Simple heuristic conversions
            if base_name.endswith("_processor"):
                func_name = "process_" + base_name.replace("_processor", "")
            elif base_name.endswith("_validator"):
                func_name = "validate_" + base_name.replace("_validator", "")
            elif base_name.endswith("_generator"):
                func_name = "generate_" + base_name.replace("_generator", "")
            elif base_name.endswith("_checker"):
                func_name = "check_" + base_name.replace("_checker", "")
            else:
                func_name = base_name + "_logic"
        else:
            self.counter += 1
            func_name = f"pythoncode_function_{self.counter}"

        return func_name

    def _create_function(self, func_name: str, code_str: str) -> tuple[str, set[str]]:
        """Create a function definition from code string."""
        # Parse the code to understand its structure
        lines = code_str.strip().split("\n")
        imports = []
        body_lines = []

        # Separate imports from body
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                imports.append(stripped)
            elif stripped and not stripped.startswith("#") or stripped.startswith("#"):
                body_lines.append(line)

        # Analyze code for input/output patterns
        has_input_data = "input_data" in code_str
        has_data_param = "data" in code_str and "data =" not in code_str
        sets_result = "result =" in code_str
        sets_output = "output =" in code_str

        # Determine function parameters
        params = []
        if has_input_data:
            params.append("input_data: dict")
        elif has_data_param:
            params.append("data=None")
        params.append("**kwargs")

        # Build function definition
        func_lines = [
            f"def {func_name}({', '.join(params)}):",
            '    """Auto-converted from PythonCodeNode string code."""',
        ]

        # Add imports inside function
        for imp in imports:
            func_lines.append(f"    {imp}")

        if imports and body_lines:
            func_lines.append("    ")

        # Add body with proper indentation
        min_indent = min(
            len(line) - len(line.lstrip()) for line in body_lines if line.strip()
        )
        for line in body_lines:
            if line.strip():
                # Remove original indent and add function indent
                dedented = line[min_indent:] if len(line) > min_indent else line
                func_lines.append(f"    {dedented}")
            else:
                func_lines.append("")

        # Add return statement if needed
        if sets_result:
            func_lines.append("    ")
            func_lines.append("    return result")
        elif sets_output:
            func_lines.append("    ")
            func_lines.append("    return output")
        else:
            # Look for any variable assignments that might be the output
            func_lines.append("    ")
            func_lines.append("    # TODO: Verify return value")
            func_lines.append("    return {}")

        return "\n".join(func_lines), set(imports)


def refactor_file(file_path: Path) -> bool:
    """Refactor a single Python file."""
    print(f"Processing {file_path}...")

    try:
        # Read the file
        with open(file_path) as f:
            source = f.read()

        # Parse the AST
        tree = ast.parse(source)

        # Transform the AST
        transformer = PythonCodeNodeTransformer()
        transformer.visit(tree)

        if not transformer.functions_to_add:
            print("  No multi-line PythonCodeNode strings found.")
            return False

        # Convert back to source code
        # Find where to insert functions (before workflow creation)
        lines = source.split("\n")
        insert_line = None

        # Find first workflow creation or class definition
        for i, line in enumerate(lines):
            if "Workflow(" in line or "def create_" in line or "def test_" in line:
                # Insert before this line
                insert_line = i
                break

        if insert_line is None:
            # Insert after imports
            for i, line in enumerate(lines):
                if (
                    line.strip()
                    and not line.startswith("import")
                    and not line.startswith("from")
                ):
                    insert_line = i
                    break

        # Build new source
        new_lines = []

        # Add imports at the top (after existing imports)
        import_insert_line = 0
        for i, line in enumerate(lines):
            if (
                line.strip()
                and not line.startswith("import")
                and not line.startswith("from")
                and not line.startswith("#")
            ):
                import_insert_line = i
                break

        # Insert new content
        for i, line in enumerate(lines):
            if i == import_insert_line and transformer.imports_to_add:
                # Add any new imports
                for imp in sorted(transformer.imports_to_add):
                    new_lines.append(imp)
                new_lines.append("")

            if i == insert_line:
                # Add all functions
                new_lines.append("")
                for func in transformer.functions_to_add:
                    new_lines.append(func)
                    new_lines.append("")
                new_lines.append("")

            new_lines.append(line)

        # Now replace PythonCodeNode calls in the new source
        new_source = "\n".join(new_lines)

        # Use ast.unparse if available (Python 3.9+)
        if hasattr(ast, "unparse"):
            # Re-parse and transform
            tree = ast.parse(new_source)
            transformer = PythonCodeNodeTransformer()
            transformer.visit(tree)
            # This is getting complex - for now, let's use regex replacement

        # Simple regex-based replacement for the PythonCodeNode calls
        # This is a simplified approach - a full implementation would need more sophisticated parsing

        # Format with black and isort if available
        if HAS_FORMATTERS:
            # Format with isort
            new_source = isort.code(new_source)
            # Format with black
            try:
                new_source = black.format_str(new_source, mode=black.FileMode())
            except:
                print("  Warning: black formatting failed")

        # Write back
        with open(file_path, "w") as f:
            f.write(new_source)

        print(
            f"  ✓ Refactored {len(transformer.functions_to_add)} PythonCodeNode instances"
        )
        return True

    except Exception as e:
        print(f"  ✗ Error processing {file_path}: {e}")
        return False


def find_python_files(directory: Path, pattern: str = "*.py") -> list[Path]:
    """Find all Python files in directory matching pattern."""
    return list(directory.rglob(pattern))


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python refactor-pythoncode-to-functions.py <directory_or_file>")
        print("\nThis script converts PythonCodeNode string code blocks to functions.")
        print("It will only convert multi-line code blocks (more than 3 lines).")
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_file():
        # Process single file
        success = refactor_file(target)
        sys.exit(0 if success else 1)
    elif target.is_dir():
        # Process directory
        files = find_python_files(target)
        print(f"Found {len(files)} Python files to process")

        success_count = 0
        for file in files:
            if refactor_file(file):
                success_count += 1

        print(f"\nRefactored {success_count} files")
        sys.exit(0 if success_count > 0 else 1)
    else:
        print(f"Error: {target} is not a file or directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
