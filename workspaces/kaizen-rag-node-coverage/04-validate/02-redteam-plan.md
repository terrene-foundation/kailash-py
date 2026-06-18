# 04 — Red-Team of the F8 /todos Plan (pre-human-gate)

Adversarial review of `todos/active/00-plan.md` against its plan-inputs
(`01-analysis/03-reconciled-findings.md`, journal 0001/0002/0003,
`04-validate/01-redteam-analysis.md`). Every empirical claim re-verified
against `.venv` (kaizen editable + kailash 2.23.0) on `main` `0f906a1e0`,
2026-05-19 — not reasoned from the doc. Analysis is treated as converged;
this round audits **plan-translation fidelity only**.

**VERDICT: BLOCK** — the plan is directionally sound and the dependency
graph's headline claim is empirically TRUE, but it drops the single
highest-impact round-1 finding (CRIT-1 / R4) entirely and ships A1+A2 with
a module-scope error that will surface mid-`/implement`.

Finding count: **1 CRIT, 2 HIGH, 2 MED, 0 LOW**.

---

## 1. Finding → todo trace table

Every CRIT/HIGH from `04-validate/01-redteam-analysis.md` and every
plan-relevant finding in journal 0001/0002/0003, mapped to a plan todo.
"MAPPED" = a specific todo discharges it; "PARTIAL" = named but the
mechanical action is missing; "UNMAPPED" = gap.

| #   | Source         | Finding                                                                                                                                          | Plan todo                                                                   | Status                              |
| --- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- | ----------------------------------- |
| F1  | redteam CRIT-1 | R4 = f-string code-template single-brace interpolation leak; widespread-but-masked; A1/A2 UNMASK it; mandate Shard-A0 mechanical grep pre-flight | A3 (b) "CLASS4 — privacy NameError class"                                   | **PARTIAL → GAP**                   |
| F2  | redteam CRIT-2 | Root cause is kailash-core bug class, not rag-local; 2 `enhanced_server.py` sites are in-scope same-class fixes                                  | A1-core (both MCP sites + `# type: ignore` removal)                         | MAPPED                              |
| F3  | redteam HIGH-1 | Shard A1 under-scoped: 38 bare + 13 name+workflow split; `__init_with_capture` config-population contract                                        | A1 + A2 split; A1 "config-bag passthrough"                                  | **PARTIAL** (see HIGH-A)            |
| F4  | redteam HIGH-2 | R3 "PRESENT" set is mostly rag's own R1-broken nodes; only 3/15 resolve to core; A3 is A1-gated                                                  | A3 blocked-by A1,A2                                                         | MAPPED                              |
| F5  | redteam HIGH-3 | A3 strictly gated on A1+A2 (R3 masked behind R1/R2); plan must encode the edge                                                                   | Dependency graph `A1→A2→A3`; B7+B9 blocked-by A3                            | MAPPED                              |
| F6  | redteam HIGH-4 | S2 `create_hybrid_rag_workflow` is certain `ModuleNotFoundError`, not "may"                                                                      | A-S2 (implement real workflow)                                              | MAPPED (see MED-A)                  |
| F7  | redteam MED-1  | R1 = 39 on instantiation, grep-count 38; doc should pin 39                                                                                       | A1 "~38 sites"                                                              | **UNMAPPED** (cosmetic; see MED-B)  |
| F8  | redteam MED-2  | `WorkflowNode.__init__` is at `nodes/logic/workflow.py:32`, not `base.py:1765`                                                                   | A2 "Implements specs/core-workflows.md" (no file:line)                      | MAPPED (plan avoids the stale cite) |
| F9  | redteam MED-3  | "17 modules" → 16 code modules                                                                                                                   | A1/A3 ("16 modules", "16 modules")                                          | MAPPED                              |
| F10 | redteam LOW-1  | Name `specs/kaizen-rag.md` + add `_index.md` row in first authoring shard                                                                        | Milestone-B preamble (in-shard spec section)                                | MAPPED                              |
| F11 | journal 0001   | Import-smoke is a false floor; harden to instantiate ≥1 node/module                                                                              | A1 ("harden ... instantiate ≥1 node per module")                            | MAPPED                              |
| F12 | journal 0001   | 58/55/56 count reconciliation; `RAGPipelineWorkflowNode` `__all__`-orphan (orphan-detection Rule 6)                                              | B7 ("RAGPipelineWorkflowNode **all** fix"); B10 ("58/55/56 reconciliation") | MAPPED                              |
| F13 | journal 0001   | `graph.py`/`agentic.py` import intra-kaizen `..ai.llm_agent` (scope correction, not defect)                                                      | Out of scope (implicitly)                                                   | MAPPED (informational)              |
| F14 | journal 0002   | CLASS4 real, blast radius UNKNOWN until measured post-A1                                                                                         | A3 (b) "enumerate its TRUE blast radius across all 16 modules"              | **PARTIAL → GAP** (same as F1)      |
| F15 | journal 0003   | Option A refined: caller-side keyword fix, NOT base-class signature change; targeted MCP regression only                                         | A1 (caller-side keyword form); A1-core (targeted MCP/middleware regression) | MAPPED                              |
| F16 | journal 0003   | R3 4 distinct missing node-types (CacheNode, Semantic/Hierarchical/Statistical ChunkerNode)                                                      | A3 (a) (all 4 named)                                                        | MAPPED                              |

