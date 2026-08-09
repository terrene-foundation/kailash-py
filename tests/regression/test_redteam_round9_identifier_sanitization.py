"""Round-9 redteam pins: identifier sanitization in secure_logging.

Round 9 returned NOT CLEAN with six findings against the three commits that no
lens had reviewed (`a17c95e76`, `7d14e0b7e`, `a87890fd6`). The security lens had
no Bash, so every finding arrived as INFERENCE with a named falsifying probe.
This module is those probes, run and pinned.

WHY ONE MODULE FOR SIX FINDINGS. Rounds 6, 7, 8 and 9 each found a defect in the
PREVIOUS round's fix, and the reason is that each fix was a point patch on ONE
instance of a single class: an attacker-influenceable string reaching a log
record unsanitized and unbounded. The fix under test is therefore a chokepoint
(`_safe_identifier`) rather than another point patch, and these pins assert the
CLASS property at the boundary, not four separate symptoms.

WHAT THE CONTRACT IS, STATED HONESTLY. `_safe_identifier` does NOT promise
secrecy. A short caller-chosen name still reaches the record on purpose -- it is
frequently the only diagnostic available. It promises exactly two things, and
these tests pin those two and nothing more:

  BOUNDED         -- no identifier can drive log volume.
  STRUCTURALLY INERT -- no identifier can forge the record's own grammar.

A test asserting "the payload is absent" would be pinning a promise the code
deliberately does not make, and would red the moment someone logged a class name.
"""

import pytest

import kailash.utils.secure_logging as sl
from kailash.utils.secure_logging import safe_callable_name, safe_exception_frames

# Resolved defensively ON PURPOSE. Importing this constant at module level would
# make the whole module fail COLLECTION against a tree that predates the fix --
# an ImportError, which is zero evidence about the behaviour these pins exist to
# measure. With a fallback the module imports anywhere and each test reds on the
# BEHAVIOUR it names, which is what makes the fail-first run readable.
_MAX_IDENTIFIER_CHARS = getattr(sl, "_MAX_IDENTIFIER_CHARS", 120)


def _raise_and_render(exc_type, message="boom", **kwargs):
    """Raise, catch, render -- so the exception carries a real traceback."""
    try:
        raise exc_type(message)
    except Exception as exc:
        return safe_exception_frames(exc, **kwargs)


class TestIdentifiersAreBounded:
    """F1: an identifier cannot drive log volume."""

    def test_oversized_qualname_is_truncated(self):
        def target():
            pass

        target.__qualname__ = "X" * 5000
        target.__name__ = "X" * 5000

        rendered = safe_callable_name(target)

        # Measured pre-fix: 5000. The bound is the whole point.
        assert len(rendered) <= _MAX_IDENTIFIER_CHARS + len("<truncated>")
        assert rendered.endswith("<truncated>")

    def test_oversized_class_name_is_truncated_in_a_chain_render(self):
        exc_type = type("Y" * 5000, (Exception,), {})

        rendered = _raise_and_render(exc_type)

        assert len(rendered) < 5000
        assert "<truncated>" in rendered


class TestIdentifiersCannotForgeTheRecordGrammar:
    """F4: no identifier can invent this module's own delimiters.

    The rendered grammar is `" <- "` between chain links, `"@"` before frames,
    `">"` between frames, `":"` inside path:lineno:name, and `"<...>"` markers.
    A caller-supplied name containing any of those could invent a link, a frame,
    or -- via a newline -- an entire additional log line.
    """

    @pytest.mark.parametrize(
        "hostile_name, forged_token",
        [
            ("Evil <- FORGED@a.py:1:f", " <- "),
            ("Evil<+9999 outer links dropped, cap reached>", "<+9999"),
            ("Evil>frame.py:1:g", ">"),
            ("Evil@frames", "@"),
        ],
        ids=["chain-separator", "cap-marker", "frame-separator", "frame-anchor"],
    )
    def test_delimiters_cannot_be_minted_from_a_class_name(
        self, hostile_name, forged_token
    ):
        exc_type = type(hostile_name, (Exception,), {})

        rendered = _raise_and_render(exc_type)

        # Exactly one link was raised, so exactly one real "@" and no " <- ".
        assert " <- " not in rendered
        assert rendered.count("@") == 1
        assert forged_token not in rendered.split("@", 1)[0]

    def test_a_newline_cannot_forge_an_extra_log_line(self):
        # `type()` rejects a NUL in a class name but NOT a newline, so this is
        # constructible. Measured pre-fix: one newline reached the record.
        exc_type = type("Evil\nERROR fake-log-line", (Exception,), {})

        rendered = _raise_and_render(exc_type)

        assert "\n" not in rendered
        assert "\r" not in rendered

    def test_a_truncation_marker_in_a_record_is_always_ours(self):
        """`<` and `>` never survive input, so any `<...>` is emitted by us."""
        exc_type = type("Evil<truncated>", (Exception,), {})

        rendered = _raise_and_render(exc_type)

        assert "<truncated>" not in rendered.split("@", 1)[0]


