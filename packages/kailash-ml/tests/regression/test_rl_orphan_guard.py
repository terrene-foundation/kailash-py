# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression guard — RL + Agents orphan pattern (2026-04-17 redteam).

The 5-agent audit at `workspaces/kailash-ml-audit/analysis/
00-synthesis-redesign-proposal.md` §§ 3.1, 5.4 flagged `kailash_ml.rl`
and `kailash_ml.agents` as orphan-shaped subpackages: they expose
manager-shape classes (`RLTrainer`, `EnvironmentRegistry`,
`PolicyRegistry`, `*Agent`) that have zero production call sites
inside `kailash_ml.engines.*` and are not surfaced at `km.*`. This is
the same failure pattern `rules/orphan-detection.md` §§ 1-3 codifies
after the kailash-py Phase 5.11 trust-executor incident.

Until Phase 6 wires these (see redesign proposal §9 Phase 6), this
file pins the orphan state so the next session cannot silently "fix"
it by surfacing a class without wiring its production call site. When
Phase 6 wires `km.rl.Engine` through `MLEngine`/`FeatureStore`/
`ModelRegistry`/`ExperimentTracker`, these tests MUST be updated or
replaced with wiring-assertion tests per `rules/facade-manager-
detection.md` § 1.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "kailash_ml"


def _iter_engine_sources():
    root = SRC_ROOT / "engines"
    for path in root.rglob("*.py"):
        if path.name.startswith("_") and path.name not in {
            "_shared.py",
            "_feature_sql.py",
            "_guardrails.py",
            "_data_explorer_report.py",
        }:
            continue
        yield path


@pytest.mark.regression
class TestRLOrphanState:
    """Pin the current orphan state; flip to wiring tests at Phase 6."""

    def test_rl_trainer_has_zero_engine_call_sites(self):
        """`RLTrainer` MUST have zero imports inside `engines/*`.

        Flipping this test to asserting a call site is the signal that
        the RL engine has been wired per redesign proposal §9 Phase 6.
        Until then, the orphan state is pinned so a future session that
        imports `RLTrainer` from an engine without wiring the hot path
        will fail this test — forcing the wiring question to the PR
        review.
        """
        offenders: list[str] = []
        for path in _iter_engine_sources():
            src = path.read_text()
            if "RLTrainer" in src or "from kailash_ml.rl" in src:
                offenders.append(str(path.relative_to(SRC_ROOT.parent)))
        assert not offenders, (
            "RLTrainer is now referenced from engines/ "
            f"({offenders}). If this is a Phase 6 wire-up, replace this "
            "test with a Tier 2 wiring assertion per "
            "rules/facade-manager-detection.md § 1."
        )

    def test_agents_have_zero_engine_call_sites(self):
        """Same contract for the `agents/` subpackage."""
        offenders: list[str] = []
        for path in _iter_engine_sources():
            src = path.read_text()
            if "from kailash_ml.agents" in src or "kailash_ml.agents." in src:
                offenders.append(str(path.relative_to(SRC_ROOT.parent)))
        assert not offenders, (
            "kailash_ml.agents is now referenced from engines/ "
            f"({offenders}). Replace this test with a wiring assertion."
        )

    def test_km_top_level_does_not_expose_rl_or_agents(self):
        """Top-level `kailash_ml.__init__` MUST NOT re-export `rl` or
        `agents` until the wiring lands (redesign proposal §§ 3.1,
        5.4). When it does, swap this test for a positive assertion.
        """
        init = (SRC_ROOT / "__init__.py").read_text()
        # Allow `import kailash_ml.rl` from tests / users who opt in
        # directly; the assertion is only that the top-level __init__
        # does not advertise the orphan.
        assert "\"rl\"" not in init or '"rl":' in init, (
            "kailash_ml.__init__.__all__ appears to export 'rl'; if the "
            "wiring landed, update this test with a wiring assertion."
        )
        assert "\"agents\"" not in init or '"agents":' in init, (
            "kailash_ml.__init__.__all__ appears to export 'agents'; if "
            "the wiring landed, update this test with a wiring "
            "assertion."
        )

    def test_rl_trainer_does_not_use_backend_resolver(self):
        """Pin the current reality: RL does not consult
        `detect_backend()`. This is a HIGH finding (redteam 2026-04-17)
        that Phase 6 MUST fix. The test keeps the gap visible instead of
        letting it rot silently.

        When RL is wired into the resolver, this test flips to assert
        that `detect_backend` IS imported — the shape flips from
        "pinning the gap" to "guarding the fix".
        """
        rl_dir = SRC_ROOT / "rl"
        for path in rl_dir.rglob("*.py"):
            src = path.read_text()
            if "detect_backend" in src or "BackendInfo" in src:
                pytest.fail(
                    f"{path.name} now imports the backend resolver — "
                    "flip this test to assert Tier 2 wiring per "
                    "rules/facade-manager-detection.md § 1."
                )
