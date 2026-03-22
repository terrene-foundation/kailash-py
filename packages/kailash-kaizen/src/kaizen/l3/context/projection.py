# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 ScopeProjection — custom dot-segment glob matching (AD-L3-13).

Pattern semantics (dot-separated segments):
    "*"  — matches exactly one segment (no dots)
    "**" — matches zero or more segments

DO NOT use ``fnmatch`` — it operates on characters, not dot-separated
segments.  This module implements the matching algorithm from scratch
per AD-L3-13.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "ScopeProjection",
]


# ---------------------------------------------------------------------------
# Segment-level matching
# ---------------------------------------------------------------------------


def _match_segments(pattern_parts: list[str], key_segments: list[str]) -> bool:
    """Match key segments against pattern parts using DP.

    Rules:
        - A literal part matches an identical segment.
        - ``"*"`` matches exactly one segment.
        - ``"**"`` in the middle matches zero or more segments.
        - ``"**"`` as the final part matches ONE or more segments
          (because the preceding dot implies additional content).
        - ``"**"`` as the ONLY part matches one or more segments
          (matches any non-empty key).

    Uses iterative dynamic programming to avoid recursion depth issues
    on deeply nested keys.

    The trailing-** rule mirrors real-world intent: ``"project.**"``
    means "anything under project", not "project itself".  Meanwhile
    ``"a.**.z"`` needs ** to match zero segments so ``"a.z"`` works.
    """
    p_len = len(pattern_parts)
    k_len = len(key_segments)

    # dp[pi][ki] = True if pattern_parts[:pi] matches key_segments[:ki]
    dp: list[list[bool]] = [[False] * (k_len + 1) for _ in range(p_len + 1)]
    dp[0][0] = True

    # Leading/middle "**" parts can match zero segments
    for pi in range(1, p_len + 1):
        if pattern_parts[pi - 1] == "**":
            dp[pi][0] = dp[pi - 1][0]

    for pi in range(1, p_len + 1):
        part = pattern_parts[pi - 1]
        is_trailing_doublestar = part == "**" and pi == p_len
        for ki in range(1, k_len + 1):
            if part == "**":
                # ** can match zero segments (dp[pi-1][ki])
                # or consume one more segment (dp[pi][ki-1])
                dp[pi][ki] = dp[pi - 1][ki] or dp[pi][ki - 1]
            elif part == "*":
                # * matches exactly one segment
                dp[pi][ki] = dp[pi - 1][ki - 1]
            else:
                # Literal match
                dp[pi][ki] = dp[pi - 1][ki - 1] and (part == key_segments[ki - 1])

    # Trailing ** must consume at least one segment.
    # If the last part is ** and it matched by consuming zero key segments
    # (i.e. the match came purely from dp[p_len-1][k_len]), reject it.
    if p_len > 0 and pattern_parts[-1] == "**":
        # The overall match is dp[p_len][k_len].
        # Check if ** consumed at least one segment: dp[p_len][k_len]
        # must NOT be solely due to dp[p_len-1][k_len] (zero consumption).
        if dp[p_len][k_len] and dp[p_len - 1][k_len]:
            # ** consumed zero — only valid if it ALSO consumed some.
            # Re-check: is there a path where ** consumed >= 1?
            # dp[p_len][k_len] could be True from dp[pi][ki-1] chain.
            # If dp[p_len-1][k_len] is True, that means the pattern
            # without the trailing ** already matched all k segments.
            # We need ** to have consumed at least one more.
            # So: if dp[p_len-1][k_len] is True and k_len has no
            # additional segments beyond that match, reject.
            #
            # Simplified: if removing ** still matches, then ** consumed
            # zero segments. We only allow this if ** also matches with
            # more (but there aren't more segments). So: reject.
            return False

    return dp[p_len][k_len]


def _matches_pattern(pattern: str, key: str) -> bool:
    """Check if a dot-separated key matches a dot-segment pattern."""
    pattern_parts = pattern.split(".")
    key_segments = key.split(".")
    return _match_segments(pattern_parts, key_segments)


def _matches_any(patterns: list[str], key: str) -> bool:
    """Return True if the key matches at least one of the patterns."""
    return any(_matches_pattern(p, key) for p in patterns)


