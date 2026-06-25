"""Regression: VAL-011 — @db.model field names that collide with a core
NodeMetadata attribute (F30 / originally surfaced by #855).

Bug
---
A user ``@db.model`` field whose name collides with a core ``NodeMetadata``
attribute corrupts node construction. ``NodeMetadata``
(``src/kailash/nodes/base.py``) has 7 fields:
``id, name, description, version, author, created_at, tags``. The
kwargs->NodeMetadata bridge in ``Node.__init__`` reads ``kwargs.get("name")``,
``("description")``, ``("version")``, ``("author")``, ``("tags")`` straight into
``NodeMetadata(...)``. A DataFlow-generated CRUD node forwards its construction
config to ``Node.__init__`` as ``**kwargs`` (``DataFlowNode.__init__`` ->
``super().__init__(**kwargs)``), so a colliding user field value reaches that
bridge through the normal ``WorkflowBuilder.add_node(...).build()`` path. Two
failure modes result:

- ``tags`` (NodeMetadata.tags is ``set[str]``, the user field is usually
  ``str``) -> hard crash ``NodeConfigurationError: Invalid node metadata ...
  tags / Input should be a valid set``.
- ``name`` / ``version`` / ``description`` / ``author`` (all ``str``) -> SILENT
  override: the user's field value is hijacked into node metadata with no error.

Before VAL-011 the only DataFlow-level field-name validator
(``_validate_naming_conventions``, VAL-008/009) caught camelCase + SQL reserved
words; ``name`` / ``tags`` / ``version`` / etc. are not SQL keywords, so the
collision was caught only at node-construction time (crash) or never (silent
override).

Fix
---
VAL-011 (``_validate_node_metadata_collisions`` in
``packages/kailash-dataflow/src/dataflow/decorators.py``) warns at
decoration/validation time when a user field collides with a core
``NodeMetadata`` attribute. The reserved set is derived from
``NodeMetadata.model_fields`` at runtime (so it cannot drift from base.py) and
excludes ``id`` (the required PK name, VAL-003) and the auto-managed fields
(owned by VAL-005). Net reserved set: ``{name, description, version, author,
tags}``. VAL-011 is a Warning in WARN mode (severity-consistent with its sibling
field-name checks VAL-005/008/009) and escalates to a ``ModelValidationError``
in STRICT mode, because — unlike a camelCase or SQL-reserved-word hint — a
NodeMetadata collision is a guaranteed crash-or-silent-corruption at node
construction.

These tests exercise the REAL build-time validation path
(``dataflow.decorators.model`` over a SQLAlchemy-mapped class — the same surface
``@db.model(strict=True)`` / the spec §2.7 validation modes use, and the same
surface every sibling VAL-0xx check is tested against in
``tests/unit/test_strict_mode_model_validation.py``). They assert the guard
FIRES with a clear message at validation time, rather than the model only
crashing later at node construction.
"""

import warnings

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

from dataflow.decorators import (
    ValidationMode,
    ValidationResult,
    _node_metadata_reserved_fields,
    _validate_node_metadata_collisions,
    model,
)
from dataflow.exceptions import ModelValidationError


@pytest.fixture
def base():
    """Fresh declarative_base per test to avoid table-name conflicts."""
    return declarative_base()


def _warning_messages(record):
    return [str(w.message) for w in record]


# ---------------------------------------------------------------------------
# Reserved-set derivation (runtime, not hardcoded)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_reserved_set_derived_from_node_metadata_excludes_id_and_created_at():
    """The VAL-011 reserved set is derived from ``NodeMetadata.model_fields`` at
    runtime and excludes ``id`` (required PK, VAL-003) and the auto-managed
    fields (owned by VAL-005). It MUST NOT be a hardcoded list that can drift
    from base.py.
    """
    from kailash.nodes.base import NodeMetadata

    reserved = _node_metadata_reserved_fields()

    # Derived from the live NodeMetadata schema.
    all_meta_fields = set(NodeMetadata.model_fields.keys())
    assert reserved <= all_meta_fields, (
        "reserved set must be a subset of NodeMetadata.model_fields; "
        f"got {reserved}, NodeMetadata fields {all_meta_fields}"
    )

    # id excluded (required PK name per VAL-003 — correct usage, not a footgun).
    assert "id" not in reserved
    # created_at excluded (owned by VAL-005 — no double-warn).
    assert "created_at" not in reserved
    # The collision-prone NodeMetadata str/set attributes ARE reserved.
    assert reserved == {"name", "description", "version", "author", "tags"}


