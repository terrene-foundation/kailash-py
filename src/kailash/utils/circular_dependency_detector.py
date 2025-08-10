"""
Circular Dependency Detector for Kailash SDK

This module provides tools to detect and report circular dependencies in the codebase,
ensuring that lazy loading doesn't mask architectural issues.
"""

import ast
import importlib
import os
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class CircularDependencyDetector:
    """Detects circular dependencies in Python modules."""

    def __init__(self, root_path: str):
        """Initialize the detector with the root path of the codebase."""
        self.root_path = Path(root_path)
        self.import_graph: Dict[str, Set[str]] = defaultdict(set)
        self.visited_files: Set[str] = set()
        self.circular_deps: List[List[str]] = []

    def analyze_file(self, file_path: Path) -> Set[str]:
        """Extract all imports from a Python file."""
        imports = set()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        # Handle relative imports
                        if node.level > 0:
                            # Relative import
                            module_parts = (
                                str(file_path.relative_to(self.root_path))
                                .replace(".py", "")
                                .split("/")
                            )
                            parent_parts = (
                                module_parts[: -node.level]
                                if node.level < len(module_parts)
                                else []
                            )
                            if node.module:
                                full_module = ".".join(
                                    parent_parts + node.module.split(".")
                                )
                            else:
                                full_module = ".".join(parent_parts)
                            imports.add(full_module.replace("/", "."))
                        else:
                            imports.add(node.module)

        except (SyntaxError, FileNotFoundError) as e:
            print(f"Error analyzing {file_path}: {e}")

        return imports

    def build_import_graph(self, start_dir: str = "src/kailash"):
        """Build the complete import dependency graph."""
        start_path = self.root_path / start_dir

        for py_file in start_path.rglob("*.py"):
            # Skip test files and __pycache__
            if "__pycache__" in str(py_file) or "test_" in py_file.name:
                continue

            module_name = self._path_to_module(py_file)
            imports = self.analyze_file(py_file)

            # Filter to only internal imports
            internal_imports = {
                imp
                for imp in imports
                if imp.startswith("kailash") or imp.startswith(".")
            }

            self.import_graph[module_name].update(internal_imports)

    def _path_to_module(self, file_path: Path) -> str:
        """Convert file path to module name."""
        relative = file_path.relative_to(self.root_path / "src")
        module = str(relative).replace(".py", "").replace("/", ".")
        return module

    def detect_cycles(self) -> List[List[str]]:
        """Detect all circular dependencies using DFS."""
        visited = set()
        rec_stack = set()
        path = []
        cycles = []

        def dfs(module: str) -> bool:
            visited.add(module)
            rec_stack.add(module)
            path.append(module)

            for imported in self.import_graph.get(module, set()):
                if imported not in visited:
                    if dfs(imported):
                        return True
                elif imported in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(imported)
                    cycle = path[cycle_start:] + [imported]
                    cycles.append(cycle)

            path.pop()
            rec_stack.remove(module)
            return False

        for module in self.import_graph:
            if module not in visited:
                dfs(module)

        # Remove duplicate cycles
        unique_cycles = []
        seen = set()
        for cycle in cycles:
            # Normalize cycle to start with smallest element
            min_idx = cycle.index(min(cycle))
            normalized = tuple(cycle[min_idx:] + cycle[:min_idx])
            if normalized not in seen:
                seen.add(normalized)
                unique_cycles.append(
                    list(normalized)[:-1]
                )  # Remove duplicate last element

        return unique_cycles

    def check_lazy_loading_safety(self, module_path: str) -> Dict[str, any]:
        """Check if lazy loading is safe for a given module."""
        result = {
            "module": module_path,
            "has_circular_deps": False,
            "circular_chains": [],
            "safe_for_lazy_loading": True,
            "warnings": [],
        }

        # Check if module is involved in any circular dependencies
        for cycle in self.circular_deps:
            if module_path in cycle:
                result["has_circular_deps"] = True
                result["circular_chains"].append(cycle)
                result["safe_for_lazy_loading"] = False
                result["warnings"].append(
                    f"Module is part of circular dependency: {' -> '.join(cycle)}"
                )

        return result

    def generate_report(self) -> str:
        """Generate a comprehensive circular dependency report."""
        self.build_import_graph()
        self.circular_deps = self.detect_cycles()

        report = []
        report.append("=" * 80)
        report.append("CIRCULAR DEPENDENCY ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")

        if not self.circular_deps:
            report.append("✅ No circular dependencies detected!")
        else:
            report.append(
                f"⚠️  Found {len(self.circular_deps)} circular dependency chains:"
            )
            report.append("")

            for i, cycle in enumerate(self.circular_deps, 1):
                report.append(f"{i}. Circular dependency chain:")
                report.append(f"   {' -> '.join(cycle)} -> {cycle[0]}")
                report.append("")

        # Analyze specific high-risk modules
        high_risk_modules = [
            "kailash.nodes.ai.a2a",
            "kailash.nodes.ai.self_organizing",
            "kailash.nodes.ai.intelligent_agent_orchestrator",
            "kailash.nodes.__init__",
        ]

        report.append("-" * 80)
        report.append("HIGH-RISK MODULE ANALYSIS")
        report.append("-" * 80)

        for module in high_risk_modules:
            safety = self.check_lazy_loading_safety(module)
            if safety["has_circular_deps"]:
                report.append(f"\n❌ {module}:")
                for warning in safety["warnings"]:
                    report.append(f"   - {warning}")
            else:
                report.append(f"\n✅ {module}: No circular dependencies")

        report.append("")
        report.append("=" * 80)

        return "\n".join(report)


