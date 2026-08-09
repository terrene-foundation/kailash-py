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
import re
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
#:
#: Teaching ``_SinkScan`` shapes 4-7 (see its docstring) —
#: ``traceback.format_exc()``, exception VALUES that were never except-bound,
#: ``%``/``.format`` interpolation, and exception ATTRIBUTES — moved the BARE
#: count from 0 to 10 while the scanner was reporting this package fully swept.
#:
#: THE PIN BELOW IS A *WRAPPED* COUNT, SO IT MOVES AT FIX TIME, NOT TEACH TIME.
#: This matters when reading the teaching as landed or not: a newly-seen shape
#: shows up first as a BARE site, and only becomes a swept site once it is
#: routed through a preset. The teach-time evidence is therefore the bare count
#: (0 -> 10, enumerated below); the pin moves one commit later, by +1 per fixed
#: site and +1 file for each file that had no scrubbed sink before.
#:
#: The ten bare sites this teaching surfaced, none of which any previous pass
#: could see:
#:   patterns/patterns/blackboard.py     281, 322  (traceback.format_exc)
#:   patterns/patterns/ensemble.py       264, 315  (traceback.format_exc)
#:   patterns/patterns/parallel.py       148, 258  (traceback.format_exc)
#:   patterns/patterns/meta_controller.py     246  (traceback.format_exc)
#:   patterns/patterns/meta_controller.py     243  (str() of an ANNOTATED
#:                                                  ``error: Exception`` param)
#:   patterns/patterns/parallel.py            256  (str() of an isinstance-
#:                                                  narrowed gather() result)
#:   delegate/loop.py                         767  (lazy ``%s`` of an isinstance-
#:                                                  narrowed gather() result,
#:                                                  thirteen lines below a
#:                                                  correctly scrubbed sibling)
#:   patterns/registry.py                     711  (``repr()`` of a CALLER-
#:                                                  SUPPLIED listener inside a
#:                                                  ``logger.warning`` extra,
#:                                                  beside a scrubbed ``exc``)
#: Ten of the eleven are routed through a preset when fixed, taking this pin to
#: 58 / 201: +10 sites, and +1 file because ``meta_controller.py`` carried no
#: scrubbed sink at all before.
#:
#: ``registry.py:711`` is the exception and MUST NOT be counted as an eleventh:
#: its accepted remediation is ``type(listener).__name__``, NOT a scrub (see
#: ``_repr_sinks``), so fixing it REMOVES a bare site without ADDING a wrapped
#: one. A pin that lands on 202 means someone scrubbed the repr instead, which
#: this file rejects. Re-derive rather than trust any of that arithmetic.
#:
#: LANDED at 58 / 201 when the six F10/F11/F13 shard worktrees were integrated.
#: Re-derived post-merge, not carried: ``registry.py:736`` resolves through
#: ``type(listener).__name__``, so the 202 this file rejects did NOT occur.
#:
#: SEVEN of the 201 became visible only when ``_traceback_sites`` learned to
#: account for a traceback call NESTED inside the scrubbed argument
#: (``scrub("".join(format_exception(e)))``) rather than only when it IS that
#: argument. Under the pre-integration scanner the same tree reads 194. Those
#: seven sites were scrubbed in the source the whole time; the instrument could
#: not see it, which is the shape every blind spot in this file has taken.
EXPECTED_FILES = 58
EXPECTED_SITES = 201


#: Standard ``logging.Logger`` emit methods. Matched on the ATTRIBUTE name, so
#: ``logger.error``, ``self.logger.error`` and
#: ``logging.getLogger(__name__).error`` are all recognised without having to
#: model how each module happens to bind its logger.
_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)

#: ``traceback`` entry points that render a caught exception — its message, and
#: every message in its ``__cause__`` / ``__context__`` chain — as text. There
#: is no safe use of one of these in a value that leaves the process: the
#: rendering ALWAYS contains ``str(exc)`` on its final line. So these are
#: flagged wherever they appear, with no name and no handler required, which is
#: the only way to see the seven sites that sit in a returned dict rather than
#: in a log record.
_TRACEBACK_FUNCS = frozenset(
    {
        "format_exc",
        "format_exception",
        "format_exception_only",
        "print_exc",
        "print_exception",
    }
)

#: Attribute chains on an exception that CANNOT carry message text. Everything
#: NOT listed is flagged — ``args``, ``msg``, ``strerror``, ``filename``,
#: ``stdout``, ``stderr``, ``response``, ``detail``, ``__cause__``,
#: ``__context__`` each render environment- or provider-controlled text, and
#: ``e.response.text`` is a whole HTTP body.
#:
#: An ALLOWLIST, deliberately, and not a denylist of the leaky ones: an
#: attribute nobody anticipated must default to FLAGGED. This scanner's entire
#: defect was that an unrecognised shape defaulted to silence, and a false
#: positive costs one reviewer minute while a false "swept" costs a credential.
_SAFE_EXC_ATTRS = frozenset(
    {
        "__class__",
        "__name__",
        "__qualname__",
        "__module__",
        "errno",
        "winerror",
        "returncode",
    }
)


def _key(node: ast.expr) -> tuple[int, int]:
    """Identity of one syntactic site.

    ``(lineno, col_offset)`` rather than ``lineno`` alone, because a site can
    now be reached by more than one pass — a name can be both except-bound and
    ``isinstance``-narrowed in the same function — and a site counted twice
    would inflate the pinned totals into meaninglessness.

    Typed ``ast.expr`` rather than ``ast.AST``: position attributes are declared
    on the expression/statement subclasses, not on the ``AST`` base, so the
    wider annotation made every call site an unchecked attribute access. Every
    caller does pass an expression, so narrowing documents the real contract
    instead of suppressing the checker.
    """
    return (node.lineno, node.col_offset)


