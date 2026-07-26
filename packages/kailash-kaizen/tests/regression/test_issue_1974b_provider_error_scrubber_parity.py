# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression suite: `ProviderError.body_snippet` scrubber parity (S1).

Issues #1970 + #1974 hardened
``kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`` and applied it at
~120 sites. A redteam lens then found a SECOND, INDEPENDENT credential scrubber
guarding ``kaizen.llm.errors.ProviderError.body_snippet`` that had learned NONE
of it, despite a docstring claiming it "mirrors" the first.

The drift ran in BOTH directions and both directions leaked:

* MISSING HERE (redacted by the node surface, leaked by the wire surface):
  Slack ``xox*``, GitHub ``ghp_``/``github_pat_``, Stripe ``sk_live_``,
  Perplexity ``pplx-``, uppercase hex, AWS 40-char secret keys, and ALL THREE
  URL-embedded-DSN rules (postgres / redis / any RFC-3986 scheme).
* MISSING THERE (redacted by the wire surface, leaked by the node surface):
  AWS STS temporary credentials ``ASIA*`` and Azure SAS ``sig=`` tokens.

This matters because all three feed sites hand ``ProviderError`` the FULL,
unredacted provider response body — ``kaizen/llm/client.py`` (embeddings +
completions) and ``kaizen/llm/http_client.py`` (streaming) — and
``body_snippet`` reaches ``str(err)``, log lines, and tracing spans.

The fix routes both surfaces through ONE implementation
(``kaizen.utils.credential_scrub.scrub_credentials``) per ``rules/security.md``
§ Credential Decode Helpers. These tests are the teeth: they fail loudly with
the literal credential visible in the assertion output if the delegation is
ever unwound or a shape regresses.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import httpx
import pytest
import respx

