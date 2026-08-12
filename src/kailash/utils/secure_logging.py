"""Secure logging utilities for masking sensitive data.

This module provides mixins and utilities for automatically detecting and
masking PII, credentials, and other sensitive information in logs.

It also provides two helpers that narrow a log line BY CONSTRUCTION rather than
by pattern-matching -- :func:`safe_callable_name` and
:func:`safe_exception_frames`. Prefer those wherever the object being logged is
CALLER-SUPPLIED: the masking below is best-effort over an open-ended payload,
while those two emit only source-level identifiers.

WHAT THAT DOES AND DOES NOT PROMISE. An earlier version of this header claimed
those identifiers "cannot carry a payload at all". That is FALSE and was
measured false -- a class name is mintable via
``type(f"ServerError_{data}", (Exception,), {})``, a function ``__name__`` is
plainly assignable, and ``__qualname__`` can resolve through a caller-controlled
``__getattr__`` returning any string whatsoever. Measured: a ``__getattr__``
returning ``"postgres://svc:hunter2@h/db"`` was emitted verbatim, and a
5000-character ``__qualname__`` came back at full length.

What IS true is narrower and is enforced here rather than asserted: every such
identifier is passed through :func:`_safe_identifier` before it reaches a
record, which BOUNDS its length and confines it to a conservative character set.
That removes the unbounded-length and record-forgery channels. It does NOT make
the identifier payload-free -- a short attacker-chosen name still survives, by
design, because it is often the only diagnostic there is. Treat these helpers as
"structurally inert and bounded", never as "cannot carry data".
"""

import functools
import json
import logging
import os
import re
import traceback
import unicodedata
from functools import wraps
from typing import Any, Dict, List, Optional, Pattern, Set, Union

from kailash.utils.url_credentials import is_sensitive_query_key

# Module-level logger. Added with the totality-wrapper telemetry below: this
# module had NO module-scope logger, only an instance one on the mixin, so a
# bare ``logger.debug`` in the wrapper raised NameError -- inside the very
# handler whose contract is that it never raises. Caught by driving the wrapper
# before commit, not by review.
_LOGGER = logging.getLogger(__name__)

# A partial wrapping a partial is flattened by CPython, so one unwrap is the
# normal case; the bound keeps a hand-built chain from spinning.
_MAX_PARTIAL_UNWRAP = 10

# Frames kept per exception in safe_exception_frames. Deep recursive failures
# produce thousands of identical frames; the innermost ones locate the fault.
_DEFAULT_FRAME_LIMIT = 20

# Resolved once at import: a cwd at or above this is not a workspace root, and
# rendering paths relative to it discloses the home-directory layout
# _relative_frame_path exists to hide. Read at call time it would be the same
# value on every call anyway, and resolving it here keeps that function free of
# a second environment read.
_HOME_DIR = os.path.expanduser("~")

# Exceptions described per chain in safe_exception_frames. The `seen` set stops
# a CYCLE; nothing stopped a long ACYCLIC one, and a retry loop doing
# `raise X from prev` produced 5000 links in a single 175,000-character log
# record. Output is O(chain x limit), so the chain needs its own bound.
#
# The innermost links carry the original failure, so truncation drops the OUTER
# wrappers and says how many, rather than trimming silently. NOTE FOR ANYONE
# CHANGING THIS: the first implementation of that sentence did the opposite of
# what it said -- it truncated during the walk, which keeps the outermost links
# because `__cause__` walks INWARD. The behaviour is pinned by
# `test_root_cause_survives_the_chain_cap`; if you rework the walk, that test is
# the one that matters.
_MAX_CHAIN_LINKS = 10

# Ceiling on any single attacker-influenceable identifier (class name, function
# name, frame name, frame path) entering a record. Long enough that a real
# qualname or vendored path survives intact; short enough that 5000 characters
# of caller-chosen text cannot.
_MAX_IDENTIFIER_CHARS = 120

# Hard ceiling on the caller-supplied ``limit``. Without it the per-identifier
# bound does not bound the RECORD: a caller passing a large limit against a
# RecursionError traceback (~1000 frames) renders megabytes. Every in-tree call
# site uses <= 20, so this clamps a latent API-contract gap, not a live path.
# With it, the worst case is 10 links x 50 frames x ~270 chars ~= 139 KB; with
# the DEFAULT limit of 20 it is ~56 KB.
_MAX_FRAME_LIMIT = 50

# Everything OUTSIDE this set is replaced before an identifier is rendered.
# Deliberately excludes the characters this module uses structurally --
# ``<`` ``>`` ``@`` ``:`` and space -- so that a rendered record's own grammar
# (" <- " between links, "@" before frames, ">" between frames, ":" inside
# path:lineno:name, and every "<...>" marker) CANNOT be forged from caller data.
# Newline is excluded for the same reason: it forges an entire extra log line.
# ``\`` is included because it is the WINDOWS path separator and is NOT
# structural to this module's grammar (the delimiters are " <- ", "@", ">", ":",
# "<", ">" and newline). Excluding it mangled every Windows frame path --
# ``svc\db\connect.py`` -> ``svc?db?connect.py`` -- degrading the diagnostic this
# helper exists to preserve, on a platform the module already reasons about.
_UNSAFE_IDENTIFIER_CHARS = re.compile(r"[^A-Za-z0-9_.\-/\\]")

#: Unicode categories that can forge a log RECORD rather than merely appear odd
#: in one: Cc (control, incl. CR/LF), Cf (format, incl. bidi overrides that
#: reorder a rendered line), Zl/Zp (LINE and PARAGRAPH SEPARATOR, which many log
#: viewers and JSON consumers break lines on exactly as they do on ``\n``).
_RECORD_FORGING_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})

