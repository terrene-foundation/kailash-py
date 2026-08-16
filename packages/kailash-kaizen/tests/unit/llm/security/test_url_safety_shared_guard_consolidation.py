# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""#2091 follow-up — kaizen's SSRF guards consolidated onto the shared one.

`kaizen.llm.url_safety` carried a full private copy of the SSRF address
guard, and `kaizen.llm.http_client`'s `SafeDnsResolver` carried a SECOND copy
inside the same package — so the repo shipped three implementations of one
security control (core's proxy guard being the third). Two guards drift as
readily inside a package as across packages, and here the two kaizen copies
are the parse-time and connect-time halves of the SAME defence: a divergence
would mean they disagreed about what "private" means.

They now all import `kailash.utils.network_guard`.

The risk a consolidation carries is not "does it still block" — it is
**silently widening** what the narrower guard used to refuse. kaizen's guard
is STRICTER than core's in two deliberate ways, and both are pinned here:

1. **HTTPS-only except the `localhost` label.** Core permits `http://` to any
   address-safe host, which is right for a reverse proxy on a trusted link and
   wrong for an LLM call that carries a provider API key in its headers.
   Measured on the shared guard directly: `http://api.openai.com/v1` is
   ALLOW. If kaizen ever delegates that decision, this file goes red.

2. **The loopback carve-out is LABEL-only.** `http://localhost:11434` is
   permitted; a literal `http://127.0.0.1:11434` is REFUSED. Not incidental —
   `deployment_resolver` documents choosing the `localhost` hostname over a
   literal loopback IP for its Ollama / Docker-Model-Runner defaults because
   "a literal-IP default would raise `InvalidEndpoint` before any request was
   ever built".

Differential evidence, 41 probes, pre- vs post-consolidation:

    TOTAL PROBES: 41   DIFFERENCES: 3
       'file:///etc/passwd'   reject:malformed_url -> reject:scheme
       'javascript:alert(1)'  reject:malformed_url -> reject:scheme
       'not-a-url'            reject:malformed_url -> reject:scheme
    WIDENING (reject->ALLOW, security regressions): 0

Four FURTHER reason-code moves arrived with the IMDS-wrapper fix this branch
rebased onto (#2136), measured the same way — all still REJECT, widening 0:

    https://[64:ff9b::169.254.169.254]/  reject:ipv4_mapped -> reject:metadata_service
    https://[::ffff:0:a9fe:a9fe]/        reject:ipv4_mapped -> reject:metadata_service
    https://[64:ff9b::a9fe:a9fe]/        reject:ipv4_mapped -> reject:metadata_service
    https://[::ffff:169.254.169.254]/    reject:ipv4_mapped -> reject:link_local

All seven are reason-code reclassification; every accept/reject verdict is
unchanged and nothing was widened. The scheme-before-host ordering makes
`file://` attempts aggregate separately from genuinely malformed input, and
the wrapper-aware metadata gate reports a metadata-wrapped address as
`metadata_service` rather than the generic `ipv4_mapped` — both strictly
more useful forensic buckets than what they replaced.
"""

from __future__ import annotations

import ipaddress

import pytest

from kailash.utils import network_guard
from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.url_safety import check_url

pytestmark = pytest.mark.unit


def _verdict(url: str, *, resolve_dns: bool = False) -> str:
    try:
        check_url(url, resolve_dns=resolve_dns)
        return "ALLOW"
    except InvalidEndpoint as exc:
        return f"reject:{exc.reason}"


# ---------------------------------------------------------------------------
# 1. HTTPS-only — the policy the shared guard does NOT have
# ---------------------------------------------------------------------------


def test_shared_guard_would_allow_plaintext_http_to_a_public_host():
    """The instrument for the widening risk.

    This asserts what the SHARED guard does, so the next assertion means
    something: kaizen's refusal cannot be inherited, it has to be kaizen's own.
    If this ever starts raising, the test below stops discriminating and this
    file must be revisited.
    """
    network_guard.check_url("http://api.openai.com/v1", resolve_dns=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "http://example.com/",
        "http://8.8.8.8/",
        "http://metadata.google.internal/",
    ],
)
def test_kaizen_still_refuses_plaintext_http_to_non_localhost(url):
    """An LLM request carries a provider API key — plaintext is disclosure."""
    assert _verdict(url) == "reject:scheme"


@pytest.mark.parametrize(
    "url", ["https://api.openai.com/v1", "https://8.8.8.8/", "https://1.1.1.1/"]
)
def test_https_to_a_public_host_is_still_allowed(url):
    """No-false-positive polarity: the guard must not refuse legitimate use."""
    assert _verdict(url) == "ALLOW"


# ---------------------------------------------------------------------------
# 2. Loopback carve-out is LABEL-only — deliberate, and depended upon
# ---------------------------------------------------------------------------


def test_localhost_label_is_permitted_over_http():
    """`DEFAULT_OLLAMA_BASE_URL` is exactly this shape."""
    assert _verdict("http://localhost:11434", resolve_dns=True) == "ALLOW"


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:11434", "https://127.0.0.1:8000/v1", "http://[::1]:8000/"]
)
def test_literal_loopback_ip_is_still_refused(url):
    """The asymmetry `deployment_resolver` documents and relies on.

    A naive consolidation passing `allow_loopback=True` with the shared
    default host set would ALLOW these — that is the widening this pins shut.
    """
    assert _verdict(url, resolve_dns=True) == "reject:loopback"


def test_shared_default_loopback_set_would_have_widened_this():
    """Shows the mistake this avoided, so the narrowing is not accidental."""
    # With core's DEFAULT loopback set, the literal IP is permitted...
    network_guard.check_url(
        "http://127.0.0.1:11434", allow_loopback=True, resolve_dns=False
    )
    # ...and with the label-only set kaizen passes, it is refused.
    with pytest.raises(Exception):
        network_guard.check_url(
            "http://127.0.0.1:11434",
            allow_loopback=True,
            loopback_hosts={"localhost"},
            resolve_dns=False,
        )


# ---------------------------------------------------------------------------
# 3. Everything the guard blocked before, it still blocks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://10.1.2.3/v1", "private_ipv4"),
        ("https://192.168.1.1/v1", "private_ipv4"),
        ("https://172.16.0.1/v1", "private_ipv4"),
        ("https://224.0.0.1/", "private_ipv4"),
        ("https://0.0.0.0/", "private_ipv4"),
        ("https://169.254.169.254/", "metadata_service"),
        ("https://[fd00:ec2::254]/", "metadata_service"),
        ("https://metadata.google.internal/", "metadata_host"),
        ("https://metadata.azure.com/", "metadata_host"),
        ("https://metadata.aws.internal/", "metadata_host"),
        ("https://[fe80::1]/", "link_local"),
        ("https://[fc00::1]/", "private_ipv6"),
        ("https://[::ffff:127.0.0.1]/", "ipv4_mapped"),
        ("https://[64:ff9b::7f00:1]/", "ipv4_mapped"),
        ("https://2130706433/", "encoded_ip_bypass"),
        ("https://0177.0.0.1/", "encoded_ip_bypass"),
        ("https://0x7f.0.0.1/", "encoded_ip_bypass"),
        ("https://127.1/", "encoded_ip_bypass"),
        ("ftp://example.com/", "scheme"),
        ("gopher://x/", "scheme"),
        ("", "malformed_url"),
        ("https://", "malformed_url"),
    ],
)
def test_pre_existing_rejections_are_preserved_with_their_reason_codes(url, reason):
    assert _verdict(url) == f"reject:{reason}"


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "javascript:alert(1)", "not-a-url"]
)
def test_deliberately_reclassified_inputs_still_reject(url):
    """The three measured differences. Still REFUSED; only the bucket moved.

    Pinned so the reclassification is a recorded decision rather than drift.
    """
    assert _verdict(url) == "reject:scheme"


@pytest.mark.parametrize(
    "url", ["https://[::ffff:8.8.8.8]/", "https://[2606:4700:4700::1111]/"]
)
def test_public_addresses_are_not_over_blocked(url):
    assert _verdict(url) == "ALLOW"


@pytest.mark.parametrize(
    "url,reason",
    [
        ("https://[64:ff9b::169.254.169.254]/", "metadata_service"),
        ("https://[::ffff:0:a9fe:a9fe]/", "metadata_service"),
        ("https://[64:ff9b::a9fe:a9fe]/", "metadata_service"),
        ("https://[::ffff:169.254.169.254]/", "link_local"),
    ],
)
def test_ipv6_wrapped_metadata_is_refused_with_the_precise_reason(url, reason):
    """Inherited from the shared guard's #2136 IMDS-wrapper fix.

    kaizen refused these BEFORE consolidation too (its own `_is_private_ipv6`
    ran unconditionally), but under the generic `ipv4_mapped` bucket. Pinning
    the sharper reason keeps the forensic split from silently regressing --
    and demonstrates the consolidation's payoff: the fix landed once in core
    and all three consumers got it.
    """
    assert _verdict(url) == f"reject:{reason}"


# ---------------------------------------------------------------------------
# 4. One implementation, not five
# ---------------------------------------------------------------------------


def test_both_kaizen_guards_use_the_shared_classifiers():
    """Object identity, not behavioural agreement.

    Two copies that agree today are exactly the thing that drifts, so this
    asserts they are the SAME objects.
    """
    import kaizen.llm.http_client as hc

    assert hc._is_private_ipv4 is network_guard.is_private_ipv4
    assert hc._is_private_ipv6 is network_guard.is_private_ipv6
    assert hc._METADATA_IPS is network_guard.METADATA_IPS
    # The reason MAPPING is shared too, not just the private-range predicates.
    # Sharing only the predicates is what let the two gates agree on the
    # verdict while disagreeing on the bucket for six addresses.
    assert hc.metadata_candidates is network_guard.metadata_candidates
    assert hc._ip_reason is network_guard.ip_reason
    # The RFC 2765 / RFC 6052 ranges are no longer referenced here at all --
    # `ip_reason` and `metadata_candidates` own that decision now. Re-importing
    # them would mean a second wrapper ladder had grown back.
    for name in ("_IPV4_TRANSLATED_NETWORK", "_NAT64_WELLKNOWN_NETWORK"):
        assert not hasattr(hc, name), (
            f"http_client re-grew {name}: the wrapper decision belongs to "
            f"network_guard.metadata_candidates / ip_reason, once"
        )


def test_url_safety_holds_no_private_classifier_copy():
    """The parse-time guard must not have grown its own copy back."""
    import kaizen.llm.url_safety as us

    for name in (
        "_is_private_ipv4",
        "_is_private_ipv6",
        "_METADATA_IPS",
        "_detect_encoded_ip_bypass",
        "_iter_resolved_ips",
        "_try_inet_aton_shortform",
    ):
        assert not hasattr(us, name), (
            f"url_safety re-grew a private {name} — the divergence #2091's "
            f"follow-up removed is back"
        )


def test_safednsresolver_still_blocks_at_connect_time():
    """The connect-time half must keep working through the shared classifiers."""
    from kaizen.llm.http_client import SafeDnsResolver

    resolver = SafeDnsResolver()
    for host, reason in [
        ("169.254.169.254", "metadata_service"),
        ("10.1.2.3", "private_ipv4"),
        ("127.0.0.1", "loopback"),
    ]:
        with pytest.raises(InvalidEndpoint) as exc:
            resolver.check_host(host)
        assert exc.value.reason == reason
    # Public literal still accepted.
    resolver.check_host("8.8.8.8")


#: Spans every class the two gates classify: RFC1918, loopback, link-local,
#: IMDS (v4 + v6), multicast, unspecified, CGNAT, benchmark, public, and all
#: three IPv6 embedded-IPv4 wrapper forms. The wrappers are the ones that
#: matter — a corpus without them is exactly what let the parse gate and the
#: connect gate disagree unnoticed.
_PARITY_ADDRESSES = [
    "127.0.0.1",
    "127.255.255.254",
    "10.0.0.1",
    "10.255.255.255",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",
    "169.254.0.1",
    "0.0.0.0",
    "224.0.0.1",
    "100.64.0.1",
    "198.18.0.1",
    "8.8.8.8",
    "1.1.1.1",
    "::1",
    "fe80::1",
    "fc00::1",
    "fd00:ec2::254",
    "::",
    "ff02::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
    "64:ff9b::7f00:1",
    "64:ff9b::169.254.169.254",
    "::ffff:0:a9fe:a9fe",
    "64:ff9b::a9fe:a9fe",
    "::ffff:169.254.169.254",
    "2606:4700:4700::1111",
]


@pytest.mark.parametrize("addr", _PARITY_ADDRESSES)
def test_parse_time_and_connect_time_agree_on_verdict_AND_bucket(addr):
    """The reason the in-package duplicate mattered — and the bucket, not
    just the verdict.

    Asserting only the VERDICT is what let this drift: both gates refused
    every wrapper form, so a verdict-only check stayed green while the
    connect gate reported the generic `ipv4_mapped` for four IMDS-wrapper
    addresses the parse gate buckets as `metadata_service` / `link_local`,
    and reported `private_ipv4` where the parse gate said `loopback` /
    `link_local`. `metadata_service` exists precisely so a metadata
    exfiltration attempt is separable in a dashboard; half the enforcement
    surfaces were not producing it.

    Both gates now share `network_guard.metadata_candidates` and
    `network_guard.ip_reason`, in that order, so the bucket cannot drift
    without this failing.
    """
    from kaizen.llm.http_client import SafeDnsResolver

    url = f"https://[{addr}]/" if ":" in addr else f"https://{addr}/"
    try:
        check_url(url, resolve_dns=False)
        parse = "ALLOW"
    except InvalidEndpoint as exc:
        parse = f"reject:{exc.reason}"

    try:
        SafeDnsResolver().check_host(addr)
        connect = "ALLOW"
    except InvalidEndpoint as exc:
        connect = f"reject:{exc.reason}"

    assert parse == connect, (
        f"{addr}: parse gate says {parse}, connect gate says {connect} — "
        f"the two SSRF enforcement surfaces disagree"
    )
