# Propagating CO Setup Updates

How to apply updates from the canonical source to other repositories.

## Canonical Source

The canonical source repository for shared CO components is:

- Core workflow improvements (implement.md, codify.md, todos.md)
- Shared agents (analysis, review, management, standards experts)
- Guides (claude-code, co-setup)
- Shared rules (git.md)

## What to Propagate

### Always propagate

| Component               | Files                                   | Reason                                                                       |
| ----------------------- | --------------------------------------- | ---------------------------------------------------------------------------- |
| Core workflow structure | `implement.md`, `codify.md`, `todos.md` | Shared improvements (completion evidence, decision log, pattern observation) |
| Utility commands        | `ws.md`, `wrapup.md`, `checkpoint.md`   | Identical across all repos                                                   |
| Guides                  | `co-setup/`, `claude-code/`             | Universal reference material                                                 |

### Propagate with adaptation

| Component                      | Adaptation needed                        |
| ------------------------------ | ---------------------------------------- |
| `implement.md` agent teams     | Replace with project-appropriate agents  |
| `codify.md` agent teams        | Replace with project-appropriate agents  |
| `todos.md` expert consultation | Replace with project-appropriate experts |

### Never propagate

| Component                 | Reason                                                                        |
| ------------------------- | ----------------------------------------------------------------------------- |
| `start.md`                | Project-type-specific orientation                                             |
| `analyze.md`              | Project-type-specific research framework                                      |
| `redteam.md`              | Project-type-specific testing approach                                        |
| Archetype-specific agents | SDK agents don't apply to governance; governance agents don't apply to coding |
| Archetype-specific skills | Domain knowledge is project-specific                                          |
| Archetype-specific rules  | Different strictness levels and concerns                                      |
| Project-specific hooks    | Different validation and enforcement needs                                    |

## How to Propagate

### Step 1: Identify what changed

```bash
# In the terrene repo
git diff --name-only HEAD~N -- .claude/commands/ .claude/guides/ .claude/rules/
```

### Step 2: Classify each change

For each modified file, determine:

- **Shared structure change** (e.g., new workflow step in implement.md) → Propagate to all repos
- **Terrene-specific content change** (e.g., new governance agent in implement.md agent teams) → Do not propagate
- **New shared component** (e.g., new guide) → Propagate to all repos

### Step 3: Apply changes

**For shared structure changes** (like adding completion evidence to implement.md):

1. Read the target repo's version of the file
2. Identify the insertion point (same section structure)
3. Insert the new content while preserving existing project-specific content
4. Verify step numbering is consistent

**For new shared components** (like this guide):

1. Copy the entire directory/file to the target repo
2. No adaptation needed

### Step 4: Verify

After propagation, verify:

- [ ] Step numbering is consistent in each command
- [ ] Agent teams reference agents that exist in the target repo
- [ ] No terrene-specific references leaked (anchor docs, constitution, publications)
- [ ] All shared content is identical across repos

## Repository Inventory

Maintain a project-specific inventory of repositories that share CO components. Each repo should list:

- Repository name
- Archetype (Coding, Governance, Education, Platform)
- Which shared components it uses

This inventory is internal to your organization and should NOT be committed to public repositories.

## Automation

For batch propagation, use parallel agents:

1. Group repos by similarity (same archetype = same edits)
2. Launch one agent per group with explicit edit instructions
3. Each agent reads the target file first, then applies targeted edits
4. Preserve all existing project-specific content
