# /deploy - Deployment Command

Standalone deployment command. Not a workspace phase — runs independently after any number of implement/redteam cycles.

## Deployment Config

Read `deploy/deployment-config.md` at the project root. This is the single source of truth for how this project deploys.

## Mode Detection

### If `deploy/deployment-config.md` does NOT exist → Onboard Mode

Run the deployment onboarding process:

1. **Analyze the codebase**
   - What type of project? (package, web app, API service, CLI tool, multi-service)
   - What build system? (setuptools, hatch, poetry)
   - Existing deployment artifacts? (Dockerfile, docker-compose, k8s manifests, terraform, CI workflows)
   - What services does it depend on? (databases, caches, queues, external APIs)

2. **Ask the human**
   - Release track: package release, cloud deployment, or both?
   - If package: target registry (PyPI, npm, GitHub Packages), docs tool (sphinx, mkdocs)
   - If cloud: provider (AWS, Azure, GCP), region, SSO profile
   - Infrastructure: compute, database, cache, managed vs self-hosted preferences
   - Cost: reserved instances, savings plans, budget constraints
   - Networking: domain name, SSL, CDN
   - Monitoring: preferred tools, alerting targets
   - Security: WAF, vulnerability scanning, secrets management

3. **Research current best practices**
   - Use web search for current provider-specific guidance
   - Use CLI help for current command syntax
   - Do NOT rely on encoded knowledge — providers change constantly

4. **Create `deploy/deployment-config.md`**
   - Document all decisions with rationale
   - Include step-by-step deployment runbook
   - Include rollback procedure
   - Include production checklist

5. **STOP — present to human for review**

### If `deploy/deployment-config.md` EXISTS → Execute Mode

Read the config and execute the appropriate track:

#### Package Release Track

1. **Pre-release prep**
   - Update README.md and CHANGELOG.md
   - Build docs (sphinx/mkdocs if configured)
   - Run full test suite
   - Security review

2. **Git workflow**
   - Stage all changes
   - Commit with conventional message: `chore: release vX.Y.Z`
   - Push (or create PR if protected branch)
   - Watch CI, merge when green

3. **Publish**
   - GitHub Release with tag
   - PyPI publish (if configured): `python -m build && twine upload dist/*.whl`
   - Verify: `pip install package==X.Y.Z` in clean venv

#### Cloud Deployment Track

1. **Pre-deploy**
   - Run full test suite
   - Security review
   - Build artifacts (Docker image, etc.)

2. **Authenticate**
   - CLI SSO login (aws sso login / az login / gcloud auth login)
   - Verify correct account and region

3. **Deploy**
   - Follow the runbook in deployment-config.md
   - Use CLI commands — research current syntax if unsure
   - Human approval gate before each destructive operation

4. **Verify**
   - Health checks pass
   - SSL working
   - Monitoring receiving data
   - Run smoke tests against production

5. **Report**
   - Document deployment in `deploy/deployments/YYYY-MM-DD-vX.Y.Z.md`
   - Note any issues encountered

## Agent Teams

- **deployment-specialist** — Analyze codebase, run onboarding, guide deployment
- **git-release-specialist** — Git workflow, PR creation, version management
- **security-reviewer** — Pre-deployment security audit (MANDATORY)
- **testing-specialist** — Verify test coverage before deploy

## Critical Rules

- NEVER hardcode cloud credentials — use CLI SSO only
- NEVER deploy without running tests first
- NEVER skip security review before deploy
- ALWAYS get human approval before destructive cloud operations
- ALWAYS document deployments in `deploy/deployments/`
- Research current CLI syntax — do not assume stale knowledge is correct

**Automated enforcement**: `validate-deployment.js` hook automatically blocks commits containing cloud credentials (AWS keys, Azure secrets, GCP service account JSON, private keys, GitHub/PyPI/Docker tokens) in deployment files.
