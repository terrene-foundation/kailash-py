# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Single source of truth for credential scrubbing across Kaizen.

Every PROVIDER-ERROR credential-scrub site in Kaizen MUST route through this
module.

SCOPED DELIBERATELY, because the unqualified form was FALSE. A third
credential-pattern list exists at
``kaizen/core/autonomy/hooks/security/redaction.py``
(``SensitiveDataRedactor.PATTERNS``), it is REACHABLE — exported from
``hooks/security/__init__.py`` and used by ``hooks/builtin/logging_hook.py``,
i.e. it sits on a LOGGING path — and it has drifted from this module on 9 of 10
measured vendor shapes, catching only the ``sk-`` form. AKIA, ASIA, ghp_, hf_,
fw_, xoxb-, sk_live_, sig= and URL-embedded DSNs all pass it unredacted.

That is the same failure this module was created to fix, one surface over, and
the unqualified sentence made it invisible by asserting it could not exist.
Routing that list through here is a real change on a hook path and belongs in
its own shard; scoping the claim is what stops the prose lying in the meantime. Two
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
The three URL rules are ORDER-DEPENDENT and each is LINEAR for DoS reasons
documented inline at that rule — but by two DIFFERENT mechanisms, and the
distinction matters if you add a rule. ``_URL_WITH_AUTH`` is BOUNDED
(``{0,256}`` on both runs). ``_URL_WITH_AUTH_OVERFLOW`` and
``_URL_WITH_USERINFO_ONLY`` are UNBOUNDED (``*`` / ``+``) and get their
linearity from a DETERMINISTIC SPLIT POINT instead — the overflow rule's first
run excludes ``:``, so the split cannot float. An earlier version of this
paragraph said all quantifiers were bounded, which two of the three contradict;
the inline comments were right and the summary was not. This module is
reachable from an error path an attacker can influence (a provider echoing
back submitted input), so a quadratic pattern here is a remote CPU-burn
vector, not a micro-optimisation concern. Any new pattern MUST bound its
quantifiers OR establish a deterministic split point, and MUST land with a
self-normalising linearity test whose input does NOT contain ``://`` — an input that matches the scheme immediately is
structurally blind to scheme-prefix backtracking.

