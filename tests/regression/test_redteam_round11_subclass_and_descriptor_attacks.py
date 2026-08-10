"""Round-11 pins: adversarial INPUT TYPES, not adversarial implementations.

Round 11's orchestrator mutation matrix reported 18/18 red -- every enumerated
behaviour pinned -- and it was WRONG about what that proved. A mutation matrix
perturbs the IMPLEMENTATION while holding the input fixed, so it is structurally
blind to a defect whose vector is the TYPE of the input. The adversarial security
lens found exactly that by reading, and it was CRITICAL.

The measured bypass, before the fix:

    class Sneak(str):
        def __hash__(self): return hash("<module>")
        def __eq__(self, other): return True

    _safe_identifier(Sneak("A\\nERROR ... " + "Z"*5000 + " <- FORGED@a.py:1:f"))
    -> LEN: 5043   NEWLINE: True   CHAIN-SEP: True   AT: True

`text in _CPYTHON_PSEUDO_IDENTIFIERS` is NOT byte-equality: it is `__hash__`
then `__eq__`, both overridable on a `str` subclass, and `isinstance(value, str)`
admits one by construction. The allowlist branch returns BEFORE the charset
filter and BEFORE the length bound, so every property the module claims fell at
once -- through all three entry points (`type.__name__` preserves the subclass on
round-trip, measured; `func.__name__`/`__qualname__` accept one by assignment).

These pins therefore attack the INPUT, not the code. That is the axis the matrix
could not reach.
"""

import logging

import kailash.utils.secure_logging as sl
import pytest
from kailash.utils.secure_logging import (
    safe_callable_name,
    safe_exception_frames,
    safe_type_name,
)


class _Sneak(str):
    """A `str` subclass that lies about equality, hashing, and length."""

    def __hash__(self):
        return hash("<module>")

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __len__(self):
        return 5


PAYLOAD = "A\nERROR forged-log-line " + "Z" * 5000 + " <- FORGED@a.py:1:f"


def _ident(value, *, allow_pseudo=False):
    """Call `_safe_identifier` across both signatures.

    `allow_pseudo` does not exist on a tree predating the fix, and a TypeError
    there is zero evidence about the BEHAVIOUR these pins measure -- it would red
    for the wrong reason and make the fail-first run unreadable.
    """
    try:
        return sl._safe_identifier(value, allow_pseudo=allow_pseudo)
    except TypeError:
        return sl._safe_identifier(value)


class TestAStrSubclassCannotDefeatTheChokepoint:
    """C1 (CRITICAL): normalization must precede every predicate."""

    def test_a_lying_eq_does_not_open_the_allowlist(self):
        rendered = _ident(_Sneak(PAYLOAD), allow_pseudo=True)

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")
        assert "\n" not in rendered
        assert " <- " not in rendered
        assert "@" not in rendered

    def test_the_same_holds_at_the_default_call_shape(self):
        """allow_pseudo=False must not be the only thing saving us."""
        rendered = _ident(_Sneak(PAYLOAD))

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")
        assert "\n" not in rendered

    def test_reachable_via_type_dunder_name(self):
        """`type.__name__` preserves a str subclass on round-trip (measured)."""
        exc_type = type("Benign", (Exception,), {})
        exc_type.__name__ = _Sneak(PAYLOAD)

        assert type(exc_type.__name__) is _Sneak, "vector itself regressed"

        try:
            raise exc_type("boom")
        except Exception as exc:
            rendered = safe_type_name(exc)

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")
        assert "\n" not in rendered

    def test_reachable_via_qualname_assignment(self):
        def target():
            pass

        target.__qualname__ = _Sneak("postgres://svc:hunter2@h/db " + "Z" * 4000)
        target.__name__ = target.__qualname__

        rendered = safe_callable_name(target)

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")
        assert "@" not in rendered
        assert " " not in rendered

    def test_a_lying_len_cannot_suppress_a_real_diagnostic(self):
        """L2: `not text` ran before normalization, so `<empty>` was reachable.

        Diagnostic denial rather than disclosure -- a real name suppressed to
        `<empty>` -- but the same subclass-identity root as the CRITICAL, closed
        by the same normalization.
        """

        class LyingEmpty(str):
            def __len__(self):
                return 0

        rendered = _ident(LyingEmpty("REAL_DIAGNOSTIC_NAME"))

        assert rendered == "REAL_DIAGNOSTIC_NAME"


