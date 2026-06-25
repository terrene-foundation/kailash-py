# External Spec Extraction — Delegate Specification v0

**Source:** `/Users/esperie/repos/dev/unicorn-focus/drafts/02-delegate-spec-v0-outline.md`
**Source size:** 256 lines (~31 KB), authored by Dr. Jack Hong (Terrene Foundation), CC BY 4.0 pre-pledged
**Source self-description (lines 3-4):**

> "**Status:** Pre-draft scaffold. Not the spec. A structural skeleton for the founder to author against."

**Critical framing finding — read this before everything else.**

The external document is **not a normative specification**. It is a _section outline plus open-question list_ that Dr. Hong intends to author the actual spec against over a 6–8 week window (lines 4-5). The 15 sections each have an **Intent paragraph** (what the section will eventually settle) and an **Open questions** list (decisions the founder must make). The document explicitly states:

- Line 3: "Pre-draft scaffold. Not the spec."
- Line 247: "if a section can only be implemented one way, it is over-specified" — the discipline being asserted for the _future_ spec
- Line 253: "The end-state I would target for v1.0: a 35–55 page document" — i.e. the current 11-page outline is not yet that document

**Consequence for #1035 acceptance criteria.** The acceptance bar "py-emitted chain verifies under rs verifier" cannot be satisfied by reading record-shape mandates off this document, because the document does not define record shapes. What it DOES define is (a) the section structure both implementations must eventually conform to, (b) the substrate inheritances (EATP v2.2 audit, PACT 5-dimensional envelope, posture gradient `PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS`), and (c) a set of recommendation candidates the author has pre-staked on individual open questions.

The honest extraction below distinguishes three categories:

1. **MANDATED** — text the outline asserts as a structural requirement (mostly inheritances from prior Terrene specs)
2. **PROPOSED / RECOMMENDATION CANDIDATE** — text the outline pre-stakes a position on but flags as not-yet-final
3. **OPEN** — open questions the author has explicitly deferred

Any kailash-py implementation that picks Category-2 or invents Category-3 answers ahead of the founder MUST flag the decision as ahead-of-spec, because the kailash-rs implementation may pick differently and the two will not converge until v1.0 lands.

---

## 1. Section Map

The outline numbers 15 sections. Issue #1035 names sections §3-§10. The outline's numbering DIFFERS from #1035's mapping — the outline's Section 3 is "Role Binding", Section 4 is "Genesis Record", etc. The mapping I infer from #1035's titles:

| #1035 title     | Outline section                                       | Outline lines |
| --------------- | ----------------------------------------------------- | ------------- |
| §3 Identity     | Section 1 — Identity                                  | 42–53         |
| §4 Genesis      | Section 4 — Genesis Record                            | 78–88         |
| §5 Envelopes    | Section 5 — Constraint Envelopes                      | 90–100        |
| §6 Posture      | Section 6 — Posture Gradient                          | 102–112       |
| §7 Cascade      | Section 7 — Cascade & Sub-Delegation                  | 114–124       |
| §8 Memory       | Section 8 — Memory and Institutional Knowledge        | 126–136       |
| §9 Audit        | Section 9 — Audit Chain (EATP Provenance)             | 138–148       |
| §10 Integration | Section 10 — Integration Surface (Enterprise Systems) | 150–171       |

This re-numbering is itself a finding — #1035 may be using a working numbering that does not match the outline's section order. Implementations should track BOTH numbers in cross-references.

### §3 Identity (outline Section 1, lines 42–53)

**Intent (verbatim line 44):** define what a Delegate is — _"a named, role-bearing, cryptographically-rooted agent with explicit authority, an explicit constraint envelope, and an unbroken audit chain back to a human sovereign."_

**Distinguishes from** (line 44): a chatbot (no role binding), an agentic framework (no audit chain), an Envoy (exterior orientation), a workflow (no posture gradient).

**Load-bearing primitives the section names but does NOT settle:**

- Identity key (open question 1, line 48): `(organization_id, role_id, version)` tuple _vs._ opaque UUID. **OPEN.**
- Human-readable name (Q2, line 49): part of spec'd identity _vs._ UI-layer only. **OPEN.**
- Voice/output style (Q3, line 50): part of identity _vs._ part of role-binding. **OPEN.**
- Sovereign pointer (Q4, line 51): persisted on Delegate _vs._ reconstructed at audit time. **OPEN.**
- Sovereign re-pointing mid-lifecycle (Q5, line 52): allowed _vs._ requires retire+re-instantiate. **OPEN.**

