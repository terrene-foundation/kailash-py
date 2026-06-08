#!/usr/bin/env python3
"""Detect version-pin drift + policy violations for first-party Kailash packages.

Issue #1183 — "single source of truth for dependency version-pin sourcing".

The monorepo declares the same first-party dependency (``kailash``,
``kailash-kaizen``, …) in many ``pyproject.toml`` manifests, each with its own
``>=`` floor. There is no canonical source, so a bump must touch every manifest
by hand and any divergence is *silent*. This tool makes the drift *loud*.

It is deliberately aligned with ``.claude/rules/dependencies.md``:

* Floors (``>=X.Y``) are *expected* to reflect each package's actual feature
  usage, so the SAME dependency pinned at DIFFERENT floors across DIFFERENT
  packages is **advisory**, not an error — homogenizing floors would violate the
  rule.
* What IS an error:
  1. **Defensive cap on a first-party sibling** (``<``/``<=``/``==``/``!=`` on a
     ``kailash*`` dep) — ``dependencies.md`` § "No Caps" / "No exact pins in
     library pyproject". A cap that excludes the sibling's *current* version is
     a live resolution break.
  2. **Unsatisfiable floor** — a floor greater than the sibling's own current
     in-repo version (the pin can never resolve in the workspace).
  3. **Intra-manifest drift** — the same dependency pinned at two different
     floors *within one manifest* (an unambiguous inconsistency).
* **Advisory** signals: cross-manifest floor divergence, and floors far behind
  the sibling's current version (staleness — a human/feature-usage call).

Exit code is non-zero ONLY on errors (1+2+3), so the check is CI-wireable
without forcing floor homogenization.

Run:  ``python tools/check_pin_consistency.py``  (exit 0 = no errors).
      ``python tools/check_pin_consistency.py --json``  for machine output.
      ``python tools/check_pin_consistency.py --strict-advisory``  also exits
      non-zero on advisory findings (for a stricter gate).

Stdlib-first (``tomllib``, 3.11+). Uses ``packaging`` for correct PEP 440
version comparison when available, with a conservative fallback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

FIRST_PARTY = {
    "kailash",
    "kailash-align",
    "kailash-dataflow",
    "kailash-kaizen",
    "kailash-mcp",
    "kailash-ml",
    "kailash-nexus",
    "kailash-pact",
    "kaizen-agents",
}

PRUNE_PARTS = {".venv", "node_modules", ".claude", "build", "dist", "site-packages"}
FIXTURE_MARKERS = ("tests/fixtures/", "tests\\fixtures\\")

# Specifier operators that constrain the UPPER side (a "cap"). dependencies.md
# forbids these on first-party siblings.
CAP_OPERATORS = ("<", "<=", "==", "!=", "===")


# ---- version comparison --------------------------------------------------
# Prefer PEP 440 comparison via `packaging`; fall back to a numeric release
# tuple so the tool still runs in a minimal CI env without the dependency.

try:
    from packaging.version import Version  # type: ignore
except ImportError:  # pragma: no cover
    Version = None  # type: ignore


def _release_tuple(v: str):
    """Best-effort numeric release tuple, trailing zeros stripped ('1.1.0'->(1,1))."""
    parts = []
    for chunk in re.split(r"[.+!-]", v):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _veq(a: str, b: str) -> bool:
    if Version is not None:
        try:
            return Version(a) == Version(b)
        except Exception:
            pass
    return _release_tuple(a) == _release_tuple(b)


def _vgt(a: str, b: str) -> bool:
    """True if floor `a` is strictly greater than current `b`."""
    if Version is not None:
        try:
            return Version(a) > Version(b)
        except Exception:
            pass
    return _release_tuple(a) > _release_tuple(b)


def _cap_excludes(caps: list[str], current: str) -> bool:
    """True if any upper cap excludes `current` (e.g. '<2.0' vs current 2.0.0)."""
    for c in caps:
        m = re.match(r"(<=|<|==|!=|===)\s*(.+)", c)
        if not m:
            continue
        op, ver = m.group(1), m.group(2)
        if op == "<" and not _vgt(ver, current):  # current >= cap-bound
            return True
        if op == "<=" and _vgt(current, ver):  # current > cap-bound
            return True
        if op in ("==", "===") and not _veq(ver, current):
            return True
        if op == "!=" and _veq(ver, current):
            return True
    return False


def _tilde_upper(ver: str) -> str | None:
    """Exclusive upper bound for a PEP 440 ``~=`` compatible-release specifier.

    ``~=2.7.5`` -> ``"2.8"`` (i.e. ``>=2.7.5,<2.8``); ``~=2.7`` -> ``"3"``
    (``>=2.7,<3``). Returns ``None`` when fewer than two numeric release
    components are present (``~=2`` is not a valid PEP 440 specifier, so there
    is no compatible-release cap to synthesise).
    """
    rel: list[int] = []
    for chunk in re.split(r"[.+!-]", ver):
        if chunk.isdigit():
            rel.append(int(chunk))
        else:
            break
    if len(rel) < 2:
        return None
    rel = rel[:-1]
    rel[-1] += 1
    return ".".join(str(p) for p in rel)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# ---- requirement parsing -------------------------------------------------


@dataclass
class Pin:
    name: str
    floor: str | None  # lower-bound version string, if any
    caps: list[str]  # cap specifiers found (operator+version), e.g. ["<2.0"]
    raw: str  # verbatim requirement string


_SPEC_RE = re.compile(r"(<=|>=|==|===|!=|~=|<|>)\s*([0-9][0-9A-Za-z.+!*-]*)")
_NAME_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(?P<rest>.*)$"
)


def _parse_req(spec: str) -> Pin | None:
    m = _NAME_RE.match(spec)
    if not m:
        return None
    name = _normalize(m.group("name"))
    floor = None
    caps: list[str] = []
    for op, ver in _SPEC_RE.findall(m.group("rest") or ""):
        if op in (">=", ">"):
            # `>` is a strict lower bound; treat it as a floor for drift checks
            # (an unsatisfiable `kailash-ml>3.0` against an in-repo 2.0.0 is the
            # same resolution break a `>=3.0` floor would be). Without this, `>`
            # is parsed into no branch and the dep vanishes from the report.
            floor = ver  # lower bound
        elif op == "~=":
            # PEP 440 compatible-release: a lower bound AND an implicit upper
            # cap (`~=2.7.5` == `>=2.7.5,<2.8`). The cap on a first-party
            # sibling is exactly what dependencies.md § "No Caps" forbids, so
            # it MUST be recorded as a cap — not waved through as a bare floor.
            floor = ver
            upper = _tilde_upper(ver)
            if upper:
                caps.append(f"<{upper}")
        elif op == "==" and "*" not in ver:
            # exact pin acts as both floor and cap
            floor = ver
            caps.append(f"=={ver}")
        elif op in CAP_OPERATORS:
            caps.append(f"{op}{ver}")
    return Pin(name=name, floor=floor, caps=caps, raw=spec.strip())


# ---- manifest discovery + extraction ------------------------------------


def _iter_manifests(root: Path):
    for p in root.rglob("pyproject.toml"):
        rel = p.relative_to(root).as_posix()
        if any(part in PRUNE_PARTS for part in p.parts):
            continue
        if any(marker in rel for marker in FIXTURE_MARKERS):
            continue
        yield p, rel


def _collect_specs(data: dict):
    proj = data.get("project", {})
    for spec in proj.get("dependencies", []) or []:
        yield "project.dependencies", spec
    for group, specs in (proj.get("optional-dependencies", {}) or {}).items():
        for spec in specs or []:
            yield f"optional-dependencies.{group}", spec
    for group, specs in (data.get("dependency-groups", {}) or {}).items():
        for spec in specs or []:
            if isinstance(spec, str):
                yield f"dependency-groups.{group}", spec


@dataclass
class Site:
    manifest: str
    table: str
    floor: str | None
    caps: list[str]
    raw: str


@dataclass
class DepRecord:
    name: str
    sites: list[Site] = field(default_factory=list)


def scan(root: Path):
    deps: dict[str, DepRecord] = {}
    versions: dict[str, str] = {}
    manifests: list[str] = []
    for path, rel in _iter_manifests(root):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError) as exc:
            print(f"WARN: could not parse {rel}: {exc}", file=sys.stderr)
            continue
        manifests.append(rel)
        proj = data.get("project", {})
        pname = proj.get("name")
        pver = proj.get("version")
        own = _normalize(pname) if pname else None
        if own and own in FIRST_PARTY and pver:
            versions[own] = pver
        for table, spec in _collect_specs(data):
            pin = _parse_req(spec)
            if not pin or pin.name not in FIRST_PARTY:
                continue
            if pin.name == own:
                continue  # self-extra reference (e.g. "kailash-ml[dl]")
            if pin.floor is None and not pin.caps:
                continue  # plain self/extra bundle with no version constraint
            rec = deps.setdefault(pin.name, DepRecord(name=pin.name))
            rec.sites.append(Site(rel, table, pin.floor, pin.caps, pin.raw))
    return deps, versions, manifests


# ---- analysis ------------------------------------------------------------


def build_report(root: Path):
    deps, versions, manifests = scan(root)

    caps_errors = []  # (name, site) — defensive cap on first-party sibling
    unsatisfiable = []  # (name, current, site) — floor > current in-repo version
    intra_manifest = []  # (name, manifest, {floor: [sites]})
    cross_manifest = []  # (name, distinct_floors, sites)  [advisory]
    stale = []  # (name, current, floor, sites)            [advisory]

    for name in sorted(deps):
        rec = deps[name]
        current = versions.get(name)

        # 1. caps on first-party siblings
        for s in rec.sites:
            if s.caps:
                caps_errors.append((name, s))

        # 2. unsatisfiable floor (> current in-repo version)
        if current:
            for s in rec.sites:
                if s.floor and _vgt(s.floor, current):
                    unsatisfiable.append((name, current, s))

        # group sites by floor (semantic equality collapses 1.1 / 1.1.0)
        def _floor_group(sites):
            groups: dict[str, list[Site]] = {}
            for s in sites:
                if not s.floor:
                    continue
                placed = False
                for key in groups:
                    if _veq(key, s.floor):
                        groups[key].append(s)
                        placed = True
                        break
                if not placed:
                    groups[s.floor] = [s]
            return groups

        # 3. intra-manifest drift: same dep, >1 floor within one manifest
        by_manifest: dict[str, list[Site]] = {}
        for s in rec.sites:
            by_manifest.setdefault(s.manifest, []).append(s)
        for manifest, sites in by_manifest.items():
            g = _floor_group(sites)
            if len(g) > 1:
                intra_manifest.append((name, manifest, g))

        # cross-manifest divergence (advisory)
        allg = _floor_group(rec.sites)
        if len(allg) > 1:
            cross_manifest.append((name, sorted(allg), rec.sites))

        # staleness (advisory): floor far behind current. Group floors
        # semantically (allg collapses 1.1 / 1.1.0) so equal floors emit once.
        if current:
            for fl, sites in allg.items():
                # "far behind" = different major/minor pair than current
                if _release_tuple(fl)[:2] != _release_tuple(current)[:2] and not _vgt(
                    fl, current
                ):
                    stale.append((name, current, fl, sites))

    return {
        "deps": deps,
        "versions": versions,
        "manifests": manifests,
        "caps_errors": caps_errors,
        "unsatisfiable": unsatisfiable,
        "intra_manifest": intra_manifest,
        "cross_manifest": cross_manifest,
        "stale": stale,
    }


def _print_human(rep) -> int:
    print(
        f"Scanned {len(rep['manifests'])} manifests; {len(rep['deps'])} first-party deps pinned.\n"
    )

    errs = 0

    if rep["caps_errors"]:
        errs += len(rep["caps_errors"])
        print(
            f"❌ ERROR — defensive cap on a first-party sibling ({len(rep['caps_errors'])}):"
        )
        print("   (dependencies.md § 'No Caps' / 'No exact pins in library pyproject')")
        for name, s in rep["caps_errors"]:
            cur = rep["versions"].get(name)
            note = "  ← EXCLUDES current!" if cur and _cap_excludes(s.caps, cur) else ""
            print(
                f"   • {name} caps={s.caps} (current {cur}){note} — {s.manifest} [{s.table}]  «{s.raw}»"
            )
        print()

    if rep["unsatisfiable"]:
        errs += len(rep["unsatisfiable"])
        print(
            f"❌ ERROR — floor exceeds sibling's current version, unsatisfiable ({len(rep['unsatisfiable'])}):"
        )
        for name, cur, s in rep["unsatisfiable"]:
            print(
                f"   • {name} >={s.floor} but current is {cur} — {s.manifest} [{s.table}]"
            )
        print()

    if rep["intra_manifest"]:
        errs += len(rep["intra_manifest"])
        print(
            f"❌ ERROR — same dependency pinned at divergent floors WITHIN one manifest ({len(rep['intra_manifest'])}):"
        )
        for name, manifest, groups in rep["intra_manifest"]:
            print(f"   • {name} in {manifest}: floors {{{', '.join(sorted(groups))}}}")
            for floor in sorted(groups):
                for s in groups[floor]:
                    print(f"       >={floor:<8} [{s.table}]  «{s.raw}»")
        print()

    if errs == 0:
        print(
            "✅ No errors (no caps, no unsatisfiable floors, no intra-manifest drift).\n"
        )

    # advisory
    if rep["cross_manifest"]:
        print(
            f"ℹ  ADVISORY — cross-manifest floor divergence ({len(rep['cross_manifest'])}):"
        )
        print(
            "   (legitimate per-package feature-usage differences per dependencies.md;"
        )
        print("    review whether the lower floors are intentional or just stale)")
        for name, floors, sites in rep["cross_manifest"]:
            cur = rep["versions"].get(name)
            print(f"   • {name} (current {cur}) — floors {{{', '.join(floors)}}}")
            for s in sites:
                if s.floor:
                    print(f"       >={s.floor:<8} {s.manifest} [{s.table}]")
        print()

    if rep["stale"]:
        seen = set()
        rows = []
        for name, cur, floor, sites in rep["stale"]:
            for s in sites:
                k = (name, floor, s.manifest, s.table)
                if k in seen:
                    continue
                seen.add(k)
                rows.append((name, cur, floor, s))
        if rows:
            print(
                f"ℹ  ADVISORY — floor far behind sibling's current version ({len(rows)}):"
            )
            for name, cur, floor, s in rows:
                print(
                    f"   • {name} >={floor} (current {cur}) — {s.manifest} [{s.table}]"
                )
            print()

    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Detect first-party pin drift (#1183).")
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument(
        "--strict-advisory",
        action="store_true",
        help="also exit non-zero on advisory findings",
    )
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    rep = build_report(root)

    n_err = (
        len(rep["caps_errors"]) + len(rep["unsatisfiable"]) + len(rep["intra_manifest"])
    )
    n_adv = len(rep["cross_manifest"]) + len(rep["stale"])

    if args.json:
        out = {
            "manifests_scanned": len(rep["manifests"]),
            "first_party_deps": len(rep["deps"]),
            "errors": {
                "caps": [
                    {
                        "name": n,
                        "caps": s.caps,
                        "manifest": s.manifest,
                        "table": s.table,
                        "raw": s.raw,
                    }
                    for n, s in rep["caps_errors"]
                ],
                "unsatisfiable": [
                    {
                        "name": n,
                        "floor": s.floor,
                        "current": cur,
                        "manifest": s.manifest,
                        "table": s.table,
                    }
                    for n, cur, s in rep["unsatisfiable"]
                ],
                "intra_manifest": [
                    {"name": n, "manifest": m, "floors": sorted(g)}
                    for n, m, g in rep["intra_manifest"]
                ],
            },
            "advisory": {
                "cross_manifest": [
                    {"name": n, "current": rep["versions"].get(n), "floors": fl}
                    for n, fl, _ in rep["cross_manifest"]
                ],
                "stale": [
                    {"name": n, "current": cur, "floor": fl, "manifest": s.manifest}
                    for n, cur, fl, sites in rep["stale"]
                    for s in sites
                ],
            },
            "error_count": n_err,
            "advisory_count": n_adv,
            "ok": n_err == 0,
        }
        print(json.dumps(out, indent=2))
    else:
        _print_human(rep)
        print(f"Summary: {n_err} error(s), {n_adv} advisory finding(s).")

    if n_err > 0:
        return 1
    if args.strict_advisory and n_adv > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