#: The ASCII line terminators, stripped by an explicit substitution in
#: :func:`safe_log_text` before the category sweep. Redundant with ``Cc`` on
#: purpose -- see the two-pass note there.
_LOG_LINE_TERMINATORS = re.compile(r"[\r\n]")

#: Prose log fields get a longer bound than identifiers: a server label or an
#: auth reason is a sentence, and truncating it at the 120-char identifier bound
#: routinely cut the operative clause off the end of the message.
_MAX_LOG_TEXT_CHARS = 300

# CPython's fixed pseudo-identifier literals for frame names and synthetic
# filenames. Passed through byte-intact on an EXACT match so the frames most
# useful for locating a comprehension, lambda, module-scope or import failure
# stay readable. A closed set, never a pattern -- see _safe_identifier.
_CPYTHON_PSEUDO_IDENTIFIERS = frozenset(
    {
        "<module>",
        "<lambda>",
        "<listcomp>",
        "<dictcomp>",
        "<setcomp>",
        "<genexpr>",
        "<string>",
        "<stdin>",
        "<frozen importlib._bootstrap>",
        "<frozen importlib._bootstrap_external>",
    }
)


def _safe_identifier(value: object, *, allow_pseudo: bool = False) -> str:
    """Bound and neutralize one attacker-influenceable identifier.

    Three properties, each measured by a regression pin rather than asserted:

    1. **Bounded.** Output never exceeds ``_MAX_IDENTIFIER_CHARS`` plus a fixed
       truncation marker, so no identifier can drive log volume.
    2. **Structurally inert.** No output character can close or open any
       delimiter this module renders, so a record's grammar always reflects the
       walk that produced it and never caller-supplied text.

       ONE STATED EXCEPTION, because an earlier revision of this line said
       ``<`` and ``>`` "can never survive from input" and that absolute is not
       what the code does: with ``allow_pseudo=True`` (the two FRAME sites only)
       an EXACT match against :data:`_CPYTHON_PSEUDO_IDENTIFIERS` passes through
       intact. So a ``<...>`` sequence in a record is ours OR a known interpreter
       literal -- never arbitrary caller text. At every other call site,
       including all three that render CLASS names, ``<`` and ``>`` are stripped
       unconditionally.
    3. **Total.** Never raises. A logging call site must not fail on the thing
       it is describing, so a non-string or an object whose ``__str__`` raises
       degrades to a marker rather than propagating.

    NOT a redaction step: a short attacker-chosen identifier survives on
    purpose. Bounding and de-fanging is the contract; secrecy is not.
    """
    try:
        raw = value if isinstance(value, str) else str(value)
        # NORMALIZE TO A PLAIN ``str`` BEFORE ANY PREDICATE RUNS. This is the
        # load-bearing line of the whole function.
        #
        # ``isinstance(value, str)`` admits a SUBCLASS, and every predicate below
        # -- ``not text``, ``text in <frozenset>``, ``len(cleaned)`` -- dispatches
        # to a method the subclass can override. The frozenset membership test in
        # particular is NOT byte-equality: it is ``__hash__`` then ``__eq__``,
        # both overridable. MEASURED, before this line existed:
        #
        #     class Sneak(str):
        #         def __hash__(self): return hash("<module>")
        #         def __eq__(self, other): return True
        #
        # returned 5043 characters containing a newline, " <- " and "@" straight
        # through the allowlist branch -- bypassing the charset filter AND the
        # length bound at once, and defeating every property this module claims.
        # Reachable through all three entry points: ``type.__name__`` preserves
        # the subclass on round-trip (measured), and ``func.__name__`` /
        # ``__qualname__`` accept one by assignment.
        #
        # ``str.__str__`` returns a plain ``str`` for a subclass instance, so
        # after this line every predicate is the builtin. ``str(value)`` alone is
        # NOT sufficient -- ``__str__`` is overridable and may itself return a
        # subclass, which is why the result is re-normalized on type identity
        # rather than on ``isinstance``.
        # noqa: E721 is CORRECT here and MUST NOT be "fixed" to isinstance().
        # E721 says "do not compare types, use isinstance()" -- but isinstance()
        # admitting subclasses IS the vulnerability this line closes. Swapping it
        # reintroduces the CRITICAL verbatim: a str subclass with a lying
        # __eq__/__hash__ walks the allowlist and returns 5043 unsanitized
        # characters. Exact type identity is the entire point.
        text = raw if type(raw) is str else str.__str__(raw)  # noqa: E721
    except Exception:
        return "<unrepresentable>"
    if not text:
        return "<empty>"
    # CPython's own pseudo-identifiers pass through INTACT on an exact match.
    # Without this they mangle to "?module?" / "?listcomp?" -- which destroys the
    # frames most used to locate a comprehension or import failure, AND leaves a
    # "?...?" form that is itself forgeable (a class named "!listcomp!" renders
    # identically). Exact-match is what makes this safe to re-admit <> for:
    # nothing an attacker supplies reaches this branch unless it is byte-equal to
    # a fixed CPython literal.
    #
    # RESIDUAL, stated: a class named EXACTLY "<listcomp>" also matches and will
    # render as a genuine frame label would. That is a cosmetic confusion (an
    # exception claiming to be a comprehension frame), NOT a grammar forgery --
    # it cannot open or close a delimiter, invent a chain link, or inject a line.
    # ``allow_pseudo`` is OFF by default and set only at the two FRAME sites.
    # The allowlist is documented as covering frame names and synthetic
    # filenames, but the same function also renders CLASS names -- so
    # ungated, a class named ``<module>`` rendered as ``<module>``, exactly
    # where a genuine module-frame label renders (measured). That widened the
    # allowlist past its stated purpose for free.
    if allow_pseudo and text in _CPYTHON_PSEUDO_IDENTIFIERS:
        return text
    cleaned = _UNSAFE_IDENTIFIER_CHARS.sub("?", text)
    # ``len`` on a str SUBCLASS is overridable, so the bound below could in
    # principle be decided by attacker code. Measured: it cannot -- ``re.sub``
    # returns a plain ``str`` copy for a subclass input (the zero-match identity
    # optimization applies to exact ``str`` only), so ``cleaned`` is always a
    # real ``str`` by this line and ``len`` is the builtin. Pinned by
    # ``test_a_lying_len_str_subclass_cannot_defeat_the_bound``.
    if len(cleaned) > _MAX_IDENTIFIER_CHARS:
        # Marker uses <> precisely because input cannot contain them.
        return f"{cleaned[:_MAX_IDENTIFIER_CHARS]}<truncated>"
    return cleaned