### §4 Genesis (outline Section 4, lines 78–88)

**Intent (line 80):** the immutable, signed artifact establishing a Delegate's authority and constraints at instantiation. Analogous to Envoy's Genesis Record. EATP v2.2 conformance.

**Load-bearing primitives:**

- Signing party (Q1, line 84): human sovereign personally / org signing authority (CISO) / countersigned. **OPEN.**
- **PROPOSED required fields (Q2, line 85, "proposed"):** `delegate_id`, `role_binding`, `sovereign`, `instantiation_timestamp`, `initial_envelope`, `initial_posture`, `signature`. **PROPOSED — not settled.**
- Optional fields candidate (line 85): expected lifetime, renewal cadence, succession plan.
- On-chain anchoring (Q3, line 86): Sigstore / org HSM / Terrene witness / hybrid / org's own EATP ledger only. **OPEN.**
- Cross-vendor portability (Q4, line 87): "should an Aegis-instantiated Delegate's Genesis Record be verifiable by a competing-vendor EATP verifier?" — _directly relevant to #1035's cross-language verification criterion._ **OPEN.**
- Genesis Amendment mechanism (Q5, line 88): non-destructive correction _vs._ retirement + re-instantiation only. **OPEN.**

### §5 Envelopes (outline Section 5, lines 90–100)

**Intent (line 92):** apply PACT's 5-dimensional envelope (Financial, Operational, Temporal, Data Access, Communication) with enterprise-specific particulars. **MANDATES monotonic tightening** — envelope may only narrow within a single lifecycle, never widen. Widening requires a new Genesis Record (re-instantiation).

**Load-bearing primitives:**

- **The 5 PACT dimensions** (line 92, MANDATED inheritance): Financial / Operational / Temporal / Data Access / Communication.
- **PROPOSED additional dimensions** (Q1, line 96): Jurisdictional (legal regimes), Counterparty (allowed external parties), Materiality (business-impact threshold). **PROPOSED — not settled.**
- Financial envelope shape (Q2, line 97): per-transaction _vs._ per-period _vs._ both. **OPEN** (line 97 calls "both" the "safest default").
- Data Access classification (Q3, line 98): import customer's existing taxonomy _vs._ re-define. **OPEN.**
- Communication enumeration (Q4, line 99): allowed channels _vs._ counterparties _vs._ both. **OPEN.**
- Monotonic tightening exceptions (Q5, line 100): "is the rule absolute?" — recommendation is child Delegate for temporary widening, NOT relaxation. **PROPOSED.**

### §6 Posture (outline Section 6, lines 102–112)

**Intent (line 104):** inherit Envoy's `PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS` ladder, redefined for enterprise verbs. **MANDATES ratcheting** — posture advances only by explicit human grant, never implicit.

**Load-bearing primitives:**

- **5-state posture ladder** (line 104, MANDATED): `PSEUDO → TOOL → SUPERVISED → DELEGATING → AUTONOMOUS`.
- PSEUDO semantics (Q1, line 108): "shadow mode" _vs._ "draft mode" — different operational shapes. **OPEN.**
- **PROPOSED 6th state `RESTRICTED`** (Q2, line 109) between SUPERVISED and DELEGATING. **PROPOSED — not settled.**
- Automatic downgrade triggers (Q3, line 110): anomaly detection / audit failure / envelope violation. **OPEN.**
- **PROPOSED cascade-posture cap** (Q4, line 111, "Recommendation candidate"): "no higher than the parent." **PROPOSED.**
- Posture granularity (Q5, line 112): per-Delegate _vs._ per-(Delegate, capability). **OPEN.**

### §7 Cascade (outline Section 7, lines 114–124)

**Intent (line 116):** how a Delegate creates and authorises sub-Delegates. References PACT's **D/T/R addressing** (Domain / Tenant / Role). **MANDATES authority/envelope tightening on cascade** — never relax. Every sub-Delegate's actions chain back through parent's Delegation Records to the originating Genesis Record.

**Load-bearing primitives:**

- **D/T/R cascade addressing** (line 116, MANDATED inheritance from PACT).
- **MANDATED audit chain-through:** sub-Delegate actions chain back through parent to originating Genesis Record (line 116).
- Maximum cascade depth (Q1, line 120): "no spec-level cap, but runtime implementations must support ≥ 5". **PROPOSED.**
- Lateral cascade (Q2, line 121): peer Delegate at same posture _vs._ downward-only. **OPEN.**
- Sync/async default (Q3, line 122). **OPEN.**
- Sub-Delegate fate on parent retirement (Q4, line 123): cascade-retire / re-root / quarantine. **OPEN.**
- **Tenant isolation under cascade (Q5, line 124):** "A Delegate in Tenant-A must not be able to cascade into Tenant-B even if both tenants are within the same Domain." This reads MANDATED, though phrased as an open question.

