---
type: ANALYSIS
slug: 1532-dc-consolidation-architecture
date: 2026-07-13
issue: 1532
grant: journal/0029 (cross-repo reads EXERCISED)
phase: 01-analyze
gate: /todos (structural model ratification + cross-repo-WRITE authorization)
---

# ANALYZE — #1532 delegate-connectors → `contrib/` consolidation

Four parallel evidence-cited reads (1 in-repo framework surface + 3 cross-repo under grant
`0029`: OSS specs authority, OSS `dc` source, `dce`+`rs` anchor). Errored first-wave (weekly
limit) → re-run on fresh account per `evidence-first-claims.md` MUST-3. All four landed clean.

## Executive summary

#1532 is a **multi-shard program with a materially stale brief**, not a one-session task. The
issue body's target structure `contrib/delegate-connectors/{ingress,connectors,conformance,catalog}`
is the **enterprise Rust** shape (`dce`/`repo-layout.md`), NOT the shape the **OSS Python specs**
(`monorepo-layout.md`) mandate for the connectors actually being migrated. Two gates block `/todos`:
(1) a structural-model decision the specs surface but do not resolve, and (2) a cross-repo WRITE
authorization (with-history migration + standalone-repo archive) that grant `0029` explicitly does
NOT cover.

## Brief corrections (issue #1532 body vs ground truth)

| #   | Issue #1532 says                                                                                            | Ground truth (evidence)                                                                                                                                                                                                                                       | Impact                                                                                                               |
| --- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| BC1 | Connectors are `ingress/{ingress-core,whatsapp,email}` + `connectors/{connectors-core,sap,m365,salesforce}` | OSS `dc` is **Phase-0**: `host/` + `connectors/{telegram,slack,email,whatsapp}` — 4 messaging connectors + 1 host. NO sap/m365/salesforce, NO ingress-core/connectors-core (`dc` inventory §0/§2)                                                             | The `{ingress,connectors}` split has nothing to populate `ingress/` with; sap/m365/salesforce don't exist to migrate |
| BC2 | Target dir `{ingress,connectors,conformance,catalog}`                                                       | That is the **enterprise `repo-layout.md`** shape. OSS `monorepo-layout.md:3` mandates a **flat `connectors/<channel>/`** tree; OSS connectors are all single `Connector`-ABC impls doing read+write — there is **no OSS "intake adapter" kind** (specs §8.1) | The specs do NOT sanction #1532's dir shape for these connectors as-is → **DECISION D1**                             |
| BC3 | "each connector is its own package with its own version + PyPI publish cadence"                             | Matches OSS `monorepo-layout.md:40` — BUT the `dc` `CHANGELOG.md` currently says the 4 connectors "release together at a shared version" (`dc` inventory §2, flag 5)                                                                                          | Independent-vs-shared versioning is unresolved in the source → **DECISION D2**                                       |

## What is authoritative (co-owner directive: "align to specs, not copy blindly")

Two spec suites exist (specs §0). For a **public kailash-py** consolidation the authority split is:

- **OSS suite** (`dc/specs/`, Apache-2.0) governs: license, Python packaging (PEP 420 namespace
  `delegate_connectors.<channel>`, per-package dist `delegate-connector-<channel>`), the `Connector`
  ABC surface, real-infra test discipline.
- **Enterprise suite** (`dce/specs/`, proprietary) governs (as a _pattern to align to, not copy_):
  independent-semver/release-train policy, the catalog-`index.json` schema, matrix-CI mechanism.
