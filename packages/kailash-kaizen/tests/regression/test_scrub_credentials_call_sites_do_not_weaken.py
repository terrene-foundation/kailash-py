# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""No production call site defeats ``scrub_credentials``'s aggressive default.

THE THIRD AXIS. THIS FILE PINS KWARG VALUES AT THE CALL SITE, NOTHING ELSE
--------------------------------------------------------------------------
``scrub_credentials`` grew two keyword-only gates,
``redact_paths=True`` and ``redact_opaque_tokens=True``. Both default to the
AGGRESSIVE value, and that default is the security posture: on a
provider-error surface an attacker can influence the string, so a leaked live
credential is strictly worse than a blanked token.

Three INDEPENDENT propositions have to hold for that posture to reach a user,
and each needs its own instrument, because each of the other two stays GREEN
while its own proposition is false:

* **Axis 1 — is every sink WRAPPED AT ALL, and is the bound symbol the
  CANONICAL one?** Owned by
  ``packages/kaizen-agents/tests/regression/test_local_error_sinks_are_scrubbed.py``.
  Its Tier 1 re-derives, per module, the set of ``except X`` handlers whose
  bound exception name reaches a string context and asserts none is bare
  (pinned at 51 files / 180 sites so the parametrisation cannot silently
  shrink to zero and still report green); Tier 2 asserts the imported
  ``scrub_local_error`` IS the object in ``kaizen.utils.credential_scrub``, so
  no module drifts onto a local copy; Tier 3 checks per-module behaviour;
  Tier 4 drives six agent-facing tool sinks end to end through
  ``Tool.execute``.
* **Axis 2 — do the DEFAULTS still fire aggressively?** Owned by
  ``test_scrub_credentials_ordinary_text_is_not_noop.py`` plus the
  ``test_issue_1974*`` family, which call ``scrub_credentials(text)`` with NO
  flags and therefore observe whatever the signature currently defaults to.
* **Axis 3 — does any call site pass a WEAKENING keyword argument?** THIS
  FILE, and nothing else in the repo.

Axis 3 exists because axes 1 and 2 are STRUCTURALLY BLIND to it, not merely
silent about it. A site can be fully wrapped (Tier 1 counts it as scrubbed),
bind the canonical symbol (Tier 2 passes), behave correctly under the symbol
it imported (Tier 3 passes), reach the model through a real ``ToolResult``
(Tier 4 passes), AND still read::

    scrub_credentials(str(exc), redact_paths=False, redact_opaque_tokens=False)

Tier 1's walker resolves the CALLEE and stops there — it never inspects
``ast.Call.keywords`` — so the weakened call is indistinguishable from an
aggressive one at every tier. Axis 2 is blind for a different reason: it pins
the function's DEFAULT PARAMETER VALUES, and those can survive BYTE-FOR-BYTE
in the signature while dying at every caller. Per
``rules/instrument-discipline.md`` MUST-1, a check whose output does not
change when the proposition is false is not evidence for that proposition, so
neither axis may be cited for this one.

The converse also holds and is what keeps this file honest: axis 3 is blind
to a sink that is not wrapped at all, and to a module that drifted onto a
local copy of the helper. It reports on keyword VALUES at calls it can see.
Three instruments, three propositions; citing any one for another's claim is
the failure this split exists to prevent.

WHY AN AST WALK, NOT A GREP
---------------------------
The instrument here is an ``ast`` walk, not a grep. This is a STRUCTURAL
property of the source (does any ``Call`` node to these two names carry a
weakening keyword?), and per ``rules/testing.md`` § "``__all__`` /
Re-export Symbol Counts Use Structural Enumeration, Not Grep" and
``rules/probe-driven-verification.md`` MUST-3 a structural property is
scored structurally. A regex over source text cannot tell a real call from
the same bytes inside a docstring, a comment, or the function's own
signature — this module's ground truth includes all three
(``credential_scrub.py`` names ``redact_paths=True`` in its ``def`` line and
quotes ``scrub_credentials()`` inside prose).

WHAT IS NOT A VIOLATION HERE
----------------------------
``packages/kaizen-agents/src/kaizen_agents/patterns/discovery.py`` calls the
AGGRESSIVE entry point (``scrub_credentials``) rather than the conservative
``scrub_local_error`` preset, deliberately and by a separate earlier change.
It passes NO gated kwargs, so it KEEPS the aggressive default — which is
precisely the compliant case this file is defending. It is not allowlisted
and needs no exemption: there is nothing to flag.