### §8 Memory (outline Section 8, lines 126–136)

**Intent (line 128):** three-tier memory model — (a) session-scoped working memory, (b) Delegate-lifecycle memory, (c) role-scoped institutional memory (outlives Delegate, passes to successor). The spec's answer to the founder's _succession / knowledge continuity_ forcing function.

**Load-bearing primitives:**

- **3-tier memory taxonomy** (line 128, structurally asserted): session / Delegate-lifecycle / role-scoped institutional.
- Memory ownership on employee departure (Q1, line 132): retire+archive _vs._ pass to successor. **OPEN — depends on §3 role-binding decision.**
- Memory storage location (Q2, line 133): inside Delegate (portability) _vs._ outside in role-scoped store (isolation, ownership clarity). **OPEN.**
- Redaction protocol on customer termination (Q3, line 134). **OPEN.**
- Schema source (Q4, line 135): import from Aegis or kailash-rs _vs._ minimal own contract. **OPEN.**
- Reasoning-chain memory vs. audit-chain memory boundary (Q5, line 136): "the boundary is load-bearing for trust." **OPEN.**

### §9 Audit (outline Section 9, lines 138–148)

**Intent (line 140):** EATP v2.2 conformance. **MANDATES every action emits a signed record naming the Delegate, the originating Genesis Record, the envelope it operated under, the inputs consumed, the outputs produced, and (where applicable) the human grant that authorised the action class** (line 140).

**Load-bearing primitives:**

- **MANDATED EATP v2.2 conformance** (line 140) — the substrate.
- **MANDATED minimum attestation surface per action** (line 140 enumeration): Delegate id, originating Genesis Record, envelope-under-which, inputs, outputs, authorising human grant.
- Granularity (Q1, line 144): every model call _vs._ every external side-effect. **PROPOSED:** "side-effects mandatory, model calls optional but encouraged."
- Latency budget (Q2, line 145): Envoy specifies ≤ 5ms structural / ≤ 50ms semantic-cached — _"does Delegate inherit this or specify its own?"_ **OPEN.**
- Tamper-anchoring (Q3, line 146): Sigstore / org HSM / Terrene witness / "implementation choice". **OPEN.**
- Regulator-access shape (Q4, line 147). **OPEN.**
- Self-introspection (Q5, line 148): Delegate queries its own audit chain _vs._ external-auditor-only. **OPEN.**

### §10 Integration (outline Section 10, lines 150–171)

**Intent (line 152):** binding contract between Delegate and enterprise systems-of-record. **MANDATES four required primitives** (lines 154–158); **specifies three optional primitives** (lines 160–164).

**Load-bearing primitives — MANDATED required (lines 155–158):**