- **`dce`+`rs` are references, NOT copy targets.** `rs` is the SPINE `dce` consumes (direction is
  `dce → rs`, anchor §2 — corrects the issue's implied `rs → dce`). Enterprise-only artifacts to
  SKIP: private-SSH pinned-git spine consumption, `publish=false`/proprietary licensing + its F1
  leak threat model, self-hosted-runner CI (anchor §4 deltas 9-12).

## In-repo framework surface (dependency target for connectors)

`kailash.delegate` exposes 51 top-level `__all__` names; the **connector-authoring surface is wider**
— `dispatch.__all__` has 10 symbols (`Principal`, `SignedActionEnvelope`, `AttestedReadReceipt`,
`RevocationChannel`, `KnowledgeLedger`, `AuthVerifier`, `SignatureContract`, `LegacyInvokeConnector`,
+2 errors) NOT re-exported at package top. Connectors import from BOTH `kailash.delegate` and
`kailash.delegate.dispatch`. Two hard fences (`tools/lint-delegate-fences.py`): Fence A (delegate
stays Apache-2.0-pure, no proprietary import), Fence B (`conformance/` is engine-free). A `contrib/`
conformance harness inherits Fence B. **Native canonical set already lives here**:
`tests/fixtures/delegate-conformance/canonical.json` (schema_v1, digest `770d539e…`, 5 vectors
DV-3/5/7/9/10) — so for this consolidation the vectors are NATIVE, not vendored → the `dc` loaders'
`parents[4]`-ascent + vendoring-provenance block become self-referential and simplify (specs §8.4).

Full delegate test baseline (parity target): 15 unit + 8 integration + 1 e2e + 5 regression + fixtures.

## Migration mechanics (OSS `dc` inventory)

- Standalone git repo, **114 PR-driven commits** (`6e47dc8` scaffold → `0a60e44` PR#30). With-history
  migration is feasible and worth doing.
- 5 packages, hatchling, `requires-python>=3.10`, Apache-2.0, `kailash>=2.28.0` (kailash-py is 2.48.1 ✓).
  `host` = `delegate-connectors-host` 0.1.0; 4 connectors = `delegate-connector-<channel>` 0.1.0.
- Dependency direction CLEAN: connectors→`kailash.delegate` + connectors→`host`; host→connectors NONE
  (verified, `dc` §3).
- **No package CI matrix exists** — the catalog-driven changed-package matrix must be AUTHORED, not
  ported (`dc` §4). Only COC-structure workflows are present.
- Tensions to reconcile: dist wheels 0.1.1 ahead of source/CHANGELOG 0.1.0 (recommend: drop `dist/`,
  source is truth); `host` is unpublished + unpinned intra-repo dep (→ path/workspace dep in `contrib/`).

## DECISIONS gating /todos (recommendations attached)

**D1 — Structural model (CRITICAL).** Flat OSS `connectors/<channel>/` (spec `monorepo-layout.md`)
vs the issue's `{ingress,connectors}` split (enterprise shape).
→ **RECOMMEND: flat `contrib/delegate-connectors/{host,connectors/<channel>,conformance,catalog}`,
aligned to the OSS `monorepo-layout.md`.** Rationale: the 4 OSS connectors are all `Connector`-ABC
impls (read+write in one class); nothing populates `ingress/`; splitting would require an
architectural refactor the OSS specs do NOT describe. Adopt the enterprise catalog + matrix-CI
_mechanism_ (D-anchor patterns to FOLLOW) without the two-tree dir split. Confidence: HIGH
(spec-grounded + co-owner "align to specs" directive).

**D2 — Versioning.** Independent per-package (issue + `monorepo-layout.md:40`) vs shared (current
CHANGELOG). → **RECOMMEND: independent semver per package** (spec-aligned; decouples protocol-chase
from the host's cadence). Confidence: HIGH.

**D3 — host dependency wiring.** → **RECOMMEND: `[tool.uv.sources]` editable path entry** per
`python-environment.md` Rule 3 (`delegate-connectors-host = { path = "...", editable = true }`), NOT
a PyPI pin. Confidence: HIGH.

**D4 — Version reconciliation.** → **RECOMMEND: source/CHANGELOG (0.1.0) is truth; do NOT migrate
`dist/` built wheels.** Confidence: HIGH.

**D5 — Cross-repo WRITE authorization (BLOCKING, human-only).** The with-history migration writes
114 commits of another repo into kailash-py AND archives the standalone `dc` repo. Grant `0029`
authorized READS only. This needs its own per-action confirm+journal, AND kailash-py is a BUILD repo
→ commits stay with the co-owner. Two sub-questions: (a) authorize the with-history import mechanism
(git subtree/filter-repo) into `contrib/`? (b) authorize archiving the standalone `dc` repo with a
redirect pointer (issue AC#4)? Confidence: N/A — human envelope decision.

## Recommended shard plan (multi-session program — sized per autonomous-execution capacity)

Gated on D1-D5 ratification. Assuming D1=flat, D2=independent:

- **S1** — Scaffold `contrib/delegate-connectors/` skeleton + root packaging + `[tool.uv.sources]`
  wiring for host + 4 connectors (no history yet); land the two fence-analogues (connectors→framework
  one-way) + SPDX headers. (~boilerplate-heavy, 1 shard)
- **S2** — With-history migration of the 5 packages (git subtree/filter-repo import preserving the
  114-commit history) into the scaffold. (mechanics shard; gated on D5a)
- **S3** — Author the catalog `index.json` + `index.md` mirror + catalog-invariant tests +
  changed-package matrix CI (does not exist in source; author per enterprise mechanism). (load-bearing)
- **S4** — Conformance consolidation: single native harness over `tests/fixtures/.../canonical.json`
  (Fence B preserved), retire the 4 duplicated per-connector loaders' vendoring-ascent. (load-bearing)
- **S5** — Test-parity verification (15+8+1+5 delegate baseline + the connectors' own 91 test files),
  real-infra Tier-2 (Mailpit/GreenMail/doubles), green CI. (verification)
- **S6** — Archive the standalone `dc` repo with redirect pointer (AC#4; gated on D5b) + CHANGELOG
  migration section + docs.

Each shard ≤ the capacity budget; S2/S6 gated on the D5 cross-repo-write authorization.

## Next action

Gate at /todos: co-owner ratifies D1-D5 (recommendations above). No BUILD code written this session —
`/analyze` complete; the migration is a structural-gated program. Nothing to `/redteam` yet (no
in-flight change); the redteam target is each shard's PR once D1-D5 land and implementation begins.
