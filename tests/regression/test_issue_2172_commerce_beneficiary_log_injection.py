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

**What "defeated" means here.** ``sanitize_log_value`` is explicitly NOT a
redaction step -- it flattens structure and bounds length, and the attacker's
TEXT survives inline on purpose, because it is usually the only diagnostic
there is. So "the payload substring is absent" is the WRONG assertion: it fails
on a correct fix. The discriminating property is that no emitted LINE STARTS a
new record. That is what is asserted below, and on the unfixed code it is
exactly what fails.

Lazy ``%s`` arguments are NOT themselves a barrier -- the record is still
formatted at emit time, so an unsanitized ``%s`` argument injects just as an
f-string does. ``sanitize_log_value`` is the entire defence; the lazy form is
a cost and style fix that these tests deliberately do not rely on.
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


class TestCommerceBeneficiaryIsSanitized:
    """The headline site: ``commerce.py`` attribution-missing record."""

    def test_attacker_chosen_beneficiary_cannot_forge_a_record(self):
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe("kailash.trust.constraints.commerce") as probe:
            result = dimension.check(parsed, {"beneficiary_id": INJECTION})

        _assert_no_forged_record(probe, "org-1")
        # The branch is benign: the log line is incidental, not a verdict.
        assert result.satisfied is True

    def test_beneficiary_length_is_bounded(self):
        """A multi-megabyte id must not drive log volume."""
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe("kailash.trust.constraints.commerce") as probe:
            dimension.check(parsed, {"beneficiary_id": "B" * 5_000_000})

        # Unfixed, this emitted 5,000,100 characters. The bound is 128 chars of
        # value plus the fixed prefix; 512 leaves room for the prefix without
        # asserting on its exact wording.
        assert (
            len(probe.text) < 512
        ), f"unbounded value reached the log: {len(probe.text)} chars emitted"

    def test_benign_absent_attribution_does_not_log_the_party_at_info(self):
        """#2172 secondary call: the identifier is DEBUG, not INFO.

        The branch is benign -- ``check`` returns satisfied=True either way --
        so an INFO record would write a financial counterparty identifier into
        default-enabled logs for a condition that triggers no enforcement.
        """
        dimension = CommerceConstraint()
        parsed = dimension.parse({"attribution_required": True})

        with _StreamProbe(
            "kailash.trust.constraints.commerce", level=logging.INFO
        ) as probe:
            dimension.check(parsed, {"beneficiary_id": "org-001"})

        assert probe.lines == [], (
            "the beneficiary identifier was emitted at INFO or above: "
            f"{probe.lines!r}"
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
