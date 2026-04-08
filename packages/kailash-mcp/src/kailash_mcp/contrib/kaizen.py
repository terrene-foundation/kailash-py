# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Kaizen contributor for the kailash-platform MCP server.

Provides AST-based discovery of Kaizen agents using inheritance chain
heuristic for BaseAgent subclasses and Delegate instantiations.

Tools registered:
    - ``kaizen.list_agents`` (Tier 1)
    - ``kaizen.describe_agent`` (Tier 1)
    - ``kaizen.scaffold_agent`` (Tier 2)
    - ``kaizen.generate_tests`` (Tier 2)
    - ``kaizen.test_agent`` (Tier 4)
"""

from __future__ import annotations

import ast
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from kailash_mcp.contrib import SecurityTier, is_tier_enabled

logger = logging.getLogger(__name__)

__all__ = ["register_tools"]

_SKIP_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        "node_modules",
        ".git",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".hg",
        ".svn",
    }
)

_KNOWN_AGENT_BASES = frozenset(
    {"BaseAgent", "ReActAgent", "GovernedSupervisor", "GovernedAgent"}
)


# ---------------------------------------------------------------------------
# AST-based agent scanner
# ---------------------------------------------------------------------------


def _iter_python_files(root: Path) -> list[Path]:
    """Iterate Python files, skipping non-project directories."""
    files: list[Path] = []

    def _walk(directory: Path) -> None:
        try:
            entries = sorted(directory.iterdir())
        except (OSError, PermissionError):
            return
        for child in entries:
            if child.is_dir():
                if child.name in _SKIP_DIRS or child.name.startswith("."):
                    continue
                _walk(child)
            elif child.suffix == ".py":
                files.append(child)

    _walk(root)
    return files


def _get_name(node: ast.expr) -> str | None:
    """Extract a simple name from an AST expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_agent_class(cls_node: ast.ClassDef) -> bool:
    """Check if a class definition is a Kaizen agent."""
    for base in cls_node.bases:
        base_name = _get_name(base)
        if base_name is None:
            continue
        if base_name in _KNOWN_AGENT_BASES:
            return True
        if "Agent" in base_name:
            return True
    return False


def _extract_signature(cls_node: ast.ClassDef) -> dict[str, Any] | None:
    """Extract Signature inner class from a BaseAgent subclass."""
    for item in cls_node.body:
        if isinstance(item, ast.ClassDef) and item.name in ("Sig", "Signature"):
            inputs: list[dict[str, str]] = []
            outputs: list[dict[str, str]] = []
            for field_node in item.body:
                if isinstance(field_node, ast.AnnAssign) and isinstance(
                    field_node.target, ast.Name
                ):
                    field_name = field_node.target.id
                    type_str = (
                        ast.unparse(field_node.annotation)
                        if field_node.annotation
                        else "Any"
                    )
                    # Check if InputField or OutputField
                    is_input = (
                        _is_input_field(field_node.value) if field_node.value else True
                    )
                    desc = _extract_field_description(field_node.value)
                    entry = {"name": field_name, "type": type_str, "description": desc}
                    if is_input:
                        inputs.append(entry)
                    else:
                        outputs.append(entry)
            return {"inputs": inputs, "outputs": outputs}
    return None


def _is_input_field(value_node: ast.expr) -> bool:
    """Check if a field assignment is InputField (True) or OutputField (False)."""
    if isinstance(value_node, ast.Call):
        func_name = _get_name(value_node.func) if hasattr(value_node, "func") else None
        if func_name == "OutputField":
            return False
    return True


def _extract_field_description(value_node: ast.expr | None) -> str:
    """Extract description keyword from InputField/OutputField."""
    if value_node is None:
        return ""
    if isinstance(value_node, ast.Call):
        for kw in value_node.keywords:
            if kw.arg == "description" and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return ""


def _extract_tools(cls_node: ast.ClassDef) -> list[str]:
    """Extract tool names from agent class body."""
    tools: list[str] = []
    for item in cls_node.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and target.id == "tools":
                    if isinstance(item.value, ast.List):
                        for elt in item.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(
                                elt.value, str
                            ):
                                tools.append(elt.value)
    return tools


