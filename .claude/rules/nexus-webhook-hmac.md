---
priority: 10
scope: path-scoped
paths:
  - "**/nexus/**"
  - "**/webhook*"
  - "**/*hmac*"
  - "**/signature*"
---

# Nexus Webhook HMAC Rules


<!-- slot:neutral-body -->

HMAC webhook signatures verify that the bytes a third-party provider sent (Stripe, GitHub, Slack, Twilio, etc.) are the exact bytes the handler is about to process. The provider computes `HMAC(secret, raw_body)` and sends it in a header; the handler recomputes `HMAC(secret, received_raw_body)` and compares. Any mutation of the body between the provider and the handler — even whitespace-equivalent re-serialization — breaks the signature.

Nexus handlers receive pre-parsed JSON. The raw byte stream is consumed and discarded before the handler runs. HMAC verification computed inside a Nexus handler — over a re-serialized copy of the parsed JSON — is structurally broken: the recomputed body will not match the bytes the provider signed, and verification will fail or (worse) succeed only by coincidence.

This rule mandates that HMAC webhook verification happens OUTSIDE the Nexus handler until raw-body exposure lands, and documents the two acceptable workarounds.

## MUST Rules

### 1. HMAC MUST NOT Be Computed Over Re-Serialized JSON Inside A Nexus Handler

Any Nexus handler that accepts a webhook with an HMAC signature header MUST NOT attempt to verify the signature by re-serializing the parsed JSON body. The verification MUST happen in a layer where the raw byte stream is still available, or via provider-side canonicalization agreement.

```python
# DO — HMAC verified in an ASGI middleware above the Nexus handler
# (the middleware reads request.body() once, verifies, then calls the handler)

from starlette.middleware.base import BaseHTTPMiddleware
import hmac
import hashlib

class StripeHMACMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: bytes):
        super().__init__(app)
        self._secret = secret

    async def dispatch(self, request, call_next):
        if request.url.path == "/webhooks/stripe":
            raw = await request.body()
            provided = request.headers.get("stripe-signature", "").encode()
            expected = hmac.new(self._secret, raw, hashlib.sha256).hexdigest().encode()
            if not hmac.compare_digest(provided, expected):
                return PlainTextResponse("signature mismatch", status_code=401)
            # Stash the raw body so the handler can still parse it
            request.state.raw_body = raw
        return await call_next(request)

# Nexus handler then trusts the middleware-verified request
async def stripe_webhook(payload: dict):
    # handler runs only if middleware verified; no HMAC code here
    return {"ok": True}

# DO NOT — re-serialize parsed JSON inside the handler
import json
async def stripe_webhook(payload: dict, signature: str, secret: bytes):
    body = json.dumps(payload, sort_keys=True).encode()  # NOT the bytes Stripe signed
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401)
    # ↑ signature mismatch on every real Stripe webhook because Stripe's
    # on-wire JSON byte order is not the same as json.dumps(sort_keys=True)
```

**BLOCKED rationalizations:**

- "We'll ask the upstream sender to canonicalize their JSON"
- "All our integrations are internal so canonical form works"
- "json.dumps with sort_keys is a standard canonical form"
- "We can pin the provider's library version so serialization is stable"
- "The handler reformats the JSON the same way the provider does"

**Why:** Provider-signed HMAC verifies exact bytes. Python's `json.dumps` emits a specific but non-standard byte sequence (trailing whitespace, key order, Unicode escaping, number formatting) that no major provider matches. Every real webhook source — Stripe, GitHub, Slack, Twilio, Shopify, PagerDuty — signs their raw on-wire bytes, not a canonical form. A re-serialization approach either silently fails (verification rejects every real webhook) or silently succeeds by coincidence on a subset of payloads and fails on the rest.

### 2. Acceptable Workarounds Are (a) External Middleware Or (b) Proxy-Layer Verification

Until Nexus exposes the raw body to handlers, HMAC webhook handlers MUST use one of:

**Workaround A — ASGI / Tower middleware above Nexus:** The middleware reads the raw body, verifies HMAC, stashes the verified bytes on `request.state`, then invokes the Nexus handler. The handler trusts the middleware's verification.

