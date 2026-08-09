"""A log-sink scanner for the ``kailash-kaizen`` tree.

WHY THIS EXISTS
---------------
``kaizen-agents`` has a sink scanner
(``kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py``),
and it cannot help this package at all: its enumeration root is
``SRC / "kaizen_agents"``, so it never opens a ``kailash-kaizen`` file. Any
coverage claim over THIS tree therefore had no instrument behind it.

It also could not have found the eight sites the F11 sweep fixed, for a reason
worth stating precisely: that scanner anchors on an EXCEPT HANDLER's bound
exception name, and the F11 leak had nothing to do with exceptions. The leaking
value was a CALLER-REGISTERED CALLABLE rendered by a ``%r`` in a format string
-- no ``repr(`` token in the source, no exception involved, nothing for a
handler-anchored scanner to bind to.

So this scanner covers TWO families, because this tree has both:

* **Family A -- object rendering.** ``repr(x)``, ``%r`` in a log format string,
  ``!r`` in a log f-string. The F11 class.
* **Family B -- exception text.** ``str(e)`` / f-string ``{e}``, the lazy
  ``%s`` argument, ``exc_info=`` / ``logger.exception``, ``format_exc()``, and
  exception ATTRIBUTES. The F10 class.
* **Family C -- assignment-then-log.** Either family's rendering bound to a
  local first and logged on a later line. This is the form BOTH prior scanners
  are structurally blind to, because it needs assignment tracking rather than
  syntactic matching.

WHAT THIS INSTRUMENT IS, AND IS NOT
-----------------------------------
It is an INVENTORY instrument: it enumerates and pins. It is deliberately NOT
the same contract as the in-file guards in
``test_f11_caller_repr_does_not_leak.py``, which are merge-gating and therefore
kept narrow enough that they never red on correct code. A gate that reds on
correct code gets scoped down or deleted by the first person it blocks.

An inventory instrument has the opposite bias: it FAILS TOWARD FLAGGING, so an
unrecognised shape is a finding rather than a silent pass. "Silently counted as
swept" is the exact defect this whole wave exists to close. Benign findings are
absorbed by an EXPLICIT, REASONED baseline below -- never by narrowing a
detector, which would make the instrument blind rather than quiet.

NAMED GAP -- exception-as-VALUE is NOT covered
----------------------------------------------
An exception arriving as a VALUE rather than via ``except ... as e`` -- the
``asyncio.gather(return_exceptions=True)`` shape -- is NOT detected here. The
sibling scanner solves it with three package-specific "region producers"; the
equivalent producers for this tree have not been enumerated, and guessing at
them would produce an instrument that reports green on a class it cannot see.
Recorded as a gap rather than closed badly. See ``test_the_named_gap_is_real``,
which PINS the gap by asserting the scanner is blind to it -- so if someone
later teaches the shape, that test reds and this docstring gets corrected
instead of silently drifting.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

import kaizen

pytestmark = pytest.mark.regression

PKG = Path(kaizen.__file__).parent
EXCLUDED_PARTS = {"build", "tests", "examples", "__pycache__"}

#: Standard ``logging.Logger`` emit methods, matched on the ATTRIBUTE name so
#: ``logger.error``, ``self.logger.error`` and
#: ``logging.getLogger(__name__).error`` are all recognised without modelling
#: how each module happens to bind its logger.
_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)

#: Helpers that render an object SAFELY -- by construction, not by filtering.
#: A call to one of these is not a finding. Kept deliberately short: every entry
#: is a function whose return value cannot carry caller state.
_SAFE_NAME_HELPERS = frozenset({"safe_handler_name", "_safe_listener_name"})

#: Attributes that yield a scalar identifier rather than a rendering. Reading
#: one of these off ANY object is safe: they are set at ``def``/``class`` time
#: or are framework-assigned identifiers.
_SAFE_NAME_ATTRS = frozenset({"__name__", "__qualname__"})

#: Credential scrubbers. An exception routed through one of these is covered.
_SCRUB_HELPERS = frozenset(
    {"scrub_remote_error", "scrub_local_error", "scrub_credentials"}
)

#: Exception attributes that do NOT carry the exception's message text. Behind
#: an allowlist so an UNANTICIPATED attribute defaults to FLAGGED rather than to
#: silence -- the fail-toward-flagging rule, applied at the narrowest point
#: where it actually bites.
_SAFE_EXC_ATTRS = frozenset({"__class__", "errno", "winerror", "returncode", "status"})


# ---------------------------------------------------------------------------
# Baseline -- explicit, reasoned, never a silent exclusion
# ---------------------------------------------------------------------------
#: Findings that are real detections but correct code, each with the reason it
#: is benign. Keyed by ``"<relative path>:<lineno>"``.
#:
#: This is the ONLY sanctioned way to quiet a finding. Narrowing a detector to
#: make a benign site disappear is BLOCKED: it makes the instrument blind to the
#: whole shape, not just to that site.
BENIGN: dict[str, str] = {}


def _source_files() -> list[Path]:
    return [
        p
        for p in sorted(PKG.rglob("*.py"))
        if not (EXCLUDED_PARTS & set(p.relative_to(PKG).parts))
    ]


# ---------------------------------------------------------------------------
# The scanner
# ---------------------------------------------------------------------------
class _Finding:
    __slots__ = ("path", "lineno", "shape", "detail")

    def __init__(self, path: str, lineno: int, shape: str, detail: str) -> None:
        self.path = path
        self.lineno = lineno
        self.shape = shape
        self.detail = detail

    @property
    def key(self) -> str:
        return f"{self.path}:{self.lineno}"

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return f"{self.key} [{self.shape}] {self.detail}"


def _is_log_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _LOG_METHODS
    )


def _renders_safely(node: ast.AST) -> bool:
    """True when the expression cannot carry caller state BY CONSTRUCTION."""
    if isinstance(node, ast.Constant):
        return True
    # ``safe_handler_name(x)`` / ``_safe_listener_name(x)``
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _SAFE_NAME_HELPERS
    ):
        return True
    # ``type(x).__name__`` and any ``<expr>.__name__`` / ``.__qualname__``
    if isinstance(node, ast.Attribute) and node.attr in _SAFE_NAME_ATTRS:
        return True
    # ``scrub_*(e)``
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _SCRUB_HELPERS
    ):
        return True
    return False


class _SinkScan(ast.NodeVisitor):
    """Walk ONE function body, tracking renderings that reach a log record.

    Scoped per-function because family C needs assignment tracking, and a
    name bound in one function says nothing about the same name in another.
    """

    def __init__(self, path: str, exc_names: frozenset[str]) -> None:
        self.path = path
        self.exc_names = exc_names
        self.findings: list[_Finding] = []
        #: ``local name -> (lineno, shape, detail)`` for family C. Populated by
        #: assignments whose VALUE is a rendering; consumed when the name later
        #: reaches a logging call.
        self.tainted: dict[str, tuple[int, str, str]] = {}

    # -- helpers ---------------------------------------------------------
    def _flag(self, lineno: int, shape: str, detail: str) -> None:
        self.findings.append(_Finding(self.path, lineno, shape, detail))

    def _is_exc_name(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in self.exc_names

    def _rendering_shape(self, node: ast.AST) -> tuple[str, str] | None:
        """Classify an expression as a rendering, or return None.

        Returns ``(shape, detail)``. Used both for the direct case (the
        expression sits in a logging call) and for family C (it is bound to a
        local first).
        """
        if _renders_safely(node):
            return None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "repr":
                return ("A1-repr-call", "repr() of an object")
            if node.func.id == "str" and node.args and self._is_exc_name(node.args[0]):
                return ("B1-str-exc", "str() of a caught exception")
        # ``traceback.format_exc()`` / a bare ``format_exc()``
        if isinstance(node, ast.Call):
            fname = (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", None)
            )
            if fname == "format_exc":
                return ("B4-format-exc", "traceback.format_exc()")
        # f-string containing ``{e}`` or any ``!r`` conversion
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                if not isinstance(value, ast.FormattedValue):
                    continue
                if value.conversion == 114 and not _renders_safely(value.value):
                    return ("A3-fstring-bang-r", "f-string !r conversion")
                if self._is_exc_name(value.value):
                    return ("B1-fstring-exc", "f-string interpolating an exception")
                inner = self._rendering_shape(value.value)
                if inner is not None:
                    return inner
        # ``e.args`` / ``e.message`` / any non-allowlisted exception attribute
        if (
            isinstance(node, ast.Attribute)
            and self._is_exc_name(node.value)
            and node.attr not in _SAFE_EXC_ATTRS
        ):
            return ("B6-exc-attribute", f"exception attribute .{node.attr}")
        # ``"failed: " + str(e)`` -- concatenation is a rendering if either
        # side is. Recursing here is what catches the oldest shape of all,
        # which is otherwise invisible when it sits in the format-string slot.
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                inner = self._rendering_shape(side)
                if inner is not None:
                    return inner
        return None

    # -- family C: assignment tracking ------------------------------------
    def visit_Assign(self, node: ast.Assign) -> None:
        shape = self._rendering_shape(node.value)
        if shape is not None:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.tainted[target.id] = (node.lineno, shape[0], shape[1])
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and isinstance(node.target, ast.Name):
            shape = self._rendering_shape(node.value)
            if shape is not None:
                self.tainted[node.target.id] = (node.lineno, shape[0], shape[1])
        self.generic_visit(node)

    # -- the sinks ---------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        if _is_log_call(node):
            self._inspect_log_call(node)
        self.generic_visit(node)

    def _inspect_log_call(self, node: ast.Call) -> None:
        assert isinstance(node.func, ast.Attribute)  # guarded by _is_log_call

        # B3a -- ``logger.exception`` always sets exc_info.
        if node.func.attr == "exception":
            self._flag(node.lineno, "B3-traceback", "logger.exception sets exc_info")
        # B3b -- an explicit truthy ``exc_info``.
        for kw in node.keywords:
            if kw.arg == "exc_info" and not (
                isinstance(kw.value, ast.Constant) and not kw.value.value
            ):
                self._flag(node.lineno, "B3-traceback", "exc_info= is truthy")

        for index, arg in enumerate(node.args):
            # A2 -- ``%r`` in the format string. Only args[0] is a format
            # string; a ``%r`` in a later argument is data, not a conversion.
            if (
                index == 0
                and isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
            ):
                if "%r" in arg.value:
                    self._flag(node.lineno, "A2-percent-r", "log format uses %r")
                # A plain constant format string holds nothing else to inspect.
                continue
            # B2 -- the exception handed over as a lazy ``%s`` argument.
            if self._is_exc_name(arg):
                self._flag(arg.lineno, "B2-bare-arg", "raw exception as a log argument")
                continue
            # C -- a previously-tainted local reaching the sink, directly...
            if isinstance(arg, ast.Name) and arg.id in self.tainted:
                self._flag_tainted(arg.lineno, arg.id)
                continue
            # ...or interpolated into an f-string in any argument slot.
            if isinstance(arg, ast.JoinedStr):
                for value in arg.values:
                    if (
                        isinstance(value, ast.FormattedValue)
                        and isinstance(value.value, ast.Name)
                        and value.value.id in self.tainted
                    ):
                        self._flag_tainted(arg.lineno, value.value.id)
            # Every remaining slot -- INCLUDING args[0] when it is an f-string
            # or a concatenation -- goes through the same rendering check.
            shape_detail = self._rendering_shape(arg)
            if shape_detail is not None:
                self._flag(arg.lineno, shape_detail[0], shape_detail[1])

    def _flag_tainted(self, lineno: int, name: str) -> None:
        bound_at, shape, detail = self.tainted[name]
        self._flag(
            lineno,
            f"C-via-local/{shape}",
            f"{detail}, bound at line {bound_at}, logged here",
        )


def _exception_names(tree: ast.AST) -> frozenset[str]:
    """Every name bound by an ``except ... as <name>`` in this tree."""
    return frozenset(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.name
    )


def scan_source(src: str, path: str = "<memory>") -> list[_Finding]:
    """Scan one module's source. The scanner's single entry point."""
    tree = ast.parse(src, filename=path)
    exc_names = _exception_names(tree)
    findings: list[_Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            scan = _SinkScan(path, exc_names)
            for stmt in node.body:
                scan.visit(stmt)
            findings.extend(scan.findings)
    # A node is visited once per enclosing scope, so dedupe on identity of
    # (line, shape) -- a nested function's finding would otherwise be counted
    # by both its own scope and its parent's walk.
    seen: set[tuple[int, str]] = set()
    unique: list[_Finding] = []
    for finding in findings:
        marker = (finding.lineno, finding.shape)
        if marker in seen:
            continue
        seen.add(marker)
        unique.append(finding)
    return sorted(unique, key=lambda f: (f.lineno, f.shape))


def scan_tree() -> list[_Finding]:
    out: list[_Finding] = []
    for path in _source_files():
        rel = str(path.relative_to(PKG))
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            pytest.fail(f"{rel}: unreadable, so it cannot be reported swept: {exc}")
        for finding in scan_source(src, rel):
            if finding.key in BENIGN:
                continue
            out.append(finding)
    return out


# ---------------------------------------------------------------------------
# An UNTAUGHT baseline, to establish the RED per shape
# ---------------------------------------------------------------------------
class _UntaughtScan(ast.NodeVisitor):
    """What a naive scanner sees: ``str(e)`` / f-string ``{e}`` only.

    This exists so each taught shape can be shown to be a real ADDITION rather
    than asserted to be one. The sibling scanner established its RED by
    extracting its own prior version with ``git show HEAD:``; this scanner has
    no prior version, so the pre-teaching state is reconstructed explicitly.
    Shape 1 is the reconstruction target because it is what every first-version
    sink scanner in this repo has implemented.
    """

    def __init__(self, exc_names: frozenset[str]) -> None:
        self.exc_names = exc_names
        self.hits: list[int] = []

    def _is_exc(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in self.exc_names

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and node.args
            and self._is_exc(node.args[0])
        ):
            self.hits.append(node.lineno)
        self.generic_visit(node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if self._is_exc(node.value):
            self.hits.append(node.lineno)
        self.generic_visit(node)


def scan_untaught(src: str) -> list[int]:
    tree = ast.parse(textwrap.dedent(src))
    scan = _UntaughtScan(_exception_names(tree))
    scan.visit(tree)
    return scan.hits


# ---------------------------------------------------------------------------
# Fixtures -- one leaking and one clean per shape
# ---------------------------------------------------------------------------
def _wrap(body: str, *, in_handler: bool = True) -> str:
    if in_handler:
        return "def f():\n    try:\n        pass\n    except Exception as e:\n" + body
    return "def f():\n" + body


#: ``(label, source, expects_untaught_blindness)``. The third element records
#: whether the naive baseline is blind to the shape -- shape B1 is the one the
#: baseline DOES see, and saying so keeps the RED evidence honest rather than
#: claiming every shape is a new addition.
LEAKING_FIXTURES = [
    ("A1-repr-call", _wrap('        logger.error("f: %s", repr(handler))'), True),
    (
        "A2-percent-r",
        _wrap('        logger.error("Listener %r failed", listener)'),
        True,
    ),
    ("A3-fstring-bang-r", _wrap('        logger.error(f"failed: {handler!r}")'), True),
    ("B1-str-exc", _wrap('        logger.error("f: " + str(e))'), False),
    ("B1-fstring-exc", _wrap('        logger.error(f"failed: {e}")'), False),
    ("B2-bare-arg", _wrap('        logger.error("failed: %s", e)'), True),
    ("B3-logger-exception", _wrap('        logger.exception("failed")'), True),
    ("B3-exc-info", _wrap('        logger.error("failed", exc_info=True)'), True),
    (
        "B4-format-exc",
        _wrap('        logger.error("f: %s", traceback.format_exc())'),
        True,
    ),
    ("B6-exc-attribute", _wrap('        logger.error("f: %s", e.args)'), True),
    (
        "C-assign-then-log",
        _wrap('        detail = repr(handler)\n        logger.error("f: %s", detail)'),
        True,
    ),
    (
        "C-assign-format-exc-then-log",
        _wrap('        tb = traceback.format_exc()\n        logger.error("f: %s", tb)'),
        True,
    ),
]

#: Near-misses that MUST NOT flag. Without these the suite would pass just as
#: well against a scanner that flags everything, which is a different way of
#: being uninformative.
CLEAN_FIXTURES = [
    ("scrubbed-exc", _wrap('        logger.error("f: %s", scrub_remote_error(e))')),
    ("safe-helper", _wrap('        logger.error("f: %s", safe_handler_name(handler))')),
    ("type-name", _wrap('        logger.error("f: %s", type(handler).__name__)')),
    ("dunder-qualname", _wrap('        logger.error("f: %s", fn.__qualname__)')),
    ("exc-info-false", _wrap('        logger.error("f", exc_info=False)')),
    ("plain-scalar-arg", _wrap('        logger.error("f: %s", event_type)')),
    ("allowlisted-exc-attr", _wrap('        logger.error("f: %s", e.errno)')),
    # A rendering that never reaches a log record is not a sink.
    ("repr-not-logged", _wrap("        detail = repr(handler)\n        return detail")),
    # ``!r`` outside a logging call -- the ValueError shape in event_hooks.py.
    (
        "bang-r-in-raise",
        _wrap('        raise ValueError(f"bad key {key!r}")', in_handler=False),
    ),
]


class TestTheScannerSeesEachShape:
    """The coverage instrument is itself covered, in both polarities."""

    @pytest.mark.parametrize(
        "label, src, _blind", LEAKING_FIXTURES, ids=[f[0] for f in LEAKING_FIXTURES]
    )
    def test_each_leaking_shape_is_flagged(self, label, src, _blind):
        assert scan_source(src), f"scanner is blind to the {label!r} shape"

    @pytest.mark.parametrize(
        "label, src", CLEAN_FIXTURES, ids=[f[0] for f in CLEAN_FIXTURES]
    )
    def test_each_clean_shape_is_not_flagged(self, label, src):
        assert not scan_source(src), f"false positive on {label!r}: {scan_source(src)}"


class TestTheRedIsEstablishedPerShape:
    """Each taught shape is shown to be an ADDITION, not asserted to be one.

    ``instrument-discipline`` MUST-2: a green that was never shown to red is not
    evidence. For every shape the naive baseline cannot see, this asserts the
    baseline is BLIND and the taught scanner DETECTS -- the two halves that
    together make the teaching real.
    """

    @pytest.mark.parametrize(
        "label, src, blind_untaught",
        LEAKING_FIXTURES,
        ids=[f[0] for f in LEAKING_FIXTURES],
    )
    def test_untaught_baseline_versus_taught_scanner(self, label, src, blind_untaught):
        untaught = scan_untaught(src)
        taught = scan_source(src)
        assert taught, f"taught scanner missed {label!r}"
        if blind_untaught:
            assert not untaught, (
                f"{label!r} was NOT a new addition -- the naive baseline already "
                f"saw it at line(s) {untaught}; the RED claim for this shape is "
                f"overstated and the fixture table must be corrected"
            )
        else:
            assert untaught, (
                f"{label!r} is recorded as visible to the naive baseline, but the "
                f"baseline did not see it; the fixture table is wrong"
            )


def test_the_named_gap_is_real():
    """PIN the exception-as-VALUE gap this scanner does NOT close.

    The module docstring records that an exception arriving as a VALUE (the
    ``gather(return_exceptions=True)`` shape) is not detected. A documented gap
    that is not pinned drifts: someone teaches the shape, the docstring keeps
    claiming blindness, and the next reader trusts the wrong description. This
    reds when the gap closes, forcing the docstring to be corrected.
    """
    src = _wrap(
        "        results = await gather(*tasks, return_exceptions=True)\n"
        "        for result in results:\n"
        "            if isinstance(result, BaseException):\n"
        '                logger.error("failed: %s", result)',
        in_handler=False,
    )
    assert not scan_source(src), (
        "the exception-as-VALUE shape is now detected -- update the module "
        "docstring's NAMED GAP section, which still claims blindness"
    )


class TestTheF11SweptFilesAreClean:
    """The four files this shard owns carry no finding, by this instrument.

    Scoped to the shard's own partition. A tree-wide zero assertion is
    deliberately NOT made here: the rest of the tree is other shards' territory,
    and an assertion this shard cannot make green would be an instrument that
    can never reach its own success state -- which teaches its operator to
    dismiss it. The tree-wide inventory is reported, not gated.
    """

    @pytest.mark.parametrize(
        "relative",
        [
            "l3/event_hooks.py",
            "core/autonomy/hooks/manager.py",
            "core/autonomy/hooks/security/isolation.py",
            "core/autonomy/hooks/security/rate_limiting.py",
        ],
    )
    def test_swept_file_has_no_finding(self, relative):
        path = PKG / relative
        findings = [
            f
            for f in scan_source(path.read_text(encoding="utf-8"), relative)
            if f.key not in BENIGN
        ]
        assert not findings, f"{relative}: {findings}"


def test_the_scanner_actually_opens_this_tree():
    """Anti-vacuity: a scanner whose enumeration is empty reports green forever.

    This is the failure mode that made the ``kaizen-agents`` scanner unable to
    help this package -- its root simply did not contain these files. Asserting
    a non-trivial file count is what makes every other green in this module
    mean something.
    """
    files = _source_files()
    assert len(files) > 200, f"enumeration collapsed to {len(files)} files"
    assert (PKG / "l3" / "event_hooks.py") in files
