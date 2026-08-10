# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit coverage for the leak-free wrapped-exception origin descriptor.

The feature-store surfaces wrap an unexpected underlying failure in a typed
``FeatureStoreError`` whose ``reason`` names the exception CLASS but never its
MESSAGE — a driver / adapter message routinely embeds the connection string,
the raw tenant id, and the offending row values (``rules/security.md`` § "No
secrets in logs"; the tenant-fingerprint convention the same call sites apply).

``describe_exception_origin`` adds the originating ``module:lineno`` so a
class-only ``reason`` becomes self-diagnosing WITHOUT weakening that
discipline. These tests pin both halves of the contract:

* the locator is present and names the INNERMOST raising frame (diagnosability);
* the underlying message never transits the descriptor (the leak-free floor).

The second half is the load-bearing one: it reds if the helper is ever
"improved" to interpolate ``str(exc)``.

Every case raises through ``pytest.raises`` rather than a bare
``try/except``: ``except ... as exc`` unbinds ``exc`` at block exit, and a
``descriptor`` assigned only inside an ``except`` branch is unbound on the
no-exception path (``UnboundLocalError`` — the test would ERROR rather than
assert). ``pytest.raises`` fails the test outright if nothing is raised AND
binds ``excinfo`` unconditionally afterwards, so every name below is bound on
every path this test can take.
"""
from __future__ import annotations

from types import TracebackType

import pytest
from kailash_ml.features._error_context import describe_exception_origin

_SECRET_MESSAGE = "connect failed for postgres://user:hunter2@db.internal/acme"


def _raise_with_secret_message() -> None:
    """Raise from a known innermost frame carrying a credential-bearing text."""
    raise RuntimeError(_SECRET_MESSAGE)


def _outer_wrapper() -> None:
    """Call the raising helper so the traceback has >1 frame to walk."""
    _raise_with_secret_message()


def _innermost_lineno(exc: BaseException) -> int:
    """Line number of the innermost frame of ``exc``'s traceback.

    Asserts the traceback is present rather than chaining through an Optional,
    so a helper regression that loses the traceback fails loudly here instead
    of raising ``AttributeError`` on ``None``.
    """
    tb: TracebackType | None = exc.__traceback__
    assert tb is not None, "a raised exception must carry a traceback"
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb.tb_lineno


def test_descriptor_names_exception_class_and_origin_module() -> None:
    """The descriptor carries the class plus a ``module:lineno`` locator."""
    with pytest.raises(RuntimeError) as excinfo:
        _outer_wrapper()
    descriptor = describe_exception_origin(excinfo.value)

    assert descriptor.startswith("RuntimeError at ")
    # The locator names THIS module (the raising frame lives here), with a line.
    module, _, lineno = descriptor.partition(" at ")[2].rpartition(":")
    assert module == __name__
    assert lineno.isdigit()


def test_descriptor_names_the_innermost_raising_frame() -> None:
    """The locator points at the raise site, not the catching wrapper.

    ``_raise_with_secret_message`` is the innermost frame; ``_outer_wrapper``
    and this test body are outer frames. A helper that read ``tb`` without
    walking to ``tb_next`` would report one of the outer line numbers.
    """
    with pytest.raises(RuntimeError) as excinfo:
        _outer_wrapper()
    reported_line = int(describe_exception_origin(excinfo.value).rpartition(":")[2])

    assert reported_line == _innermost_lineno(excinfo.value)
    raise_site = _raise_with_secret_message.__code__.co_firstlineno
    # The raise statement sits within the small body of the innermost helper.
    assert raise_site <= reported_line <= raise_site + 4


def test_descriptor_never_leaks_the_underlying_message() -> None:
    """No part of the exception's message text reaches the descriptor.

    This is the security floor: a driver error embedding a connection string,
    a raw tenant id, or row values MUST NOT transit the wrapped-error surface.
    """
    with pytest.raises(RuntimeError) as excinfo:
        _outer_wrapper()
    descriptor = describe_exception_origin(excinfo.value)

    assert _SECRET_MESSAGE not in descriptor
    for secret_fragment in ("hunter2", "postgres://", "db.internal", "acme"):
        assert secret_fragment not in descriptor


def test_descriptor_falls_back_to_class_name_without_a_traceback() -> None:
    """A hand-constructed exception (no traceback) degrades to the bare class."""
    assert describe_exception_origin(ValueError("never raised")) == "ValueError"


def test_descriptor_falls_back_when_the_frame_declares_no_module() -> None:
    """A frame whose globals carry no ``__name__`` degrades to the bare class."""
    with pytest.raises(KeyError) as excinfo:
        exec(compile("raise KeyError('x')", "<synthetic>", "exec"), {})

    assert describe_exception_origin(excinfo.value) == "KeyError"


@pytest.mark.parametrize(
    "exc_factory",
    [
        lambda: TypeError("f() missing 1 required keyword-only argument: 'max_length'"),
        lambda: KeyError("tenant"),
        lambda: ZeroDivisionError("division by zero"),
    ],
)
def test_descriptor_shape_is_stable_across_exception_types(exc_factory) -> None:
    """Every raised exception yields ``"<ExcType> at <module>:<lineno>"``."""
    with pytest.raises(
        Exception
    ) as excinfo:  # noqa: B017 — shape, not a class, is under test
        raise exc_factory()
    exc = excinfo.value

    expected = f"{type(exc).__name__} at {__name__}:{_innermost_lineno(exc)}"
    assert describe_exception_origin(exc) == expected
