"""Round-10 redteam pins: the SINK side, and the helper's totality.

Round 9 hardened `safe_exception_frames` / `safe_callable_name`. Round 10's
adversarial security lens found that hardening the HELPER left the SINK open:
nine call sites logged `type(exc).__name__` RAW as a sibling `%s` in the SAME
log call, so a sanitized field and an unsanitized copy of the same identifier
landed four characters apart in one record.

Measured before the fix, which is the whole point of this module:

    'Channel c: event task failed during cleanup: A\\nERROR fake-log-line
     at A?ERROR?fake-log-line@...'
                              ^ helper field, sanitized
     ^ sink field, raw -- real newline in the record

That is the fifth consecutive round in which a fix carried a defect of the class
it was written to close. The pattern is worth naming: each fix hardened the layer
it was looking at, and the next round found the same class one layer over.
"""

import pytest

import kailash.utils.secure_logging as sl
from kailash.utils.secure_logging import safe_callable_name, safe_exception_frames

try:
    from kailash.utils.secure_logging import safe_type_name
except ImportError:  # pragma: no cover - only on a tree predating the fix
    # Deliberate: a module-level import of the new symbol would make this file
    # fail COLLECTION against a pre-fix tree, and an ImportError is zero
    # evidence about the behaviour these pins measure. The shim reproduces the
    # PRE-FIX sink (a raw `type(obj).__name__`) so every test below reds on the
    # BEHAVIOUR it names, which is what makes the fail-first run readable.
    def safe_type_name(obj: object) -> str:
        return type(obj).__name__


class TestSinkSideTypeNameIsSanitized:
    """F1: `safe_type_name` closes the raw sibling-field channel."""

    def test_newline_cannot_reach_a_record_through_the_type_field(self):
        exc_type = type("A\nERROR fake-log-line", (Exception,), {})
        try:
            raise exc_type("boom")
        except Exception as exc:
            # The exact caller shape from channels/base.py.
            record = "Channel %s: event task failed during cleanup: %s at %s" % (
                "c",
                safe_type_name(exc),
                safe_exception_frames(exc, limit=3),
            )

        assert "\n" not in record
        assert "\r" not in record

    def test_type_field_is_bounded(self):
        exc_type = type("Z" * 5000, (Exception,), {})
        try:
            raise exc_type("boom")
        except Exception as exc:
            rendered = safe_type_name(exc)

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")

    def test_type_field_cannot_forge_the_record_grammar(self):
        exc_type = type("Evil <- FORGED@a.py:1:f", (Exception,), {})
        try:
            raise exc_type("boom")
        except Exception as exc:
            rendered = safe_type_name(exc)

        assert " <- " not in rendered
        assert "@" not in rendered

    def test_safe_type_name_never_raises(self):
        class Hostile:
            @property
            def __class__(self):
                raise RuntimeError("no type for you")

        # Called from inside except blocks -- raising would REPLACE the handled
        # exception, which is the failure this totality guard exists to prevent.
        assert isinstance(safe_type_name(Hostile()), str)

    def test_no_helper_sink_still_logs_a_raw_type_name(self):
        """Mechanical sweep: the nine sites stay closed.

        A behavioural pin cannot see a NEW sink added later, so this asserts the
        absolute state of the tree rather than the diff -- the `agents.md`
        mechanical-sweep shape. `base_async.py:304` is the one known exclusion:
        it is an exception MESSAGE (not a log record) and separately embeds the
        full `{e}`, which belongs to the runtime-hot-path shard, not here.
        """
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2] / "src" / "kailash"
        sink_files = [
            "channels/base.py",
            "nodes/base_async.py",
            "runtime/distributed.py",
            "runtime/durable.py",
            "runtime/scheduler.py",
            "utils/lifespan.py",
            "visualization/api.py",
        ]
        pattern = re.compile(
            r"type\((exc|e|error|err|task_error|previous_error)\)\.__name__"
        )
        offenders = []
        for rel in sink_files:
            path = root / rel
            if not path.exists():
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    if rel == "nodes/base_async.py" and "execution failed" in line:
                        continue  # documented exclusion above
                    offenders.append(f"{rel}:{number}")

        assert not offenders, f"raw type-name sinks reappeared: {offenders}"


