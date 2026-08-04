# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Single source of truth for credential scrubbing across Kaizen.

Every credential-scrub site in Kaizen MUST route through this module. Two
independent scrubbers previously guarded two independent surfaces:

* ``kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`` — the
  LLMAgentNode / provider-exception surface (~120 call sites, hardened by
  issues #1960 and #1974).
* ``kaizen.llm.errors.ProviderError.body_snippet`` — the four-axis
  ``LlmClient`` / ``LlmDeployment`` wire surface, fed the FULL provider
  response body at ``kaizen/llm/client.py`` (embeddings + completions) and
  ``kaizen/llm/http_client.py`` (streaming).

The second scrubber's docstring claimed it "mirrors" the first. It did not:
every hardening applied by #1974 (Slack, GitHub PAT, Stripe, URL-embedded
DSN credentials) and #1960 (uppercase hex, AWS 40-char secrets, Perplexity)
was invisible to it, and conversely its own AWS-STS (``ASIA``) and Azure-SAS
(``sig=``) rules were invisible to the first. Both directions leaked.

Two pattern lists that "must agree" is the defect; a shared helper is the
fix. Per ``rules/security.md`` § Credential Decode Helpers, every scrub site
routes through ONE implementation — per-module copies are BLOCKED because
drift between them is guaranteed, not hypothetical.