FAIL-CLOSED, DELIBERATELY
-------------------------
A gated kwarg is accepted ONLY when its value is the literal ``True``.
Anything else — ``False``, ``0``, ``None``, a variable, a conditional
expression, or a ``**kwargs`` splat that could carry either flag — is
reported. A dynamic value is not "probably fine": it is a value this
instrument cannot decide, and deciding it silently in the permissive
direction is how the whole class re-opens. If a site legitimately needs a
dynamic flag, it goes in ``_ALLOWLIST`` with a stated reason, which is a
review event rather than an invisible one.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, List, NamedTuple, Tuple

import pytest

pytestmark = pytest.mark.regression

# ---------------------------------------------------------------------------
# What we walk
# ---------------------------------------------------------------------------
#: Repo root: .../packages/kailash-kaizen/tests/regression/<this file>
_REPO_ROOT: Path = Path(__file__).resolve().parents[4]

#: The tree that OWNS the scrubber. Its absence is a broken checkout, not a
#: reason to pass — every anchor assertion below applies to it unconditionally.
_KAIZEN_SRC: Path = _REPO_ROOT / "packages" / "kailash-kaizen" / "src" / "kaizen"

#: The sibling package that consumes it. 51 of its modules import
#: ``scrub_local_error`` and one imports ``scrub_credentials`` directly, so a
#: call-site invariant that stopped at the package boundary would miss the
#: overwhelming majority of the call sites it exists to guard. READ-ONLY: this
#: suite parses that tree, it never writes to it.
_AGENTS_SRC: Path = _REPO_ROOT / "packages" / "kaizen-agents" / "src" / "kaizen_agents"

#: Directory names that are never production source.
_SKIP_DIR_PARTS = frozenset({"__pycache__", "tests", "test"})

#: The functions whose aggression this suite pins.
#:
#: ``scrub_remote_error`` joined when the ~180-site sweep was re-triaged: it is
#: the second named preset (opaque tokens ON, paths OFF) for sinks whose
#: exception can be raised at a provider / HTTP / subprocess boundary, where the
#: conservative preset's disabled shape-only rules are the ONLY rules that claim
#: a prefix-less credential. It is guarded here for the same reason its sibling
#: is: so that a future call site cannot quietly pass a gated kwarg through it.
_GUARDED_CALLEES = frozenset(
    {"scrub_credentials", "scrub_local_error", "scrub_remote_error"}
)

#: The keyword-only gates whose ``True`` default IS the security posture.
_GATED_KWARGS = frozenset({"redact_paths", "redact_opaque_tokens"})


# ---------------------------------------------------------------------------
# ALLOWLIST — every entry states WHY that site legitimately weakens
# ---------------------------------------------------------------------------
# Keyed by (path relative to the repo root, callee name). The value is the set
# of gated kwargs that site is permitted to weaken; a site that weakens a
# kwarg OUTSIDE its entry is still reported, so widening an existing exemption
# is as visible as adding a new one.
_ALLOWLIST: dict[Tuple[str, str], frozenset] = {
    # TWO wrapper presets share this key, because the allowlist is keyed by
    # (file, callee) and both delegate to ``scrub_credentials`` from this file:
    #
    #   * ``scrub_local_error``  — weakens BOTH gates (see below).
    #   * ``scrub_remote_error`` — weakens ONLY ``redact_paths``; it keeps
    #     ``redact_opaque_tokens`` at its aggressive default precisely because
    #     the two shape-only rules are the only ones that claim a prefix-less
    #     credential (a bare AWS secret, a bare 32+ hex Azure ``api-key``), and
    #     those DO arrive on a sink fed by a provider boundary. Its weakened set
    #     is a strict subset of this entry, so it is covered without widening.
    #
    # ``scrub_local_error`` IS the named CONSERVATIVE preset over
    # ``scrub_credentials``. Turning both gates off is not a weakening of the
    # posture, it is the entire content of the function: on a LOCAL-error
    # surface the redacted bytes are the diagnostic payload (an ``OSError``
    # message IS a path plus a reason, and local orchestration errors are keyed
    # by git SHA / run id / trace id — all claimed by the two shape-only
    # rules). Its docstring and the module's own bipolar corpus in
    # test_scrub_credentials_ordinary_text_is_not_noop.py verify that the
    # remaining rules are a no-op over credential-free text, which is what
    # makes the preset safe. This is the ONE site where the weakening is the
    # feature; every other caller inherits the aggressive default.
    (
        "packages/kailash-kaizen/src/kaizen/utils/credential_scrub.py",
        "scrub_credentials",
    ): frozenset({"redact_paths", "redact_opaque_tokens"}),
}