**Workaround B — Reverse-proxy verification:** A proxy in front of Nexus (nginx with `njs`, Caddy with a plugin, Envoy with an ext_authz filter, Cloudflare Worker) verifies HMAC and rejects unsigned requests at the edge. The Nexus handler assumes every request it sees is already verified.

```python
# DO — middleware-verified, handler trusts verification
app = nexus.App()
app.add_middleware(StripeHMACMiddleware, secret=os.environ["STRIPE_WEBHOOK_SECRET"])

@app.webhook("/webhooks/stripe")
async def stripe_webhook(payload: dict):
    # middleware already verified; handler focuses on business logic
    return handle_stripe_event(payload)

# DO NOT — handler attempts verification inline
@app.webhook("/webhooks/stripe")
async def stripe_webhook(payload: dict, stripe_signature: str):
    # No raw body access here; verification is structurally impossible
    ...
```

**BLOCKED rationalizations:**

- "Middleware is overkill for one webhook endpoint"
- "We can get raw body from the ASGI scope directly in the handler"
- "A Cloudflare Worker adds latency"

**Why:** The workaround is NOT extra infrastructure — it's the correct layer for the check. HMAC verification is an authentication concern; authentication is not a business-logic concern, and putting it in the handler conflates the two. Middleware and proxy are the standard separation; the only reason to put verification in the handler is that the middleware API is unavailable, and in those cases middleware MUST be added.

### 3. Document The Workaround In The Handler's Docstring

Every webhook handler that relies on external HMAC verification MUST state that reliance in its docstring, name the verification layer, and link to the middleware or proxy configuration.

```python
# DO — explicit dependency on the verification layer
@app.webhook("/webhooks/stripe")
async def stripe_webhook(payload: dict):
    """
    Stripe webhook handler.

    HMAC verification: external. See `middleware/stripe_hmac.py` for the
    ASGI middleware that verifies `Stripe-Signature` against
    `STRIPE_WEBHOOK_SECRET` before this handler runs. If that middleware
    is removed, this handler accepts forged Stripe events.
    """
    ...

# DO NOT — silent reliance on external verification
@app.webhook("/webhooks/stripe")
async def stripe_webhook(payload: dict):
    """Process Stripe webhook."""
    ...
# ↑ a later refactor that removes the middleware leaves the handler
#   wide-open; no reviewer signal, no grep target, no safety.
```

**Why:** The handler is the unit of code a reviewer will see when auditing "is this webhook verified?" A docstring that names the verification layer converts the answer from "search the whole app" to a single grep.

## MUST NOT

- Compute HMAC over `json.dumps(payload)` in a Nexus handler and treat that as verification

**Why:** See MUST Rule 1 — no JSON library's byte output matches what real webhook providers sign.

- Accept unsigned webhooks on the grounds that "all senders are internal"

**Why:** "All senders are internal" is true on day 1 and false on day 180. Every webhook endpoint MUST verify at the edge so the verification survives future external integrations without a security-review blast radius.

- Add a Nexus runtime workaround that mutates `request.state` inside the handler

**Why:** Handler-side `request.state` surgery re-implements what middleware is already the correct mechanism for. Re-implementing middleware inside handlers multiplies the surface a reviewer must audit.

## Relationship To Other Rules

- `rules/security.md` § Input Validation — HMAC is the authentication form for webhooks; this rule is the Nexus-specific implementation constraint.
- `rules/zero-tolerance.md` Rule 2 — a handler that "looks like it verifies" but computes HMAC over re-serialized JSON is a fake-security stub.
- `rules/agent-reasoning.md` — the workaround is the explicit intent: verification is externalized, not hidden.

Origin: gh-coc-claude-rs#51 items 1A + 1C (2026-04-17). kailash-rs Nexus handlers receive pre-parsed JSON; `axum::extract::Json` consumes the raw body before the handler runs, and the handler signature accepts only `Query + Json` (no `HeaderMap`, no raw body access). The runtime fix is tracked as the extractor-trait architecture rework at `esperie-enterprise/kailash-rs#404` (D1 Option D — `NexusExtract` trait; shards S1–S8; cross-SDK followup `terrene-foundation/kailash-py#497`). Until S1–S8 land, every HMAC webhook consumer MUST externalize verification per this rule; when the extractor trait ships, this rule will be revised to document the DO pattern using `TypedHeader<HmacSignature> + Bytes`.

<!-- /slot:neutral-body -->