REGEX SAFETY CONTRACT (read before touching ANY pattern below)
--------------------------------------------------------------
The three URL rules are ORDER-DEPENDENT and their quantifiers are BOUNDED
for DoS reasons that are documented inline at each rule. This module is
reachable from an error path an attacker can influence (a provider echoing
back submitted input), so a quadratic pattern here is a remote CPU-burn
vector, not a micro-optimisation concern. Any new pattern MUST bound its
quantifiers and MUST land with a self-normalising linearity test whose input
does NOT contain ``://`` — an input that matches the scheme immediately is
structurally blind to scheme-prefix backtracking.
"""

from __future__ import annotations

import re
from typing import Final, List

__all__ = [
    "scrub_credentials",
    "DEFAULT_PLACEHOLDER",
]

#: Replacement token used when the caller does not supply one.
DEFAULT_PLACEHOLDER: Final[str] = "[REDACTED]"

# ---------------------------------------------------------------------------
# Vendor-prefixed and shape-anchored credential patterns
# ---------------------------------------------------------------------------
_CREDENTIAL_PATTERNS: List[re.Pattern] = [
    # OpenAI keys (sk-..., sk-proj-...). Greedy, so it spans the whole token
    # and subsumes the more specific sk-proj-/sk-ant- prefixes below.
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.ASCII),
    # Anthropic keys (sk-ant-...)
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}", re.ASCII),
    # Google API keys (AIza...)
    re.compile(r"AIza[a-zA-Z0-9_-]{30,}", re.ASCII),
    # Perplexity keys (pplx-...)
    re.compile(r"pplx-[a-zA-Z0-9]{20,}", re.ASCII),
    # AWS access-key IDs (AKIA + 16 upper-alnum) — Bedrock provider path (#1960).
    re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
    # AWS STS TEMPORARY credentials (ASIA + 16 upper-alnum). Structurally
    # identical to AKIA and equally sensitive — a temporary credential is live
    # until it expires. Previously present ONLY in kaizen/llm/errors.py, so the
    # ~120-site sanitize_provider_error surface leaked it in full; the
    # consolidation lands it at BOTH surfaces per rules/security.md
    # § Enforcement-Surface Parity.
    re.compile(r"ASIA[0-9A-Z]{16}", re.ASCII),
    # Generic hex tokens (32+ chars, common in Azure/other services).
    # #1960: case-INSENSITIVE ([a-fA-F0-9]) — the prior lowercase-only rule let
    # uppercase/mixed-case hex (e.g. "A1B2C3...") slip through unredacted.
    re.compile(r"\b[a-fA-F0-9]{32,}\b", re.ASCII),
    # Slack tokens (#1974). The full `xox[baprse]-` family: bot / app / user /
    # refresh / session / token-rotation. Segment separators ("-") break the
    # 40-char contiguous-run rule below, so no other pattern claims these.
    # The family letter is enumerated (NOT [a-z]) so ordinary hyphenated prose
    # such as "xoxo-..." is not swept up.
    re.compile(r"\bxox[baprse]-[A-Za-z0-9-]{10,}", re.ASCII),
    # Bare (non-"Bearer") JWTs (#1974). The three-segment
    # header.payload.signature structure is what makes this discriminating:
    # "eyJ" is merely base64 for '{"', so ANY base64-encoded JSON object starts
    # with it. Requiring two "."-separated follow-on segments means an ordinary
    # base64 payload in an error string is NOT redacted, while a real token is.
    # Base64URL alphabet ([A-Za-z0-9_-]) — "-"/"_"/"." all break the 40-char
    # contiguous-run rule below, which is why bare JWTs previously slipped.
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", re.ASCII
    ),
    # GitHub PATs / OAuth tokens. Structurally identical to the Slack rule
    # above: an opaque secret behind a fixed vendor prefix whose "_" separator
    # breaks the 40-char contiguous-run rule below. A ``ghp_`` body is exactly
    # 36 chars — four short of the threshold — so nothing previously claimed it.
    # The "_" also defeats the generic-hex rule above (``\b`` cannot fire
    # between "_" and the body), even for an all-hex-alphabet body.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}", re.ASCII),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}", re.ASCII),
    # Stripe secret / restricted keys. The ``sk-`` rule at the top of this list
    # requires a HYPHEN; Stripe spells its prefix with an UNDERSCORE
    # (``sk_live_`` / ``rk_test_``), so the underscore form was never matched
    # and the body is well under the 40-char contiguous-run threshold.
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}", re.ASCII),
    # HuggingFace user access tokens (``hf_`` + ~34 alnum) and Fireworks keys
    # (``fw_`` + ~24 alnum). Both are first-class providers in
    # ``llm/presets.py::_FROM_ENV_PROVIDERS`` (HUGGINGFACE_API_KEY /
    # FIREWORKS_API_KEY), and neither was claimed by ANY rule above:
    #   - the "_" is a word char, so ``\b`` cannot fire before the body, which
    #     defeats the generic-hex rule even for an all-hex body (same mechanism
    #     the ``ghp_`` comment above describes);
    #   - both bodies are under the 40-char contiguous-run threshold.
    # Verified empirically before landing: both shapes passed through
    # scrub_credentials() unredacted.
    re.compile(r"\bhf_[A-Za-z0-9]{30,}", re.ASCII),
    re.compile(r"\bfw_[A-Za-z0-9]{20,}", re.ASCII),
    # Azure storage SAS token (the ``sig=`` query parameter). A SAS token IS a
    # bearer credential for the blob it signs. Previously present ONLY in
    # kaizen/llm/errors.py; landed here so the sanitize_provider_error surface
    # stops leaking it (§ Enforcement-Surface Parity, same as ASIA above).
    #
    # The class admits the percent-encoding alphabet because a SAS `sig` is
    # base64 that has been URL-escaped (`%2F`, `%2B`, `%3D`). Single bounded
    # class after a literal anchor — linear, no adjacent-run ambiguity.
    re.compile(r"sig=[A-Za-z0-9%+/=_\-]{20,}", re.ASCII),
    # AWS 40-char base64 secret access keys ([A-Za-z0-9/+]{40}) — #1960.
    #
    # FALSE-POSITIVE-vs-SENSITIVITY DECISION: we deliberately ACCEPT broad
    # over-redaction here rather than anchor to AWS-secret context. Rationale:
    #   (1) A sanitizer MUST err toward over-redacting secrets — under-redaction
    #       leaks a live credential (the strictly worse failure); over-redaction
    #       only blanks a token in an error string a human still gets the gist of.
    #   (2) A 40+ char contiguous run of [A-Za-z0-9/+] essentially never occurs
    #       in legitimate human-readable error prose (words are space-separated,
    #       ~<=20 chars). The only 40-char contiguous runs are tokens / secrets /
    #       hashes / signed-URL query tokens — all safe (indeed desirable) to
    #       redact. Negative-vector tests confirm normal error text is untouched.
    #   (3) Anchoring to an "aws"/"secret" keyword would MISS a secret that
    #       appears bare in a raw exception string — the common real case.
    # {40,} is greedy, so it spans the whole run (no partial mid-token match).
    re.compile(r"[A-Za-z0-9/+]{40,}", re.ASCII),
    # Bearer tokens in error messages.
    #
    # "=" is in the class because base64 bearer tokens carry "=" padding; the
    # prior class stopped before it and left the padding dangling. The class is
    # disjoint from the preceding ``\s`` run, so the pattern stays linear.
    re.compile(r"Bearer\s+[a-zA-Z0-9._\-=]+", re.ASCII),
    # Partial key exposure (OpenAI style: "sk-tenA...B12C")
    re.compile(r"sk-[a-zA-Z0-9]{3,4}\.\.\.[a-zA-Z0-9]{3,4}", re.ASCII),
]

# ---------------------------------------------------------------------------
# URL-embedded credentials (user:pass@host). ORDER-DEPENDENT — see apply order
# in `scrub_credentials` below.
# ---------------------------------------------------------------------------
#
# #1974: the scheme is ANY RFC-3986 scheme, not just http(s). Connection
# strings for postgres / redis / mongodb / mysql / amqp all embed credentials
# in the same userinfo position, and the prior `https?://` anchor left every
# one of them unredacted. The scheme class `[A-Za-z][A-Za-z0-9+.-]*` also
# covers driver-qualified forms (`postgresql+asyncpg://`, `mongodb+srv://`).
#
# The scheme quantifier is BOUNDED ({0,31}). An earlier revision broadened
# `(https?://)` to an UNBOUNDED `([A-Za-z][A-Za-z0-9+.-]*://)` and measured
# 1773 ms on a 64 KB input with no `://` — the unbounded scheme run backtracks
# at every start position. Do NOT unbound it.
#
# The userinfo quantifiers are `*`, NOT `+`. `redis://:pass@host` — a DSN with
# an EMPTY username — is the conventional redis/rediss shape, and `+` requires a
# non-empty username, so it would leak exactly the vector #1974 gap 1 names.
# `*` costs no precision: the match still requires a literal `:`, a terminating
# `@`, and the scheme prefix, which do not co-occur in a credential-free URL
# (a bare `host:port/path` URL has no `@` to anchor on).
#
# The userinfo character class is `[^\s]`, NOT `[^@\s]`. RFC 3986 requires an
# `@` inside userinfo to be percent-encoded, but real-world DSNs routinely carry
# a literal one in either half (`user:p@ssw0rd@host`, `ad@corp.com:pw@host`).
# Excluding `@` stops the match at the FIRST one and redacts only the prefix,
# leaving the rest of the secret in the output — a partial leak. Because both
# halves are greedy and `\s` still terminates them, the match extends to the
# LAST `@` of the same whitespace-delimited token, so the whole credential goes.
# This trades a little over-redaction for no under-redaction, per the
# false-positive-vs-sensitivity decision documented above.
#
# Both halves are LENGTH-BOUNDED ({0,256}), which is a DoS bound, not a
# coverage one. Two adjacent unbounded greedy runs joined by a literal make the
# no-match case quadratic in token length: on a colon-dense token with no `@`
# the engine retries every `:` against every suffix. Measured on a synthetic
# 32 KB `http://a:a:a:...` string that is O(seconds) of CPU per call on an
# error path an attacker can influence (a provider echoing back user input).
# The bound makes the per-start-position work constant, so the whole scan is
# linear. 256 is ~an order of magnitude above any real DSN userinfo.
#
# The bound alone would leave a COVERAGE HOLE, so it is paired with the
# overflow rule below. (An earlier revision of this comment claimed a longer
# secret "is claimed by the 40-char contiguous-run rule above instead" — that
# is FALSE for any secret containing `-`, `_` or `.`, since those are outside
# `[A-Za-z0-9/+]` and break the run. A 272-char hyphenated DSN password leaked
# in full. Verified, not assumed.)
#
# Group 1 (the scheme) is preserved by the replacement, so no replacement-side
# change is needed for the broadened scheme.
#
# Both halves also exclude the double quote `"`. Whitespace was previously the
# ONLY terminator, and a provider 4xx body is compact JSON with NO whitespace —
# so the whole body is one token and the greedy halves ran from the first
# `scheme://` to the LAST `@` anywhere in it. A body carrying a docs link and a
# contact address collapsed the error message, the docs link AND the JSON
# delimiters into `https://[REDACTED]:[REDACTED]@example.com"}` — destroying
# diagnosability on the exact surface `body_snippet` exists to provide, AND
# leaving the snippet STRUCTURALLY UNPARSEABLE (the swallowed `}` unbalances the
# braces), so a consumer that json-loads it now fails outright.
#
# `"` is safe to exclude because RFC 3986 §3.2.1 defines
#   userinfo = *( unreserved / pct-encoded / sub-delims / ":" )
# and `"` appears in NONE of those productions — not unreserved
# (`ALPHA / DIGIT / -._~`), not a sub-delim (`!$&'()*+,;=`), not `:` — so it can
# never occur unencoded in a well-formed userinfo.
#
# EXACTLY ONE character is excluded, and that is deliberate. An earlier revision
# of this fix excluded `"`, `{`, `}` AND `\` — reasoning that all four are
# RFC-illegal in userinfo, so excluding all four was "free". It was not free, and
# the extra three bought NOTHING:
#
#   * MEASURED: the quote fences the compact-JSON case where the URL and the
#     terminating `@` sit in DIFFERENT string values — the observed shape of a
#     provider error body. The run stops at the field boundary of the value
#     holding the URL, before any `{`/`}`/`\` is reached.
#     NOT "every compact-JSON case": when both sit inside ONE value no boundary
#     intervenes and the match crosses freely (see the residual below). The
#     earlier wording here asserted the general claim from the one body in the
#     suite — an inference in the grammar of a measurement.
#   * MEASURED: excluding `{`, `}`, `\` made `postgresql://u:pa{ss@host/db`,
#     `…pa}ss@…` and `…pa\ss@…` stop matching — the passwords LEAKED IN FULL.
#
# RFC-illegal is NOT the same as "cannot occur". Real deployments carry
# generated passwords with brace and backslash bytes, and lenient drivers accept
# them; a scrubber that only redacts well-formed URLs redacts the wrong set. So
# the test is not "is this byte legal here?" but "does excluding it buy coverage
# I cannot get otherwise?" — and for all three the answer was no.
#
# `,` is excluded for the same reason and additionally IS a legal sub-delim, so
# dropping it would leak `user:pa,ss@host`.
#
# This module trades diagnosability for sensitivity, and where it CANNOT, the
# residual is DOCUMENTED and bounded — never silent. (That wording was an
# unqualified "NEVER the reverse" until a review showed two residuals trading in
# the forbidden direction; an absolute that the code does not hold is worse than
# a stated bound, because it stops anyone looking.) Any
# future widening of this exclusion set MUST first show a compact-JSON case that
# `"` alone does not fence, and MUST re-run the leak probes in
# `test_issue_1974e_compact_json_over_redaction.py::TestRealCredentialsStillRedacted`.
#
# ACCEPTED RESIDUAL — do NOT "fix" this by excluding more characters.
# `"` fences the compact-JSON case where the URL and the later `@` sit in
# DIFFERENT JSON values, which is the shape provider error bodies actually take
# (a docs link in one field, a contact address in another). It does NOT fence
# them inside the SAME string value:
#
#     {"m":"https://a.example.com/p:q/me@y.com"}
#       -> {"m":"https://[REDACTED]:[REDACTED]@y.com"}
#
# That needs a `:` in the URL path AND a later `@` in the same value. It is left
# over-redacting DELIBERATELY: `scheme://<x>:<y>@<host>` is exactly the
# credential shape, and no regex can separate that byte sequence from a real DSN
# without parsing the URL. Over-redaction is the safe side of this module's
# stated trade, so the residual is accepted rather than closed.
#
# Closing it by excluding more characters is the specific error already made
# once here: `{`, `}` and `\` were excluded on the same "RFC-illegal so it is
# free" reasoning and silently leaked every password containing those bytes. If
# this residual ever needs closing, the sound route is a URL PARSE on the
# candidate span — not a wider character class.
# THE FENCE IS THE JSON FIELD BOUNDARY, NOT THE QUOTE CHARACTER.
#
# It models JSON ONLY. A non-JSON body — an HTML/XML attribute boundary such as
# `<a href="https://docs.example.com/p:q">ops@example.com</a>` — closes its
# quote with `>`, which is not in the delimiter set, so the run crosses and
# over-redacts, swallowing the `">` and malforming the tag. Realistic on this
# surface: `body_snippet` carries whatever the provider returned, and gateway /
# WAF / proxy 4xx-5xx responses are routinely HTML.
#
# ACCEPTED: over-redaction is the safe direction. Do NOT close it by adding `>`
# to the delimiter set — that costs a password containing `">`, which is the
# under-redaction residual below.
#
# An earlier revision excluded `"` outright from both halves. That LEAKED: a
# quote anywhere in the userinfo killed the match for the WHOLE credential,
# both halves —
#     postgresql://us"er:s3cr3t@db.internal/db   ->  unchanged, s3cr3t survives
#     postgresql://u:pa"ss@host/db               ->  unchanged, pa"ss survives
# — because the run halted at the quote and could no longer reach the `:` or
# the `@`. Nothing else claimed them either (too short for the vendor-prefix
# and 40-char-run rules).
#
# So the tempered token below stops only at a quote that is followed by a JSON
# STRUCTURAL delimiter — `,` `}` `]` `:` — i.e. a real field boundary. A quote
# in the MIDDLE of a value (`us"er`) is ordinary userinfo and is consumed.
# That fences the compact-JSON crossing (which must traverse `"},"` or `","`)
# while keeping claimable every credential shape whose quote is not IMMEDIATELY
# followed by a JSON delimiter. That qualifier is load-bearing — see the
# under-redaction residual below. An earlier revision of this line claimed
# "every credential shape", which is the same unqualified-generalisation shape
# corrected above, made one revision later in the same file.
#
# UNDER-REDACTION RESIDUAL (F2's class, narrowed — NOT closed).
# A password containing `",` `"}` `"]` or `":` halts both runs and leaks IN
# FULL:
#     postgresql://svcuser:pa",ss@db.internal/app  ->  unchanged, pa",ss survives
# and likewise for the other three pairs, in the overflow rule too. Nothing else
# claims it (6 chars, no vendor prefix, not 32+ hex).
#
# The aperture is ~4/95 of the plain `"` exclusion's per quote occurrence, but
# it is the SAME direction, and this residual is the forbidden one.
#
# DO NOT CHASE IT BY TIGHTENING THE LOOKAHEAD. Requiring the delimiter itself be
# followed by `"` would claim `pa",ss` and still fence `","` — and then a
# password containing `","` leaks, and `"}`/`"]` still leak. That trades one
# aperture for a smaller one indefinitely. A tempered lookahead IS a wider
# character class wearing a lookahead: same failure mode, rarer. The sound route
# is the URL PARSE named in the over-redaction residual below; both residuals
# close together or not at all. Pinned as an xfail-strict vector in
# `test_issue_1974e_compact_json_over_redaction.py` so it self-clears on XPASS
# the moment a parse lands.
#
# Complexity: MEASURED, not assumed. Self-normalising ratio on the documented
# worst case (colon-dense, no `@`) at 1x vs 10x input: 1.0x, i.e. no
# complexity-class regression versus the plain class (1.1x). Absolute cost is
# ~5x higher in microseconds, on an error path. The `{0,256}` DoS bound above
# is unchanged and still does the load-bearing work.
_URL_WITH_AUTH = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]{0,31}://)"
    r'(?:(?!"[,}\]:])[^\s]){0,256}'
    r":"
    r'(?:(?!"[,}\]:])[^\s]){0,256}'
    r"@",
    re.ASCII,
)

# Overflow companion to `_URL_WITH_AUTH` — catches a userinfo LONGER than the
# 256-char DoS bound above (e.g. a Cloud SQL IAM OAuth access token used as the
# DSN password), which that rule's bound would otherwise leak in full.
#
# The FIRST run excludes `:` as well as `@`/whitespace, and that exclusion is
# load-bearing for COMPLEXITY, not for matching. An earlier revision used
# `[^\s@]*:[^\s@]*@` — allowing `:` in the first run — which is QUADRATIC on a
# colon-dense non-matching token: the first run matches to the end, then retries
# against every interior `:`, and for each split the second run rescans the
# tail. Measured on `"http://" + "a:"*n`: 4 KB → 59 ms, 16 KB → 923 ms,
# 64 KB → 14.8 s. Stopping the first run at the FIRST `:` makes the split point
# deterministic, so the scan is linear (same input: single-digit ms).
# Do NOT "simplify" this back to `[^\s@]*` — that reintroduces the DoS.
#
# The `@`-INSIDE-userinfo case is deliberately NOT handled here — the bounded
# rule above already owns it, and secrets long enough to overflow that bound
# overwhelmingly carry no literal `@`.
#
# The `:` is REQUIRED so this stays credential-shaped: without it an ordinary
# `https://example.com/@handle` (a very common profile URL) would be redacted.
#
# Both runs ALSO exclude `"`, for the same reason and on the same RFC 3986
# §3.2.1 grounds as the bounded rule above — see its comment for the full
# derivation, and for why `{`, `}`, `\` and `,` are deliberately NOT excluded
# (they buy no coverage and each one leaks a real password shape).
#
# This companion is the one that ACTUALLY fired on the compact-JSON body: the
# bounded rule alone was fixed first and went clean, yet the over-redaction
# persisted, because this rule's SECOND run (`[^\s@]*`) still crossed the JSON
# string boundary — it walked `…/docs/auth"},"contact"`, took the `:` after
# `"contact"`, then reached the `@` of the contact address. Fixing one pattern
# and not its companion left the defect fully intact, so both MUST carry the
# exclusion; a future edit that relaxes either one re-opens the whole class.
_URL_WITH_AUTH_OVERFLOW = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]{0,31}://)"
    r'(?:(?!"[,}\]:])[^\s@:])*'
    r":"
    r'(?:(?!"[,}\]:])[^\s@])*'
    r"@",
    re.ASCII,
)

# Userinfo with NO password half — `scheme://<token>@host`.
#
# BOTH rules above require a `:`, so a bare token in the USERNAME position was
# never redacted by either. That is the standard shape for git-over-HTTPS with a
# PAT (`https://<token>@github.com/org/repo`) and for APIs that accept a token as
# HTTP-basic username. Only credentials carrying a recognised vendor prefix were
# incidentally caught (by `_CREDENTIAL_PATTERNS`); an opaque token leaked in full.
# Pre-existing — the original `https?://[^@\s]+:[^@\s]+@` required the colon too.
#
# `/` is excluded from the userinfo class so a PATH segment can never be mistaken
# for userinfo: `https://example.com/@handle` (a common profile URL) stops at the
# `/` and does not match, and neither does `git://host/user@thing`.
# Only the scheme is kept — there is no user/pass split to preserve here.
#
# ACCEPTED RESIDUAL (documented deliberately, per the false-positive-vs-
# sensitivity posture above): a userinfo token CONTAINING `/` and shorter than
# 40 chars is NOT claimed — e.g. `https://AbCd+9/xYz123456789@api.example.com`.
# Three reasons this is accepted rather than closed:
#   1. RFC 3986 ends the authority at the first `/`, so a `/` before the `@`
#      means the `@` is in the PATH, not userinfo — the shape is malformed as a
#      URL, not a well-formed credential-bearing one.
#   2. Admitting `/` here would redact `https://example.com/some/path/@handle`,
#      a common and entirely credential-free shape, destroying diagnostics on
#      the far more frequent case.
#   3. A `/`-bearing token of 40+ contiguous `[A-Za-z0-9/+]` IS already claimed
#      by the AWS-secret rule above, so only the short-and-slashed window is
#      open — and base64 secrets in that window are below every provider's key
#      length.
# If a real leak of this shape is ever observed, the correct fix is a
# LENGTH-ANCHORED companion (`[^\s@]{N,}@`), not widening this class.
# Carries the SAME tempered JSON-field-boundary fence as the two rules above.
#
# An earlier revision left this rule alone and claimed it was "proven" not to
# need one. That claim was WRONG, and the test pinning it could not have caught
# the error: both of its vectors were fenced by the `:` in a `"<key>":`
# transition, so it passed whether or not a gap existed
# (`instrument-discipline.md` MUST-1). Its stated mechanism was also wrong —
# it said the run stops at "the first `/` of the path" for a vector that has
# no path at all.
#
# Derived rather than probed: the class `[^\s@:/]` excludes only `:` and `/`,
# so it admits `"`, `,`, `[`, `]`, `{`, `}`. A KEYED transition (`","<key>":`)
# is fenced by its `:`, and a URL with a path is fenced by the `/` — which is
# why the two vectors passed. But an ARRAY transition has no key and no colon,
# and a bare authority has no path, so both crossings were WIDE OPEN:
#     {"eps":["https://example.com","ops@example.com"]}
#       -> {"eps":["https://[REDACTED]@example.com"]}      (element silently lost)
#     {"a":["https://example.com",["ops@example.com"]]}
#       -> {"a":["https://[REDACTED]@example.com"]]}       (UNPARSEABLE)
# The second is exactly the structural-validity loss this module treats as the
# BUG-not-cosmetic half of the W19 finding.
#
# The tempered fence is used here rather than a plain `"` exclusion because a
# plain exclusion would leak a bare token CONTAINING a quote — the same
# under-redaction already made and reverted twice on the rules above. Measured:
# tempered fences both array crossings AND still claims
# `https://tok"en...@host`; the plain exclusion fences the crossings but drops
# that token entirely.
_URL_WITH_USERINFO_ONLY = re.compile(
    r'([A-Za-z][A-Za-z0-9+.-]{0,31}://)(?:(?!"[,}\]:])[^\s@:/])+@', re.ASCII
)

# Azure OpenAI endpoint hostname (#1960). The <resource> subdomain is the
# customer's Azure resource name — sensitive infra identity that reveals the
# tenant. Redact the resource while keeping the ".openai.azure.com" suffix so
# the message still reads as "an Azure OpenAI endpoint".
_AZURE_OPENAI_ENDPOINT = re.compile(
    r"https://[A-Za-z0-9][A-Za-z0-9-]*\.openai\.azure\.com", re.ASCII
)

# Internal file paths that could reveal infrastructure
_INTERNAL_PATH_PATTERNS: List[re.Pattern] = [
    re.compile(r"/home/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"/Users/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"C:\\Users\\[a-zA-Z0-9_-]+\\", re.ASCII),
]

#: Marker substituted for an internal filesystem path.
_PATH_PLACEHOLDER: Final[str] = "[PATH]/"


def scrub_credentials(text: str, *, placeholder: str = DEFAULT_PLACEHOLDER) -> str:
    """Redact every known credential shape from ``text``.

    This is the ONLY credential-scrub implementation in Kaizen. Both
    ``kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`` and
    ``kaizen.llm.errors.ProviderError`` route through it, so a pattern added
    here lands at BOTH surfaces simultaneously — which is the whole point.

    Args:
        text: The raw string to scrub (a provider error message, a response
            body, a log payload). Never mutated.
        placeholder: Replacement token. Callers use distinct markers so the
            originating surface stays identifiable in logs
            (``[REDACTED]`` for the node surface, ``[REDACTED-CRED]`` for the
            ``LlmClient`` wire surface). It MUST NOT contain ``@``, ``://``,
            or whitespace: the URL-rule ordering contract below depends on a
            substituted userinfo remaining un-rematchable.

    Returns:
        ``text`` with every recognised credential shape replaced.

    Raises:
        ValueError: if ``placeholder`` contains ``@``, ``://``, or whitespace,
            which would break the URL-rule ordering contract and could cause a
            substituted value to be re-matched or a match to be missed.
    """
    if (
        "@" in placeholder
        or "://" in placeholder
        or any(c.isspace() for c in placeholder)
    ):
        # Fail loudly rather than silently producing a mis-scrubbed string:
        # a placeholder carrying `@`/`://`/whitespace re-enters the URL rules'
        # match space and the ordering contract below stops holding.
        raise ValueError(
            "placeholder must not contain '@', '://', or whitespace "
            f"(got {placeholder!r}); it would break the URL-rule ordering "
            "contract in scrub_credentials()"
        )

    sanitized = text

    # Vendor-prefixed / shape-anchored credentials first.
    for pattern in _CREDENTIAL_PATTERNS:
        sanitized = pattern.sub(placeholder, sanitized)

    # URL-embedded credentials. The bounded rule runs FIRST because it
    # is the one that handles a literal `@` inside the userinfo; the overflow
    # companion then claims any userinfo too long for that rule's DoS bound.
    userpass_replacement = f"\\1{placeholder}:{placeholder}@"
    sanitized = _URL_WITH_AUTH.sub(userpass_replacement, sanitized)
    sanitized = _URL_WITH_AUTH_OVERFLOW.sub(userpass_replacement, sanitized)
    # Runs LAST: the two user:pass rules above have already rewritten their
    # matches to `scheme://<placeholder>:<placeholder>@`, which contains a `:`
    # and so is not re-matched by this no-colon rule. Ordering therefore keeps
    # the user/pass shape visible where one existed, and only collapses
    # userinfo that genuinely had no password half.
    sanitized = _URL_WITH_USERINFO_ONLY.sub(f"\\1{placeholder}@", sanitized)

    # Redact the resource name in Azure OpenAI endpoints (keep the suffix).
    sanitized = _AZURE_OPENAI_ENDPOINT.sub(
        f"https://{placeholder}.openai.azure.com", sanitized
    )

    # Replace internal file paths.
    for pattern in _INTERNAL_PATH_PATTERNS:
        sanitized = pattern.sub(_PATH_PLACEHOLDER, sanitized)

    return sanitized
