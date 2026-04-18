# /redteam Round 1 — Security — #498 Session 1 LLM deployment

Scope: `packages/kailash-kaizen/src/kaizen/llm/{deployment,errors,url_safety,presets,client}.py`
and `kaizen/llm/auth/{__init__,bearer}.py`.

Reviewed against threat classes:

1. SSRF bypass (mechanical payload verification)
2. Credential leak paths (logger, repr, dump, deepcopy, pickle)
3. Preset registry injection (factory authorization)
4. Header reflection (forbidden-list completeness)
5. Pydantic parsing attack (nested-dict + `auth: Any`)
6. SecretStr leak through Pydantic dump
7. Timing channel in `constant_time_eq`
8. Error-message log-injection via control chars

## CRITICAL findings

_None._

## HIGH findings

### H1 — SSRF bypass: non-standard IPv4-mapped IPv6 form `[::ffff:0:127.0.0.1]` is NOT classified as IPv4-mapped

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/url_safety.py:85-94`

**Reproduction:**

```python
import ipaddress
ip = ipaddress.IPv6Address("::ffff:0:127.0.0.1")
# str(ip) -> '::ffff:0:7f00:1'
# This is NOT a standard IPv4-mapped (::ffff:a.b.c.d/96) — it sits in
# the IPv4-translated address range ::ffff:0:0:0/96 (RFC 2765).
print(ip.ipv4_mapped)   # -> None  (Python's strict IPv4-mapped check)
print(ip.is_private)    # -> False
print(ip.is_loopback)   # -> False
print(ip.is_reserved)   # -> False  on typical Python stdlib

# Therefore `_is_private_ipv6(ip)` returns False → check_url ACCEPTS this URL.
from kaizen.llm.url_safety import check_url
check_url("https://[::ffff:0:127.0.0.1]/")   # NO exception — BYPASS
```

The guard's IPv4-mapped handling (`_is_private_ipv6` at line 92:
`if ip.ipv4_mapped is not None: return _is_private_ipv4(ip.ipv4_mapped)`)
only triggers for the strict `::ffff:a.b.c.d` form. The IPv4-translated form
`::ffff:0:a.b.c.d` (RFC 2765 SIIT) passes through every check: it is not
literal-loopback IPv6, it is not private by Python's definition, `is_reserved`
depends on stdlib version, and DNS resolution is skipped because the literal
parse succeeded at line 231-234.

Downstream impact: at request time the OS resolver (or the HTTP library's
socket layer) treats the IPv4-translated form as effectively 127.0.0.1 on
many stacks. That is the whole point of RFC 2765.

**Proposed fix:** in `_is_private_ipv6`, also check the range
`::ffff:0:0:0/96` (IPv4-translated) and `64:ff9b::/96` (well-known NAT64)
against `_is_private_ipv4` applied to the embedded IPv4:

```python
_IPV4_TRANSLATED = ipaddress.IPv6Network("::ffff:0:0:0/96")
_NAT64_WELLKNOWN = ipaddress.IPv6Network("64:ff9b::/96")

