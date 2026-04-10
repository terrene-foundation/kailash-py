# Parallel Worktree Merge Workflow

When multiple agents modify the same file in parallel worktrees, use this workflow to merge their changes deterministically.

## When to Use

- 3+ agents implementing independent features that all touch the same central file (e.g., `engine.py`, `base_agent.py`)
- Each agent's worktree passes its own tests in isolation
- The main tree has diverged from HEAD during the session (e.g., unrelated fixes applied)

## The Merge Protocol

### 1. Identify unique variants

Each worktree branches from the committed HEAD and applies ONE feature. Filter worktrees by feature marker:

```bash
for wt in .claude/worktrees/agent-*/; do
    f="${wt}src/kailash/trust/pact/engine.py"
    [ -f "$f" ] || continue
    n1=$(grep -c "KnowledgeFilter" "$f")
    n2=$(grep -c "_envelope_cache" "$f")
    n3=$(grep -c "suspend_plan" "$f")
    # One worktree per feature
    [ "$n1" -gt 0 ] && echo "$(basename $wt): N1"
done
```

### 2. Generate per-feature diffs vs HEAD

Each diff isolates one feature's additions without entanglement:

```bash
git show HEAD:src/kailash/trust/pact/engine.py > /tmp/engine_head.py
diff -u /tmp/engine_head.py .claude/worktrees/agent-XXX/src/kailash/trust/pact/engine.py > /tmp/n1.patch
```

### 3. Delegate the merge to a specialist

Do NOT try to apply patches with `patch` — line offsets will drift. Instead, hand the diffs to a specialist agent with explicit injection point documentation:

```
For each feature, tell the agent:
- Which imports to add
- Which __init__ params to add (and ordering)
- Which __init__ body fields to initialize
- Which methods to add (new)
- Which existing methods to modify (and where)
```

The agent reads the current main tree file and applies changes section by section using Edit.

### 4. Handle interaction points

Features that both touch the same method need explicit ordering instructions. Example from the PACT N1-N5 merge:

- N2 and N5 both add code to `grant_clearance`, `approve_bridge`, `set_role_envelope`
- N2 adds cache invalidation INSIDE the lock
- N5 adds observation emits OUTSIDE the lock (after audit)
- Both must be present; document the order explicitly

### 5. Verify with tests

Run the specialist's own test suite to verify the merge compiles and all features work together. Then run the project-wide suite to catch regressions from interaction points.

## Anti-Patterns

- **Sequential worktree rebasing**: Each rebase fights the previous merge's line shifts
- **Cherry-picking across worktrees**: Loses the per-feature test verification
- **Manual three-way merge**: Error-prone for 5+ concurrent features
- **Trusting the "individually passing" claim**: Interaction points are rarely tested in isolation — always re-run full suite after merge

## Origin

2026-04-10 session: 5 PACT conformance features (N1 KnowledgeFilter, N2 EnvelopeCache, N3 PlanSuspension, N4 AuditTiers, N5 ObservationSink) merged from 5 independent worktrees into `engine.py` (2329 → 3211 lines). All 1192 PACT tests passed on first merged run after specialist applied the changes with explicit injection-point documentation.