import kaizen.llm.errors as llm_errors
import kaizen.nodes.ai.error_sanitizer as node_sanitizer
from kaizen.llm import LlmClient
from kaizen.llm.errors import ProviderError
from kaizen.llm.http_client import LlmHttpClient, SafeDnsResolver
from kaizen.llm.presets import openai_preset
from kaizen.utils.credential_scrub import scrub_credentials

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# The credential corpus. Each entry is (shape_id, literal_secret, must_vanish).
#
# `must_vanish` is the substring whose survival constitutes the leak. For DSNs
# it is the PASSWORD alone — the host/port legitimately survive and asserting
# on the whole DSN would pass for the wrong reason.
# ---------------------------------------------------------------------------
_SHAPES: list[tuple[str, str, str]] = [
    # --- the 8 shapes the wire surface leaked before this fix ---
    (
        "slack",
        "xoxb-2468013579-2468013579246-AbCdEfGhIjKlMnOpQrStUvWx",
        "AbCdEfGhIjKlMnOpQrStUvWx",
    ),
    (
        "github_ghp",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
    ),
    (
        "github_pat",
        "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz0123456789",
    ),
    (
        "stripe",
        "sk_live_AbCdEfGhIjKlMnOpQrStUvWx",
        "sk_live_AbCdEfGhIjKlMnOpQrStUvWx",
    ),
    (
        "postgres_dsn",
        "postgresql://dbuser:Sup3rS3cr3tPassw0rd@db.internal:5432/prod",
        "Sup3rS3cr3tPassw0rd",
    ),
    (
        "redis_dsn_empty_user",
        "redis://:R3d1sS3cr3tPassw0rd@cache.internal:6379/0",
        "R3d1sS3cr3tPassw0rd",
    ),
    (
        "hex_uppercase",
        "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
        "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4",
    ),
    (
        "aws_secret_40",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    ),
    (
        "perplexity",
        "pplx-abcdefghijklmnopqrstuvwxyz0123456789",
        "pplx-abcdefghijklmnopqrstuvwxyz0123456789",
    ),
    # --- the 2 shapes the NODE surface leaked before this fix (reverse delta) ---
    ("aws_sts_temp", "ASIAIOSFODNN7EXAMPLE", "ASIAIOSFODNN7EXAMPLE"),
    (
        "azure_sas_sig",
        "https://acct.blob.core.windows.net/c/b?sig=abc123def456ghi789jkl012mno345",
        "sig=abc123def456ghi789jkl012mno345",
    ),
    # --- shapes both already covered; pinned so consolidation cannot drop them ---
    ("openai", "sk-hunter2xxxxxxxxxxxxxxxxxxxx", "sk-hunter2xxxxxxxxxxxxxxxxxxxx"),
    (
        "anthropic",
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz",
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz",
    ),
    (
        "google_aiza",
        "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r",
        "AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r",
    ),
    ("aws_akia", "AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
]

_SHAPE_IDS = [s[0] for s in _SHAPES]


def _provider_body(secret: str) -> str:
    """A realistic 4xx body echoing the submitted credential."""
    return '{"error":{"code":"invalid_api_key","message":"Incorrect key: %s"}}' % secret


# ---------------------------------------------------------------------------
# 1. Every shape, through ProviderError.body_snippet
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("shape", "secret", "must_vanish"), _SHAPES, ids=_SHAPE_IDS)
def test_provider_error_body_snippet_redacts_shape(
    shape: str, secret: str, must_vanish: str
) -> None:
    """The credential MUST NOT survive in body_snippet, str(err), or args.

    On failure the assertion message carries the literal surviving credential,
    which is the point: the teeth are visible.
    """
    err = ProviderError(status=401, body_snippet=_provider_body(secret))

    assert must_vanish not in err.body_snippet, (
        f"{shape}: credential SURVIVED ProviderError.body_snippet -> "
        f"{err.body_snippet!r}"
    )
    assert must_vanish not in str(
        err
    ), f"{shape}: credential SURVIVED str(ProviderError) -> {str(err)!r}"
    for arg in err.args:
        assert must_vanish not in str(
            arg
        ), f"{shape}: credential SURVIVED ProviderError.args -> {arg!r}"
    assert (
        "[REDACTED-CRED]" in err.body_snippet
    ), f"{shape}: nothing was redacted; body_snippet -> {err.body_snippet!r}"


@pytest.mark.parametrize(("shape", "secret", "must_vanish"), _SHAPES, ids=_SHAPE_IDS)
def test_both_surfaces_redact_the_same_shape(
    shape: str, secret: str, must_vanish: str
) -> None:
    """Enforcement-surface parity: the wire surface and the node surface agree.

    ``rules/security.md`` § Enforcement-Surface Parity — a fail-closed dimension
    added at one surface MUST land at EVERY independent surface. This is the
    test that would have caught the original defect in either direction.
    """
    body = _provider_body(secret)
    wire = ProviderError(status=401, body_snippet=body).body_snippet
    node = node_sanitizer.sanitize_provider_error(Exception(body), "testprovider")

    assert must_vanish not in wire, f"{shape}: leaked at the LlmClient wire surface"
    assert (
        must_vanish not in node
    ), f"{shape}: leaked at the sanitize_provider_error node surface -> {node!r}"


@pytest.mark.parametrize(("shape", "secret", "must_vanish"), _SHAPES, ids=_SHAPE_IDS)
def test_scrub_runs_before_truncation_for_every_shape(
    shape: str, secret: str, must_vanish: str
) -> None:
    """A credential straddling the 256-char truncation boundary still vanishes.

    Scrubbing AFTER truncation would leave a partial match unredacted, so the
    ordering is load-bearing. Padding places the secret across the boundary.
    """
    pad = "provider rejected the request. " * 8  # ~248 chars, credential-free
    err = ProviderError(status=401, body_snippet=pad + secret + " trailing")
    assert must_vanish not in err.body_snippet, (
        f"{shape}: credential straddling the truncation boundary SURVIVED -> "
        f"{err.body_snippet!r}"
    )