class TestShadowedDescriptorsCannotLie:
    """H1: a shadow that LIES is invisible to a guard that catches raises."""

    def test_a_lying_suppress_context_cannot_defeat_from_None(self):
        """`raise X from None` suppression, defeated by a class attribute.

        A plain `__suppress_context__ = False` sits earlier in the MRO than
        BaseException's member descriptor and wins the INSTANCE read, while the
        author's real suppression lives in the C-struct field. The round-10
        totality wrapper cannot help: this shadow never raises, it lies.
        """

        class Evil(Exception):
            __suppress_context__ = False

        with pytest.raises(Evil) as caught:
            try:
                raise KeyError("SUPPRESSED_SECRET_LOCATION")
            except Exception:
                raise Evil("public") from None

        # The instance read is still the lie -- we do not "fix" the exception.
        assert caught.value.__suppress_context__ is False
        rendered = safe_exception_frames(caught.value)

        assert "KeyError" not in rendered
        assert "Evil@" in rendered

    def test_a_shadowed_context_cannot_inject_chosen_frames(self):
        class Injector(Exception):
            @property
            def __context__(self):
                return ValueError("INJECTED_LINK")

        with pytest.raises(Injector) as caught:
            raise Injector("public")

        rendered = safe_exception_frames(caught.value)

        assert "INJECTED_LINK" not in rendered
        assert "ValueError" not in rendered


class TestTotalityIsTelemetered:
    """M2: the guard was right; the silence was not."""

    def test_an_internal_defect_is_reported_not_swallowed(self, monkeypatch, caplog):
        """`except Exception` catches OUR bugs too, and said nothing about them.

        This function has already shipped THREE instances of one arithmetic bug.
        A fourth would have degraded every record to `<frames-unavailable>` with
        no log line and no way to tell our defect from an attack -- the
        `zero-tolerance.md` Rule 3 swallow shape.
        """

        def boom(*args, **kwargs):
            raise IndexError("OUR OWN BUG")

        monkeypatch.setattr(sl, "_safe_exception_frames_impl", boom)

        with caplog.at_level(logging.DEBUG, logger="kailash.utils.secure_logging"):
            try:
                raise ValueError("normal")
            except Exception as exc:
                rendered = safe_exception_frames(exc)

        assert rendered == "<frames-unavailable>"
        assert any(
            "unavailable" in record.message for record in caplog.records
        ), "internal defect was swallowed with no telemetry"

    def test_telemetry_cannot_break_totality(self, monkeypatch):
        """A logger that raises must not turn the guard into the defect."""

        class ExplodingLogger:
            def debug(self, *args, **kwargs):
                raise RuntimeError("logging is down")

        def boom(*args, **kwargs):
            raise IndexError("OUR OWN BUG")

        monkeypatch.setattr(sl, "_safe_exception_frames_impl", boom)
        monkeypatch.setattr(sl, "_LOGGER", ExplodingLogger())

        try:
            raise ValueError("normal")
        except Exception as exc:
            rendered = safe_exception_frames(exc)

        assert rendered == "<frames-unavailable>"


class TestPlatformAndRecordBounds:
    def test_a_windows_path_survives_intact(self):
        """M3: `\\` is not structural to this grammar; excluding it mangled every
        Windows frame path, degrading the diagnostic the helper exists to keep."""
        rendered = _ident(r"svc\db\connect.py")

        assert rendered == r"svc\db\connect.py"

    def test_the_caller_supplied_limit_is_clamped(self):
        """L1: the per-identifier bound did not bound the RECORD.

        A caller passing a large `limit` against a deep traceback rendered
        megabytes. Every in-tree site uses <= 20, so this closes a latent
        API-contract gap rather than a live path.
        """

        def recurse(depth):
            if depth:
                return recurse(depth - 1)
            raise ValueError("deep")

        with pytest.raises(ValueError) as caught:
            recurse(400)

        rendered = safe_exception_frames(caught.value, limit=10**6)

        # Assert the FRAME COUNT, not the character count: a char threshold
        # passes on a short traceback whether or not a clamp exists, which is
        # exactly how the first version of this pin passed at parent.
        frame_count = rendered.count(">") + 1

        assert frame_count <= sl._MAX_FRAME_LIMIT, frame_count
        # ...and the traceback really was deeper than the clamp, so the pin is
        # measuring the clamp rather than a short stack.
        assert len(caught.traceback) > sl._MAX_FRAME_LIMIT
