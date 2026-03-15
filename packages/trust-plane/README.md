# TrustPlane

Your AI assistant does things. Can you prove it stayed within bounds?

TrustPlane is a trust environment for human-AI collaborative work. It sits between you and your AI tools, recording what happens, enforcing boundaries you set, and giving you a cryptographic audit trail you can verify independently.

## Installation

```bash
pip install trust-plane
```

## Quick Start (30 seconds)

Start with shadow mode. It watches what your AI does without blocking anything:

```bash
# Set up a project in shadow mode — observe first, enforce later
attest quickstart --project-name "My Project" --author "Your Name" \
  --domain web-app --mode shadow-first

# Work normally with your AI assistant...

# See what happened
attest shadow --report

# See what WOULD have been blocked under enforcement
attest diagnose
```

That's it. You now have an audit trail of AI activity with zero disruption to your workflow.

## Full Setup

When you're ready to enforce constraints (not just observe), use full-governance mode:

```bash
attest quickstart --project-name "Production App" --author "DevOps Team" \
  --domain web-app --mode full-governance
```

This creates a project with the `software` constraint template applied and strict enforcement active. Actions that violate constraints will be held for human approval.

### Record Decisions and Milestones

```bash
# Record a decision with reasoning
attest decide --type scope --decision "Focus on X" --rationale "Because Y"

# Record a milestone
attest milestone --version v0.1 --description "First draft" --file paper.md

# Verify the full audit trail
attest verify

# Show project status
attest status
```

## Templates

TrustPlane ships with domain-specific constraint templates. Each configures all five constraint dimensions (operational, data access, financial, temporal, communication).

```bash
# List available templates
attest template list

# See what a template constrains
attest template describe software

# Apply a template to an existing project
attest template apply research
```

Available templates:

| Template        | Domain                | Key Constraints                                        |
| --------------- | --------------------- | ------------------------------------------------------ |
| `software`      | Web apps, services    | Blocks production access, merge to main, CI/CD changes |
| `data-pipeline` | ETL, data engineering | Protects source data, blocks production pipelines      |
| `research`      | Academic, analysis    | Protects raw data, requires publication review         |
| `governance`    | Policy, compliance    | Protects constitutions, blocks external publication    |
| `minimal`       | Exploration           | Only blocks credential file patterns                   |

## CI Integration

Add trust verification to your CI pipeline:

```yaml
# .github/workflows/trust.yml
- name: Verify trust chain
  run: attest verify --dir ./trust-plane
```

Verification checks cryptographic chain integrity across all recorded decisions, milestones, and audit events. A broken chain means someone tampered with the audit trail.

## Pre-commit Hook

Verify trust chain integrity before every commit:

```yaml
# .pre-commit-config.yaml
- repo: local
  hooks:
    - id: trust-verify
      name: TrustPlane verification
      entry: attest verify
      language: system
      pass_filenames: false
```

## As a Library

```python
from trustplane import TrustProject, DecisionRecord, DecisionType

project = await TrustProject.create(
    trust_dir="./trust-plane",
    project_name="My Project",
    author="Jane Doe",
    constraints=["honest_limitations_required"],
)

await project.record_decision(DecisionRecord(
    decision_type=DecisionType.SCOPE,
    decision="Focus on philosophy only",
    rationale="Clean separation of concerns",
    confidence=0.9,
))

report = await project.verify()
assert report["chain_valid"] is True
```

## License

Apache-2.0 -- Terrene Foundation
