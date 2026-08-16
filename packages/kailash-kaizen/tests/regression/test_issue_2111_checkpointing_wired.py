# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2111 — ``enable_checkpointing=True`` must install a working manager.

``SmartDefaultsManager.create_checkpointing`` imported
``kaizen.memory.checkpoint``, a module that exists nowhere in the source tree.
The ``except ImportError`` therefore fired on EVERY construction, so
``enable_checkpointing=True`` returned ``None``: no state saved, no run
resumable, and the only signal was a log line naming neither the flag that
requested it nor what had stopped working.

The parts were mislocated rather than missing, which is why the disposition is
to WIRE them rather than to make the flag honest by raising (the verdict #2084
reached for the sibling observability flags):

* ``FilesystemStorage`` — ``kaizen.core.autonomy.state.storage``
* ``StateManager``      — ``kaizen.core.autonomy.state.manager``

``StateManager`` is the correct counterpart, not the ``CheckpointManager`` in
``kailash.middleware.gateway``: that one is a tiered gateway cache whose
``storage`` parameter is a ``DiskStorage``, so ``FilesystemStorage`` is not
even type-compatible with it, and it checkpoints gateway requests rather than
agent state.

These tests DRIVE the manager — a non-None return is necessary but not
sufficient, since an object that cannot round-trip a checkpoint is the same
defect wearing a different shape.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from kaizen.agent_config import AgentConfig
from kaizen.smart_defaults import SmartDefaultsManager

pytestmark = pytest.mark.regression


def test_enable_checkpointing_installs_a_manager(tmp_path: Path):
    """The assertion whose absence let this ship (#2111 acceptance)."""
    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_path=str(tmp_path / "ckpt"),
    )
    manager = SmartDefaultsManager().create_checkpointing(config)

    assert manager is not None, (
        "enable_checkpointing=True installed nothing. The flag advertises a "
        "subsystem that is not wired (#2111)."
    )


def test_checkpoint_manager_round_trips_agent_state(tmp_path: Path):
    """Non-None is not enough — the manager must actually persist and reload.

    A manager that cannot round-trip is the advertised-but-unimplemented
    defect again, one layer down, and a test asserting only `is not None`
    would pass against it.
    """
    from kaizen.core.autonomy.state.types import AgentState

    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_path=str(tmp_path / "ckpt"),
    )
    manager = SmartDefaultsManager().create_checkpointing(config)
    assert manager is not None

    state = AgentState(agent_id="agent-2111", step_number=7)
    state.conversation_history = [{"role": "user", "content": "remember me"}]

    checkpoint_id = asyncio.run(manager.storage.save(state))
    restored = asyncio.run(manager.storage.load(checkpoint_id))

    assert restored.agent_id == "agent-2111"
    assert restored.step_number == 7
    assert restored.conversation_history == [{"role": "user", "content": "remember me"}]


def test_checkpoint_path_is_honoured(tmp_path: Path):
    """``checkpoint_path`` was accepted and never used (#2111 acceptance)."""
    target = tmp_path / "nested" / "checkpoints"
    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_path=str(target),
    )
    manager = SmartDefaultsManager().create_checkpointing(config)

    assert manager is not None
    assert target.is_dir(), f"checkpoint_path {target} was not created"
    assert Path(manager.storage.base_dir) == target


def test_checkpoint_interval_maps_to_step_frequency_not_seconds():
    """``AgentConfig.checkpoint_interval`` is ITERATIONS, not seconds.

    ``StateManager`` carries BOTH a ``checkpoint_frequency`` (every N steps)
    and a ``checkpoint_interval`` (every M seconds). The config field shares
    the latter's NAME and the former's MEANING, so a name-to-name wiring would
    silently reinterpret "every 5 iterations" as "every 5 seconds". Pinned
    because nothing else would catch it.
    """
    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_interval=5,
    )
    manager = SmartDefaultsManager().create_checkpointing(config)

    assert manager is not None
    assert manager.checkpoint_frequency == 5
    # And the time-based cadence must stay disabled: the config exposes no
    # seconds knob, so a default would checkpoint on a schedule nobody asked for.
    assert manager.should_checkpoint("a", current_step=0, current_time=1e9) is False


def test_checkpoint_interval_none_means_on_demand_only():
    """``None`` is documented as "checkpoint on demand only"."""
    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_interval=None,
    )
    manager = SmartDefaultsManager().create_checkpointing(config)

    assert manager is not None
    # No step count and no elapsed time may trigger an automatic checkpoint.
    assert (
        manager.should_checkpoint("a", current_step=10_000, current_time=1e9) is False
    )


def test_unwritable_checkpoint_path_warns_and_disables(tmp_path, caplog):
    """Read-only filesystem must not break agent construction (#2101 parity).

    Now reachable for the first time: the mkdir used to sit below a failing
    import, so no OSError could ever be raised from it. Construction must
    degrade to no checkpointing with a warning that names the flag, not
    propagate an OSError out of ``Agent()``.
    """
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    readonly.chmod(0o500)  # r-x: cannot create children

    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_path=str(readonly / "ckpt"),
    )

    try:
        with caplog.at_level("WARNING"):
            manager = SmartDefaultsManager().create_checkpointing(config)
    finally:
        readonly.chmod(0o700)  # restore so tmp_path cleanup can run

    assert manager is None
    assert "enable_checkpointing" in caplog.text, (
        "The warning must name the flag that requested the subsystem, so the "
        "operator knows what to turn off (#2101)."
    )


def test_agent_construction_installs_a_checkpoint_manager(tmp_path, monkeypatch):
    """The end-to-end form named in the #2111 acceptance criteria.

    ``SmartDefaultsManager`` is the unit under repair, but the flag users
    actually set lives on ``Agent``. Asserting only at the manager would leave
    the forwarding untested, which is the seam the defect hid behind for four
    subsystems already.
    """
    monkeypatch.setenv("KAIZEN_ALLOW_KEYLESS_MOCK", "1")
    from kaizen.agent import Agent

    agent = Agent(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        checkpoint_path=str(tmp_path / "ckpt"),
        mcp_servers=[],
    )

    assert agent.checkpoint_manager is not None
    assert Path(agent.checkpoint_manager.storage.base_dir) == tmp_path / "ckpt"


def test_checkpointing_disabled_returns_none():
    """No-false-positive polarity: the off switch must still switch off."""
    config = AgentConfig(
        model="test-model", llm_provider="mock", enable_checkpointing=False
    )
    assert SmartDefaultsManager().create_checkpointing(config) is None


def test_custom_checkpoint_manager_still_overrides():
    """No-false-positive polarity: Layer 3 override must still win."""
    sentinel = object()
    config = AgentConfig(
        model="test-model",
        llm_provider="mock",
        enable_checkpointing=True,
        custom_checkpoint_manager=sentinel,
    )
    assert SmartDefaultsManager().create_checkpointing(config) is sentinel
