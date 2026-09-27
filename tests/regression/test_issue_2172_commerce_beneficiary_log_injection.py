"""Regression: caller-supplied ids reaching constraint log lines (#2172).

``CommerceConstraint.check`` read the beneficiary straight from caller-supplied
context and interpolated it into a record::

    beneficiary = context.get("beneficiary_id")          # commerce.py:114
    ...
    logger.info(
        f"Attribution required but no chain provided for beneficiary {beneficiary}"
    )                                                    # commerce.py:149-151

So a caller chose the bytes of a log record. MEASURED against the unfixed code,
a ``beneficiary_id`` of ``"org-1\\nINFO:root:audit: approved"`` emitted TWO
lines, the second being a well-formed ``INFO:root:audit: approved`` record that
a collector ingests as genuine; a 5 MB value emitted 5,000,100 characters.

**The instrument is the emitted STREAM, not the LogRecord.** A forged record is
forged at FORMAT time, so ``caplog`` shows exactly one ``LogRecord`` either way
and counting records cannot discriminate. These tests attach a real
``StreamHandler`` with a real ``Formatter`` and read the rendered text.

Commerce diagnostics omit the financial counterparty identifier entirely,
including at DEBUG. The commerce tests therefore require the fixed diagnostic
and reject identifier disclosure as well as forged records. Sibling diagnostic
values remain sanitized: control characters and length are bounded while their
non-sensitive text stays available. Their assertions still require that text.

Lazy ``%s`` arguments are not an injection barrier: formatting happens at emit
time. The tests inspect the rendered stream for both privacy and structure.
"""

import io
import logging

import pytest

from kailash.trust.constraints.builtin import ResourceDimension
from kailash.trust.constraints.commerce import CommerceConstraint
from kailash.trust.constraints.dimension import ConstraintDimensionRegistry
from kailash.trust.constraints.evaluator import MultiDimensionEvaluator
from kailash.trust.constraints.spend_tracker import SpendTracker

pytestmark = pytest.mark.regression

#: One value carrying every structural threat the sanitizer must neutralize: a
#: bare LF (forges a record), a CRLF pair (forges another), a NUL (truncates
#: C-string consumers) and an ANSI CSI sequence (rewrites a terminal).
INJECTION = (
    "org-1\nINFO:root:audit: approved\r\n2026-01-01 ERROR forged: transfer cleared"
    "\x00\x1b[31mred\x1b[0m"
)

#: Bytes that must not survive INSIDE an emitted line. ``\n`` is absent because
#: a ``StreamHandler`` appends its own terminator to every record: an
#: ATTACKER-injected newline shows up as a SECOND line, which the line count
#: below is what asserts on.
CONTROL_BYTES = ("\r", "\x00", "\x1b")


class _StreamProbe:
    """Capture what a real ``Formatter`` writes for one logger."""

    def __init__(self, logger_name: str, level: int = logging.DEBUG):
        self._logger = logging.getLogger(logger_name)
        self._buffer = io.StringIO()
        self._handler = logging.StreamHandler(self._buffer)
        # A realistic collector-shaped format: the levelname/logger prefix is
        # what makes a forged "INFO:root:..." line indistinguishable from a
        # genuine record, so the probe must render it.
        self._handler.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        self._level = level

    def __enter__(self) -> "_StreamProbe":
        self._prior_level = self._logger.level
        self._prior_propagate = self._logger.propagate
        self._logger.setLevel(self._level)
        self._logger.propagate = False
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, *exc_info) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._prior_level)
        self._logger.propagate = self._prior_propagate

    @property
    def text(self) -> str:
        self._handler.flush()
        return self._buffer.getvalue()

    @property
    def lines(self) -> list[str]:
        return [line for line in self.text.split("\n") if line]


def _assert_no_forged_record(probe: _StreamProbe, expect_substring: str) -> None:
    """Exactly one record, no control bytes, value still diagnosable."""
    assert probe.lines, "no record was emitted at all -- the probe missed the call"
    assert len(probe.lines) == 1, (
        "an injected newline forged an extra log line: expected exactly ONE, got "
        f"{len(probe.lines)}: {probe.lines!r}"
    )
    # The specific forgery the issue names: a line a collector would parse as
    # its own record. Checked independently of the count so the failure message
    # names the forged record rather than just a number.
    forged = [ln for ln in probe.lines if ln.startswith(("INFO:root:", "2026-01-01"))]
    assert not forged, f"a forged record reached the stream: {forged!r}"
    for byte in CONTROL_BYTES:
        assert (
            byte not in probe.lines[0]
        ), f"control byte {byte!r} survived into the record: {probe.lines[0]!r}"
    assert expect_substring in probe.text, (
        "the sanitizer redacted the diagnostic instead of neutralizing it: "
        f"{probe.text!r}"
    )


