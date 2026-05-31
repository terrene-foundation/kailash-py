# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #855 — persistent/learning memory shortcuts.

Issue #855 had two coupled defects:

1. **Crash (confirmed user-facing):** ``Agent(memory="persistent")`` and
   ``Agent(memory="learning")`` raised
   ``TypeError: unexpected keyword argument 'storage_path'`` because the shortcut
   factories passed ``storage_path=`` / ``enable_*=`` kwargs that
   ``HierarchicalMemory.__init__`` does not accept.

2. **Warm-tier persistence:** the DataFlow warm backend stored the tag list in a
   column named ``tags``, which collides with the core SDK's reserved
   ``NodeMetadata.tags`` (``set[str]``) and failed CreateNode validation. The
   column was renamed to ``tag_list``.

``test_memory_shortcut_constructs_without_crash`` pins defect (1) and runs in any
environment (the crash was about kwargs, independent of DataFlow). The warm-tier
round-trip pins defect (2) and requires DataFlow (skipped when unavailable, since
``kaizen-agents`` does not declare ``kailash-dataflow`` as a hard dependency — the
warm tier is an optional capability that degrades to hot-tier-only with a warning).
"""

from __future__ import annotations

import pytest

from kaizen.memory.providers.types import MemoryEntry
from kaizen_agents.api.shortcuts import _safe_sqlite_dsn, resolve_memory_shortcut


@pytest.mark.regression
@pytest.mark.parametrize("bad", ["x?mode=ro", "x#frag", "x\x00y"])
def test_safe_sqlite_dsn_rejects_uri_metacharacters(tmp_path, bad):
    """?, #, and null bytes must be rejected (they corrupt the SQLite URI, #855).

    Pins the security invariant so a future refactor that drops the validation —
    or a switch to SQLite ``file:`` URI mode where ``?mode=ro`` would be honored —
    fails loudly instead of silently re-opening URI parameter injection.
    """
    with pytest.raises(ValueError, match="must not contain"):
        _safe_sqlite_dsn(str(tmp_path / bad))


@pytest.mark.regression
def test_safe_sqlite_dsn_emits_4slash_absolute_form(tmp_path):
    """Output is the 4-slash absolute DSN DataFlow requires, free of ?/# (#855)."""
    dsn = _safe_sqlite_dsn(str(tmp_path / "mem"))
    assert dsn.startswith("sqlite:////")
    assert "?" not in dsn and "#" not in dsn
    # Exactly four leading slashes after the scheme (absolute path, not relative).
    assert dsn[len("sqlite://") :].startswith("//")


@pytest.mark.regression
@pytest.mark.parametrize("shortcut", ["persistent", "learning"])
def test_memory_shortcut_constructs_without_crash(tmp_path, shortcut):
    """resolve_memory_shortcut('persistent'|'learning') must not raise (#855).

    Before the fix this raised ``TypeError`` on the unsupported ``storage_path``
    kwarg, so ``Agent(memory="persistent"|"learning")`` was unusable.
    """
    provider = resolve_memory_shortcut(shortcut, memory_path=str(tmp_path / shortcut))
    assert type(provider).__name__ == "HierarchicalMemory"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.parametrize("shortcut", ["persistent", "learning"])
async def test_memory_shortcut_roundtrips_through_warm_tier(tmp_path, shortcut):
    """A stored entry reads back with content AND tags via the warm tier (#855).

    Pins the ``tag_list`` rename: the tag column persists as ``tag_list`` (not the
    reserved ``NodeMetadata.tags``), so a regression to the colliding name would
    fail this round-trip loudly. Requires DataFlow (the real warm-tier backend).
    """
    pytest.importorskip(
        "dataflow", reason="warm-tier round-trip requires kailash-dataflow"
    )

    provider = resolve_memory_shortcut(shortcut, memory_path=str(tmp_path / shortcut))
    assert provider.has_warm_tier is True, "DataFlow present but warm tier not wired"

    entry = MemoryEntry(
        content="remember this across sessions",
        session_id="s-855",
        importance=0.2,  # low importance -> demoted to the warm tier
        tags=["alpha", "beta"],
    )
    entry_id = await provider.store(entry)

    retrieved = await provider.get(entry_id)
    assert retrieved is not None, "entry did not persist to the warm tier"
    assert retrieved.content == "remember this across sessions"
    assert retrieved.tags == ["alpha", "beta"], "tags must round-trip via tag_list"
    assert await provider.count() >= 1
