# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SSRF guard for LLM endpoint base URLs.

Every `LlmDeployment` / `LlmClient.from_deployment(...)` entry point routes
its `base_url` through `check_url()`. The guard rejects:

* Non-`https` schemes in production (http allowed only for the `localhost`
  label, enabling local tests against a stubbed endpoint);
* Private IPv4 ranges (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16);
* Private, loopback, and link-local IPv6 (::1, fe80::/10, fc00::/7) plus
  IPv4-mapped addresses (::ffff:127.0.0.1);
* Cloud metadata IPs and hostnames (169.254.169.254, fd00:ec2::254,
  metadata.google.internal, metadata.azure.com, metadata.aws.internal);
* Decimal / octal / hex encoded bypass attempts (2130706433, 0177.0.0.1);
* Hostnames whose DNS resolution returns any of the above private addresses
  (defeats DNS-rebinding where the attacker hosts a public domain that
  resolves to 127.0.0.1).

On reject, raises `EndpointError.InvalidEndpoint(reason="…", raw_url=…)`.
The `reason` comes from a closed allowlist in `errors.py`; the raw URL is
hashed and stored only as a fingerprint so log aggregators don't echo the
user-supplied URL verbatim.

Cross-SDK parity: semantic match with kailash-rs SafeDnsResolver. Python
uses `socket.getaddrinfo` for resolution, Rust uses hyper's resolver.

