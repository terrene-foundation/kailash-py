# Deployment Onboarding Process

Interactive process for creating a project's `deploy/deployment-config.md`. The deployment-specialist agent drives this process with the human architect.

## When to Run

Run when `/deploy` is invoked and `deploy/deployment-config.md` does not exist at the project root.

## Step 1: Codebase Analysis

Analyze the project to understand what needs deploying. Check:

- **Project type**: Package (library)? Web app? API service? CLI tool? Multi-service?
- **Build system**: `pyproject.toml` (setuptools/hatch/poetry), `setup.py`, `setup.cfg`
- **Existing deployment artifacts**: Dockerfile, docker-compose.yml, k8s manifests, terraform files, CI workflows
- **Dependencies**: Database (PostgreSQL, MySQL, SQLite, MongoDB), cache (Redis, Memcached), queue (RabbitMQ, SQS), external APIs
- **Entry points**: ASGI/WSGI app, CLI script, scheduled jobs
- **Docs**: sphinx `conf.py`, mkdocs.yml, or docs/ directory

## Step 2: Structured Questions for the Human

### Release Track

- Package release (GitHub + PyPI/npm), cloud deployment, or both?

### Package Release (if applicable)

- Target registry? (PyPI, npm, GitHub Packages)
- Package name?
- Docs tool? (sphinx, mkdocs, none)
- CI system? (GitHub Actions, GitLab CI)

### Cloud Deployment (if applicable)

- Provider? (AWS, Azure, GCP)
- Region?
- SSO profile name for CLI auth?
- Compute: containers (ECS, Cloud Run, AKS), VMs, serverless?
- Database: managed service or self-hosted?
- Do you have reserved instances or savings plans to use?
- Domain name? DNS provider?
- SSL: provider-managed (ACM, Azure, GCP) or external?
- Monitoring: provider-native or third-party?
- Alerting targets? (email, Slack, PagerDuty)
- Security: WAF needed? Vulnerability scanning tool?
- Secrets management: which service?
- Budget constraints?

## Step 3: Research

The agent MUST research current approaches rather than prescribe from stale knowledge:

- Web search for current best practices with the chosen provider
- CLI `--help` for current command syntax
- Check provider documentation for service availability in chosen region
- Look up current pricing for selected services

## Step 4: Create deploy/ Directory

```
deploy/
  deployment-config.md    # Decisions + rationale + runbook + rollback
  deployments/            # Deployment logs (created per deployment)
```

## Step 5: Human Review

Present the completed `deployment-config.md` to the human for review before any deployment.

## deployment-config.md Template

The onboarding process creates this file. Structure adapts to the project:

```markdown
# Deployment Configuration

## Project

- **Name**: [project name]
- **Type**: [package | web-app | api-service | cli-tool | multi-service]
- **Build**: [build system]

## Release Track: Package (if applicable)

- **Registry**: [PyPI | npm | GitHub Packages]
- **Package name**: [name]
- **Docs**: [sphinx | mkdocs | none]
- **CI**: [system]

### Package Release Runbook

1. [step-by-step release procedure]

## Release Track: Cloud (if applicable)

- **Provider**: [AWS | Azure | GCP]
- **Region**: [region]
- **Auth**: `[sso login command]`

### Infrastructure

| Service   | Type                  | Sizing | Notes                      |
| --------- | --------------------- | ------ | -------------------------- |
| [service] | [managed/self-hosted] | [size] | [reserved instances, etc.] |

### Networking

- **Domain**: [domain]
- **DNS**: [provider]
- **SSL**: [provider]
- **CDN**: [provider or none]

### Monitoring

- **Metrics**: [tool]
- **Logging**: [tool]
- **Alerting**: [targets]

### Security

- **Secrets**: [secrets manager]
- **WAF**: [yes/no]
- **Scanning**: [tool]

### Cloud Deployment Runbook

1. [step-by-step deployment procedure]

### Rollback Procedure

1. [step-by-step rollback]

## Production Checklist

- [ ] Tests pass
- [ ] Security review
- [ ] SSL configured
- [ ] Monitoring active
- [ ] Secrets in secrets manager
- [ ] DNS configured
- [ ] Right-sizing verified
```
