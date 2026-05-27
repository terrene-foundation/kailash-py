# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``DataFlow.from_brief()`` — prose-to-schema realizer for DataFlow models.

This module is the DataFlow surface of the ``from_brief()`` primitive
family (issue #1125). It turns a natural-language description of a
database schema into a fully-configured :class:`DataFlow` instance whose
synthesized model classes pass round-trip ``create()`` → ``read()``
against the supplied connection string (issue #1125 AC 2 + AC 7).

Pipeline (per ``workspaces/from-brief-1125/02-plans/01-architecture.md``
§3.2)::

    brief (prose)
      → scrub_brief()                          # credential scrub
      → SchemaPlanSignature (Kaizen Signature) # LLM emits typed plan
      → validate_plan() with field allowlist   # confidence + allowlist gate
      → realize model classes via type()       # dynamic class construction
      → db.register_model(cls)                 # canonical registration path
      → return configured DataFlow

The realizer does NOT call the operator-facing MCP ``scaffold_model``
tool (per architecture §3.2 Q4 — that tool is for operator scaffolding,
not end-user runtime). Instead, model classes are built directly via
:func:`type` calls bound to the :class:`DataFlow` instance, then
registered through :meth:`DataFlow.register_model` so the resulting
state is byte-identical to the ``@db.model`` decorator path.

Invariants:

1. **LLM-first** — no ``if``/``elif`` on brief content; the Signature
   does the parsing and classification.
2. **Field-type allowlist** — every LLM-emitted field type is validated
   via :func:`kailash._from_brief.allowlist.validate_field_type` against
   DataFlow's known type set; unknown types raise
   :class:`BriefInterpretationError` with ``unknown_value`` set.
3. **Credential scrub** — :func:`scrub_brief` runs BEFORE the brief
   reaches the LLM.
4. **Confidence gate** — ``interpretation_confidence < 0.6`` raises
   :class:`BriefInterpretationError` with ``low_confidence=True``.
5. **Round-trip succeeds** — the synthesized models pass
   ``db.express.create()`` → ``db.express.read()`` against the
   declared connection string.
6. **No scaffold_model coexistence drift** — does NOT invoke the
   operator-facing MCP ``scaffold_model`` tool.
"""

from __future__ import annotations

import keyword
import logging
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Type, cast

from kailash._from_brief import BriefInterpretationError
from kailash._from_brief import BriefPlan as _BasePlan
from kailash._from_brief import coerce_plan, scrub_brief, validate_plan

# kaizen-dependent imports (`BriefPlanSignature` from kailash._from_brief,
# `OutputField` / `BaseAgent` from kaizen) are LAZY — deferred into function
# bodies + the lazy `_schema_plan_signature_cls()` factory below. kaizen is a
# SEPARATE downstream package (kailash-kaizen); importing it at module scope
# would make `import dataflow.from_brief` require kaizen, breaking the DataFlow
# conftest at collection time in any CI job where kaizen is absent. See
# `rules/dependencies.md` § "Declared = Imported" + `rules/framework-first.md`
# layering. Pattern mirrors `kailash/workflow/from_brief.py::_workflow_plan_cls`.
if TYPE_CHECKING:
    from kailash._from_brief import BriefPlanSignature  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "SchemaPlanSignature",
    "DEFAULT_DATAFLOW_FIELD_TYPES",
    "DEFAULT_RELATIONSHIP_TYPES",
    "realize_models",
]


# DataFlow's runtime-accepted field type set, derived from
# ``dataflow/core/engine.py::TYPE_MAPPING`` values + the Python
# primitive types the model-registration path accepts via
# ``get_resolved_type_hints``. This is the allowlist the validator
# checks every LLM-emitted field type against; an LLM emitting a name
# outside this set raises :class:`BriefInterpretationError` with
# ``unknown_value`` set, NOT a deep ``KeyError`` from inside the
# realizer.
DEFAULT_DATAFLOW_FIELD_TYPES: Set[str] = frozenset(
    {
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "datetime",
        "date",
        "time",
        "timedelta",
        "dict",
        "list",
    }
)  # type: ignore[assignment]

# Relationship type vocabulary the LLM may emit. Per architecture §3.2,
# the realizer materializes only one-to-many today (a foreign-key
# column on the child table); other shapes raise a typed allowlist
# miss until the realizer surface is extended.
DEFAULT_RELATIONSHIP_TYPES: Set[str] = frozenset(
    {
        "one_to_many",
        "many_to_one",
        "one_to_one",
    }
)  # type: ignore[assignment]


# Map LLM-emitted field-type strings to actual Python types so the
# dynamic class's ``__annotations__`` carry the right type objects.
# DataFlow's ``_register_model_internal`` reads
# ``cls.__annotations__`` and stores the type for later SQL-type
# inference, so the values here MUST be real Python types (not
# strings) — otherwise the engine cannot infer the SQL column type.
import datetime as _dt  # imported inline so the module-scope import

# list stays focused on the public-API helpers.

_FIELD_TYPE_TO_PYTHON: Dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "bytes": bytes,
    "datetime": _dt.datetime,
    "date": _dt.date,
    "time": _dt.time,
    "timedelta": _dt.timedelta,
    "dict": dict,
    "list": list,
}


# SEC-5: dialect identifier regex (ASCII-only) + 63-char length limit
# (PostgreSQL identifier max). Applied at realizer input time per
# rules/dataflow-identifier-safety.md Rule 1+2, BEFORE the LLM-emitted
# name reaches type(name, bases, ns) and downstream DDL. This keeps the
# loud failure at the validation gate (BriefInterpretationError with
# unknown_value), not 30 frames deep in the DDL stack. See
# workspaces/from-brief-1125/04-validate/round-02-security.md:127-142.
_SQL_IDENTIFIER_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


# ---------------------------------------------------------------------------
# Lazy Signature class (defers kaizen + _from_brief.signatures import past
# module load so `import dataflow.from_brief` does not require kaizen).
# ---------------------------------------------------------------------------
#
# `SchemaPlanSignature(BriefPlanSignature)` was a module-scope class; both its
# base (`BriefPlanSignature` from `kailash._from_brief`) and `OutputField`
# (from `kaizen.signatures`) carry the kaizen dependency. Defining the class at
# module scope therefore made `import dataflow.from_brief` require kaizen,
# breaking the DataFlow conftest at collection time in kaizen-absent CI jobs.
# The class is now built LAZILY via `_schema_plan_signature_cls()` and exposed
# at module scope through `__getattr__` (PEP 562) — mirroring
# `kailash/workflow/from_brief.py::_signature_cls`.

_SCHEMA_PLAN_SIGNATURE_CLS_CACHE: Optional[type] = None


def _schema_plan_signature_cls() -> type:
    """Return the :class:`SchemaPlanSignature` class, constructed lazily.

    Defers the ``kailash._from_brief.BriefPlanSignature`` +
    ``kaizen.signatures.OutputField`` imports to call time so importing this
    module (and thus the DataFlow conftest's ``import kailash._from_brief``
    chain + ``import dataflow``) does not require kaizen.

    Returns:
        The lazily-constructed :class:`SchemaPlanSignature` subclass, cached
        after first invocation.
    """
    global _SCHEMA_PLAN_SIGNATURE_CLS_CACHE
    if _SCHEMA_PLAN_SIGNATURE_CLS_CACHE is not None:
        return _SCHEMA_PLAN_SIGNATURE_CLS_CACHE

    from kailash._from_brief import BriefPlanSignature
    from kaizen.signatures import OutputField

    class SchemaPlanSignature(BriefPlanSignature):
        """Kaizen Signature emitting a DataFlow schema plan from a brief.

        The Signature is invoked once per brief; the LLM emits a list of
        :class:`ModelSpec`-shaped dicts the realizer then materializes into
        actual ``@db.model``-equivalent classes. Per
        ``rules/agent-reasoning.md`` MUST Rule 3, the OutputField
        description below describes the reasoning the LLM is to perform —
        it does NOT pre-filter the brief in Python.

        Plan-shape contract (what the LLM emits in ``models``):

        .. code-block:: python

            [
                {
                    "name": "User",                       # Python class name
                    "fields": [
                        {"name": "id", "type": "int"},
                        {"name": "email", "type": "str"},
                        {"name": "created_at", "type": "datetime"},
                    ],
                    "relationships": [
                        {
                            "target_model": "Post",
                            "rel_type": "one_to_many",
                            "fk_column": "user_id",
                        }
                    ],
                },
                ...
            ]

        The ``fields`` list MUST include an ``id`` field per the DataFlow
        primary-key invariant (see ``rules/patterns.md`` § DataFlow Models
        & Workflows: "PK MUST be named 'id'"). The realizer surfaces a
        typed error if ``id`` is absent so the failure mode is loud, not
        silent.
        """

        # See the pyright suppressions in BriefPlanSignature for the
        # Signature metaclass-rebinding rationale.
        models: list = OutputField(  # pyright: ignore[reportAssignmentType]
            description=(
                "List of ModelSpec dicts, one per database table the user "
                "asked for. Each dict has: 'name' (Python class name, "
                "CamelCase, valid Python identifier); 'fields' (list of "
                "{'name', 'type'} dicts, type drawn from "
                "{str, int, float, bool, bytes, datetime, date, time, "
                "timedelta, dict, list}); 'relationships' (list of "
                "{'target_model', 'rel_type', 'fk_column'} dicts, "
                "rel_type drawn from {one_to_many, many_to_one, "
                "one_to_one}). Every model MUST have an 'id' field. "
                "Field names MUST be valid Python identifiers. Do NOT "
                "emit columns the brief did not ask for (no inferred "
                "audit columns, no inferred timestamps unless the brief "
                "mentions them); DataFlow manages created_at/updated_at "
                "automatically when annotated."
            )
        )

    _SCHEMA_PLAN_SIGNATURE_CLS_CACHE = SchemaPlanSignature
    return SchemaPlanSignature


def __getattr__(name: str) -> Any:
    """PEP 562 module-level ``__getattr__`` for lazy class resolution.

    Per ``rules/orphan-detection.md`` § 6b, lazy-loaded symbols MUST stay
    discoverable through the module's public surface. This hook resolves
    ``from dataflow.from_brief import SchemaPlanSignature`` at call-time (the
    symbol is in ``__all__``, has a lazy resolver, and has a ``TYPE_CHECKING``
    stub below).
    """
    if name == "SchemaPlanSignature":
        return _schema_plan_signature_cls()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:
    # Surface the lazy class to static analyzers (CodeQL py/undefined-export,
    # pyright, mypy) per `rules/orphan-detection.md` § 6b. Runtime body lives
    # inside `_schema_plan_signature_cls`.
    class SchemaPlanSignature:  # type: ignore[no-redef]
        """Static-analyzer stub; runtime body in :func:`_schema_plan_signature_cls`."""

        models: list


# ---------------------------------------------------------------------------
# Realizer
# ---------------------------------------------------------------------------


def _validate_model_spec(spec: Any) -> Dict[str, Any]:
    """Coerce one ``models`` entry into a validated dict.

    The Signature's typed output is permissive (LLMs occasionally emit
    keys with extra whitespace, omit optional sections, or wrap the
    spec in a single-element list). This helper normalises the shape
    so the realizer can iterate cleanly, raising
    :class:`BriefInterpretationError(malformed=True)` on any
    structural defect the validator cannot reasonably repair.
    """
    if not isinstance(spec, dict):
        raise BriefInterpretationError(
            f"model spec is not a dict (got {type(spec).__name__!r}); "
            f"the LLM emitted a malformed plan entry",
            malformed=True,
        )
    name = spec.get("name")
    # SEC-5 three-layer gate: regex (ASCII, 63-char limit) + keyword check.
    # `str.isidentifier()` alone accepts unicode and Python keywords,
    # both of which break at DDL time deeper in the call stack. Per
    # rules/dataflow-identifier-safety.md Rule 1+2, validation fires here.
    if (
        not isinstance(name, str)
        or not _SQL_IDENTIFIER_RE.match(name)
        or keyword.iskeyword(name)
    ):
        raise BriefInterpretationError(
            f"model name {name!r} fails the dialect identifier gate "
            f"(ASCII-only ^[A-Za-z_][A-Za-z0-9_]{{0,62}}$ AND not a "
            f"Python keyword)",
            unknown_value=f"identifier={name!r}",
        )
    fields = spec.get("fields") or []
    if not isinstance(fields, list) or not fields:
        raise BriefInterpretationError(
            f"model {name!r} has no fields; every DataFlow model "
            f"requires at least an 'id' field",
            malformed=True,
        )
    relationships = spec.get("relationships") or []
    if not isinstance(relationships, list):
        raise BriefInterpretationError(
            f"model {name!r} has malformed relationships (expected "
            f"list, got {type(relationships).__name__!r})",
            malformed=True,
        )
    return {"name": name, "fields": fields, "relationships": relationships}


def _build_annotations(
    model_name: str,
    fields: List[Any],
    allowed_field_types: Set[str],
) -> Dict[str, type]:
    """Convert LLM-emitted field dicts into ``__annotations__``.

    Each field dict MUST have ``{"name": <identifier>, "type": <str>}``
    where ``type`` is in ``allowed_field_types``. Returns a mapping
    suitable for assignment as ``cls.__annotations__`` — DataFlow's
    ``_register_model_internal`` reads exactly that attribute via
    ``get_resolved_type_hints``.

    Raises:
        BriefInterpretationError: with ``unknown_value=<type-name>``
            when a field type is outside the allowlist;
            ``malformed=True`` for structural defects.
    """
    annotations: Dict[str, type] = {}
    seen: Set[str] = set()
    has_id = False
    for entry in fields:
        if not isinstance(entry, dict):
            raise BriefInterpretationError(
                f"model {model_name!r} has a non-dict field entry "
                f"(got {type(entry).__name__!r}); the LLM emitted a "
                f"malformed plan entry",
                malformed=True,
            )
        fname = entry.get("name")
        ftype = entry.get("type")
        # SEC-5: same dialect identifier gate as the model-name check.
        # Field names become column names in DDL; the same
        # ASCII-regex + keyword constraint applies.
        if (
            not isinstance(fname, str)
            or not _SQL_IDENTIFIER_RE.match(fname)
            or keyword.iskeyword(fname)
        ):
            raise BriefInterpretationError(
                f"model {model_name!r} field name {fname!r} fails the "
                f"dialect identifier gate (ASCII-only "
                f"^[A-Za-z_][A-Za-z0-9_]{{0,62}}$ AND not a Python "
                f"keyword)",
                unknown_value=f"identifier={fname!r}",
            )
        if fname in seen:
            raise BriefInterpretationError(
                f"model {model_name!r} declares duplicate field " f"{fname!r}",
                malformed=True,
            )
        seen.add(fname)
        if not isinstance(ftype, str):
            raise BriefInterpretationError(
                f"model {model_name!r} field {fname!r} has a non-string "
                f"type (got {type(ftype).__name__!r}); the LLM emitted "
                f"a malformed plan entry",
                malformed=True,
            )
        if ftype not in allowed_field_types:
            # Route through the typed exception per invariant 2: the
            # LLM emitted a field type DataFlow does not expose. Loud
            # error with the offending name in ``unknown_value``.
            raise BriefInterpretationError(
                f"model {model_name!r} field {fname!r} declared "
                f"type={ftype!r} which is not in DataFlow's field-type "
                f"allowlist (allowed: {sorted(allowed_field_types)!r})",
                unknown_value=ftype,
            )
        python_type = _FIELD_TYPE_TO_PYTHON[ftype]
        annotations[fname] = python_type
        if fname == "id":
            has_id = True
    if not has_id:
        # DataFlow's PK invariant (`rules/patterns.md`): every model's
        # primary key MUST be named "id". The realizer enforces this
        # at plan-validation time so the failure surface is the brief,
        # not a deep DDL error 30 frames in.
        raise BriefInterpretationError(
            f"model {model_name!r} has no 'id' field; DataFlow "
            f"requires the primary key to be named 'id'",
            malformed=True,
        )
    return annotations


def _build_relationship_columns(
    model_name: str,
    relationships: List[Any],
    allowed_relationship_types: Set[str],
    annotations: Dict[str, type],
) -> None:
    """Add foreign-key columns to ``annotations`` from relationship specs.

    Per architecture §3.2 the realizer materializes one-to-many /
    many-to-one as a foreign-key column on the child table. The
    Signature emits the relationship from the parent side
    (``User -> one_to_many -> Post on user_id``); the realizer adds
    the ``user_id`` int column to the OTHER model's annotations at
    the orchestrator level. This helper validates the rel_type +
    fk_column shape; the cross-model column wiring happens in
    :func:`realize_models`.
    """
    for entry in relationships:
        if not isinstance(entry, dict):
            raise BriefInterpretationError(
                f"model {model_name!r} has a non-dict relationship "
                f"entry (got {type(entry).__name__!r})",
                malformed=True,
            )
        rel_type = entry.get("rel_type")
        target = entry.get("target_model")
        fk = entry.get("fk_column")
        if rel_type not in allowed_relationship_types:
            raise BriefInterpretationError(
                f"model {model_name!r} declares relationship type "
                f"{rel_type!r} which is not in DataFlow's "
                f"allowlist (allowed: "
                f"{sorted(allowed_relationship_types)!r})",
                unknown_value=rel_type if isinstance(rel_type, str) else None,
            )
        if not isinstance(target, str) or not target.isidentifier():
            raise BriefInterpretationError(
                f"model {model_name!r} relationship has invalid "
                f"target_model={target!r}",
                malformed=True,
            )
        if not isinstance(fk, str) or not fk.isidentifier():
            raise BriefInterpretationError(
                f"model {model_name!r} relationship has invalid " f"fk_column={fk!r}",
                malformed=True,
            )


def realize_models(
    db: Any,
    plan_models: List[Any],
    *,
    allowed_field_types: Set[str] = DEFAULT_DATAFLOW_FIELD_TYPES,
    allowed_relationship_types: Set[str] = DEFAULT_RELATIONSHIP_TYPES,
) -> List[Type]:
    """Materialize plan model specs into ``@db.model``-equivalent classes.

    For each :class:`SchemaPlanSignature` ``models`` entry, this
    function constructs a synthetic class via :func:`type` with the
    appropriate ``__annotations__`` and registers it through
    :meth:`DataFlow.register_model` — the canonical programmatic
    counterpart to the ``@db.model`` decorator (engine.py:1733).
    Both paths share the same body (``_register_model_internal``)
    so the resulting framework state is byte-identical.

    The realizer is two-pass so cross-model foreign-key columns are
    wired correctly even when the LLM emits the parent model first
    (the typical case). Pass 1 collects validated specs + annotations
    per model; pass 2 splices each relationship's FK column into the
    target model's annotations BEFORE registration.

    Args:
        db: The :class:`DataFlow` instance the synthesized models
            will be registered against.
        plan_models: The validated ``models`` field from the
            Signature output.
        allowed_field_types: Allowlist used by
            :func:`_build_annotations`. Defaults to
            :data:`DEFAULT_DATAFLOW_FIELD_TYPES`.
        allowed_relationship_types: Allowlist used by
            :func:`_build_relationship_columns`. Defaults to
            :data:`DEFAULT_RELATIONSHIP_TYPES`.

    Returns:
        The list of synthesized classes, in plan order, after
        registration.

    Raises:
        BriefInterpretationError: When any spec fails validation.
    """
    # Pass 1 — validate every spec into a normalised dict + collect
    # the per-model annotations the registrar will consume.
    normalised: List[Dict[str, Any]] = [_validate_model_spec(s) for s in plan_models]
    per_model_annotations: Dict[str, Dict[str, type]] = {}
    for spec in normalised:
        per_model_annotations[spec["name"]] = _build_annotations(
            spec["name"], spec["fields"], allowed_field_types
        )

    # Pass 2 — validate relationships AND splice FK columns into the
    # target model's annotations. The parent-side declaration
    # (``User -> one_to_many -> Post on user_id``) means the child
    # model ``Post`` MUST grow a ``user_id: int`` column. The
    # validator runs first per relationship so an allowlist miss is
    # raised BEFORE any mutation lands.
    for spec in normalised:
        _build_relationship_columns(
            spec["name"],
            spec["relationships"],
            allowed_relationship_types,
            per_model_annotations[spec["name"]],
        )
        for rel in spec["relationships"]:
            target = rel["target_model"]
            fk = rel["fk_column"]
            rel_type = rel["rel_type"]
            # one_to_many / one_to_one: the FK lives on the TARGET
            # (child) model. many_to_one: the FK lives on THIS model.
            if rel_type in ("one_to_many", "one_to_one"):
                if target not in per_model_annotations:
                    raise BriefInterpretationError(
                        f"model {spec['name']!r} relationship targets "
                        f"unknown model {target!r}; the LLM emitted a "
                        f"plan referencing a model it did not define",
                        malformed=True,
                    )
                # Idempotent: re-declaring the same FK column is a
                # no-op; declaring a different type for the SAME name
                # is a malformed plan.
                target_ann = per_model_annotations[target]
                if fk in target_ann and target_ann[fk] is not int:
                    raise BriefInterpretationError(
                        f"relationship FK column {fk!r} on model "
                        f"{target!r} conflicts with existing "
                        f"{target_ann[fk]!r} annotation",
                        malformed=True,
                    )
                target_ann[fk] = int
            elif rel_type == "many_to_one":
                this_ann = per_model_annotations[spec["name"]]
                if fk in this_ann and this_ann[fk] is not int:
                    raise BriefInterpretationError(
                        f"relationship FK column {fk!r} on model "
                        f"{spec['name']!r} conflicts with existing "
                        f"{this_ann[fk]!r} annotation",
                        malformed=True,
                    )
                this_ann[fk] = int

    # Pass 3 — build the actual classes and register through the
    # canonical programmatic API. ``register_model`` shares the body
    # of ``@db.model`` (engine.py:1813), so framework state is
    # byte-identical to the decorator path.
    registered: List[Type] = []
    for spec in normalised:
        name = spec["name"]
        annotations = per_model_annotations[name]
        # Build the synthetic class via the standard 3-arg builtin
        # (name, bases, namespace). Empty bases so DataFlow does not
        # try to walk a parent class's MRO for fields. The
        # ``__annotations__`` namespace entry is what
        # ``get_resolved_type_hints`` reads at registration time.
        cls = type(name, (), {"__annotations__": dict(annotations)})
        # ``register_model`` is the programmatic counterpart to
        # ``@db.model`` (engine.py:1733) — same body, no per-model
        # decorator-versus-programmatic drift.
        db.register_model(cls)
        registered.append(cls)
    return registered


# ---------------------------------------------------------------------------
# Classmethod entry point — wired onto DataFlow in ``dataflow/__init__.py``.
# ---------------------------------------------------------------------------


def from_brief(
    cls: Type,
    brief: str,
    conn_str: Optional[str] = None,
    *,
    confidence_threshold: float = 0.6,
    llm_model: Optional[str] = None,
) -> Any:
    """Realize a :class:`DataFlow` from a natural-language brief.

    This is the body of :meth:`DataFlow.from_brief`; it lives in the
    module so the realizer + Signature stay co-located with the
    classmethod binding. The class binding happens in
    ``dataflow/__init__.py``.

    Args:
        cls: The :class:`DataFlow` class (bound classmethod self).
        brief: Natural-language description of the schema. May embed
            credentials — :func:`scrub_brief` runs before the brief
            reaches the LLM.
        conn_str: Database connection string. ``None`` resolves to
            DataFlow's default (in-memory SQLite via the engine).
        confidence_threshold: Minimum
            ``interpretation_confidence`` required to proceed.
            Defaults to 0.6 per
            :data:`kailash._from_brief.DEFAULT_CONFIDENCE_THRESHOLD`.
        llm_model: Override the LLM model used by the Signature.
            ``None`` reads ``DEFAULT_LLM_MODEL`` from the
            environment per :func:`get_default_llm_model`.

    Returns:
        A configured :class:`DataFlow` instance with the synthesized
        models registered. The caller is responsible for awaiting
        ``await db.initialize()`` if a schema-creation pass is
        required before the first ``db.express`` call.

    Raises:
        BriefInterpretationError: For confidence / allowlist /
            malformed-plan failures (see :class:`BriefInterpretationError`
            discriminator fields).
        MissingDefaultLLMModelError: When ``llm_model`` is None and
            ``DEFAULT_LLM_MODEL`` is unset.
    """
    # Lazy kaizen imports — deferred to call time so importing this module
    # does not require kaizen (the DataFlow conftest collection path). A
    # caller invoking from_brief() IS in an execution path where kaizen is
    # present. `get_default_llm_model` lives in `kailash._from_brief.signatures`
    # which imports kaizen at module scope, so it is lazy too.
    from kailash._from_brief import get_default_llm_model
    from kaizen.core.base_agent import BaseAgent, BaseAgentConfig

    # Invariant 3 — scrub credentials before any logging or LLM call.
    # The Kaizen agent dispatch logs the input prompt; the brief MUST
    # be scrubbed before it reaches that surface.
    scrubbed = scrub_brief(brief)

    # Resolve the LLM model from .env per ``rules/env-models.md``.
    resolved_model = llm_model or get_default_llm_model()

    # Invariant 1 — LLM-first: the Signature describes the reasoning,
    # the BaseAgent dispatches it through the LLM. The Python side
    # does not branch on brief content.
    #
    # Per ``rules/agent-reasoning.md`` MUST Rule 3, the Signature is
    # the contract — the BaseAgent is the executor that compiles the
    # Signature into a single LLM call. We use ``single_shot``
    # strategy (one-pass; no tool-use loop is required for schema
    # synthesis from prose per architecture §3.2).
    agent_config = BaseAgentConfig(
        model=resolved_model,
        strategy_type="single_shot",
        # Hooks / MCP / async-LLM defaults are off; this is a pure
        # synchronous one-shot inference.
    )
    agent = BaseAgent(
        config=agent_config,
        signature=_schema_plan_signature_cls()(),
        # Pass an empty mcp_servers list so the default MCP
        # auto-discovery doesn't try to launch the builtin server
        # for what is a one-shot inference call.
        mcp_servers=[],
    )
    raw_output = agent.run(brief=scrubbed)

    # Normalise the Signature output into the plan dict the validator
    # expects. Kaizen's Signature returns a dict-like object whose
    # keys are the OutputField names; coerce via ``coerce_plan`` so a
    # Pydantic ``ValidationError`` becomes a typed
    # ``BriefInterpretationError(malformed=True)``.
    raw_plan: Dict[str, Any] = {
        "interpretation_confidence": raw_output.get("interpretation_confidence"),
        "models": raw_output.get("models", []),
    }
    # ``coerce_plan`` is typed to return ``BriefPlan``; the concrete
    # value here is a ``_SchemaPlan`` (the subclass we passed). Cast
    # the local binding so the ``plan.models`` access below is
    # statically typed against the subclass surface.
    plan = cast(_SchemaPlan, coerce_plan(raw_plan, _SchemaPlan))

    # Invariants 2 + 4 — confidence + allowlist gates. The validator
    # surfaces both via :class:`BriefInterpretationError` with
    # discriminator fields (``low_confidence`` / ``unknown_value``).
    validate_plan(
        plan,
        confidence_threshold=confidence_threshold,
    )
    # ``validate_plan`` covers ``BriefPlan`` shape + confidence. The
    # field-type / relationship-type allowlists fire inside the
    # realizer where they have per-spec context. This keeps the
    # validator generic across the from_brief() primitive family.

    # Construct the DataFlow instance. ``cls`` is the bound classmethod
    # receiver (==``DataFlow``); we call ``cls(conn_str)`` so subclasses
    # transparently get their own ``from_brief`` if any future
    # subclass wants to override construction.
    db = cls(conn_str) if conn_str is not None else cls()

    # Invariant 6 — does NOT call ``scaffold_model``. The realizer
    # uses :meth:`DataFlow.register_model` (engine.py:1733), which is
    # the same body the ``@db.model`` decorator delegates to.
    realize_models(db, plan.models)
    return db


# Pydantic plan model the validator constructs from the Signature's
# raw output. Lives at module scope so the type is reusable in tests.
# The ``_BasePlan`` import is hoisted to the top of the module so the
# class definition below resolves at module-load time.


class _SchemaPlan(_BasePlan):
    """Pydantic model the validator constructs from raw Signature output.

    Inherits ``interpretation_confidence`` from
    :class:`kailash._from_brief.BriefPlan`; adds the ``models`` list
    the realizer consumes. Pydantic's ``extra="forbid"`` config means
    a stray field raises at model construction — converting "the LLM
    hallucinated a field" into a loud, debuggable error.
    """

    models: List[Any]
