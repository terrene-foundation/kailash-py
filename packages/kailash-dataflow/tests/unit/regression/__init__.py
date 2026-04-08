"""Unit regression tests — deterministic bug reproductions.

Regression tests in this directory use Tier 1 semantics (mocks allowed)
because the bugs they reproduce live on internal error paths that cannot
be exercised with real infrastructure alone.
"""
