"""Regression gate for #772 — consolidated two-spelling Optional/Union detection.

#772 consolidated the two-spelling Optional/Union detection (``origin is Union
or origin is types.UnionType``) that was independently re-implemented across
DataFlow's type-introspection helpers into a SINGLE primitive,
``union_non_none_args`` (plus ``strip_annotated``). #1207 and #1228 were the
maintenance-tax incidents the consolidation prevents recurring.

Two test classes:

1. **Structural invariants** (``ast``/``grep`` based — this is the ONE
   legitimately structural test per cross-sdk-inspection Rule 3a + refactor-
   invariants.md): exactly ONE ``def union_non_none_args`` exists in the source
   tree, AND no ``is types.UnionType`` literal survives OUTSIDE
   ``type_introspection.py``. These fail loudly if a future change re-inlines
   union detection at any caller.

2. **Behavioral coverage** mirroring #768 (parameterized generics on
   ``_resolve_type``), #1207 (``_unwrap_optional_type`` JSONB read path), and
   #1228 (PEP 604 ``T | None`` across every routed helper) THROUGH the
   consolidated path, so those fixes stay green.
"""

import ast
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union

import pytest

from dataflow.core.nodes import NodeGenerator, _normalize_id_type, _unwrap_optional_type
from dataflow.core.type_processor import TypeAwareFieldProcessor

# packages/kailash-dataflow/src/dataflow  (this file is at .../tests/regression/)
SRC_DATAFLOW = Path(__file__).resolve().parents[2] / "src" / "dataflow"
INTROSPECTION_REL = "core/type_introspection.py"


# --------------------------------------------------------------------------- #
# 1. Structural invariants (AST / grep — the consolidation's signature lock)
# --------------------------------------------------------------------------- #
@pytest.mark.regression
class TestIssue772StructuralInvariants:
    """The two-spelling union detection exists in EXACTLY ONE place."""

    def _py_files(self):
        return sorted(SRC_DATAFLOW.rglob("*.py"))

    def test_exactly_one_def_union_non_none_args(self):
        """AST-enumerate every `def union_non_none_args` across the src tree."""
        definitions = []
        for path in self._py_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "union_non_none_args"
                ):
                    definitions.append(
                        f"{path.relative_to(SRC_DATAFLOW)}:{node.lineno}"
                    )
        assert len(definitions) == 1, (
            "union_non_none_args must be defined EXACTLY once (the #772 "
            f"consolidation invariant); found {len(definitions)}: {definitions}. "
            "A second definition means a caller re-inlined union detection."
        )
        assert definitions[0].startswith("core/type_introspection.py"), (
            f"the single union_non_none_args def must live in "
            f"{INTROSPECTION_REL}; found at {definitions[0]}"
        )

    def test_no_uniontype_reference_survives_outside_introspection_module(self):
        """No ``types.UnionType`` attribute reference survives in live code
        outside type_introspection.py -- ``is types.UnionType``,
        ``isinstance(x, types.UnionType)``, or ANY other form.

        AST-based (matches every ``ast.Attribute`` whose attr is ``UnionType``)
        so it catches the ``isinstance`` spelling the prior substring check
        missed at ``model_registry.py`` (issue #772 follow-up), AND it ignores
        docstring / comment prose (those parse as ``ast.Constant``, never
        ``ast.Attribute``) without needing string-prefix special-casing.
        """
        offenders = []
        for path in self._py_files():
            rel = str(path.relative_to(SRC_DATAFLOW))
            if rel == INTROSPECTION_REL:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr == "UnionType":
                    offenders.append(f"{rel}:{node.lineno}")
        assert not offenders, (
            "types.UnionType must NOT be referenced in live code outside "
            f"{INTROSPECTION_REL} (the #772 single-detection-site invariant). "
            f"Re-inlined/missed sites: {offenders}"
        )

    def test_routed_callers_import_the_shared_primitive(self):
        """The routed callers import union_non_none_args (no orphan helper)."""
        # The four primary + routed sibling modules MUST import the primitive.
        routed = [
            "core/type_processor.py",
            "core/nodes.py",
            "core/engine.py",
            "core/schema.py",
            "core/model_registry.py",
            "validation/model_validator.py",
            "migrations/fk_aware_model_integration.py",
        ]
        for rel in routed:
            text = (SRC_DATAFLOW / rel).read_text(encoding="utf-8")
            assert "union_non_none_args" in text, (
                f"{rel} no longer references union_non_none_args; either the "
                "import was dropped or the detection was re-inlined."
            )


# --------------------------------------------------------------------------- #
# 2. Behavioral coverage through the consolidated path (#768 / #1207 / #1228)
# --------------------------------------------------------------------------- #
def _resolve(annotation: Any):
    tp = TypeAwareFieldProcessor({"f": {"type": annotation, "required": False}}, "M")
    return tp._resolved_types["f"]


@pytest.fixture
def gen():
    import types as _types

    return NodeGenerator(_types.SimpleNamespace())