class _Finding(NamedTuple):
    """One call site passing a gated kwarg we cannot prove is aggressive."""

    relpath: str
    lineno: int
    callee: str
    kwarg: str
    rendered: str

    def render(self) -> str:
        return (
            f"  {self.relpath}:{self.lineno}  {self.callee}(..., "
            f"{self.kwarg}={self.rendered})"
        )


def _iter_source_files(root: Path) -> Iterator[Path]:
    """Yield every production ``.py`` file under ``root``.

    Excludes caches, vendored egg-info metadata, and anything that is itself a
    test — a test is allowed to exercise the weakened form (that is how the
    conservative preset gets covered at all), so including tests here would
    make the invariant unstatable.
    """
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*.py")):
        parts = set(path.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        if any(part.endswith(".egg-info") for part in path.parts):
            continue
        name = path.name
        if name.startswith("test_") or name.endswith("_test.py"):
            continue
        yield path


def _callee_name(node: ast.Call) -> str | None:
    """Resolve the called NAME, for both bare and attribute-qualified calls.

    ``scrub_credentials(...)`` -> ``ast.Name.id``;
    ``credential_scrub.scrub_credentials(...)`` -> ``ast.Attribute.attr``.
    A ``def`` of the same name is an ``ast.FunctionDef``, never an ``ast.Call``,
    so the definition site (whose signature literally reads
    ``redact_paths: bool = True``) cannot be reached from here — pinned by
    ``test_definition_site_is_not_mistaken_for_a_call_site`` below.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _is_provably_aggressive(value: ast.expr) -> bool:
    """True only for the literal ``True``. Everything else is undecided."""
    return isinstance(value, ast.Constant) and value.value is True


def _scan(root: Path) -> Tuple[List[_Finding], List[Tuple[str, int, str]]]:
    """Return ``(findings, call_sites)`` for every guarded call under ``root``.

    ``call_sites`` is the enumeration receipt: it is what proves the walk
    actually reached the code, so a walk that silently found nothing cannot be
    read as "no violations".
    """
    findings: List[_Finding] = []
    call_sites: List[Tuple[str, int, str]] = []

    for path in _iter_source_files(root):
        relpath = path.relative_to(_REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            callee = _callee_name(node)
            if callee not in _GUARDED_CALLEES:
                continue

            call_sites.append((relpath, node.lineno, callee))
            permitted = _ALLOWLIST.get((relpath, callee), frozenset())

            for kw in node.keywords:
                if kw.arg is None:
                    # ``**opts`` — could carry either gate; undecidable here.
                    if not permitted:
                        findings.append(
                            _Finding(
                                relpath,
                                node.lineno,
                                callee,
                                "**splat",
                                ast.unparse(kw.value),
                            )
                        )
                    continue
                if kw.arg not in _GATED_KWARGS:
                    continue
                if _is_provably_aggressive(kw.value):
                    continue
                if kw.arg in permitted:
                    continue
                findings.append(
                    _Finding(
                        relpath,
                        node.lineno,
                        callee,
                        kw.arg,
                        ast.unparse(kw.value),
                    )
                )

    return findings, call_sites


#: Every failure message in this module leads with the axis, because the
#: three scrub instruments fail for three different reasons and the first
#: question a reader asks is which one just fired.
_AXIS = "AXIS 3 (CALL-SITE KWARG VALUES) FAILED"

_FAILURE_PREAMBLE = (
    f"{_AXIS}: a production call site is DEFEATING the aggressive "
    "credential-scrub default by passing a weakening keyword argument.\n\n"
    "`scrub_credentials` defaults `redact_paths=True` and "
    "`redact_opaque_tokens=True`; those defaults ARE the security posture on "
    "any surface an attacker can influence. A caller passing a value this "
    "check cannot prove is `True` turns the corresponding rules OFF for that "
    "surface — the signature keeps advertising the aggressive default while "
    "the bytes that reach the user are scrubbed by the conservative one.\n\n"
    "The other two axes are GREEN through exactly this failure and must NOT "
    "be cited against it:\n"
    "  * AXIS 1 (sink wrapped at all / canonical symbol bound) — "
    "kaizen-agents' test_local_error_sinks_are_scrubbed.py resolves the "
    "CALLEE and never inspects the call's keywords, so a weakened call reads "
    "to it as scrubbed.\n"
    "  * AXIS 2 (defaults still aggressive) — "
    "test_scrub_credentials_ordinary_text_is_not_noop.py pins the "
    "signature's DEFAULT PARAMETER VALUES, which are untouched by a caller "
    "overriding them.\n\n"
    "Offending site(s):\n"
)

_FAILURE_EPILOGUE = (
    "\n\nIf the site is legitimately conservative (a LOCAL-error surface where "
    "the redacted bytes are the diagnostic payload), prefer calling "
    "`scrub_local_error(...)` — the ONE named preset that owns that trade. "
    "If it genuinely needs its own combination, add it to `_ALLOWLIST` in "
    "this file WITH a stated reason, so the exemption is a review event."
)


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------
def test_no_production_call_site_weakens_the_scrub() -> None:
    """No `scrub_credentials` / `scrub_local_error` call turns a gate off."""
    kaizen_findings, kaizen_sites = _scan(_KAIZEN_SRC)
    agents_findings, agents_sites = _scan(_AGENTS_SRC)

    # Enumeration receipt FIRST. A walk that reached nothing produces an empty
    # findings list, which is byte-identical to a clean result — so the
    # non-emptiness is asserted before the findings are read, not after.
    assert kaizen_sites, (
        f"{_AXIS} — as an INSTRUMENT failure, not a finding: walked "
        f"{_KAIZEN_SRC} and found ZERO calls to {sorted(_GUARDED_CALLEES)}. "
        "The scrubber lives in this tree, so an empty enumeration means the "
        "walk broke (moved package root, changed exclusion set) — NOT that "
        "the invariant holds."
    )

    findings = kaizen_findings + agents_findings
    assert not findings, (
        _FAILURE_PREAMBLE + "\n".join(f.render() for f in findings) + _FAILURE_EPILOGUE
    )


def test_walk_reaches_the_known_scrub_consumers() -> None:
    """The walked set contains the modules this invariant exists to cover.

    Without this, every assertion above degrades quietly the moment the
    enumeration stops reaching a tree: an empty walk yields zero findings,
    which reads exactly like a clean run.
    """
    _, kaizen_sites = _scan(_KAIZEN_SRC)
    kaizen_files = {relpath for relpath, _, _ in kaizen_sites}

    for expected in (
        "packages/kailash-kaizen/src/kaizen/utils/credential_scrub.py",
        "packages/kailash-kaizen/src/kaizen/nodes/ai/error_sanitizer.py",
        "packages/kailash-kaizen/src/kaizen/llm/errors.py",
        "packages/kailash-kaizen/src/kaizen/rich_output.py",
        "packages/kailash-kaizen/src/kaizen/core/autonomy/hooks/security/redaction.py",
    ):
        assert expected in kaizen_files, (
            f"{_AXIS} — INSTRUMENT failure: {expected} calls a guarded "
            "scrubber but the AST walk did not reach it, so this suite's "
            "keyword-value verdict does not cover it. Walked files with call "
            f"sites: {sorted(kaizen_files)}"
        )

    if _AGENTS_SRC.is_dir():
        _, agents_sites = _scan(_AGENTS_SRC)
        # 51 modules import `scrub_local_error` and one imports
        # `scrub_credentials`; the floor is deliberately far below that count
        # so ordinary churn does not red the suite, while a walk that stopped
        # reaching the tree still does.
        assert len(agents_sites) >= 20, (
            f"{_AXIS} — INSTRUMENT failure: kaizen-agents is present but the "
            f"walk found only {len(agents_sites)} guarded call sites there. "
            "test_local_error_sinks_are_scrubbed.py pins that tree at 51 "
            "files / 180 scrubbed sinks, so a count this low is an "
            "enumeration failure, not a real count."
        )


def test_definition_site_is_not_mistaken_for_a_call_site() -> None:
    """`def scrub_credentials(..., redact_paths: bool = True, ...)` is not a Call.

    The definition's own signature carries both gated kwarg NAMES, and its
    docstring quotes `scrub_credentials()` in prose. A grep-based instrument
    would report all three; the AST walker must report none of them, and the
    only call it may find in that file is the wrapper's own (allowlisted) one.
    """
    source = (_KAIZEN_SRC / "utils" / "credential_scrub.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    defs = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert _GUARDED_CALLEES <= defs, (
        f"{_AXIS} — INSTRUMENT failure: both guarded functions must be "
        "DEFINED in this module for the no-false-positive claim to mean "
        f"anything; found {sorted(defs)}"
    )

    calls = [
        (node.lineno, _callee_name(node))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _callee_name(node) in _GUARDED_CALLEES
    ]
    assert calls == [
        (lineno, "scrub_credentials") for lineno, _ in calls
    ], f"unexpected guarded call shapes in the defining module: {calls}"
    assert len(calls) == 2, (
        "the defining module should contain exactly TWO guarded calls — the "
        "`scrub_local_error` and `scrub_remote_error` wrappers, each "
        "delegating to `scrub_credentials`. "
        f"Found {len(calls)}: {calls}. If a third call landed, it needs its "
        "own allowlist entry or it is a real weakening."
    )


def test_default_pinning_suites_still_rely_on_the_defaults() -> None:
    """AXIS 2 is still a live instrument — verified here, not assumed.

    This file's docstring claims axis 2 (the DEFAULT-pinning suites) and axis
    3 (this one) are independent and jointly necessary. Naming that split is
    not evidence for it: axis 2 stops discriminating the moment its calls stop
    exercising the defaults, and axis 3 would then be citing a dead
    instrument. So the property is asserted here.

    The claim holds only while the default-pinning suites actually exercise
    the DEFAULTS — i.e. while a substantial body of their calls supplies
    NEITHER gate and therefore observes whatever the signature currently
    defaults to. If every one of their calls started supplying the flags
    explicitly, axes 2 and 3 would BOTH be pinning caller-supplied values and
    NOTHING in the repo would verify that the default itself is aggressive.

    Two distinct things are checked, and the distinction is load-bearing:

    * a call passing NOTHING is what pins the default (counted, floored);
    * a call passing ``redact_paths=True`` is NOT a defect — that is
      ``TestAggressiveDefaultIsUnchanged``, whose entire job is to assert
      explicit-True equals implicit, which is the additivity contract. Only a
      value this module cannot prove is ``True`` counts as an offender, using
      the same fail-closed predicate as the production scan.

    ``placeholder=`` is not a gated kwarg and is freely varied by these
    suites; only the two aggression gates are considered here.
    """
    regression_dir = Path(__file__).resolve().parent
    targets = sorted(regression_dir.glob("test_issue_1974*.py")) + [
        regression_dir / "test_scrub_credentials_ordinary_text_is_not_noop.py"
    ]
    present = [p for p in targets if p.is_file()]
    assert len(present) >= 5, (
        "AXIS 2 (DEFAULTS STILL AGGRESSIVE) FAILED — its suites are missing: "
        "expected the issue-1974 family plus the ordinary-text corpus to be "
        f"present; found {[p.name for p in present]}"
    )

    offenders: List[str] = []
    total_calls = 0
    default_relying_calls = 0
    for path in present:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _callee_name(node) not in _GUARDED_CALLEES:
                continue
            total_calls += 1
            supplied = {kw.arg for kw in node.keywords} & _GATED_KWARGS
            if not supplied:
                default_relying_calls += 1
            for kw in node.keywords:
                if kw.arg not in _GATED_KWARGS:
                    continue
                if _is_provably_aggressive(kw.value):
                    continue
                offenders.append(
                    f"{path.name}:{node.lineno} passes {kw.arg}={ast.unparse(kw.value)}"
                )

    assert total_calls >= 10, (
        "AXIS 2 (DEFAULTS STILL AGGRESSIVE) — INSTRUMENT failure: its suites "
        f"should contain many guarded calls; found {total_calls}. An "
        "empty/near-empty count means this check walked the wrong files and "
        "proves nothing about them."
    )
    assert default_relying_calls >= 10, (
        "AXIS 2 (DEFAULTS STILL AGGRESSIVE) FAILED — it no longer observes "
        f"the defaults: only {default_relying_calls} of {total_calls} guarded "
        "calls in the default-pinning suites supply NEITHER aggression gate. "
        "Those bare calls are the ONLY ones that observe the signature's "
        "default, so if they disappear the aggressive default becomes "
        "unverified — and this file's three-independent-axes claim becomes "
        "false."
    )
    assert not offenders, (
        "AXIS 2 (DEFAULTS STILL AGGRESSIVE) FAILED — its suites now pass an "
        "aggression gate a value this check cannot prove is `True`:\n  "
        + "\n  ".join(offenders)
        + "\n\nA suite pinning the WEAKENED behaviour cannot also be the "
        "evidence that the aggressive default still fires."
    )
