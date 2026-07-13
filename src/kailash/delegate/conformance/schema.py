# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Conformance schema for the kailash.delegate composition primitive (S7, #1035).

Mirrors rs ``kailash-delegate-conformance`` (M7-01 + M7-02 substrate) per
``rules/cross-sdk-inspection.md`` Rule 4a (sibling-canonical vendoring).
The schema is **behavioural-only** by design — vectors assert spec-§-numbered
behaviours from a CLOSED taxonomy (:class:`BehaviouralOutcome`), never
engine-internal field values.

Cross-impl agreement is :func:`receipts_agree` over the
:class:`ConformanceReceipt` counts-based protocol — NEVER a field-by-field
engine diff. This matches rs ``ConformanceReceipt`` byte-for-byte and matches
rs's F4 protocol intent: "Naively, 'agree' would mean diffing the two engines'
outputs field-by-field — but that re-introduces the F1 leak (an engine
internal becomes the comparison key)."

A complementary dict-shape comparator :func:`receipts_agree_dict` operates on
ALREADY-SERIALIZED ``RuntimeExecutionResult.to_dict()`` output — engine-callers
serialize via the public ``.to_dict()`` method on the engine, pass the dicts in,
get a structured :class:`ReceiptsAgreeReport` back. Engine classes NEVER cross
the conformance/ Fence-B boundary (``tools/lint-delegate-fences.py`` §42-51 —
``conformance/`` MUST NOT import any ``kailash.delegate.{runtime,dispatch,
trust,audit,posture}`` symbol).

Invariants (5 — within budget per ``rules/autonomous-execution.md`` MUST-1):

1. **Schema vendoring** — :class:`ConformanceVector` / :class:`SpecAnchor` /
   :class:`BehaviouralOutcome` / :class:`ConformanceReceipt` /
   :func:`receipts_agree` byte-shape-match rs ``kailash-delegate-conformance``
   serde encoding.
2. **Fence B preserved** — this module imports ZERO
   ``kailash.delegate.{runtime,dispatch,trust,audit,posture}`` symbols.
3. **Behavioural-only** — :class:`BehaviouralOutcome` is a CLOSED enum;
   vectors structurally cannot smuggle engine internals.
4. **Dict-shape parity contract** — :func:`receipts_agree_dict` excludes
   observation-local timestamp fields AND uses ordered comparison for
   chained data (``audit_chain_entries`` + ``transitions``).
5. **Validating deserialization** — every vector deserialized from JSON
   routes through the same validator (:meth:`ConformanceVector.validate`)
   as in-code construction; malformed vectors fail to deserialize.

Mirrors rs:
- ``crates/kailash-delegate-conformance/src/vectors/mod.rs`` (schema)
- ``crates/kailash-delegate-conformance/src/vectors/catalog.rs`` (vectors)
- ``crates/kailash-delegate-conformance/src/receipt.rs`` (receipt + agree)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from importlib import resources
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "BehaviouralOutcome",
    "ConformanceReceipt",
    "ConformanceVector",
    "ConformanceVectorIntegrityError",
    "ConformanceVectorLoader",
    "ReceiptError",
    "ReceiptsAgreeReport",
    "ReceiptsAgreementError",
    "SchemaError",
    "SpecAnchor",
    "assert_receipts_agree",
    "canonical_vector_set_digest",
    "receipts_agree",
    "receipts_agree_dict",
    "validate_vector_set",
]


# ---------------------------------------------------------------------------
# Errors -- typed, raise-on-malformed (fail-closed)
# ---------------------------------------------------------------------------


