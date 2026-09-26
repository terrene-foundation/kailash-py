# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash_ml.rl._lineage``.

Covers spec §5.1 invariants:

* ``RLLineage`` round-trips cleanly through ``to_dict`` + ``from_dict``.
* ``paradigm`` and ``sdk_source`` Literal constraints are enforced
  at runtime via ``__post_init__`` (Literal hints are NOT enforced
  by dataclasses natively — spec §5.1 requires the check).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kailash_ml.rl._lineage import RLLineage


def _make_lineage(**overrides: object) -> RLLineage:
    """Factory for a valid ``RLLineage`` used across tests."""
    defaults = dict(
        run_id="run-001",
        experiment_name="baseline",
        tenant_id="tenant-x",
        base_model_ref="sshleifer/tiny-gpt2",
        reference_model_ref="sshleifer/tiny-gpt2",
        reward_model_ref="OpenAssistant/reward-model-v1",
        dataset_ref="alpaca-v1:rows=100",
        env_spec="text:preferences",
        algorithm="dpo",
        paradigm="rlhf",
        parent_run_id=None,
        sdk_source="kailash-align",
        sdk_version="0.5.0",
        created_at=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return RLLineage(**defaults)  # type: ignore[arg-type]


def test_lineage_roundtrip_via_dict() -> None:
    """``to_dict`` + ``from_dict`` round-trips a lineage unchanged."""
    original = _make_lineage()
    payload = original.to_dict()
    # Round-trip the datetime via ISO-8601 string.
    assert isinstance(payload["created_at"], str)
    restored = RLLineage.from_dict(payload)
    assert restored == original


def test_lineage_to_dict_is_json_compatible() -> None:
    """``to_dict`` output MUST be serializable by ``json.dumps`` without
    a custom encoder (critical for event-bus emission)."""
    import json

    lineage = _make_lineage()
    payload = lineage.to_dict()
    # This raises TypeError if any value is not JSON-compatible.
    encoded = json.dumps(payload)
    assert "run-001" in encoded
    assert "rlhf" in encoded


def test_lineage_paradigm_literal_enforced() -> None:
    """Spec §5.1: ``paradigm`` MUST be one of the 4 enumerated values."""
    with pytest.raises(ValueError, match="paradigm"):
        _make_lineage(paradigm="invalid")


def test_lineage_sdk_source_literal_enforced() -> None:
    """Spec §5.1: ``sdk_source`` MUST be one of the 2 enumerated values."""
    with pytest.raises(ValueError, match="sdk_source"):
        _make_lineage(sdk_source="kailash-rs")


def test_lineage_run_id_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="run_id"):
        _make_lineage(run_id="")


def test_lineage_algorithm_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="algorithm"):
        _make_lineage(algorithm="")


def test_lineage_sdk_version_must_be_non_empty_string() -> None:
    with pytest.raises(ValueError, match="sdk_version"):
        _make_lineage(sdk_version="")


def test_lineage_created_at_must_be_datetime() -> None:
    with pytest.raises(ValueError, match="created_at"):
        _make_lineage(created_at="2026-04-23")  # not a datetime


def test_lineage_is_frozen() -> None:
    """``RLLineage`` is a frozen dataclass — attr assignment blocked."""
    from dataclasses import FrozenInstanceError

    lineage = _make_lineage()
    with pytest.raises(FrozenInstanceError):
        lineage.run_id = "mutated"  # type: ignore[misc]


def test_lineage_optional_fields_default_to_none() -> None:
    """Every optional field accepts ``None`` without complaint."""
    lineage = RLLineage(
        run_id="run-002",
        experiment_name=None,
        tenant_id=None,
        base_model_ref=None,
        reference_model_ref=None,
        reward_model_ref=None,
        dataset_ref=None,
        env_spec=None,
        algorithm="ppo",
        paradigm="on-policy",
        parent_run_id=None,
        sdk_source="kailash-ml",
        sdk_version="1.1.0",
        created_at=datetime.now(timezone.utc),
    )
    assert lineage.experiment_name is None
    assert lineage.base_model_ref is None
    assert lineage.env_spec is None


def test_lineage_from_dict_rejects_non_dict() -> None:
    with pytest.raises(ValueError, match="dict"):
        RLLineage.from_dict("not a dict")  # type: ignore[arg-type]
