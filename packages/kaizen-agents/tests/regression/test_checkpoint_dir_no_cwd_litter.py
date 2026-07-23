"""Regression: autonomous-agent checkpoints never litter the caller's cwd.

Pins two related fixes:

- **0.11.8** — ``BaseAutonomousAgent.__init__`` no longer creates its
  ``checkpoint_dir`` eagerly (construction has no filesystem side effect; the
  directory is created lazily on the first checkpoint write).
- **0.12.0** — the DEFAULT checkpoint location is a per-user state directory
  (``platformdirs.user_state_dir("kaizen")/checkpoints``), NOT ``./checkpoints``
  in the current working directory; the directory/files are created with
  owner-only permissions (``0o700``/``0o600``) on POSIX.

Behavioral tests (call the code, observe the filesystem) per rules/testing.md —
NOT source-grep. Write-triggering tests use an EXPLICIT tmp ``checkpoint_dir`` so
they never write into the real per-user state directory. NEVER delete.
"""

import os
import stat

import platformdirs
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
def test_construction_creates_no_dir_and_default_is_off_cwd(tmp_path, monkeypatch):
    """Constructing an agent creates nothing, and the default dir is NOT cwd."""
    monkeypatch.chdir(tmp_path)

    agent = BaseAutonomousAgent(config=_make_config(), signature=_TaskSignature())

    # 0.11.8: no eager creation anywhere.
    assert not (tmp_path / "checkpoints").exists()
    # 0.12.0: the default resolves off the cwd, under the per-user state dir.
    assert not str(agent.checkpoint_dir).startswith(str(tmp_path))
    assert agent.checkpoint_dir.is_absolute()


@pytest.mark.regression
def test_default_location_is_user_state_dir(tmp_path, monkeypatch):
    """The default checkpoint dir is platformdirs' per-user state location."""
    monkeypatch.chdir(tmp_path)
    agent = BaseAutonomousAgent(config=_make_config(), signature=_TaskSignature())

    expected_root = platformdirs.user_state_dir("kaizen")
    assert str(agent.checkpoint_dir).startswith(expected_root)
    assert agent.checkpoint_dir.name == "checkpoints"


@pytest.mark.regression
def test_explicit_checkpoint_dir_lazy_and_owner_only(tmp_path):
    """Explicit dir: not created on construction; on first write dir+file exist,
    owner-only on POSIX (0o700 dir / 0o600 file)."""
    cp_dir = tmp_path / "custom_cp"
    agent = BaseAutonomousAgent(
        config=_make_config(),
        signature=_TaskSignature(),
        checkpoint_dir=cp_dir,
    )

    assert not cp_dir.exists()  # construction must not create it

    agent._save_checkpoint({"status": "ok"}, cycle_num=2)

    cp_file = cp_dir / "checkpoint_cycle_002.jsonl"
    assert cp_dir.exists()
    assert cp_file.exists()

    if os.name == "posix":
        assert stat.S_IMODE(cp_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(cp_file.stat().st_mode) == 0o600


@pytest.mark.regression
@pytest.mark.skipif(os.name != "posix", reason="O_NOFOLLOW/symlinks are POSIX-only")
def test_checkpoint_write_refuses_symlink_at_leaf(tmp_path):
    """A symlink pre-placed at the checkpoint file path must NOT be written
    through (O_NOFOLLOW sink hardening, security.md § Path Containment)."""
    cp_dir = tmp_path / "cp"
    cp_dir.mkdir()
    target = tmp_path / "victim.txt"
    target.write_text("original", encoding="utf-8")
    # Attacker pre-places a symlink where cycle-3's checkpoint file would land.
    (cp_dir / "checkpoint_cycle_003.jsonl").symlink_to(target)

    agent = BaseAutonomousAgent(
        config=_make_config(), signature=_TaskSignature(), checkpoint_dir=cp_dir
    )
    # _save_checkpoint swallows the write failure (logs a warning); the point is
    # the victim target is NOT appended to through the symlink.
    agent._save_checkpoint({"status": "ok"}, cycle_num=3)

    assert target.read_text(encoding="utf-8") == "original", (
        "checkpoint write followed a symlink and corrupted the target — "
        "O_NOFOLLOW must refuse the write"
    )