# ---------------------------------------------------------------------------
# ScopeProjection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeProjection:
    """Controls which keys are visible (read) or writable (write) in a scope.

    Uses glob pattern matching on dot-separated key segments.

    Evaluation rules (INV-2):
        1. If allow_patterns is empty, nothing is allowed (default-deny).
        2. If deny_patterns is empty, all allowed patterns pass.
        3. A key is accessible iff it matches >= 1 allow AND 0 deny patterns.
        4. Deny takes absolute precedence over allow.

    Attributes:
        allow_patterns: Glob patterns for permitted keys.
        deny_patterns: Glob patterns for denied keys (precedence over allow).
    """

    allow_patterns: list[str]
    deny_patterns: list[str]

    def permits(self, key: str) -> bool:
        """Return True if this projection permits access to the given key.

        Implements: matches_any(allow, key) AND NOT matches_any(deny, key).
        """
        if not self.allow_patterns:
            return False
        if not _matches_any(self.allow_patterns, key):
            return False
        if self.deny_patterns and _matches_any(self.deny_patterns, key):
            return False
        return True

    def is_subset_of(self, other: ScopeProjection) -> bool:
        """Return True if every key this projection permits is also permitted by other.

        Uses a generative approach: generate representative test keys from
        self's allow patterns AND from other's deny patterns, then check
        that self.permits(key) implies other.permits(key) for all test keys.

        For exact correctness this would require symbolic analysis. We use a
        pragmatic enumeration strategy that covers common cases including
        deny-pattern interactions.
        """
        if not self.allow_patterns:
            # Empty projection permits nothing -- trivially a subset of anything.
            return True

        # Collect test keys from self's allow patterns
        test_keys: set[str] = set()
        for pattern in self.allow_patterns:
            test_keys.update(_generate_representative_keys(pattern))

        # Also collect test keys from other's deny patterns -- these are the
        # specific keys that other blocks. If self permits any of them, self
        # is NOT a subset of other.
        for pattern in other.deny_patterns:
            test_keys.update(_generate_representative_keys(pattern))

        # Also collect test keys from other's allow patterns for coverage
        for pattern in other.allow_patterns:
            test_keys.update(_generate_representative_keys(pattern))

        # Also collect test keys from self's deny patterns
        for pattern in self.deny_patterns:
            test_keys.update(_generate_representative_keys(pattern))

        for key in test_keys:
            if self.permits(key) and not other.permits(key):
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_patterns": list(self.allow_patterns),
            "deny_patterns": list(self.deny_patterns),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ScopeProjection:
        return cls(
            allow_patterns=list(d["allow_patterns"]),
            deny_patterns=list(d["deny_patterns"]),
        )


# ---------------------------------------------------------------------------
# Representative key generation for subset checking
# ---------------------------------------------------------------------------


def _generate_representative_keys(pattern: str) -> list[str]:
    """Generate representative keys that a pattern would match.

    This is used for is_subset_of() — we need to test whether another
    projection also permits these keys. We generate keys at various
    depths to cover single-star and double-star patterns.
    """
    parts = pattern.split(".")
    keys: list[str] = []

    # Check if pattern contains any glob chars
    has_glob = any(p in ("*", "**") for p in parts)

    if not has_glob:
        # Literal pattern — only matches itself
        keys.append(pattern)
        return keys

    # Generate keys by expanding globs
    _expand_pattern(parts, 0, [], keys, depth_limit=4)
    return keys


def _expand_pattern(
    parts: list[str],
    idx: int,
    current: list[str],
    results: list[str],
    depth_limit: int,
) -> None:
    """Recursively expand a pattern into representative keys."""
    if idx == len(parts):
        if current:
            results.append(".".join(current))
        return

    part = parts[idx]

    if part == "*":
        # Generate a few representative single-segment values
        for seg in ("_x_", "_y_", "_z_"):
            _expand_pattern(parts, idx + 1, current + [seg], results, depth_limit)
    elif part == "**":
        # ** matches zero or more segments
        # Zero segments — skip **
        _expand_pattern(parts, idx + 1, current, results, depth_limit)
        # One segment
        for seg in ("_x_", "_y_"):
            _expand_pattern(parts, idx + 1, current + [seg], results, depth_limit)
        # Two segments (for coverage of deeper nesting)
        if depth_limit > 0:
            _expand_pattern(
                parts, idx + 1, current + ["_x_", "_y_"], results, depth_limit - 1
            )
    else:
        # Literal segment
        _expand_pattern(parts, idx + 1, current + [part], results, depth_limit)
