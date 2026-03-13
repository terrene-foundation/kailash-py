# Management Skills

## Quick Patterns

Management skills handle internal COC infrastructure and synchronization workflows.

### COC Sync Mapping

The sync mapping defines transformation rules for syncing BUILD repo artifacts to COC template:

```yaml
# Categories of transforms during sync
Category 1: As-Is # No transform needed, copy directly
Category 2: Strip Paths # Remove builder-specific source paths
Category 3: Fix Abs Paths # Convert absolute paths to relative
Category 4: Rule Softening # MUST -> SHOULD for user-facing rules
Category 5: CLAUDE.md # Full rewrite for user context
```

### Exclusions (Never Sync)

```
agents/management/coc-sync.md         # Sync infrastructure (meta)
skills/management/coc-sync-mapping.md  # Sync infrastructure (meta)
rules/learned-instincts.md             # Auto-generated per repo
learning/                              # Per-repo learning data
```

### Global Strip Patterns

```
src/kailash/                              # Internal SDK source - NEVER sync
packages/kailash-dataflow/src/                # Internal DataFlow source
packages/kailash-kaizen/src/                  # Internal Kaizen source
packages/kailash-nexus/src/                   # Internal Nexus source
# contrib (removed)/                         # Builder-only docs
```

## Critical Gotchas

- NEVER sync internal source paths (`src/kailash/`, `apps/kailash-*/src/`)
- NEVER sync absolute paths (`
- NEVER sync learning data or auto-generated instincts
- Always preserve user-facing imports (`from kailash.workflow.builder import WorkflowBuilder`)

## Related Skills

- `.claude/skills/management/coc-sync-mapping.md` - Full transformation rules and mapping tables

## Full Documentation

When this guidance is insufficient, consult:

- `coc-sync-mapping.md` - Complete sync mapping with all categories and patterns
