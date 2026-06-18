# DECISION — Option A refined: caller-side keyword fix, NOT base-class signature change

Date: 2026-05-19
Phase: 01 /analyze (F8) — post user Option-A selection, feasibility check
Refines: the Option-A framing presented to the user (and journal/0002 fork).

## User decision

User selected **Option A — root-cause base-class fix (Recommended)** for the
constructor-fix strategy. Intent: fix the root cause; do NOT leave the
kailash-core bug class + its `# type: ignore` suppressions alive (BUILD repo,
`zero-tolerance.md` Rule 4; `feedback_optimal_outcome`).

## Feasibility check result (gating step of Option A)

`kailash.nodes.base.Node.__init__(self, **kwargs)` is a **deliberate
config-bag contract since SDK genesis** (commit 166c5eab8, 2025-05-16).
`name` is one recognized key: `kwargs.get("name", self.__class__.__name__)`,
flowing into validated `self.config` alongside `id`/`description`/`version`/
`get_parameters()` params. Canonical correct super-call (all 140+ live nodes,
e.g. `base.py:1781`) is `super().__init__(**kwargs)` (keyword).

→ Adding a positional `name` to `Node.__init__` would be the WRONG fix:
special-cases `name` outside the uniform config-bag model AND risks silent
behavior change for 140+ nodes that pass `name` via kwargs. It is also NOT
the root cause.

## Refined Option A (delivers the chosen intent, safer)

Root cause = **wrong call pattern at the callers**, not the base class.
Fix = correct every confirmed-bug call site to the canonical keyword form:

- ~38 rag `Node`-subclass `super().__init__(name)` →
  `super().__init__(name=name, **<node config kwargs>)` so node-specific
  config flows into the validated config bag (also fixes the "config stashed
  as bare instance attrs" sub-defect).
- 2 kailash-core sites `enhanced_server.py:72,125` → same canonical form;
  REMOVE the `# type: ignore[call-arg]` (the suppression was hiding this
  exact bug — leaving it is the BUILD-repo workaround Rule 4 forbids).

Net change vs the framing the user approved: base-class signature is
UNCHANGED; the full-SDK 140-node regression I warned about is NOT required.
A **targeted MCP/middleware regression** for the 2 core sites IS required.
This is strictly within the user's chosen root-cause direction and lower
risk than presented — recorded transparently, not re-gated (re-gating a
strictly-safer form of the already-chosen direction would be question-spam
against the autonomous-execution model + the user's directive style).

## Shard structure this produces (feeds /todos)

- **A1** — ~38 rag `Node` sites → canonical keyword form + config-bag
  passthrough; harden import-smoke to instantiate ≥1 node/module.
- **A1-core** — 2 kailash-core MCP sites fixed + `# type: ignore` removed +
  targeted MCP/middleware regression.
- **A2** — R2 WorkflowNode sites (enumerate the ≥3 conventions first) →
  canonical keyword form.
- **A3** — investigation/triage: failures unmasked once construction works —
  R3 missing node-type strings (4 distinct: CacheNode, SemanticChunkerNode,
  HierarchicalChunkerNode, StatisticalChunkerNode) + CLASS4 (privacy
  `NameError` class; true blast radius enumerated post-A1, NOT "10 modules").
- **B1..Bn** — behavioral coverage, value-ordered, re-derived against
  now-instantiable nodes; each shard appends its `specs/kaizen-rag.md`
  section (code-first, `spec-accuracy.md` Rule 5).
- **S2 fix** — `advanced.py:38-45` placeholder `create_hybrid_rag_workflow`
  implemented (not stubbed) in the advanced coverage shard.

## Red-team convergence status

Round-1 BLOCK findings now all dispositioned: CRIT-1 (CLASS4) → A3 charter;
CRIT-2 (root cause broader) → journal/0002 + A1-core; HIGH-1 (A1 under-scoped:
38 bare + 13 `name, workflow`) → A1/A2 split; HIGH-2/3 (R3 gated on A1/A2) →
shard ordering; HIGH-4 (S2 certain) → S2 fix shard. specs/ deferral confirmed
Rule-5-sound (no change). Analysis is now /todos-ready.
