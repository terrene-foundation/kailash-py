# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Leak-free origin descriptor for wrapped feature-store exceptions.

The feature-store surfaces (:mod:`~kailash_ml.features.materialiser`,
:mod:`~kailash_ml.features.erasure`, :mod:`~kailash_ml.features.store`) wrap an
unexpected underlying failure in a typed
:class:`~kailash_ml.errors.FeatureStoreError` whose ``reason`` deliberately
carries the exception CLASS ONLY — never the underlying message. That discipline
is load-bearing: a driver / adapter error message routinely embeds the
connection string, the raw tenant id, and the offending row values, none of
which may reach an error surface (``rules/security.md`` § "No secrets in logs";
``rules/observability.md`` Rule 4; the tenant-fingerprint convention the same
call sites already apply).

The cost of a class-only ``reason`` is diagnosability: ``"materialize failed:
TypeError"`` names the failure class but not WHERE it came from, so a reader of
a CI short-summary line cannot tell an in-package bug from a bug in a
downstream binding without opening the full traceback.

:func:`describe_exception_origin` closes that gap without weakening the
discipline. It adds the DOTTED MODULE NAME + line number of the innermost
raising frame and nothing else:

    ``"TypeError at dataflow.core.nodes:3620"``

Why the dotted module name rather than a filesystem path: a path may embed the
absolute install prefix (a home directory, a per-run pytest tmpdir, a container
layout), which is operator-correlatable. The dotted module name is the same
identifier the package publishes in its own import surface, so it discloses
nothing an importer does not already hold. NO exception message text is read,
so no driver-embedded credential / tenant / row value can transit this helper.
"""
from __future__ import annotations

__all__ = ["describe_exception_origin"]


def describe_exception_origin(exc: BaseException) -> str:
    """Return ``"<ExcType> at <module>:<lineno>"`` for ``exc``.

    The location names the INNERMOST frame of ``exc``'s traceback — the frame
    that actually raised — so the descriptor points at the originating call
    site rather than at the wrapper that caught it.

    Parameters
    ----------
    exc:
        The caught exception being wrapped in a typed error.

    Returns
    -------
    str
        ``"<ExcType> at <module>:<lineno>"``, or the bare ``"<ExcType>"`` when
        ``exc`` carries no traceback (e.g. a hand-constructed instance) or when
        the raising frame declares no module name.

    Notes
    -----
    The exception's ``str(exc)`` / ``args`` are NEVER read, so an underlying
    driver message embedding a connection string, a raw tenant id, or row
    values cannot reach the returned descriptor.
    """
    exc_type = type(exc).__name__

    tb = exc.__traceback__
    if tb is None:
        return exc_type

    # Walk to the innermost frame — the raising site, not the catching wrapper.
    while tb.tb_next is not None:
        tb = tb.tb_next

    module = tb.tb_frame.f_globals.get("__name__")
    if not isinstance(module, str) or not module:
        return exc_type

    return f"{exc_type} at {module}:{tb.tb_lineno}"