# ---------------------------------------------------------------------------
# Raw-attribute scan path (white-box)
#
# The committed @model(...) tests above exercise the SQLAlchemy *mapper*
# fallback path: a declarative_base() subclass exposes InstrumentedAttribute
# (not Column) for its columns, so the validator's raw `isinstance(attr, Column)`
# scan finds nothing and falls through to `sa_inspect(cls).columns`. The raw
# path fires for a class carrying raw `Column` class attributes (a pre-mapping
# class). This direct call pins that branch so a future refactor that breaks
# raw-attribute scanning fails loudly here.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_raw_attribute_path_catches_collision_on_unmapped_column_class():
    class RawColumnModel:
        # Raw Column class attributes (NOT declarative-mapped) → the validator's
        # `isinstance(attr, Column)` raw scan fires; mapper fallback is not reached.
        id = Column(Integer, primary_key=True)
        name = Column(String)  # collides with NodeMetadata.name (silent-override mode)
        tags = Column(String)  # collides with NodeMetadata.tags (crash mode)
        username = Column(String)  # substring-only → MUST NOT collide

    result = ValidationResult()
    _validate_node_metadata_collisions(RawColumnModel, result)

    flagged = {w.field for w in result.warnings if w.code == "VAL-011"}
    assert flagged == {"name", "tags"}, (
        "raw-attribute path must flag exactly the colliding columns "
        f"(name, tags); got {flagged}"
    )
    # id (required PK, VAL-003) and username (substring-only) MUST NOT be flagged.
    assert "id" not in flagged
    assert "username" not in flagged


# ---------------------------------------------------------------------------
# (a) tags collision is caught at validation time with a clear message
#     (instead of only crashing at node construction)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_warns_on_tags_collision_in_warn_mode(base):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class WidgetWithTags(base):
            __tablename__ = "val011_widget_tags_warn"
            id = Column(Integer, primary_key=True)
            tags = Column(String)

        assert WidgetWithTags is not None  # WARN mode does not raise
        msgs = _warning_messages(rec)
        assert any(
            "VAL-011" in m and "tags" in m and "tag_list" in m for m in msgs
        ), f"expected a VAL-011 tags warning suggesting tag_list; got {msgs}"


@pytest.mark.regression
def test_val011_raises_on_tags_collision_in_strict_mode(base):
    """STRICT mode escalates the VAL-011 ``tags`` collision to a hard error at
    DECORATION time — the clear failure the bug report wanted, instead of the
    opaque ``NodeConfigurationError`` that previously only surfaced when the
    generated node was constructed during ``WorkflowBuilder.build()``.
    """
    with pytest.raises(ModelValidationError) as exc_info:

        @model(strict=True)
        class WidgetWithTagsStrict(base):
            __tablename__ = "val011_widget_tags_strict"
            id = Column(Integer, primary_key=True)
            tags = Column(String)

    msg = str(exc_info.value)
    assert "VAL-011" in msg and "tags" in msg


