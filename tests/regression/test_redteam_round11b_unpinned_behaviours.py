"""Regression cases retained from the historical round-11b report.

The original round-11b mutation report concerns the original test context.
Its mutation results are historical and are not re-verified by the CSQ16
source-only reporting correction.

The retained virtual `type(obj).__name__` control reaches the raising metaclass
property. `safe_type_name` uses the canonical type descriptor instead, and its
existing assertion expects the declared `Hostile` name. Source:
src/kailash/utils/secure_logging.py:651-672 (`safe_type_name`). The separate
raising-str case retains the identifier fallback assertion.

The CSQ16 edits change source expectations and commentary only. This regression
module remains NOT_RUN in that correction; stock Tier 1 hook results do not
establish results for these regression cases.
"""

import os

import pytest

import kailash.utils.secure_logging as sl
from kailash.utils.secure_logging import (
    safe_callable_name,
    safe_exception_frames,
    safe_type_name,
)


class TestSafeCallableNameOuterFallback:
    """HIGH-1: the `except` fallback at the bottom of `safe_callable_name`.

    Same shape as round 10's finding -- a sanitization site with no guard.
    Unmutated `'Ev?il??-?x'`; unsanitized `'Ev@il <- x'`, forging BOTH the `@`
    frame anchor and the ` <- ` chain separator. The trigger is a lazy proxy,
    which that function's own docstring calls the ordinary case.
    """

    def test_the_outer_fallback_sanitizes(self):
        def exploding_getattr(self, name):
            raise RuntimeError("lazy proxy outside request context")

        hostile = type("Ev@il <- x", (), {"__getattr__": exploding_getattr})()

        rendered = safe_callable_name(hostile)

        # The pre-existing pin only asserted isinstance(..., str), which the RAW
        # string satisfies too -- it reached this branch without measuring it.
        assert "@" not in rendered
        assert " <- " not in rendered


class TestFrameLimitBoundaries:
    """HIGH-2 / MED-7: the `limit` contract and the default that enforces it."""

    @staticmethod
    def _deep(depth):
        if depth:
            return TestFrameLimitBoundaries._deep(depth - 1)
        raise ValueError("deep")

    @pytest.mark.parametrize("limit", [0, -1])
    def test_a_non_positive_limit_renders_NO_frames(self, limit):
        """`<= 0` means none, not unlimited -- the N3 bug, at the ORIGINAL site.

        The SIBLING slice (the chain cap) was pinned; this one, the slice N3 was
        actually about, was not. Measured unpinned: `limit=0` rendered 43 frames.
        """
        with pytest.raises(ValueError) as caught:
            self._deep(60)

        rendered = safe_exception_frames(caught.value, limit=limit)

        # Assert the frames field IS the marker, exactly. A `">" not in ...`
        # check is wrong here -- `<no-frames>` contains one.
        assert rendered.split("@", 1)[1] == "<no-frames>"

    def test_the_DEFAULT_limit_is_the_live_bound(self):
        """5 of 7 production sinks pass no `limit`, so this default IS the bound.

        Its stated purpose -- "deep recursive failures produce thousands of
        identical frames" -- had no pin. Measured unpinned: 403 frames.
        """
        with pytest.raises(ValueError) as caught:
            self._deep(400)

        rendered = safe_exception_frames(caught.value)
        frame_count = rendered.count(">") + 1

        assert frame_count <= sl._DEFAULT_FRAME_LIMIT


class TestRelativeFramePathDisclosureGuards:
    """MED-3: both guards are the function's ENTIRE privacy property.

    Unpinned, removing them rendered `Users/esperie/secretproj/app/mod.py` and
    `../var/hidden/layout/app/mod.py` where the guarded form renders `mod.py`.
    """

    def test_a_cwd_above_home_falls_back_to_the_basename(self, monkeypatch):
        monkeypatch.setattr(os, "getcwd", lambda: "/")

        rendered = sl._relative_frame_path("/Users/someone/secretproj/app/mod.py")

        assert rendered == "mod.py"
        assert "secretproj" not in rendered

    def test_a_path_outside_cwd_does_not_render_dot_dot(self, monkeypatch):
        monkeypatch.setattr(os, "getcwd", lambda: "/tmp/workspace")

        rendered = sl._relative_frame_path("/var/hidden/layout/app/mod.py")

        assert ".." not in rendered
        assert rendered == "mod.py"


class TestTotalityGuardsAreReallyReached:
    """Canonical type names and the separate raising-str fallback.

    The historical class name is retained. The name case keeps its virtual-lookup
    control while the helper bypasses the metaclass property. The identifier case
    retains its raising-str guard pin.
    """

    def test_safe_type_name_survives_a_raising_metaclass_name(self):
        """Canonical type names bypass a raising metaclass property.

        The virtual `type(obj).__name__` lookup below still reaches the
        property. The canonical type descriptor used by `safe_type_name`
        instead reads the declared `Hostile` name without consulting it.
        """

        class Meta(type):
            @property
            def __name__(cls):
                raise RuntimeError("metaclass __name__ raises")

        class Hostile(metaclass=Meta):
            pass

        # Preserve the virtual-lookup control: the property still raises here.
        with pytest.raises(RuntimeError):
            _ = type(Hostile()).__name__

        assert safe_type_name(Hostile()) == "Hostile"

    def test_safe_identifier_survives_a_raising_str(self):
        class Boom:
            def __str__(self):
                raise RuntimeError("str raises")

        with pytest.raises(RuntimeError):
            str(Boom())

        assert sl._safe_identifier(Boom()) == "<unrepresentable>"


class TestChainCycleGuard:
    """MED-6: `__cause__` is assignable, so a cycle is constructible."""

    @pytest.mark.timeout(15, method="thread")
    def test_a_cause_cycle_terminates(self):
        # The timeout is the ASSERTION here, not belt-and-braces. Without the
        # `seen` guard the walk follows a -> b -> a forever, so this pin HANGS
        # rather than fails -- an unreadable red that stalls the whole run. The
        # marker converts it into an attributable failure naming this test.
        # (Measured: the un-marked version timed out a 10-minute mutation batch.)
        first = ValueError("first")
        second = ValueError("second")
        first.__cause__ = second
        second.__cause__ = first

        rendered = safe_exception_frames(first)

        # Unpinned, the walk ran to the chain cap: 11 links instead of 2.
        assert rendered.count(" <- ") <= 1


class TestSentinelMarkersArePinned:
    """LOW-10 / LOW-11: a marker nobody asserts can be deleted silently."""

    def test_empty_input_renders_the_empty_marker(self):
        assert sl._safe_identifier("") == "<empty>"

    def test_a_frameless_exception_renders_the_no_frames_marker(self):
        # Never raised, so it carries no traceback.
        rendered = safe_exception_frames(ValueError("never raised"))

        assert "<no-frames>" in rendered
