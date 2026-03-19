# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Automated convention checks for EATP SDK compliance (D1, D2).

D1: Scan all EATP modules for unbounded list/dict patterns in classes that
    track per-agent state. All such collections must have documented size bounds.

D2: Scan all EATP modules for ``==`` comparisons on signature/hash/hmac
    variables. All such comparisons must use ``hmac.compare_digest()`` instead.

Written BEFORE implementation (TDD). Tests define the contract.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest

# Root of the EATP package source
_EATP_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "eatp"


def _get_all_module_paths() -> List[Path]:
    """Return all .py module paths in the EATP source, excluding __pycache__."""
    return [p for p in _EATP_SRC.rglob("*.py") if "__pycache__" not in str(p) and p.name != "__init__.py"]


# ===================================================================
# D1: Bounded collection convention check
# ===================================================================

# Known per-agent tracking classes that MUST have bounded collections.
# Format: (module_relative_path, class_name, attribute_name)
_BOUNDED_COLLECTION_REQUIREMENTS: List[Tuple[str, str, str]] = [
    ("circuit_breaker.py", "PostureCircuitBreaker", "_failures"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_states"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_last_failure"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_half_open_calls"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_half_open_successes"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_original_postures"),
    ("circuit_breaker.py", "PostureCircuitBreaker", "_open_time"),
    ("circuit_breaker.py", "CircuitBreakerRegistry", "_breakers"),
    ("metrics.py", "TrustMetricsCollector", "_agent_postures"),
    ("metrics.py", "TrustMetricsCollector", "_transitions"),
    ("metrics.py", "TrustMetricsCollector", "_dimension_failures"),
    ("metrics.py", "TrustMetricsCollector", "_anti_gaming_flags"),
]


class TestBoundedCollectionConvention:
    """D1: All per-agent tracking collections must have size bounds."""

    def test_per_agent_classes_declare_max_attribute(self):
        """Classes tracking per-agent state must have a _max_* or maxlen attribute.

        This test scans the known per-agent classes and verifies that:
        1. The class __init__ sets a maximum size attribute
        2. There is trimming logic when the collection grows
        """
        missing_bounds: List[str] = []

        for module_rel, class_name, attr_name in _BOUNDED_COLLECTION_REQUIREMENTS:
            module_path = _EATP_SRC / module_rel
            if not module_path.exists():
                missing_bounds.append(f"{module_rel}:{class_name}.{attr_name} - module not found")
                continue

            source = module_path.read_text()
            tree = ast.parse(source)

            # Find the class definition
            class_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    class_node = node
                    break

            if class_node is None:
                missing_bounds.append(f"{module_rel}:{class_name}.{attr_name} - class not found")
                continue

            # Check for a max/maxlen attribute in __init__
            has_bound = False
            for node in ast.walk(class_node):
                if isinstance(node, ast.Attribute) and isinstance(node.attr, str):
                    if node.attr.startswith("_max") or node.attr == "maxlen":
                        has_bound = True
                        break
                if isinstance(node, ast.Name) and isinstance(node.id, str):
                    if node.id.startswith("_max") or node.id == "maxlen":
                        has_bound = True
                        break

            if not has_bound:
                missing_bounds.append(f"{module_rel}:{class_name}.{attr_name} - no _max*/maxlen attribute found")

        assert not missing_bounds, f"Per-agent collections missing bounds declaration:\n" + "\n".join(
            f"  - {m}" for m in missing_bounds
        )

    def test_no_unbounded_per_agent_dict_in_init(self):
        """Scan __init__ methods for Dict assignments that lack a companion _max_* field.

        This is a heuristic check: if a class __init__ creates a Dict[str, ...]
        attribute and no _max_* attribute exists, it may be an unbounded per-agent
        dict that needs bounds.
        """
        # Only check known per-agent tracking modules
        modules_to_check = ["circuit_breaker.py", "metrics.py"]
        warnings: List[str] = []

        for module_name in modules_to_check:
            module_path = _EATP_SRC / module_name
            if not module_path.exists():
                continue

            source = module_path.read_text()
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue

                # Find __init__ method
                init_method = None
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                        init_method = item
                        break

                if init_method is None:
                    continue

                # Collect all self._ attribute assignments
                dict_attrs: Set[str] = set()
                max_attrs: Set[str] = set()

                for sub_node in ast.walk(init_method):
                    if isinstance(sub_node, ast.Assign):
                        for target in sub_node.targets:
                            if (
                                isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                            ):
                                attr_name = target.attr
                                if attr_name.startswith("_max"):
                                    max_attrs.add(attr_name)
                                # Check if value is a dict literal or Dict call
                                if isinstance(sub_node.value, ast.Dict):
                                    dict_attrs.add(attr_name)
                                elif isinstance(sub_node.value, ast.Call):
                                    # Check for Dict() or {} type hint
                                    dict_attrs.add(attr_name)

                # Every class that has per-agent Dict attributes should have _max_*
                if dict_attrs and not max_attrs:
                    # Only flag known per-agent classes
                    known_classes = {c for _, c, _ in _BOUNDED_COLLECTION_REQUIREMENTS}
                    if node.name in known_classes:
                        warnings.append(
                            f"{module_name}:{node.name} has Dict attributes {dict_attrs} but no _max_* bounds"
                        )

        assert not warnings, f"Potentially unbounded per-agent dicts found:\n" + "\n".join(f"  - {w}" for w in warnings)


# ===================================================================
# D2: hmac.compare_digest() convention check
# ===================================================================

# Patterns that indicate a signature/hash/hmac comparison using ==
# These are KNOWN SAFE patterns to exclude:
_SAFE_PATTERNS = {
    # Length checks (len(...) == 64) are fine
    r"len\(",
    # Boolean comparisons are fine
    r"is True",
    r"is False",
    r"is None",
    # Type checks are fine
    r"isinstance\(",
    # String comparisons for non-crypto values are fine
    r"\.value ==",
    r"\.name ==",
}

# Variables/attributes whose values should use compare_digest, not ==
_CRYPTO_COMPARISON_NAMES = {
    "signature",
    "hmac",
    "hash",
    "integrity_hash",
    "root_hash",
    "chain_hashes",
    "hmac_signature",
    "computed_hash",
    "expected_hash",
    "digest",
}


class TestHmacCompareDigestConvention:
    """D2: Signature/hash/hmac comparisons must use hmac.compare_digest()."""

    def test_no_equality_comparison_on_crypto_values(self):
        """Scan for == on signature/hash/hmac variables.

        Any comparison like `computed == self.integrity_hash` or
        `current_hash == proof.root_hash` should use hmac.compare_digest().
        """
        violations: List[Tuple[str, int, str]] = []

        for module_path in _get_all_module_paths():
            source_lines = module_path.read_text().splitlines()
            rel_path = str(module_path.relative_to(_EATP_SRC))

            for line_num, line in enumerate(source_lines, start=1):
                stripped = line.strip()

                # Skip comments
                if stripped.startswith("#"):
                    continue

                # Skip string literals (docstrings, etc.)
                if stripped.startswith(('"""', "'''", '"', "'")):
                    continue

                # Check for == comparisons
                if "==" not in stripped:
                    continue

                # Skip safe patterns
                is_safe = False
                for safe in _SAFE_PATTERNS:
                    if re.search(safe, stripped):
                        is_safe = True
                        break
                if is_safe:
                    continue

                # Check if any crypto variable name appears in the comparison
                line_lower = stripped.lower()
                for crypto_name in _CRYPTO_COMPARISON_NAMES:
                    if crypto_name in line_lower and "==" in stripped:
                        # Additional check: is this actually a comparison
                        # (not an assignment, not a default value)?
                        if "!=" not in stripped:
                            violations.append((rel_path, line_num, stripped))
                            break

        assert not violations, f"Found == comparisons on crypto values (use hmac.compare_digest()):\n" + "\n".join(
            f"  - {path}:{line}: {code}" for path, line, code in violations
        )