class SchemaError(ValueError):
    """A malformed conformance vector (or vector set) was rejected by the
    schema (fail-closed -- a vector that does not validate never enters the
    OSS-bound set).

    Mirrors rs ``SchemaError`` variants: ``InvalidSpecAnchor``,
    ``EmptyField``, ``DuplicateId``. Carries a structured ``kind`` discriminator
    so callers can dispatch on the rs variant without parsing the message.
    """

    def __init__(
        self, message: str, *, kind: str, detail: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.kind = kind
        self.detail = detail or {}


class ReceiptError(ValueError):
    """A malformed :class:`ConformanceReceipt` was rejected (fail-closed).

    Mirrors rs ``ReceiptError`` variants: ``EmptyField``, ``PassedExceedsTotal``.
    """

    def __init__(
        self, message: str, *, kind: str, detail: dict[str, Any] | None = None
    ):
        super().__init__(message)
        self.kind = kind
        self.detail = detail or {}


class ConformanceVectorIntegrityError(ValueError):
    """A vector-set fixture file failed integrity validation on load.

    Raised by :meth:`ConformanceVectorLoader.load_canonical` and
    :meth:`ConformanceVectorLoader.load_from_file` when the on-disk
    fixture's content digest does not match the digest stored in the
    fixture file itself. Tampering with a vector body without updating
    the digest header is fail-closed at load time.
    """


class ReceiptsAgreementError(ValueError):
    """:func:`assert_receipts_agree` raised because two receipts do NOT agree.

    Carries the :class:`ReceiptsAgreeReport` on ``.report`` for the caller
    to inspect mismatches without re-running the comparator.
    """

    def __init__(self, message: str, *, report: ReceiptsAgreeReport):
        super().__init__(message)
        self.report = report


# ---------------------------------------------------------------------------
# SpecAnchor -- mandatory, always-well-formed Delegate-spec § anchor
# Mirrors rs SpecAnchor (vectors/mod.rs §89-153)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SpecAnchor:
    """A Delegate-spec section anchor -- the MANDATORY provenance of a
    conformance vector's asserted behaviour (F1 structural fence #1).

    Stores a dotted-decimal section number WITHOUT the ``§`` glyph
    (e.g. ``"7.3"``, ``"11"``). Constructed only through :meth:`from_str`
    (or, equivalently, via dict-deserialization through the same validator)
    so a ``SpecAnchor`` value is always a well-formed section number.

    Mirrors rs ``SpecAnchor`` (vectors/mod.rs §89-153). Wire shape matches rs
    ``serde(try_from = "String", into = "String")`` — serializes as bare
    section string, NOT as a struct.
    """

    section: str

    def __post_init__(self) -> None:
        # validate at construction; matches rs ``SpecAnchor::new`` semantics.
        _validate_section(self.section)

    @classmethod
    def from_str(cls, section: str) -> SpecAnchor:
        """Construct a spec anchor from a section number.

        The ``§`` glyph is NOT part of the stored value.

        Raises:
            SchemaError: if ``section`` is empty, contains non-digit/non-dot
                characters, or has leading/trailing/doubled dots.
        """
        return cls(section=section)

    def __str__(self) -> str:
        """Render with the ``§`` glyph (e.g. ``§7.3``). Matches rs ``Display``."""
        return f"§{self.section}"

    def to_wire(self) -> str:
        """Serialize as the bare section string -- the form rs ``serde`` round-trips."""
        return self.section


def _validate_section(section: str) -> None:
    """Validates a dotted-decimal Delegate-spec § number.

    Mirrors rs ``validate_section`` (vectors/mod.rs §157-183).

    Raises:
        SchemaError: with ``kind="invalid_spec_anchor"`` on any malformation.
    """
    if not isinstance(section, str):
        raise SchemaError(
            f"spec-§ anchor MUST be a string; got {type(section).__name__}",
            kind="invalid_spec_anchor",
            detail={"section": section},
        )
    if not section:
        raise SchemaError(
            "the spec-§ anchor is empty -- every conformance vector "
            "MUST anchor to a Delegate-spec section number",
            kind="invalid_spec_anchor",
            detail={"section": section},
        )
    if not all(c.isascii() and (c.isdigit() or c == ".") for c in section):
        raise SchemaError(
            f"section {section!r} is not a dotted-decimal number -- a "
            f"spec-§ anchor is ASCII digits with interior dots only "
            f"(e.g. `7.3`), never a prose label or an engine symbol",
            kind="invalid_spec_anchor",
            detail={"section": section},
        )
    if section.startswith(".") or section.endswith(".") or ".." in section:
        raise SchemaError(
            f"section {section!r} has a leading, trailing, or doubled dot -- "
            f"a spec-§ anchor is a well-formed dotted-decimal number",
            kind="invalid_spec_anchor",
            detail={"section": section},
        )


# ---------------------------------------------------------------------------
# BehaviouralOutcome -- CLOSED taxonomy (F1 structural fences #2 + #3)
# Mirrors rs BehaviouralOutcome (vectors/mod.rs §199-209)
# ---------------------------------------------------------------------------


class BehaviouralOutcome(str, Enum):
    """The CLOSED taxonomy of behavioural outcomes a conformance vector may
    assert (F1 structural fences #2 + #3 -- behavioural-only + value-allowlist).

    A conformance vector asserts a spec-§-numbered *behaviour*, never an
    engine-determined *value*. Because this enum is closed, a vector CANNOT
    assert an engine internal -- a literal error-variant name, a tightening
    order, an audit-row cardinality are all unrepresentable. The published
    Delegate-spec behavioural taxonomy IS this enum.

    Mirrors rs ``BehaviouralOutcome`` (vectors/mod.rs §199-209). Wire shape
    matches rs ``serde`` default: PascalCase variant names (``Accept``,
    ``Reject``, ``EscalateToHuman``).
    """

    ACCEPT = "Accept"
    REJECT = "Reject"
    ESCALATE_TO_HUMAN = "EscalateToHuman"

    @classmethod
    def from_wire(cls, value: str) -> BehaviouralOutcome:
        """Construct from rs serde wire string. Raises on unknown variant
        (the value-allowlist enforcement)."""
        for member in cls:
            if member.value == value:
                return member
        raise SchemaError(
            f"unknown BehaviouralOutcome variant {value!r}; allowed: "
            f"{[m.value for m in cls]}",
            kind="unknown_outcome",
            detail={"value": value},
        )


# ---------------------------------------------------------------------------
# ConformanceVector -- spec-§-anchored behavioural assertion
# Mirrors rs ConformanceVector (vectors/mod.rs §211-356)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConformanceVector:
    """A single behavioural conformance vector (F1-fenced; #1035 S7).

    A vector is a spec-§-anchored behavioural assertion: *given* a scenario,
    the runtime MUST exhibit a closed-taxonomy :class:`BehaviouralOutcome`.
    It carries NO engine internals -- the schema makes that structurally
    impossible.

    Mirrors rs ``ConformanceVector`` (vectors/mod.rs §211-356). Wire shape
    matches rs ``serde`` default: a JSON object with keys
    ``{id, spec_anchor, given, behaviour, expected}``.
    """

    id: str
    spec_anchor: SpecAnchor
    given: str
    behaviour: str
    expected: BehaviouralOutcome

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validates this vector against the schema.

        The spec-§ anchor is always well-formed (it is a :class:`SpecAnchor`,
        which has no invalid representation). This method checks the
        remaining contract: ``id``, ``given``, and ``behaviour`` are non-empty.

        Raises:
            SchemaError: for the first empty required field.
        """
        if not isinstance(self.id, str) or not self.id.strip():
            raise SchemaError(
                "conformance vector field 'id' is empty -- a vector id "
                "(e.g. 'DV-7.3-001') so a cross-impl receipt can address the vector",
                kind="empty_field",
                detail={"field": "id"},
            )
        if not isinstance(self.given, str) or not self.given.strip():
            raise SchemaError(
                "conformance vector field 'given' is empty -- the scenario the "
                "vector sets up, in plain spec language",
                kind="empty_field",
                detail={"field": "given"},
            )
        if not isinstance(self.behaviour, str) or not self.behaviour.strip():
            raise SchemaError(
                "conformance vector field 'behaviour' is empty -- the "
                "spec-§-numbered behaviour the runtime MUST exhibit, in "
                "plain spec language",
                kind="empty_field",
                detail={"field": "behaviour"},
            )
        if not isinstance(self.spec_anchor, SpecAnchor):
            raise SchemaError(
                "conformance vector field 'spec_anchor' MUST be a SpecAnchor; "
                f"got {type(self.spec_anchor).__name__}",
                kind="empty_field",
                detail={"field": "spec_anchor"},
            )
        if not isinstance(self.expected, BehaviouralOutcome):
            raise SchemaError(
                "conformance vector field 'expected' MUST be a BehaviouralOutcome; "
                f"got {type(self.expected).__name__}",
                kind="empty_field",
                detail={"field": "expected"},
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-canonical dict matching rs serde encoding.

        Round-trip with :meth:`from_dict` is lossless. Wire shape:

        - ``id``: str
        - ``spec_anchor``: bare section string (e.g. ``"7.3"``)
        - ``given``: str
        - ``behaviour``: str
        - ``expected``: PascalCase outcome string (``"Accept"`` etc.)
        """
        return {
            "id": self.id,
            "spec_anchor": self.spec_anchor.to_wire(),
            "given": self.given,
            "behaviour": self.behaviour,
            "expected": self.expected.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformanceVector:
        """Reconstruct from a :meth:`to_dict` payload.

        Routes through the validating constructor: a hand-edited fixture file
        with an empty required field, malformed spec anchor, or unknown
        outcome variant fails to deserialize.

        Raises:
            SchemaError: on any validation failure.
            TypeError: if ``data`` is not a dict or missing a required key.
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"ConformanceVector.from_dict requires a dict; got {type(data).__name__}"
            )
        required = ("id", "spec_anchor", "given", "behaviour", "expected")
        for key in required:
            if key not in data:
                raise SchemaError(
                    f"ConformanceVector.from_dict missing required field {key!r}",
                    kind="empty_field",
                    detail={"field": key},
                )
        spec_anchor = SpecAnchor.from_str(data["spec_anchor"])
        expected = BehaviouralOutcome.from_wire(data["expected"])
        return cls(
            id=data["id"],
            spec_anchor=spec_anchor,
            given=data["given"],
            behaviour=data["behaviour"],
            expected=expected,
        )


def validate_vector_set(vectors: list[ConformanceVector]) -> None:
    """Validates a full conformance-vector SET -- every vector individually
    valid AND all ids unique.

    Mirrors rs ``validate_vector_set`` (vectors/mod.rs §369-380). This is the
    in-session feedback loop: a vector set that does not pass this MUST NOT
    enter the OSS-bound mirror.

    Raises:
        SchemaError: with ``kind="empty_field"`` for the first vector with
            an empty field; ``kind="duplicate_id"`` for the first repeated id.
    """
    if not isinstance(vectors, (list, tuple)):
        raise SchemaError(
            f"validate_vector_set requires a list/tuple; got {type(vectors).__name__}",
            kind="invalid_argument",
            detail={"type": type(vectors).__name__},
        )
    seen: set[str] = set()
    for vector in vectors:
        if not isinstance(vector, ConformanceVector):
            raise SchemaError(
                "validate_vector_set entries MUST be ConformanceVector; got "
                f"{type(vector).__name__}",
                kind="invalid_argument",
                detail={"type": type(vector).__name__},
            )
        vector.validate()
        if vector.id in seen:
            raise SchemaError(
                f"duplicate conformance vector id {vector.id!r} -- vector ids "
                f"MUST be unique within a set",
                kind="duplicate_id",
                detail={"id": vector.id},
            )
        seen.add(vector.id)


# ---------------------------------------------------------------------------
# Canonical vector-set integrity digest (tamper-evident fixture loading)
# ---------------------------------------------------------------------------


def _canonical_json_bytes(obj: Any) -> bytes:
    """Deterministic JSON encoding for digest computation.

    Sorted keys, no whitespace, UTF-8 bytes. Matches the
    ``kailash.trust._json.canonical_json_dumps`` convention without
    importing it (Fence B keeps conformance/ engine-free, and trust/ is
    not on the Fence B blocklist BUT we minimize cross-package imports
    so the OSS mirror has the narrowest possible boundary).
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_vector_set_digest(vectors: list[ConformanceVector]) -> str:
    """SHA-256 hex digest over the canonical-JSON serialization of the
    vector set (ordered as given).

    The digest stored in the fixture file's ``digest`` field IS this
    function's output over ``vectors``. :meth:`ConformanceVectorLoader`
    methods re-compute and compare on load; mismatch raises
    :class:`ConformanceVectorIntegrityError`.

    Args:
        vectors: ordered list of vectors. Order matters for the digest;
            re-ordering produces a different digest by design.
    """
    payload = [v.to_dict() for v in vectors]
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


# ---------------------------------------------------------------------------
# ConformanceVectorLoader -- tamper-evident fixture loading
# ---------------------------------------------------------------------------


# The canonical conformance vectors ship as PACKAGE DATA inside the installed
# wheel (``src/kailash/delegate/conformance/data/canonical.json``) so
# :meth:`ConformanceVectorLoader.load_canonical` resolves them via
# ``importlib.resources`` for every consumer -- source checkout AND
# ``pip install``ed wheel alike (#1532 RC1). Reading the resource as TEXT (not a
# filesystem path) keeps resolution zip-safe. Only stdlib is used, so the loader
# stays engine-free (Fence B).
_CANONICAL_PACKAGE = "kailash.delegate.conformance"
_CANONICAL_RESOURCE = "data/canonical.json"

# Legacy repo-root-relative location, retained ONLY for the explicit
# ``load_canonical(root=...)`` override (a caller pointing at a source tree or a
# vendored copy). The default (``root=None``) path is the packaged resource
# above -- NOT this path -- because a wheel install ships no ``tests/`` tree.
_CANONICAL_REL_PATH = "tests/fixtures/delegate-conformance/canonical.json"


class ConformanceVectorLoader:
    """Tamper-evident loader for conformance vector fixtures.

    Reads JSON fixtures of shape::

        {
          "schema_version": 1,
          "digest": "<sha256 hex over vectors>",
          "vectors": [<ConformanceVector.to_dict()>, ...]
        }

    On load, re-computes :func:`canonical_vector_set_digest` over the
    deserialized vectors and compares with the stored ``digest``. Mismatch
    raises :class:`ConformanceVectorIntegrityError` (the fixture file
    itself is tamper-evident; editing a vector body without re-computing
    the digest fails at load time).

    Vectors are also validated via :func:`validate_vector_set` -- duplicate
    ids, empty required fields, malformed spec anchors, and unknown outcome
    variants all fail-closed at load.
    """

    SCHEMA_VERSION = 1

    @classmethod
    def load_from_file(cls, path: str | Path) -> tuple[ConformanceVector, ...]:
        """Load + validate + integrity-check a vector-set fixture file.

        Returns:
            Tuple of validated :class:`ConformanceVector` instances in the
            order the fixture defined.

        Raises:
            ConformanceVectorIntegrityError: digest mismatch (tamper).
            SchemaError: malformed vector / duplicate id.
            FileNotFoundError: fixture missing.
            ValueError: malformed JSON or wrong schema_version.
        """
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        return cls._load_from_text(text, source=str(p))

    @classmethod
    def _load_from_text(
        cls, text: str, *, source: str
    ) -> tuple[ConformanceVector, ...]:
        """Parse + validate + integrity-check a vector set from raw JSON text.

        ``source`` labels the origin (a filesystem path or a packaged-resource
        name) in error messages. Shared by :meth:`load_from_file` (filesystem)
        and :meth:`load_canonical` (packaged resource) so BOTH paths enforce the
        identical schema-version + digest-integrity + validation contract.
        """
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"conformance fixture {source} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"conformance fixture {source} top-level MUST be an object; got "
                f"{type(payload).__name__}"
            )
        schema_version = payload.get("schema_version")
        if schema_version != cls.SCHEMA_VERSION:
            raise ValueError(
                f"conformance fixture {source} schema_version {schema_version!r} "
                f"does not match loader version {cls.SCHEMA_VERSION}"
            )
        stored_digest = payload.get("digest")
        if not isinstance(stored_digest, str) or not stored_digest:
            raise ValueError(
                f"conformance fixture {source} missing or empty 'digest' field"
            )
        raw_vectors = payload.get("vectors")
        if not isinstance(raw_vectors, list):
            raise ValueError(
                f"conformance fixture {source} 'vectors' MUST be a list; got "
                f"{type(raw_vectors).__name__}"
            )
        vectors = [ConformanceVector.from_dict(rv) for rv in raw_vectors]
        validate_vector_set(vectors)
        computed = canonical_vector_set_digest(vectors)
        if computed != stored_digest:
            raise ConformanceVectorIntegrityError(
                f"conformance fixture {source} integrity check failed -- stored "
                f"digest {stored_digest!r} != computed {computed!r}. The fixture "
                f"was modified without updating the digest header; either "
                f"re-compute the digest via canonical_vector_set_digest() or "
                f"investigate the tamper."
            )
        return tuple(vectors)

    @classmethod
    def load_canonical(
        cls, root: str | Path | None = None
    ) -> tuple[ConformanceVector, ...]:
        """Load the canonical OSS conformance vector set.

        The vectors ship as package data inside the installed wheel, so the
        default (``root=None``) resolves them via ``importlib.resources`` and
        works identically from a source checkout AND a ``pip install``ed wheel
        (#1532 RC1 -- previously this walked up from ``__file__`` for a
        ``tests/`` fixture, which raised ``FileNotFoundError`` for every
        wheel-installed consumer, forcing downstream connectors to hand-roll a
        parent-directory-ascent loader).

        Args:
            root: optional override. When given, the loader reads
                ``<root>/canonical.json`` (a vendored copy) or, failing that,
                ``<root>/tests/fixtures/delegate-conformance/canonical.json``
                (a legacy source tree). When ``None`` (default), the packaged
                resource is used.

        Returns:
            Tuple of validated canonical vectors.

        Raises:
            FileNotFoundError: if the canonical fixture cannot be located.
            ConformanceVectorIntegrityError: digest mismatch.
            SchemaError: malformed vector / duplicate id.
        """
        if root is None:
            try:
                text = (
                    resources.files(_CANONICAL_PACKAGE)
                    .joinpath(_CANONICAL_RESOURCE)
                    .read_text(encoding="utf-8")
                )
            except (FileNotFoundError, ModuleNotFoundError) as exc:
                raise FileNotFoundError(
                    f"canonical conformance vectors not found as package data "
                    f"'{_CANONICAL_PACKAGE}/{_CANONICAL_RESOURCE}'; the wheel was "
                    f"built without the conformance data file (see pyproject.toml "
                    f"[tool.setuptools.package-data])."
                ) from exc
            return cls._load_from_text(
                text, source=f"{_CANONICAL_PACKAGE}/{_CANONICAL_RESOURCE}"
            )

        base = Path(root)
        for candidate in (base / "canonical.json", base / _CANONICAL_REL_PATH):
            if candidate.is_file():
                return cls.load_from_file(candidate)
        raise FileNotFoundError(
            f"canonical conformance fixture not found under root {base!r} "
            f"(looked for 'canonical.json' and '{_CANONICAL_REL_PATH}')"
        )


# ---------------------------------------------------------------------------
# ConformanceReceipt -- F4 cross-impl receipt protocol
# Mirrors rs ConformanceReceipt (receipt.rs §67-158)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConformanceReceipt:
    """A cross-impl conformance-run receipt (F4; #1035 S7).

    One implementation's durable record of a single conformance run: which
    vector-set (crate version + commit SHA), how many vectors it ran, and
    how many passed. Cross-impl agreement is :func:`receipts_agree` applied
    to two receipts -- NEVER a field-by-field engine diff.

    Mirrors rs ``ConformanceReceipt`` (receipt.rs §67-158). Wire shape matches
    rs ``serde`` default: JSON object with keys ``{implementation,
    vector_crate_version, commit_sha, vectors_total, vectors_passed}``.
    """

    implementation: str
    vector_crate_version: str
    commit_sha: str
    vectors_total: int
    vectors_passed: int

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validates: three identity fields non-empty, ``vectors_passed`` does
        not exceed ``vectors_total``.

        Raises:
            ReceiptError: with ``kind="empty_field"`` or ``kind="passed_exceeds_total"``.
        """
        for field_name, value in (
            ("implementation", self.implementation),
            ("vector_crate_version", self.vector_crate_version),
            ("commit_sha", self.commit_sha),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ReceiptError(
                    f"conformance receipt field {field_name!r} is empty",
                    kind="empty_field",
                    detail={"field": field_name},
                )
        if not isinstance(self.vectors_total, int) or self.vectors_total < 0:
            raise ReceiptError(
                f"conformance receipt 'vectors_total' MUST be a non-negative int; "
                f"got {self.vectors_total!r}",
                kind="invalid_count",
                detail={"field": "vectors_total", "value": self.vectors_total},
            )
        if not isinstance(self.vectors_passed, int) or self.vectors_passed < 0:
            raise ReceiptError(
                f"conformance receipt 'vectors_passed' MUST be a non-negative int; "
                f"got {self.vectors_passed!r}",
                kind="invalid_count",
                detail={"field": "vectors_passed", "value": self.vectors_passed},
            )
        if self.vectors_passed > self.vectors_total:
            raise ReceiptError(
                f"conformance receipt claims {self.vectors_passed} vectors passed "
                f"but only {self.vectors_total} were run -- a receipt cannot pass "
                f"more vectors than it executed",
                kind="passed_exceeds_total",
                detail={
                    "passed": self.vectors_passed,
                    "total": self.vectors_total,
                },
            )

    def conforms(self) -> bool:
        """True iff the run conformed -- executed at least one vector AND
        every vector passed."""
        return self.vectors_total > 0 and self.vectors_passed == self.vectors_total

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-canonical dict (rs serde wire shape)."""
        return {
            "implementation": self.implementation,
            "vector_crate_version": self.vector_crate_version,
            "commit_sha": self.commit_sha,
            "vectors_total": self.vectors_total,
            "vectors_passed": self.vectors_passed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConformanceReceipt:
        """Reconstruct from a :meth:`to_dict` payload.

        Routes through validating constructor; a hand-edited receipt with
        ``passed > total`` fails to deserialize.

        Raises:
            ReceiptError: on any validation failure.
            TypeError: if ``data`` is not a dict or missing a required key.
        """
        if not isinstance(data, dict):
            raise TypeError(
                f"ConformanceReceipt.from_dict requires a dict; got {type(data).__name__}"
            )
        for key in (
            "implementation",
            "vector_crate_version",
            "commit_sha",
            "vectors_total",
            "vectors_passed",
        ):
            if key not in data:
                raise ReceiptError(
                    f"ConformanceReceipt.from_dict missing required field {key!r}",
                    kind="empty_field",
                    detail={"field": key},
                )
        return cls(
            implementation=data["implementation"],
            vector_crate_version=data["vector_crate_version"],
            commit_sha=data["commit_sha"],
            vectors_total=data["vectors_total"],
            vectors_passed=data["vectors_passed"],
        )


def receipts_agree(a: ConformanceReceipt, b: ConformanceReceipt) -> bool:
    """Whether two conformance receipts AGREE (the F4 cross-impl agreement check).

    Mirrors rs ``receipts_agree`` (receipt.rs §215-221) byte-for-byte semantics.

    Two receipts agree iff ALL of:

    - they come from DISTINCT implementations
      (``a.implementation != b.implementation``);
    - they name the SAME vector-set -- identical ``vector_crate_version`` AND
      identical ``commit_sha``;
    - both runs conformed (:meth:`ConformanceReceipt.conforms`).

    This is a verifiable cross-reference, NEVER a field-by-field engine
    diff: agreement is a function of the implementations' identities, the
    pinned version + SHA, and the pass counts -- never of any
    engine-internal value.
    """
    return (
        a.implementation != b.implementation
        and a.vector_crate_version == b.vector_crate_version
        and a.commit_sha == b.commit_sha
        and a.conforms()
        and b.conforms()
    )


# ---------------------------------------------------------------------------
# Dict-shape parity comparator (Python-OSS-only extension; Fence B intact)
# ---------------------------------------------------------------------------


# Observation-local fields that do NOT participate in cross-impl byte-shape
# comparison. Two impls executing the same scenario will produce different
# wall-clock timestamps; excluding them keeps the comparator stable.
_DEFAULT_EXCLUDE_FIELDS: frozenset[str] = frozenset(
    {
        "terminated_at",
        "executed_at",
        "started_at",
        "signed_at",
    }
)


@dataclass(frozen=True, slots=True)
class ReceiptsAgreeReport:
    """Structured report from :func:`receipts_agree_dict`.

    Attributes:
        agree: True iff the two dicts agree on all non-excluded fields.
        mismatches: ordered tuple of dotted field paths that differ.
        mismatch_details: dict mapping field path -> ``(a_value, b_value)``
            tuple for human-readable inspection.
        excluded_fields: the fields excluded from comparison (default
            timestamps + caller-supplied).
    """

    agree: bool
    mismatches: tuple[str, ...]
    mismatch_details: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    excluded_fields: frozenset[str] = field(default_factory=frozenset)


def receipts_agree_dict(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    exclude_fields: frozenset[str] | None = None,
) -> ReceiptsAgreeReport:
    """Compare two ``RuntimeExecutionResult.to_dict()`` outputs for byte-shape
    parity.

    Operates on ALREADY-SERIALIZED dicts -- engine-callers serialize via
    ``.to_dict()`` on the runtime engine class (which lives in
    ``kailash.delegate.runtime``, OUTSIDE conformance/); the dict crosses the
    Fence-B boundary, the engine class never does.

    Comparison rules:

    - Observation-local fields in ``exclude_fields`` (default:
      ``{terminated_at, executed_at, started_at, signed_at}``) are skipped
      at ANY nesting depth.
    - Lists / tuples are compared element-by-element AS ORDERED sequences.
      ``audit_chain_entries`` and ``transitions`` are ordered chains; a
      set-comparison would mask reorder bugs.
    - Nested dicts recurse with the same exclusion set.
    - Scalar values compare by equality.

    Args:
        a: first dict (e.g. rs ``RuntimeExecutionResult.to_dict()``).
        b: second dict (e.g. py ``RuntimeExecutionResult.to_dict()``).
        exclude_fields: optional override of timestamp exclusions; default
            covers all known observation-local fields. Caller-supplied set
            UNIONs with the default to avoid accidentally re-enabling
            timestamp comparison.

    Returns:
        :class:`ReceiptsAgreeReport` -- ``agree=True`` iff all non-excluded
        fields are equal.
    """
    if exclude_fields is None:
        excluded = _DEFAULT_EXCLUDE_FIELDS
    else:
        # Union with defaults: callers can ADD exclusions but cannot
        # accidentally re-enable timestamp comparison.
        excluded = _DEFAULT_EXCLUDE_FIELDS | frozenset(exclude_fields)

    mismatches: list[str] = []
    details: dict[str, tuple[Any, Any]] = {}
    _compare(a, b, path="", excluded=excluded, mismatches=mismatches, details=details)
    return ReceiptsAgreeReport(
        agree=not mismatches,
        mismatches=tuple(mismatches),
        mismatch_details=details,
        excluded_fields=excluded,
    )


def _compare(
    a: Any,
    b: Any,
    *,
    path: str,
    excluded: frozenset[str],
    mismatches: list[str],
    details: dict[str, tuple[Any, Any]],
) -> None:
    """Recursive byte-shape comparator. Internal helper for
    :func:`receipts_agree_dict`."""
    if isinstance(a, dict) and isinstance(b, dict):
        keys_a = set(a.keys())
        keys_b = set(b.keys())
        if keys_a != keys_b:
            # Filter out excluded keys from the divergence report.
            divergent_keys = (keys_a ^ keys_b) - excluded
            if divergent_keys:
                key_path = f"{path}.<keys>" if path else "<keys>"
                mismatches.append(key_path)
                details[key_path] = (sorted(keys_a), sorted(keys_b))
        for key in sorted(keys_a & keys_b):
            if key in excluded:
                continue
            child_path = f"{path}.{key}" if path else key
            _compare(
                a[key],
                b[key],
                path=child_path,
                excluded=excluded,
                mismatches=mismatches,
                details=details,
            )
        return
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        if len(a) != len(b):
            mismatches.append(path)
            details[path] = (a, b)
            return
        for idx, (ai, bi) in enumerate(zip(a, b)):
            child_path = f"{path}[{idx}]"
            _compare(
                ai,
                bi,
                path=child_path,
                excluded=excluded,
                mismatches=mismatches,
                details=details,
            )
        return
    if type(a) is not type(b) or a != b:
        mismatches.append(path)
        details[path] = (a, b)


def assert_receipts_agree(
    a: dict[str, Any],
    b: dict[str, Any],
    *,
    exclude_fields: frozenset[str] | None = None,
) -> None:
    """Raise :class:`ReceiptsAgreementError` if :func:`receipts_agree_dict`
    reports disagreement.

    Convenience for test code that wants a typed exception with the report
    attached rather than asserting on ``agree`` manually.
    """
    report = receipts_agree_dict(a, b, exclude_fields=exclude_fields)
    if not report.agree:
        raise ReceiptsAgreementError(
            f"receipts_agree_dict disagreed on {len(report.mismatches)} field(s): "
            f"{list(report.mismatches)}",
            report=report,
        )