# ---------------------------------------------------------------------------
# 2. The three feed sites — behavioral, through the real send path
# ---------------------------------------------------------------------------
#
# These are what stop a future change to the feed sites (pre-formatting the
# body into a message, bypassing ProviderError, adding a fourth site that
# formats its own string) from silently reintroducing the leak.

_FEED_SECRET = "xoxb-2468013579-2468013579246-AbCdEfGhIjKlMnOpQrStUvWx"
_FEED_MUST_VANISH = "AbCdEfGhIjKlMnOpQrStUvWx"


class _AllowAllResolver(SafeDnsResolver):
    """SafeDnsResolver that skips the real DNS lookup (test-only)."""

    __slots__ = ()

    def check_host(self, host: str) -> None:  # noqa: D401 - test stub resolver
        return None


def _client_and_http():
    dep = openai_preset("sk-x", "gpt-4o")
    http = LlmHttpClient(deployment_preset=dep.wire.name, resolver=_AllowAllResolver())
    return LlmClient.from_deployment(dep), http


def _assert_no_leak(err: ProviderError, site: str) -> None:
    assert (
        _FEED_MUST_VANISH not in err.body_snippet
    ), f"{site}: credential SURVIVED into body_snippet -> {err.body_snippet!r}"
    assert _FEED_MUST_VANISH not in str(
        err
    ), f"{site}: credential SURVIVED into str(err) -> {str(err)!r}"
    assert (
        "[REDACTED-CRED]" in err.body_snippet
    ), f"{site}: body reached the caller unscrubbed -> {err.body_snippet!r}"


@pytest.mark.asyncio
@respx.mock
async def test_feed_site_embeddings_does_not_leak() -> None:
    """Feed site: kaizen/llm/client.py embeddings 4xx -> ProviderError."""
    respx.post("https://api.openai.com/v1/embeddings").mock(
        return_value=httpx.Response(401, text=_provider_body(_FEED_SECRET))
    )
    client, http = _client_and_http()
    try:
        with pytest.raises(ProviderError) as exc_info:
            await client.embed(["hello"], http_client=http)
    finally:
        await http.aclose()
    _assert_no_leak(exc_info.value, "client.py embeddings")


@pytest.mark.asyncio
@respx.mock
async def test_feed_site_completions_does_not_leak() -> None:
    """Feed site: kaizen/llm/client.py completions 4xx -> ProviderError."""
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text=_provider_body(_FEED_SECRET))
    )
    client, http = _client_and_http()
    try:
        with pytest.raises(ProviderError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}], http_client=http)
    finally:
        await http.aclose()
    _assert_no_leak(exc_info.value, "client.py completions")


@pytest.mark.asyncio
@respx.mock
async def test_feed_site_streaming_does_not_leak() -> None:
    """Feed site: kaizen/llm/http_client.py stream 4xx -> ProviderError.

    The streaming path reads the error body off the socket separately
    (``await resp.aread()`` then ``.decode(...)``), so it is an INDEPENDENT
    feed site from the two in client.py and needs its own coverage.
    """
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text=_provider_body(_FEED_SECRET))
    )
    client, http = _client_and_http()
    try:
        with pytest.raises(ProviderError) as exc_info:
            async for _chunk in client.stream(
                [{"role": "user", "content": "hi"}], http_client=http
            ):
                pass
    finally:
        await http.aclose()
    _assert_no_leak(exc_info.value, "http_client.py stream_lines")


# ---------------------------------------------------------------------------
# 3. Structural invariants — the single-choke-point contract
# ---------------------------------------------------------------------------


