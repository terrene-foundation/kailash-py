# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""No-secrets scan over ``from_brief()`` regression fixtures.

Issue #1125 brief item B2b: every fixture file under
``tests/regression/from_brief/fixtures/`` MUST be free of
credential-shaped substrings. A brief used as a regression fixture is
read by the test runner, may be logged to CI output, and lives forever
in git history — a real-looking credential in a fixture leaks the same
way a real credential in source code does.

This test runs as a Tier-1 structural scan (no LLM, no infrastructure)
per ``rules/probe-driven-verification.md`` Rule 3 — credential
detection is a structural property (regex over file bytes), not a
semantic property. The scan is in scope precisely BECAUSE its
output's meaning is "did this byte pattern appear in this file?".

Origin: issue #1125 brief item B2b — the regression-test fixture set
is itself a credential-leak surface unless explicitly gated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import pytest


class BriefFixtureLeakError(AssertionError):
    """A fixture file contains a credential-shaped substring."""


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


# Patterns mirror :mod:`kailash._from_brief.scrubber` for symmetry with
# the runtime scrubber. The scan is intentionally strict — fixtures
# that legitimately need to mention credential SHAPES (e.g. an example
# brief teaching credential handling) MUST use the literal
# ``[REDACTED]`` sentinel, NOT a fake credential-shaped string.
LEAK_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "openai/anthropic API key",
        re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}\b"),
    ),
    (
        "password kv-pair",
        re.compile(r"\bpassword\s*=\s*\S+", re.IGNORECASE),
    ),
    (
        "URL with embedded credentials",
        re.compile(r"://[^/\s:]+:[^@\s]+@"),
    ),
    (
        "bearer token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b"),
    ),
    (
        "AWS access key",
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    ),
    # SEC-3: mirror the extended corpus added to scrubber.py. See
    # workspaces/from-brief-1125/04-validate/round-02-security.md:78-103.
    (
        "github personal access token",
        re.compile(
            r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"
            r"|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
        ),
    ),
    (
        "google api key",
        re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b"),
    ),
    (
        "slack token",
        re.compile(r"\bxox[bopars]-[A-Za-z0-9\-]{10,}\b"),
    ),
    (
        "jwt token",
        re.compile(r"\bey[A-Za-z0-9_\-]+\.ey[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    ),
    (
        "stripe api key",
        re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{20,}\b"),
    ),
    (
        "twilio token",
        re.compile(r"\bSK[a-f0-9]{32}\b"),
    ),
]


# ``[REDACTED]`` is the canonical sentinel emitted by ``scrub_brief()``
# and accepted in fixtures as evidence that a credential was
# intentionally redacted. The scanner exempts substrings containing
# this sentinel from the false-positive list.
ALLOWED_SENTINEL = "[REDACTED]"


def _iter_fixture_files() -> List[Path]:
    """Return every regular file under FIXTURE_DIR.

    Skips hidden anchor files (``.gitkeep``, ``.gitignore``) and
    directories. Empty ``FIXTURE_DIR`` is acceptable — the scan
    reports zero files and the test passes (the regression suite has
    no fixtures yet at S1; later shards will add some).
    """
    if not FIXTURE_DIR.exists():
        return []
    return [
        p for p in FIXTURE_DIR.rglob("*") if p.is_file() and not p.name.startswith(".")
    ]


def _scan_file(path: Path) -> List[Tuple[str, str]]:
    """Return ``[(pattern_name, matched_substring), ...]`` for ``path``.

    Reads file bytes as UTF-8 with lenient errors so the scan never
    fails to read a fixture. Returns an empty list when the file
    contains no leak patterns. Matches containing the ALLOWED_SENTINEL
    are filtered (e.g. ``password=[REDACTED]`` is permitted).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        # An unreadable fixture is a different class of failure; raise
        # AssertionError so the test surfaces the issue loudly.
        raise BriefFixtureLeakError(f"could not read fixture {path}: {exc}") from exc

    findings: List[Tuple[str, str]] = []
    for name, pattern in LEAK_PATTERNS:
        for match in pattern.finditer(text):
            substring = match.group(0)
            if ALLOWED_SENTINEL in substring:
                continue
            findings.append((name, substring))
    return findings


@pytest.mark.regression
def test_from_brief_fixtures_contain_no_credentials():
    """Every fixture file MUST be free of credential-shaped substrings.

    Raises :class:`BriefFixtureLeakError` (a typed
    :class:`AssertionError` subclass) listing every offending file +
    pattern + matched substring so the fix is mechanical: replace the
    matched substring with ``[REDACTED]`` (the canonical sentinel) or
    remove the credential entirely.
    """
    fixtures = _iter_fixture_files()
    leaks: List[str] = []
    for path in fixtures:
        for pattern_name, matched in _scan_file(path):
            relpath = path.relative_to(FIXTURE_DIR)
            leaks.append(f"  {relpath}: {pattern_name} matched {matched!r}")
    if leaks:
        joined = "\n".join(leaks)
        raise BriefFixtureLeakError(
            "credential-shaped substrings found in regression "
            "fixtures (B2b of issue #1125):\n" + joined
        )
