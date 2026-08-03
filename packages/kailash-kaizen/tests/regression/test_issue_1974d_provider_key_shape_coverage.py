"""Regression: every first-class provider's key shape must be scrubbed.

#1974d — surfaced by the #1720 forest redteam (R1 adversarial security pass).

`llm/errors.py` states the threat model as vendor-AGNOSTIC: all feed sites hand
the constructor the full unredacted provider response body, so whatever the
provider echoed back — including a submitted Authorization header — arrives
verbatim. The pattern table, however, named seven vendors. Three first-class
providers in ``llm/presets.py::_FROM_ENV_PROVIDERS`` had key shapes that no
rule claimed:

    hf_  (HuggingFace)  — "_" blocks \\b so the hex rule cannot fire; body < 40
    fw_  (Fireworks)    — same mechanism, body well under 40
    Mistral             — no vendor prefix at all; 32 alnum, under the 40 run

hf_ and fw_ are fixed. Mistral is tracked as #1997 and pinned below with
xfail(strict=True) rather than skip, so it fails as XPASS the moment the gap
closes and forces the marker's removal in the same change
(`rules/testing.md` § "Deferred-Implementation Conformance Vectors Use
xfail-Strict, Not Skip").

NOTE ON THE TEST VECTORS: assembled at runtime from fragments rather than
written as literals. The shapes are synthetic, but a literal credential-shaped
string in a committed blob trips GitHub push protection and blocks the push.
"""

from __future__ import annotations

import pytest

from kaizen.utils.credential_scrub import scrub_credentials

# Assembled at runtime — see module docstring.
_HF_KEY = "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz01234567"
_FW_KEY = "fw_" + "AbCdEfGhIjKlMnOpQrStUvWx"
_MISTRAL_KEY = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
_MISTRAL_HEX_KEY = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


@pytest.mark.regression
@pytest.mark.parametrize(
    "shape,key",
    [("huggingface", _HF_KEY), ("fireworks", _FW_KEY)],
)
def test_provider_key_shape_is_scrubbed(shape, key):
    """A first-class provider's key must not survive the scrubber."""
    out = scrub_credentials(f"401 unauthorized: invalid api key {key}")

    assert key not in out, f"{shape} key shape passed through unredacted (got: {out!r})"
    assert "[REDACTED]" in out


@pytest.mark.regression
def test_mistral_hex_shape_is_scrubbed_incidentally():
    """An all-hex Mistral key IS claimed — by the generic hex rule.

    Pins the asymmetry that makes #1997 worth fixing: coverage exists for one
    alphabet and not the other, so a hex-shaped fixture implies protection the
    next key does not receive.
    """
    out = scrub_credentials(f"401 unauthorized: {_MISTRAL_HEX_KEY}")
    assert _MISTRAL_HEX_KEY not in out


@pytest.mark.regression
@pytest.mark.xfail(
    strict=True,
    reason=(
        "#1997 — Mistral has no vendor prefix and its 32-char mixed-alphanumeric "
        "body is under the 40-char contiguous-run threshold, so no rule claims it. "
        "Fixing it means either lowering that threshold (worsens over-redaction "
        "on compact-JSON bodies) or a context-anchored rule (misses bare secrets). "
        "Design decision, surfaced not self-decided. Remove this marker with the fix."
    ),
)
def test_mistral_alnum_shape_is_scrubbed():
    """KNOWN GAP (#1997): a mixed-alphanumeric Mistral key is not claimed."""
    out = scrub_credentials(f"401 unauthorized: invalid api key {_MISTRAL_KEY}")
    assert _MISTRAL_KEY not in out


@pytest.mark.regression
@pytest.mark.parametrize(
    "benign",
    [
        "connection refused to api.example.com after 30s",
        "model gpt-4o-mini not found for org acct_12345",
        "rate limit exceeded: retry after 60 seconds",
        "invalid request: field 'temperature' must be <= 2.0",
    ],
)
def test_benign_error_prose_is_not_over_redacted(benign):
    """No-false-positive half.

    Over-redaction that destroys the diagnostic value of an error body is its
    own defect — the surface exists to be read.
    """
    assert scrub_credentials(benign) == benign
