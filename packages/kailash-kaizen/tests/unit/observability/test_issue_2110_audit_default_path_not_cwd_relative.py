"""
#2110 defect 2 -- the DEFAULT audit location must not depend on the caller's CWD.

``AgentConfig.audit_log_path`` defaulted to the RELATIVE ``.kaizen/audit.jsonl``
while ``enable_audit`` defaults ``True``, so a bare ``AgentConfig(model=...)``
wired through ``create_observability`` dropped a ``.kaizen/`` directory into
whatever tree the process was launched from. The harm that actually matters is
not the stray directory: it is that running the same agent from two directories
produces two DISJOINT audit trails, neither of which is the complete record an
auditor asked for. A compliance artifact's whole value is completeness.

The fix anchors only the DEFAULT (XDG state dir, via ``default_audit_path()``).
An EXPLICIT relative path stays relative -- a caller who writes
``audit_log_path="./my.jsonl"`` has chosen CWD-relative semantics and gets them.

No mocks and no dual-read fallback: a fallback that also reads the old location
would reintroduce exactly the fragmentation this issue exists to remove.

Every test here monkeypatches ``XDG_STATE_HOME`` and ``HOME`` to a tmp dir, so
the suite never writes into the developer's real ``~/.local/state``.
"""

from pathlib import Path

import pytest

from kaizen.agent_config import AgentConfig
from kaizen.smart_defaults import SmartDefaultsManager

MODEL = "test-model"
PROVIDER = "ollama"


def test_the_module_under_test_is_this_checkout():
    """
    Guard against the site-packages trap: an installed copy would green this
    whole module while the worktree stayed broken.

    Pinned RELATIVE to this file, never to an absolute worktree path, so the
    guard survives being run from a different checkout.
    """
    package_root = Path(__file__).resolve().parents[3]  # packages/kailash-kaizen
    import kaizen.agent_config as module_under_test

    assert (
        Path(module_under_test.__file__).resolve().is_relative_to(package_root / "src")
    ), (
        f"agent_config resolved to {module_under_test.__file__}, which is "
        f"outside {package_root / 'src'} -- the test is exercising another copy"
    )


@pytest.fixture
def anchored_state_home(tmp_path, monkeypatch):
    """Redirect the XDG state root out of the developer's real home."""
    state_home = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return state_home


def test_default_audit_log_path_is_absolute(anchored_state_home):
    """A default that is not absolute is a default that moves with the process."""
    config = AgentConfig(model=MODEL, llm_provider=PROVIDER)

    assert Path(config.audit_log_path).is_absolute(), (
        f"default audit_log_path is {config.audit_log_path!r}, which is "
        "relative -- it resolves against whatever CWD the process was started in"
    )


def test_default_audit_log_path_ignores_the_cwd(
    anchored_state_home, tmp_path, monkeypatch
):
    """
    THE defect, stated directly: two CWDs must not produce two trails.

    Constructing from two different working directories must yield the SAME
    absolute path. Under the old relative default these differ, which is the
    fragmentation the issue names.
    """
    first_cwd = tmp_path / "checkout-a"
    second_cwd = tmp_path / "checkout-b"
    first_cwd.mkdir()
    second_cwd.mkdir()

    # RESOLVED against the CWD in force at construction, never compared as the
    # raw stored string: the old relative default stores the SAME string in
    # both directories, so a string comparison passes while the two processes
    # write to two different files. That comparison could not fail, and a
    # check that cannot fail is not evidence.
    monkeypatch.chdir(first_cwd)
    from_first = Path(
        AgentConfig(model=MODEL, llm_provider=PROVIDER).audit_log_path
    ).resolve()

    monkeypatch.chdir(second_cwd)
    from_second = Path(
        AgentConfig(model=MODEL, llm_provider=PROVIDER).audit_log_path
    ).resolve()

    assert from_first == from_second, (
        f"audit trail fragments across working directories: {from_first} vs "
        f"{from_second} -- neither file is the complete record"
    )


def test_default_audit_log_path_lands_under_the_xdg_state_home(anchored_state_home):
    """
    The default resolves PER INSTANCE, honouring the environment as it stands
    at construction.

    This is the test that discriminates the chosen design from an
    import-time-evaluated default (``= str(default_audit_path())`` in the class
    body): that form freezes the path at MODULE IMPORT, before this fixture's
    monkeypatch runs, so it would land under the developer's real home and fail
    here.
    """
    config = AgentConfig(model=MODEL, llm_provider=PROVIDER)

    assert Path(config.audit_log_path).is_relative_to(anchored_state_home), (
        f"default audit_log_path {config.audit_log_path!r} is not under the "
        f"configured XDG state home {anchored_state_home}"
    )


def test_wiring_the_default_creates_no_kaizen_directory_in_the_cwd(
    anchored_state_home, tmp_path, monkeypatch
):
    """
    End-to-end: the default-on audit path must leave the working tree untouched.

    ``create_observability`` is what actually opens the file, so the absence
    assertion is made AFTER the subsystem that writes has run -- an absence
    asserted before any writer runs could not have failed.
    """
    working_tree = tmp_path / "someones-repo"
    working_tree.mkdir()
    monkeypatch.chdir(working_tree)

    config = AgentConfig(model=MODEL, llm_provider=PROVIDER)
    assert config.enable_audit is True, "precondition: audit is the default path"

    hook_manager = SmartDefaultsManager().create_observability(config)
    assert "audit_trail_hook" in hook_manager.registered_hook_names(), (
        "precondition: the audit hook must actually be registered, otherwise "
        "the absence assertion below passes because nothing ever wrote"
    )

    assert not (
        working_tree / ".kaizen"
    ).exists(), "a default AgentConfig dropped .kaizen/ into the caller's working tree"
    assert Path(
        config.audit_log_path
    ).exists(), "the audit file was not opened at the anchored default location"


def test_explicit_relative_path_is_still_honoured(
    anchored_state_home, tmp_path, monkeypatch
):
    """
    Only the DEFAULT moves. ``audit_log_path="./my.jsonl"`` means it.

    A caller who writes a relative path has chosen CWD-relative semantics;
    silently anchoring it would be a different defect -- writing somewhere the
    caller did not ask for.
    """
    working_tree = tmp_path / "explicit"
    working_tree.mkdir()
    monkeypatch.chdir(working_tree)

    config = AgentConfig(
        model=MODEL, llm_provider=PROVIDER, audit_log_path="./my.jsonl"
    )

    assert config.audit_log_path == "./my.jsonl", (
        f"an explicitly-supplied relative path was rewritten to "
        f"{config.audit_log_path!r}"
    )

    SmartDefaultsManager().create_observability(config)
    assert (
        working_tree / "my.jsonl"
    ).exists(), "the explicitly-requested relative location was not used"


def test_explicit_absolute_path_is_still_honoured(anchored_state_home, tmp_path):
    """An absolute override must survive untouched."""
    target = tmp_path / "somewhere" / "else.jsonl"

    config = AgentConfig(model=MODEL, llm_provider=PROVIDER, audit_log_path=str(target))

    assert config.audit_log_path == str(target)

    SmartDefaultsManager().create_observability(config)
    assert target.exists(), "the explicitly-requested absolute location was not used"