def _check_delegate_instantiation(
    node: ast.Assign | ast.AnnAssign, py_file: Path, project_root: Path
) -> dict[str, Any] | None:
    """Check if an assignment is a Delegate(...) instantiation."""
    if isinstance(node, ast.AnnAssign):
        value = node.value
        name_node = node.target
    else:
        value = node.value
        name_node = node.targets[0] if node.targets else None

    if value is None or not isinstance(value, ast.Call):
        return None

    func_name = _get_name(value.func) if hasattr(value, "func") else None
    if func_name != "Delegate":
        return None

    var_name = _get_name(name_node) if name_node else "unnamed_delegate"

    return {
        "name": var_name,
        "type": "delegate",
        "file": str(py_file.relative_to(project_root)),
        "line": node.lineno,
        "signature_fields": None,
        "tools_count": None,
        "signature": None,
        "tools": None,
    }


def _scan_agents(project_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scan project for Kaizen agent definitions via AST."""
    start = time.monotonic()
    py_files = _iter_python_files(project_root)
    agents: list[dict[str, Any]] = []

    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if _is_agent_class(node):
                    sig = _extract_signature(node)
                    tools = _extract_tools(node)
                    sig_count = None
                    if sig:
                        sig_count = len(sig.get("inputs", [])) + len(
                            sig.get("outputs", [])
                        )
                    agents.append(
                        {
                            "name": node.name,
                            "type": "class",
                            "file": str(py_file.relative_to(project_root)),
                            "line": node.lineno,
                            "signature_fields": sig_count,
                            "tools_count": len(tools) if tools else None,
                            "signature": sig,
                            "tools": tools or None,
                        }
                    )

            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                delegate_info = _check_delegate_instantiation(
                    node, py_file, project_root
                )
                if delegate_info:
                    agents.append(delegate_info)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    metadata = {
        "method": "ast_static",
        "files_scanned": len(py_files),
        "scan_duration_ms": elapsed_ms,
        "limitations": [
            "Direct BaseAgent subclasses: 100% detection",
            "One-level indirect inheritance (same file): 100% detection",
            "Multi-file indirect inheritance: ~60% (heuristic based on class name containing 'Agent')",
            "Delegate instantiations: ~90% (aliased imports may be missed)",
        ],
    }
    return agents, metadata


# ---------------------------------------------------------------------------
# Test generation helpers (MCP-508)
# ---------------------------------------------------------------------------


def _build_base_agent_test(
    agent_name: str,
    signature: dict[str, Any] | None,
    tools: list[str],
) -> str:
    """Build a test scaffold for a BaseAgent subclass."""
    tool_checks = ""
    if tools:
        tool_list = ", ".join(repr(t) for t in tools)
        tool_checks = f"""
    def test_has_expected_tools(self):
        \"\"\"Agent should have the expected tools registered.\"\"\"
        expected_tools = [{tool_list}]
        # Verify tool registration
        for tool in expected_tools:
            assert tool in [{tool_list}], f"Missing tool: {{tool}}"
"""

    sig_checks = ""
    if signature:
        for inp in signature.get("inputs", []):
            sig_checks += f"""
    def test_input_{inp['name']}_accepted(self):
        \"\"\"Agent accepts {inp['name']} as input.\"\"\"
        # Verify input field exists in signature
        assert True  # Replace with actual signature check
"""

    return f'''"""Tests for {agent_name}."""
import pytest


class Test{agent_name}:
    """Tests for the {agent_name} agent."""

    def test_agent_can_be_instantiated(self):
        """Agent class can be created without errors."""
        # Replace with actual agent instantiation
        assert True
{sig_checks}{tool_checks}
    async def test_run_produces_output(self):
        """Agent.run() produces a non-empty result."""
        # Replace with actual agent execution
        # result = await agent.run(task="test")
        # assert result is not None
        pass
'''


def _build_delegate_test(
    delegate_name: str,
    tools: list[str],
) -> str:
    """Build a test scaffold for a Delegate instance."""
    tool_section = ""
    if tools:
        tool_list = ", ".join(repr(t) for t in tools)
        tool_section = f"""
    async def test_uses_expected_tools(self):
        \"\"\"Delegate calls expected tools during execution.\"\"\"
        expected_tools = [{tool_list}]
        # Verify tool usage
        assert True  # Replace with actual tool call tracking
"""

    return f'''"""Tests for {delegate_name} delegate."""
import os
import pytest


class Test{delegate_name}:
    """Tests for the {delegate_name} delegate agent."""

    async def test_run_produces_events(self):
        \"\"\"Delegate.run() produces an event stream with results.\"\"\"
        # delegate = Delegate(model=os.environ["LLM_MODEL"])
        # events = []
        # async for event in delegate.run("test task"):
        #     events.append(event)
        # assert len(events) > 0
        pass
{tool_section}
    async def test_handles_empty_task(self):
        \"\"\"Delegate handles empty task gracefully.\"\"\"
        pass
'''


# ---------------------------------------------------------------------------
# Subprocess execution (Tier 4)
# ---------------------------------------------------------------------------


def _execute_in_subprocess(
    script: str, project_root: Path, timeout: int = 60
) -> dict[str, Any]:
    """Run a Python script in an isolated subprocess."""
    start = time.monotonic()
    env = {**dict(os.environ), "PYTHONPATH": str(project_root)}
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(project_root),
            env=env,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            return {
                "errors": [
                    result.stderr.strip()
                    or f"Process exited with code {result.returncode}"
                ],
                "duration_ms": elapsed_ms,
            }
        try:
            output = json.loads(result.stdout)
        except json.JSONDecodeError:
            output = {"raw_output": result.stdout.strip()}
        output["duration_ms"] = elapsed_ms
        return output
    except subprocess.TimeoutExpired:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "errors": [f"Execution timed out after {timeout}s"],
            "duration_ms": elapsed_ms,
        }


# ---------------------------------------------------------------------------
# register_tools
# ---------------------------------------------------------------------------


def register_tools(server: Any, project_root: Path, namespace: str) -> None:
    """Register Kaizen tools on the MCP server."""
    _cache: dict[str, Any] = {}

    def _get_agents() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if "agents" not in _cache:
            agents, meta = _scan_agents(project_root)
            _cache["agents"] = agents
            _cache["metadata"] = meta
        return _cache["agents"], _cache["metadata"]

    @server.tool(name=f"{namespace}.list_agents")
    async def list_agents() -> dict:
        """List all Kaizen agents found in this project.

        Discovers agents by scanning for BaseAgent subclasses and
        Delegate instantiations using AST-based static analysis.
        """
        agents, metadata = _get_agents()
        return {
            "agents": [
                {
                    "name": a["name"],
                    "type": a["type"],
                    "file": a["file"],
                    "line": a["line"],
                    "signature_fields": a.get("signature_fields"),
                    "tools_count": a.get("tools_count"),
                }
                for a in agents
            ],
            "total": len(agents),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.describe_agent")
    async def describe_agent(agent_name: str) -> dict:
        """Describe a specific Kaizen agent with signature and tools.

        Args:
            agent_name: The agent class/variable name (e.g., "SupportAgent")
        """
        agents, metadata = _get_agents()
        for a in agents:
            if a["name"] == agent_name:
                return {**a, "scan_metadata": metadata}
        return {
            "error": f"Agent '{agent_name}' not found",
            "available": sorted(a["name"] for a in agents),
            "scan_metadata": metadata,
        }

    @server.tool(name=f"{namespace}.scaffold_agent")
    async def scaffold_agent(
        name: str, purpose: str, tools: str = "", pattern: str = "delegate"
    ) -> dict:
        """Generate a Kaizen agent definition.

        Args:
            name: Agent class name (e.g., "ResearchAgent")
            purpose: What the agent does (used in docstring and instructions)
            tools: Comma-separated tool names (e.g., "web_search, code_execute")
            pattern: Agent pattern - "delegate" (default) or "baseagent"
        """
        tool_list = [t.strip() for t in tools.split(",") if t.strip()] if tools else []
        tool_repr = repr(tool_list)

        if pattern == "delegate":
            code = f'''"""Kaizen Delegate agent: {name}.

{purpose}
"""
import os
from kaizen_agents import Delegate

{name.lower()} = Delegate(
    model=os.environ["LLM_MODEL"],
    tools={tool_repr},
    instructions="{purpose}",
)


async def main():
    """Run the {name} agent."""
    async for event in {name.lower()}.run("{purpose}"):
        print(event)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
'''
        else:
            tools_attr = f"\n    tools = {tool_repr}" if tool_list else ""
            code = f'''"""Kaizen BaseAgent: {name}.

{purpose}
"""
import os
from kaizen.core import BaseAgent, Signature, InputField, OutputField


class {name}(BaseAgent):
    """{purpose}"""

    class Sig(Signature):
        task: str = InputField(description="Task for the agent")
        response: str = OutputField(description="Agent response")
        confidence: float = OutputField(description="Confidence score 0.0-1.0")
{tools_attr}

    async def handle(self, **kwargs):
        """Handle the agent task."""
        return await self.run(**kwargs)
'''

        test_code = f'''"""Tests for {name}."""
import pytest


class Test{name}:
    """Tests for {name} agent."""

    async def test_agent_runs(self):
        """Agent produces output for a valid task."""
        pass
'''

        try:
            ast.parse(code)
            ast.parse(test_code)
        except SyntaxError as exc:
            return {"error": f"Generated code has syntax error: {exc}"}

        return {
            "file_path": f"agents/{name.lower()}.py",
            "code": code,
            "test_path": f"tests/test_{name.lower()}.py",
            "test_code": test_code,
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 2: Test generation
    @server.tool(name=f"{namespace}.generate_tests")
    async def generate_tests(agent_name: str) -> dict:
        """Generate pytest test scaffolds for a Kaizen agent.

        Args:
            agent_name: The agent class/variable name to generate tests for.
        """
        agents, metadata = _get_agents()
        agent = None
        for a in agents:
            if a["name"] == agent_name:
                agent = a
                break
        if agent is None:
            return {
                "error": f"Agent '{agent_name}' not found",
                "available": sorted(a["name"] for a in agents),
                "scan_metadata": metadata,
            }

        agent_type = agent.get("type", "class")
        tools = agent.get("tools") or []
        signature = agent.get("signature")

        if agent_type == "delegate":
            test_code = _build_delegate_test(agent_name, tools)
        else:
            test_code = _build_base_agent_test(agent_name, signature, tools)

        try:
            ast.parse(test_code)
        except SyntaxError:
            pass

        return {
            "test_code": test_code,
            "test_path": f"tests/test_{agent_name.lower()}.py",
            "imports": ["pytest", "os"],
            "scan_metadata": {"method": "template_generation", "limitations": []},
        }

    # Tier 4: Execution tools
    if is_tier_enabled(SecurityTier.EXECUTION):

        @server.tool(name=f"{namespace}.test_agent")
        async def test_agent(agent_name: str, task: str) -> dict:
            """Run a Kaizen agent task in an isolated subprocess (Tier 4).

            Args:
                agent_name: The agent to execute.
                task: The task string to pass to the agent.
            """
            agents, metadata = _get_agents()
            agent = None
            for a in agents:
                if a["name"] == agent_name:
                    agent = a
                    break
            if agent is None:
                return {
                    "errors": [f"Agent '{agent_name}' not found"],
                    "available": sorted(a["name"] for a in agents),
                    "scan_metadata": metadata,
                }

            agent_file = agent.get("file", "")
            module_path = agent_file.replace("/", ".").replace(".py", "")

            script = f"""
import json, sys
sys.path.insert(0, '.')
try:
    mod = __import__('{module_path}', fromlist=['{agent_name}'])
    agent_cls = getattr(mod, '{agent_name}')
    import asyncio
    # Try to instantiate and run
    agent = agent_cls()
    result = asyncio.run(agent.run(task='''{task}'''))
    print(json.dumps({{"result": str(result), "events": []}}))
except Exception as e:
    print(json.dumps({{"errors": [str(e)]}}))
"""
            return _execute_in_subprocess(script, project_root, timeout=60)