# ---------------------------------------------------------------------------
# (b) silent-override mode (a str-typed NodeMetadata attr, e.g. name) is caught
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_warns_on_name_collision_silent_override_in_warn_mode(base):
    """``name`` collides silently at runtime (the user's value is hijacked into
    node metadata with no error). VAL-011 surfaces it at validation time.
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class WidgetWithName(base):
            __tablename__ = "val011_widget_name_warn"
            id = Column(Integer, primary_key=True)
            name = Column(String)

        assert WidgetWithName is not None
        msgs = _warning_messages(rec)
        assert any(
            "VAL-011" in m and "'name'" in m for m in msgs
        ), f"expected a VAL-011 name collision warning; got {msgs}"


@pytest.mark.regression
@pytest.mark.parametrize("field_name", ["description", "version", "author"])
def test_val011_warns_on_remaining_str_collisions_in_warn_mode(base, field_name):
    """The remaining str-typed NodeMetadata attrs (description / version /
    author) all silent-override and MUST each warn under VAL-011.
    """
    attrs = {
        "__tablename__": f"val011_widget_{field_name}_warn",
        "id": Column(Integer, primary_key=True),
        field_name: Column(String),
    }
    cls = type(f"WidgetWith_{field_name}", (base,), attrs)

    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        model(validation=ValidationMode.WARN)(cls)
        msgs = _warning_messages(rec)
        assert any(
            "VAL-011" in m and f"'{field_name}'" in m for m in msgs
        ), f"expected a VAL-011 {field_name} collision warning; got {msgs}"


# ---------------------------------------------------------------------------
# (c) a legit `id` PK field does NOT trigger VAL-011
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_does_not_fire_for_legit_id_primary_key_warn_mode(base):
    """``id`` is the REQUIRED DataFlow primary-key name (VAL-003). A user ``id``
    field is correct usage, not a footgun — VAL-011 MUST NOT warn on it.
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class WidgetWithIdOnly(base):
            __tablename__ = "val011_widget_id_only"
            id = Column(Integer, primary_key=True)
            title = Column(String)

        assert WidgetWithIdOnly is not None
        msgs = _warning_messages(rec)
        assert not any(
            "VAL-011" in m for m in msgs
        ), f"VAL-011 must not fire for the required id PK; got {msgs}"


@pytest.mark.regression
def test_val011_does_not_raise_for_legit_id_primary_key_strict_mode(base):
    """Even in STRICT mode, a model whose only NodeMetadata-named field is the
    required ``id`` PK MUST NOT raise VAL-011.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("always")

        @model(strict=True)
        class WidgetWithIdOnlyStrict(base):
            __tablename__ = "val011_widget_id_only_strict"
            id = Column(Integer, primary_key=True)
            # Explicit length avoids an unrelated VAL-007 warning; this test is
            # only concerned with the absence of a VAL-011 strict-mode raise.
            title = Column(String(120))

        # No ModelValidationError raised => the decorator returns the class.
        assert WidgetWithIdOnlyStrict is not None


# ---------------------------------------------------------------------------
# (d) created_at is handled by VAL-005 only (no VAL-011 double-warn)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_created_at_is_val005_only_no_val011_double_warn(base):
    """``created_at`` overlaps both ``NodeMetadata`` and ``AUTO_MANAGED_FIELDS``.
    It is owned by VAL-005; VAL-011 explicitly excludes it so the same field is
    not double-warned.
    """
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")

        @model(validation=ValidationMode.WARN)
        class WidgetWithCreatedAt(base):
            __tablename__ = "val011_widget_created_at"
            id = Column(Integer, primary_key=True)
            created_at = Column(String)

        msgs = _warning_messages(rec)
        # VAL-005 owns created_at.
        assert any(
            "VAL-005" in m and "created_at" in m for m in msgs
        ), f"expected VAL-005 to own created_at; got {msgs}"
        # VAL-011 MUST NOT also fire on created_at.
        assert not any(
            "VAL-011" in m for m in msgs
        ), f"VAL-011 must not double-warn created_at (VAL-005 owns it); got {msgs}"


# ---------------------------------------------------------------------------
# OFF mode skips VAL-011 entirely (consistency with the validation-mode contract)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_val011_skipped_in_off_mode(base):
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")

        @model(skip_validation=True)
        class WidgetOff(base):
            __tablename__ = "val011_widget_off"
            id = Column(Integer, primary_key=True)
            tags = Column(String)

        assert WidgetOff is not None
        msgs = _warning_messages(rec)
        assert not any("VAL-011" in m for m in msgs)
