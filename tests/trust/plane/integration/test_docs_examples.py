# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests that code examples in tutorial.md are syntactically valid.

Extracts Python code blocks from the tutorial documentation,
compiles them to verify syntax, and checks that import statements
reference modules that actually exist in the trustplane package.
"""

from __future__ import annotations

import ast
import re
import importlib
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
TUTORIAL_PATH = DOCS_DIR / "tutorial.md"
CONCEPTS_PATH = DOCS_DIR / "concepts.md"
DEMO_PATH = DOCS_DIR / "demo-script.md"


def _extract_python_blocks(md_path: Path) -> list[tuple[int, str]]:
    """Extract Python code blocks from a Markdown file.

    Returns a list of (line_number, code_string) tuples.
    The line_number is the line where the code block starts in the
    Markdown file (1-indexed), for error reporting.
    """
    content = md_path.read_text(encoding="utf-8")
    blocks: list[tuple[int, str]] = []

    # Match ```python ... ``` blocks
    pattern = re.compile(
        r"^```python\s*\n(.*?)^```",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(content):
        # Calculate line number of the code block start
        line_num = content[: match.start()].count("\n") + 1
        blocks.append((line_num, match.group(1)))

    return blocks


def _extract_bash_commands(md_path: Path) -> list[tuple[int, str]]:
    """Extract attest CLI commands from bash code blocks.

    Returns a list of (line_number, command_string) tuples.
    Only extracts lines starting with 'attest'.
    """
    content = md_path.read_text(encoding="utf-8")
    commands: list[tuple[int, str]] = []

    pattern = re.compile(
        r"^```bash\s*\n(.*?)^```",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(content):
        line_num = content[: match.start()].count("\n") + 1
        block = match.group(1)
        for i, line in enumerate(block.splitlines()):
            stripped = line.strip()
            # Skip comments, empty lines, and non-attest lines
            if stripped.startswith("attest"):
                commands.append((line_num + i + 1, stripped))

    return commands


class TestTutorialPythonBlocks:
    """Verify Python code blocks in tutorial.md are syntactically valid."""

    @pytest.fixture(autouse=True)
    def skip_if_no_tutorial(self):
        if not TUTORIAL_PATH.exists():
            pytest.skip("tutorial.md not found")

    def test_tutorial_exists(self):
        assert TUTORIAL_PATH.exists(), "tutorial.md should exist"

    def test_python_blocks_compile(self):
        """Every Python code block must be syntactically valid."""
        blocks = _extract_python_blocks(TUTORIAL_PATH)
        assert len(blocks) > 0, "tutorial.md should contain Python code blocks"

        for line_num, code in blocks:
            try:
                compile(code, f"tutorial.md:line-{line_num}", "exec")
            except SyntaxError as e:
                pytest.fail(
                    f"Syntax error in tutorial.md Python block starting at "
                    f"line {line_num}: {e}"
                )

    def test_python_blocks_parse_as_ast(self):
        """Every Python code block must parse into a valid AST."""
        blocks = _extract_python_blocks(TUTORIAL_PATH)
        for line_num, code in blocks:
            try:
                ast.parse(code)
            except SyntaxError as e:
                pytest.fail(
                    f"AST parse error in tutorial.md Python block starting "
                    f"at line {line_num}: {e}"
                )

    def test_import_statements_resolve(self):
        """Import statements in code blocks must reference real modules."""
        blocks = _extract_python_blocks(TUTORIAL_PATH)
        for line_num, code in blocks:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name
                        try:
                            importlib.import_module(module_name)
                        except ImportError:
                            pytest.fail(
                                f"Import '{module_name}' in tutorial.md "
                                f"block at line {line_num} does not resolve"
                            )
                elif isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    # Check the top-level module exists
                    top_module = node.module.split(".")[0]
                    try:
                        importlib.import_module(top_module)
                    except ImportError:
                        pytest.fail(
                            f"Import 'from {node.module}' in tutorial.md "
                            f"block at line {line_num} does not resolve "
                            f"(top-level module '{top_module}' not found)"
                        )
                    # Check the full module path exists
                    try:
                        importlib.import_module(node.module)
                    except ImportError:
                        pytest.fail(
                            f"Import 'from {node.module}' in tutorial.md "
                            f"block at line {line_num} does not resolve"
                        )


class TestConceptsPythonBlocks:
    """Verify Python code blocks in concepts.md are syntactically valid."""

    @pytest.fixture(autouse=True)
    def skip_if_no_concepts(self):
        if not CONCEPTS_PATH.exists():
            pytest.skip("concepts.md not found")

    def test_concepts_exists(self):
        assert CONCEPTS_PATH.exists(), "concepts.md should exist"

    def test_python_blocks_compile(self):
        """Every Python code block in concepts.md must compile."""
        blocks = _extract_python_blocks(CONCEPTS_PATH)
        # concepts.md may have zero Python blocks; that is fine
        for line_num, code in blocks:
            try:
                compile(code, f"concepts.md:line-{line_num}", "exec")
            except SyntaxError as e:
                pytest.fail(
                    f"Syntax error in concepts.md Python block starting at "
                    f"line {line_num}: {e}"
                )


class TestDemoScriptPythonBlocks:
    """Verify Python code blocks in demo-script.md are syntactically valid."""

    @pytest.fixture(autouse=True)
    def skip_if_no_demo(self):
        if not DEMO_PATH.exists():
            pytest.skip("demo-script.md not found")

    def test_demo_exists(self):
        assert DEMO_PATH.exists(), "demo-script.md should exist"

    def test_python_blocks_compile(self):
        """Every Python code block in demo-script.md must compile."""
        blocks = _extract_python_blocks(DEMO_PATH)
        for line_num, code in blocks:
            try:
                compile(code, f"demo-script.md:line-{line_num}", "exec")
            except SyntaxError as e:
                pytest.fail(
                    f"Syntax error in demo-script.md Python block starting "
                    f"at line {line_num}: {e}"
                )


class TestTutorialCLICommands:
    """Verify CLI commands in tutorial.md reference valid attest subcommands."""

    KNOWN_SUBCOMMANDS = {
        "shadow",
        "init",
        "decide",
        "milestone",
        "verify",
        "status",
        "decisions",
        "export",
        "audit",
        "template",
        "enforce",
        "hold",
        "mirror",
        "diagnose",
        "delegate",
        "migrate",
    }

    @pytest.fixture(autouse=True)
    def skip_if_no_tutorial(self):
        if not TUTORIAL_PATH.exists():
            pytest.skip("tutorial.md not found")

    def test_cli_commands_use_valid_subcommands(self):
        """Every 'attest <subcommand>' in tutorial.md must be a real subcommand."""
        commands = _extract_bash_commands(TUTORIAL_PATH)
        assert len(commands) > 0, "tutorial.md should contain attest commands"

        for line_num, cmd in commands:
            # Parse: attest [--dir ...] <subcommand> ...
            parts = cmd.split()
            # Skip 'attest' itself
            idx = 1
            # Skip global options
            while idx < len(parts) and parts[idx].startswith("--"):
                idx += 1
                # Skip option values (e.g., --dir ./path)
                if idx < len(parts) and not parts[idx].startswith("--"):
                    idx += 1
            if idx < len(parts):
                subcommand = parts[idx]
                # Handle line continuations
                if subcommand == "\\":
                    continue
                assert subcommand in self.KNOWN_SUBCOMMANDS, (
                    f"Unknown subcommand 'attest {subcommand}' in tutorial.md "
                    f"at line {line_num}. Known: {sorted(self.KNOWN_SUBCOMMANDS)}"
                )


class TestDocumentationCompleteness:
    """Verify documentation files exist and have minimum content."""

    def test_tutorial_exists(self):
        assert TUTORIAL_PATH.exists(), "docs/tutorial.md must exist"

    def test_concepts_exists(self):
        assert CONCEPTS_PATH.exists(), "docs/concepts.md must exist"

    def test_demo_script_exists(self):
        assert DEMO_PATH.exists(), "docs/demo-script.md must exist"

    def test_tutorial_has_all_sections(self):
        content = TUTORIAL_PATH.read_text(encoding="utf-8")
        required_sections = [
            "Installation",
            "Shadow Mode",
            "Shadow Report",
            "Graduating to Full Governance",
            "Recording a Decision",
            "Recording a Milestone",
            "Verifying the Chain",
            "Exporting a Bundle",
            "What's Next",
        ]
        for section in required_sections:
            assert section in content, (
                f"tutorial.md missing required section: '{section}'"
            )

    def test_concepts_has_all_sections(self):
        content = CONCEPTS_PATH.read_text(encoding="utf-8")
        required_sections = [
            "What Is a Trust Plane",
            "What Is a Constraint Envelope",
            "What Is a Trust Posture",
            "What Is the Mirror Thesis",
            "What Is a Trust Chain",
            "Glossary",
        ]
        for section in required_sections:
            assert section in content, (
                f"concepts.md missing required section: '{section}'"
            )

    def test_demo_has_before_and_after(self):
        content = DEMO_PATH.read_text(encoding="utf-8")
        assert "WITHOUT TrustPlane" in content, (
            "demo-script.md must have a 'WITHOUT TrustPlane' section"
        )
        assert "WITH TrustPlane" in content, (
            "demo-script.md must have a 'WITH TrustPlane' section"
        )

    def test_tutorial_minimum_length(self):
        """Tutorial should be substantial (at least 500 lines)."""
        content = TUTORIAL_PATH.read_text(encoding="utf-8")
        line_count = content.count("\n")
        assert line_count >= 500, (
            f"tutorial.md has {line_count} lines, expected at least 500"
        )

    def test_concepts_minimum_length(self):
        """Concepts doc should be substantial (at least 200 lines)."""
        content = CONCEPTS_PATH.read_text(encoding="utf-8")
        line_count = content.count("\n")
        assert line_count >= 200, (
            f"concepts.md has {line_count} lines, expected at least 200"
        )