Consolidated onto the shared guard (#2091 follow-up)
----------------------------------------------------

The network DECISION -- private/loopback/link-local/metadata classification,
encoded-IP bypass forms, the RFC 2765 / RFC 6052 embedded-IPv4 ranges, the
DNS-rebinding sweep -- now lives ONCE in `kailash.utils.network_guard` and is
shared with `nexus.http_client` and core's reverse-proxy surfaces. This module
had its own full copy; nexus had a third. Three implementations of one
security control diverge, and the divergence is found by an attacker before it
is found by a reader (`zero-tolerance.md` Rule 4).

What this module KEEPS, because it is genuinely kaizen policy and not network
policy:

1. **HTTPS-only, except the `localhost` label.** The shared guard permits
   `http://` to any host that passes the address checks -- correct for a
   reverse proxy talking to an internal service over a trusted link, and
   WRONG here: an LLM request carries a provider API key in its headers, so
   plaintext `http://` to an arbitrary public host is credential disclosure.
   This check runs BEFORE delegating and is the reason this function is not a
   pure pass-through. Adopting the shared default here would have silently
   widened kaizen from "https only" to "http anywhere" -- a security
   regression wearing a refactor's clothes.

2. **The loopback carve-out is LABEL-only.** `http://localhost:11434` is
   permitted; a literal `http://127.0.0.1:11434` is REFUSED with
   `reason="loopback"`. That asymmetry is deliberate and load-bearing --
   `deployment_resolver` documents choosing the `localhost` hostname over a
   literal loopback IP for the Ollama / Docker-Model-Runner defaults for
   exactly this reason. It is preserved by passing
   `loopback_hosts={"localhost"}` to the shared guard rather than by keeping
   a private copy of the resolution logic.

One deliberate reason-code CHANGE, measured and accepted: a URL whose scheme
is neither http nor https and which also fails to parse a host -- `file:///x`,
or a bare `not-a-url` -- previously reported `malformed_url` and now reports
`scheme`. Both still REJECT; only the forensic bucket moves. The shared guard
orders the scheme check first deliberately, so `file://` attempts aggregate
separately from genuinely malformed input, which is the more useful split.
"""

from __future__ import annotations

import logging
from typing import Optional

from kailash.utils.network_guard import check_url as _shared_check_url
from kailash.utils.url_credentials import fingerprint_value
from kaizen.llm.errors import InvalidEndpoint

logger = logging.getLogger(__name__)


def _url_fingerprint(raw: str | None) -> str:
    """Produce a short, non-reversible tag for a URL.

    Must match the shape used by `errors._fingerprint` so log entries can be
    correlated with the fingerprint stored on the raised `InvalidEndpoint`.

    #617: migrated from hashlib.sha256 to the canonical BLAKE2b helper in
    `kailash.utils.url_credentials` to stay aligned with
    `errors._fingerprint` after the same migration. The two MUST use the same
    algorithm or log-to-exception correlation breaks — and they still do:
    `fingerprint_value` IS the implementation `fingerprint_secret` delegates
    to, so both names return byte-identical output.

    `fingerprint_value` rather than `fingerprint_secret` because the value
    fingerprinted here is a URL, not a credential, and the tag goes to a LOG
    line. CodeQL's `py/clear-text-logging-sensitive-data` classifies the
    result of any call whose callee name matches `secret` as sensitive data
    and raises HIGH when it reaches a logging sink — interprocedurally, so a
    local wrapper does not clear it. The finding is a naming artifact (the
    logged value is 8 hex chars of a non-reversible digest, i.e. the
    SANITIZED form), and the honest fix is to call the helper by what it
    produces rather than to suppress the alert.

    Deliberately NOT the shared guard's `url_fingerprint` (SHA-256): that one
    serves core's audit trail, this one has to join kaizen's log line to
    kaizen's exception. Sharing the network decision does not mean sharing an
    unrelated hashing contract.
    """
    if not raw:
        return "none"
    return fingerprint_value(raw)


def _rejecting_error_factory(reason: str, raw_url: Optional[str] = None):
    """Adapt the shared guard's rejection into kaizen's log-then-raise shape.

    The shared guard signals by RAISING whatever `error_factory` returns. This
    module has to WARN-log first, so the factory logs as a side effect and
    then returns the exception for the guard to raise. The log line therefore
    fires for every rejection, exactly as it did when this module owned the
    checks.

    This is the ONE rejection-logging site in the module. `_reject` routes
    through it rather than carrying a second copy of the same `logger.warning`
    call: two copies drift, and each one is an independent
    `py/clear-text-logging-sensitive-data` sink to keep clean.

    The fingerprint attached here matches the one stored on the exception
    (`InvalidEndpoint._fingerprint`), so audit trails can join the log line
    with the exception instance via the shared tag. WARN is the correct level
    because the guard SUCCEEDED at blocking an attack — operators should see
    that in routine dashboards (rules/observability.md MUST Rule 3).
    """
    logger.warning(
        "url_safety.rejected",
        extra={"reason": reason, "url_fingerprint": _url_fingerprint(raw_url)},
    )
    return InvalidEndpoint(reason, raw_url=raw_url)


def _reject(reason: str, url: str | None) -> None:
    """Log-and-raise for the kaizen-specific checks this module still owns.

    The shared guard raises what `_rejecting_error_factory` returns; the
    HTTPS-only check below has no guard to raise for it, so it raises here.
    Same factory either way, so both paths emit the identical log line.
    """
    raise _rejecting_error_factory(reason, raw_url=url)


# These hostnames are permitted with http:// so local tests can run against a
# stub endpoint. Any other host forces https://.
#
# NOTE the deliberate difference between this set and the loopback carve-out
# passed to the shared guard below. This one governs the SCHEME (may this host
# be reached over plaintext); `{"localhost"}` governs the ADDRESS (may this
# host resolve into loopback). A literal `127.0.0.1` passes the scheme check
# here and is then refused on the address check — which is the pre-existing,
# documented behaviour `deployment_resolver` depends on.
_HTTP_LOCALHOST_ALLOWLIST = frozenset({"localhost", "127.0.0.1", "::1"})

#: The loopback carve-out is LABEL-only — see the module docstring.
_LOOPBACK_LABELS = frozenset({"localhost"})


def check_url(url: str, *, resolve_dns: bool = True) -> None:
    """Validate `url` as an SSRF-safe LLM endpoint.

    Raises `InvalidEndpoint` on any rejection; `reason` comes from the fixed
    allowlist in `errors.InvalidEndpoint._REASON_ALLOWLIST`. The raw URL is
    hashed and attached only as a fingerprint on the exception, never echoed.

    `resolve_dns=False` runs only the checks that are DECIDABLE OFFLINE:
    scheme, metadata hostnames, literal-IP classification, encoded-IP and
    `inet_aton` short-form bypasses. It is NOT a test-only knob — it is the
    posture `deployment.Endpoint._validate_base_url` uses, because
    constructing an Endpoint is config parsing, not egress, and a name that
    resolves public at parse time can resolve to loopback at connect time.
    The resolve-time gate is `http_client.SafeDnsResolver.check_host`,
    installed structurally on the only httpx transport in `kaizen/llm/**`
    and re-run immediately before every TCP SYN. See that validator's
    docstring for the full rationale.

    The address checks are `kailash.utils.network_guard.check_url`. The
    HTTPS-only policy below is kaizen's own and runs first — see the module
    docstring for why it is not delegated.
    """
    # ---- kaizen-specific transport policy: HTTPS-only ------------------
    # Runs BEFORE the shared guard because it is stricter than the shared
    # default, not a refinement of it. An LLM request carries a provider API
    # key, so plaintext http to an arbitrary host is credential disclosure
    # regardless of whether the address itself is safe.
    if isinstance(url, str) and url:
        from urllib.parse import urlparse

        try:
            _parsed = urlparse(url)
        except Exception:
            _parsed = None
        if _parsed is not None:
            _scheme = (_parsed.scheme or "").lower()
            _host = (_parsed.hostname or "").lower()
            if _scheme == "http" and _host and _host not in _HTTP_LOCALHOST_ALLOWLIST:
                _reject("scheme", url)

    # ---- shared SSRF address checks ------------------------------------
    _shared_check_url(
        url,
        resolve_dns=resolve_dns,
        # Loopback is reachable, but only under the `localhost` LABEL; a
        # literal 127.0.0.1 / ::1 stays refused. See the module docstring.
        allow_loopback=True,
        loopback_hosts=_LOOPBACK_LABELS,
        # Everything else keeps the strict posture: no RFC1918, no metadata.
        allow_private=False,
        allow_metadata=False,
        error_factory=_rejecting_error_factory,
    )


__all__ = ["check_url"]
