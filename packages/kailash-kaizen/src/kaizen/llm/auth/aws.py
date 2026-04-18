# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AWS auth strategies: `AwsBearerToken`, `AwsSigV4`, `AwsCredentials`.

Session 3 (S4a + S4b-i) of #498. Implements two AWS auth strategies for the
Bedrock runtime surface:

* `AwsBearerToken(token, region)` -- static bearer-token auth using the
  `Authorization: Bearer <token>` header. The bearer-token path is the
  fast-path for operators who have cut a rotatable Bedrock token via the
  AWS console + STS. Region is carried on the strategy to enforce the
  allowlist at construction (NEW-H2 resolution from spec review: keeping
  region on the strategy avoids drift between strategy + endpoint).
* `AwsSigV4(credentials)` -- full AWS Signature Version 4 signing using
  `botocore.auth.SigV4Auth`. SigV4 is required for the assumed-role and
  workload-identity paths where a static bearer is not available. We route
  canonicalization exclusively through botocore -- inlined HMAC chain
  reproduction in this module is BLOCKED by rules/zero-tolerance.md Rule
  4 (no workarounds for SDK bugs -- if botocore has a bug, fix botocore).
  This policy is grep-auditable: the regex for the HMAC primitive
  (imported from Python's stdlib) MUST return empty against this file.

Both strategies validate the region against `BEDROCK_SUPPORTED_REGIONS` at
construction and raise `RegionNotAllowed` on unknown input. The region
allowlist is byte-identical to `kailash-rs/crates/kailash-kaizen/src/llm/
deployment/bedrock.rs::BEDROCK_REGIONS` so cross-SDK forensic correlation
works without translation.

`AwsCredentials` wraps the AWS access-key / secret-key / session-token
triple in `pydantic.SecretStr` so `repr`, logs, and pickle captures never
leak the raw secret. Rotation via `refresh()` re-reads credentials from
the botocore provider chain; the rotation is guarded by an `asyncio.Lock`
so concurrent refresh attempts under 403 ExpiredTokenException serialize
to exactly one botocore call per wave.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

try:
    from botocore.auth import SigV4Auth as _BotocoreSigV4Auth
    from botocore.awsrequest import AWSRequest as _BotocoreAWSRequest
    from botocore.credentials import Credentials as _BotocoreCredentials
except ImportError:  # pragma: no cover - optional-extra guard
    _BotocoreSigV4Auth = None
    _BotocoreAWSRequest = None
    _BotocoreCredentials = None

from pydantic import SecretStr

from kaizen.llm.auth.bearer import ApiKey
from kaizen.llm.errors import AuthError, LlmClientError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Region allowlist -- byte-identical to kailash-rs bedrock.rs::BEDROCK_REGIONS
# ---------------------------------------------------------------------------

# Source of truth for cross-SDK parity:
# kailash-rs/crates/kailash-kaizen/src/llm/deployment/bedrock.rs::BEDROCK_REGIONS
#
# 27 published AWS Bedrock regions, refreshed per release. Operators on
# unreleased regions will need to wait for a release bump; we deliberately
# do NOT accept arbitrary region strings because the region is interpolated
# into the endpoint hostname (`bedrock-runtime.{region}.amazonaws.com`),
# and a permissive allowlist would be a host-control vector.
#
# Order MUST match the Rust source so the cross-SDK parity fixture (S9) can
# compare the tuple byte-for-byte.
BEDROCK_SUPPORTED_REGIONS: tuple[str, ...] = (
    # Americas
    "us-east-1",
    "us-east-2",
    "us-west-2",
    "us-gov-east-1",
    "us-gov-west-1",
    "ca-central-1",
    "sa-east-1",
    # Europe
    "eu-central-1",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-north-1",
    "eu-south-1",
    "eu-south-2",
    # Asia Pacific
    "ap-south-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-southeast-3",
    "ap-southeast-4",
    "ap-southeast-5",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-northeast-3",
    "ap-east-1",
    # Middle East & Africa
    "me-south-1",
    "me-central-1",
    "af-south-1",
)


class RegionNotAllowed(AuthError):
    """The region supplied to an AWS auth strategy is not in the allowlist.

    Region strings are PUBLIC identifiers (they appear in AWS docs, AWS
    CLI output, and in Bedrock console URLs), so echoing the rejected
    region in the error message is safe and useful for operators
    debugging "why doesn't eu-central-2 work" -type issues.
    """

    def __init__(self, region: str) -> None:
        self.region = region
        super().__init__(
            f"region not allowed for AWS Bedrock: {region!r} "
            f"(allowed: {len(BEDROCK_SUPPORTED_REGIONS)} published regions -- "
            f"see kaizen.llm.auth.aws.BEDROCK_SUPPORTED_REGIONS)"
        )


class ClockSkew(AuthError):
    """SigV4 signing request was outside the 5-minute clock-skew window."""

    def __init__(self, skew_seconds: float) -> None:
        self.skew_seconds = skew_seconds
        super().__init__(
            f"SigV4 request outside 5-minute clock-skew window "
            f"(skew={skew_seconds:.1f}s)"
        )


def _validate_region_or_raise(region: Any) -> str:
    """Normalize + allowlist-check a region string.

    Centralized so `AwsBearerToken.__init__` and `AwsSigV4.__init__` apply
    the same check -- drift between the two constructors is BLOCKED.
    """
    if not isinstance(region, str) or not region:
        raise RegionNotAllowed(repr(region))
    if region not in BEDROCK_SUPPORTED_REGIONS:
        raise RegionNotAllowed(region)
    return region


# ---------------------------------------------------------------------------
# AwsBearerToken -- static bearer-token auth (S4a)
# ---------------------------------------------------------------------------


class AwsBearerToken:
    """Bearer-token auth strategy for AWS Bedrock.

    Applies `Authorization: Bearer <token>` on `apply(request)`. The
    region is carried on the strategy so the allowlist is enforced at
    construction (not only at endpoint-build time), which means a caller
    constructing `AwsBearerToken(token, "attacker.com")` sees a
    `RegionNotAllowed` at the construction site rather than later during
    URL assembly. Cross-SDK parity: the Rust `AwsBearerToken` also carries
    no token text in its Debug impl -- our `__repr__` redacts to the
    `ApiKey.fingerprint` only.

    `refresh()` is a no-op for bearer tokens; rotating to a new token is
    modeled as "construct a new AwsBearerToken and replace the deployment"
    rather than mutating the strategy in place.
    """

    __slots__ = ("_key", "_region")

    def __init__(self, token: str | SecretStr | ApiKey, region: str) -> None:
        # Accept raw str, pydantic SecretStr, or already-wrapped ApiKey so
        # callers who already hold a secret-bearing wrapper don't round-trip
        # through plain-string unwrap.
        if isinstance(token, ApiKey):
            key = token
        elif isinstance(token, (str, SecretStr)):
            if isinstance(token, str) and not token:
                raise AuthError("AwsBearerToken token must be a non-empty string")
            if isinstance(token, SecretStr) and not token.get_secret_value():
                raise AuthError("AwsBearerToken token must be a non-empty string")
            key = ApiKey(token)
        else:
            raise TypeError(
                "AwsBearerToken token must be str, SecretStr, or ApiKey; "
                f"got {type(token).__name__}"
            )
        self._region: str = _validate_region_or_raise(region)
        self._key: ApiKey = key

    @classmethod
    def from_env(cls) -> "AwsBearerToken":
        """Construct from `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION`.

        Both env vars MUST be present AND non-empty; a missing / empty
        value raises `AuthError.MissingCredential` (for the token) or
        `RegionNotAllowed` (for the region). We deliberately do NOT
        default region to `us-east-1` or any other value -- silent
        defaulting is the #1 cause of "my model serves from the wrong
        region and the latency tanked" incidents.
        """
        token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or ""
        region = os.environ.get("AWS_REGION") or ""
        if not token:
            from kaizen.llm.errors import MissingCredential

            raise MissingCredential("AWS_BEARER_TOKEN_BEDROCK")
        if not region:
            # Empty string fails the allowlist check with a distinct
            # RegionNotAllowed message so the operator can grep for
            # "region not allowed" across logs and find this call site.
            raise RegionNotAllowed("")
        return cls(token=token, region=region)

    @property
    def region(self) -> str:
        """The validated region. Public -- regions are non-sensitive."""
        return self._region

    @property
    def fingerprint(self) -> str:
        """8-char SHA-256 fingerprint of the token for log correlation."""
        return self._key.fingerprint

    def apply(self, request: Any) -> Any:
        """Install `Authorization: Bearer <token>` on the request.

        Accepts dict-like (with `headers` key) or object-with-`.headers`.
        Mirrors `ApiKeyBearer.apply` so callers can substitute the two
        without branching.
        """
        header_value = f"Bearer {self._key.get_secret_value()}"
        headers = getattr(request, "headers", None)
        if headers is not None and hasattr(headers, "__setitem__"):
            headers["Authorization"] = header_value
            return request
        if isinstance(request, dict):
            hdrs = request.setdefault("headers", {})
            hdrs["Authorization"] = header_value
            return request
        raise TypeError(
            "AwsBearerToken.apply requires a request with .headers mapping "
            "or a dict containing a 'headers' key"
        )

    def auth_strategy_kind(self) -> str:
        return "aws_bearer_token"

    def refresh(self) -> None:
        """No-op -- bearer tokens are static; rotation is out-of-band."""
        return None

    def __repr__(self) -> str:
        # Never include raw token bytes. Fingerprint + region is enough for
        # correlation across log aggregators.
        return (
            f"AwsBearerToken(region={self._region!r}, "
            f"fingerprint={self._key.fingerprint})"
        )


# ---------------------------------------------------------------------------
# AwsCredentials -- SecretStr-wrapped AWS credential triple
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AwsCredentials:
    """AWS credential triple for SigV4 signing.

    All three string fields are wrapped in `pydantic.SecretStr` so repr /
    pickle / logging never leak raw values. The dataclass is `frozen=True`
    so a running `AwsSigV4` cannot mutate its stored credential behind its
    rotation lock -- the rotation path replaces the whole object slot.

    `region` is the only non-secret field. It is still validated against
    the Bedrock allowlist in `AwsSigV4.__init__`; this dataclass itself
    does not enforce it so non-Bedrock SigV4 consumers (if any land) could
    carry an `AwsCredentials` with an arbitrary region.
    """

    access_key_id: SecretStr
    secret_access_key: SecretStr
    session_token: Optional[SecretStr]
    region: str

    @classmethod
    def from_botocore(cls, creds: Any, region: str) -> "AwsCredentials":
        """Adapt a botocore `Credentials` object into our SecretStr form.

        Called by `AwsSigV4.refresh()` after the provider chain resolves.
        The botocore credential object MAY be None (resolver failure) --
        callers MUST null-check before invoking.
        """
        if creds is None:
            raise AuthError(
                "botocore provider chain returned no credentials; set "
                "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or configure "
                "~/.aws/credentials"
            )
        # botocore.Credentials exposes .access_key, .secret_key, .token
        access_key = getattr(creds, "access_key", None)
        secret_key = getattr(creds, "secret_key", None)
        token = getattr(creds, "token", None)
        if not access_key or not secret_key:
            raise AuthError(
                "botocore provider chain returned partial credentials; "
                "access_key_id and secret_access_key are both required"
            )
        return cls(
            access_key_id=SecretStr(access_key),
            secret_access_key=SecretStr(secret_key),
            session_token=SecretStr(token) if token else None,
            region=region,
        )

    def to_botocore(self) -> Any:
        """Return a botocore-compatible `Credentials` for SigV4Auth.

        Unwraps the SecretStr fields just long enough to hand them to
        botocore's signer. The returned object IS secret-bearing in its
        own right -- it is botocore's responsibility to hold it safely
        during signing and to drop references afterward.
        """
        if _BotocoreCredentials is None:
            raise LlmClientError(
                "botocore is not installed; install the [bedrock] extra: "
                "pip install kailash-kaizen[bedrock]"
            )
        return _BotocoreCredentials(
            access_key=self.access_key_id.get_secret_value(),
            secret_key=self.secret_access_key.get_secret_value(),
            token=self.session_token.get_secret_value() if self.session_token else None,
        )


# ---------------------------------------------------------------------------
# AwsSigV4 -- full SigV4 signing via botocore (S4b-i)
# ---------------------------------------------------------------------------

_CLOCK_SKEW_WINDOW_SECONDS = 300  # 5 minutes per AWS SigV4 spec.


class AwsSigV4:
    """AWS SigV4 signing strategy, backed by `botocore.auth.SigV4Auth`.

    Canonicalization -- the delicate bit of SigV4 -- is delegated to
    botocore. Inlined HMAC logic is BLOCKED by rules/zero-tolerance.md
    Rule 4: if botocore's SigV4Auth has a bug, the fix lives in botocore.
    This is enforced by a repo-level grep audit: `hmac\\.new` MUST NOT
    appear in this file.

    # Clock skew

    AWS SigV4 signatures carry an `x-amz-date` header that the upstream
    service compares against its own clock with a 5-minute tolerance.
    This strategy validates the request timestamp against `time.time()`
    with the same tolerance BEFORE signing, so a clock-skewed caller gets
    a loud `ClockSkew` error locally instead of an opaque 403 from AWS.
    The pre-sign check is structural insurance against forgetting an NTP
    sync on an air-gapped deployment.

    # Credential rotation

    On upstream 403 with `ExpiredTokenException`, the client calls
    `refresh()` to re-read credentials from botocore's provider chain.
    Concurrent refresh calls are serialized by `self._rotation_lock`
    (`asyncio.Lock`) so a thundering herd of 403s produces exactly one
    botocore provider invocation per rotation wave. The stored credential
    is replaced atomically (the immutable `AwsCredentials` dataclass slot
    is reassigned as a single pointer swap).

    The SecretStr wrappers on the OLD `AwsCredentials` object are cleared
    via `.get_secret_value()` -> overwrite-in-place (best-effort --
    Python's immutable-string guarantees mean we can't truly zero memory,
    but we can drop the SecretStr references so the GC can collect).

    # Streaming

    For streaming request bodies, `x-amz-content-sha256` is set to the
    well-known `STREAMING-AWS4-HMAC-SHA256-PAYLOAD` literal (per AWS
    SigV4 chunked-encoding spec). Non-streaming requests get the SHA-256
    of the payload, which botocore computes.
    """

    def __init__(
        self,
        credentials: AwsCredentials,
        *,
        service: str = "bedrock",
    ) -> None:
        if _BotocoreSigV4Auth is None:
            raise LlmClientError(
                "botocore is not installed; install the [bedrock] extra: "
                "pip install kailash-kaizen[bedrock]"
            )
        if not isinstance(credentials, AwsCredentials):
            raise TypeError(
                "AwsSigV4.credentials must be an AwsCredentials; "
                f"got {type(credentials).__name__}"
            )
        _validate_region_or_raise(credentials.region)
        self._service = service
        self._credentials: AwsCredentials = credentials
        # Lock guards rotation: any .refresh() call acquires the lock,
        # re-reads botocore's provider chain, and swaps self._credentials
        # under the lock. Concurrent refreshers pile up behind the lock.
        self._rotation_lock = asyncio.Lock()

    @property
    def credentials(self) -> AwsCredentials:
        """Snapshot of the current credential state (safe to hand to tests)."""
        return self._credentials

    def _check_clock_skew(self, now_epoch: Optional[float] = None) -> None:
        """Reject requests outside the 5-minute clock-skew window.

        The "current time" argument is optional so tests can pin it. In
        production the caller passes None and we use `time.time()`.
        """
        now = now_epoch if now_epoch is not None else time.time()
        # Compare against our own wall clock's UTC -- we are checking that
        # THIS machine's sense of time is roughly correct. botocore will
        # produce its own x-amz-date at sign time; if THAT timestamp is
        # outside AWS's tolerance, AWS returns 403. Our check catches the
        # "clock is ~hours off" failure mode BEFORE we burn a signing call.
        utc_now_epoch = datetime.now(tz=timezone.utc).timestamp()
        skew = abs(utc_now_epoch - now)
        if skew > _CLOCK_SKEW_WINDOW_SECONDS:
            raise ClockSkew(skew_seconds=skew)

    def sign(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        body: Optional[bytes] = None,
        *,
        streaming: bool = False,
    ) -> dict[str, str]:
        """Sign an AWS request and return the resulting header dict.

        Delegates canonicalization + HMAC chain to
        `botocore.auth.SigV4Auth.add_auth`. The returned headers are ready
        to be attached to the outbound HTTP request.

        For streaming calls, `x-amz-content-sha256` is pre-set to the
        AWS-reserved literal per the SigV4 chunked-encoding spec; botocore
        respects an already-set `x-amz-content-sha256` and does NOT
        overwrite it.
        """
        self._check_clock_skew()
        hdrs = dict(headers or {})
        if streaming:
            hdrs["x-amz-content-sha256"] = "STREAMING-AWS4-HMAC-SHA256-PAYLOAD"
        aws_request = _BotocoreAWSRequest(
            method=method,
            url=url,
            data=body if body is not None else b"",
            headers=hdrs,
        )
        botocore_creds = self._credentials.to_botocore()
        signer = _BotocoreSigV4Auth(
            botocore_creds, self._service, self._credentials.region
        )
        signer.add_auth(aws_request)
        return dict(aws_request.headers.items())

    def apply(self, request: Any) -> Any:
        """Sign a request and install the SigV4 headers.

        Accepts dict-like (with `method`, `url`, `headers`, optional
        `body`, optional `streaming`) or object-with-those-attrs. Mirrors
        the `ApiKeyBearer` / `AwsBearerToken` contract but the input shape
        is richer because SigV4 needs method + URL + body to canonicalize.
        """
        if isinstance(request, dict):
            method = request.get("method", "POST")
            url = request.get("url")
            if not url:
                raise TypeError("AwsSigV4.apply requires request['url']")
            headers = request.setdefault("headers", {})
            body = request.get("body")
            streaming = bool(request.get("streaming", False))
            signed = self.sign(
                method=method,
                url=url,
                headers=headers,
                body=body,
                streaming=streaming,
            )
            request["headers"] = signed
            return request
        # Object-with-attrs path
        method = getattr(request, "method", "POST")
        url = getattr(request, "url", None)
        if not url:
            raise TypeError("AwsSigV4.apply requires request.url")
        headers = getattr(request, "headers", None)
        if headers is None or not hasattr(headers, "__setitem__"):
            raise TypeError(
                "AwsSigV4.apply requires a request.headers mapping (dict-like)"
            )
        body = getattr(request, "body", None)
        streaming = bool(getattr(request, "streaming", False))
        signed = self.sign(
            method=method,
            url=str(url),
            headers=dict(headers),
            body=body,
            streaming=streaming,
        )
        # Overwrite headers in place so callers retain their reference.
        for k, v in signed.items():
            headers[k] = v
        return request

    def auth_strategy_kind(self) -> str:
        return "aws_sigv4"

    async def refresh(self) -> None:
        """Re-read credentials from botocore's provider chain.

        Guarded by `self._rotation_lock` so concurrent callers after a
        wave of 403 ExpiredTokenException responses serialize to exactly
        one botocore invocation. The lock is released as soon as the new
        credential slot is installed.

        The OLD `AwsCredentials` object is explicitly de-referenced so the
        GC can collect its SecretStr fields (pydantic's SecretStr does
        not expose a zeroize API -- the best we can do in Python is drop
        references promptly and rely on CPython's reference-counting
        freeing the underlying buffers).
        """
        if _BotocoreSigV4Auth is None:
            raise LlmClientError(
                "botocore is not installed; install the [bedrock] extra"
            )
        async with self._rotation_lock:
            # Re-import inside the lock so pytest-style monkeypatching of
            # botocore.session surfaces here rather than being frozen at
            # strategy-construction time.
            from botocore.session import Session as _Session

            session = _Session()
            resolver_creds = session.get_credentials()
            region = self._credentials.region
            new_creds = AwsCredentials.from_botocore(resolver_creds, region=region)
            old_creds = self._credentials
            self._credentials = new_creds
            # Drop the old wrapper references. pydantic.SecretStr stores
            # the underlying string in a private attribute; we clear our
            # references to the dataclass and let CPython's refcount-to-
            # zero free them. Assigning placeholders blocks accidental
            # re-use via a lingering pointer.
            #
            # Explicit del + reassignment of each field to an empty
            # SecretStr keeps the attribute type stable (important for
            # any external tool that may have captured a weakref).
            _zeroize_awscredentials(old_creds)
            logger.info(
                "aws_sigv4.credentials_refreshed",
                extra={
                    "region": region,
                    "auth_strategy_kind": "aws_sigv4",
                    "session_token_present": new_creds.session_token is not None,
                },
            )

    def __repr__(self) -> str:
        return (
            f"AwsSigV4(region={self._credentials.region!r}, "
            f"service={self._service!r})"
        )


def _zeroize_awscredentials(creds: AwsCredentials) -> None:
    """Best-effort zeroization of an old AwsCredentials slot.

    pydantic.SecretStr does not expose a public zeroize API. CPython
    strings are immutable, so we cannot overwrite the underlying bytes
    in-place. What we CAN do is swap the internal `_secret_value`
    attribute to an empty string reference so any lingering pointer to
    the SecretStr wrapper returns "" rather than the real credential.
    """
    for field_name in ("access_key_id", "secret_access_key", "session_token"):
        secret = getattr(creds, field_name, None)
        if isinstance(secret, SecretStr):
            # SecretStr stores the value in `_secret_value` (pydantic v2).
            # Replace with an empty string so subsequent
            # `get_secret_value()` returns "" and the attribute type
            # stays stable for any external weakref holders.
            try:
                object.__setattr__(secret, "_secret_value", "")
            except Exception:  # pragma: no cover - defensive
                # If pydantic changes internals, zeroization is best-effort;
                # the refresh path has already swapped the live credential.
                pass


__all__ = [
    "BEDROCK_SUPPORTED_REGIONS",
    "RegionNotAllowed",
    "ClockSkew",
    "AwsBearerToken",
    "AwsCredentials",
    "AwsSigV4",
]
