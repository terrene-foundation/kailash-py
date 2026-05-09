# L3 ScopedContext — Hierarchical Context with Access Control

## What It Is

ScopedContext provides hierarchical context scopes with projection-based access control for multi-agent delegation. Each child scope sees a controlled, filtered subset of its parent's data.

## Key Concepts

- **ContextScope**: Tree of scopes with local data + parent reference
- **ScopeProjection**: Glob patterns controlling key visibility (allow/deny with deny precedence)
- **DataClassification**: 5 levels (PUBLIC=0, RESTRICTED=1, CONFIDENTIAL=2, SECRET=3, TOP_SECRET=4)
- **Parent traversal**: `get()` walks up the tree if key not found locally
- **Merge**: Child writes flow back to parent via `merge_child_results()`

## Usage

```python
from kaizen.l3.context import ContextScope, ScopeProjection, DataClassification

# Root scope (unrestricted)
root = ContextScope.root(owner_id="root-agent")

# Set values with classification
root.set("project.name", "kaizen", classification=DataClassification.PUBLIC)
root.set("secrets.api_key", "sk-xxx", classification=DataClassification.SECRET)

# Create restricted child scope
child = root.create_child(
    owner_id="child-agent",
    read_projection=ScopeProjection(allow_patterns=["project.**"], deny_patterns=[]),
    write_projection=ScopeProjection(allow_patterns=["results.*"], deny_patterns=[]),
    effective_clearance=DataClassification.CONFIDENTIAL,
)

# Child can see project.name (PUBLIC, within projection)
child.get("project.name")  # → ContextValue("kaizen")
# Child cannot see secrets.api_key (SECRET > CONFIDENTIAL clearance)
child.get("secrets.api_key")  # → None

# Child writes results
child.set("results.analysis", {"status": "complete"})

# Parent merges child results
merge_result = root.merge_child_results(child)
# merge_result.merged_keys: ["results.analysis"]
```

## Pattern Matching (AD-L3-13)

- `*` matches ONE segment: `project.*` → `project.name` (yes), `project.config.debug` (no)
- `**` matches ANY segments: `project.**` → both
- Deny takes absolute precedence over allow

## Invariants

- INV-1: Child read_projection always subset of parent's (monotonic tightening)
- INV-4: Classification filtering independent of projection filtering
- INV-7: Parent traversal for reads (lazy, not eager copy)
- INV-8: `remove()` is local only

## Reference

- Spec: Kaizen L3 scoped context brief
- Source: `kaizen/l3/context/`