class TestSafeCallableNameSanitizesEveryReturnPath:
    """F1: all four resolution branches route through the chokepoint."""

    def test_qualname_via_caller_controlled_getattr_is_sanitized(self):
        class Hostile:
            def __getattr__(self, name):
                if name in ("__qualname__", "__name__"):
                    return "postgres://svc:hunter2@h/db"
                raise AttributeError(name)

        rendered = safe_callable_name(Hostile())

        # NOT asserting the payload is gone -- it is not, by design. Asserting
        # it cannot carry the delimiters that would forge a record.
        assert "@" not in rendered
        assert "/" in rendered or "?" in rendered

    def test_type_name_branch_is_sanitized(self):
        hostile = type("K@evil <- forged", (), {})()

        rendered = safe_callable_name(hostile)

        assert "@" not in rendered
        assert " <- " not in rendered

    def test_partial_branch_is_sanitized(self):
        import functools

        def target():
            pass

        target.__qualname__ = "evil@name"
        target.__name__ = "evil@name"

        rendered = safe_callable_name(functools.partial(target))

        assert rendered.startswith("partial(")
        assert "@" not in rendered

    def test_never_raises_on_a_hostile_object(self):
        class Exploding:
            def __getattr__(self, name):
                raise RuntimeError("working outside of request context")

        # A logging call site must not fail on the thing it describes.
        assert isinstance(safe_callable_name(Exploding()), str)


class TestChainCapArithmetic:
    """F5: a zero cap means NO links, not every link."""

    def test_zero_cap_renders_no_links(self, monkeypatch):
        # `links[-0:]` is `links[0:]` -- the whole list. Measured pre-fix with
        # a cap of 0: 12 links rendered while announcing all were dropped.
        # This is the N3 bug class (`limit=0` rendered EVERY frame) recurring in
        # the sibling slice 22 lines away.
        monkeypatch.setattr(sl, "_MAX_CHAIN_LINKS", 0)

        exc = ValueError("innermost")
        for index in range(10):
            try:
                raise RuntimeError(f"wrapper-{index}") from exc
            except Exception as wrapped:
                exc = wrapped

        rendered = safe_exception_frames(exc)

        assert " <- " not in rendered


class TestChainCapDocstringMatchesBehaviour:
    """F2: the docstring's absolute claim was false; pin what is TRUE.

    The claim "the root cause always survives truncation" does not hold. The cap
    keeps a fixed window at the INNERMOST end, which is symmetric: an attacker
    who lengthens the chain at that end evicts the other. `__context__` is
    chained implicitly whenever an exception is raised while another is handled,
    so an in-handler retry recursion grows the chain inward.

    This pins the REAL behaviour so the docstring cannot drift back to the
    absolute. If someone later bounds the walk from the other end, this reds and
    the docstring must be re-read -- which is the correct place for that
    conversation.
    """

    def test_outermost_failure_is_evicted_by_inner_context_chaining(self):
        def retry(depth):
            try:
                raise ValueError(f"attempt-{depth}")
            except Exception:
                if depth:
                    return retry(depth - 1)
                raise

        # pytest.raises rather than a bare try/except: if the construction ever
        # stops raising, this fails loudly instead of leaving `rendered` unbound
        # and erroring somewhere less legible.
        with pytest.raises(KeyError) as caught:
            try:
                retry(sl._MAX_CHAIN_LINKS + 5)
            except Exception:
                raise KeyError("REAL_FAILURE")

        rendered = safe_exception_frames(caught.value, limit=1)

        # The failure that actually propagated is NOT in the record.
        assert "KeyError" not in rendered
        # ...and the loss is announced rather than silent.
        assert "outer links dropped" in rendered

    def test_wrapper_chain_keeps_the_root_cause(self):
        """The half the docstring CAN promise: outer wrappers cannot evict."""
        exc = ValueError("ROOT_CAUSE")
        for index in range(sl._MAX_CHAIN_LINKS * 3):
            try:
                raise RuntimeError(f"wrapper-{index}") from exc
            except Exception as wrapped:
                exc = wrapped

        rendered = safe_exception_frames(exc, limit=1)

        assert "ValueError" in rendered
        assert "outer links dropped" in rendered
