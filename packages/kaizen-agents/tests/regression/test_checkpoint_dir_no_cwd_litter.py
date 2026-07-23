"""Regression: autonomous-agent construction must not litter the caller's cwd.

Pins the F-TESTHYG fix: ``BaseAutonomousAgent.__init__`` previously created its
``checkpoint_dir`` (default ``./checkpoints``) unconditionally via ``mkdir`` in
the constructor, so merely *constructing* an agent dropped an empty
``checkpoints/`` directory into the caller's current working directory — even
for agents that never checkpoint (the base run loop persists via
``state_manager``/DataFlow, not this directory). The directory is now created
lazily, on the first checkpoint write.

Behavioral tests (call the code, observe the filesystem) per rules/testing.md —
NOT source-grep. NEVER delete (rules/testing.md § Regression Testing).
"""

import pytest

from kaizen.signatures import InputField, OutputField, Signature
from kaizen_agents.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent


class _TaskSignature(Signature):
    """Minimal signature for constructing an agent under test."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result")


def _make_config() -> AutonomousConfig:
    # Mirrors the construction pattern used across the autonomous unit suite;
    # ollama/local model — no network, no API key, construction never calls out.
    return AutonomousConfig(
        max_cycles=3, llm_provider="ollama", model="llama3.1:8b-instruct-q8_0"
    )


@pytest.mark.regression
def test_construction_does_not_create_checkpoint_dir(tmp_path, monkeypatch):
    """Constructing an agent must NOT create ./checkpoints in the caller's cwd."""
    monkeypatch.chdir(tmp_path)

    BaseAutonomousAgent(config=_make_config(), signature=_TaskSignature())

    assert not (tmp_path / "checkpoints").exists(), (
        "constructing BaseAutonomousAgent created ./checkpoints in the caller's "
        "cwd — the directory must be created lazily on first checkpoint write"
    )


@pytest.mark.regression
def test_checkpoint_write_creates_dir_lazily(tmp_path, monkeypatch):
    """First checkpoint write must create the dir + file (fix is non-breaking)."""
    monkeypatch.chdir(tmp_path)
    agent = BaseAutonomousAgent(config=_make_config(), signature=_TaskSignature())

    assert not (tmp_path / "checkpoints").exists()  # precondition: still absent

    agent._save_checkpoint({"status": "ok"}, cycle_num=1)

    assert (tmp_path / "checkpoints").exists(), "dir must be created on first write"
    assert (
        tmp_path / "checkpoints" / "checkpoint_cycle_001.jsonl"
    ).exists(), "checkpoint file must be written under the lazily-created directory"


@pytest.mark.regression
def test_explicit_checkpoint_dir_also_lazy(tmp_path, monkeypatch):
    """An explicit checkpoint_dir is likewise not created until first write."""
    monkeypatch.chdir(tmp_path)
    cp_dir = tmp_path / "custom_cp"
    agent = BaseAutonomousAgent(
        config=_make_config(), signature=_TaskSignature(), checkpoint_dir=cp_dir
    )

    assert not cp_dir.exists(), "explicit checkpoint_dir must not be eagerly created"

    agent._save_checkpoint({"status": "ok"}, cycle_num=2)

    assert cp_dir.exists(), "explicit checkpoint_dir must be created on first write"
    assert (cp_dir / "checkpoint_cycle_002.jsonl").exists()