**Unmapped/partial findings: F1/F14 (CRIT-class), F3 (HIGH), F7 (MED).**

---

## 2. Per-shard capacity verdict

Against `.claude/rules/autonomous-execution.md` § Per-Session Capacity
Budget (≤500 LOC load-bearing / ≤5–10 invariants / ≤3–4 call-graph hops /
≤3-sentence describable). Empirically sanity-checked.

| Shard                        | Verdict                                          | Basis                                                                                                                                                                                                                                                                                                                                         |
| ---------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1                           | **OVER-SCOPED (module list wrong) — see HIGH-A** | 38 bare-name sites confirmed (`grep -c` = 38). One stamped pattern across boilerplate ctors → within budget AS a pattern. BUT the line-35-36 module list omits `optimized` and `multimodal`-as-R2 and conflates the 38/13 split. Capacity is fine; _scope correctness_ is not.                                                                |
| A1-core                      | WITHIN                                           | 2 sites (`enhanced_server.py:72,125`) + type-ignore removal + targeted regression. ≤2 invariants. 1-sentence describable.                                                                                                                                                                                                                     |
| A2                           | **UNDER-SPECIFIED — see HIGH-B**                 | 17 WorkflowNode subclasses confirmed (exact). 13 name+workflow super-calls span **9 modules**; STEP-1 enumeration scoped to only 4 (`workflows/strategies/graph/optimized`). STEP-2 says "correct all 17" so intent is total, but the enumeration that drives the edit is under-scoped → agent will under-fix. Capacity OK; scope spec wrong. |
| A3                           | WITHIN (investigation)                           | Disposition doc. Bounded inputs: 4 absent node-types (verified: optimized→CacheNode, strategies→3 chunkers), CLASS4 blast radius (verified: 1 confirmed module + 2 static — see below). Single shard.                                                                                                                                         |
| A-S2                         | WITHIN                                           | `advanced.py:38-45`, one workflow builder. `kaizen.workflow` confirmed absent (`ModuleNotFoundError`). Folded into B6.                                                                                                                                                                                                                        |
| B1 similarity (7)            | WITHIN                                           | ≤7 classes, one infra (numpy T1+T2a). No CLASS4 (empirically verified — see §3).                                                                                                                                                                                                                                                              |
| B2 graph (3)                 | WITHIN                                           | networkx T1+T2a. No CLASS4.                                                                                                                                                                                                                                                                                                                   |
| B3 agentic (3)               | WITHIN                                           | T1+T2a loopback. No CLASS4.                                                                                                                                                                                                                                                                                                                   |
| B4 multimodal (3)            | WITHIN                                           | Pillow T1+T2a. No CLASS4.                                                                                                                                                                                                                                                                                                                     |
| B5 federated (3)             | WITHIN                                           | T1+T2a. No CLASS4 (13 surviving interps all `{self.X}` builder-scope).                                                                                                                                                                                                                                                                        |
| B6 advanced (4)+A-S2         | WITHIN                                           | T1+T2b. advanced has 0 code-template f-strings; A-S2 folded.                                                                                                                                                                                                                                                                                  |
| B7 workflows+strategies (8)  | WITHIN, A3-gated                                 | strategies carries R4 (`fusion_method` leak) + 3 absent chunkers — correctly A3-gated.                                                                                                                                                                                                                                                        |
| B8 query_processing (6)      | WITHIN                                           | T1. 0 code-template f-strings; no R4.                                                                                                                                                                                                                                                                                                         |
| B9a privacy (3)              | WITHIN, A3-gated                                 | CLASS4 confirmed here (`pii_type`); correctly A3-gated.                                                                                                                                                                                                                                                                                       |
| B9b eval(3)+conv(2)          | WITHIN                                           | T1+T2a aiosqlite. conv/eval R4 interps all `{self.X}` — no NameError.                                                                                                                                                                                                                                                                         |
| B9c realtime(3)+optimized(4) | WITHIN, A3-gated                                 | optimized references absent CacheNode (R3) — B9 is A3-gated, correct.                                                                                                                                                                                                                                                                         |
| B10 router(3)+registry       | WITHIN                                           | T1. router has 0 code-template f-strings.                                                                                                                                                                                                                                                                                                     |