@pytest.mark.regression
class TestIssue768ParameterizedGenericsResolveType:
    """#768: parameterized generics resolve to their isinstance-usable origin."""

    def test_list_str_resolves_to_list(self):
        assert _resolve(list[str]) is list

    def test_dict_str_any_resolves_to_dict(self):
        assert _resolve(Dict[str, Any]) is dict

    def test_typing_list_resolves_to_list(self):
        assert _resolve(List[int]) is list

    def test_optional_parameterized_resolves_through_to_origin(self):
        # Optional[list[str]] -> list[str] -> list (recurse through the union).
        assert _resolve(Optional[list[str]]) is list


@pytest.mark.regression
class TestIssue1207UnwrapOptionalThroughConsolidatedPath:
    """#1207: _unwrap_optional_type handles both union spellings, collapse-only."""

    def test_optional_list_collapses_to_list(self):
        assert _unwrap_optional_type(Optional[list]) is list

    def test_typing_union_list_none_collapses_to_list(self):
        assert _unwrap_optional_type(Union[list, None]) is list

    def test_pep604_list_or_none_collapses_to_list(self):
        assert _unwrap_optional_type(list | None) is list

    def test_optional_dict_collapses_to_dict(self):
        assert _unwrap_optional_type(Optional[dict]) is dict

    def test_multi_arg_union_returned_unchanged(self):
        assert _unwrap_optional_type(Union[list, dict]) == Union[list, dict]

    def test_plain_type_passes_through(self):
        assert _unwrap_optional_type(str) is str


@pytest.mark.regression
class TestIssue1228Pep604ThroughConsolidatedPath:
    """#1228: PEP 604 ``T | None`` treated identically to Optional[T]."""

    def test_normalize_id_type_pep604_agrees_with_typing(self):
        assert _normalize_id_type(int | None) is _normalize_id_type(Optional[int])

    def test_normalize_type_annotation_pep604_agrees_with_typing(self, gen):
        assert gen._normalize_type_annotation(
            list | None
        ) is gen._normalize_type_annotation(Optional[list])

    def test_resolve_type_pep604_optional_resolves_to_inner(self):
        assert _resolve(int | None) is int

    def test_resolve_type_multi_arg_pep604_union_returned_as_is(self):
        # _resolve_type's distinct policy: multi-type union returned unchanged.
        assert _resolve(int | str) == (int | str)

    def test_validate_field_passes_multi_arg_pep604_union_through(self):
        tp = TypeAwareFieldProcessor({"x": {"type": int | str, "required": False}}, "M")
        assert tp._resolved_types["x"] == (int | str)
        assert tp.validate_field("x", "hello") == "hello"


@pytest.mark.regression
class TestIssue772AnnotatedStripAdd:
    """#772 strict ADD: every routed normalize/resolve site now strips Annotated.

    Pre-consolidation, Annotated[T, ...] fell through to the str fallback at
    _normalize_type_annotation / _normalize_id_type and was returned unchanged
    by _resolve_type's origin branch. Post-consolidation, strip_annotated runs
    first at each site, so Annotated resolves to its wrapped type. This is the
    consolidation's proof — a new type-form handled in ONE place.
    """

    def test_resolve_type_strips_annotated(self):
        assert _resolve(Annotated[int, "x"]) is int

    def test_normalize_type_annotation_strips_annotated(self, gen):
        assert gen._normalize_type_annotation(Annotated[int, "x"]) is int

    def test_normalize_id_type_strips_annotated(self):
        assert _normalize_id_type(Annotated[int, "x"]) is int


@pytest.mark.regression
class TestIssue772ModelRegistryFieldNaming:
    """#772 follow-up: ``model_registry._normalize_field_type`` was a 10th site
    re-implementing two-spelling union detection via ``isinstance(_,
    types.UnionType)`` -- missed by the original substring invariant (it has no
    ``is types.UnionType`` literal). It now routes through ``union_non_none_args``;
    BOTH union spellings name identically and the prior outputs are preserved
    exactly. Behavior baseline (pre-refactor): Optional[int]/int|None -> "Optional",
    str|int / Union[int,str,None] / int|str|None -> "Union", list[str] -> "list",
    str -> "str".
    """

    @staticmethod
    def _norm(annotation: Any) -> str:
        from dataflow.core.model_registry import ModelRegistry

        # _normalize_field_type uses only its argument, not instance state.
        reg = object.__new__(ModelRegistry)
        return reg._normalize_field_type(annotation)

    def test_pep604_optional_names_optional(self):
        assert self._norm(int | None) == "Optional"

    def test_typing_optional_names_optional(self):
        assert self._norm(Optional[int]) == "Optional"

    def test_both_optional_spellings_agree(self):
        assert self._norm(int | None) == self._norm(Optional[int]) == "Optional"

    def test_pep604_multi_union_names_union(self):
        assert self._norm(str | int) == "Union"

    def test_typing_multi_union_with_none_names_union(self):
        assert self._norm(Union[int, str, None]) == "Union"

    def test_pep604_multi_union_with_none_names_union(self):
        assert self._norm(int | str | None) == "Union"

    def test_builtin_passes_through(self):
        assert self._norm(str) == "str"

    def test_parameterized_generic_names_origin(self):
        assert self._norm(list[str]) == "list"