- SAML / OIDC authentication into target system
- A signed action envelope around every write
- An EATP-attested receipt of every read (for audit completeness on data-access decisions)
- A revocation channel (instant human revocation of Delegate's access to a specific system)

**Load-bearing primitives — optional (lines 161–164):**

- Native API binding (vs. screen-scraping fallback)
- Change-data-capture subscription
- Bulk-operation envelope

**Open questions:**

- Connector catalog scope (Q1, line 167): part of spec _vs._ separate "Delegate Connector Catalog". **OPEN.**
- Direct database access (Q2, line 168): forbidden _vs._ allowed under stricter envelope _vs._ allowed only at posture ≤ SUPERVISED. **OPEN.**
- Credential model (Q3, line 169): impersonation _vs._ delegation _vs._ substitution. **PROPOSED:** "delegation by default, impersonation forbidden, substitution allowed for write-heavy systems."
- Connector conformance test suite (Q4, line 170): "**Recommendation candidate: yes, mandatory at v1.0; Apache 2.0 published alongside the spec; pre-pledged to Terrene.**" **PROPOSED but strong.**
- Bindingless-system fallback (Q5, line 171): browser-driven action with per-action attestation. **OPEN.**

---

## 2. Canonical Types

**Finding — the outline does NOT define canonical types in the sense of dataclass-shaped record schemas.** It names artifacts by role and inherits structure from prior Terrene specs (EATP, PACT) without re-deriving fields. The complete inventory of _named_ artifacts in the outline:

| Named artifact                        | Where named                                                                                                                                      | Field shape given?                                                                                                                                                                                     |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Delegate**                          | line 13 (definition), throughout                                                                                                                 | NO — described by behaviour, not by struct                                                                                                                                                             |
| **Genesis Record**                    | line 80 (Sec 4 intent), and lines 78, 85, 87, 116, 140, 175, 216, 217                                                                            | PARTIAL — line 85 "proposed" enumeration: `delegate_id`, `role_binding`, `sovereign`, `instantiation_timestamp`, `initial_envelope`, `initial_posture`, `signature`                                    |
| **Delegation Record**                 | lines 31, 80, 116                                                                                                                                | NO — inherited from EATP v2.2; not re-derived                                                                                                                                                          |
| **Constraint Envelope** (PACT 5-dim)  | line 92 (Sec 5 intent), throughout                                                                                                               | PARTIAL — five dimensions named (Financial / Operational / Temporal / Data Access / Communication), proposed extensions (Jurisdictional, Counterparty, Materiality); per-dimension shape NOT specified |
| **Posture** (state in 5-state ladder) | line 104 (Sec 6 intent)                                                                                                                          | PARTIAL — state values enumerated (`PSEUDO`, `TOOL`, `SUPERVISED`, `DELEGATING`, `AUTONOMOUS`); proposed `RESTRICTED`; transition rules NOT formalised                                                 |
| **Role binding**                      | Section 3 (lines 67–76) — re-numbered, OUT OF #1035 scope                                                                                        | OPEN — Q4 (line 75) asks whether "Role" is a first-class spec object                                                                                                                                   |
| **Grant Moment**                      | line 175 (Sec 11), line 178                                                                                                                      | NO — inherited from Envoy charter, not re-derived                                                                                                                                                      |
| **Escalation event**                  | Q2 line 180 ("structured event with a category and a routing target")                                                                            | PARTIAL — categories named (envelope violation, anomaly, novel intent); fields not specified                                                                                                           |
| **Audit Chain**                       | line 138 (Sec 9 title)                                                                                                                           | NO — inherited from EATP v2.2                                                                                                                                                                          |
| **Delegate Posture Digest**           | line 181 ("Recommendation candidate")                                                                                                            | PROPOSED — not specified                                                                                                                                                                               |
| **Lifecycle state**                   | line 56 (6 proposed states: `proposed → instantiated → posture-graded → active → retired → archived`) — Sec 2, OUT OF #1035 scope but referenced |

**Types implementations need that the outline does NOT name:**

- `Connector` — outline references "connector implementations" (lines 167, 170) but never defines the type
- `Executor` — not named
- `DelegateMessage` — outline references "inter-Delegate messaging surface" (Sec 12, line 191) but defers the messaging contract to "a minimal messaging contract is part of the Delegate spec; richer orchestration patterns are a sibling spec" (line 191). No type given.
- `PrincipalDirectory` — not named
- `AuditChain` — named but no struct given (line 138)
- `LifecycleTransition` — not named; the issue body's reference to a Rust runtime crate using `LifecycleTransition` over the 6-state chain is a kailash-rs implementation choice, NOT a spec mandate
- `PostureState` — implicit only

**The composition surface `Delegate.compose(connectors=, directory=, signature=, envelope=, executor=, pact_engine=)` named in the issue body is NOT in the outline at all.** This is an issue-body invention (likely a kailash-rs reflection), not a spec-mandated API. See §6 below.

---

## 3. Invariants

Tagged with section of origin. Categorised as MANDATED (asserted as structural requirement) or PROPOSED (recommendation candidate / "should").

### MANDATED invariants

| #    | Invariant                                                                                                                                                                            | Section                                     | Line |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------- | ---- |
| I-1  | Every Delegate is cryptographically rooted with an unbroken audit chain back to a human sovereign                                                                                    | Identity (Sec 1)                            | 44   |
| I-2  | Constraint envelope monotonic tightening within a lifecycle — may narrow, never widen                                                                                                | Envelopes (Sec 5)                           | 92   |
| I-3  | Envelope widening requires a new Genesis Record (re-instantiation)                                                                                                                   | Envelopes (Sec 5)                           | 92   |
| I-4  | Posture is ratcheted — advances only by explicit human grant, never implicit                                                                                                         | Posture (Sec 6)                             | 104  |
| I-5  | Authority and envelopes always tighten on cascade — never relax                                                                                                                      | Cascade (Sec 7)                             | 116  |
| I-6  | Every sub-Delegate's actions chain back through parent's Delegation Records to originating Genesis Record                                                                            | Cascade (Sec 7)                             | 116  |
| I-7  | Tenant isolation under cascade — a Delegate in Tenant-A MUST NOT cascade into Tenant-B even within the same Domain                                                                   | Cascade (Sec 7)                             | 124  |
| I-8  | Every action emits a signed record naming: Delegate, originating Genesis Record, envelope-under-which, inputs consumed, outputs produced, authorising human grant (where applicable) | Audit (Sec 9)                               | 140  |
| I-9  | EATP v2.2 conformance for the entire audit chain                                                                                                                                     | Audit (Sec 9)                               | 140  |
| I-10 | Integration writes require a signed action envelope                                                                                                                                  | Integration (Sec 10)                        | 156  |
| I-11 | Integration reads emit an EATP-attested receipt                                                                                                                                      | Integration (Sec 10)                        | 157  |
| I-12 | Every integration MUST expose an instant human revocation channel                                                                                                                    | Integration (Sec 10)                        | 158  |
| I-13 | Integration authentication MUST use SAML / OIDC into the target system                                                                                                               | Integration (Sec 10)                        | 155  |
| I-14 | Two Delegates from different organizations interacting MUST present mutual attestation (this is where Delegate meets Envoy)                                                          | Multi-Delegate (Sec 12, OUT-OF-#1035-scope) | 194  |
| I-15 | The Delegate spec MUST reference (not re-derive) PACT and EATP — "one paragraph and a citation — never a re-explanation"                                                             | Author's Note                               | 249  |

### PROPOSED invariants ("Recommendation candidate" — author has pre-staked but not settled)

| #    | Invariant                                                                                                                              | Section                         | Line |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- | ---- |
| P-1  | Multi-role binding requires the INTERSECTION of role envelopes, never the union                                                        | Role Binding (Sec 3, OUT)       | 72   |
| P-2  | Cascade depth: no spec-level cap, runtime implementations must support ≥ 5                                                             | Cascade (Sec 7)                 | 120  |
| P-3  | Sub-Delegate's posture: no higher than parent                                                                                          | Posture (Sec 6)                 | 111  |
| P-4  | Audit granularity: side-effects mandatory, model calls optional but encouraged                                                         | Audit (Sec 9)                   | 144  |
| P-5  | Integration credential model: delegation by default, impersonation forbidden, substitution allowed for write-heavy systems             | Integration (Sec 10)            | 169  |
| P-6  | Connector conformance test suite mandatory at v1.0, Apache 2.0, pre-pledged to Terrene                                                 | Integration (Sec 10)            | 170  |
| P-7  | Backward compatibility: minor versions (v1.x) MUST accept records from any prior v1.x                                                  | Versioning (Sec 14, OUT)        | 215  |
| P-8  | Deprecation cycle: feature deprecated in N MUST remain implementable in N+1, MAY be removed in N+2; runtimes MUST emit warnings in N+1 | Versioning (Sec 14, OUT)        | 218  |
| P-9  | Emergent fleet behaviour monitoring: optional at v1.0, mandatory at v2.0                                                               | Multi-Delegate (Sec 12, OUT)    | 195  |
| P-10 | Delegate portability across deployment tiers: portable; tier is runtime property, not identity                                         | Sovereignty (Sec 13, OUT)       | 203  |
| P-11 | Grant Moments: expiring grants encouraged; permanent grants explicitly marked                                                          | Human Interaction (Sec 11, OUT) | 182  |
| P-12 | Spec governance transfers from Integrum to Terrene at v1.0 stability                                                                   | Versioning (Sec 14, OUT)        | 219  |

**Lifecycle state machine — proposed transitions** (Sec 2, line 56, OUT OF #1035 scope but referenced by #1035's issue body):

> "Six proposed states: **proposed → instantiated → posture-graded → active → retired → archived**."

The outline proposes this chain but explicitly asks open questions about whether `proposed` is a real state (Q1, line 60), whether `retired` is one-shot or has a wind-down period (Q3, line 62), and whether `archived` is runtime or storage (Q4, line 63). The state machine **edges are NOT formalised** beyond the arrow-chain in line 56. A Delegate forking (sub-state, parallel chain, e.g. a Compliance Delegate spawning GDPR-Audit-2026) is asked as open question 5 (line 64) — NOT settled.

---

## 4. Conformance Vectors

**Finding — the outline does NOT enumerate canonical conformance vectors.** What it says about implementation agreement:

1. **Conformance levels are mentioned but not defined** (Sec 14, line 211): "Conformance levels (Conforming / Partially Conforming / Non-Conforming) and the labelling discipline implementations must follow." The labels are named; the criteria are not.

2. **Cross-vendor verification is an OPEN question** (Sec 4 Q4, line 87, verbatim):

   > "What is the spec's stance on Genesis Record portability across runtime vendors? Should an Aegis-instantiated Delegate's Genesis Record be verifiable by a competing-vendor EATP verifier?"

   This is precisely the kailash-py / kailash-rs interop question #1035 is asking — and the spec author has flagged it as not-yet-decided.

3. **Conformance test vector set is planned but not authored** (Author's Note, line 253):

   > "a separate conformance test vector set (Apache 2.0, pre-pledged to Terrene), accompanied by an Aegis reference-implementation conformance report"

   The test vectors are an artifact of the _future_ v1.0 release, not part of the current outline.

4. **Connector conformance test suite is also proposed-not-built** (Sec 10 Q4, line 170, "Recommendation candidate"): mandatory at v1.0.

5. **Conformance report shape** (Author's Note, line 253): example phrasing — "Aegis v1.0 implements Delegate spec v1.0 at Conformance Level 2 [Sections 1–14, partial 15]; gaps listed; remediation timeline published". This is illustrative of the _form_ a conformance report would take, not a per-section vector.

**Implication for #1035.** Until conformance vectors exist, kailash-py and kailash-rs cannot agree on "compatible" by running a shared test suite. They can only agree on (a) shared inheritances (EATP v2.2 record shapes, PACT 5-dim envelope grammar) — which are external substrate specs already in the Terrene ecosystem — and (b) on whatever convention the two teams negotiate ahead of the spec landing. The kailash-py team should treat the kailash-rs implementation as a _peer_, not as the conformance oracle.

---

## 5. Cross-Language Verification Surface

#1035's acceptance criterion is "py-emitted chain verifies under rs verifier". The outline tells us:

### What the outline says verification covers

The audit chain (Sec 9) is the verification target. The mandated attestation surface (I-8 above, line 140) names six fields every action record carries:

1. The Delegate (identity)
2. The originating Genesis Record (root)
3. The envelope it operated under (constraint snapshot at action time)
4. The inputs it consumed
5. The outputs it produced
6. (Where applicable) the human grant that authorised the action class

A "py-emitted chain" that "verifies under rs verifier" therefore needs cross-language agreement on:

- **EATP v2.2 record framing** — signature scheme, canonicalisation, hash function. NOT defined in the outline; INHERITED from EATP spec.
- **Genesis Record fields** — the proposed list at line 85 (`delegate_id`, `role_binding`, `sovereign`, `instantiation_timestamp`, `initial_envelope`, `initial_posture`, `signature`). PROPOSED, not settled.
- **Envelope serialisation** — PACT 5-dim. NOT defined in the outline; INHERITED from PACT spec.
- **Delegation Record framing** — NOT defined in the outline; INHERITED from EATP v2.2.
- **Hash-chain anchoring scheme** — Sec 9 Q3 (line 146) explicitly OPEN: Sigstore / org HSM / Terrene witness / "implementation choice".

### What the outline does NOT settle that verification needs

- Canonical JSON / CBOR / protobuf encoding for records
- Time encoding (RFC 3339? unix epoch? monotonic counter for ordering?)
- Field ordering for hashing
- Signature scheme (Ed25519? ECDSA P-256?)
- Whether the audit chain is per-Delegate, per-tenant, or per-organisation
- How the chain is anchored against tampering (Q3, line 146 OPEN)
- Cross-vendor verifiability is itself OPEN (Sec 4 Q4, line 87)

**Conclusion for #1035.** Cross-language verification cannot be implemented purely from this outline. It requires:

(a) The actual EATP v2.2 and PACT spec texts (referenced but external to the outline); **AND**

(b) A documented convention between kailash-py and kailash-rs on every Category-3 OPEN item above that affects byte-level record shape. This convention should be filed as part of #1035's analysis output and propagated to BOTH SDKs so neither drifts.

The kailash-rs implementation (per the issue body) has presumably already made choices on these — those choices are NOT spec-derived, they are kailash-rs-derived. kailash-py either (i) mirrors them by reading the rs source, (ii) negotiates revisions with the rs team, or (iii) waits for the Dr. Hong v1.0 spec. Strategy (i) is fastest; strategy (ii) is safest cross-SDK; strategy (iii) defeats #1035's timeline.

---

## 6. Composition Surface

**Finding — the API shape named in the issue body does NOT appear in the outline.**

The issue body cites:

```
Delegate.compose(connectors=, directory=, signature=, envelope=, executor=, pact_engine=)
await delegate.run()  # ingest → classify → trust → dispatch → audit
```

Searching the outline for these terms:

- `compose` — NOT present
- `connectors=` — `connector` plural appears at lines 27 ("specific connector implementations"), 167 ("connector implementations (SAP, M365, Salesforce, Workday, ServiceNow)"), 170 ("connector conformance test suite"). The PARAMETER NAME `connectors=` is not in the outline.
- `directory=` (PrincipalDirectory) — NOT present
- `signature=` (signing config) — `signature` appears in the proposed Genesis Record field list at line 85, but not as a composer parameter
- `envelope=` — `envelope` is everywhere; not as a composer parameter
- `executor=` — NOT present
- `pact_engine=` — NOT present
- `ingest → classify → trust → dispatch → audit` pipeline — NOT present in the outline

**What the outline says about runtime surface (verbatim, line 247, Author's Note):**

> "Resist the temptation to specify the runtime. Aegis is the reference runtime. The spec must not encode Aegis's internal architecture as if it were universal. The spec must define what every conforming runtime must do, not how Aegis does it. The discipline is: if a section can only be implemented one way, it is over-specified; if a section can be implemented in five reasonable ways, the spec is at the right altitude."

**Implication.** The `Delegate.compose(...)` builder is a kailash-rs-shaped API, not a spec-mandated API. If kailash-py mirrors it, it does so as cross-SDK courtesy / parity, not as spec conformance. The outline's discipline (line 247) actively WARNS against any single runtime shape being treated as universal — so adopting the rs surface as the spec contract would violate the outline's own anti-over-specification rule.

**Recommendation for kailash-py.** Adopt the rs composer shape if cross-SDK parity is the project goal, but flag it in the codebase as "convention with kailash-rs, not spec-derived" so future spec revisions don't break the parity claim silently.

---

## 7. Genesis / Lifecycle

### Genesis Record (Section 4, lines 78–88)

**MANDATED:**

- The Genesis Record is **immutable, signed, established at instantiation** (line 80)
- It establishes the Delegate's **authority and constraints** (line 80)
- **Every subsequent Delegation Record cascades from it** (line 80)
- **EATP v2.2 conformance** (line 80)

**PROPOSED required fields** (line 85, the only field shape given anywhere in the outline):

```
delegate_id
role_binding
sovereign
instantiation_timestamp
initial_envelope
initial_posture
signature
```

The author qualifies this with "(proposed)" — it is not settled.

**Optional field candidates** (line 85): expected lifetime, renewal cadence, succession plan.

### Lifecycle (Section 2, lines 54–64)

The outline proposes a 6-state chain (line 56, verbatim):

> "Six proposed states: **proposed → instantiated → posture-graded → active → retired → archived**."

**This matches the issue body's chain `Proposed → Instantiated → PostureGraded → Active → Retired → Archived` exactly** (casing differs). So the kailash-rs `LifecycleTransition` enum is faithful to the outline's PROPOSED chain.

**However**, the outline flags FIVE open questions about this state machine (lines 60–64):

1. Is `proposed` a real spec-level state, or pre-spec (procurement/RFP)?
2. What is the minimum data set required to transition `instantiated` → `posture-graded`?
3. Does `retired` immediately strip envelope+credentials, or is there a wind-down period for in-flight obligations?
4. Is `archived` runtime (read-only audit) or storage (cold)?
5. Can a Delegate fork (e.g. a Compliance Delegate spawning GDPR-Audit-2026)?

The state machine **edges are NOT formalised** beyond the arrow chain. The outline does not enumerate allowed transitions (e.g. "can active → retired be re-opened? must instantiated → posture-graded happen before any work?"). These are exactly the edges a kailash-py implementation needs to settle to be cross-verifiable with kailash-rs.

---

## 8. Spec Ground Beyond #1035 Acceptance Criteria

The outline covers 15 sections; #1035's scope explicitly names §3–§10 (mapping to outline Sections 1, 4–10). The following sections are in the outline but presumably outside #1035's first-pass scope. They are surfaced here because several of them carry MANDATED invariants kailash-py implementations will encounter at the boundary:

### Section 2 — Lifecycle (lines 54–64)

**Why it matters even though #1035 names §4 Genesis as the lifecycle proxy.** The 6-state chain (`proposed → instantiated → posture-graded → active → retired → archived`) is the temporal spine the outline says "every other section refers back to" (line 56). The issue body's `LifecycleTransition` enum implements this; #1035 work cannot ship without taking a position on the state machine edges.

### Section 3 — Role Binding (lines 67–76)

**Why it matters.** Section 8 Memory ownership (Q1, line 132) explicitly depends on the role-binding decision (Delegate bound to role? to human? to both?). And the Genesis Record's `role_binding` field (line 85) cannot be designed without the §3 answer. So §4 Genesis is downstream of §3 Role Binding even though #1035 only names §4.

### Section 11 — Human Interaction (Grant Moments, lines 173–183)

**Why it matters.** The MANDATED attestation surface in §9 Audit (line 140) names "the human grant that authorised the action class" as a record field. Without §11's Grant Moment shape, the audit record's grant reference field has no schema. PROPOSED time-bounded grants (P-11 above) imply the audit record needs to encode grant expiry.

### Section 12 — Multi-Delegate Coordination (lines 185–195)

**Why it matters.** I-14 above (Delegate-meets-Envoy mutual attestation, line 194) is a MANDATED cross-organization invariant. A kailash-py implementation that does not surface the messaging contract will not be able to interoperate with another organization's kailash-rs Delegate. The outline pre-stakes a position (line 191, "Recommendation candidate"): "a minimal messaging contract is part of the Delegate spec; richer orchestration patterns are a sibling spec."

### Section 13 — Sovereignty and Deployment (lines 197–207)

**Why it matters.** Four deployment tiers (public cloud / private cloud / on-prem / sovereign appliance). P-10 above mandates Delegate portability across tiers. If kailash-py is the OSS Python SDK and kailash-rs is proprietary, the portability invariant means a Delegate emitted by one MUST be loadable by the other after a tier migration.

### Section 14 — Versioning (lines 209–219)

**Why it matters.** P-7 (backward compat within minor) and P-8 (deprecation cycle) are PROPOSED but apply to both SDKs immediately. Spec capability advertisement in the Genesis Record (Q3, line 217) is OPEN — both SDKs likely need to add a `spec_version` field to Genesis Records before #1035 closes.

### Section 15 — Open Licensing (lines 221–231)

**Why it matters for kailash-py specifically.** kailash-py is Apache 2.0 OSS; kailash-rs is proprietary. Q4 (line 230, MANDATED-by-Apache-2.0): "May commercial implementations charge for runtime, certification, support? Yes." This explicitly permits the asymmetric licensing of the two SDKs. The trademark question (Q2, line 228) recommends "Delegate" the term stays untrademarked — so kailash-py can use the term freely.

### Cross-cutting from the Author's Note (lines 235–253)

- **Honesty discipline** (line 251, citing CLAUDE.md Directive 2): "The four production deployments (RRPS, TPC, HMI, RSAF) have implemented Delegate-shaped artifacts informally, before the spec existed. The spec must describe what _can be built_, not retroactively elevate what _has been built_ into more than it was." — Implication for kailash-py: do NOT extract canonical types from those production deployments and claim them as spec; flag any port as "pre-spec convention".

- **One trust system with two orientations** (line 243): Envoy (exterior) + Delegate (interior) share EATP / PACT / posture / CARE. kailash-py's Delegate impl shares substrate with any Envoy impl; the spec author has been explicit that they are NOT separate trust systems with a bridge.

- **The end-state v1.0 target** (line 253): "a 35–55 page document". The current outline is ~11 printed pages. The spec is roughly 25–40% complete by page count.

---

## Appendix — Citations Index

All line numbers reference `/Users/esperie/repos/dev/unicorn-focus/drafts/02-delegate-spec-v0-outline.md`.

| Topic                                         | Lines   |
| --------------------------------------------- | ------- |
| Status: pre-draft scaffold                    | 3–7     |
| Purpose & Scope                               | 11–36   |
| Delegate definition (1-sentence)              | 13, 44  |
| Five PACT envelope dimensions                 | 92      |
| Five posture states                           | 33, 104 |
| Six lifecycle states                          | 56      |
| Proposed Genesis Record fields                | 85      |
| Mandated audit record contents                | 140     |
| Mandated integration primitives               | 154–158 |
| Mandated cross-org mutual attestation         | 194     |
| Anti-over-specification discipline            | 247     |
| Honesty discipline (vs retroactive elevation) | 251     |
| v1.0 end-state target                         | 253     |