No shard exceeds the LOC/invariant/call-graph budget. The B9 split into
B9a/b/c is justified and correct. **Capacity is not the problem; scope
specification (A1/A2) and a missing class (R4) are.**

---

## 3. Dependency-graph verdict — **SOUND** (highest-value check)

The plan claims: `B1..B6,B8,B10 need only A1+A2`; only `B7+B9` need A3.
This is the highest-risk claim (an under-gated B shard burns a session).
**Empirically verified TRUE for CLASS4** by simulating the A1+A2 fix
(bypass the broken `super()`, populate ctor-default attrs, run
`_create_workflow()` on every WorkflowNode subclass) and classifying the
exception:

- **CLASS4 (NameError) confirmed in exactly ONE module**:
  `privacy.PrivacyPreservingRAGNode` → `NameError: name 'pii_type' is
not defined`. `privacy` = **B9a**, which IS A3-gated. ✅
- **strategies.py:240** `"fusion_method": "{fusion_method}"` is a second
  genuine R4 leak (static-pattern; `fusion_method` is a local inside the
  _generated_ code, undefined in builder scope). `strategies` = **B7**,
  which IS A3-gated. ✅
- **R3 absent-node-type references**: `optimized` → `CacheNode`
  (= B9c, A3-gated ✅); `strategies` → 3 chunkers (= B7, A3-gated ✅).
- **B1–B6 (similarity/graph/agentic/multimodal/federated/advanced)**:
  every surviving f-string interpolation is `{self.X}` — builder-scope
  config injection, NOT a bare-local-name NameError. Instantiation test
  raised ZERO CLASS4 across all six. **They genuinely run on A1+A2
  alone.** ✅

**The gating is correct.** Every module carrying a latent CLASS4/R3
defect (privacy, strategies, optimized) lands in an A3-gated shard
(B7/B9a/B9c). No B1–B6/B8/B10 shard is under-gated. The plan's
sequencing claim is empirically defensible — this is the plan's
strongest section.

Caveat (folds into CRIT-A): this verdict was only _derivable_ by running
the exact mechanical audit redteam CRIT-1 mandated as Shard-A0. The plan
provides no such pre-flight, so the next session has no structural way to
reproduce this confidence — it would re-derive it by hitting the failures
mid-`/implement`, the precise anti-pattern HIGH-3 named.

---

## 4. Build/wire-collapse verdict — **SOUND**

The /todos workflow mandates separate build vs wire todos for
data-consuming components. The plan argues (lines 108-112) coverage
shards inherently fuse them because the Tier-2/3 real-infra assertion IS
the wiring (NO MOCKING per `rules/testing.md`).

Adversarial reading: this is not a forbidden collapse. The build-vs-wire
separation exists to prevent "endpoint exists but returns mock data"
(zero-tolerance Rule 2/6). Here the unit-of-work is a _coverage shard
over already-built nodes_ — the nodes exist post-A; the shard's job is to
prove they behave against real infra. A passing Tier-2 assertion against
real numpy/networkx/aiosqlite cannot be satisfied by an unwired node, so
build and wire are not separable artifacts here — they are one
verification. The argument is sound AND it cites the controlling rule
(`testing.md` NO-MOCKING) rather than asserting convenience. No finding.