def _provider_error_call_sites() -> list[tuple[str, int, ast.Call]]:
    """Every `ProviderError(...)` construction in the kaizen.llm package."""
    llm_dir = Path(llm_errors.__file__).parent
    found: list[tuple[str, int, ast.Call]] = []
    for py in sorted(llm_dir.rglob("*.py")):
        tree = ast.parse(py.read_text(), filename=str(py))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ProviderError"
            ):
                found.append((py.name, node.lineno, node))
    return found


def test_every_provider_error_feed_site_is_covered_by_this_suite() -> None:
    """A NEW feed site must not land without a test.

    The behavioral tests above cover exactly three sites. If a fourth
    `ProviderError(...)` construction appears in `kaizen/llm/`, this fails and
    forces the author to extend the coverage rather than silently adding an
    unscrubbed path.
    """
    sites = _provider_error_call_sites()
    located = {(name, lineno) for name, lineno, _ in sites}
    assert len(sites) == 3, (
        "The number of ProviderError feed sites in kaizen/llm/ changed "
        f"(found {len(sites)}: {sorted(located)}). Add a behavioral "
        "no-leak test for the new site, then update this count."
    )
    assert {name for name, _, _ in sites} == {"client.py", "http_client.py"}


def test_feed_sites_pass_the_body_unformatted_to_provider_error() -> None:
    """The scrub is a single choke point only if callers do not pre-format.

    A site building its own message string (e.g.
    ``ProviderError(status, body_snippet=f"failed: {resp.text}")`` is still
    scrubbed, but a site that formats the body into a DIFFERENT exception, or
    logs it before constructing, bypasses the choke point entirely. Pinning the
    keyword shape keeps the body arriving raw so `ProviderError.__init__` is
    the one and only place redaction happens.
    """
    for name, lineno, call in _provider_error_call_sites():
        kwargs = {kw.arg for kw in call.keywords}
        assert "body_snippet" in kwargs, (
            f"{name}:{lineno} constructs ProviderError without the "
            "`body_snippet=` keyword; the scrub choke point is bypassed."
        )


def test_llm_errors_module_holds_no_private_pattern_list() -> None:
    """The root defect was TWO pattern lists. There must be exactly one.

    ``kaizen.llm.errors`` must delegate, never re-declare. A module-level
    compiled-pattern collection reappearing here is the drift restarting.
    """
    src = Path(llm_errors.__file__).read_text()
    assert "_CRED_PATTERNS" not in src, (
        "kaizen/llm/errors.py re-declared a private credential pattern list. "
        "It MUST delegate to kaizen.utils.credential_scrub instead — two lists "
        "that must agree are what caused this issue."
    )
    assert "re.compile" not in src, (
        "kaizen/llm/errors.py compiled a regex of its own. Credential patterns "
        "belong in kaizen.utils.credential_scrub (single source of truth)."
    )


def test_both_surfaces_share_one_scrub_implementation() -> None:
    """Object identity, not textual similarity, is the parity guarantee."""
    assert node_sanitizer.scrub_credentials is scrub_credentials
    assert node_sanitizer._CREDENTIAL_PATTERNS is not None
    # The node module re-exports the SHARED list object, so a pattern-level
    # assertion made through either import path is about the same rules.
    from kaizen.utils import credential_scrub as shared

    assert node_sanitizer._CREDENTIAL_PATTERNS is shared._CREDENTIAL_PATTERNS


def test_provider_error_docstring_does_not_claim_to_mirror() -> None:
    """The original docstring claimed parity it did not have.

    A docstring asserting equivalence with another module is exactly how the
    drift went unnoticed for two hardening cycles. The contract must be
    delegation (structural), never a prose claim of mirroring.
    """
    doc = ProviderError.__doc__ or ""
    assert "mirror" not in doc.lower(), (
        "ProviderError's docstring claims to mirror another scrubber. "
        "Delegate to the shared implementation and describe THAT instead."
    )
    assert "credential_scrub" in doc, (
        "ProviderError's docstring must name the shared scrub implementation "
        "it delegates to, so a reader can find the authoritative pattern list."
    )