class CircularImportResolver:
    """Provides solutions for resolving circular dependencies."""

    @staticmethod
    def create_lazy_import_wrapper(
        module_name: str, attribute_name: Optional[str] = None
    ) -> str:
        """Generate code for a lazy import wrapper."""
        if attribute_name:
            return f"""
def get_{attribute_name}():
    \"\"\"Lazy import of {module_name}.{attribute_name}\"\"\"
    from {module_name} import {attribute_name}
    return {attribute_name}
"""
        else:
            return f"""
def get_{module_name.split('.')[-1]}():
    \"\"\"Lazy import of {module_name}\"\"\"
    import {module_name}
    return {module_name}
"""

    @staticmethod
    def create_type_checking_import(module_name: str, types: List[str]) -> str:
        """Generate code for TYPE_CHECKING imports to avoid runtime circular deps."""
        return f"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from {module_name} import {', '.join(types)}
"""

    @staticmethod
    def suggest_refactoring(cycles: List[List[str]]) -> List[str]:
        """Suggest refactoring strategies for circular dependencies."""
        suggestions = []

        for cycle in cycles:
            if len(cycle) == 2:
                suggestions.append(
                    f"""
Circular dependency between {cycle[0]} and {cycle[1]}:
1. Extract shared functionality to a common base module
2. Use dependency injection instead of direct imports
3. Consider if one module should be a submodule of the other
"""
                )
            elif "ai" in str(cycle):
                suggestions.append(
                    f"""
AI module circular dependency in {' -> '.join(cycle)}:
1. Create an ai.base module for shared components
2. Use factory pattern for agent creation
3. Move orchestration logic to a separate coordinator module
"""
                )
            else:
                suggestions.append(
                    f"""
Complex circular dependency in {' -> '.join(cycle)}:
1. Apply Dependency Inversion Principle
2. Create interfaces/protocols for cross-module communication
3. Use event-driven architecture to decouple modules
"""
                )

        return suggestions


def main():
    """Run circular dependency detection on Kailash SDK."""
    # Get the SDK root directory
    sdk_root = Path(__file__).parent.parent.parent.parent

    detector = CircularDependencyDetector(sdk_root)
    report = detector.generate_report()

    print(report)

    if detector.circular_deps:
        print("\n" + "=" * 80)
        print("REFACTORING SUGGESTIONS")
        print("=" * 80)

        resolver = CircularImportResolver()
        suggestions = resolver.suggest_refactoring(detector.circular_deps)

        for i, suggestion in enumerate(suggestions, 1):
            print(f"\n{i}. {suggestion}")

        print("\n" + "=" * 80)
        print("IMMEDIATE ACTION REQUIRED")
        print("=" * 80)
        print(
            """
1. Fix AI module circular dependencies (critical)
2. Clean up duplicate __init__.py files
3. Implement lazy loading WITH circular dependency checks
4. Add this detector to CI/CD pipeline
"""
        )


if __name__ == "__main__":
    main()