def safe_log_text(value: object, *, limit: int = _MAX_LOG_TEXT_CHARS) -> str:
    """Bound and de-fang caller-supplied PROSE destined for a log field.

    The sibling of :func:`_safe_identifier`, for the case that helper is wrong
    for. Its charset (``[^A-Za-z0-9_.\\-/\\\\]``) is deliberately identifier-
    shaped, so a human-readable sentence -- a server label, an
    ``external_auth_reason`` -- comes out as ``mounted?under?Enterprise...``
    and the operator loses the message. This keeps printable text and removes
    only what can forge a RECORD.

    Two properties:

    1. **No line forgery.** Every Unicode character in categories ``Cc``
       (control, including ``\\r`` and ``\\n``), ``Cf`` (format, including the
       bidi overrides that reorder a rendered line), ``Zl`` and ``Zp`` becomes
       ``?``. ``Zl``/``Zp`` matter as much as ``\\n``: ``U+2028`` LINE
       SEPARATOR is treated as a line break by many log viewers and JSON
       consumers, so stripping only ASCII newlines leaves the injection open
       in a form that reads as invisible whitespace in a diff.
    2. **Bounded.** Never longer than ``limit`` plus a fixed marker, so a
       caller-supplied string cannot drive log volume.

    Total -- never raises. A logging call site must not fail on the thing it is
    describing, so an object whose ``__str__`` raises degrades to a marker.

    NOT a redaction step. Bounding and de-fanging is the contract; a caller who
    puts a secret in a server title still gets it logged. Do not pass values
    that may hold credentials.

    Args:
        value: The caller-supplied value to render.
        limit: Maximum characters before truncation.

    Returns:
        A bounded, control-character-free string safe to place in a log field.
    """
    try:
        raw = value if isinstance(value, str) else str(value)
        # Normalize a ``str`` SUBCLASS to a plain ``str`` before any predicate
        # runs, for the reason documented at length in ``_safe_identifier``: a
        # subclass can override ``__len__``/``__eq__``/``__hash__`` and decide
        # the bound below in attacker code. Exact type identity, not
        # isinstance.
        text = raw if type(raw) is str else str.__str__(raw)  # noqa: E721
    except Exception:
        return "<unrepresentable>"
    if not text:
        return "<empty>"
    # TWO passes, and both are load-bearing. ORDER MATTERS, for a reason that
    # is about tooling rather than behaviour -- the output is identical either
    # way, since both passes replace with the same character.
    #
    # 1. The category sweep is what makes the guarantee real: beyond CR/LF it
    #    removes U+2028/U+2029, the C1 controls, and the bidi overrides that
    #    reorder an already-written line.
    # 2. The explicit regex substitution over the ASCII line terminators is a
    #    no-op by the time it runs -- pass 1 has already replaced them. It is
    #    kept, and kept LAST, because it is the recognized shape of a
    #    log-injection barrier and it must be the final transformation the
    #    returned value flows through. Measured: with the regex first and the
    #    join last, `py/log-injection` was still reported at every call site,
    #    because the value actually returned came from the join.
    #
    # Dropping either is a regression: pass 1 alone loses the recognized
    # barrier, pass 2 alone is the ASCII-only strip this function replaces.
    swept = "".join(
        "?" if unicodedata.category(ch) in _RECORD_FORGING_CATEGORIES else ch
        for ch in text
    )
    cleaned = _LOG_LINE_TERMINATORS.sub("?", swept)
    if len(cleaned) > limit:
        # Marker uses <> precisely because... they are ours: the categories
        # stripped above cannot produce them, and a caller who writes a literal
        # "<truncated>" forges only a cosmetic suffix, never a new record.
        return f"{cleaned[:limit]}<truncated>"
    return cleaned


def safe_type_name(obj: object) -> str:
    """Bounded, structurally inert name of an object's TYPE, for a log field.

    THE SINK-SIDE HALF of :func:`safe_exception_frames`. Hardening the helper
    alone was not enough: nine call sites logged ``type(exc).__name__`` RAW as a
    sibling ``%s`` in the SAME log call, so the sanitized field and an
    unsanitized copy of the same identifier landed four characters apart.
    Measured, a class named ``"A\\nERROR fake-log-line"`` put a real newline into
    the record through the raw field while the helper's field rendered
    ``A?ERROR?fake-log-line``, and a 5000-character class name arrived in full.

    The type name is NOT redundant with the chain render and MUST NOT be dropped
    to "fix" this: the chain keeps the INNERMOST links, so on a chain longer than
    :data:`_MAX_CHAIN_LINKS` the caught exception's own type is evicted and this
    field is the only place it appears.
    """
    try:
        return _safe_identifier(type(obj).__name__)
    except Exception:
        # Total for the same reason safe_callable_name is: this is called from
        # inside ``except`` blocks, where raising REPLACES the handled exception.
        return "<unrepresentable>"


