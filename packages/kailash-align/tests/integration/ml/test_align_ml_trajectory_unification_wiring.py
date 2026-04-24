# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 wiring test for the trajectory-unification entry.

Per ``workspaces/kailash-ml-audit/todos/active/W32-kaizen-align-pact-integrations.md``
§32b + ``specs/ml-rl-align-unification.md`` v1.0.0 §5 + §7, this test
exercises the cross-SDK round-trip:

1. Construct a realistic ``AlignmentResult`` from ``kailash_align``.
2. Convert via ``trajectory_from_alignment_run`` → ``RLLineage``
   (kailash-ml type; single-source per spec §7).
3. Round-trip the ``RLLineage`` through its ``to_dict`` / ``from_dict``
   helpers (the W30 cross-SDK serialization surface).
4. Assert the round-tripped lineage is field-for-field equal AND
   carries ``sdk_source="kailash-align"`` + ``paradigm="rlhf"``.

Real ``kailash_align.AlignmentResult`` + real
``kailash_ml.rl.RLLineage`` — zero mocks. Both packages are runtime
dependencies of the other via the ``[rl-bridge]`` extra chain (see
``specs/ml-rl-align-unification.md`` §7) so this test runs any time
kailash-align's test suite does.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.integration


def test_trajectory_round_trips_via_w30_schema() -> None:
    """AlignmentResult → RLLineage → dict → RLLineage equality."""
    from kailash_align.pipeline import AlignmentResult
    from kailash_align.ml import trajectory_from_alignment_run
    from kailash_ml.rl import RLLineage

    # Real AlignmentResult instance — uses the actual dataclass, not a mock
    result = AlignmentResult(
        adapter_name="integration-test-lora",
        adapter_path="/tmp/integration-test-lora",
        adapter_version=None,
        training_metrics={"loss": 0.33, "reward_margin": 0.55},
        experiment_dir="/tmp/exp-integration",
        method="dpo",
    )

    lineage = trajectory_from_alignment_run(result)

    # Spec §5.1 — runtime isinstance check (RLLineage is a @dataclass(frozen=True))
    assert isinstance(lineage, RLLineage)
    # Spec §5.2 — align-produced trajectories always mark sdk_source
    assert lineage.sdk_source == "kailash-align"
    # Every align run is "rlhf" paradigm per spec §5
    assert lineage.paradigm == "rlhf"
    assert lineage.algorithm == "dpo"
    assert lineage.experiment_name == "integration-test-lora"

    # W30 cross-SDK serialization surface (ml-rl-align-unification §5)
    payload = lineage.to_dict()
    assert payload["sdk_source"] == "kailash-align"
    assert payload["paradigm"] == "rlhf"
    assert payload["algorithm"] == "dpo"
    assert "created_at" in payload
    # ISO-8601 representation so it round-trips through JSON without a
    # custom serializer
    assert isinstance(payload["created_at"], str)

    # Round-trip via from_dict rebuilds the exact same lineage
    rebuilt = RLLineage.from_dict(payload)
    assert rebuilt == lineage


def test_trajectory_preserves_tenant_when_supplied_via_hasattr() -> None:
    """When the caller attaches ``tenant_id`` to the run, it flows through."""
    from kailash_align.pipeline import AlignmentResult
    from kailash_align.ml import trajectory_from_alignment_run

    result = AlignmentResult(
        adapter_name="multi-tenant-lora",
        adapter_path="/tmp/mt-lora",
        adapter_version=None,
        training_metrics={},
        experiment_dir="/tmp/mt-exp",
        method="sft",
    )
    # AlignmentResult is a plain dataclass so new attrs attach freely;
    # the conversion helper duck-types this.
    result.tenant_id = "acme-corp"
    result.base_model_id = "sshleifer/tiny-gpt2"

    lineage = trajectory_from_alignment_run(result)
    assert lineage.tenant_id == "acme-corp"
    assert lineage.base_model_ref == "sshleifer/tiny-gpt2"


def test_trajectory_single_source_on_ml_side() -> None:
    """Spec §7: kailash-align MUST NOT define a parallel Trajectory class.

    Protocol-invariant: the return type of ``trajectory_from_alignment_run``
    is the authoritative W30 ``kailash_ml.rl.RLLineage`` dataclass, NOT
    a kailash-align-owned copy. A future refactor that defines
    ``kailash_align.ml.Trajectory`` OR swaps the return type would
    silently violate spec §7 (single source in ml); this assertion is
    the structural defense.
    """
    from kailash_align.pipeline import AlignmentResult
    from kailash_align.ml import trajectory_from_alignment_run
    from kailash_ml.rl import RLLineage

    result = AlignmentResult(
        adapter_name="single-source-check",
        adapter_path="/tmp/ssc",
        adapter_version=None,
        training_metrics={},
        experiment_dir="/tmp/ssc-exp",
        method="orpo",
    )
    lineage = trajectory_from_alignment_run(result)

    # Class identity — same module, same object
    assert type(lineage) is RLLineage
    assert type(lineage).__module__.startswith("kailash_ml.rl")