A LINEARITY TEST MUST ALSO REACH THE QUANTIFIER IT CLAIMS TO MEASURE, and that
is a SEPARATE requirement from the one above. ``_COMMA_BEARING_RUN`` shipped
with a probe whose payload could not enter it: the units were ``password=,``
and ``password:,``, and this rule's leading atom EXCLUDES ``,``, so the
alternative failed at its first character at every offset and the
``(?:,+...)+`` group was never entered at all. The timing assertion returned
the same verdict whether the group was linear or quadratic — a check that
cannot discriminate is not evidence (``rules/instrument-discipline.md``
MUST-1). Every linearity unit MUST therefore carry an ENTRY assertion — the
pattern's match on the payload must actually span the construct under test —
and the probe MUST include the FAILING path (a payload that reaches the
quantifier and then fails), because a quantifier that always succeeds never
backtracks and so is measured by nothing.
"""

from __future__ import annotations

import re
from typing import Final, List

__all__ = [
    "scrub_credentials",
    "scrub_local_error",
    "scrub_remote_error",
    "DEFAULT_PLACEHOLDER",
]

# NOTE: ``__all__`` is the SUPPORTED surface, but three underscore-prefixed
# patterns — ``_URL_WITH_AUTH``, ``_URL_WITH_AUTH_OVERFLOW`` and
# ``_URL_WITH_USERINFO_ONLY`` — are imported CROSS-MODULE by
# ``nodes/ai/error_sanitizer.py``. They are de-facto public API wearing private
# names, so a rename here is a silent break there rather than the local edit the
# underscore implies. Recorded rather than renamed: promoting them would widen
# the supported surface, which is a decision, not a cleanup.

#: Replacement token used when the caller does not supply one.
DEFAULT_PLACEHOLDER: Final[str] = "[REDACTED]"

# ---------------------------------------------------------------------------
# SHAPE-ONLY rules (gated by ``redact_opaque_tokens``)
# ---------------------------------------------------------------------------
# The two rules below are the ONLY entries in ``_CREDENTIAL_PATTERNS`` that
# discriminate on SHAPE ALONE — a run of the right characters at the right
# length, with no vendor prefix, no protocol literal, and no credential-
# announcing context. Every other entry is anchored on a literal that only
# appears where a credential does (``sk-``, ``AKIA``, ``ghp_``, ``Bearer ``,
# ``sig=``, ``eyJ<hdr>.<payload>.<sig>``, …).
#
# That distinction is what the ``redact_opaque_tokens`` flag switches on. It is
# NOT a quality ranking: on the provider-error surface these two rules are
# load-bearing (a bare AWS secret carries no prefix), which is why they are ON
# by default. They are separable because on a LOCAL-error surface the same
# shapes are overwhelmingly git SHAs, MD5 digests, unhyphenated UUIDs and long
# CamelCase identifiers — see
# ``tests/regression/test_scrub_credentials_ordinary_text_is_not_noop.py``.
#
# They are hoisted OUT of the list literal purely so they can be named. Their
# positions inside ``_CREDENTIAL_PATTERNS`` are UNCHANGED, and that matters:
# the list is applied in order and the order is load-bearing (``sk-<40 alnum>``
# is claimed WHOLE by the ``sk-`` rule at index 0; if the 40-char run rule ran
# first it would claim only the body, yielding ``sk-[REDACTED]``).

# Generic hex tokens (32+ chars, common in Azure/other services).
# #1960: case-INSENSITIVE ([a-fA-F0-9]) — the prior lowercase-only rule let
# uppercase/mixed-case hex (e.g. "A1B2C3...") slip through unredacted.
_GENERIC_HEX_TOKEN: Final[re.Pattern] = re.compile(r"\b[a-fA-F0-9]{32,}\b", re.ASCII)

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
#
# Reason (2) is TRUE FOR ERROR PROSE and FALSE for identifiers: a full 40-hex
# git SHA and a long CamelCase class name are both 40+ contiguous runs, and
# both occur constantly in LOCAL orchestration errors. That is precisely the
# surface split ``redact_opaque_tokens`` exists to express.
_AWS_SECRET_CONTIGUOUS_RUN: Final[re.Pattern] = re.compile(
    r"[A-Za-z0-9/+]{40,}", re.ASCII
)

#: Key names that ANNOUNCE their value as a secret. Shared by the two
#: ``key=value`` rules below so the vocabulary cannot drift between them.
#:
#: EVERY ALTERNATIVE IS A COMPLETE KEY, because the sub-pattern ends in a
#: MANDATORY separator (``["']?\s*[=:]``). That is why a prefix already in the
#: list does NOT cover a longer key built on it, and it is the whole reason
#: ``secret[-_]?key`` and ``passphrase`` had to be added rather than being
#: redundant with the ``secret`` and ``passwd|password|pwd`` already here:
#:
#:   ``secret_key=<v>`` — the ``secret`` alternative matches its six
#:   characters and then meets ``_``, which is neither ``=`` nor ``:``, so the
#:   key-name match FAILS. It fails at every other start offset too, because
#:   nothing in the alternation matches a bare ``key`` (``api[-_]?key``,
#:   ``session[-_]?key`` and ``encryption[-_]?key`` each require their own
#:   prefix). Verified empirically before this edit, not assumed: the compiled
#:   sub-pattern returned NO MATCH on ``secret_key=``, ``secret-key=`` and
#:   ``secretkey=``, and the value leaked IN FULL through BOTH presets.
#:
#:   ``passphrase=<v>`` — ``pass`` is not an alternative at all, and
#:   ``passwd`` / ``password`` diverge at the fifth character (``w`` vs ``p``).
#:   Also verified NO MATCH, also leaking through both presets.
#:
#: Both are ordinary spellings on this surface: ``SECRET_KEY`` is the Django /
#: Flask signing key and a common env-var name, and ``passphrase`` is what a
#: private key, a keystore and an SSH agent all call theirs — so both reach an
#: error string through the same env-dump and config-repr shapes the rest of
#: this vocabulary exists for.
#:
#: LONGER LITERAL FIRST (``secret[-_]?key`` ahead of ``secret``), matching the
#: ``(?i:signature|sig)=`` rule's convention below. Python's alternation is
#: leftmost-FIRST rather than longest-match, so it would also reach the right
#: verdict by backtracking out of the shorter alternative; ordering it this way
#: makes the intent legible instead of incidental.
#:
#: ADDED AS ALTERNATIVES, NOT AS A WIDENED CHARACTER CLASS, and that shape is
#: forced by the same ReDoS argument ``_COMMA_BEARING_RUN`` records below. Each
#: new alternative is a literal (plus one BOUNDED ``[-_]?``), so it costs O(1)
#: per start offset and introduces no quantifier that can interact with the
#: value part's runs. The tempting "just let the key run to the separator"
#: form — e.g. ``secret[\w-]*`` — is exactly the widened class that argument
#: rejects: it makes the key/separator boundary float and it would newly claim
#: unrelated prose such as ``secret_scanning_enabled: false``.
_CREDENTIAL_KEY_NAMES: Final[str] = (
    r"[\"']?(?i:passwd|password|passphrase|pwd|secret[-_]?key|secret|"
    r"api[-_]?key|apikey|"
    r"access[-_]?token|refresh[-_]?token|id[-_]?token|"
    r"client[-_]?secret|auth[-_]?token|private[-_]?key|"
    r"session[-_]?key|encryption[-_]?key)[\"']?\s*[=:]\s*[\"']?"
)

#: ``password=<secret-shaped value>`` — safe under BOTH presets, because the
#: key announces a secret AND the value looks like one. "Looks like one" is
#: EITHER of two discriminators, and it takes both to separate secrets from
#: prose without losing either:
#:
#:   1. contains a digit or token punctuation (``-_./+=``) — ``hunter2longenough``,
#:      ``aB3-xY9_qq77``, ``dXNlcjpwYXNzd29yZA==``; or
#:   2. is at least 16 characters — catches a PURE-ALPHABETIC key such as
#:      ``api_key=abcdefghijklmnopqrst`` (a real issued-key shape), which
#:      discriminator 1 alone misses.
#:
#: Length is what separates a pure-alpha secret from a pure-alpha word: real
#: issued keys run 20+ chars, while the prose that appears after one of these
#: key names is short (``unavailable`` 11, ``expected`` 8, ``Optional[str]`` 13).
#:
#: The lookahead is what earns this rule a place OUTSIDE
#: ``_OPAQUE_SHAPE_PATTERNS``. Without it (the original single-rule form) the
#: value class ``[^\s"',;&]{6,}`` constrained nothing and matched prose, so
#: ``secret: unavailable`` and ``api_key: Optional[str]`` were blanked ENTIRELY
#: and ``invalid value for 'api_key': expected string`` lost its type
#: information — a diagnosability regression at ~180 conservative-preset sinks
#: whose text an AGENT reads to decide its retry, which is the precise cost
#: ``redact_opaque_tokens=False`` exists to avoid.
#: A COMMA IS A VALUE CHARACTER, NOT ALWAYS A TERMINATOR — and treating it as
#: only a terminator was a hole in BOTH presets, not just this one.
#:
#: The value class used to exclude ``,``, so ``password=ab,cdefghij`` matched
#: only ``ab``. Two characters fails the ``{6,}`` floor, so the token rule
#: below did not match AND the prose rule did not match: a password containing
#: a comma leaked IN FULL through the conservative preset AND through the
#: aggressive one. The length floor was measuring a truncated prefix rather
#: than the value.
#:
#: The fix is an ADDITIONAL alternative, not a widened character class, and
#: that shape is forced by ReDoS rather than chosen for tidiness. Letting ``,``
#: into the existing run and requiring the run not to END with one
#: (``[^\s"';&]{5,}[^\s"';&,]``) is the obvious form and is QUADRATIC: on a
#: comma-dense input the greedy ``{5,}`` swallows the commas and then
#: backtracks one position at a time looking for a non-comma tail, at every
#: start offset. This module's own linearity regressions caught it. A scrubber
#: runs on every error path, so a complexity regression here is worse than the
#: leak it closes.
#:
#: ``_COMMA_BEARING_RUN`` is DETERMINISTIC instead: ``,`` is excluded from the
#: run atom, so each character belongs to exactly one class and there is no
#: ambiguity for the engine to explore. The trailing ``+`` on the group (not
#: ``*``) means this alternative matches ONLY runs with an internal comma —
#: which is also precisely the new capability, so it cannot change the verdict
#: on any input the pre-existing rule already handled.
#:
#: A trailing comma is still not part of the value: ``secret: unavailable,
#: retrying`` cannot match this alternative (no comma with run characters
#: after it), so prose stays diagnosable — the ~180-sink regression the
#: lookahead exists to avoid.
#:
#: DOCUMENTED RESIDUAL — THIS ALTERNATIVE OVER-REDACTS, DELIBERATELY.
#:
#: When it fires it consumes to the end of the comma-joined token, so a
#: comma-separated FIELD LIST after a credential key loses every field, not
#: just the secret::
#:
#:     password=abc,user=bob,host=dblocal   ->   [REDACTED]
#:
#: That is a real diagnosability cost on the conservative preset, which is the
#: cost ``redact_opaque_tokens=False`` exists to avoid, so it is a decision and
#: is recorded as one rather than left for the next reader to "fix".
#:
#: IT IS NOT BOUNDABLE. Once the key has announced a secret, ``ab,cdefghij``
#: (a password containing a comma — the leak this alternative was added to
#: close) and ``abc,user=bob`` (a short value followed by a field list) are the
#: SAME STRING SHAPE. Bounding the run means guessing where the value ends, and
#: a wrong guess UNDER-redacts a live credential. Under-redaction leaks;
#: over-redaction blanks text a human still gets the gist of. The module
#: already takes that trade explicitly at ``_AWS_SECRET_CONTIGUOUS_RUN`` and
#: takes it again here, for the same reason and in the same direction.
#:
#: TWO PRE-EXISTING BOUNDS ALREADY CONTAIN THE BLAST RADIUS, and both are
#: pinned by tests so a future edit cannot quietly widen them:
#:
#:   1. ALTERNATION ORDER. The token rule's alternatives are tried in order and
#:      the FIRST one wins, so whenever the pre-comma segment is ITSELF
#:      secret-shaped the earlier alternative claims it and stops at the comma:
#:      ``password=hunter2,user=bob`` -> ``[REDACTED],user=bob``. This
#:      alternative therefore only reaches a field list in the case where the
#:      announced value is NOT secret-shaped — i.e. exactly the case where the
#:      rule cannot tell whether the comma is inside the value.
#:   2. NO WHITESPACE. The run atom excludes whitespace, so the ordinary
#:      ``key=value, key=value`` spelling (comma SPACE) does not match at all:
#:      ``password=xyz, user=bob`` is untouched. The residual needs a
#:      comma-separated list written with no spaces.
#:
#: WHY THIS ALTERNATIVE RESISTS CATASTROPHIC BACKTRACKING — THREE INDEPENDENT
#: REASONS, and only the first was previously recorded. Stated because four
#: separate attempts to mutate this construct into a quadratic one were INERT,
#: and a reader who does not know why will mistake that for a blind test:
#:
#:   a. DISJOINT CLASSES. ``,`` is excluded from the run atom, so each
#:      character belongs to exactly one class and the run/separator boundary
#:      cannot float. (The reason this file already gave.)
#:   b. NO MANDATORY TAIL. Nothing is required AFTER ``(?:,+A+)+``. A regex
#:      engine backtracks catastrophically only when it must EXHAUST a search
#:      to prove failure; here the alternative succeeds the moment the group
#:      matches once, so there is no exhaustive failure to drive. Adding a
#:      mandatory element after the group would remove this property — the
#:      same construct WITH a trailing literal measures ~30x per added run
#:      character (k=15 -> 2 ms, k=25 -> 2.2 s) while this one stays flat.
#:   c. THE FAILING PATH IS LENGTH-CAPPED BY ALTERNATION ORDER. When the group
#:      cannot match, the engine backtracks the leading ``A+`` — but ``A+`` is
#:      capped at 15 characters here, because alternative 1's ``{16,}``
#:      lookahead claims any comma-free run of 16 or more BEFORE this
#:      alternative is tried. Measured at the boundary: a 15-char pure-alpha
#:      value reaches this alternative and fails; a 16-char one is claimed by
#:      alternative 1 and never arrives.
#:
#: (b) and (c) are load-bearing and NOT self-evident from this line. An edit to
#: alternative 1's ``{16,}`` lookahead would silently remove (c) without
#: touching this pattern at all, which is why the boundary is pinned by a test.
_COMMA_BEARING_RUN: Final[str] = r"[^\s\"';&,]+(?:,+[^\s\"';&,]+)+"

#: Six run characters, counted with a FIXED repetition rather than a greedy
#: star, so the floor costs O(1) per start offset.
_MIN_VALUE_FLOOR: Final[str] = r"(?=[^\s\"';&]{6})"

_CREDENTIAL_KEYVALUE_TOKEN: Final[re.Pattern] = re.compile(
    _CREDENTIAL_KEY_NAMES
    + r"(?:"
    + r"(?=[^\s\"',;&]*[0-9\-_./+=]|[^\s\"',;&]{16,})[^\s\"',;&]{6,}"
    + r"|"
    + _MIN_VALUE_FLOOR
    + _COMMA_BEARING_RUN
    + r")",
    re.ASCII,
)

#: ``password=<any 6+ run>`` — the ORIGINAL unconstrained form, retained so a
#: pure-alphabetic secret (``password=hunterpassword``) is still caught. It CAN
#: match credential-free prose, so per this module's own contract (see
#: ``_OPAQUE_SHAPE_PATTERNS`` below) it is classified shape-only and is
#: therefore AGGRESSIVE-PRESET ONLY — on the provider-error surface, where
#: over-redaction is the documented and correct trade.
_CREDENTIAL_KEYVALUE_PROSE: Final[re.Pattern] = re.compile(
    _CREDENTIAL_KEY_NAMES
    + r"(?:"
    + r"[^\s\"',;&]{6,}"
    + r"|"
    + _MIN_VALUE_FLOOR
    + _COMMA_BEARING_RUN
    + r")",
    re.ASCII,
)

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
    # SHAPE-ONLY — defined above, gated by ``redact_opaque_tokens``. Position
    # in this list is unchanged; only the definition moved.
    _GENERIC_HEX_TOKEN,
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
    #
    # THE LITERAL IS CASE-INSENSITIVE AND ALSO SPELLS OUT ``signature``. It was
    # ``sig=`` alone, case-SENSITIVELY, which matches neither the AWS SigV4
    # query parameter ``X-Amz-Signature=`` nor any ``Signature=`` / ``SIG=``
    # spelling. That gap is worst under the CONSERVATIVE preset
    # (``scrub_local_error``), where the shape-only rules that would otherwise
    # have incidentally claimed a long signature value are switched OFF — so
    # this literal-anchored rule was the only thing standing between a
    # signed-URL credential and the log, and it did not fire.
    #
    # ``(?i:...)`` scopes the case-insensitivity to the LITERAL only; the value
    # class already admits both cases, so nothing else changes. Deliberately NOT
    # ``\b``-anchored: adding one would NARROW the pre-existing rule (it would
    # stop matching a ``…mysig=`` suffix that matches today), and this is a
    # widening. ``signature`` is listed FIRST so the longer literal is preferred.
    re.compile(r"(?i:signature|sig)=[A-Za-z0-9%+/=_\-]{20,}", re.ASCII),
    # SHAPE-ONLY — defined above, gated by ``redact_opaque_tokens``. Position
    # in this list is unchanged; only the definition moved.
    _AWS_SECRET_CONTIGUOUS_RUN,
    # Bearer tokens in error messages.
    #
    # "=" is in the class because base64 bearer tokens carry "=" padding; the
    # prior class stopped before it and left the padding dangling. The class is
    # disjoint from the preceding ``\s`` run, so the pattern stays linear.
    re.compile(r"Bearer\s+[a-zA-Z0-9._\-=]+", re.ASCII),
    # HTTP Basic auth. The sibling of the ``Bearer`` rule directly above, and
    # its absence was a plain omission rather than a decision: a
    # ``Authorization: Basic dXNlcjpwYXNzd29yZA==`` header echoed into an error
    # message passed through BOTH presets IN FULL, and base64 of
    # ``user:password`` is a reversible credential, not a digest.
    #
    # Case-insensitive on the literal only (``(?i:...)``), matching the
    # ``signature|sig`` rule's convention — ``basic`` / ``BASIC`` appear in
    # real header dumps. The value class admits the base64 alphabet plus "="
    # padding, same as ``Bearer``.
    #
    # Credential-ANNOUNCING, so it stays OUT of ``_OPAQUE_SHAPE_PATTERNS`` and
    # is therefore ON under the conservative preset too.
    #
    # THE LOOKAHEAD IS LOAD-BEARING, not defensive tidiness. Without it this
    # rule redacted the ORDINARY ENGLISH PHRASE "Basic authentication is not
    # configured" — ``authentication`` is 14 characters of the base64 alphabet,
    # so a bare ``[a-zA-Z0-9+/]{8,}`` claimed it and the message became
    # "[REDACTED] is not configured". Caught by this rule's own
    # no-false-positive corpus before landing.
    #
    # A real base64 credential essentially always carries a DIGIT or "+"/"/"/"="
    # padding; a lowercase English word never does. Requiring one such character
    # separates them without needing an ``Authorization:`` context anchor (which
    # would miss the bare ``(Basic <tok>)`` form). The lookahead is BOUNDED
    # ({0,128}) so it cannot become a backtracking vector — see the module
    # docstring's REGEX SAFETY CONTRACT.
    re.compile(
        r"(?i:Basic)\s+(?=[A-Za-z0-9+/=]{0,128}[0-9+/=])[A-Za-z0-9+/]{8,}={0,2}",
        re.ASCII,
    ),
    # Credential-ANNOUNCING ``key=value`` assignments.
    #
    # Every key here NAMES its value as a secret, so a match cannot be a false
    # positive in the way a bare shape can: the string literally says
    # ``password=``. That is the same argument the ``(?i:signature|sig)=``
    # widening above already won, applied to the rest of the family — and like
    # that rule these belong OUTSIDE ``_OPAQUE_SHAPE_PATTERNS``, i.e. ON under
    # BOTH presets, at zero false-positive cost.
    #
    # The gap this closes: NOTHING previously claimed ``password=hunter2...``.
    # It has no vendor prefix (so no literal rule), the "=" and typical length
    # defeat the 40-char contiguous-run rule, and a non-hex body defeats the
    # generic-hex rule — and both of those are OFF under the conservative
    # preset anyway. So it passed through in full on every surface.
    #
    # Separators: ``=`` and ``:`` (``password: hunter2`` in a YAML/JSON dump or
    # a repr), with optional surrounding space and optional quoting. The value
    # class deliberately EXCLUDES whitespace so the match stops at the token
    # and does not swallow the rest of the message.
    #
    # A 6-char floor keeps ``password=`` with an obviously-empty or sentinel
    # value (``password=`` / ``pwd=1``) from being reported as a redaction,
    # while staying well under any real credential length.
    # The optional quote AFTER the key name (``["']?`` before the separator) is
    # what makes a Python/JSON dict repr match: ``'password': 'hunter2...'``
    # puts a closing quote between the key and the ":", and without it the rule
    # missed exactly the shape a logged dict produces.
    # SPLIT INTO TWO by aggression, per the ``_OPAQUE_SHAPE_PATTERNS`` contract
    # below. The token-shaped half runs under both presets; the prose-matching
    # half is aggressive-only. Definitions + rationale at the constants.
    #
    # Order matters only in that both may match the same span; the token rule is
    # listed first so the tighter match is applied before the looser one.
    _CREDENTIAL_KEYVALUE_TOKEN,
    _CREDENTIAL_KEYVALUE_PROSE,
    # Partial key exposure (OpenAI style: "sk-tenA...B12C")
    re.compile(r"sk-[a-zA-Z0-9]{3,4}\.\.\.[a-zA-Z0-9]{3,4}", re.ASCII),
]

#: The subset of ``_CREDENTIAL_PATTERNS`` that discriminates on SHAPE ALONE.
#: Membership is by IDENTITY, not by pattern text — a rule cannot fall out of
#: this set by having its regex edited.
#:
#: CONTRACT FOR ANY NEW RULE ADDED TO ``_CREDENTIAL_PATTERNS``: if the rule can
#: match a string that carries NO credential — i.e. it is not anchored on a
#: vendor prefix, a protocol literal, or a credential-announcing keyword — it
#: MUST be added here too. Leaving it out silently widens the CONSERVATIVE
#: mode, which is the one mode whose whole contract is "matches nothing but a
#: real credential". The bipolar corpus in
#: ``tests/regression/test_scrub_credentials_ordinary_text_is_not_noop.py``
#: is the tripwire: a shape-only rule left unclassified reds it.
_OPAQUE_SHAPE_PATTERNS: Final[frozenset] = frozenset(
    {_GENERIC_HEX_TOKEN, _AWS_SECRET_CONTIGUOUS_RUN, _CREDENTIAL_KEYVALUE_PROSE}
)

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
# residual is DOCUMENTED and bounded — never silent.
#
# That sentence has now been wrong TWICE, in the same direction, and the second
# time was in the correction of the first. It began as an unqualified "NEVER the
# reverse"; a review found residuals trading the other way, so it was softened to
# the above — and a further review falsified THAT, because "this module ... never
# silent" is module-wide while two under-redaction residuals were documented
# NOWHERE in the file. Both are listed below, which is what finally makes the
# claim true rather than merely narrower.
#
# PRE-EXISTING UNDER-REDACTION RESIDUALS — NOT introduced by the exclusion set,
# and not fixable inside it. Listed because a residual known to a reviewer but
# invisible to the next reader is exactly what the sentence above exists to
# prevent:
#
#   1. ESCAPED SCHEME. All three URL rules anchor on a LITERAL `://`. A JSON
#      encoder that escapes forward slashes — PHP `json_encode` does by default
#      — emits `:\/\/`, so the scheme group never matches and nothing claims
#      the credential:
#          {"error":"cannot reach postgresql:\/\/svcuser:s3cr3t@db.internal"}
#            -> unchanged, s3cr3t survives IN FULL
#      Closing it means changing the ANCHOR to a scheme group admitting escaped
#      slashes, not widening any character class here.
#
#   1b. THE REST OF THE ANCHOR-ABSENCE FAMILY. Entry 1 covers a scheme that is
#      present but ESCAPED. All three rules require BOTH a literal `scheme://`
#      AND a literal `@`, so the same root produces three more leaks:
#          u:s3cr3tpw@db.internal/app          (no scheme at all)
#          //u:s3cr3tpw@h/d                    (scheme-relative)
#          postgresql://u:s3cr3tpw%40h/d       (`@` percent-encoded)
#      All three verified leaking in full.
#
#      SCOPE STATUS DIFFERS ACROSS THEM, and two reviewers disagreed about
#      exactly this, which is why it is spelled out rather than asserted:
#        - `%40` is INSIDE stated coverage. The shape IS `scheme://user:pass`;
#          only the separator is encoded. This one is a genuine residual.
#        - scheme-less and scheme-relative are OUTSIDE stated coverage. The
#          module claims `scheme://user:pass@host`, and claiming every
#          `x:y@z` would be wildly over-broad — it would redact ordinary
#          `key:value@timestamp` prose.
#      Listed together anyway because they share ONE root (an absent or
#      unrecognised anchor) and because the ASYMMETRY was the actual defect:
#      entry 1 documented one member of this family while three siblings sat
#      undocumented. A list that covers one member of a family and not the rest
#      is the failure the list exists to prevent.
#
#   2. WHITESPACE IN USERINFO. `[^\s]` makes whitespace the hard terminator, so
#      `postgresql://u:pa ss@host/db` leaks `pa ss`. Structural and deliberate:
#      admitting whitespace would let a run consume whole log lines (see the DoS
#      note above). Accepted, not merely unnoticed.
#
# Any
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
# That fences the compact-JSON crossing (all four forms enumerated below) while
# keeping claimable every credential shape whose quote is not IMMEDIATELY
# followed by a JSON delimiter. That qualifier is load-bearing — see the
# under-redaction residual below.
#
# The delimiter set is EXHAUSTIVE, not illustrative: in well-formed JSON the only
# non-whitespace characters that can follow a closing `"` are `,` (next member),
# `}` (end object), `]` (end array) and `:` (it was a key) — giving the four
# crossing forms `","` / `"},"` / `"],"` / `":"`. The fifth case is end-of-input,
# which is not a character and has nothing to cross to. An earlier version of
# this note named only the first two, which left `]` and `:` looking unjustified
# and would invite a future reader to "simplify" them out, re-opening the array
# and key-position crossings. Whitespace needs no delimiter: `[^\s]` fences it. An earlier revision of this line claimed
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

# ---------------------------------------------------------------------------
# INTERNAL-LOCATION rules (gated by ``redact_paths``)
# ---------------------------------------------------------------------------
# Neither of the two rules below redacts a CREDENTIAL. Both redact an
# identifier of WHERE our infrastructure lives — a filesystem home directory
# and an Azure resource hostname. Knowing the answer grants no access; it is
# infra-identity disclosure, a materially weaker class than a live secret.
#
# They share one flag because they share one trade: on a provider-error
# surface, which may be echoed to a third party, the location is noise worth
# blanking. On a LOCAL-error surface the location is the entire diagnostic
# payload — an ``OSError`` message is a path plus a reason, and an agent that
# cannot read the path cannot retry.
#
# NAMING CAVEAT, recorded rather than papered over: the flag is called
# ``redact_paths`` and one of the two members is a HOSTNAME, not a path. The
# name is narrower than the group. It is kept because "path" is what a caller
# reaches for, and the docstring + this block enumerate the group exactly, so
# the name is imprecise but nothing here is hidden behind it.
_AZURE_OPENAI_ENDPOINT = re.compile(
    r"https://[A-Za-z0-9][A-Za-z0-9-]*\.openai\.azure\.com", re.ASCII
)
"""Azure OpenAI endpoint hostname (#1960).

The <resource> subdomain is the customer's Azure resource name — infra
identity that reveals the tenant. Redact the resource while keeping the
``.openai.azure.com`` suffix so the message still reads as "an Azure OpenAI
endpoint".
"""

# Internal file paths that could reveal infrastructure
_INTERNAL_PATH_PATTERNS: List[re.Pattern] = [
    re.compile(r"/home/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"/Users/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"C:\\Users\\[a-zA-Z0-9_-]+\\", re.ASCII),
]

#: Marker substituted for an internal filesystem path.
_PATH_PLACEHOLDER: Final[str] = "[PATH]/"


def scrub_credentials(
    text: str,
    *,
    placeholder: str = DEFAULT_PLACEHOLDER,
    redact_paths: bool = True,
    redact_opaque_tokens: bool = True,
) -> str:
    """Redact every known credential shape from ``text``.

    This is the ONLY credential-scrub implementation in Kaizen. Both
    ``kaizen.nodes.ai.error_sanitizer.sanitize_provider_error`` and
    ``kaizen.llm.errors.ProviderError`` route through it, so a pattern added
    here lands at BOTH surfaces simultaneously — which is the whole point.

    AGGRESSION IS A CALLER CHOICE, AND THE DEFAULT IS UNCHANGED
    -----------------------------------------------------------
    Both flags default to ``True``, which is BYTE-FOR-BYTE the behaviour every
    caller had before they existed. This is purely additive: an existing call
    site that passes neither flag is indistinguishable from the pre-flag
    function. That is deliberate — the aggressive rules are load-bearing on the
    PROVIDER-ERROR surface this module was built for, where an attacker can
    influence the string and a leaked live credential is strictly worse than a
    blanked token.

    The flags exist because that trade is surface-specific, not universal:

    * ``redact_opaque_tokens`` — the two SHAPE-ONLY rules (32+ hex run, 40+
      char ``[A-Za-z0-9/+]`` run). They claim real bare AWS secrets, and they
      also claim full git SHAs, MD5 digests, unhyphenated UUID/trace ids and
      long CamelCase identifiers.
    * ``redact_paths`` — the INTERNAL-LOCATION rules (``$HOME`` filesystem
      paths, and the Azure OpenAI resource hostname; see that block for the
      naming caveat). They redact infra identity, never a credential.

    Turning BOTH off leaves the rules that can match nothing but a real
    credential: vendor-prefixed tokens (``sk-``, ``sk-ant-``, ``AIza``,
    ``pplx-``, ``AKIA``, ``ASIA``, ``xox?-``, bare JWTs, ``gh?_``,
    ``github_pat_``, ``[sr]k_live_``/``_test_``, ``hf_``, ``fw_``, ``sig=``,
    ``Bearer <tok>``) and URL-userinfo / DSN credentials. That combination is a
    verified no-op across the credential-free corpus in
    ``tests/regression/test_scrub_credentials_ordinary_text_is_not_noop.py``,
    which is what makes it safe on surfaces where the redacted bytes would
    otherwise be load-bearing — an agent-facing ``ToolResult`` carrying an
    ``OSError`` path the model must read to retry, or a local orchestration
    error keyed by git SHA / run id / trace id.

    Args:
        text: The raw string to scrub (a provider error message, a response
            body, a log payload). Never mutated.
        placeholder: Replacement token. Callers use distinct markers so the
            originating surface stays identifiable in logs
            (``[REDACTED]`` for the node surface, ``[REDACTED-CRED]`` for the
            ``LlmClient`` wire surface). It MUST NOT contain ``@``, ``://``,
            or whitespace: the URL-rule ordering contract below depends on a
            substituted userinfo remaining un-rematchable.
        redact_paths: When ``True`` (default) redact internal filesystem paths
            and the Azure OpenAI resource hostname. Set ``False`` on surfaces
            where the location is the diagnostic rather than the disclosure.
        redact_opaque_tokens: When ``True`` (default) apply the two shape-only
            rules. Set ``False`` on surfaces where a hash / SHA / trace id is
            the reader's only correlation handle.

    Returns:
        ``text`` with every ENABLED credential shape replaced.

    Raises:
        ValueError: if ``placeholder`` contains ``@``, ``://``, or whitespace,
            which would break the URL-rule ordering contract and could cause a
            substituted value to be re-matched or a match to be missed.
    """
    # A quote IMMEDIATELY followed by a JSON structural delimiter is the
    # tempered fence's trigger, so a placeholder containing one injects a live
    # trigger into the scrubbed text — a third way to re-enter the URL rules'
    # match space, alongside `@` and `://`.
    #
    # This clause POST-DATES the original guard and was missed when the fence
    # landed: the guard's own rationale is that a substituted userinfo must
    # remain un-rematchable, and the fence changed what "re-matchable" means
    # without the guard being revisited. Demonstrated accepted before the fix —
    # placeholder `":` produced `postgresql://"::":@db.internal/app`.
    #
    # No exploit was found (both in-repo callers pass fixed strings, and a
    # quote-bearing placeholder still redacted both credentials in a
    # two-credential probe). Fixed rather than documented because here a guard
    # CAN attribute: the property is decidable from the placeholder alone. That
    # is the opposite of the ownership-vs-exclusivity limit in the test suite,
    # which is documented precisely because no guard can decide it.
    _fence_trigger = any(
        placeholder[i] == '"' and placeholder[i + 1] in ",}]:"
        for i in range(len(placeholder) - 1)
    )
    if (
        "@" in placeholder
        or "://" in placeholder
        or any(c.isspace() for c in placeholder)
        or _fence_trigger
        or "\\" in placeholder
    ):
        # Fail loudly rather than silently producing a mis-scrubbed string:
        # a placeholder carrying `@`/`://`/whitespace, or a quote followed by a
        # JSON delimiter, re-enters the URL rules' match space and the ordering
        # contract below stops holding.
        #
        # BACKSLASH is a DIFFERENT hazard and is rejected as DEFENCE IN DEPTH,
        # not as the fix. Every substitution below now passes a CALLABLE, and
        # a callable's return value is used LITERALLY — `re.sub` performs no
        # template expansion on it — so a backslash-bearing placeholder is
        # already inert. The guard stays because it makes the property
        # decidable from the placeholder alone, and because it fails at the
        # boundary rather than relying on every future substitution site
        # remembering to pass a callable.
        raise ValueError(
            "placeholder must not contain '@', '://', whitespace, a quote "
            "immediately followed by one of ',}]:' (the tempered fence's "
            "trigger), or a backslash "
            f"(got {placeholder!r}); it would break the URL-rule "
            "ordering contract in scrub_credentials()"
        )

    sanitized = text

    # EVERY substitution below passes a CALLABLE, never a replacement-template
    # STRING, and that is a correctness requirement rather than a style.
    #
    # ``re.sub``'s string replacement is a TEMPLATE: it expands ``\1``,
    # ``\g<0>`` and ``\g<name>`` inside it. ``placeholder`` is CALLER-SUPPLIED
    # and was being interpolated straight into that template, so a placeholder
    # of ``\g<0>`` replaced every matched credential WITH ITSELF — a scrubber
    # that returns its own input, reporting success. The guard above rejected
    # ``@``, ``://``, whitespace and the fence trigger, none of which is a
    # backslash, so the value sailed through.
    #
    # Not hypothetical: ``core/autonomy/hooks/security/redaction.py`` passes an
    # operator-settable ``RedactionConfig.redaction_marker`` here, documented
    # with a ``redaction_marker="***"`` example — i.e. reachable from public
    # config.
    #
    # A callable's return value is used LITERALLY (no expansion), so the
    # placeholder can no longer be interpreted as syntax at all. The two
    # backreference-bearing replacements below rebuild ``\1`` from
    # ``match.group(1)`` instead, keeping the scheme prefix exactly as the
    # template did.
    def _literal(_match: re.Match) -> str:
        return placeholder

    # Vendor-prefixed / shape-anchored credentials first.
    #
    # The gate SKIPS entries in place rather than iterating a filtered list
    # built elsewhere, because the apply ORDER of this list is load-bearing and
    # a second list is a second thing to keep in order. With
    # ``redact_opaque_tokens=True`` the sequence of substitutions is identical
    # to the pre-flag function, element for element.
    for pattern in _CREDENTIAL_PATTERNS:
        if not redact_opaque_tokens and pattern in _OPAQUE_SHAPE_PATTERNS:
            continue
        sanitized = pattern.sub(_literal, sanitized)

    # URL-embedded credentials. The bounded rule runs FIRST because it
    # is the one that handles a literal `@` inside the userinfo; the overflow
    # companion then claims any userinfo too long for that rule's DoS bound.
    def _userpass_replacement(match: re.Match) -> str:
        # group(1) is the scheme (`postgresql://`), preserved verbatim — the
        # literal equivalent of the old `\1` template, without the expansion.
        return f"{match.group(1)}{placeholder}:{placeholder}@"

    sanitized = _URL_WITH_AUTH.sub(_userpass_replacement, sanitized)
    sanitized = _URL_WITH_AUTH_OVERFLOW.sub(_userpass_replacement, sanitized)

    # Runs LAST: the two user:pass rules above have already rewritten their
    # matches to `scheme://<placeholder>:<placeholder>@`, which contains a `:`
    # and so is not re-matched by this no-colon rule. Ordering therefore keeps
    # the user/pass shape visible where one existed, and only collapses
    # userinfo that genuinely had no password half.
    def _userinfo_only_replacement(match: re.Match) -> str:
        return f"{match.group(1)}{placeholder}@"

    sanitized = _URL_WITH_USERINFO_ONLY.sub(_userinfo_only_replacement, sanitized)

    # INTERNAL-LOCATION rules. Both are gated together by ``redact_paths``;
    # with the flag on, the order and effect are identical to the pre-flag
    # function.
    if redact_paths:
        # Redact the resource name in Azure OpenAI endpoints (keep the suffix).
        sanitized = _AZURE_OPENAI_ENDPOINT.sub(
            lambda _m: f"https://{placeholder}.openai.azure.com", sanitized
        )

        # Replace internal file paths.
        for pattern in _INTERNAL_PATH_PATTERNS:
            sanitized = pattern.sub(_PATH_PLACEHOLDER, sanitized)

    return sanitized


def scrub_local_error(value: object, *, placeholder: str = DEFAULT_PLACEHOLDER) -> str:
    """Scrub a LOCAL error value for a message a human or an agent will read.

    THIS IS NOT A SECOND SCRUBBER. It owns no patterns, compiles no regexes and
    makes no decisions: it is the named CONSERVATIVE preset over
    :func:`scrub_credentials`, which remains the single implementation. It
    exists for exactly two reasons, both structural:

    1. **One place defines "conservative".** ~180 call sites in
       ``kaizen-agents`` want this exact combination. Spelling the flags out at
       each of them means a future rule that needs gating has ~180 sites to
       reach, and will not reach them. Here it has one.
    2. **The default stays safe.** A new rule added to
       :data:`_CREDENTIAL_PATTERNS` is ON for provider surfaces by default,
       which is the correct posture; this preset opts out only of the two
       named groups, so a new rule is opted out only if it is deliberately
       classified into one of them.

    ``value`` is the error itself, not a pre-formatted string, because
    ``str(exc)`` is precisely what an f-string ``{exc}`` interpolation
    produces — so ``f"...{exc}"`` becomes ``f"...{scrub_local_error(exc)}"``
    with no change of meaning beyond the scrub.

    WHAT THIS DOES NOT REDACT — AND THE FIRST TWO ENTRIES ARE CREDENTIALS
    ---------------------------------------------------------------------
    Switching ``redact_opaque_tokens`` off disables the only two rules that can
    claim a credential carrying NO vendor prefix. This list previously named
    only benign classes, which is what made the ~180-site sweep onto this
    preset read as safe. It is not safe on a REMOTE surface, and the omission
    was the disclosure defect:

    * **A bare AWS secret access key** (``wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY``)
      — no vendor prefix; claimed ONLY by ``_AWS_SECRET_CONTIGUOUS_RUN``.
    * **A bare 32+ character hex secret** — **Azure OpenAI ``api-key`` values
      are exactly this shape** (see ``_GENERIC_HEX_TOKEN``); claimed ONLY by
      that rule.
    * Filesystem paths, Azure resource hostnames, git SHAs, MD5/SHA digests,
      unhyphenated UUIDs and trace ids — these ARE benign, and they are the
      diagnostic payload of a local error: an ``OSError`` message IS a path
      plus a reason, and an agent handed ``[PATH]/...`` cannot retry.

    USE :func:`scrub_remote_error` INSTEAD whenever the exception being
    rendered can originate at an HTTP / SDK / subprocess / provider boundary.
    "It is caught in local orchestration code" is NOT the test — the test is
    where the exception can be RAISED. A caller-injected provider object is a
    remote boundary even though the ``except`` clause is local.

    Verified no-op over the credential-free corpus in
    ``tests/regression/test_scrub_credentials_ordinary_text_is_not_noop.py``.

    Args:
        value: The caught exception (or any object); rendered with ``str()``.
        placeholder: Replacement token; same contract as
            :func:`scrub_credentials`.

    Returns:
        ``str(value)`` with vendor-prefixed and URL-userinfo credentials
        replaced, and nothing else touched.
    """
    return scrub_credentials(
        str(value),
        placeholder=placeholder,
        redact_paths=False,
        redact_opaque_tokens=False,
    )


def scrub_remote_error(value: object, *, placeholder: str = DEFAULT_PLACEHOLDER) -> str:
    """Scrub an error that can ORIGINATE AT A REMOTE BOUNDARY.

    The sibling of :func:`scrub_local_error`, and the reason that one had to
    stop being the universal answer. Also not a second scrubber: it owns no
    patterns and is a named preset over :func:`scrub_credentials`.

    THE SPLIT EXISTS BECAUSE ONE PRESET CANNOT SERVE BOTH SURFACES.
    ``scrub_local_error`` turns OFF the two SHAPE-ONLY rules, and on a LOCAL
    error that is right: there, a 32-hex run is a git SHA or an MD5 digest and
    a 40-char run is a CamelCase identifier — blanking them destroys the
    diagnostic while protecting nothing.

    On a REMOTE error the SAME shapes are the credential. A bare AWS secret
    access key carries no vendor prefix, and an Azure OpenAI ``api-key`` value
    is a bare 32+ hex run; NO literal-anchored rule matches either, so with the
    shape rules off they pass through into the log IN FULL. Sweeping a
    provider-error sink onto the conservative preset therefore CLOSED a
    filesystem-path disclosure and OPENED a live-credential one.

    So: ``redact_opaque_tokens`` is ON here (the credential axis), while
    ``redact_paths`` stays OFF (the diagnostic axis) — an agent retrying a
    failed call still needs the path and the endpoint, and neither is a
    credential.

    ACCEPTED RESIDUAL, named rather than left implicit: with ``redact_paths``
    off, the Azure OpenAI RESOURCE HOSTNAME (``https://<resource>.openai.azure.com``)
    is NOT redacted here. That is tenant-identifying infra metadata, not a
    credential, and it is load-bearing for diagnosing which deployment failed.
    A surface that must also blank it should call :func:`scrub_credentials`
    directly with both flags at their ``True`` defaults — which is what the
    genuine provider-RESPONSE-body surfaces
    (``sanitize_provider_error``, ``ProviderError.body_snippet``) already do.

    CHOOSING BETWEEN THE TWO PRESETS — TWO TESTS, BOTH MUST PASS FOR LOCAL.

    **Test 1 — where can it be RAISED?** Never where it is CAUGHT. If the
    ``try`` block calls an injected provider, an HTTP client, a subprocess, an
    MCP session, a database driver, or any callable supplied by the caller
    whose implementation is unknown, it is REMOTE.

    **Test 2 — does the exception carry a REMOTE-DERIVED OPERAND?** Test 1
    alone is NOT sufficient, and treating it as sufficient is how a family of
    LOCAL misclassifications was shipped. Many in-process builtins EMBED THEIR
    ARGUMENT in the message they raise::

        float("<x>")   -> ValueError: could not convert string to float: '<x>'
        int("<x>")     -> ValueError: invalid literal for int() with base 10: '<x>'
        re.compile(p)  -> re.error: ... at position N   (echoes the pattern)
        json.loads(s)  -> JSONDecodeError                (position only — SAFE)

    So ``float(llm_response["score"])`` raises IN-PROCESS — passing Test 1 —
    while the message it raises is MODEL OUTPUT. That is REMOTE, and the shape
    that actually leaks is the prefix-less one: a bare AWS secret or a bare
    32+ hex Azure ``api-key`` passes straight through the conservative preset,
    which is precisely the pair of rules this preset switches off. A
    vendor-prefixed key (``sk-``, ``AKIA``) would have been caught either way,
    so testing the classification with one of THOSE cannot distinguish a
    correct verdict from an incorrect one.

    LOCAL therefore requires BOTH: the exception is raised in-process AND it
    carries no remote-derived operand. Genuinely LOCAL: file I/O whose path is
    program-controlled, imports, attribute errors, local registry lookups,
    ``json.loads`` (position-only message).

    VERIFY THE ECHO EMPIRICALLY — DO NOT REASON ABOUT IT, AND PROBE EVERY
    BRANCH, NOT ONE. Which builtins embed their operand is not obvious, and
    guessing produces BOTH error directions::

        json.loads(x)   -> "Expecting value: line 1 column 1 (char 0)"   NO echo
        float(x)/int(x) -> "could not convert string to float: '<x>'"    ECHOES
        open(x)         -> "[Errno 2] No such file or directory: '<x>'"  ECHOES
        re.compile(x)   -> BRANCH-DEPENDENT — see below

    ``re.compile`` IS THE TRAP, AND AN EARLIER REVISION OF THIS PARAGRAPH FELL
    INTO IT. It asserted that ``str()`` of a ``re.error`` is "purely
    positional" and classified the builtin NO-echo. That is true of the
    POSITIONAL branches and FALSE of the GROUP-NAME branches, which
    interpolate the offending name verbatim (Python 3.13)::

        re.compile("<x>(")      -> "missing ), unterminated subpattern
                                    at position N"                      NO echo
        re.compile("(?P=<x>)")  -> "unknown group name '<x>' at position 4"
                                                                        ECHOES
        re.compile("(?P<<x>>y)")-> "bad character in group name '<x>'
                                    at position 4"                      ECHOES

    The wrong verdict was reached by sampling two positional branches and
    generalizing — the precise error this paragraph exists to prevent,
    committed inside it. It shipped a real leak: ``delegate/tools/grep_tool``
    compiles a model-supplied ``pattern`` and was left LOCAL on the strength
    of that claim, so a prefix-less credential inside a group name reached the
    tool result in full. A probe per BRANCH settles it; a probe of one branch,
    or an assumption, does not. The pinned probes are
    ``TestReCompileEchoesItsOperandOnGroupNameBranches`` in
    ``kaizen-agents/tests/regression/test_issue_1720_remote_value_scrub.py``.

    FIVE MORE FAMILIES, PROBED PER BRANCH ON CPython 3.13 RATHER THAN REASONED
    ABOUT. The four entries above were the whole enumeration, so every author
    meeting a type not on the list had to guess — and the ``re.compile`` entry
    is the record of what guessing produces. These are the empirical verdicts;
    the probes are ``TestProbedOperandEchoVerdicts`` in the same file, and they
    read the REAL message, so a CPython change returns the other answer instead
    of leaving a stale verdict standing::

        Decimal(x)                 -> InvalidOperation: "[<class
                                      'decimal.ConversionSyntax'>]"       NO echo
        base64.b64decode(x)        -> binascii.Error: "Incorrect padding"  NO echo
        datetime.strptime(x, f)    -> "time data '<x>' does not match
                                      format '<f>'"                       ECHOES
        datetime.fromisoformat(x)  -> "Invalid isoformat string: '<x>'"    ECHOES
        ipaddress.ip_address(x)    -> "'<x>' does not appear to be an
                                      IPv4 or IPv6 address"               ECHOES
        KeyError                   -> str(KeyError(k)) IS repr(k)         ECHOES

    THE TWO NO-ECHO VERDICTS ARE THE ONES THAT WOULD HAVE BEEN GUESSED WRONG.
    ``Decimal`` and ``b64decode`` both take a string the caller is trying to
    parse — the ``float``/``int`` shape exactly — and both feel like they must
    quote it back. Neither does: ``decimal`` reports the CONDITION CLASS
    (``ConversionSyntax``, ``DivisionByZero``) and never the operand, and
    ``binascii`` reports a padding/character-class complaint with counts only.
    Probed across branches, not sampled: ``Decimal`` of a ``bytes`` names the
    source TYPE only, and its ``quantize``/division branches are condition
    classes too; ``b64decode`` was probed strict and lax, with bad padding,
    illegal characters, leading padding, and non-UTF-8 bytes. (Its ``altchars``
    branch raises ``AssertionError`` echoing the ALTCHARS argument — which is
    program-controlled, not the remote operand.)

    ``KeyError`` IS THE SHARPEST OF THE THREE ECHOERS, because it has no
    message of its own to inspect: ``str()`` of it is the ``repr`` of the
    missing key, so ``f"missing field: {exc}"`` prints the key verbatim with
    nothing that looks like interpolation. A key taken from model output or a
    remote payload is a remote-derived operand by exactly the Test-2 rule.

    ``strptime`` ECHOES ON BOTH OPERANDS — the data on a mismatch, the tail of
    the data on ``unconverted data remains``, and the FORMAT string on a bad
    directive. A site that takes the format from remote input fails Test 2 on
    that argument alone.

    The sweep that produced these verdicts also checked this repo's call sites
    for the same types: every ``ipaddress`` parse (``llm/http_client``,
    ``llm/url_safety``, ``tools/builtin/api``, ``mcp/builtin_server/tools/api``)
    SWALLOWS its exception (``except (ValueError, TypeError): ... None``) and
    reports a constructed reason code instead, and every ``b64decode`` site
    interpolates an exception that does not echo. So the enumeration above is a
    doctrine gap closed BEFORE it shipped a leak, not after — which is the
    difference between this entry and the ``re.compile`` one.

    ``Path.glob`` — NO ECHO, AND THE BRANCH SET MOVES BETWEEN RELEASES. Probed
    per branch on CPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14 because
    ``delegate/tools/glob_tool`` passes a MODEL-supplied ``pattern`` to it, so
    the site turns entirely on Test 2. No branch echoes a credential-bearing
    pattern on ANY of the five::

        misplaced ``**`` -> "Invalid pattern: '**' can only be an entire
                            path component"        3.10-3.12 ONLY; gone 3.13+
        empty/dot-only   -> "Unacceptable pattern: ''"      3.10-3.12, 3.14
                            "Unacceptable pattern: PosixPath('.')"      3.13
        embedded NUL     -> "embedded null character in path"
                            ValueError on 3.13 ONLY; no raise on 3.10-3.12, 3.14
        absolute pattern -> "Non-relative patterns are unsupported"
                            NotImplementedError (NOT ValueError), all five

    The only raise that interpolates at all is ``Unacceptable pattern``, and it
    is reachable ONLY when the pattern normalizes to no tail components
    (``""``, ``"."``, ``"./"``) — shapes that cannot carry a credential. So
    ``glob_tool`` is LOCAL on the evidence, and recording that is the point: a
    NO-echo verdict is a result, and leaving this family out of the enumeration
    is what forces the next author to guess.

    TWO THINGS THIS ENTRY EXISTS TO WARN ABOUT, both invisible from one
    interpreter. First, the branch SET is not stable — two of the four rows
    above differ between 3.12 and 3.13 in BOTH directions (a ValueError
    removed, another added), so a verdict measured on one interpreter is not a
    verdict about the versions this package supports. Second, the absolute-
    pattern branch raises ``NotImplementedError``, a ``RuntimeError`` subclass:
    an ``except ValueError`` around a glob does not catch it, which is a
    correctness bug independent of the scrub question and is exactly how it sat
    unnoticed. Probe every branch AND every supported interpreter, or the
    sample is again standing in for the enumeration.

    NAMED CARVE-OUT — FILESYSTEM-PATH OPERANDS STAY LOCAL. A file tool whose
    path argument came from a model (``file_read``, ``file_write``,
    ``file_edit``) raises an ``OSError`` that DOES echo the path, which by the
    two tests above reads as REMOTE. It stays LOCAL deliberately, because
    switching it would not redact the path anyway — ``redact_paths=False`` on
    BOTH presets — and the only added rules are the two SHAPE-ONLY ones, which
    would blank legitimate content-addressed path segments (a git object path
    carries a 38-character hex run that ``_GENERIC_HEX_TOKEN`` matches exactly).
    The result: a tool error the agent cannot act on, for no credential gain.
    A path is the diagnostic payload of a file error, and this preset exists to
    preserve it. Recorded here so the next audit does not re-litigate it.

    When in doubt, use this one: over-redacting a hash costs a correlation
    handle, under-redacting leaks a live credential.

    Args:
        value: The caught exception (or any object); rendered with ``str()``.
        placeholder: Replacement token; same contract as
            :func:`scrub_credentials`.

    Returns:
        ``str(value)`` with every credential shape replaced — including the
        prefix-less AWS-secret and bare-hex shapes — and internal paths and the
        Azure resource hostname left intact.
    """
    return scrub_credentials(
        str(value),
        placeholder=placeholder,
        redact_paths=False,
        redact_opaque_tokens=True,
    )
