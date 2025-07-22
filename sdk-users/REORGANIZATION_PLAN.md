# SDK Users Folder Reorganization Plan

## Current Issues

The current sdk-users folder has 27 top-level directories with significant redundancy:
- **10 pairs of overlapping folders** identified
- **Unclear navigation** - difficult to know where to find information
- **Duplicate content** - same concepts explained in multiple places
- **No clear user journey** - beginners don't know where to start

## Proposed New Structure

```
sdk-users/
├── README.md                    # Main navigation hub
├── CLAUDE.md                    # Claude Code instructions
├── decision-matrix.md           # Architecture decisions
│
├── 1-quickstart/               # START HERE - New users
│   ├── README.md               # Getting started guide
│   ├── installation.md         # Installation instructions
│   ├── first-workflow.md       # Hello world workflow
│   └── common-patterns.md      # Basic patterns to copy
│
├── 2-core-concepts/            # Learn the fundamentals
│   ├── nodes/                  # Node catalog and selection
│   ├── workflows/              # Workflow examples by pattern
│   ├── cheatsheet/            # Quick reference patterns
│   └── validation/            # Common mistakes and fixes
│
├── 3-development/             # Build real applications
│   ├── README.md              # Development guides index
│   ├── [existing dev guides]  # All current developer/ content
│   └── testing/               # Testing strategies
│
├── 4-features/                # Advanced capabilities
│   ├── mcp/                   # Model Context Protocol
│   ├── edge/                  # Edge computing
│   ├── middleware/            # Middleware patterns
│   └── [other features]       # Feature-specific guides
│
├── 5-enterprise/              # Production deployment
│   ├── security/              # Security patterns + validation
│   ├── monitoring/            # Monitoring and observability
│   ├── production/            # Production deployment guides
│   └── patterns/              # Enterprise patterns
│
├── 6-reference/               # API and technical reference
│   ├── api/                   # Consolidated API reference
│   ├── migration-guides/      # Version migration guides
│   └── changelogs/            # Release notes
│
└── examples/                  # Working code examples
    ├── by-industry/           # Industry-specific workflows
    └── production-examples/   # Real production patterns
```

## Migration Actions

### 1. **Remove Redundant Folders**
- `api/` → Keep only `api-consolidated/` renamed to `6-reference/api/`
- `guides/` → Move single file to `3-development/`
- `security/` → Move to `5-enterprise/security/`
- `production/` → Merge into `5-enterprise/production/`

### 2. **Consolidate Similar Content**
- `patterns/` + `production-patterns/` → `examples/`
- `features/` → Split between `4-features/` and `5-enterprise/`

### 3. **Reorganize Stray Files**
- `admin-nodes-quick-reference.md` → `2-core-concepts/nodes/`
- `node-catalog.md` → `2-core-concepts/nodes/`
- `validation-guide.md` → `2-core-concepts/validation/`
- `api-registry.yaml` → `6-reference/api/`
- Infrastructure guides → `5-enterprise/production/`

## Benefits

1. **Clear Learning Path**: Numbered folders guide users from beginner to advanced
2. **No Duplication**: Each concept has one authoritative location
3. **Better Discovery**: Related content grouped logically
4. **Easier Maintenance**: Clear ownership of each section
5. **Claude Code Friendly**: Simple navigation structure

## Implementation Priority

1. **Phase 1**: Create new folder structure
2. **Phase 2**: Move non-conflicting content
3. **Phase 3**: Merge redundant content
4. **Phase 4**: Update all cross-references
5. **Phase 5**: Update root CLAUDE.md navigation

## Folders to Keep As-Is

These folders have clear, non-overlapping purposes:
- `nodes/` - Node documentation
- `cheatsheet/` - Quick reference
- `changelogs/` - Version history
- `instructions/` - Internal instructions
- `apps/` - App framework docs

## Next Steps

1. Review and approve this plan
2. Create backup of current structure
3. Execute reorganization
4. Update all documentation references
5. Test navigation paths