# ---------------------------------------------------------------------------
# 4. Negative vectors — the scrub must not destroy diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "benign",
    [
        "model gpt-4o is not available in your region",
        "request_id=a1b2c3d4e5f6 not found",  # 12 hex, under the 32 floor
        "rate limit exceeded, retry after 30 seconds",
        "https://api.openai.com/v1/chat/completions returned 503",
        "https://example.com/some/path/@handle is not a valid endpoint",
        "context_length_exceeded: 8192 tokens requested, 4096 available",
    ],
)
def test_benign_provider_errors_survive_unredacted(benign: str) -> None:
    """Over-redaction that blanks ordinary diagnostics is its own failure."""
    err = ProviderError(status=400, body_snippet=benign)
    assert (
        "[REDACTED-CRED]" not in err.body_snippet
    ), f"benign provider text was redacted -> {err.body_snippet!r}"
    assert err.body_snippet == benign


# ---------------------------------------------------------------------------
# 5. ReDoS linearity — input that does NOT contain "://"
# ---------------------------------------------------------------------------


# Payload sizing balances two opposing constraints, both measured:
#
#  * HEALTHY runs must not be flaky. An earlier revision used a 2 KB baseline
#    costing ~0.3 ms; the ratio spread was 7.7-25.8x on an idle machine, wide
#    enough to trip the `< 25` bound spuriously. A flaky complexity test is
#    worse than none, because the standard response is to raise the bound —
#    precisely how a real O(n^2) regression gets buried (`rules/testing.md`
#    § Complexity Bounds). Fix the MEASUREMENT, never the threshold.
#  * FAILING runs must fail FAST. With the ReDoS present the large payload is
#    quadratic, so an oversized one turns a failure into a multi-minute hang
#    that reads as an infra problem rather than a security regression. A 250 KB
#    payload took >120 s and hit the pytest timeout instead of asserting.
#
# At 7.8 KB the healthy 8x ratio measures 7.46-9.61 (stable), while the
# unbounded-scheme ReDoS measures 41x and asserts in ~13 s.
_LINEARITY_BASE_UNITS = 2_000  # -> ~7.8 KB baseline, ~62 KB at 8x

# min-of-N. The SMALL payload is timer-noise-dominated and needs many samples;
# the LARGE one runs long enough that 3 is plenty — and keeping it at 3 is what
# bounds the failing-run wall clock.
_LINEARITY_REPEATS_SMALL = 9
_LINEARITY_REPEATS_LARGE = 3

# The scheme-backtracking payload unit. EVERY character is in the URL rules'
# scheme class `[A-Za-z0-9+.-]`, so an UNBOUNDED scheme run rescans the whole
# remaining string from every start position (quadratic). Critically, `.` and
# `-` are NOT in the AWS-secret class `[A-Za-z0-9/+]` and are not hex, so no
# vendor pattern consumes this payload before the URL rules see it.
#
# Getting this unit wrong silently disarms the test — see the docstring of
# `test_provider_error_scrub_is_linear_on_input_with_no_scheme` for the two
# shapes that LOOK adversarial and are not.
_SCHEME_BACKTRACK_UNIT = "a.b-"


def _cost(payload: str, repeats: int) -> float:
    """Minimum wall-clock over N runs — min is the noise-robust estimator."""
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        ProviderError(status=500, body_snippet=payload)
        best = min(best, time.perf_counter() - start)
    return best


def _ratio(small: str, large: str) -> float:
    """Cost of the 8x payload relative to the baseline."""
    small_cost = _cost(small, _LINEARITY_REPEATS_SMALL)
    large_cost = _cost(large, _LINEARITY_REPEATS_LARGE)
    return large_cost / max(small_cost, 1e-9)