One narrowing: A-S2 (`create_hybrid_rag_workflow`) IS a genuine build
(net-new workflow body), distinct from coverage. The plan correctly
calls it out as a separate todo "implemented, not stubbed-around"
(line 99) and blocks it on A1. Correctly handled.

---

## 5. Findings

### CRIT-A — R4 (f-string code-template leak) is dropped as a named class; the mandated Shard-A0 pre-flight is absent

Round-1 redteam CRIT-1 (the explicitly-labeled "single highest-impact
omission") requires the analysis/plan to: (1) add **R4** as a distinct
class, (2) state that R1/R2 fixes UNMASK R4, (3) **mandate a Shard-A0
mechanical grep pre-flight** for single-brace `{ident}` inside
`code=f"""..."""` blocks, "not a /redteam afterthought."

The plan does NONE of these. It folds R4 into A3(b) as "CLASS4 — the
privacy `NameError` class" and — worse — actively _understates_ it:
lines 80-81 say _"the round-1 red-team's '10 modules / `code=f\"\"\"`'
was unverified — `grep code=f\"\"\"` = 0; real surface unknown until
measured."_ The `grep code=f"""` = 0 result is a **false-negative from
the wrong grep pattern**: the actual source uses `"code": f"""` (dict
key form). The correct AST scan finds code-template f-strings in **12
modules** and **3 confirmed genuine leaks**: `privacy.py:152`
(`pii_type`/`hash_value`), `privacy.py:221` (`pattern`/`replacement`),
`strategies.py:240` (`fusion_method`). The plan's own text would lead
the next session to believe R4's surface is unknown/speculative when it
is mechanically enumerable in ~1 second.

Consequence: A3 is an _investigation_ shard with no mechanical R4
detector specified. The next session re-derives R4's surface by hitting
NameErrors mid-coverage — the exact `autonomous-execution.md`
"defer-sharding-to-/implement is BLOCKED" anti-pattern HIGH-3 was raised
to prevent. The dependency graph happens to be correct (§3), but the
plan provides no structural way to know that; it got the right answer
without the mandated method.

**Required fix:** add an **A0 pre-flight todo** (before A1): mechanical
AST/grep audit of every `"code": f"""` / `code = f"""` / `code=f"""`
block for surviving single-brace interpolations whose expression is NOT
`self.<attr>` (those are intentional config injection) → that residue is
the R4 leak set. Output feeds A3's disposition table. Name R4 as the 4th
class in the plan body. Correct the lines 80-81 false-negative framing
with the verified count (3 confirmed leaks: privacy ×2 sites,
strategies ×1).

### HIGH-A — A1 module list (lines 35-36) is wrong and conflates the 38/13 split

A1's scope sentence lists "~38 sites across similarity/agentic/
conversational/evaluation/federated/graph/multimodal/query_processing/
realtime/router/strategies/advanced." This omits `optimized` (4 R2
sites) entirely and presents all 38 as one homogeneous "single pattern."
Empirically: 38 bare-name + 13 name+workflow = 51 super-call sites; the
13 span 9 modules (agentic, conversational, evaluation, federated,
graph, multimodal, optimized, privacy, realtime). The plan DID split
A1/A2 (absorbing HIGH-1's headline) and A1's "single pattern" framing is
defensible _for the 38 bare-name sites only_ — but the module list reads
as if A1 covers a module's whole constructor surface, when in 9 of those
modules the name+workflow sites belong to A2. An A1 agent following the
line-35-36 list will either touch A2's sites (scope collision) or leave
a module half-fixed. **Required fix:** A1 scope MUST state "38
bare-name `super().__init__(name)` sites; the 13 name+workflow sites in
the same modules are A2, not A1" and cite the `__init_with_capture`
(`src/kailash/nodes/base.py:282-304`) config-population contract as the
post-fix invariant (redteam HIGH-1 item (b), currently unmapped).

### HIGH-B — A2 STEP-1 enumeration scope (4 modules) under-covers the 9-module R2 surface

A2 STEP 1 says "enumerate the ≥3 distinct WorkflowNode super-call
conventions across workflows.py/strategies.py/graph.py/optimized.py."
The 13 name+workflow (R2) sites span **9 modules**, not 4 — the
enumeration step that drives STEP-2's fix is scoped to fewer than half
the surface. STEP-2 ("correct all 17") states total intent, but an agent
enumerates conventions from the 4 named files, then applies them; a
convention unique to `realtime`/`federated`/`privacy` etc. is missed.
Also empirically: `strategies.py` has BOTH shapes (4× bare
`super().__init__(name)` at :385/432/482/537 AND name+workflow), and
`graph` carries only 1 R2 site — the "≤3 conventions across these 4
files" framing is an undercount of where the conventions actually live.
**Required fix:** A2 STEP-1 scope = all 9 modules holding a
`super().__init__(name, self._create_workflow())` site (enumerate via
`grep -rl`), not the 4-file list.

### MED-A — A-S2 inherits the "may not exist" hedge redteam HIGH-4 explicitly corrected

A-S2 (line 93-96) describes the placeholder but does not state the
defect is **certain**: `kaizen.workflow` is confirmed absent
(`ModuleNotFoundError: No module named 'kaizen.workflow'`). redteam
HIGH-4 required restating it as certain, upgrading the 4 consumer nodes
(`SelfCorrectingRAGNode`/`RAGFusionNode`/`HyDENode`/`StepBackRAGNode`)
from "investigate" to "known in-shard fix." Plan still reads as
discovery. Low blast radius (A-S2 implements it regardless) but the
sizing signal is lost. **Fix:** state the `ModuleNotFoundError` as
certain in A-S2.

### MED-B — R1 count: plan says "~38", redteam MED-1 pinned 39-on-instantiation

`grep -c 'super().__init__(name)'` = 38 (I reconfirmed). redteam MED-1
says instantiation-classification yields R1 = 39 (one class reaches the
same `Node.__init__()` error via a call shape the literal grep misses).
The plan's "~38" hedge technically covers it but A1's "Done when: every
targeted node constructs" is the real gate, so the off-by-one is
cosmetic IF A1's acceptance is "all construct" rather than "38 edited."
**Fix:** A1 acceptance should be construction-based for ALL Node
subclasses (already is — "every targeted node constructs"), and the
prose should pin 39 to avoid an agent treating 38 as a checklist
length.

---

## 6. Verdict

**BLOCK.** The plan is directionally correct, its dependency graph is
empirically SOUND (the highest-risk claim — verified, §3), its
build/wire-collapse argument is rule-grounded and valid (§4), and 12 of
16 traced findings are cleanly mapped. But it ships to the human gate
with:

- **CRIT-A**: the round-1 "single highest-impact omission" (R4 + the
  mandated A0 mechanical pre-flight) is dropped as a named class AND the
  plan's own lines 80-81 understate R4 with a false-negative grep. The
  dependency graph is right by luck of analysis, not by the structural
  pre-flight that would let the next session reproduce the confidence.
- **HIGH-A / HIGH-B**: A1's module list and A2's STEP-1 enumeration
  scope are both narrower than the empirical surface; an `/implement`
  agent following them under-fixes or collides scopes mid-shard.
- **MED-A / MED-B**: residual hedges redteam round-1 explicitly told
  the plan to harden.

**Plan gaps that MUST be fixed before the human gate:**

1. Add **A0 mechanical R4 pre-flight todo** (before A1); name R4 as the
   4th class in the plan body; correct lines 80-81 to the verified
   count (3 confirmed leaks: `privacy.py:152`, `privacy.py:221`,
   `strategies.py:240`). [CRIT-A]
2. Fix A1 scope: "38 bare-name sites; the 13 name+workflow sites in
   shared modules are A2"; cite `__init_with_capture`
   (`base.py:282-304`) as the post-fix invariant. [HIGH-A]
3. Fix A2 STEP-1 scope: enumerate conventions across **all 9** modules
   holding a `name, self._create_workflow()` site, not the 4-file list.
   [HIGH-B]
4. Restate A-S2's `kaizen.workflow` defect as certain
   (`ModuleNotFoundError`). [MED-A]
5. Pin R1 = 39 in A1 prose; keep construction-based acceptance. [MED-B]

The dependency-graph and build/wire sections need NO change — they are
the plan's strongest, and §3's empirical confirmation should be carried
forward into A3's disposition doc rather than re-derived.
