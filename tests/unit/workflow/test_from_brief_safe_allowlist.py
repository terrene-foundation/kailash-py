# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Inverse-completeness guard for the from_brief default-deny safe allowlist.

Issue #1125 R2 (CRITICAL-2): `from_brief` realizes only `_SAFE_NODE_TYPES`
(default-deny positive allowlist). The security invariant is that NO member
of that set can execute config-supplied code. The denylist model it replaced
was proven unsound because the dangerous set cannot be reliably auto-derived;
this test is the regression backstop that fires if a future edit adds a
code-execution-capable node to the safe allowlist.

The human review required to add a node to `_SAFE_NODE_TYPES` is the primary
defense; these mechanical assertions are the structural net beneath it.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import textwrap

import pytest


def _warm_and_registry():
    for mod in (
        "kailash.nodes.data",
        "kailash.nodes.transform",
        "kailash.nodes.logic",
        "kailash.nodes.code",
    ):
        importlib.import_module(mod)
    from kailash.nodes.base import NodeRegistry

    return NodeRegistry.list_nodes()


def _source_calls_code_exec(cls) -> bool:
    """True if `cls`'s OWN source calls a config-supplied code-load primitive:
    - direct `exec`/`eval`/`compile` builtin call, or an attribute named
      exec/eval;
    - the `CodeExecutor` helper (PythonCodeNode's helper-delegation pattern a
      plain builtin scan would miss);
    - dynamic import `importlib.import_module(...)` / `__import__(...)` (the
      #1125 R4 SharePointGraphReader `device_code_callback` vector — a config
      string imported + getattr'd + called);
    - unsafe deserialization `pickle.loads` / `marshal.loads` /
      `dill.loads` / `cloudpickle.loads` / `yaml.load` (each can execute
      arbitrary objects from config-supplied bytes).
    """
    try:
        src = textwrap.dedent(inspect.getsource(cls))
    except (OSError, TypeError):
        return False
    if "CodeExecutor" in src:
        return True
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    _UNSAFE_LOADS = {"pickle", "marshal", "dill", "cloudpickle"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in (
                "exec",
                "eval",
                "compile",
                "__import__",
            ):
                return True
            if isinstance(fn, ast.Attribute):
                if fn.attr in ("exec", "eval", "import_module"):
                    return True
                # <module>.loads — pickle/marshal/dill/cloudpickle deserialize
                if (
                    fn.attr == "loads"
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id in _UNSAFE_LOADS
                ):
                    return True
                # yaml.load (without SafeLoader) executes arbitrary tags
                if (
                    fn.attr == "load"
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "yaml"
                ):
                    return True
    return False


def _class_calls_code_exec(cls) -> bool:
    """True if `cls` OR any of its base classes (walking the MRO) calls
    config-supplied code execution. Walking the MRO closes the
    base-class/mixin inheritance gap (R3 security note): a node that inherits
    an exec-capable `run`/`process` method from a base would otherwise pass an
    own-source-only scan.

    KNOWN ACCEPTED GAPS (mitigated by the human-curated allowlist + the
    `_DANGEROUS_NODE_TYPES` floor + the disjointness test, NOT by this scan):
    (1) a node execing via a helper named something other than `CodeExecutor`;
    (2) dynamically-generated classes with no `inspect.getsource`; (3)
    composition nodes (e.g. WorkflowNode) that nest an arbitrary sub-workflow
    without any exec/eval in their own source — covered instead by the
    denylist floor + `test_safe_allowlist_disjoint_from_denylist_floor`.
    """
    for klass in getattr(cls, "__mro__", (cls,)):
        if klass is object:
            continue
        if _source_calls_code_exec(klass):
            return True
    return False


def test_safe_allowlist_disjoint_from_denylist_floor():
    """The positive allowlist and the defense-in-depth floor never overlap."""
    from kailash.workflow.from_brief import _DANGEROUS_NODE_TYPES, _SAFE_NODE_TYPES

    overlap = _SAFE_NODE_TYPES & _DANGEROUS_NODE_TYPES
    assert overlap == set(), f"safe allowlist overlaps the denylist floor: {overlap}"


def test_every_safe_node_is_registered():
    """Every `_SAFE_NODE_TYPES` entry resolves to a real registered node
    (typo / stale-name guard for the hand-curated frozenset)."""
    from kailash.workflow.from_brief import _SAFE_NODE_TYPES

    reg = _warm_and_registry()
    missing = sorted(n for n in _SAFE_NODE_TYPES if n not in reg)
    assert missing == [], f"safe allowlist names not in NodeRegistry: {missing}"


def test_no_safe_node_executes_config_code():
    """INVERSE-COMPLETENESS (the load-bearing guard): no node on the safe
    allowlist may execute config-supplied code. Fires if a future edit adds
    a code-exec-capable node to `_SAFE_NODE_TYPES`."""
    from kailash.workflow.from_brief import _SAFE_NODE_TYPES

    reg = _warm_and_registry()
    offenders = sorted(
        name
        for name in _SAFE_NODE_TYPES
        if name in reg and _class_calls_code_exec(reg[name])
    )
    assert offenders == [], (
        f"safe-allowlisted nodes execute config code (denylist them + remove "
        f"from _SAFE_NODE_TYPES): {offenders}"
    )


@pytest.mark.regression
def test_known_code_exec_nodes_are_not_brief_reachable():
    """#1125 R2 CRITICAL-2 regression: every confirmed config-code-exec node
    is excluded from the resolved safe allowlist."""
    from kailash.workflow.from_brief import _safe_node_types

    allowed = _safe_node_types()
    for danger in (
        "PythonCodeNode",
        "AsyncPythonCodeNode",
        "DataTransformer",
        "ConvergenceCheckerNode",
        "MultiCriteriaConvergenceNode",
        "WorkflowNode",
    ):
        assert danger not in allowed, f"{danger} is brief-reachable (CRITICAL-2)"