def safe_callable_name(obj: Any) -> str:
    """Name a CALLER-SUPPLIED callable for a log line without rendering its repr.

    The idiom this replaces is ``getattr(fn, "__name__", repr(fn))``. Python
    evaluates a ``getattr`` default eagerly but only USES it when the attribute
    is absent -- and the callables that lack ``__name__`` are exactly the ones
    that carry payloads:

    * ``functools.partial(connect, dsn="postgres://svc:<credential>@host/db")``
      renders its bound arguments verbatim.
    * a callable object with a dataclass-generated ``__repr__`` renders EVERY
      field, including a credential one, without the call or the exception
      mentioning it.

    A plain ``def`` function has ``__name__``, so the fallback never fires for
    one -- which is why the idiom reads as safe and is not.

    Resolution order:

    1. ``__qualname__`` / ``__name__`` when present -- unchanged behaviour for
       every plain function and method.
    2. For a ``functools.partial``, the WRAPPED function's own name, rendered
       ``partial(<name>)``. ``type(obj).__name__`` alone would be ``"partial"``
       for every partial ever passed, which on a dependency-injection surface
       is not a diagnostic at all -- it cannot tell the database dependency
       from the cache one. ``partial.func`` is the wrapped function; the
       payload lives in ``partial.args`` / ``partial.keywords``, which are
       never read here.
    3. Otherwise ``type(obj).__name__`` -- a class name.

    WHAT THE RETURNED NAME IS AND IS NOT. An earlier version of item 3 said a
    class name "cannot carry a caller payload". That is FALSE and was measured
    false: ``type("K_hunter2", (), {})`` mints one carrying arbitrary text, and
    item 1 fires FIRST and is worse -- ``__name__`` is plainly assignable and
    ``__qualname__`` can resolve through a caller-controlled ``__getattr__``
    returning any string (measured: ``"postgres://svc:hunter2@h/db"`` returned
    verbatim; a 5000-character name returned at full length).

    Every return below therefore passes through :func:`_safe_identifier`, which
    BOUNDS the length and strips the characters this module renders
    structurally. A short caller-chosen name still survives, by design -- it is
    frequently the only diagnostic available. Read the result as "bounded and
    structurally inert", never as "payload-free".

    Returns a string for every object that misbehaves; it does not raise on
    account of the object, because a logging call site must not fail on the
    thing it is trying to describe.

    THE ATTRIBUTE READS BELOW CAN RAISE, WHICH IS WHY THEY ARE GUARDED.
    ``getattr(x, attr, default)`` swallows ONLY ``AttributeError`` -- anything
    else the descriptor raises propagates -- and ``isinstance`` consults
    ``__class__``, which is equally caller-controlled. A lazy proxy is the
    ordinary case, not an exotic one: a Werkzeug/Flask ``LocalProxy`` raises
    ``RuntimeError("Working outside of request context")``, a Django
    ``SimpleLazyObject`` raises whatever its setup function raises, and an
    unbound client raises ``ConnectionError``. Unguarded, that escapes into
    callers which invoke this INSIDE an ``except`` block (``runtime/scheduler``,
    ``runtime/distributed``, the nexus resolver), where it would REPLACE the
    exception being handled -- turning a logging helper into a defect that
    destroys the diagnostic it exists to produce -- and into
    ``utils/lifespan``, which calls it BEFORE its ``try`` and documents that one
    handler raising must not prevent the next from running.

    ``Exception``, deliberately NOT ``BaseException``: ``KeyboardInterrupt``,
    ``SystemExit`` and ``CancelledError`` are the program being stopped, not the
    object misbehaving, and swallowing a cancellation here would re-open at the
    logging layer exactly the defect the channel-lifecycle work closed at the
    channel layer.
    """
    target = obj
    unwrapped = 0
    try:
        while True:
            for attribute in ("__qualname__", "__name__"):
                name = getattr(target, attribute, None)
                # A non-str __name__ is possible on an exotic object; only a real
                # string is usable, and only a non-empty one is a diagnostic.
                if isinstance(name, str) and name:
                    safe = _safe_identifier(name)
                    return f"partial({safe})" if unwrapped else safe
            if (
                isinstance(target, functools.partial)
                and unwrapped < _MAX_PARTIAL_UNWRAP
            ):
                target = target.func
                unwrapped += 1
                continue
            type_name = _safe_identifier(type(target).__name__)
            return f"partial({type_name})" if unwrapped else type_name
    except Exception:
        # Fall back to the ONE read that cannot be intercepted by the object:
        # its type's name. Reached only when the object actively resisted
        # description, so the lost precision is the object's own doing.
        try:
            return _safe_identifier(type(obj).__name__)
        except Exception:
            return "<unrepresentable>"


def _relative_frame_path(filename: str) -> str:
    """Render a traceback filename workspace-relative.

    Absolute paths disclose the operator's home-directory layout to whatever
    ships the logs. Falls back to the basename when the file lives outside the
    working directory (or on another Windows drive) rather than emitting a
    ``../../..`` chain that hints at the same layout.
    """
    try:
        cwd = os.getcwd()
        relative = os.path.relpath(filename, cwd)
    except (ValueError, OSError):
        return os.path.basename(filename)
    if relative.startswith(".."):
        return os.path.basename(filename)
    # A cwd sitting AT OR ABOVE the home directory -- "/" under a systemd unit
    # with no WorkingDirectory, or "/home" -- makes every rendering beneath it
    # disclose the exact layout this function exists to hide, and does it
    # WITHOUT ever producing a leading "..", so the guard above never fires.
    # Such a cwd is not a workspace root, so decline to render against it.
    try:
        if os.path.commonpath([cwd, _HOME_DIR]) == cwd and cwd != _HOME_DIR:
            return os.path.basename(filename)
    except ValueError:
        # Different drives on Windows: no common path, nothing to disclose.
        pass
    return relative