class TestCommerceBeneficiaryIsPrivate:
    """The headline site: ``commerce.py`` attribution-missing record."""

    @pytest.mark.parametrize("beneficiary", [INJECTION, "finance-person@example.test"])
    def test_beneficiary_is_omitted_from_debug_record(self, beneficiary):
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe("kailash.trust.constraints.commerce") as probe:
            result = dimension.check(parsed, {"beneficiary_id": beneficiary})

        _assert_no_forged_record(probe, "Attribution required but no chain provided")
        assert beneficiary not in probe.text
        assert probe.text == (
            "DEBUG:kailash.trust.constraints.commerce:"
            "Attribution required but no chain provided\n"
        )
        # The branch is benign: the log line is incidental, not a verdict.
        assert result.satisfied is True

    def test_beneficiary_length_is_bounded(self):
        """A multi-megabyte id must not drive log volume."""
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe("kailash.trust.constraints.commerce") as probe:
            result = dimension.check(parsed, {"beneficiary_id": "B" * 5_000_000})

        _assert_no_forged_record(probe, "Attribution required but no chain provided")
        assert result.satisfied is True
        # The fixed diagnostic carries no identifier, regardless of its length.
        assert (
            len(probe.text) < 512
        ), f"unbounded value reached the log: {len(probe.text)} chars emitted"

    def test_benign_absent_attribution_does_not_log_the_party_at_info(self):
        """The benign diagnostic stays below the default INFO threshold."""
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe(
            "kailash.trust.constraints.commerce", level=logging.INFO
        ) as probe:
            result = dimension.check(
                parsed, {"beneficiary_id": "finance-person@example.test"}
            )

        assert result.satisfied is True
        assert probe.lines == [], (
            "the benign diagnostic was emitted at INFO or above: " f"{probe.lines!r}"
        )


class TestConstraintSiblingSitesAreSanitized:
    """The same shape at the sibling sites swept in the same change."""

    def test_dimension_registry_name_and_reviewer(self):
        registry = ConstraintDimensionRegistry()

        with _StreamProbe("kailash.trust.constraints.dimension") as probe:
            registry.register(_StubDimension(INJECTION), requires_review=True)

        _assert_no_forged_record(probe, "org-1")

    def test_evaluator_unknown_dimension_name(self):
        registry = ConstraintDimensionRegistry()
        evaluator = MultiDimensionEvaluator(registry=registry)
        with _StreamProbe("kailash.trust.constraints.evaluator") as probe:
            evaluator.evaluate(constraints={INJECTION: 1}, context={})

        _assert_no_forged_record(probe, "org-1")

    def test_spend_tracker_agent_id(self):
        tracker = SpendTracker()
        tracker.set_budget(INJECTION, limit=100.0)

        with _StreamProbe("kailash.trust.constraints.spend_tracker") as probe:
            tracker.record_spend(INJECTION, amount=1.0, action="buy")

        _assert_no_forged_record(probe, "org-1")

    def test_resource_constraint_rejects_unbounded_path(self):
        """``!r`` already blocked the newline here; the BOUND was missing."""
        dimension = ResourceDimension()
        parsed = dimension.parse(["data/*"])

        with _StreamProbe("kailash.trust.constraints.builtin") as probe:
            dimension.check(parsed, {"resource_requested": "../" + "A" * 5_000_000})

        assert probe.lines, "the security-violation warning did not fire"
        assert (
            len(probe.text) < 1024
        ), f"unbounded resource path reached the log: {len(probe.text)} chars"


class _StubDimension:
    """Minimal dimension object for registry tests."""

    def __init__(self, name: str):
        self.name = name

    def parse(self, value):  # pragma: no cover - not exercised
        raise NotImplementedError

    def check(self, parsed, context):  # pragma: no cover - not exercised
        raise NotImplementedError
