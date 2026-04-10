# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for EATP vocabulary documentation (Phase 6, G10).

Covers:
    1. Posture vocabulary: machine-readable descriptions for each TrustPosture
    2. posture_to_eatp: Maps TrustPosture -> EATP vocabulary identifier
    3. posture_from_eatp: Maps EATP vocabulary identifier -> TrustPosture
    4. posture_from_eatp raises ValueError for invalid identifiers
    5. POSTURE_VOCABULARY completeness: every TrustPosture has an entry
    6. POSTURE_VOCABULARY structure: each entry has required keys
    7. Constraint vocabulary: machine-readable descriptions for each ConstraintType
    8. constraint_to_eatp: Maps ConstraintType -> EATP vocabulary identifier
    9. constraint_from_eatp: Maps EATP vocabulary identifier -> ConstraintType
    10. constraint_from_eatp raises ValueError for invalid identifiers
    11. CONSTRAINT_VOCABULARY completeness: every ConstraintType has an entry
    12. Round-trip: posture -> eatp_id -> posture
    13. Round-trip: constraint -> eatp_id -> constraint
    14. Vocabulary IDs follow eatp: prefix convention
"""

from __future__ import annotations

import pytest
from kailash.trust.chain import ConstraintType
from kailash.trust.posture.postures import TrustPosture
from kailash.trust.vocabulary import (
    CONSTRAINT_VOCABULARY,
    POSTURE_VOCABULARY,
    constraint_from_eatp,
    constraint_to_eatp,
    posture_from_eatp,
    posture_to_eatp,
)

# ---------------------------------------------------------------------------
# 1. Posture vocabulary
# ---------------------------------------------------------------------------


class TestPostureVocabulary:
    """POSTURE_VOCABULARY must contain machine-readable descriptions for all postures."""

    def test_every_posture_has_entry(self):
        """Every TrustPosture member must have a vocabulary entry."""
        for posture in TrustPosture:
            assert (
                posture.value in POSTURE_VOCABULARY
            ), f"Missing vocabulary entry for posture: {posture.value}"

    def test_no_extra_entries(self):
        """POSTURE_VOCABULARY must not contain entries for non-existent postures."""
        posture_values = {p.value for p in TrustPosture}
        for key in POSTURE_VOCABULARY:
            assert key in posture_values, f"Unexpected vocabulary entry: {key}"

    def test_entry_has_eatp_id(self):
        """Each entry must have an eatp_id field."""
        for name, entry in POSTURE_VOCABULARY.items():
            assert "eatp_id" in entry, f"Missing eatp_id for posture {name}"
            assert isinstance(entry["eatp_id"], str)

    def test_entry_has_autonomy_level(self):
        """Each entry must have an autonomy_level matching the posture."""
        for posture in TrustPosture:
            entry = POSTURE_VOCABULARY[posture.value]
            assert (
                "autonomy_level" in entry
            ), f"Missing autonomy_level for posture {posture.value}"
            assert entry["autonomy_level"] == posture.autonomy_level

    def test_entry_has_description(self):
        """Each entry must have a non-empty description."""
        for name, entry in POSTURE_VOCABULARY.items():
            assert "description" in entry, f"Missing description for posture {name}"
            assert isinstance(entry["description"], str)
            assert (
                len(entry["description"]) > 0
            ), f"Empty description for posture {name}"

    def test_eatp_ids_follow_prefix_convention(self):
        """All posture eatp_ids must start with 'eatp:posture:'."""
        for name, entry in POSTURE_VOCABULARY.items():
            assert entry["eatp_id"].startswith(
                "eatp:posture:"
            ), f"Invalid eatp_id prefix for posture {name}: {entry['eatp_id']}"


# ---------------------------------------------------------------------------
# 2. posture_to_eatp / posture_from_eatp
# ---------------------------------------------------------------------------


class TestPostureMapping:
    """posture_to_eatp and posture_from_eatp must form a bijection."""

    @pytest.mark.parametrize("posture", list(TrustPosture))
    def test_posture_to_eatp_returns_string(self, posture: TrustPosture):
        result = posture_to_eatp(posture)
        assert isinstance(result, str)
        assert result.startswith("eatp:posture:")

    @pytest.mark.parametrize("posture", list(TrustPosture))
    def test_round_trip_posture(self, posture: TrustPosture):
        """posture -> eatp_id -> posture must return the original posture."""
        eatp_id = posture_to_eatp(posture)
        recovered = posture_from_eatp(eatp_id)
        assert recovered is posture

    def test_posture_from_eatp_invalid_prefix(self):
        """posture_from_eatp must raise ValueError for non-eatp:posture: prefix."""
        with pytest.raises(ValueError, match="Invalid EATP posture identifier"):
            posture_from_eatp("invalid:posture:delegated")

    def test_posture_from_eatp_unknown_posture(self):
        """posture_from_eatp must raise ValueError for unknown posture name."""
        with pytest.raises(ValueError, match="Unknown EATP posture"):
            posture_from_eatp("eatp:posture:nonexistent")

    def test_unique_eatp_ids(self):
        """Each posture must map to a unique eatp_id."""
        ids = [posture_to_eatp(p) for p in TrustPosture]
        assert len(ids) == len(set(ids)), "Duplicate eatp_ids found"

    def test_specific_mappings(self):
        """Verify specific well-known mappings."""
        assert posture_to_eatp(TrustPosture.AUTONOMOUS) == "eatp:posture:autonomous"
        assert posture_to_eatp(TrustPosture.PSEUDO) == "eatp:posture:pseudo"
        assert posture_to_eatp(TrustPosture.SUPERVISED) == "eatp:posture:supervised"
        assert posture_to_eatp(TrustPosture.TOOL) == "eatp:posture:tool"
        assert posture_to_eatp(TrustPosture.DELEGATING) == "eatp:posture:delegating"


# ---------------------------------------------------------------------------
# 3. Constraint vocabulary
# ---------------------------------------------------------------------------


class TestConstraintVocabulary:
    """CONSTRAINT_VOCABULARY must contain machine-readable descriptions for all constraint types."""

    def test_every_constraint_type_has_entry(self):
        """Every ConstraintType member must have a vocabulary entry."""
        for ct in ConstraintType:
            assert (
                ct.value in CONSTRAINT_VOCABULARY
            ), f"Missing vocabulary entry for constraint type: {ct.value}"

    def test_no_extra_entries(self):
        """CONSTRAINT_VOCABULARY must not contain entries for non-existent types."""
        ct_values = {ct.value for ct in ConstraintType}
        for key in CONSTRAINT_VOCABULARY:
            assert key in ct_values, f"Unexpected vocabulary entry: {key}"

    def test_entry_has_eatp_id(self):
        """Each entry must have an eatp_id field."""
        for name, entry in CONSTRAINT_VOCABULARY.items():
            assert "eatp_id" in entry, f"Missing eatp_id for constraint {name}"
            assert isinstance(entry["eatp_id"], str)

    def test_entry_has_description(self):
        """Each entry must have a non-empty description."""
        for name, entry in CONSTRAINT_VOCABULARY.items():
            assert "description" in entry, f"Missing description for constraint {name}"
            assert isinstance(entry["description"], str)
            assert (
                len(entry["description"]) > 0
            ), f"Empty description for constraint {name}"

    def test_entry_has_dimension(self):
        """Each entry must have a dimension field mapping to constraint dimension names."""
        for name, entry in CONSTRAINT_VOCABULARY.items():
            assert "dimension" in entry, f"Missing dimension for constraint {name}"
            assert isinstance(entry["dimension"], str)

    def test_eatp_ids_follow_prefix_convention(self):
        """All constraint eatp_ids must start with 'eatp:constraint:'."""
        for name, entry in CONSTRAINT_VOCABULARY.items():
            assert entry["eatp_id"].startswith(
                "eatp:constraint:"
            ), f"Invalid eatp_id prefix for constraint {name}: {entry['eatp_id']}"


# ---------------------------------------------------------------------------
# 4. constraint_to_eatp / constraint_from_eatp
# ---------------------------------------------------------------------------


class TestConstraintMapping:
    """constraint_to_eatp and constraint_from_eatp must form a bijection."""

    @pytest.mark.parametrize("ct", list(ConstraintType))
    def test_constraint_to_eatp_returns_string(self, ct: ConstraintType):
        result = constraint_to_eatp(ct)
        assert isinstance(result, str)
        assert result.startswith("eatp:constraint:")

    @pytest.mark.parametrize("ct", list(ConstraintType))
    def test_round_trip_constraint(self, ct: ConstraintType):
        """constraint -> eatp_id -> constraint must return the original type."""
        eatp_id = constraint_to_eatp(ct)
        recovered = constraint_from_eatp(eatp_id)
        assert recovered is ct

    def test_constraint_from_eatp_invalid_prefix(self):
        """constraint_from_eatp must raise ValueError for invalid prefix."""
        with pytest.raises(ValueError, match="Invalid EATP constraint identifier"):
            constraint_from_eatp("invalid:constraint:financial")

    def test_constraint_from_eatp_unknown_type(self):
        """constraint_from_eatp must raise ValueError for unknown constraint name."""
        with pytest.raises(ValueError, match="Unknown EATP constraint"):
            constraint_from_eatp("eatp:constraint:nonexistent")

    def test_unique_eatp_ids(self):
        """Each constraint type must map to a unique eatp_id."""
        ids = [constraint_to_eatp(ct) for ct in ConstraintType]
        assert len(ids) == len(set(ids)), "Duplicate eatp_ids found"

    def test_specific_mappings(self):
        """Verify specific well-known mappings."""
        assert (
            constraint_to_eatp(ConstraintType.FINANCIAL) == "eatp:constraint:financial"
        )
        assert constraint_to_eatp(ConstraintType.TEMPORAL) == "eatp:constraint:temporal"
        assert (
            constraint_to_eatp(ConstraintType.REASONING_REQUIRED)
            == "eatp:constraint:reasoning_required"
        )


# ---------------------------------------------------------------------------
# 5. Adapter scope documentation
# ---------------------------------------------------------------------------


class TestAdapterScopeDocumentation:
    """Vocabulary module must document that adapters belong in CARE Platform, not EATP SDK."""

    def test_module_docstring_mentions_adapter_scope(self):
        """The vocabulary module docstring must note adapter modules are out of scope."""
        from kailash.trust import vocabulary

        assert vocabulary.__doc__ is not None
        docstring = vocabulary.__doc__
        assert (
            "adapter" in docstring.lower() or "bridge" in docstring.lower()
        ), "vocabulary module docstring must mention adapter/bridge scope"