def safe_exception_frames(
    exc: BaseException,
    *,
    limit: int = _DEFAULT_FRAME_LIMIT,
    follow_chain: bool = True,
) -> str:
    """Total wrapper over :func:`_safe_exception_frames_impl`.

    TOTALITY IS THE CONTRACT, for the same reason :func:`safe_callable_name`
    argues for its own guard: this helper is called from INSIDE ``except``
    blocks, so an exception raised here REPLACES the exception being handled --
    the caller's error disappears and is replaced by a failure in the logging
    helper. ``safe_callable_name`` was given that guard in round 1; its sibling
    was not, and round 10 measured the gap.

    Every read the walk performs -- ``__cause__``, ``__context__``,
    ``__traceback__`` -- is a getset descriptor on ``BaseException`` that a
    SUBCLASS can shadow with a property, and the threat model already grants the
    attacker the exception class. Measured: a class defining
    ``__cause__ = property(raiser)`` made this helper raise ``RuntimeError``
    straight through its caller's ``except`` block.

    ``BaseException`` (not ``Exception``) is deliberately NOT caught here --
    ``KeyboardInterrupt`` / ``SystemExit`` / ``CancelledError`` must propagate,
    matching :func:`safe_callable_name`.
    """
    try:
        return _safe_exception_frames_impl(exc, limit=limit, follow_chain=follow_chain)
    except Exception:
        # No detail from the failure is RENDERED: it may originate in
        # attacker-shadowed descriptors, so its own text is caller-controlled.
        #
        # But it IS reported, at DEBUG, because the previous form swallowed it
        # entirely -- and the comment there asserted the cause was a hostile
        # descriptor when the ``except`` actually catches ANY Exception from the
        # whole impl. This function has already shipped THREE instances of one
        # arithmetic bug; a fourth would have degraded every record to
        # ``<frames-unavailable>`` with no log line, no counter, and no way for an
        # operator to tell our own defect from an attack. That is the
        # ``zero-tolerance.md`` Rule 3 swallow shape. The catch is right; the
        # silence was not.
        try:
            _LOGGER.debug(
                "safe_exception_frames.unavailable",
                exc_info=True,
                extra={"helper": "safe_exception_frames"},
            )
        except Exception:
            # Telemetry must NEVER be able to break totality. A handler that
            # raises while reporting that a handler raised is the same defect
            # one layer up, and this module has already shipped that shape once.
            pass
        return "<frames-unavailable>"


