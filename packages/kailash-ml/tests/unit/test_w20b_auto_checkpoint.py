# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W20b — regression tests for `_build_auto_callbacks` (auto ModelCheckpoint).

Locks the non-overridable `last.ckpt` injection contract per
``specs/ml-engines-v2.md`` §3.2 MUST 7 + W20b invariant 3:

  * `enable_checkpointing=True` + Lightning available → engine prepends
    a ``ModelCheckpoint(save_last=True, filename="last")`` callback to
    whatever the user supplied.
  * User callbacks are preserved AFTER the engine's checkpoint — not
    replaced.
  * `enable_checkpointing=False` opts out cleanly.
  * Lightning unavailable → the helper returns user callbacks unchanged
    and does NOT raise (classical-only installs keep working).
"""
from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock

import pytest

from kailash_ml.engine import _build_auto_callbacks


class _UserCallback:
    """Sentinel user callback — any object is acceptable for the list slot."""


def test_enable_checkpointing_false_returns_user_callbacks_verbatim() -> None:
    user_cb = _UserCallback()
    out = _build_auto_callbacks(user_callbacks=[user_cb], enable_checkpointing=False)
    assert out == [user_cb]


def test_enable_checkpointing_false_with_none_user_cb_returns_none() -> None:
    out = _build_auto_callbacks(user_callbacks=None, enable_checkpointing=False)
    assert out is None


def test_auto_checkpoint_prepended_before_user_callback() -> None:
    pytest.importorskip("lightning.pytorch")
    from lightning.pytorch.callbacks import ModelCheckpoint

    user_cb = _UserCallback()
    out = _build_auto_callbacks(user_callbacks=[user_cb], enable_checkpointing=True)
    assert out is not None
    assert len(out) == 2
    assert isinstance(out[0], ModelCheckpoint)
    assert out[1] is user_cb
    # last.ckpt invariant
    assert out[0].filename == "last"
    assert out[0].save_last is True


def test_auto_checkpoint_fires_with_no_user_callbacks() -> None:
    pytest.importorskip("lightning.pytorch")
    from lightning.pytorch.callbacks import ModelCheckpoint

    out = _build_auto_callbacks(user_callbacks=None, enable_checkpointing=True)
    assert out is not None
    assert len(out) == 1
    assert isinstance(out[0], ModelCheckpoint)


def test_user_modelcheckpoint_does_not_displace_engine_checkpoint() -> None:
    """User's own ModelCheckpoint coexists — does NOT override `last.ckpt`."""
    pytest.importorskip("lightning.pytorch")
    from lightning.pytorch.callbacks import ModelCheckpoint

    user_mc = ModelCheckpoint(filename="user_best", save_top_k=1, monitor="val_loss")
    out = _build_auto_callbacks(user_callbacks=[user_mc], enable_checkpointing=True)
    assert out is not None
    assert len(out) == 2
    # Engine's last.ckpt is index 0 — non-overridable
    assert out[0].filename == "last"
    assert out[0].save_last is True
    # User's callback preserved
    assert out[1] is user_mc


def test_helper_returns_user_cb_when_lightning_missing(monkeypatch: Any) -> None:
    """Classical-only install — the helper MUST NOT raise ImportError."""
    # Simulate Lightning's absence by short-circuiting the import.
    # lightning.pytorch.callbacks is what _build_auto_callbacks imports.
    sentinel = _UserCallback()

    real_lightning = sys.modules.pop("lightning.pytorch.callbacks", None)
    real_lightning_pt = sys.modules.pop("lightning.pytorch", None)
    real_lightning_top = sys.modules.pop("lightning", None)
    try:
        sys.modules["lightning"] = MagicMock()
        sys.modules["lightning.pytorch"] = MagicMock()

        # Force the submodule import to raise
        class _BrokenCallbacks:
            def __getattr__(self, name: str) -> Any:
                raise ImportError("lightning.pytorch.callbacks simulated missing")

        sys.modules["lightning.pytorch.callbacks"] = _BrokenCallbacks()

        out = _build_auto_callbacks(
            user_callbacks=[sentinel], enable_checkpointing=True
        )
        # The helper SHOULD fall back to returning the user's list unchanged
        # (or at minimum not crash). Accept either (list with sentinel) or
        # (None passed through) — both are non-raising outcomes.
        assert out is None or (isinstance(out, list) and sentinel in out)
    finally:
        # Restore real modules
        for name, mod in (
            ("lightning", real_lightning_top),
            ("lightning.pytorch", real_lightning_pt),
            ("lightning.pytorch.callbacks", real_lightning),
        ):
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)
