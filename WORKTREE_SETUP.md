# Git Worktree Setup for Parallel Development

**Created**: 2025-10-07
**Purpose**: Work on VS Code extension and React web app in parallel

---

## Worktree Locations

You now have **3 separate working directories**:

### 1. Main Repository (Current Branch)
- **Path**: `./repos/projects/kailash_python_sdk/`
- **Branch**: `feature/kaizen-developer-experience-improvements`
- **Purpose**: Backend development, deployment fixes
- **Status**: ✅ All services deployed

### 2. VS Code Extension Worktree
- **Path**: `./repos/projects/kailash_python_sdk_vscode/`
- **Branch**: `feature/vscode-python-visualization`
- **Purpose**: Python code visualization feature
- **Based on**: `main` branch (clean slate)

### 3. React Web App Worktree
- **Path**: `./repos/projects/kailash_python_sdk_webapp/`
- **Branch**: `feature/react-web-app-enhancements`
- **Purpose**: Workflow search, execution UI, advanced features
- **Based on**: `main` branch (clean slate)

---

## How to Use Worktrees

### Open in Separate VS Code Windows

```bash
# Terminal 1 - VS Code Extension work
cd ./repos/projects/kailash_python_sdk_vscode
code .

# Terminal 2 - React Web App work
cd ./repos/projects/kailash_python_sdk_webapp
code .

# Terminal 3 - Backend/deployment work (optional)
cd ./repos/projects/kailash_python_sdk
code .
```

### Navigate to Each Worktree

```bash
# VS Code Extension
cd ../kailash_python_sdk_vscode
cd apps/kailash-studio/vscode-extension

# React Web App
cd ../kailash_python_sdk_webapp
cd apps/kailash-studio/frontend

# Main repo
cd ./repos/projects/kailash_python_sdk
cd apps/kailash-studio
```

---

## Worktree Commands

### List All Worktrees

```bash
git worktree list
```

**Output**:
```
./repos/projects/kailash_python_sdk         9cf065088 [feature/kaizen-developer-experience-improvements]
./repos/projects/kailash_python_sdk_vscode  ca3ccc6bd [feature/vscode-python-visualization]
./repos/projects/kailash_python_sdk_webapp  ca3ccc6bd [feature/react-web-app-enhancements]
```

### Check Current Branch (in any worktree)

```bash
git branch --show-current
```

### Commit in Each Worktree Independently

Each worktree is **independent** - you can commit, branch, and push separately:

```bash
# In vscode worktree
cd ../kailash_python_sdk_vscode
git add .
git commit -m "feat: Add Python AST parser for workflow visualization"
git push origin feature/vscode-python-visualization

# In webapp worktree
cd ../kailash_python_sdk_webapp
git add .
git commit -m "feat: Add advanced workflow search filters"
git push origin feature/react-web-app-enhancements
```

### Remove a Worktree (when done)

```bash
# From main repo
cd ./repos/projects/kailash_python_sdk

# Remove vscode worktree
git worktree remove ../kailash_python_sdk_vscode

# Remove webapp worktree
git worktree remove ../kailash_python_sdk_webapp

# Or prune all removed worktrees
git worktree prune
```

---

## Development Workflow

### VS Code Extension (Python Visualization)

**Goal**: Parse Python Kailash SDK code and visualize as diagram

**Tasks** (see `vscode-extension/PYTHON_VISUALIZATION_DESIGN.md`):
1. Install Python AST parser (`tree-sitter-python`)
2. Implement `PythonWorkflowParser.ts`
3. Add visualization command (`Cmd+Shift+K V`)
4. Build React Flow webview
5. Add bidirectional sync (canvas → Python code)

**Quick Start**:
```bash
cd ../kailash_python_sdk_vscode/apps/kailash-studio/vscode-extension
npm install
npm run compile
npm run build:webview

# Press F5 to test extension
```

---

### React Web App (Advanced Features)

**Goal**: Enhanced standalone web app with search, execution, collaboration

**Potential Tasks**:
1. **Workflow Search**: Full-text search with filters (status, tags, date)
2. **Execution UI**: Run workflows from browser, show live progress
3. **Node Palette**: Searchable palette with 113+ SDK nodes
4. **Property Panel**: Edit node parameters inline
5. **Version History**: Git-style workflow versioning
6. **Templates**: Pre-built workflow templates library
7. **Collaboration**: Real-time multi-user editing
8. **Export**: Download workflows as Python code