def _safe_exception_frames_impl(
    exc: BaseException,
    *,
    limit: int = _DEFAULT_FRAME_LIMIT,
    follow_chain: bool = True,
) -> str:
    """Render WHERE an exception failed, without rendering WHAT it said.

    This is the replacement for ``exc_info=True`` on a log line whose exception
    is CALLER-SUPPLIED. ``logging`` renders ``exc_info`` by walking the whole
    exception chain and printing each exception's ``str()``, so a driver error
    reading ``could not connect to postgres://svc:<credential>@host/db`` lands
    in the record verbatim -- re-entering through the traceback even when the
    log message itself was built to carry nothing.

    Dropping the traceback outright would close that leak but destroy the
    diagnostic: the operator loses the only record of where the failure came
    from. This keeps the frames -- ``path:line:function`` per frame, plus each
    exception's TYPE -- and drops only the message. Source text is NOT included,
    so a frame cannot echo an interpolated value.

    WHAT THIS DOES NOT PROMISE. An earlier version of this docstring claimed
    every retained element "cannot carry a runtime payload." That is FALSE and
    was measured false, so it is stated correctly here instead. The line number
    is genuinely inert; the other three retained elements are ATTACKER-
    INFLUENCEABLE in narrow, real cases:

    * **class name** -- ``type(f"ServerError_{data}", (Exception,), {})``. SDKs
      that mint an exception class per server error name do exactly this.
    * **function name** -- ``exec``/``compile`` with a data-derived identifier
      (generated RPC stubs, ORM-generated methods).
    * **file path** -- ``compile(src, filename=<data>, ...)``. Jinja2 compiles a
      template with the TEMPLATE NAME as the filename, so a data-derived
      template name reaches the frame, INCLUDING any directory structure in it.
      An earlier revision of this paragraph said only the basename survives
      because :func:`_relative_frame_path` "falls back to the basename". That is
      true on only THREE branches -- ``relpath`` raised, a leading ``".."``, or
      cwd STRICTLY ABOVE the home directory. (Strictly: the guard is
      ``commonpath([cwd, _HOME_DIR]) == cwd and cwd != _HOME_DIR``, so cwd ==
      home takes the COMMON branch and keeps directories. An earlier revision of
      this line said "at/above", which is measurably wrong at exactly that one
      value -- the same overstatement class this paragraph was written to fix.)
      On the COMMON branch (the file resolves
      under cwd) it returns the relative path with directories intact, which
      this repo's own negative control asserts. So the safe statement is
      narrower: an ABSOLUTE path outside cwd collapses to its basename; a path
      under cwd does not.

    This is a far narrower channel than the exception MESSAGE it replaces -- a
    message carries attacker data by default, whereas these carry it only when
    an identifier is minted from that data -- and the helper remains the right
    default. But "narrower" is the honest claim and "cannot" was not, and a
    security helper whose contract overstates itself invites a caller to trust
    it somewhere it should not.

    Args:
        exc: The exception to describe.
        limit: Innermost frames kept per exception. ``<= 0`` retains NO frames
            (type only) -- it does NOT mean unlimited. An earlier version
            skipped the slice entirely for 0 and negatives, so ``limit=0``
            rendered EVERY frame, which is the opposite of what a bound named
            ``limit`` should do.
        follow_chain: Also describe ``__cause__`` / ``__context__``. The cause
            usually holds the real failure site, so this defaults on. The chain
            is capped at :data:`_MAX_CHAIN_LINKS`: ``seen`` stops a CYCLE, but
            nothing stopped a long ACYCLIC chain, and a retry loop doing
            ``raise X from prev`` drove 5000 links to a single 175,000-character
            log record -- the log-spam mode ``observability.md`` forbids, on an
            error path an attacker can drive. **The INNERMOST links are kept**,
            so a root cause cannot be evicted by an attacker who adds WRAPPING
            (outer) layers; the dropped OUTER count is rendered at the head of
            the string.

            THE CONVERSE IS NOT PROMISED, and an earlier revision of this line
            wrongly said "always survives truncation". Keeping a fixed window at
            one END is symmetric: whatever sits at the OTHER end is evictable by
            lengthening the retained end. ``__context__`` is chained implicitly
            whenever an exception is raised while another is handled, so an
            in-handler retry recursion grows the chain INWARD and pushes the
            failure that actually propagated out past the cap. Measured: 15
            in-handler retries under a final ``KeyError`` rendered
            ``<+7 outer links dropped>`` and the ``KeyError`` was absent.
            For a WRAPPER chain -- the diagnostic case this helper serves --
            innermost is the right end; for a RETRY-storm chain it is not, and
            the comment beside the implementation says so too.

    Returns a string like
    ``RuntimeError@svc/db.py:31:connect <- ValueError@svc/dsn.py:12:parse``.
    """
    # WALK THE WHOLE CHAIN FIRST, THEN KEEP THE INNERMOST LINKS.
    #
    # Truncating DURING the walk kept the wrong end. ``exc`` is the OUTERMOST
    # exception and ``__cause__``/``__context__`` walk INWARD, so appending as
    # we go fills [outermost … innermost] and breaking at the cap keeps the ten
    # outermost WRAPPERS while discarding the root cause -- the exact opposite
    # of what this cap is for, and of what the comment beside it claimed.
    # Measured: a ValueError root under 30 RuntimeError wrappers did not appear
    # in the output at all.
    #
    # It was also attacker-driveable. Anything that adds >= _MAX_CHAIN_LINKS
    # wrapping layers above the root -- a retry loop that re-wraps, a
    # middleware stack wrapping per layer -- pushed the original failure past
    # the cap and left ten generic wrappers behind. Keeping the innermost links
    # removes that lever entirely.
    #
    # COST, STATED ACCURATELY. An earlier revision of this comment said the
    # walk "costs nothing". It does not: the pre-cap walk below is O(total
    # chain length) in time AND in auxiliary memory (one `seen` slot + one
    # `links` slot per link), in a quantity an attacker influences -- where the
    # superseded truncate-during-walk did at most _MAX_CHAIN_LINKS iterations.
    # What IS bounded, and is the half that matters for the 175,000-character
    # record this cap exists to prevent, is the RENDER: it still happens at most
    # _MAX_CHAIN_LINKS times, so the emitted record stays bounded regardless of
    # chain length. The residual is a constant-factor overhead on objects the
    # chain already allocated before this function was called -- real, but not a
    # new unbounded allocation and not a DoS. A deque(maxlen=...) plus a counter
    # would bound the walk too, at the cost of the exact dropped-count.
    #
    # Honest trade, not a free win: for a RETRY-storm chain the outermost link
    # is the most RECENT attempt and the innermost the oldest, so "innermost"
    # is not unambiguously better there. For a wrapper chain -- the diagnostic
    # case this helper exists to serve -- the root cause is what an operator
    # needs, and it is also the half an attacker would otherwise evict.
    links: List[BaseException] = []
    seen: Set[int] = set()
    walker: Optional[BaseException] = exc
    while walker is not None and id(walker) not in seen:
        seen.add(id(walker))
        links.append(walker)
        if not follow_chain:
            break
        # HONOR ``__suppress_context__``. ``raise X from None`` is the
        # documented "do not disclose what I was handling" idiom, and it sets
        # __cause__=None AND __suppress_context__=True. The superseded
        # ``__cause__ or __context__`` fell through to __context__ in exactly
        # that case, so a helper whose entire job is disclosure control emitted
        # the one link the author had explicitly suppressed. Measured: a
        # ``raise ValueError("public") from None`` over a
        # ``KeyError("SUPPRESSED_SECRET")`` rendered the KeyError.
        #
        # Note ``raise X from Y`` ALSO sets __suppress_context__=True, so the
        # flag cannot be tested first -- an explicit __cause__ always wins, and
        # the flag only decides whether an IMPLICIT __context__ may be followed.
        # READ THROUGH ``BaseException``'S OWN DESCRIPTORS, never off the
        # instance. A subclass can shadow ``__cause__`` / ``__context__`` /
        # ``__suppress_context__`` with a class attribute or property that either
        # RAISES (round 10) or LIES (measured here): a plain
        # ``__suppress_context__ = False`` class attribute sits earlier in the MRO
        # than BaseException's member descriptor and wins the instance read, so
        # ``raise X from None`` suppression was defeated and the suppressed link
        # rendered. The totality wrapper cannot help against a shadow that lies
        # rather than raises. Reading the descriptor unconditionally returns the
        # real C-struct value and collapses both attack shapes into one defence.
        cause = BaseException.__cause__.__get__(walker)
        if cause is not None:
            walker = cause
        elif BaseException.__suppress_context__.__get__(walker):
            walker = None
        else:
            walker = BaseException.__context__.__get__(walker)

    # ``max(0, ...)`` on the CAP, not just on the result: a NEGATIVE cap
    # made this over-count (a 12-link chain announced 13 dropped). Third
    # instance of one arithmetic bug in this function -- N3's ``limit``, the
    # zero-cap ``kept`` slice, and now ``dropped`` -- which is why it is
    # pinned rather than dismissed as unreachable.
    dropped = max(0, len(links) - max(0, _MAX_CHAIN_LINKS))
    # ``<= 0`` means NO links, not "all links" -- the same arithmetic the frame
    # slice below gets wrong when written as a truthiness test. ``links[-0:]``
    # is ``links[0:]``, i.e. the WHOLE chain, so a zero cap would render every
    # link while announcing that all of them were dropped (measured: cap 0 ->
    # 12 links rendered). This is the N3 bug class in the sibling slice.
    if _MAX_CHAIN_LINKS <= 0:
        kept: List[BaseException] = []
    else:
        kept = links[-_MAX_CHAIN_LINKS:] if dropped else links

    descriptions: List[str] = []
    if dropped:
        # Head, not tail: the dropped links are the OUTER ones, so the marker
        # belongs where they were. Carries the count, so an 11-link chain and a
        # 5000-link retry storm no longer render identically.
        descriptions.append(f"<+{dropped} outer links dropped, cap reached>")

    for current in kept:
        # ``extract_tb`` defaults to ``lookup_lines=True``, so it reads the
        # SOURCE for every frame -- before the slice below throws all but the
        # innermost few away. The docstring above anticipates "thousands of
        # identical frames" from deep recursion; unguarded, that is thousands of
        # linecache reads on an error path an attacker can drive to
        # RecursionError. ``.line`` is never read here (only filename, lineno
        # and name), so the lookup buys nothing at any depth.
        frames = traceback.StackSummary.extract(
            traceback.walk_tb(current.__traceback__), lookup_lines=False
        )
        # ``<= 0`` means NO frames, not "all frames". The old ``if limit > 0``
        # skipped the slice, so a caller asking for zero got everything.
        effective_limit = min(limit, _MAX_FRAME_LIMIT)
        frames = frames[-effective_limit:] if effective_limit > 0 else []
        # Every component below is caller-influenceable and is de-fanged before
        # it is joined: a class name, a frame name and a template BASENAME can
        # all carry caller text (measured -- see the module header). Unfiltered,
        # any of them could forge this record's own grammar: a name containing
        # " <- " invents a chain link, one containing "@" or ">" invents a frame
        # boundary, and one containing a NEWLINE forges an entire extra log
        # line (measured constructible via type("A\nERROR ...", (Exception,), {})).
        # ``lineno`` is an int from the traceback machinery, never caller text.
        rendered_frames = ">".join(
            f"{_safe_identifier(_relative_frame_path(frame.filename), allow_pseudo=True)}"
            f":{frame.lineno}:{_safe_identifier(frame.name, allow_pseudo=True)}"
            for frame in frames
        )
        descriptions.append(
            f"{_safe_identifier(type(current).__name__)}"
            f"@{rendered_frames or '<no-frames>'}"
        )

    return " <- ".join(descriptions)