def _root_name(node: ast.expr) -> str | None:
    """The ``Name`` an attribute/subscript chain is rooted at, if any."""
    current: ast.expr = node
    while isinstance(current, ast.Attribute | ast.Subscript):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _is_exception_like(node: ast.AST | None) -> bool:
    """``Exception`` / ``BaseException`` / anything named like an error class.

    Matched on the trailing identifier, so ``httpx.HTTPError`` and
    ``asyncio.TimeoutError`` resolve without importing anything.
    """
    if isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Attribute):
        name = node.attr
    else:
        return False
    return name in ("Exception", "BaseException") or name.endswith(
        ("Error", "Exception", "Exit", "Interrupt")
    )


def _annotation_is_exception(node: ast.AST | None) -> bool:
    """``Exception``, ``Exception | None``, ``Optional[Exception]``, ``"Exception"``."""
    if node is None:
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_is_exception(node.left) or _annotation_is_exception(
            node.right
        )
    if isinstance(node, ast.Subscript):  # Optional[X] / Union[X, Y]
        sl = node.slice
        elts = sl.elts if isinstance(sl, ast.Tuple) else [sl]
        return any(_annotation_is_exception(e) for e in elts)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:  # PEP 563 / quoted forward reference
            return _annotation_is_exception(ast.parse(node.value, mode="eval").body)
        except SyntaxError:
            return False
    return _is_exception_like(node)


def _isinstance_narrowed_names(test: ast.AST) -> set[str]:
    """Names an ``if`` test proves to hold an exception, for that branch.

    ``if isinstance(result, Exception):`` is how an exception returned as a
    VALUE — ``asyncio.gather(..., return_exceptions=True)`` is the canonical
    producer — announces itself. There is no ``ExceptHandler`` anywhere in
    scope, so the except-bound scan misses the whole class by construction.
    """
    names: set[str] = set()
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        for value in test.values:
            names |= _isinstance_narrowed_names(value)
        return names
    if (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "isinstance"
        and len(test.args) == 2
        and isinstance(test.args[0], ast.Name)
    ):
        cls = test.args[1]
        candidates = cls.elts if isinstance(cls, ast.Tuple | ast.List) else [cls]
        if candidates and all(_is_exception_like(c) for c in candidates):
            names.add(test.args[0].id)
    return names


def _param_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    a = fn.args
    out = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    if a.vararg is not None:
        out.append(a.vararg)
    if a.kwarg is not None:
        out.append(a.kwarg)
    return out


