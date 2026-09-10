#!/usr/bin/env python3
"""Measure CONTENT parity per package: what src has landed since the PyPI upload.

Version parity (declared == PyPI) is NOT content parity. This anchors at the
actual upload timestamp, not at the version-bump commit -- measured on kaizen,
the bump and the release were 11 days apart, so a bump-anchored diff over-reports.

Falsifying result, stated up front: a package with genuinely nothing unreleased
prints commits=0 / files=0. A package with unreleased work prints non-zero. If
the script cannot reach PyPI or git it raises -- it never prints 0 on failure.
"""
import json
import subprocess
import sys
import urllib.request

PKGS = [
    ("kailash", "src/kailash"),
    ("kailash-mcp", "packages/kailash-mcp/src"),
    ("kailash-kaizen", "packages/kailash-kaizen/src"),
    ("kaizen-agents", "packages/kaizen-agents/src"),
    ("kailash-dataflow", "packages/kailash-dataflow/src"),
    ("kailash-nexus", "packages/kailash-nexus/src"),
    ("kailash-ml", "packages/kailash-ml/src"),
    ("kailash-align", "packages/kailash-align/src"),
    ("kailash-pact", "packages/kailash-pact/src"),
]


def pypi_upload_time(pkg: str) -> tuple[str, str]:
    url = f"https://pypi.org/pypi/{pkg}/json"
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    v = d["info"]["version"]
    times = sorted(x["upload_time_iso_8601"] for x in d["releases"][v])
    if not times:
        raise RuntimeError(f"{pkg} {v}: no upload times")
    return v, times[0]


def git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return out.stdout


print(f"{'package':<20} {'ver':<9} {'uploaded':<21} {'commits':>7} {'src files':>10}")
print("-" * 72)
rows = []
for pkg, path in PKGS:
    ver, up = pypi_upload_time(pkg)
    log = git("log", "--oneline", f"--since={up}", "origin/dev", "--", path)
    commits = len([x for x in log.splitlines() if x.strip()])
    names = git(
        "log", f"--since={up}", "--name-only", "--format=", "origin/dev", "--", path
    )
    files = len({x for x in names.splitlines() if x.strip()})
    rows.append((pkg, ver, up, commits, files))
    print(f"{pkg:<20} {ver:<9} {up[:19]:<21} {commits:>7} {files:>10}")

print()
need = [r for r in rows if r[3] > 0]
print(f"Packages with UNRELEASED src work: {len(need)} of {len(rows)}")
for pkg, ver, up, c, f in sorted(need, key=lambda r: -r[4]):
    print(f"  {pkg}: {c} commits, {f} src files since {ver} shipped {up[:10]}")
if not need:
    print("  (none -- every package's src is fully released)")