class TestHelperTotality:
    """F3: the walk reads descriptors a subclass can shadow."""

    def test_a_shadowed_cause_descriptor_does_not_escape(self):
        """The outcome is reduced to a plain string BEFORE any assert.

        Necessary, not stylistic: on a pre-fix tree the helper raises, and
        pytest's own failure rendering builds a `TracebackException`, which
        re-reads `__cause__` on the propagating exception -- re-entering the
        shadowed property and taking the RUNNER down with an INTERNALERROR that
        aborts the whole session. Measured while writing this pin. Catching here
        and comparing a string keeps the fail-first run readable, and is itself
        evidence of how far this vector reaches.
        """

        def raiser(self):
            raise RuntimeError("gotcha")

        exc_type = type("E", (Exception,), {"__cause__": property(raiser)})
        try:
            raise exc_type("boom")
        except Exception as exc:
            try:
                outcome = safe_exception_frames(exc)
            except Exception as leak:
                outcome = f"RAISED:{type(leak).__name__}"

        assert outcome == "<frames-unavailable>", outcome

    def test_the_normal_path_is_unaffected(self):
        try:
            raise ValueError("normal")
        except Exception as exc:
            rendered = safe_exception_frames(exc, limit=1)

        assert "ValueError@" in rendered
        assert rendered != "<frames-unavailable>"


class TestCPythonPseudoIdentifiers:
    """F5: keep the diagnostic without re-opening a forgery channel."""

    @pytest.mark.parametrize(
        "literal",
        ["<module>", "<lambda>", "<listcomp>", "<genexpr>", "<string>"],
    )
    def test_cpython_literals_survive_intact(self, literal):
        assert sl._safe_identifier(literal) == literal

    def test_a_near_miss_does_not_survive(self):
        """Exact-match is what keeps the passthrough safe.

        `!listcomp!` previously rendered `?listcomp?` -- byte-identical to what a
        GENUINE listcomp frame degraded to, so our own label was forgeable. It
        must not now render as `<listcomp>` either.
        """
        rendered = sl._safe_identifier("!listcomp!")

        assert rendered != "<listcomp>"
        assert "<" not in rendered and ">" not in rendered


class TestBoundHoldsAgainstALyingLength:
    """F2: REFUTED by measurement, pinned so it stays refuted.

    `isinstance(value, str)` admits a SUBCLASS, and `len` is overridable, so a
    lying `__len__` could in principle decide the truncation branch. It cannot:
    `re.sub` returns a plain `str` copy for a subclass input, so `cleaned` is a
    real `str` and `len` is the builtin. This pins the property, not the reason —
    if a future refactor drops the `sub` for an all-safe fast path, this reds.
    """

    def test_a_lying_len_str_subclass_cannot_defeat_the_bound(self):
        class Lying(str):
            def __len__(self):
                return 5

        def target():
            pass

        target.__qualname__ = Lying("A" * 5000)
        target.__name__ = Lying("A" * 5000)

        rendered = safe_callable_name(target)

        assert len(rendered) <= sl._MAX_IDENTIFIER_CHARS + len("<truncated>")


class TestGetattrRouteIsGenuinelyExercised:
    """F4: the round-9 pin's assertions were satisfiable without the payload.

    The lens flagged that `"@" not in rendered` and `"/" in rendered or "?" in
    rendered` both hold for the CLASS's own qualname, so the test would pass even
    if `__getattr__` never fired. Measured: the route DOES fire
    (`'__qualname__' in Hostile.__dict__` is False). Pinning it decisively —
    assert the payload's own characters, so only the payload path can satisfy it.
    """

    def test_the_payload_itself_is_what_gets_sanitized(self):
        class Hostile:
            def __getattr__(self, name):
                if name in ("__qualname__", "__name__"):
                    return "postgres://svc:hunter2@h/db"
                raise AttributeError(name)

        rendered = safe_callable_name(Hostile())

        # Only the payload route can produce this: the class's own qualname
        # contains neither "hunter2" nor a mangled "://".
        assert "hunter2" in rendered, f"payload route did not fire: {rendered!r}"
        assert "@" not in rendered
        assert "://" not in rendered