def test_provider_error_scrub_is_linear_on_input_with_no_scheme() -> None:
    """Guards the scheme-prefix backtracking class at the WIRE surface.

    A prior change broadened the URL rules' scheme from `(https?://)` to an
    unbounded `([A-Za-z][A-Za-z0-9+.-]*://)` and cost 1773 ms on a 64 KB input.
    The bound (`{0,31}`) is what makes the scan linear.

    NO `://` APPEARS IN THE INPUT — by construction. A payload containing `://`
    lets the scheme match immediately, so the engine never backtracks the
    scheme run and the regression is invisible.

    TWO FURTHER SHAPES LOOK ADVERSARIAL AND ARE NOT. Both were measured against
    a deliberately re-injected unbounded scheme, and both PASSED (i.e. failed to
    detect it):

    * ``"a:" * n`` — colon-dense. `:` is outside the scheme class, so the
      scheme run dies after one character at every start position. 31 KB cost
      2.54 ms with the ReDoS present.
    * ``"a" * n`` — a plain run. `a` IS a hex digit, so the
      `\\b[a-fA-F0-9]{32,}\\b` rule collapses the entire payload to a 10-char
      sentinel BEFORE any URL rule runs. 62 KB cost 0.14 ms with the ReDoS
      present.

    The payload must therefore be built from `_SCHEME_BACKTRACK_UNIT`: every
    character in the scheme class, and no vendor pattern able to claim it
    first. Same input with the ReDoS present: 3.9 KB 11 ms / 15.6 KB 161 ms /
    62.5 KB 2846 ms — unmistakably quadratic.

    Self-normalising 8x ratio per `rules/testing.md` § Complexity Bounds — an
    absolute wall-clock threshold would ratchet upward under CI load until it
    masked the very regression it exists to catch.
    """
    small = _SCHEME_BACKTRACK_UNIT * _LINEARITY_BASE_UNITS  # ~7.8 KB
    large = _SCHEME_BACKTRACK_UNIT * (_LINEARITY_BASE_UNITS * 8)  # ~62 KB

    # Guard the guard: if a future pattern starts consuming the payload, the
    # timing assertion below would pass vacuously on a 10-char string.
    assert scrub_credentials(small) == small, (
        "the linearity payload is being consumed by a credential pattern before "
        "the URL rules run; this test would pass vacuously. Choose a payload "
        "unit inside the scheme class but outside every vendor pattern."
    )

    ratio = _ratio(small, large)
    assert ratio < 25, (
        f"8x input scaled {ratio:.1f}x (linear ~8x, quadratic ~64x) — a URL-rule "
        f"scheme prefix probably lost its {{0,31}} bound. Bound it; possessive "
        f"quantifiers do NOT help (the backtracking is over start positions)."
    )


def test_provider_error_scrub_is_linear_on_colon_dense_scheme_input() -> None:
    """Companion: the same adversarial shape WITH a scheme prefix.

    Covers the userinfo-run backtracking that the scheme-free test cannot
    reach, because the two rules' bounds are independent.
    """
    small = "http://" + "a:" * _LINEARITY_BASE_UNITS
    large = "http://" + "a:" * (_LINEARITY_BASE_UNITS * 8)

    ratio = _ratio(small, large)
    assert ratio < 25, (
        f"8x input scaled {ratio:.1f}x — the bounded/overflow userinfo runs are "
        f"backtracking on a colon-dense no-match token."
    )


def test_scrub_credentials_rejects_a_placeholder_that_breaks_ordering() -> None:
    """The three URL rules are order-dependent; the placeholder must not re-enter.

    A placeholder containing `@`, `://`, or whitespace would be re-matched by
    the later rules and could either double-redact or mask a real match. Fail
    loudly rather than silently emit a mis-scrubbed string (zero-tolerance
    Rule 3: no silent fallbacks).
    """
    for bad in ["[REDACTED]@", "scheme://x", "[RED ACTED]"]:
        with pytest.raises(ValueError, match="placeholder"):
            scrub_credentials("postgres://u:p@h/db", placeholder=bad)
