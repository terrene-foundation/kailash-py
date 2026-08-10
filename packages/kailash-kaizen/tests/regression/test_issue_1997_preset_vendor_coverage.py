# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: credential coverage MUST NOT depend on which preset is called.

#1997. The issue was filed as "Mistral redaction is probabilistic per key". It
is measured here as something wider and worse: coverage is **PRESET-dependent**,
and the preset with the leaks is the one with the call sites.

MEASURED BEFORE THE FIX (each key embedded in an error string, then checked for
verbatim survival — the matrix that motivated this file)::

    vendor        len  conservative      remote
    openai        43   REDACTED          REDACTED
    anthropic     49   REDACTED          REDACTED
    google        37   REDACTED          REDACTED
    perplexity    37   REDACTED          REDACTED
    huggingface   37   REDACTED          REDACTED
    fireworks     27   REDACTED          REDACTED
    groq          56   LEAKS             REDACTED
    mistral       32   LEAKS             LEAKS
    cohere        40   LEAKS             REDACTED
    together      64   LEAKS             REDACTED
    openrouter    73   REDACTED          REDACTED
    deepseek      35   REDACTED          REDACTED

``scrub_local_error`` IS the CONSERVATIVE preset (its own docstring: "the named
CONSERVATIVE preset"; it turns the two SHAPE-ONLY rules OFF) and it is the one
used at ~180 call sites in ``kaizen-agents``. Every "REDACTED" in the remote
column for groq / cohere / together was INCIDENTAL — produced by
``_AWS_SECRET_CONTIGUOUS_RUN`` / ``_GENERIC_HEX_TOKEN``, both of which live in
``_OPAQUE_SHAPE_PATTERNS`` and are therefore OFF on the conservative preset.

THE FALSIFYING RESULT, STATED (``rules/instrument-discipline.md`` MUST-1): had
coverage been the per-vendor binary the issue assumed, both columns would agree
for every vendor. They did not — groq, cohere and together flip ACROSS presets,
and that disagreement is the finding. The same probe prints REDACTED/REDACTED
for the six covered vendors, which is what shows it discriminates rather than
reporting LEAKS indiscriminately.

WHY THIS FILE IS PARAMETERIZED OVER (preset x vendor). A suite that exercises
one preset reports success while the other leaks. That is precisely how the
defect survived: no existing test called ``scrub_local_error`` with a vendor
key at all. The product of both axes is the shape that makes preset-dependence
impossible to reintroduce silently.

BOTH POLARITIES ARE PINNED. Positive: every first-class provider shape is
redacted on every preset. Negative: git SHAs, digests, hyphen-free UUIDs,
digit-free CamelCase identifiers and the ``cache_key`` / ``primary_key`` /
``sort_key`` / ``tokenizer`` / ``monkey`` shapes are untouched on every preset.
A future widening that over-masks therefore fails as loudly as one that
under-masks — the conservative preset's whole value is the diagnostic text an
agent reads to decide its retry.

SCOPE CORRECTION RECORDED HERE, NOT ONLY IN THE PR: **xAI is deliberately NOT
covered.** It is not a provider in this codebase — no ``_FROM_ENV_PROVIDERS``
entry and no mention in the kaizen source — so a rule for it would be dead code
protecting no surface. ``test_vendor_vocabulary_tracks_the_provider_registry``
below is the tripwire that will demand coverage the day it becomes one.

KEY SHAPES ARE CITED FROM PUBLISHED VENDOR FORMATS, NOT INFERRED FROM THE REPO.
``gsk_`` has ZERO in-repo literals (verified by grep), so it is pinned on Groq's
published API-key format (``gsk_`` + 52 alphanumerics) rather than on anything
observed here. Mistral (32 alphanumerics), Cohere (40 alphanumerics) and
Together (64 hex) are likewise published shapes. Every VALUE below is synthetic
and assembled at runtime from fragments: a credential-shaped literal in a
committed blob trips GitHub push protection and blocks the push of the whole
branch (the reason the sibling #1974d file does the same).
"""

from __future__ import annotations

import gc
import time
from typing import Callable, Final, List, Tuple

import pytest

from kaizen.llm.errors import ProviderError
from kaizen.llm.presets import _FROM_ENV_PROVIDERS
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.utils.credential_scrub import (
    _MIXED_ALPHABET_OPAQUE_KEY,
    _OPAQUE_SHAPE_PATTERNS,
    _PROVIDER_NAME_ALTERNATION,
    scrub_local_error,
    scrub_remote_error,
)

pytestmark = pytest.mark.regression

# ---------------------------------------------------------------------------
# The two presets under test, by name.
# ---------------------------------------------------------------------------
PRESETS: Final[dict] = {
    "conservative": scrub_local_error,  # scrub_local_error — ~180 call sites
    "remote": scrub_remote_error,
}

# ---------------------------------------------------------------------------
# Synthetic vendor key shapes, assembled at runtime (see module docstring).
# ---------------------------------------------------------------------------
_ALNUM32: Final[str] = "AbCdEfGhIjKlMnOpQrStUvWxYz012345"
_ALNUM40: Final[str] = "AbCdEfGhIjKlMnOpQrStUvWxYz01234567890123"
_HEX64: Final[str] = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" * 2

VENDOR_KEYS: Final[List[Tuple[str, str]]] = [
    ("openai", "sk-" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd"),
    ("anthropic", "sk-" + "ant-api03-" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"),
    ("google", "AIza" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456"),
    ("perplexity", "pplx-" + "AbCdEfGhIjKlMnOpQrStUvWxYz012345"),
    ("huggingface", "hf_" + "AbCdEfGhIjKlMnOpQrStUvWxYz01234567"),
    ("fireworks", "fw_" + "AbCdEfGhIjKlMnOpQrStUvWx"),
    # Groq: published format is ``gsk_`` + 52 alphanumerics.
    ("groq", "gsk_" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCdEfGhIjKlMnOp"),
    # Mistral / Cohere: NO vendor prefix at all — the shapes #1997 is about.
    ("mistral", _ALNUM32),
    ("cohere", _ALNUM40),
    ("openrouter", "sk-" + "or-v1-" + _HEX64),
    ("deepseek", "sk-" + _ALNUM32),
]

#: Together AI issues a 64-character HEX key, which is byte-for-byte the shape
#: of a SHA-256 digest. It is split out of ``VENDOR_KEYS`` because the
#: conservative row is a KNOWN, DOCUMENTED residual rather than a covered case —
#: see ``test_together_bare_key_is_a_documented_residual`` for why no shape rule
#: can claim it there without blanking every digest in every local error.
_TOGETHER_KEY: Final[str] = _HEX64


def _probe(preset_name: str, key: str) -> str:
    """Embed ``key`` in a realistic error string and return the scrubbed text."""
    return PRESETS[preset_name](RuntimeError(f"401 unauthorized: invalid api key {key}"))


# ---------------------------------------------------------------------------
# POSITIVE POLARITY — every supported vendor, on every preset.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("preset_name", sorted(PRESETS))
@pytest.mark.parametrize("vendor,key", VENDOR_KEYS, ids=[v for v, _ in VENDOR_KEYS])
def test_vendor_key_is_redacted_on_every_preset(
    preset_name: str, vendor: str, key: str
) -> None:
    """A first-class provider's key MUST NOT survive EITHER preset.

    The vendor axis alone was already tested (#1974d). The PRESET axis is what
    this file adds, and it is the axis the defect lived on.
    """
    out = _probe(preset_name, key)

    assert key not in out, (
        f"{vendor} key survived the {preset_name} preset verbatim: {out!r}. "
        "Coverage is preset-dependent again — see #1997."
    )
    assert "[REDACTED]" in out, (
        f"{vendor} key vanished from the {preset_name} preset output without a "
        f"placeholder appearing, which means something other than a redaction "
        f"changed the string: {out!r}"
    )


@pytest.mark.parametrize("preset_name", sorted(PRESETS))
def test_prefixless_key_is_redacted_at_both_module_surfaces(preset_name: str) -> None:
    """#1997 AC: the Mistral shape is claimed at BOTH consuming surfaces.

    ``sanitize_provider_error`` (the node surface) and ``ProviderError``
    (the ``LlmClient`` wire surface) both route through ``scrub_credentials``,
    so this is a parity assertion over the shared implementation rather than
    over two lists agreeing.
    """
    assert _ALNUM32 not in _probe(preset_name, _ALNUM32)

    node_out = sanitize_provider_error(RuntimeError(f"401 {_ALNUM32}"), "test")
    assert _ALNUM32 not in node_out, f"node surface leaked: {node_out!r}"

    wire = ProviderError(401, f'{{"error":"invalid api key {_ALNUM32}"}}')
    assert _ALNUM32 not in wire.body_snippet, f"wire surface leaked: {wire!r}"


# ---------------------------------------------------------------------------
# NEGATIVE POLARITY — the conservative preset's diagnostic payload survives.
# ---------------------------------------------------------------------------
#: Credential-free strings that MUST pass through BOTH presets byte-identically.
#:
#: The five key-name entries are the ones a segment-wise widening of
#: ``_CREDENTIAL_KEY_NAMES`` would destroy. A bare ``key`` stem would claim
#: ``cache_key`` / ``primary_key`` / ``sort_key``; a bare ``token`` stem would
#: claim ``tokenizer``; an unanchored compound would claim ``monkey``. Every
#: value here is >= 6 characters and carries a digit or punctuation, so it WOULD
#: satisfy the value half of the ``key=value`` rules — the ONLY thing keeping
#: them out of the match is the key-name vocabulary, which is exactly the
#: property under test. (A short value would pass this test whether or not the
#: vocabulary widened: it would fail the 6-char floor instead, and the check
#: would report the same verdict either way.)
BENIGN: Final[List] = [
    pytest.param("checkpoint at f0e1d2c3b4a5968778695a4b3c2d1e0f0a1b2c3d", id="git-sha"),
    pytest.param("checksum mismatch: 9e107d9d372bb6826bd81d3542a419d6", id="md5"),
    pytest.param("trace 6f1c2a3b4d5e6f708192a3b4c5d6e7f8 not found", id="uuid-nohyphen"),
    pytest.param(
        "unknown node type: AbstractSingletonProxyFactoryBeanBuilderImpl",
        id="camelcase-identifier",
    ),
    pytest.param("cache_key=orders:2026-08 evicted", id="cache_key"),
    pytest.param("primary_key=order_id_v2 is not unique", id="primary_key"),
    pytest.param("sort_key=created_at_desc unsupported", id="sort_key"),
    pytest.param("tokenizer=BertFastV2 could not be loaded", id="tokenizer"),
    pytest.param("monkey=patched_module already applied", id="monkey"),
    pytest.param("run_id 6f1c2a3b-4d5e-6f70-8192-a3b4c5d6e7f8 missing", id="uuid"),
    pytest.param("revision 03795208d not found", id="short-sha"),
]


@pytest.mark.parametrize("preset_name", sorted(PRESETS))
@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_is_untouched_on_every_preset(preset_name: str, text: str) -> None:
    """Over-masking fails as loudly as under-masking.

    ``primary_key`` / ``sort_key`` / ``cache_key`` are legitimate parameter
    traces; blanking them destroys the diagnostic on the very surface the
    conservative preset exists to preserve.
    """
    assert PRESETS[preset_name](text) == text, (
        f"the {preset_name} preset rewrote credential-free text. A key-name or "
        "shape rule has widened into ordinary error prose."
    )


# ---------------------------------------------------------------------------
# The vendor-name key vocabulary — positive half.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("preset_name", sorted(PRESETS))
@pytest.mark.parametrize(
    "text,secret",
    [
        ("config: MISTRAL_KEY=Zx9-tuvw12 rejected", "Zx9-tuvw12"),
        ("config: GROQ_TOKEN=Zx9-tuvw12 rejected", "Zx9-tuvw12"),
        ("config: cohere_api_key: Zx9-tuvw12 rejected", "Zx9-tuvw12"),
        ("config: togetherApiKey=Zx9-tuvw12 rejected", "Zx9-tuvw12"),
    ],
    ids=["mistral_key", "groq_token", "cohere_api_key", "together_camel"],
)
def test_vendor_named_key_assignment_is_masked(
    preset_name: str, text: str, secret: str
) -> None:
    """``<vendor>_KEY=`` / ``<vendor>_TOKEN=`` announce a secret.

    ``api[-_]?key`` already covered ``MISTRAL_API_KEY``; nothing covered the
    ``<vendor>_KEY`` spelling, because no alternative matches a bare ``key``
    stem — and deliberately so, per the negative corpus above.
    """
    out = PRESETS[preset_name](text)
    assert secret not in out, f"{preset_name}: vendor-named assignment leaked: {out!r}"


def test_vendor_vocabulary_tracks_the_provider_registry() -> None:
    """Adding a provider to ``_FROM_ENV_PROVIDERS`` MUST fail here until scrubbed.

    This is the "or a loud failure" half of the requirement. Without it, the
    next provider added to the registry silently inherits zero key-name
    coverage, which is exactly how groq / mistral / cohere / together got here.
    """
    registry = {name for name, _, _ in _FROM_ENV_PROVIDERS}
    vocabulary = set(_PROVIDER_NAME_ALTERNATION.split("|"))

    missing = sorted(registry - vocabulary)
    assert not missing, (
        f"providers in _FROM_ENV_PROVIDERS with no entry in the scrubber's "
        f"vendor vocabulary: {missing}. Add them to _PROVIDER_NAME_ALTERNATION "
        f"in kaizen/utils/credential_scrub.py and extend VENDOR_KEYS here."
    )


# ---------------------------------------------------------------------------
# Classification + documented residuals.
# ---------------------------------------------------------------------------
def test_mixed_alphabet_rule_is_not_shape_only_gated() -> None:
    """The new rule MUST fire on the conservative preset.

    Membership in ``_OPAQUE_SHAPE_PATTERNS`` is what switches a rule OFF under
    ``redact_opaque_tokens=False``. A future edit that "tidies" this rule into
    that set silently restores the entire #1997 defect, and every positive test
    above would still pass on the remote preset while the conservative one
    leaks again — so the classification is pinned directly.
    """
    assert _MIXED_ALPHABET_OPAQUE_KEY not in _OPAQUE_SHAPE_PATTERNS


@pytest.mark.parametrize("preset_name", sorted(PRESETS))
@pytest.mark.xfail(
    strict=True,
    reason=(
        "#1997 DOCUMENTED RESIDUAL — a Together AI key is 64 hex characters, "
        "which is byte-for-byte a SHA-256 digest. No shape rule can claim it on "
        "the conservative preset without blanking every digest in every local "
        "error, which is the diagnostic payload that preset exists to preserve. "
        "Covered when the key is ANNOUNCED (TOGETHER_API_KEY=...); the residual "
        "is the BARE form. xfail-strict so it self-clears as XPASS the moment a "
        "rule does claim it."
    ),
)
def test_together_bare_key_is_a_documented_residual(preset_name: str) -> None:
    assert _TOGETHER_KEY not in _probe(preset_name, _TOGETHER_KEY)


def test_together_announced_key_is_masked_on_every_preset() -> None:
    """The residual above is BARE-ONLY — the announced form IS covered.

    Pinned so the residual's boundary is a measured fact rather than a claim in
    a docstring, and so a regression in the announced path cannot hide behind
    the xfail above.
    """
    for preset_name in PRESETS:
        out = PRESETS[preset_name](f"config: TOGETHER_API_KEY={_TOGETHER_KEY}")
        assert _TOGETHER_KEY not in out, f"{preset_name}: {out!r}"


@pytest.mark.parametrize("preset_name", sorted(PRESETS))
@pytest.mark.xfail(
    strict=True,
    reason=(
        "#1997 DOCUMENTED RESIDUAL — a prefix-less key drawn with NO DIGIT is "
        "indistinguishable from a long CamelCase identifier "
        "(AbstractSingletonProxyFactoryBeanBuilderImpl), which the negative "
        "corpus above requires to survive. Measured aperture: a uniformly "
        "random 32-char alphanumeric key omits digits with probability "
        "(52/62)^32 ~ 0.36%, and a 40-char one with ~0.09%. Deterministic per "
        "shape, not per key: the residual is the digit-free draw, not 'this "
        "vendor is probabilistic'. xfail-strict so it self-clears on XPASS."
    ),
)
def test_digit_free_prefixless_key_is_a_documented_residual(preset_name: str) -> None:
    digit_free = "AbCdEfGhIjKlMnOpQrStUvWxYzAbCdEf"
    assert len(digit_free) == 32
    assert digit_free not in _probe(preset_name, digit_free)


# ---------------------------------------------------------------------------
# REGEX SAFETY CONTRACT — the module docstring requires a self-normalising
# linearity test for every new pattern, and requires it to REACH the quantifier
# it claims to measure (`rules/instrument-discipline.md` MUST-1).
# ---------------------------------------------------------------------------
def _linearity_ratio(small: str, large: str, reps: int = 5) -> float:
    """CPU-time cost of the 8x payload relative to the baseline.

    Same shape and the same rationale as ``_linearity_ratio`` in
    ``test_issue_1974_sanitizer_pattern_gaps.py``: ``process_time`` rather than
    ``perf_counter`` (the property is WORK, not wall clock, and this repo runs
    several suites at once), interleaved samples, GC disabled, best-of-N, and no
    absolute threshold anywhere.
    """
    small_best = float("inf")
    large_best = float("inf")
    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(reps):
            start = time.process_time()
            _MIXED_ALPHABET_OPAQUE_KEY.sub("x", small)
            small_best = min(small_best, time.process_time() - start)

            start = time.process_time()
            _MIXED_ALPHABET_OPAQUE_KEY.sub("x", large)
            large_best = min(large_best, time.process_time() - start)
    finally:
        if gc_was_enabled:
            gc.enable()
    return large_best / max(small_best, 1e-9)


def test_mixed_alphabet_rule_reaches_its_own_quantifier() -> None:
    """ENTRY assertion for the linearity probe below.

    A timing probe whose payload cannot enter the construct under test returns
    the same verdict whether that construct is linear or quadratic — the exact
    non-discriminating instrument ``credential_scrub``'s own docstring records
    (`_COMMA_BEARING_RUN`). So: prove the payload MATCHES and that the match
    SPANS the run, and prove the FAILING path is reached too (a quantifier that
    always succeeds never backtracks and is measured by nothing).
    """
    hit = _MIXED_ALPHABET_OPAQUE_KEY.search(f"error {_ALNUM32} rejected")
    assert hit is not None, "positive payload does not enter the pattern at all"
    assert hit.group(0) == _ALNUM32, hit.group(0)

    # FAILING path: the run is long enough but is single-case, so every
    # class lookahead is exercised and one of them fails at each start offset.
    assert _MIXED_ALPHABET_OPAQUE_KEY.search("f0e1d2c3b4a5968778695a4b3c2d1e0f") is None


def test_mixed_alphabet_rule_scan_is_linear_not_quadratic() -> None:
    """8x input MUST NOT cost >>8x.

    The payload deliberately has NO character that satisfies the third class
    lookahead, so every start offset drives the bounded lookaheads to failure —
    the worst case for this pattern, and the one an attacker-influenced error
    string can produce.
    """
    unit = "aBcDeFgHiJkLmNoPqRsTuVwXyZaBcDeF "
    small = unit * 256
    large = unit * 2048

    ratio = _linearity_ratio(small, large)
    assert ratio < 25, (
        f"8x input scaled {ratio:.1f}x — the class lookaheads on "
        "_MIXED_ALPHABET_OPAQUE_KEY are backtracking. Their {0,256} bounds are "
        "what keep the per-start-offset cost constant; do NOT unbound them."
    )


def test_probe_helpers_are_callable() -> None:
    """Guards against a refactor leaving ``PRESETS`` holding non-callables."""
    for name, fn in PRESETS.items():
        assert isinstance(fn, Callable), name  # type: ignore[arg-type]
