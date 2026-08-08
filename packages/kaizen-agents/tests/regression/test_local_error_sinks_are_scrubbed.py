# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Every local exception-text sink in ``kaizen_agents`` is credential-scrubbed.

WHAT LANDED, AND WHY IT IS NOT THE SWEEP THAT WAS HALTED
--------------------------------------------------------
A first attempt would have routed these sites through ``scrub_credentials`` in
its DEFAULT (aggressive) mode. That was halted, because the default is not a
no-op on ordinary text: it rewrites ``$HOME`` paths, 40-char contiguous runs
(git SHAs, long CamelCase identifiers), 32+ hex runs (MD5 digests, unhyphenated
UUID/trace ids) and Azure resource names. Those bytes are incidental noise in a
provider error body and load-bearing diagnostics in a LOCAL one — an ``OSError``
message IS a path plus a reason, and it is read by an LLM deciding its retry.
See ``kailash-kaizen``'s ``test_scrub_credentials_ordinary_text_is_not_noop``.

So the helper's contract was split instead. ``scrub_local_error`` is
``scrub_credentials`` with ``redact_paths=False, redact_opaque_tokens=False``:
only the rules anchored on a literal that cannot occur outside a credential
(``sk-``, ``AKIA``, ``ASIA``, ``ghp_``, ``hf_``, ``fw_``, ``xox?-``,
``sk_live_``, ``sig=``, ``Bearer``, bare JWTs) plus URL-userinfo / DSN
credentials. That combination is a measured no-op across the credential-free
corpus, which is what makes this sweep safe where the aggressive one was not.

THEN THE SPLIT ITSELF TURNED OUT TO BE ONE DESTINATION SHORT
------------------------------------------------------------
Routing ALL ~180 sinks onto the conservative preset fixed the diagnostic
problem and introduced a CREDENTIAL one. Turning ``redact_opaque_tokens`` off
disables the only two rules that discriminate on shape alone, and those are the
only rules that can claim a credential carrying NO vendor prefix:

* a bare **AWS secret access key** (``wJalrXUtnFEMI/K7…``), and
* a bare **32+ char hex secret** — the **Azure OpenAI ``api-key`` shape**.

No literal-anchored rule matches either. So on any sink whose exception can be
raised at an HTTP / SDK / subprocess / provider boundary — and many swept sinks
are exactly that, e.g. ``runtime_adapters/kaizen_local.py`` rendering an
exception from a caller-injected ``_llm_provider`` — the sweep replaced a path
disclosure with a live-credential disclosure.

``scrub_remote_error`` is the second destination: opaque tokens ON, paths still
OFF. Every sink was re-triaged by where its exception can be RAISED (not where
it is caught), fail-closed — 162 remote, 18 local. ``TestThePresetSplitIsReal``
pins that the two presets genuinely differ, so the routing cannot quietly
become decorative.

WHAT THIS FILE PINS
-------------------
Four tiers, and the first two are what make the last two generalise:

1. ``test_no_unwrapped_exception_text_sink_remains`` — per module, an AST pass
   re-derives the sink set from source and asserts NONE is unwrapped. This is
   the coverage instrument: it reds if a site is reverted AND if a NEW
   unscrubbed sink is added later.
2. ``test_module_binds_the_canonical_preset`` — per module, the imported
   ``scrub_local_error`` is the SAME object as the one in
   ``kaizen.utils.credential_scrub``, so no module can drift onto a local copy.
3. ``test_credential_scrubbed_and_path_survives`` — per module, the symbol that
   module will actually invoke redacts a credential and leaves an ``OSError``
   filename byte-identical. (1) + (2) + (3) compose to a per-module behavioural
   claim about every one of that module's sinks.
4. The agent-facing tool sinks named in the halt report — ``file_read``,
   ``file_write``, ``file_edit``, ``bash_tool``, ``glob_tool``, ``grep_tool``
   — driven END TO END through ``Tool.execute``, asserting on the real
   ``ToolResult`` the model would receive.