class SecureLoggingPatterns:
    """Patterns for detecting sensitive data."""

    # Credit card patterns
    CREDIT_CARD = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

    # SSN patterns
    SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

    # Email pattern
    EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")

    # Phone patterns
    PHONE = re.compile(
        r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b"
    )

    # API key patterns
    API_KEY_PATTERNS = [
        re.compile(r"sk-[a-zA-Z0-9]{48}"),  # OpenAI
        re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub
        re.compile(r"[a-zA-Z0-9]{32}"),  # Generic 32-char
    ]

    # Password in various formats
    PASSWORD_PATTERNS = [
        re.compile(r'["\']?password["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pwd["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?pass["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Token patterns
    TOKEN_PATTERNS = [
        re.compile(r'["\']?token["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?api_key["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
        re.compile(r'["\']?secret["\']?\s*[:=]\s*["\']?([^"\']+)["\']?', re.I),
    ]

    # Common PII field names.
    #
    # Credential query-key names (password / pwd / passwd / token /
    # api_key / apikey / secret / access_token / client_secret /
    # private_key / ...) are NOT listed here — they are owned by the SINGLE
    # canonical set ``kailash.utils.url_credentials._SENSITIVE_QUERY_KEYS``
    # and matched via ``is_sensitive_query_key`` in
    # :meth:`SecureLogger._mask_dict`, so there is no local copy to drift.
    # This set holds only the broader PII field names (SSN, email,
    # address, ...) plus ``pass`` (ambiguous; outside the URL-query set).
    PII_FIELD_NAMES = {
        "ssn",
        "social_security",
        "social_security_number",
        "credit_card",
        "card_number",
        "cc_number",
        "pass",
        "email",
        "email_address",
        "phone",
        "phone_number",
        "address",
        "street_address",
        "home_address",
        "date_of_birth",
        "dob",
        "birthdate",
        "driver_license",
        "license_number",
        "passport",
        "passport_number",
        "bank_account",
        "account_number",
        "routing_number",
    }


class SecureLogger:
    """Logger that automatically masks sensitive data."""

    def __init__(
        self,
        name: str,
        mask_char: str = "*",
        mask_length: int = 8,
        custom_patterns: Optional[List[Pattern]] = None,
        custom_fields: Optional[Set[str]] = None,
    ):
        """
        Initialize secure logger.

        Args:
            name: Logger name
            mask_char: Character to use for masking
            mask_length: Fixed length for masks (0 = preserve length)
            custom_patterns: Additional regex patterns to mask
            custom_fields: Additional field names to mask
        """
        self.logger = logging.getLogger(name)
        self.mask_char = mask_char
        self.mask_length = mask_length
        self.custom_patterns = custom_patterns or []
        self.custom_fields = custom_fields or set()

    def _mask_value(self, value: str, preserve_partial: bool = True) -> str:
        """Mask a sensitive value."""
        if not value:
            return value

        if self.mask_length > 0:
            # Fixed length mask
            return self.mask_char * self.mask_length
        elif preserve_partial and len(value) > 8:
            # Preserve first 2 and last 2 chars
            return value[:2] + self.mask_char * (len(value) - 4) + value[-2:]
        else:
            # Full mask
            return self.mask_char * len(value)

    def _mask_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively mask sensitive fields in dictionary."""
        masked = {}

        for key, value in data.items():
            # Check if field name indicates sensitive data. Credential
            # query-key names route through the single canonical helper
            # (normalized match: ``access_token``/``client_secret``/... all
            # covered); PII field names + custom fields use exact match.
            if (
                key.lower() in SecureLoggingPatterns.PII_FIELD_NAMES
                or key.lower() in self.custom_fields
                or is_sensitive_query_key(key)
            ):
                masked[key] = (
                    self._mask_value(str(value)) if value is not None else None
                )
            elif isinstance(value, dict):
                masked[key] = self._mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self._mask_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def _mask_string(self, text: str) -> str:
        """Mask sensitive patterns in string."""
        # Credit cards
        text = SecureLoggingPatterns.CREDIT_CARD.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # SSNs
        text = SecureLoggingPatterns.SSN.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=False), text
        )

        # Emails - preserve domain
        text = SecureLoggingPatterns.EMAIL.sub(
            lambda m: self._mask_email(m.group()), text
        )

        # Phone numbers
        text = SecureLoggingPatterns.PHONE.sub(
            lambda m: self._mask_value(m.group(), preserve_partial=True), text
        )

        # API keys
        for pattern in SecureLoggingPatterns.API_KEY_PATTERNS:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        # Passwords and tokens
        for pattern in (
            SecureLoggingPatterns.PASSWORD_PATTERNS
            + SecureLoggingPatterns.TOKEN_PATTERNS
        ):
            text = pattern.sub(
                lambda m: m.group().replace(m.group(1), self._mask_value(m.group(1))),
                text,
            )

        # Custom patterns
        for pattern in self.custom_patterns:
            text = pattern.sub(lambda m: self._mask_value(m.group()), text)

        return text

    def _mask_email(self, email: str) -> str:
        """Mask email preserving domain."""
        if "@" in email:
            local, domain = email.split("@", 1)
            return self._mask_value(local, preserve_partial=True) + "@" + domain
        return self._mask_value(email)

    def _mask_data(self, data: Any) -> Any:
        """Mask sensitive data in any format."""
        if isinstance(data, str):
            return self._mask_string(data)
        elif isinstance(data, dict):
            return self._mask_dict(data)
        elif isinstance(data, (list, tuple)):
            return [self._mask_data(item) for item in data]
        else:
            return data

    def debug(self, msg: str, *args, **kwargs):
        """Log debug with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.debug(masked_msg, **masked_kwargs)

    def info(self, msg: str, *args, **kwargs):
        """Log info with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.info(masked_msg, **masked_kwargs)

    def warning(self, msg: str, *args, **kwargs):
        """Log warning with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.warning(masked_msg, **masked_kwargs)

    def error(self, msg: str, *args, **kwargs):
        """Log error with masking."""
        masked_msg = self._mask_string(msg % args if args else msg)
        masked_kwargs = self._mask_dict(kwargs)
        self.logger.error(masked_msg, **masked_kwargs)


class SecureLoggingMixin:
    """Mixin to add secure logging to any class."""

    def __init__(self, *args, **kwargs):
        """Initialize with secure logger."""
        super().__init__(*args, **kwargs)
        self._secure_logger = SecureLogger(
            name=f"{self.__class__.__module__}.{self.__class__.__name__}",
            custom_fields=getattr(self, "_sensitive_fields", set()),
        )

    def log_debug(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log debug with automatic masking."""
        if data:
            self._secure_logger.debug(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.debug(msg)

    def log_info(self, msg: str, data: Optional[Dict[str, Any]] = None):
        """Log info with automatic masking."""
        if data:
            self._secure_logger.info(
                f"{msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.info(msg)

    def log_error(
        self,
        msg: str,
        error: Optional[Exception] = None,
        data: Optional[Dict[str, Any]] = None,
    ):
        """Log error with automatic masking."""
        error_msg = f"{msg}: {str(error)}" if error else msg
        if data:
            self._secure_logger.error(
                f"{error_msg}: {json.dumps(self._secure_logger._mask_data(data))}"
            )
        else:
            self._secure_logger.error(error_msg)


def secure_log(mask_params: Optional[List[str]] = None):
    """Decorator for secure logging of function calls."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = SecureLogger(f"{func.__module__}.{func.__name__}")

            # Mask specified parameters
            masked_kwargs = {}
            for key, value in kwargs.items():
                if mask_params and key in mask_params:
                    masked_kwargs[key] = logger._mask_value(str(value))
                else:
                    masked_kwargs[key] = logger._mask_data(value)

            logger.debug(f"Calling {func.__name__} with args: {masked_kwargs}")

            try:
                result = func(*args, **kwargs)
                logger.debug(f"{func.__name__} completed successfully")
                return result
            except Exception as e:
                logger.error(f"{func.__name__} failed: {str(e)}")
                raise

        return wrapper

    return decorator


def apply_secure_logging_to_node(node_class):
    """Decorator to add secure logging to a node class."""

    # Create new class that inherits from both
    class SecureNode(SecureLoggingMixin, node_class):
        """Node with secure logging enabled."""

        def run(self, **inputs):
            """Run with secure logging."""
            self.log_debug("Node execution started", inputs)

            try:
                result = super().run(**inputs)
                self.log_debug("Node execution completed")
                return result
            except Exception as e:
                self.log_error("Node execution failed", e, inputs)
                raise

    # Preserve original class name and module
    SecureNode.__name__ = node_class.__name__
    SecureNode.__module__ = node_class.__module__
    SecureNode.__qualname__ = node_class.__qualname__

    return SecureNode