**Quick Start**:
```bash
cd ../kailash_python_sdk_webapp/apps/kailash-studio/frontend
npm install
npm start  # Development server on http://localhost:3000

# Or build for production
npm run build
```

---

## Keeping Worktrees in Sync

### Pull Latest Changes from Main

Each worktree can pull independently:

```bash
# In vscode worktree
cd ../kailash_python_sdk_vscode
git pull origin main
git merge main  # Merge into your feature branch

# In webapp worktree
cd ../kailash_python_sdk_webapp
git pull origin main
git merge main
```

### Rebase on Main (alternative to merge)

```bash
cd ../kailash_python_sdk_vscode
git fetch origin
git rebase origin/main
```

---

## Merging Back to Main

When features are complete:

### 1. Create Pull Requests

**VS Code Extension**:
```bash
cd ../kailash_python_sdk_vscode
git push origin feature/vscode-python-visualization

# Then create PR on GitHub:
# feature/vscode-python-visualization → main
```

**React Web App**:
```bash
cd ../kailash_python_sdk_webapp
git push origin feature/react-web-app-enhancements

# Then create PR on GitHub:
# feature/react-web-app-enhancements → main
```

### 2. Review and Merge

- Review PRs separately
- Run CI/CD tests
- Merge to `main`
- Delete branches after merge

### 3. Cleanup Worktrees

```bash
cd ./repos/projects/kailash_python_sdk
git worktree remove ../kailash_python_sdk_vscode
git worktree remove ../kailash_python_sdk_webapp
git worktree prune
```

---

## Tips & Best Practices

### ✅ DO

1. **Commit frequently** in each worktree
2. **Push to remote** often to backup work
3. **Test in isolation** - each worktree is independent
4. **Use descriptive commits** - makes PR review easier
5. **Keep branches focused** - one feature per worktree

### ❌ DON'T

1. **Don't modify same files** in multiple worktrees simultaneously (merge conflicts)
2. **Don't forget which worktree you're in** - use `git branch --show-current`
3. **Don't delete worktree directories manually** - use `git worktree remove`
4. **Don't share branches** between worktrees (defeats the purpose)

---

## Current Status

### VS Code Extension Worktree

**Branch**: `feature/vscode-python-visualization`
**Status**: Ready for development
**Next Steps**:
1. Review design doc: `vscode-extension/PYTHON_VISUALIZATION_DESIGN.md`
2. Install dependencies: `npm install`
3. Start coding Python AST parser

**Key Files**:
- `src/parsers/PythonWorkflowParser.ts` (to create)
- `src/commands/VisualizeWorkflowCommand.ts` (to create)
- `src/panels/WorkflowVisualizerPanel.ts` (to create)

---

### React Web App Worktree

**Branch**: `feature/react-web-app-enhancements`
**Status**: Ready for development
**Next Steps**:
1. Identify first feature to implement
2. Install dependencies: `npm install`
3. Start development server: `npm start`

**Current Features**:
- ✅ React Flow canvas
- ✅ Node palette (basic)
- ✅ Property panel
- ✅ Ant Design UI
- ⏳ Workflow search (needs enhancement)
- ⏳ Execution UI (needs implementation)
- ⏳ Real-time collaboration (needs testing)

---

## Troubleshooting

### "fatal: '../kailash_python_sdk_vscode' already exists"

**Solution**: Remove existing directory first
```bash
rm -rf ../kailash_python_sdk_vscode
git worktree add -b feature/vscode-python-visualization ../kailash_python_sdk_vscode main
```

### "worktree already locked"

**Solution**: Unlock and remove
```bash
git worktree unlock ../kailash_python_sdk_vscode
git worktree remove ../kailash_python_sdk_vscode
```

### "cannot force update the branch 'feature/...' checked out at '...'"

**Issue**: Branch is checked out in another worktree
**Solution**: Switch branches in that worktree first
```bash
cd ../kailash_python_sdk_vscode
git checkout main
# Then force push from main repo
```

---

## Quick Reference

```bash
# List worktrees
git worktree list

# Add new worktree
git worktree add -b <branch-name> <path> <base-branch>

# Remove worktree
git worktree remove <path>

# Prune deleted worktrees
git worktree prune

# Check current branch
git branch --show-current

# Show all branches and their worktrees
git worktree list --verbose
```

---

**Questions?** Check the design docs or create a GitHub issue!

**Happy Parallel Development!** 🚀
