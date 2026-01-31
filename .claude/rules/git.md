# Git Workflow Rules

## Scope
These rules apply to all git operations.

## MUST Rules

### 1. Conventional Commits
Commit messages MUST follow conventional commits format.

**Format**:
```
type(scope): description

[optional body]

[optional footer]
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting, no code change
- `refactor`: Code restructure
- `test`: Adding tests
- `chore`: Maintenance

**Examples**:
```
feat(auth): add OAuth2 support
fix(api): resolve rate limiting issue
docs(readme): update installation guide
refactor(workflow): simplify node connection logic
test(dataflow): add integration tests for bulk operations
```

**Enforced by**: Pre-commit hook (future)
**Violation**: Commit message rejection

### 2. Security Review Before Commit
MUST run security-reviewer before commit.

**Process**:
1. Complete code changes
2. Delegate to security-reviewer
3. Address all CRITICAL findings
4. Then commit

**Enforced by**: agents.md rule
**Violation**: Potential security issues

### 3. Branch Naming
Feature branches MUST follow naming convention.

**Format**: `type/description`

**Examples**:
- `feat/add-auth`
- `fix/api-timeout`
- `docs/update-readme`
- `refactor/workflow-builder`
- `test/dataflow-integration`

### 4. PR Description
Pull requests MUST include:
- Summary of changes (what and why)
- Test plan (how to verify)
- Related issues (links)

**Template**:
```markdown
## Summary
[1-3 bullet points]

## Test plan
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Related issues
Fixes #123
```

### 5. Atomic Commits
Each commit MUST be self-contained.

**Correct**:
- One commit per logical change
- Tests and implementation together
- Each commit builds and passes tests

**Incorrect**:
```
❌ "WIP"
❌ "fix stuff"
❌ "update files"
❌ Multiple unrelated changes
```

## MUST NOT Rules

### 1. No Direct Push to Main
MUST NOT push directly to main/master branch.

**Enforced by**: Branch protection
**Consequence**: Push rejected

### 2. No Force Push to Main
MUST NOT force push to main/master.

**Enforced by**: Branch protection
**Consequence**: Team notification, potential rollback

### 3. No Secrets in Commits
MUST NOT commit secrets, even in history.

**Detection**: Pre-commit secret scanning
**Consequence**: History rewrite required

**Check for**:
- API keys
- Passwords
- Tokens
- Private keys
- .env files

### 4. No Large Binaries
MUST NOT commit large binary files.

**Limits**:
- Single file: <10MB
- Total repo: <1GB

**Alternatives**:
- Git LFS for large files
- External storage for assets

## Pre-Commit Checklist

Before every commit:
- [ ] Code review completed (intermediate-reviewer)
- [ ] Security review completed (security-reviewer)
- [ ] Tests pass
- [ ] Linting passes
- [ ] No secrets in changes
- [ ] Commit message follows convention

## Branching Strategy

### Main
- Always deployable
- Protected branch
- Requires PR with reviews

### Feature Branches
- Branch from main
- PR back to main
- Delete after merge

### Hotfix Branches
- Branch from main
- Fix critical issues
- Fast-track review process

## Exceptions
Git exceptions require:
1. Explicit user approval
2. Documentation in PR
3. Team notification for force operations