def _exception_regions(tree: ast.AST) -> list[tuple[str, list[ast.stmt]]]:
    """``(name, body)`` for every region in which ``name`` holds an exception.

    THREE PRODUCERS, AND THE SCANNER ORIGINALLY KNEW ONE
    ----------------------------------------------------
    The first version enumerated ``except ... as e`` handlers ONLY, so an
    exception that arrives as a VALUE was outside its universe of discourse —
    not missed by a weak heuristic, but unreachable, because the loop that built
    the scan set filtered on ``isinstance(node, ast.ExceptHandler)``.

    * ``except E as name`` — the original.
    * ``if isinstance(name, ExcLike):`` — scoped to that branch's body, which is
      exactly where a ``gather(return_exceptions=True)`` result is unpacked.
    * a FUNCTION whose parameter holds an exception, evidenced either by an
      exception-like ANNOTATION (``error: Exception``) or by a bare
      ``raise <param>`` in its body — you cannot ``raise`` a non-exception, and
      restricting to parameters keeps ``raise ValueError`` (a class, not a
      value) out.
    """
    regions: list[tuple[str, list[ast.stmt]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.name:
            regions.append((node.name, node.body))
        elif isinstance(node, ast.If):
            for name in _isinstance_narrowed_names(node.test):
                regions.append((name, node.body))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            params = {arg.arg for arg in _param_names(node)}
            names = {
                arg.arg
                for arg in _param_names(node)
                if _annotation_is_exception(arg.annotation)
            }
            names |= {
                sub.exc.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Raise)
                and isinstance(sub.exc, ast.Name)
                and sub.exc.id in params
            }
            for name in names:
                regions.append((name, node.body))
    return regions


def _is_traceback_call(node: ast.expr) -> bool:
    """``traceback.format_exc()`` and its siblings, however the module is bound.

    Matched on the FUNCTION name alone — ``traceback.format_exc()``,
    ``tb.format_exc()`` and a ``from traceback import format_exc`` all count.
    Not qualifying on the module binding is a deliberate over-reach: a
    same-named helper of someone's own gets flagged, and that costs a comment,
    whereas requiring the literal ``traceback.`` prefix would have re-introduced
    a blind spot for the sake of a tidier count.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _TRACEBACK_FUNCS
    return isinstance(func, ast.Name) and func.id in _TRACEBACK_FUNCS


_ALL_HELPERS = frozenset(HELPERS) | {AGGRESSIVE_HELPER}


def _traceback_sites(
    tree: ast.AST,
) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    """Shape 7 — ``(bare, wrapped)`` traceback renderings, name-independent.

    Runs over the WHOLE module rather than over handler bodies, because seven of
    the nine sites this pass exists for sit in a ``return {...}`` dict — five
    inside a handler, two in a plain function body with no handler in sight.
    Keying the scan on a bound name could never have reached the latter two.
    """
    accounted: set[tuple[int, int]] = set()
    wrapped: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _ALL_HELPERS
            and len(node.args) == 1
        ):
            continue
        # The traceback call is accounted wherever it sits INSIDE the scrubbed
        # argument, not only when it IS that argument. The direct form
        # ``scrub(format_exc())`` is preserved because ``ast.walk`` yields the
        # argument itself first; the nested form
        # ``scrub("".join(format_exception(e)))`` is the one that was missed.
        # That nested spelling is not incidental -- it is the FIX for a separate
        # defect (rendering from the exception OBJECT instead of ``format_exc``'s
        # ambient ``sys.exc_info()``, which once produced a traceback of no
        # exception at all), so the shape it produces is the shape the swept
        # sites now have. Scoping the walk to the argument subtree is what keeps
        # this sound: a traceback call OUTSIDE the helper call -- e.g.
        # ``scrub(x) + format_exc()`` -- is not reached and stays bare.
        nested_tracebacks = [
            inner
            for inner in ast.walk(node.args[0])
            if isinstance(inner, ast.Call) and _is_traceback_call(inner)
        ]
        if not nested_tracebacks:
            continue
        for inner in nested_tracebacks:
            accounted.add(_key(inner))
        if node.func.id in HELPERS:
            wrapped.add(_key(node))
    bare = {
        _key(node)
        for node in ast.walk(tree)
        # The ``isinstance`` is redundant at runtime — ``_is_traceback_call``
        # already rejects a non-``Call`` — and is kept so the position access in
        # ``_key`` is a CHECKED one rather than an unchecked attribute read on
        # the ``AST`` base class, which is what ``ast.walk`` is typed to yield.
        if isinstance(node, ast.Call)
        and _is_traceback_call(node)
        and _key(node) not in accounted
    }
    return bare, wrapped


#: One printf conversion specifier. Groups the mapping key and the conversion
#: type, so ``%(handler)r`` and ``%-10.5r`` both resolve, and ``%%`` — a literal
#: percent, NOT a conversion — can be told apart from a real one.
_PRINTF_CONVERSION = re.compile(
    r"%(?:\((?P<key>[^)]*)\))?"
    r"[#0\- +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[hlL]?"
    r"(?P<type>[diouxXeEfFgGcrsa%])"
)


def _repr_conversion_slots(fmt: str) -> tuple[list[int], set[str]]:
    """``(positional indices, mapping keys)`` of the ``%r`` conversions in *fmt*.

    ``%r`` renders its argument through ``repr()`` with no ``repr`` token and no
    ``!r`` conversion anywhere in the tree, so it is invisible to a scan that
    looks for either. It is also the form the executed proof used, which is the
    argument for parsing the format string rather than pattern-matching the
    call.

    Only the conversions BEFORE a given ``%r`` advance the positional index, and
    ``%%`` advances nothing, so the index returned is the true argument slot.
    """
    positional: list[int] = []
    keys: set[str] = set()
    slot = 0
    for match in _PRINTF_CONVERSION.finditer(fmt):
        kind = match.group("type")
        if kind == "%":  # a literal percent consumes no argument
            continue
        key = match.group("key")
        if key is not None:
            if kind == "r":
                keys.add(key)
            continue  # mapping form: no positional slot to advance
        if kind == "r":
            positional.append(slot)
        slot += 1
    return positional, keys


def _is_scrub_call(node: ast.expr) -> bool:
    """``scrub_local_error(...)`` / ``scrub_remote_error(...)`` / the aggressive one.

    Used ONLY by the ``%r`` pass, where it marks a value that is already
    scrubbed TEXT rather than a live object. ``%r`` of a ``str`` merely adds
    quotes; ``%r`` of an object renders its fields. That difference is why this
    exemption does not contradict shape 8's refusal to excuse
    ``scrub_remote_error(repr(handler))`` — there the object's fields are
    rendered FIRST and the scrubber only filters the resulting text.
    """
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _ALL_HELPERS
    )


def _invoked_names(scope: ast.AST) -> set[str]:
    """Names INVOKED as callables anywhere in *scope*.

    Structural evidence that a name holds a callable, which is the object class
    the ``%r`` threat model is actually about — not a keyword list of plausible
    names, which would be unsound in both directions.
    """
    return {
        sub.func.id
        for sub in ast.walk(scope)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
    }


def _percent_r_sinks(
    node: ast.Call, exception_names: set[str], callable_names: set[str]
) -> set[tuple[int, int]]:
    """Shape 8c — ``logger.error("Listener %r ...", listener)``.

    The third rendering form, and the one no token-level scan can see: there is
    no ``repr(`` call and no ``!r`` conversion in the tree at all. The repr
    happens inside ``logging``'s own interpolation, driven by two nodes that are
    syntactically unrelated — a string constant and a positional argument.

    Resolves the ``%r`` to its actual argument slot so the FLAG LANDS ON THE
    LEAKING VALUE rather than on the call, which is what makes the report
    actionable. Where the slot cannot be resolved — ``*args`` splat, or a format
    string built at runtime — the call itself is flagged instead: unresolvable
    is not the same as safe, and this pass exists because the unresolvable case
    used to resolve to silence.

    NARROWED TO CALLABLES, AND THE MEASUREMENT THAT FORCED IT
    ---------------------------------------------------------
    Unlike shape 8's explicit ``repr()``, this fires only when the argument is a
    name INVOKED as a callable somewhere in the same scope. Un-narrowed it
    flagged 28 sites in this package where 11 are real — a 61% false-positive
    rate, every one of them ``%r`` used for its ordinary purpose of quoting a
    STRING (``line[:200]``, ``query[:80]``, a config ``name``, a model id).

    That rate is not a cosmetic problem. This scanner backs a gate that must sit
    at zero bare sinks, so 17 spurious reds buy either 17 pointless edits or a
    hand-maintained exclusion list — and an exclusion list is how a detector
    ends up switched off, which is the same outcome as the blindness it
    replaced.

    The narrowing is not a convenience: ``repr`` only exposes what ``str`` would
    not when the value is an OBJECT whose ``__repr__`` renders its fields. On a
    string ``%r`` merely adds quotes, so there is no shape-8 delta to claim, and
    plain ``%s`` interpolation is deliberately out of scope anyway.
    ``journey/manager.py`` states the threat as a CALLABLE one exactly —
    ``functools.partial(post, url="https://u:pw@host")`` renders its bound
    kwargs — so keying on callable evidence tracks the actual class rather than
    approximating it.

    Held to a LOOSER bar than shape 8's ``repr()`` deliberately: an explicit
    ``repr()`` is a deliberate act and rare (2 in this package), while ``%r`` is
    idiomatic string-quoting and common (17). Different base rates, different
    thresholds — stated here rather than applied silently.
    """
    flagged: set[tuple[int, int]] = set()
    if not node.args:
        return flagged
    fmt = node.args[0]
    if not (isinstance(fmt, ast.Constant) and isinstance(fmt.value, str)):
        return flagged  # runtime-built format: no conversions to resolve
    positional, keys = _repr_conversion_slots(fmt.value)
    if not positional and not keys:
        return flagged
    rest = list(node.args[1:])

    # ``logger.error(fmt, *args)`` — the slots are not statically knowable.
    if any(isinstance(arg, ast.Starred) for arg in rest):
        if callable_names:
            flagged.add(_key(node))
        return flagged

    # ``logger.error(fmt, (a, b))`` passes ONE tuple holding every slot.
    if len(rest) == 1 and isinstance(rest[0], ast.Tuple):
        rest = list(rest[0].elts)

    for index in positional:
        if index < len(rest):
            target = rest[index]
            root = _root_name(target)
            if (
                root in callable_names
                and root not in exception_names
                and not _is_scrub_call(target)
            ):
                flagged.add(_key(target))
        elif callable_names:
            flagged.add(_key(node))  # arity mismatch: flag rather than assume

    if keys:
        mapping = rest[0] if len(rest) == 1 else None
        if isinstance(mapping, ast.Dict):
            for key_node, value in zip(mapping.keys, mapping.values, strict=False):
                if (
                    isinstance(key_node, ast.Constant)
                    and key_node.value in keys
                    and value is not None
                    and _root_name(value) in callable_names
                    and _root_name(value) not in exception_names
                    and not _is_scrub_call(value)
                ):
                    flagged.add(_key(value))
        elif callable_names:
            flagged.add(_key(node))  # mapping not a literal: flag the call
    return flagged


def _repr_sinks(tree: ast.AST, exception_names: set[str]) -> set[tuple[int, int]]:
    """Shape 8 — ``repr()`` of a NON-exception object reaching a log record.

    Every other shape here is keyed on an EXCEPTION. This one is not, and that
    is the whole point: ``_SinkScan`` inspects one exception-valued name, so an
    arbitrary object rendered into a log was outside its universe of discourse
    however the name-tracking was tuned. The control that makes this a finding
    rather than a guess is that the same probe DOES fire on the exception form —
    ``repr(handler)`` scanned to ``[]`` while ``repr(e)`` scanned to ``[4]``.

    WHY AN OBJECT'S ``repr`` IS A CREDENTIAL SURFACE
    ------------------------------------------------
    ``journey/manager.py`` already fixed one of these and wrote out the threat
    model, which this pass exists to enforce everywhere else::

        functools.partial(post, url="https://u:pw@host")

    renders its bound kwargs verbatim, and a callable object's
    dataclass-generated ``__repr__`` renders every field including a credential
    one. Both are CALLER-SUPPLIED, so whether the repr carries a secret is not
    decidable here.

    THE CONDITIONALITY IS WHY IT IS FLAGGED, NOT WHY IT IS EXCUSED
    --------------------------------------------------------------
    The live shape is ``getattr(handler, "name", repr(handler))``. Python
    evaluates that third argument EAGERLY, so the repr is computed on every
    call, but it only REACHES the log when the attribute is missing. So this is
    a conditional leak — and whether the attribute is present is a property of
    objects the caller supplies, which no scan-time analysis can settle. Flagged
    for exactly that reason: unprovable is not the same as absent, and this
    scanner's defect was resolving the unprovable case to silence.

    Matched on the SHAPE — a ``repr()`` call, or an ``!r`` conversion, anywhere
    inside a logging call — never on the attribute literal, because the same
    defect ships as both ``"name"`` and ``"__name__"``.

    A SCRUBBED ``repr`` IS STILL FLAGGED, DELIBERATELY
    ---------------------------------------------------
    Everywhere else in this file, routing through a preset means covered. Not
    here, and not by oversight: ``journey/manager.py`` rejected that remediation
    explicitly, preferring ``type(handler).__name__`` because "the scrubber's
    coverage is porous (a prefix-less 32-39 char key, ``token=``, a %40-encoded
    ``@`` all survive it)", whereas a type name cannot carry a payload BY
    CONSTRUCTION. Counting a scrubbed repr as covered would have this scanner
    bless the fix that codebase already considered and rejected.

    ``repr(e)`` on an exception is NOT claimed here — shape 1 owns it, and
    scrubbing an exception IS the accepted remediation for it.
    """
    flagged: set[tuple[int, int]] = set()
    # Scope by scope, so the ``%r`` pass can ask whether THIS function invokes
    # the name it is about to render. A nested function is visited under its own
    # scope AND under each enclosing one; the union means "flagged if any
    # enclosing scope carries the evidence", which is the permissive direction.
    scopes: list[ast.AST] = [tree]
    scopes += [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    for scope in scopes:
        callable_names = _invoked_names(scope)
        for node in ast.walk(scope):
            if not (
                isinstance(node, ast.Call) and _SinkScan._is_logging_call(node.func)
            ):
                continue
            flagged |= _percent_r_sinks(node, exception_names, callable_names)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _SinkScan._is_logging_call(node.func)):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "repr"
                and len(sub.args) == 1
            ):
                if _root_name(sub.args[0]) in exception_names:
                    continue  # shape 1 owns it; a scrubbed exception is covered
                flagged.add(_key(sub))
            elif isinstance(sub, ast.FormattedValue) and sub.conversion == ord("r"):
                if _root_name(sub.value) in exception_names:
                    continue
                flagged.add(_key(sub))
    return flagged


class _SinkScan(ast.NodeVisitor):
    """Find uses of one exception-valued name that reach a rendered string.

    ``wrapped`` are the uses already routed through one of :data:`HELPERS`;
    ``bare`` are the ones that would put the raw exception text into a message.
    Both are sets of :func:`_key` site identities.

    SEVEN SHAPES, AND THE SCANNER ORIGINALLY SAW ONE
    ------------------------------------------------
    This class advertises (docstring tier 1, above) that it reds when a NEW
    unscrubbed sink is added. That claim is worth exactly what the scanner can
    SEE, and each time the answer has been "less than it advertised": the #1970
    sweep left ELEVEN traceback sinks and FIVE bare-argument sinks behind, and
    the pass that fixed those still reported this package fully swept while NINE
    live leaks sat in files it had marked covered. An instrument that cannot see
    a defect class reports the same green whether or not that class is present,
    which makes its green uninformative for it.

    1. **String context** — ``str(e)``, ``repr(e)``, f-string ``{e}``. Original.
    2. **Bare argument** — ``logger.error("failed: %s", e)``. The exception is
       handed to the logger as a lazy ``%s`` arg, so no ``str()`` call and no
       ``FormattedValue`` node ever appears in the tree.
    3. **Logging traceback** — ``exc_info=True`` or ``logger.exception(...)``.
       ``logging`` renders ``exc_info`` by walking the exception chain, so a
       scrubbed MESSAGE beside a retained traceback still prints the raw
       exception and its ``__cause__`` on the traceback's final line.
    4. **``%`` interpolation** — ``"failed: %s" % e``, ``"%s/%s" % (tag, e)``,
       ``"%(err)s" % {"err": e}``. Produces the same bytes as ``str(e)`` with no
       ``str`` call and no ``JoinedStr`` node.
    5. **``.format()``** — ``"failed: {}".format(e)``, ``"{err}".format(err=e)``.
       Same, via an ``ast.Attribute`` call the scanner did not inspect.
    6. **Exception ATTRIBUTES** — ``e.args``, ``e.strerror``, ``e.response.text``,
       ``e.__cause__``. The exception itself never appears, so every branch
       keyed on ``self.name`` being the whole argument missed them, and
       ``e.response.text`` is an entire provider HTTP body — the single richest
       credential source at any of these sinks. Discriminated by
       :data:`_SAFE_EXC_ATTRS`, an allowlist, so an unanticipated attribute
       fails toward FLAGGED.
    7. **``traceback.format_exc()``** — see :func:`_traceback_sites`. Handled
       outside this class because it needs no name at all.

    WHERE THIS DELIBERATELY OVER-FLAGS
    ----------------------------------
    Shape 6 fires on ANY attribute outside the allowlist, and :func:`_is_traceback_call`
    fires on ANY ``format_exc``-named callable. Both will occasionally flag a
    site that is genuinely fine. That trade is taken on purpose and in one
    direction only: a false positive is discharged by a reviewer in a minute,
    while a false "swept" is the exact defect this class exists to fix and is
    discharged by a credential in a log. Where a shape could be discriminated
    cheaply and soundly it IS — ``exc_info=False`` is not a sink, ``e.errno`` is
    not a sink, ``type(e).__name__`` is not a sink, and a bare ``Name`` handed to
    a NON-logging call is not a sink — but no cleverer heuristic is added just to
    make the count tidier.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.bare: set[tuple[int, int]] = set()
        self.wrapped: set[tuple[int, int]] = set()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        # An inner handler rebinding the same name owns its own uses.
        if node.name != self.name:
            self.generic_visit(node)

    def _is_our_name(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id == self.name

    def _is_our_value(self, node: ast.AST) -> bool:
        """Our exception, or a text-bearing attribute/index chain rooted at it.

        ``e`` / ``e.args`` / ``e.args[0]`` / ``e.response.text`` are all our
        value; ``e.errno`` and ``e.__class__.__name__`` are not, because every
        attribute in those chains is in :data:`_SAFE_EXC_ATTRS`.
        """
        if self._is_our_name(node):
            return True
        if isinstance(node, ast.Subscript):
            return self._is_our_value(node.value)
        if isinstance(node, ast.Attribute):
            chain: list[str] = []
            current: ast.AST = node
            while isinstance(current, ast.Attribute):
                chain.append(current.attr)
                current = current.value
            if not self._is_our_name(current):
                return False
            return not all(attr in _SAFE_EXC_ATTRS for attr in chain)
        return False

    def _is_render_of_our_value(self, node: ast.AST) -> bool:
        """``str(e)`` / ``repr(e)`` — so ``scrub(str(e))`` still counts wrapped."""
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("str", "repr")
            and len(node.args) == 1
            and self._is_our_value(node.args[0])
        )

    def _is_scrubbable(self, node: ast.AST) -> bool:
        return self._is_our_value(node) or self._is_render_of_our_value(node)

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
            self.bare.add(_key(node))
            return
        for kw in node.keywords:
            # Shape 3b — an explicit truthy ``exc_info``. ``exc_info=False`` /
            # ``exc_info=None`` are the documented ways to turn it off, so they
            # are not sinks.
            if kw.arg == "exc_info" and not (
                isinstance(kw.value, ast.Constant) and not kw.value.value
            ):
                self.bare.add(_key(node))
                return
        # Shape 2 — the exception handed over as a lazy ``%s`` argument. args[0]
        # is the format string; anything after it is interpolated into the
        # record exactly as ``str(e)`` would be. Shape 6 rides along here: an
        # ATTRIBUTE passed the same way renders the same way.
        for arg in node.args[1:]:
            if self._is_our_value(arg):
                self.bare.add(_key(arg))
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
            and self._is_scrubbable(node.args[0])
        ):
            self.wrapped.add(_key(node))
            return  # do not descend: the Name inside is accounted for
        if (
            isinstance(func, ast.Name)
            and func.id == AGGRESSIVE_HELPER
            and len(node.args) == 1
            and self._is_scrubbable(node.args[0])
        ):
            # Scrubbed, but by the aggressive entry point. Counts as covered for
            # Tier 1; deliberately NOT counted as part of this sweep.
            return
        if (
            isinstance(func, ast.Name)
            and func.id in ("str", "repr")
            and len(node.args) == 1
            and self._is_our_value(node.args[0])
        ):
            self.bare.add(_key(node))
            return
        # Shape 5 — ``"...".format(e)`` / ``"{e}".format(e=e)``. Any ``.format``
        # call is a candidate; it is our exception appearing among its arguments
        # that makes it a sink, which is specific enough that an unrelated
        # ``formatter.format(record)`` is untouched.
        if isinstance(func, ast.Attribute) and func.attr in ("format", "format_map"):
            rendered = [*node.args, *(kw.value for kw in node.keywords)]
            if any(self._is_our_value(value) for value in rendered):
                self.bare.add(_key(node))
                return
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        # Shape 4 — printf-style interpolation. The right operand is the value,
        # a tuple of values, or a mapping for the ``%(name)s`` form.
        if isinstance(node.op, ast.Mod):
            right = node.right
            if isinstance(right, ast.Dict):
                operands: list[ast.AST] = [v for v in right.values if v is not None]
            elif isinstance(right, ast.Tuple | ast.List):
                operands = list(right.elts)
            else:
                operands = [right]
            if any(self._is_our_value(value) for value in operands):
                self.bare.add(_key(node))
                return
        self.generic_visit(node)

    def visit_FormattedValue(self, node: ast.FormattedValue) -> None:
        if self._is_our_value(node.value):
            self.bare.add(_key(node.value))
            return
        self.generic_visit(node)


def _scan_tree(tree: ast.AST) -> tuple[list[int], list[int]]:
    """Return ``(bare_linenos, wrapped_linenos)`` for one parsed module.

    THREE passes whose results are UNIONED by site identity: the
    name-independent traceback pass, one :class:`_SinkScan` per region from
    :func:`_exception_regions`, and the ``repr``-of-a-non-exception pass. Two of
    the three are name-independent, which is the structural lesson of this
    file — every blind shape it has had was a shape that could not be reached by
    tracking one bound exception name, however well that tracking was done.

    Regions legitimately overlap — a parameter can also be ``isinstance``-
    narrowed inside the same function — so the union is taken over :func:`_key`
    rather than over line numbers, which keeps a site counted exactly once
    however many passes reach it.
    """
    regions = _exception_regions(tree)
    bare, wrapped = _traceback_sites(tree)
    for name, body in regions:
        scan = _SinkScan(name)
        for stmt in body:
            scan.visit(stmt)
        bare |= scan.bare
        wrapped |= scan.wrapped
    bare |= _repr_sinks(tree, {name for name, _ in regions})
    return sorted(lineno for lineno, _ in bare), sorted(lineno for lineno, _ in wrapped)


def _enumerate(path: Path) -> tuple[list[int], list[int]]:
    """Return ``(bare_linenos, wrapped_linenos)`` for one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _scan_tree(tree)


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
        """Scan a snippet through the SAME entry point real source goes through.

        ``_scan_tree`` rather than a hand-rolled handler loop: the traceback and
        non-except-bound passes live outside :class:`_SinkScan`, so a fixture
        harness that only instantiated the visitor per handler would exercise a
        scanner the package is never scanned with — and would have gone on
        reporting green for shapes 6 and 7 forever.
        """
        return _scan_tree(ast.parse(textwrap.dedent(src)))[0]

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
            # Shape 4 — printf-style interpolation, all three right-hand forms.
            ("percent-scalar", '    logger.error("failed: %s" % exc)'),
            ("percent-tuple", '    logger.error("%s: %s" % ("ctx", exc))'),
            ("percent-mapping", '    logger.error("%(e)s" % {"e": exc})'),
            # Shape 5 — str.format, positional and keyword.
            ("format-positional", '    logger.error("failed: {}".format(exc))'),
            ("format-keyword", '    logger.error("{e}".format(e=exc))'),
            # Shape 6 — attributes, which never mention the exception itself.
            ("attr-args", '    logger.error("failed: %s", exc.args)'),
            ("attr-strerror", '    logger.error(f"failed: {exc.strerror}")'),
            ("attr-nested", '    logger.error("failed: %s", exc.response.text)'),
            ("attr-cause", '    logger.error("failed: " + str(exc.__cause__))'),
            ("attr-subscript", '    logger.error("failed: %s", exc.args[0])'),
        ],
    )
    def test_each_leaking_shape_is_flagged(self, label: str, body: str) -> None:
        src = f"try:\n    pass\nexcept Exception as exc:\n{body}\n"
        assert self._scan(src), f"scanner is blind to the {label!r} shape"

    @pytest.mark.parametrize(
        "label, src",
        [
            # Shape 7 — a traceback rendering needs NO handler and no bound name.
            # These are the seven `return {"traceback": ...}` sites in
            # patterns/patterns/, five of which sit in a handler and two of which
            # do not; keying the scan on a bound name could reach neither.
            (
                "format_exc-in-handler",
                "try:\n    pass\nexcept Exception as exc:\n"
                '    return {"error": scrub_remote_error(exc),'
                ' "traceback": traceback.format_exc()}\n',
            ),
            (
                "format_exc-no-handler",
                "def handle(agent, error):\n"
                '    return {"traceback": traceback.format_exc()}\n',
            ),
            ("format_exc-imported-bare", "def f():\n    return format_exc()\n"),
            ("print_exc", "def f():\n    print_exc()\n"),
            # Shape 2/6 without any handler — the exception arrives as a VALUE.
            (
                "isinstance-narrowed-gather-result",
                "async def run(tasks):\n"
                "    results = await asyncio.gather(*tasks, return_exceptions=True)\n"
                "    for result in results:\n"
                "        if isinstance(result, Exception):\n"
                '            out.append({"error": str(result)})\n',
            ),
            (
                "annotated-exception-parameter",
                "def _handle(self, agent, error: Exception):\n"
                '    return {"error": str(error)}\n',
            ),
            (
                "unannotated-parameter-proved-by-raise",
                "def _handle(self, error):\n"
                "    if self.fail_fast:\n"
                "        raise error\n"
                '    return {"error": str(error)}\n',
            ),
            # Shape 8 — repr() of a NON-exception object. Both live variants,
            # which differ only in the attribute literal, plus the !r form.
            (
                "getattr-name-repr-fallback",
                "def register(handler):\n"
                '    name = getattr(handler, "name", repr(handler))\n'
                '    logger.info("registered %s", getattr(handler, "name", repr(handler)))\n',
            ),
            (
                "getattr-dunder-name-repr-fallback",
                "def register(handler):\n"
                '    logger.info("registered %s",'
                ' getattr(handler, "__name__", repr(handler)))\n',
            ),
            (
                "repr-inside-logging-extra",
                "def notify(listener):\n"
                '    logger.warning("failed", extra={"listener": repr(listener)})\n',
            ),
            (
                "repr-conversion-in-fstring",
                'def notify(listener):\n    logger.warning(f"failed for {listener!r}")\n',
            ),
            # The remediation this codebase ACCEPTED is type(x).__name__, not a
            # scrubbed repr -- so a scrubbed repr must still flag. See
            # _repr_sinks' docstring and journey/manager.py.
            (
                "scrubbed-repr-still-flagged",
                "def notify(listener):\n"
                '    logger.warning("failed: %s", scrub_remote_error(repr(listener)))\n',
            ),
            # Shape 8c — %r in the format string with the value as a separate
            # positional argument. No `repr(` token, no !r conversion; the repr
            # happens inside logging's own interpolation. This is the form the
            # executed proof used (event_hooks.py:120). Each fixture invokes the
            # name, which is the callable evidence _percent_r_sinks requires.
            (
                "percent-r-the-proven-shape",
                "def emit(self, event):\n"
                "    for listener in self._listeners:\n"
                "        try:\n"
                "            listener(event)\n"
                "        except Exception as exc:\n"
                "            logger.error(\n"
                '                "Listener %r raised during event %s: %s",\n'
                "                listener,\n"
                "                event.event_type,\n"
                "                scrub_remote_error(exc),\n"
                "            )\n",
            ),
            (
                "percent-r-in-a-later-slot",
                "def emit(tag, handler):\n"
                "    handler()\n"
                '    logger.error("during %s handler %r failed", tag, handler)\n',
            ),
            (
                "percent-r-after-a-literal-percent",
                "def emit(handler):\n"
                "    handler()\n"
                '    logger.error("100%% done, handler %r", handler)\n',
            ),
            (
                "percent-r-mapping-form",
                "def emit(handler):\n"
                "    handler()\n"
                '    logger.error("handler %(h)r", {"h": handler})\n',
            ),
            (
                "percent-r-with-width-and-precision",
                "def emit(handler):\n"
                "    handler()\n"
                '    logger.error("handler %-10.5r", handler)\n',
            ),
            (
                "percent-r-args-splat-unresolvable",
                "def emit(handler, args):\n"
                "    handler()\n"
                '    logger.error("handler %r", *args)\n',
            ),
            (
                "percent-r-single-tuple-argument",
                "def emit(tag, handler):\n"
                "    handler()\n"
                '    logger.error("%s %r", (tag, handler))\n',
            ),
        ],
    )
    def test_each_non_handler_shape_is_flagged(self, label: str, src: str) -> None:
        """The shapes with no ``ExceptHandler`` anywhere in scope.

        Separated from the parametrisation above because those all share a
        ``try/except`` preamble, and a shape whose whole point is that it has no
        handler cannot be expressed in it. That preamble is precisely how the
        earlier fixture set managed to look thorough while covering only sites
        the scanner could already reach.
        """
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
            # Shape 6's allowlist — attributes that cannot carry message text.
            ("attr-errno", '    logger.error("f: %s", exc.errno)'),
            ("attr-returncode", '    logger.error("f: %s", exc.returncode)'),
            ("attr-class-name", '    logger.error("f: %s", exc.__class__.__name__)'),
            (
                "attr-class-name-fstring",
                '    logger.error(f"{exc.__class__.__name__}")',
            ),
            # Shapes 4/5/6 must all stay recognisable as SCRUBBED.
            ("percent-scrubbed", '    logger.error("f: %s" % scrub_local_error(exc))'),
            (
                "format-scrubbed",
                '    logger.error("f: {}".format(scrub_remote_error(exc)))',
            ),
            (
                "attr-scrubbed",
                '    logger.error("f: %s", scrub_remote_error(exc.args))',
            ),
            (
                "scrub-of-str",
                '    logger.error("f: %s", scrub_remote_error(str(exc)))',
            ),
            # Shape 7's negative control: a scrubbed traceback is not a sink.
            (
                "format_exc-scrubbed",
                '    logger.error("f: %s", scrub_remote_error(traceback.format_exc()))',
            ),
            # Modulo on numbers must not be mistaken for interpolation.
            ("arithmetic-modulo", "    _ = exc.errno % 2"),
            # An unrelated .format call on a non-exception argument.
            ("unrelated-format", '    logger.error("f: {}".format(agent_id))'),
        ],
    )
    def test_each_safe_shape_is_not_flagged(self, label: str, body: str) -> None:
        src = f"try:\n    pass\nexcept Exception as exc:\n{body}\n"
        assert not self._scan(src), f"scanner false-positives on {label!r}"

    def test_a_non_exception_isinstance_narrowing_is_not_a_region(self) -> None:
        """``isinstance(x, dict)`` must not make ``x`` an exception.

        Without this the narrowing rule would turn every ``isinstance`` branch
        in the package into a scan region, and the resulting noise is exactly
        what gets a detector switched off.
        """
        src = (
            "def f(results):\n"
            "    for result in results:\n"
            "        if isinstance(result, dict):\n"
            '            logger.error("got %s", result)\n'
        )
        assert not self._scan(src)

    @pytest.mark.parametrize(
        "label, src",
        [
            # repr() outside a log record is not a sink -- __repr__ methods,
            # assertion messages and debug reprs are not credential surfaces.
            (
                "repr-in-dunder-repr",
                "class R:\n"
                "    def __repr__(self):\n"
                '        return f"R(text={repr(self.preview)})"\n',
            ),
            ("repr-in-a-return-value", "def f(x):\n    return repr(x)\n"),
            # The accepted remediation must NOT read as a sink, or the fix has
            # nowhere to land.
            (
                "type-name-fallback",
                "def register(handler):\n"
                '    logger.info("registered %s",'
                ' getattr(handler, "name", type(handler).__name__))\n',
            ),
            # repr OF AN EXCEPTION belongs to shape 1, where scrubbing IS the
            # accepted remediation; shape 8 must not double-claim it.
            (
                "scrubbed-repr-of-an-exception",
                "try:\n    pass\nexcept Exception as exc:\n"
                '    logger.error("f: %s", scrub_remote_error(repr(exc)))\n',
            ),
            # Shape 8c's negative controls. The first is the whole reason for
            # the callable narrowing: %r quoting a STRING is idiomatic and
            # common, and flagging it produced 17 false positives against 11
            # real sites in this package. `line` is never invoked, so there is
            # no evidence it is an object whose __repr__ renders fields.
            (
                "percent-r-quoting-a-string",
                "def parse(line):\n"
                "    try:\n"
                "        return json.loads(line)\n"
                "    except ValueError:\n"
                '        logger.warning("failed to parse line: %r", line[:200])\n',
            ),
            (
                "percent-r-quoting-a-config-name",
                "def load(name, server_data):\n"
                "    if not isinstance(server_data, dict):\n"
                '        logger.warning("MCP server %r: invalid config", name)\n',
            ),
            (
                "percent-s-is-out-of-scope",
                'def emit(h):\n    h()\n    logger.error("%s", h)\n',
            ),
            (
                "literal-percent-only",
                'def emit(h, pct):\n    h()\n    logger.error("100%% done: %s", pct)\n',
            ),
            (
                "percent-r-outside-any-log",
                'def emit(handler):\n    handler()\n    return "handler %r" % handler\n',
            ),
            (
                "percent-r-of-a-scrubbed-exception",
                "try:\n    pass\nexcept Exception as exc:\n"
                '    logger.error("boom %r", scrub_remote_error(exc))\n',
            ),
            (
                "runtime-built-format-string",
                "def emit(fmt, handler):\n"
                "    handler()\n"
                "    logger.error(fmt, handler)\n",
            ),
        ],
    )
    def test_each_safe_repr_shape_is_not_flagged(self, label: str, src: str) -> None:
        """Shape 8's negative controls.

        Without these the ``repr`` pass would pass just as well while flagging
        every ``repr`` in the package, and a detector that noisy is one someone
        switches off — which is the same outcome as the blindness it replaced.
        """
        assert not self._scan(src), f"scanner false-positives on {label!r}"

    def test_raise_of_a_class_is_not_an_exception_valued_name(self) -> None:
        """``raise ValueError`` names a CLASS, not a parameter holding a value.

        The ``raise <param>`` producer is restricted to parameter names for this
        reason; a bare class name in a ``raise`` must not enrol the module-level
        symbol as a scannable exception value.
        """
        src = (
            "def f(payload):\n"
            "    if not payload:\n"
            "        raise ValueError\n"
            '    logger.error("got %s", ValueError)\n'
        )
        assert not self._scan(src)


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