``patterns/discovery.py`` was scrubbed earlier, under the aggressive default, by
a different change, and is left that way. Tier 1 recognises that form too, so it
is covered without a hand-maintained exclusion; Tiers 2-4 do not see it because
it does not use the conservative preset.
"""

from __future__ import annotations

import ast
import importlib
import textwrap
from pathlib import Path

import pytest

from kaizen.utils.credential_scrub import scrub_local_error, scrub_remote_error

pytestmark = pytest.mark.regression

SRC = Path(__file__).resolve().parents[2] / "src"
PKG = SRC / "kaizen_agents"

#: BOTH conservative presets, because the sweep now has two destinations.
#:
#: This was a single ``HELPER = "scrub_local_error"``, and that single name is
#: what made the original sweep unsafe: it routed EVERY sink — including ones
#: whose exception is raised at an HTTP / provider / subprocess boundary — onto
#: the preset that switches the two SHAPE-ONLY rules OFF. Those two rules are
#: the ONLY ones that claim a credential carrying no vendor prefix (a bare AWS
#: secret access key, a bare 32+ hex run — the Azure OpenAI ``api-key`` shape),
#: so on a remote sink the sweep closed a path disclosure and opened a
#: credential one.
#:
#: ``scrub_remote_error`` is the sibling preset for those sinks: opaque tokens
#: ON, paths still OFF. Both are counted as covered here; which one a given
#: module must use is a property of where its exception can be RAISED, and is
#: pinned per-preset by ``TestThePresetSplitIsReal`` below.
HELPERS = ("scrub_local_error", "scrub_remote_error")

#: name -> the canonical function object, for the no-drift check.
CANONICAL_BY_NAME = {
    "scrub_local_error": scrub_local_error,
    "scrub_remote_error": scrub_remote_error,
}

#: The AGGRESSIVE entry point. ``patterns/discovery.py`` was routed through it
#: by an earlier, separate change and is deliberately left that way. Tier 1
#: recognises it as scrubbed, so ``discovery.py`` needs no special case and
#: still cannot regain a bare sink unnoticed; it is absent from the Tier 2/3
#: parametrisation as a CONSEQUENCE of not using the conservative preset, not
#: as a hand-maintained exclusion.
AGGRESSIVE_HELPER = "scrub_credentials"

EXCLUDED_PARTS = {"build", "tests", "examples", "__pycache__"}

#: Measured surface, reproduced by ``_enumerate`` below. Pinned so the
#: parametrisation cannot silently shrink to nothing and still report green.
#:
#: 51 -> 53 files, 180 -> 185 sites: the traceback-releak sweep routed five
#: previously-bare sinks through the conservative preset. Two of the files had
#: no scrubbed sink at all before it, which is what moves the FILE count:
#:   delegate/delegate.py  +1 (new to the swept set)
#:   delegate/loop.py      +2 (new to the swept set)
#:   delegate/print_mode.py +1 (already swept; the log line beside an
#:                              already-scrubbed return was still bare)
#:   delegate/mcp.py       +1 (already swept; the reader-error sink was the
#:                              only bare one left in that module)
#:
#: 53 -> 57 files, 185 -> 191 sites: teaching ``_SinkScan`` shapes 2 and 3 (see
#: its docstring) surfaced SIX bare sinks in FOUR files that no previous pass --
#: neither the #1970 sweep nor a `grep exc_info|logger.exception` -- could see,
#: because all six are the lazy ``%s``-argument form. Found by the upgraded
#: scanner on its first run against real source, which is the whole point of
#: the upgrade:
#:   agents/nodes.py           +1 ([rag]-extra ImportError)
#:   agents/register_builtin.py +1 (its sibling)
#:   delegate/hooks.py         +1 (hook-spawn OSError)
#:   delegate/session.py       +3 (session load / scan / fork-update)
#: All six are LOCAL (in-process ImportError / OSError / JSONDecodeError), so
#: they route through the conservative preset, which preserves the path that IS
#: their diagnostic.
EXPECTED_FILES = 57
EXPECTED_SITES = 191


#: Standard ``logging.Logger`` emit methods. Matched on the ATTRIBUTE name, so
#: ``logger.error``, ``self.logger.error`` and
#: ``logging.getLogger(__name__).error`` are all recognised without having to
#: model how each module happens to bind its logger.
_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)


class _SinkScan(ast.NodeVisitor):
    """Find uses of one handler's bound exception name that reach a log record.

    ``wrapped`` are the uses already routed through one of :data:`HELPERS`; ``bare``
    are the ones that would put the raw exception text into a message.

    THREE SHAPES, AND THE SCANNER ORIGINALLY SAW ONLY ONE
    ----------------------------------------------------
    This class advertises (docstring tier 1, above) that it reds when a NEW
    unscrubbed sink is added. For its first version that was only true of the
    ``str(e)`` / ``repr(e)`` / f-string ``{e}`` shape, and the gap was not
    theoretical: it is why the #1970 sweep left ELEVEN traceback sinks and FIVE
    bare-argument sinks in this package for a later session to find. An
    instrument that cannot see a defect class reports the same green whether or
    not that class is present, which makes its green uninformative for it.

    1. **String context** — ``str(e)``, ``repr(e)``, f-string ``{e}``. Original.
    2. **Bare argument** — ``logger.error("failed: %s", e)``. The exception is
       handed to the logger as a lazy ``%s`` arg, so no ``str()`` call and no
       ``FormattedValue`` node ever appears in the tree; ``logger.error`` is an
       ``ast.Attribute``, which no branch matched, and there is no
       ``visit_Name``. This is the exact shape of the five bare sinks in
       ``delegate/`` fixed in 689f9ebd8.
    3. **Traceback** — ``exc_info=True`` or ``logger.exception(...)``. Not a
       node the scanner inspected at all. ``logging`` renders ``exc_info`` by
       walking the exception chain, so a scrubbed MESSAGE beside a retained
       traceback still prints the raw exception and its ``__cause__`` on the
       traceback's final line. Every one of the eleven CLASS-2 sinks fixed in
       689f9ebd8 had a correctly-scrubbed message and was invisible here.

    Shapes 2 and 3 are deliberately narrow: shape 2 fires only for a bare
    ``Name`` passed to a LOGGING call, so ``type(e)``, ``isinstance(e, X)``,
    ``raise e`` and ``SomeResult.from_exception(e)`` are untouched; shape 3
    fires only inside an except handler, which is the only place a traceback can
    carry the caught exception.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.bare: list[int] = []
        self.wrapped: list[int] = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # An inner handler rebinding the same name owns its own uses.
        if node.name != self.name:
            self.generic_visit(node)

    def _is_our_name(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id == self.name

    def _is_str_of_our_name(self, node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        )

    @staticmethod
    def _is_logging_call(func: ast.AST) -> bool:
        """``<anything>.<log-method>(...)`` — matched on the attribute only."""
        return isinstance(func, ast.Attribute) and func.attr in _LOG_METHODS

    def _flag_traceback_and_bare_args(self, node: ast.Call) -> None:
        """Record shapes 2 and 3 on a logging call (see the class docstring).

        Does NOT return early: the caller still descends, so a
        ``scrub_remote_error(e)`` sitting in the SAME call is still counted as
        wrapped. Flagging and short-circuiting here would silently drop that
        site from the wrapped tally and move the pinned counts.
        """
        # Shape 3a — ``logger.exception`` ALWAYS sets exc_info.
        if isinstance(node.func, ast.Attribute) and node.func.attr == "exception":
            self.bare.append(node.lineno)
            return
        for kw in node.keywords:
            # Shape 3b — an explicit truthy ``exc_info``. ``exc_info=False`` /
            # ``exc_info=None`` are the documented ways to turn it off, so they
            # are not sinks.
            if kw.arg == "exc_info" and not (
                isinstance(kw.value, ast.Constant) and not kw.value.value
            ):
                self.bare.append(node.lineno)
                return
        # Shape 2 — the exception handed over as a lazy ``%s`` argument. args[0]
        # is the format string; anything after it is interpolated into the
        # record exactly as ``str(e)`` would be.
        for arg in node.args[1:]:
            if self._is_our_name(arg):
                self.bare.append(arg.lineno)
                return

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if self._is_logging_call(func):
            self._flag_traceback_and_bare_args(node)
            # fall through to generic_visit -- see the docstring above.
        if (
            isinstance(func, ast.Name)
            and func.id in HELPERS
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        ):
            self.wrapped.append(node.lineno)
            return  # do not descend: the Name inside is accounted for
        if (
            isinstance(func, ast.Name)
            and func.id == AGGRESSIVE_HELPER
            and len(node.args) == 1
            and (
                self._is_our_name(node.args[0])
                or self._is_str_of_our_name(node.args[0])
            )
        ):
            # Scrubbed, but by the aggressive entry point. Counts as covered for
            # Tier 1; deliberately NOT counted as part of this sweep.
            return
        if (
            isinstance(func, ast.Name)
            and func.id in ("str", "repr")
            and len(node.args) == 1
            and self._is_our_name(node.args[0])
        ):
            self.bare.append(node.lineno)
            return
        self.generic_visit(node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if self._is_our_name(node.value):
            self.bare.append(node.value.lineno)
            return
        self.generic_visit(node)


def _enumerate(path: Path) -> tuple[list[int], list[int]]:
    """Return ``(bare_linenos, wrapped_linenos)`` for one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bare: list[int] = []
    wrapped: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not node.name:
            continue
        scan = _SinkScan(node.name)
        for stmt in node.body:
            scan.visit(stmt)
        bare.extend(scan.bare)
        wrapped.extend(scan.wrapped)
    return bare, wrapped


def _source_files() -> list[Path]:
    out = []
    for p in sorted(PKG.rglob("*.py")):
        if EXCLUDED_PARTS & set(p.relative_to(PKG).parts):
            continue
        out.append(p)
    return out


def _swept_files() -> list[Path]:
    """Files that carry at least one scrubbed sink."""
    return [p for p in _source_files() if _enumerate(p)[1]]


SWEPT = _swept_files()
SWEPT_IDS = [str(p.relative_to(PKG)) for p in SWEPT]


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(SRC).with_suffix("").parts)


# ---------------------------------------------------------------------------
# Tier 1 — coverage. No bare sink anywhere in the package.
# ---------------------------------------------------------------------------
class TestTheScannerSeesEachShape:
    """The coverage instrument is itself covered.

    Tier 1 claims to red when a NEW unscrubbed sink appears. That claim is only
    worth what the scanner can SEE, and for its first version the answer was
    "one shape of three" -- which is why eleven traceback sinks and five
    bare-argument sinks survived the #1970 sweep and a `grep exc_info` both.

    So each shape is planted here as a fixture and asserted to red, and each
    near-miss that must NOT red is planted beside it. Without the negative
    controls this class would pass just as well against a scanner that flags
    everything, which would be a different way of being uninformative.
    """

    @staticmethod
    def _scan(src: str) -> list[int]:
        tree = ast.parse(textwrap.dedent(src))
        bare: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or not node.name:
                continue
            scan = _SinkScan(node.name)
            for stmt in node.body:
                scan.visit(stmt)
            bare.extend(scan.bare)
        return bare

    @pytest.mark.parametrize(
        "label, body",
        [
            # Shape 1 — string context. The original detector.
            ("str", '    logger.error("failed: " + str(exc))'),
            ("f-string", '    logger.error(f"failed: {exc}")'),
            ("repr", '    logger.error("failed: " + repr(exc))'),
            # Shape 2 — the lazy %s argument. The five delegate/ sinks.
            ("bare-%s-arg", '    logger.error("failed: %s", exc)'),
            # Shape 3 — the traceback. All eleven CLASS-2 sinks.
            (
                "logger.exception",
                '    logger.exception("failed: %s", scrub_local_error(exc))',
            ),
            (
                "exc_info=True",
                '    logger.error("f: %s", scrub_local_error(exc), exc_info=True)',
            ),
        ],
    )
    def test_each_leaking_shape_is_flagged(self, label: str, body: str) -> None:
        src = f"try:\n    pass\nexcept Exception as exc:\n{body}\n"
        assert self._scan(src), f"scanner is blind to the {label!r} shape"

    @pytest.mark.parametrize(
        "label, body",
        [
            ("scrubbed-%s-arg", '    logger.error("f: %s", scrub_local_error(exc))'),
            ("scrubbed-remote", '    logger.error("f: %s", scrub_remote_error(exc))'),
            # exc_info=False / None are the documented ways to turn it OFF.
            (
                "exc_info=False",
                '    logger.error("f: %s", scrub_local_error(exc), exc_info=False)',
            ),
            # Uses that never reach a log record as text.
            ("type-name", '    logger.error("f: %s", type(exc).__name__)'),
            ("isinstance", "    _ = isinstance(exc, OSError)"),
            ("re-raise", "    raise exc"),
            # A bare Name handed to a NON-logging call is out of scope: it does
            # not become a log record, and flagging it would make the scanner
            # noisy enough that someone would add exclusions.
            ("non-log-call", "    _ = Result.from_exception(exc)"),
        ],
    )
    def test_each_safe_shape_is_not_flagged(self, label: str, body: str) -> None:
        src = f"try:\n    pass\nexcept Exception as exc:\n{body}\n"
        assert not self._scan(src), f"scanner false-positives on {label!r}"


class TestNoBareExceptionTextSinkRemains:
    @pytest.mark.parametrize(
        "path",
        _source_files(),
        ids=[str(p.relative_to(PKG)) for p in _source_files()],
    )
    def test_no_unwrapped_exception_text_sink_remains(self, path: Path) -> None:
        bare, _ = _enumerate(path)
        assert bare == [], (
            f"{path.relative_to(PKG)} puts a caught exception into a string at "
            f"line(s) {bare} without one of {HELPERS}. A local error message can carry "
            "a credential from a DSN, a config value or a provider payload; every "
            "such sink routes through the conservative scrub."
        )

    def test_the_sweep_covers_the_measured_surface(self) -> None:
        """Pin the enumeration itself.

        Without this, every parametrised assertion above could pass over an
        empty set — the classic vacuous-coverage shape.
        """
        total = sum(len(_enumerate(p)[1]) for p in SWEPT)
        assert (len(SWEPT), total) == (EXPECTED_FILES, EXPECTED_SITES), (
            f"swept surface moved: {len(SWEPT)} files / {total} sites, "
            f"expected {EXPECTED_FILES} / {EXPECTED_SITES}. If a sink was "
            "legitimately added or removed, update the pin in the same commit."
        )


# ---------------------------------------------------------------------------
# Tier 2 + 3 — per module: the right symbol, doing the right thing.
# ---------------------------------------------------------------------------
CREDENTIAL = "sk-abcdefghijklmnopqrstuvwxyz0123456789"
LOADBEARING_PATH = "/Users/alice/repos/app/config.yaml"


def _bound_presets(path: Path) -> list[str]:
    """The preset names this module actually imports."""
    mod = importlib.import_module(_module_name(path))
    return [name for name in HELPERS if getattr(mod, name, None) is not None]


class TestEverySweptModule:
    @pytest.mark.parametrize("path", SWEPT, ids=SWEPT_IDS)
    def test_module_binds_the_canonical_preset(self, path: Path) -> None:
        mod = importlib.import_module(_module_name(path))
        names = _bound_presets(path)
        assert names, (
            f"{path.relative_to(PKG)} carries a scrubbed sink but binds neither "
            f"of {HELPERS}"
        )
        for name in names:
            assert getattr(mod, name) is CANONICAL_BY_NAME[name], (
                f"{path.relative_to(PKG)} does not bind the canonical "
                f"kaizen.utils.credential_scrub.{name}. A per-module copy is "
                "the drift this module exists to prevent."
            )

    @pytest.mark.parametrize("path", SWEPT, ids=SWEPT_IDS)
    def test_credential_scrubbed_and_path_survives(self, path: Path) -> None:
        """Both directions, through every symbol this module actually calls.

        The path assertion holds for BOTH presets by construction: they differ
        only on ``redact_opaque_tokens``, and both leave ``redact_paths`` off,
        because an agent reading a failure to decide its retry needs the
        location under either classification.
        """
        mod = importlib.import_module(_module_name(path))

        for name in _bound_presets(path):
            scrub = getattr(mod, name)
            exc = OSError(
                f"[Errno 13] Permission denied: '{LOADBEARING_PATH}' "
                f"(token {CREDENTIAL})"
            )
            rendered = scrub(exc)

            assert CREDENTIAL not in rendered, (
                f"{path.relative_to(PKG)} would leak a credential into its "
                f"error text via {name}"
            )
            assert "[REDACTED]" in rendered
            assert LOADBEARING_PATH in rendered, (
                f"{path.relative_to(PKG)} would mangle, via {name}, the path an "
                "agent needs in order to retry — the exact failure the "
                "aggressive sweep was halted over."
            )


class TestThePresetSplitIsReal:
    """The split must be a real difference, not two names for one behaviour.

    Without this the whole re-triage is unfalsifiable: every module could bind
    ``scrub_remote_error`` while it behaved identically to the conservative
    preset, and every assertion above would still pass.
    """

    #: Prefix-less credential shapes. NO literal-anchored rule matches either,
    #: so ONLY the shape-only rules can claim them — which is exactly what
    #: ``scrub_local_error`` switches off.
    AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    AZURE_HEX_KEY = "a1b2c3d4e5f60718293a4b5c6d7e8f90"

    @pytest.mark.parametrize("secret", [AWS_SECRET, AZURE_HEX_KEY])
    def test_remote_preset_claims_prefixless_credentials(self, secret: str) -> None:
        rendered = scrub_remote_error(Exception(f"auth failed: {secret}"))
        assert secret not in rendered, (
            "scrub_remote_error let a prefix-less credential through; it is the "
            "preset for sinks whose exception crosses a provider boundary, and "
            "a bare AWS secret / bare hex Azure api-key is precisely what "
            "arrives there"
        )

    @pytest.mark.parametrize("secret", [AWS_SECRET, AZURE_HEX_KEY])
    def test_local_preset_deliberately_does_not(self, secret: str) -> None:
        """Pins the WHY of the split, and the residual it accepts.

        This is not an endorsement — it is the measured reason a remote sink
        MUST NOT use the conservative preset. If this ever starts redacting,
        the two presets have converged and the re-triage is moot.
        """
        rendered = scrub_local_error(Exception(f"auth failed: {secret}"))
        assert secret in rendered

    def test_both_presets_preserve_the_diagnostic_path(self) -> None:
        """CONTROL. The split is on the credential axis, not the path axis."""
        for scrub in (scrub_local_error, scrub_remote_error):
            rendered = scrub(OSError(f"[Errno 2] No such file: '{LOADBEARING_PATH}'"))
            assert LOADBEARING_PATH in rendered

    def test_signature_query_value_claimed_by_both(self) -> None:
        """``sig=`` was case-SENSITIVE and never matched ``Signature=``.

        Literal-anchored, so it must hold under the CONSERVATIVE preset too —
        which is where it matters most, the shape rules being off there.
        """
        sig = "X-Amz-Signature=abcdef0123456789abcdef0123456789abcdef01"
        for scrub in (scrub_local_error, scrub_remote_error):
            assert "abcdef0123456789" not in scrub(Exception(f"denied {sig}"))


# ---------------------------------------------------------------------------
# Tier 4 — the agent-facing tool sinks, driven end to end.
# ---------------------------------------------------------------------------
def _raising_oserror(message: str):
    def _raise(*_args, **_kwargs):
        raise OSError(message)

    return _raise


CREDENTIALED_OSERROR = (
    f"[Errno 5] I/O error: '{LOADBEARING_PATH}' while using {CREDENTIAL}"
)
ORDINARY_OSERROR = f"[Errno 5] Input/output error: '{LOADBEARING_PATH}'"


class TestDelegateToolResultsReachTheModelIntact:
    """The ``ToolResult`` an LLM reads to decide its retry.

    Asserting on ``result.error`` rather than on the scrub helper is the point:
    this is the surface the halt report identified, so it is driven rather than
    reasoned about.
    """

    def test_file_read_scrubs_credential_and_keeps_path(self, tmp_path, monkeypatch):
        from kaizen_agents.delegate.tools.file_read import FileReadTool

        target = tmp_path / "config.yaml"
        target.write_text("k: v", encoding="utf-8")
        monkeypatch.setattr(Path, "read_text", _raising_oserror(CREDENTIALED_OSERROR))

        result = FileReadTool().execute(file_path=str(target))

        assert result.is_error
        assert CREDENTIAL not in result.error
        assert "[REDACTED]" in result.error
        assert LOADBEARING_PATH in result.error

    def test_file_read_leaves_an_ordinary_oserror_path_byte_identical(
        self, tmp_path, monkeypatch
    ):
        from kaizen_agents.delegate.tools.file_read import FileReadTool

        target = tmp_path / "config.yaml"
        target.write_text("k: v", encoding="utf-8")
        monkeypatch.setattr(Path, "read_text", _raising_oserror(ORDINARY_OSERROR))

        result = FileReadTool().execute(file_path=str(target))

        assert result.error == f"Error reading file: {ORDINARY_OSERROR}", (
            "an ordinary OSError must reach the model unchanged; the model "
            "cannot retry against '[PATH]/...'"
        )

    def test_file_write_scrubs_credential_and_keeps_path(self, tmp_path, monkeypatch):
        from kaizen_agents.delegate.tools.file_write import FileWriteTool

        monkeypatch.setattr(Path, "write_text", _raising_oserror(CREDENTIALED_OSERROR))

        result = FileWriteTool().execute(
            file_path=str(tmp_path / "out.txt"), content="x"
        )

        assert result.is_error
        assert CREDENTIAL not in result.error
        assert LOADBEARING_PATH in result.error

    def test_file_write_leaves_an_ordinary_oserror_path_byte_identical(
        self, tmp_path, monkeypatch
    ):
        from kaizen_agents.delegate.tools.file_write import FileWriteTool

        monkeypatch.setattr(Path, "write_text", _raising_oserror(ORDINARY_OSERROR))

        result = FileWriteTool().execute(
            file_path=str(tmp_path / "out.txt"), content="x"
        )

        assert result.error == f"Error writing file: {ORDINARY_OSERROR}"
