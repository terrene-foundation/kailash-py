# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test: _get_async_database_connection must raise (not return None)
on an unsupported DB URL scheme when ErrorEnhancer is unavailable.

Bug: the final ``else`` branch of ``DataFlow._get_async_database_connection``
only raised ``if ErrorEnhancer is not None``; ``ErrorEnhancer`` can be ``None``
(its import is wrapped in ``try/except ImportError -> None`` at engine.py top),
so an unsupported scheme with ErrorEnhancer unavailable fell through and
returned ``None`` SILENTLY — deferring the failure to a single downstream
``assert conn is not None`` at one call site and handing every other caller a
None connection. The fix raises ``ValueError`` unconditionally. (silent None
return on unsupported scheme when ErrorEnhancer unavailable)

This is a Tier-1 unit test: it invokes the method on a minimal stub object via
the unbound function, so it never constructs a full DataFlow instance (avoiding
the async express-path setup). No real DB connection is opened — the unsupported
scheme short-circuits before any connect() call.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dataflow.core import engine as engine_mod
from dataflow.core.engine import DataFlow


def _stub_with_url(url: str) -> SimpleNamespace:
    """Minimal object exposing only ``self.config.database.url``.

    ``_get_async_database_connection`` reads nothing else off ``self`` before
    the unsupported-scheme branch, so this stub is sufficient to drive the
    branch under test without DataFlow.__init__.
    """
    return SimpleNamespace(config=SimpleNamespace(database=SimpleNamespace(url=url)))


@pytest.mark.regression
@pytest.mark.timeout(30)
async def test_unsupported_scheme_raises_when_error_enhancer_none(monkeypatch):
    # Exercise the EXACT previously-falling-through branch: unsupported scheme
    # AND ErrorEnhancer unavailable (its import failed -> None at module load).
    monkeypatch.setattr(engine_mod, "ErrorEnhancer", None)
    monkeypatch.delenv("DATAFLOW_TDD_MODE", raising=False)  # stay on the prod path

    stub = _stub_with_url("mongodb://localhost:27017/db")  # unsupported by this method

    with pytest.raises(ValueError, match="Unsupported database URL"):
        # Bind the unbound method to the stub — no DataFlow.__init__, no hang.
        await DataFlow._get_async_database_connection(stub)


@pytest.mark.regression
@pytest.mark.timeout(30)
async def test_unsupported_scheme_error_masks_credentials(monkeypatch):
    # Security regression: the fallback raise (ErrorEnhancer=None branch) routes
    # db_url through mask_url() so a credentialed connection string never leaks
    # its password into the exception message (logs/traces). The unmasked-db_url
    # form would have shipped 'admin:secretpass@' verbatim.
    monkeypatch.setattr(engine_mod, "ErrorEnhancer", None)
    monkeypatch.delenv("DATAFLOW_TDD_MODE", raising=False)

    # mysql:// is unsupported by this method -> hits the masked fallback raise.
    stub = _stub_with_url("mysql://admin:secretpass@db.internal:3306/app")

    with pytest.raises(ValueError) as excinfo:
        await DataFlow._get_async_database_connection(stub)

    message = str(excinfo.value)
    assert "secretpass" not in message, f"password leaked into error: {message!r}"
    assert "admin:secretpass" not in message
    assert "***" in message  # mask_url canonical redaction marker


@pytest.mark.regression
@pytest.mark.timeout(30)
async def test_unsupported_scheme_raises_when_error_enhancer_present(monkeypatch):
    # When ErrorEnhancer IS present it raises via enhance_invalid_database_url;
    # assert the path still raises (does NOT return None) regardless of which
    # branch handles it.
    class _EnhancerStub:
        @staticmethod
        def enhance_invalid_database_url(database_url, error_message):
            return ValueError(f"enhanced: {error_message}")

    monkeypatch.setattr(engine_mod, "ErrorEnhancer", _EnhancerStub)
    monkeypatch.delenv("DATAFLOW_TDD_MODE", raising=False)

    stub = _stub_with_url("oracle://localhost/db")  # unsupported scheme

    with pytest.raises(ValueError):
        await DataFlow._get_async_database_connection(stub)


@pytest.mark.regression
@pytest.mark.timeout(30)
async def test_none_url_raises(monkeypatch):
    # Sibling guard already present in the method: a None url must raise too,
    # never return None.
    monkeypatch.delenv("DATAFLOW_TDD_MODE", raising=False)
    stub = _stub_with_url(None)

    with pytest.raises(ValueError, match="Database URL is not configured"):
        await DataFlow._get_async_database_connection(stub)
