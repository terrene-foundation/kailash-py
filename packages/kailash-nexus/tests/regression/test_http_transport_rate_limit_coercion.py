# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""``HTTPTransport(rate_limit=...)`` MUST route through ``_coerce_rate_limit``.

``HTTPTransport.__init__`` was the FIFTH surface writing ``_rate_limit`` and the
last one still writing the kwarg RAW. It is the SAME attribute name the enforced
path reads, and ``nexus/sse.py::_rate_limit_exceeded`` reaches it by ``getattr``
duck-typing::

    rate_limit = getattr(nexus, "_rate_limit", None)
    if not isinstance(rate_limit, int) or rate_limit <= 0:
        return False  # no limit configured

so a negative value stored there yields ``-5 <= 0 -> return False``: silently
unlimited. The ``Optional[int] = 100`` annotation on the kwarg is the only thing
that looked like a guard, and an annotation does not execute.

These assertions are BEHAVIOURAL -- each constructs the transport and observes
the raise or the coerced attribute. A source-grep assertion would pass against a
per-adapter copy of the coercion logic, which is precisely the drift this bug
class keeps producing (``rules/security.md`` § Enforcement-Surface Parity: ONE
shared restrictiveness function, per-adapter copies BLOCKED).

Bug class: commit ``98e83dfbe`` ("two of four rate-limit write surfaces never
coerced; a typo'd minus disabled it") -- this is the fifth surface it missed.
"""

import pytest

from nexus.core import _coerce_rate_limit
from nexus.transports.http import HTTPTransport

pytestmark = pytest.mark.regression


class TestHTTPTransportRateLimitRejectsFailOpenValues:
    """Every value the other four surfaces reject MUST raise here too."""

    def test_negative_rate_limit_raises_rather_than_disabling_the_limiter(self):
        """A typo'd minus MUST NOT resolve to "no limit configured"."""
        with pytest.raises(ValueError) as exc_info:
            HTTPTransport(rate_limit=-5)

        message = str(exc_info.value)
        # The error names the surface, so the operator knows which call to edit.
        assert "HTTPTransport(rate_limit=...)" in message
        assert "-5" in message

    def test_bool_rate_limit_raises_rather_than_meaning_one_request_per_minute(self):
        """``isinstance(True, int)`` is True; a bool here is always a mistake."""
        with pytest.raises(ValueError) as exc_info:
            HTTPTransport(rate_limit=True)

        assert "HTTPTransport(rate_limit=...)" in str(exc_info.value)

    def test_non_integral_float_raises_rather_than_truncating_to_unlimited(self):
        """``int(0.5)`` is 0, which the reader treats as unlimited."""
        with pytest.raises(ValueError) as exc_info:
            HTTPTransport(rate_limit=0.5)

        assert "HTTPTransport(rate_limit=...)" in str(exc_info.value)

    def test_non_int_type_raises(self):
        """A str limit reaches the reader's ``isinstance`` check as "no limit"."""
        with pytest.raises(ValueError) as exc_info:
            HTTPTransport(rate_limit="100")

        assert "HTTPTransport(rate_limit=...)" in str(exc_info.value)


class TestHTTPTransportRateLimitAcceptsValidValues:
    """The coercion MUST NOT break the values that were already legitimate."""

    def test_default_is_stored_unchanged(self):
        assert HTTPTransport()._rate_limit == 100

    def test_positive_int_is_stored_unchanged(self):
        assert HTTPTransport(rate_limit=50)._rate_limit == 50

    def test_explicit_none_stays_none(self):
        """None is the documented "unlimited"."""
        assert HTTPTransport(rate_limit=None)._rate_limit is None

    def test_integral_float_is_accepted_and_narrowed_to_int(self):
        """Config from JSON/YAML/env routinely arrives as ``50.0``."""
        stored = HTTPTransport(rate_limit=50.0)._rate_limit
        assert stored == 50
        assert isinstance(stored, int) and not isinstance(stored, bool)

    def test_zero_stays_unlimited(self):
        """0 kept its pre-existing "unlimited" meaning; the reader agrees."""
        assert HTTPTransport(rate_limit=0)._rate_limit is None


class TestHTTPTransportSharesTheOneCoercionFunction:
    """Parity is only real if it is the SAME function, not a copy of it."""

    @pytest.mark.parametrize("value", [-5, True, 0.5, "100", None, 0, 50, 50.0])
    def test_stored_value_matches_the_shared_helper_exactly(self, value):
        """Same input -> same outcome (value or raise) as ``_coerce_rate_limit``.

        A per-adapter copy would drift from this the moment either side changed;
        pinning outcome-equality across the whole accept/reject domain is what
        makes the drift fail loudly.
        """
        try:
            expected = _coerce_rate_limit(value, "HTTPTransport(rate_limit=...)")
        except ValueError as shared_exc:
            with pytest.raises(ValueError) as transport_exc:
                HTTPTransport(rate_limit=value)
            assert str(transport_exc.value) == str(shared_exc)
        else:
            assert HTTPTransport(rate_limit=value)._rate_limit == expected