def _is_private_ipv6(ip: ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    if ip.ipv4_mapped is not None:
        return _is_private_ipv4(ip.ipv4_mapped)
    # Catch RFC 2765 / RFC 6052 embedded-IPv4 forms too.
    for net in (_IPV4_TRANSLATED, _NAT64_WELLKNOWN):
        if ip in net:
            embedded = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
            if _is_private_ipv4(embedded):
                return True
    return False
```

Add an `encoded_ip_bypass`-style reason ("ipv6_embedded_ipv4") to the allowlist.

### H2 — Forbidden-header list is missing request-smuggling + upstream-trust headers

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/deployment.py:104-114`

**Reproduction:**

```python
from kaizen.llm.deployment import ResolvedModel
rm = ResolvedModel(name="gpt-4")
# None of these are rejected:
rm.with_extra_header("Proxy-Authorization", "Bearer attacker-token")   # passes
rm.with_extra_header("X-Forwarded-For", "10.0.0.1, 192.168.0.1")       # passes
rm.with_extra_header("X-Real-IP", "10.0.0.1")                          # passes
rm.with_extra_header("X-HTTP-Method-Override", "DELETE")               # passes
rm.with_extra_header("Transfer-Encoding", "chunked")                   # passes
rm.with_extra_header("Content-Length", "0")                            # passes
```

Consequences:

- **`Proxy-Authorization`** — installs a second credential that a caller
  uploads to the OpenAI egress proxy. A malicious integrator could trick a
  shared proxy into authenticating their traffic as the deployment's tenant.
- **`X-Forwarded-For` / `X-Real-IP`** — if the provider (or any intermediate
  observability / rate-limit layer) trusts these for tenant isolation or
  per-IP rate limiting, the caller can forge the source IP and defeat both.
- **`X-HTTP-Method-Override`** — Rails/Django-style override lets a POST
  masquerade as DELETE; some providers honor it.
- **`Transfer-Encoding` / `Content-Length`** — request-smuggling primitives.
  If a desync occurs between the HTTP library and the upstream proxy, an
  attacker can splice a second HTTP request inside the body.

**Proposed fix:** extend `_FORBIDDEN_EXTRA_HEADERS`:

```python
_FORBIDDEN_EXTRA_HEADERS = frozenset({
    "authorization", "host", "cookie",
    "x-amz-security-token", "x-api-key", "x-goog-api-key",
    "anthropic-version",
    # Request-smuggling primitives
    "transfer-encoding", "content-length",
    # Forged-identity / proxy-trust headers
    "proxy-authorization", "proxy-authenticate",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-real-ip",
    "x-http-method-override", "x-method-override",
    "forwarded",
})
```

Also pin the case-insensitive match with `name.strip().lower()` because the
Python dict API preserves whatever capitalization the caller sent; the
forbidden check uses `.lower()` (good) but `.strip()` is missing — trailing
whitespace (`"Authorization "`) would bypass the allowlist on dicts that treat
the keys as-is. httpx and requests normalize; not every downstream will.

## MED findings

### M1 — `ProviderError.body_snippet` 256-char window is large enough to leak API keys echoed in provider errors

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/errors.py:102-109`

**Reproduction:**

Several LLM providers echo the submitted Authorization header in 4xx error
bodies when the token is malformed (seen with OpenAI, Anthropic, and
third-party wrappers):

```json
{
  "error": {
    "message": "Invalid Authorization header: Bearer sk-proj-abc...xyz"
  }
}
```

A typical sk-proj-\* token is ~130 chars. With the `"Invalid Authorization
header: Bearer "` prefix (~35 chars) and JSON envelope (~30 chars), the whole
key fits under the 256-char ProviderError snippet limit. When the error is
logged or ends up in a Sentry trace, the key is leaked verbatim via
`repr(err)` → `args[0]` → `f"provider error: status={status} body={body_snippet!r}"`.

The docstring says `"The caller is responsible for redaction; this class
performs a final defensive truncation."` — but "responsible for" is not the
same as "enforced". Every call site that forgets to scrub is a leak.

**Proposed fix:** scrub known credential patterns inside `ProviderError.__init__`
defensively:

```python
import re
_CREDENTIAL_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),     # OpenAI
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), # Anthropic
    re.compile(r"AKIA[0-9A-Z]{16}"),           # AWS access key
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.=]{20,}"),
]

def __init__(self, status: int, body_snippet: str = "") -> None:
    for pat in _CREDENTIAL_PATTERNS:
        body_snippet = pat.sub("<redacted-credential>", body_snippet)
    if len(body_snippet) > self._SNIPPET_LIMIT:
        body_snippet = body_snippet[: self._SNIPPET_LIMIT] + "...[truncated]"
    ...
```

### M2 — Pydantic `HttpUrl` normalizes userinfo before the validator sees the string, weakening the userinfo-trick defense

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/deployment.py:82-92`

```python
base_url: HttpUrl

@field_validator("base_url", mode="after")
@classmethod
def _validate_base_url(cls, v: HttpUrl) -> HttpUrl:
    check_url(str(v))     # <-- str(v) after Pydantic normalization
    return v
```

Two related weaknesses:

1. `check_url(str(v))` — Pydantic v2 normalizes `HttpUrl`: it strips the
   default path (`/`) or adds it, canonicalizes IDN, percent-decodes /
   re-encodes certain characters, and emits a different byte-string than
   the one the user passed. `urlparse` on the normalized form can see a
   different `hostname` than what the user intended. Today
   `api.openai.com@127.0.0.1` is caught because `urlparse` on EITHER the
   raw or the normalized form treats `127.0.0.1` as hostname, but the
   decoupling between Pydantic's view of the URL and `check_url`'s view
   leaves an unaudited surface. Any future Pydantic normalization bug, any
   future urlparse divergence, re-opens the gap.

2. `check_url` uses `parsed.hostname` which is lowercased and IDN-normalized
   by urlparse. But if the user passes an IDN homograph
   (`https://аpi.openai.com/` — Cyrillic `а`), Pydantic's HttpUrl accepts
   it, punycode-encodes it (`xn--pi-...`), and `check_url` sees the
   punycode host. The punycode host is not in any metadata / private /
   loopback list, so it passes. The request then goes to the attacker's
   actual domain. This is not a loopback-SSRF bypass per se but it is a
   phishing / mis-routing bypass that the module's SSRF-guard promise
   (rejects "attacker-controlled endpoint") implies it should handle.

**Proposed fix:** (a) call `check_url` BEFORE Pydantic's HttpUrl normalization
by validating the raw input in `mode='before'`:

```python
@field_validator("base_url", mode="before")
@classmethod
def _validate_base_url(cls, v) -> str:
    if not isinstance(v, str):
        v = str(v)
    check_url(v)
    return v
```

(b) reject hostnames that contain any character outside ASCII after
normalization, with an explicit `"unicode_host"` reason. Or require an
explicit opt-in for non-ASCII hosts.

### M3 — `ApiKeyBearer.apply()` raw key lands in request headers without redacting reprs

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/auth/bearer.py:167-184`

```python
def apply(self, request: Any) -> Any:
    header_name = self._header_name()
    header_value = self._header_value()         # 'Bearer sk-...'
    headers = getattr(request, "headers", None)
    if headers is not None and hasattr(headers, "__setitem__"):
        headers[header_name] = header_value
        return request
    ...
```

The raw `Bearer sk-...` value is written into `request.headers`. That is
necessary for the HTTP call. The risk is downstream: `httpx.Request.__repr__`
does NOT redact headers; `requests.PreparedRequest.__repr__` shows the URL
only but application code often does `logger.info(f"sending {req!r}")` or
includes `req.headers` in a structured log for debug. The credentials-on-wire
story is necessarily "trust the HTTP library"; the credentials-in-logs story
is where the `apply()` contract should add a hook.

Secondary: `ApiKeyBearer.__repr__` (line 194-199) is safe, but nothing in
`apply()` marks the resulting request object as "contains-credentials" so a
generic log-formatter later cannot skip it.

**Proposed fix:** document the pattern in a top-level caution (implementation
only lands in S2+, but record the contract now):

```python
def apply(self, request: Any) -> Any:
    """...
    SECURITY: mutates `request.headers` with the raw API key. Callers MUST
    NOT log `repr(request)` after `apply()` — the HTTP library may expose
    headers in its repr. Log the request BEFORE calling apply, or tag the
    request with `request._credentials_installed = True` and skip it in the
    formatter.
    """
```

And add a defensive marker:

```python
if headers is not None and hasattr(headers, "__setitem__"):
    headers[header_name] = header_value
    try:
        setattr(request, "_credentials_installed", True)
    except Exception:
        pass
    return request
```

### M4 — `register_preset` has no authorization gate; any import-time import of a downstream module can overwrite a preset

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/presets.py:88-102`

The docstring notes this is "defense against insiders" — but there is also
no check that `name` is not a reserved preset. `register_preset("openai",
malicious_factory)` is rejected only because `_PRESETS["openai"]` already
exists (line 98) — but any session where `openai` has not yet been
registered (e.g., import-order-sensitive code, mocked test setups, workers
that lazy-import presets) lets a malicious module register its own
`openai`. The current import order at module load time closes this in
practice (`register_preset("openai", openai_preset)` runs on first import
of `kaizen.llm.presets`), but nothing in the type system prevents a
downstream from importing `kaizen.llm.presets._PRESETS` and mutating it.

**Proposed fix:** mark the internal registry with a module-level guard
(`_PRESETS: Mapping[...]` via `types.MappingProxyType` to make it read-only
for consumers), and split "core presets (ship-locked)" from "community
presets" (runtime-registered with different namespace). Also:
`register_preset("openai", ...)` should fail with a specific error
("`openai` is a reserved core preset; use the `community_` prefix") rather
than the generic "already registered" ValueError.

### M5 — `_detect_encoded_ip_bypass` does not catch all inet_aton decimal + mixed-base forms

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/url_safety.py:128-155`

The current detector covers:

- all-digits: `2130706433`
- any part starting `0x` / `0X`
- any part starting `0` + additional digits (octal)

But `inet_aton` also accepts:

- **Dotted-decimal with fewer than 4 parts** (`127.1` → 127.0.0.1, `127.0.1`
  → 127.0.0.1). Both resolve correctly by libc. Current detector: `parts =
host.split('.')` splits `"127.1"` into `["127", "1"]`; neither starts with
  `0` or `0x`, neither matches `isdigit()` check (which runs only when the
  whole string has no dots). Passes → reaches DNS resolution → DNS fails for
  `127.1` (not a resolvable name on most systems) → `resolution_failed` →
  rejected. OK TODAY — but an adversary controls their resolver for their
  own hostname; the libc path gets invoked for direct socket connections
  the HTTP library might make.
- **Mixed-base in a single part**: `0x7f.1` (hex 127 + decimal 1). First
  part starts `0x` → caught. ✓
- **Trailing-dot tricks**: `0177.0.0.1.` — the trailing `.` is legitimate
  FQDN; `_detect_encoded_ip_bypass` sees `parts = ["0177", "0", "0", "1",
""]` → `"0177"` starts with `0` and has more digits → REJECTED. ✓
- **IPv6 zone-id**: `fe80::1%eth0` — hostnames with `%` embedded. urlparse
  behavior on zone-id URLs is inconsistent across Python versions; worth a
  test.

Verified-bypass-class: **`https://127.1/v1`** and **`https://127.0.1/v1`**.
Today these escape `_detect_encoded_ip_bypass` but fail DNS resolution. If
a future `check_url` caller passes `resolve_dns=False` (test knob, currently
gated to tests but may leak), the bypass is live.

**Proposed fix:** tighten `_detect_encoded_ip_bypass` to reject any hostname
where ALL dot-separated parts are numeric and `len(parts) < 4` — the two
conditions together match the inet_aton short-form space without
false-positives on real hostnames:

```python
if all(p.isdigit() for p in parts) and 1 < len(parts) < 4:
    return True
```

## LOW findings

### L1 — `copy.deepcopy(api_key)` and `pickle.dumps(api_key)` expose the raw key

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/auth/bearer.py:45-97`

Verified: `ApiKey` has `__slots__ = ("_secret", "_fingerprint")`. Standard
library `copy.deepcopy` + `pickle.dumps` serialize the `_secret: SecretStr`
which internally stores the raw value in `_secret_value`. So an `ApiKey`
round-tripped through deepcopy/pickle retains the raw key — and any process
that imports the pickled blob learns the key.

This is mostly expected (the secret MUST be usable), but the public-API
docstring promise "a future reviewer shouldn't find a back door to the
credential" (from `errors.py::Invalid.__init__`) implies a higher bar than
what `ApiKey` actually provides. Two concrete hardenings:

- Override `__reduce__` to refuse pickling: `raise TypeError("ApiKey refuses
pickling; construct a new instance from the secret store at each node")`.
- Override `__deepcopy__` to refuse: `raise TypeError("ApiKey refuses
deepcopy; construct a new instance")`.

This forces credentials to be re-loaded from the source of truth on each
process boundary, which is the correct behavior for any secret rotation
scheme. Marked LOW because the current signature doesn't explicitly promise
"unpicklable"; it only promises "no back door via args / repr".

### L2 — `ApiKey.fingerprint` is 16 bits of entropy (4 hex chars) — collisions across a 1000-key rotation are plausible

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/auth/bearer.py:68`

4 hex chars = 65536 buckets. A 1000-key rotation has ~birthday-paradox
collision probability ~`1 - exp(-1000*1000 / (2 * 65536))` ≈ 99.96% — two
different keys will share a fingerprint with near-certainty. At that point
forensic correlation ("key fingerprint=abcd was rejected 3x in 30s")
becomes ambiguous.

For a single-tenant deployment with a handful of keys this doesn't matter.
At multi-tenant scale (one kailash-kaizen instance serving many BYOK
customers), the fingerprint becomes useless for correlation.

**Proposed fix:** extend to 8 hex chars (32 bits) to match the cross-SDK
PK-fingerprint contract used in `rules/event-payload-classification.md`.
The cross-SDK hash prefix should be 8 hex chars uniformly.

### L3 — `InvalidEndpoint.reason` is allowlisted, but `Invalid` (auth credential rejected) stores `_fingerprint` only — no way to correlate to the upstream rotation

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/errors.py:131-146`

The docstring "A unit test in `tests/unit/llm/test_apikey.py` asserts both
methods are absent" — good for the constant-time contract — but the
reconcile story is: `Invalid.fingerprint` is 4 chars, `ApiKey.fingerprint`
is 4 chars, but they are computed from DIFFERENT inputs. `Invalid(raw)`
hashes `raw`; `ApiKey(raw).fingerprint` hashes `raw`. The same `raw` →
same fingerprint. OK. But an ApiKeyBearer's `fingerprint` (via
`ApiKeyBearer.__repr__`) reads `self.key.fingerprint` which is the 4-char
hash. Consistent. So actual correlation IS possible via the 4-char hash —
but at the low entropy of L2, the correlation breaks above ~200 keys.

Same fix as L2.

### L4 — `check_url` logs `resolution_failed` at DEBUG with only a "reason" tag — no fingerprint

**File:** `/Users/esperie/repos/loom/kailash-py/packages/kailash-kaizen/src/kaizen/llm/url_safety.py:273-276`

```python
logger.debug(
    "url_safety.resolution_failed",
    extra={"reason": "resolution_failed"},
)
```

If an operator wants to audit "how many distinct attacker hostnames failed
resolution in the last hour", this log line gives no hostname fingerprint —
only the reason code. Every failed-resolution event looks identical. This
breaks the log-level-1-triage ability to detect "attacker is iterating
through a hostname list".

**Proposed fix:** attach a fingerprint (same `_fingerprint(url)` helper
from `errors.py`) to the DEBUG line:

```python
logger.debug(
    "url_safety.resolution_failed",
    extra={"reason": "resolution_failed", "host_fingerprint": _fingerprint(host)},
)
```

## Green

- **SSRF payload: `https://127.0.0.1.nip.io/`** — verified rejected. DNS
  resolves to 127.0.0.1; `_is_private_ipv4` flags; `_ip_reason` returns
  `"loopback"`; `InvalidEndpoint("loopback", raw_url=url)` raised. ✓
- **SSRF payload: `https://api.openai.com@127.0.0.1/`** — verified rejected.
  `urlparse.hostname` returns `127.0.0.1` (the `api.openai.com` lives in
  `.username`), literal-IP check flags loopback, rejected. ✓
- **SSRF payload: `https://0/v1`** — verified rejected.
  `_detect_encoded_ip_bypass("0")` returns True via `host.isdigit()`. ✓
- **SSRF payload: `https://[::]/v1`** — verified rejected.
  `ipaddress.IPv6Address("::")` has `is_unspecified=True`;
  `_is_private_ipv6` returns True. ✓
- **Preset name log-injection via CRLF / Unicode / null-byte** — `_PRESET_NAME_RE`
  rejects; error message uses only a 4-char fingerprint. ✓
- **InvalidEndpoint reason CRLF injection** — the reason allowlist at
  `_REASON_ALLOWLIST` (errors.py:187-199) contains only string literals
  with no control chars; any non-allowlisted reason is coerced to
  `"malformed_url"` before reaching `super().__init__`. CRLF cannot reach
  the log line. ✓
- **`ApiKey.__eq__` / `__hash__` absence** — both methods absent from the
  class definition; `ApiKey(a) == ApiKey(b)` falls back to object identity
  (always False for distinct instances). ✓
- **`hmac.compare_digest` is actually called in `constant_time_eq`** —
  line 90: `return hmac.compare_digest(a, b)`. Not a Python-level `==`. ✓
- **SecretStr in Pydantic dump** — `ApiKey` is NOT a pydantic model and
  `ApiKeyBearer` uses `arbitrary_types_allowed=True`, so `LlmDeployment.
model_dump_json()` does NOT introspect `ApiKey._secret` (Pydantic
  serializes arbitrary types as their repr or skips them depending on
  the serializer mode). ✓ — with caveat that a future change to make
  `ApiKey` a BaseModel would need explicit `SecretStr` dump-handling.
- **`LlmDeployment.auth: Any` nested-dict attack** — even if a caller
  passes `LlmDeployment.model_validate({"auth": {...}})`, the resulting
  `d.auth` is a plain dict, not a callable; `d.auth.apply(request)` would
  raise `AttributeError: 'dict' has no 'apply'` before any malicious code
  runs. Typed `Any` is safe in the sense that it defers validation to
  call-time rather than allowing type-confusion injection. ✓
- **`register_preset` duplicate rejection** — line 98-101 raises on
  duplicate name, preventing silent shadowing. ✓
- **Error messages never echo raw URL verbatim** — `InvalidEndpoint`
  always logs `reason` + optional `url_fingerprint`, never the raw URL. ✓
- **`MissingCredential.source_hint` doc note** — docstring pins the hint
  to a constant chosen by the loader, not a user-supplied string. ✓
