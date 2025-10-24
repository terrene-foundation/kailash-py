# Nexus Team: Developer Instructions

**Team:** Nexus Platform Development
**Timeline:** Weeks 5-8 (parallel with DataFlow)
**Estimated Effort:** 40 hours
**Priority:** Medium (convenience features for IT teams)

---

## Your Responsibilities

You are responsible for making Nexus easier to configure:

1. ✅ Add configuration presets (for_development, for_production, for_saas)
2. ✅ Add quick_deploy() method for Quick Mode
3. ✅ Enhance error messages with AI-friendly suggestions
4. ✅ Add preflight checks before startup
5. ✅ Enhanced startup feedback

**Impact:** IT teams choose preset instead of configuring 10+ parameters

---

## Required Reading

### MUST READ (2.5 hours):

**1. Strategic Context (30 min):**
- `../01-strategy/00-overview.md` - Dual-market thesis

**2. Codebase Analysis (1 hour):**
- `../02-implementation/01-codebase-analysis/nexus-structure.md` - Your domain

**3. Your Specifications (1 hour):**
- `../02-implementation/03-modifications/03-nexus-modifications.md` - What to build (825 lines)

---

## Detailed Tasks

### Task 1: Configuration Presets (Week 5-6, 20 hours)

**File to modify:** `apps/kailash-nexus/src/nexus/core.py`

**Add 4 classmethods:**

```python
@classmethod
def for_development(cls):
    """Preset for local development."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=False,
        enable_monitoring=False,
        enable_durability=False
    )

@classmethod
def for_production(cls):
    """Preset for production deployment."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=True,
        enable_monitoring=True,
        enable_durability=True,
        rate_limit=1000
    )

@classmethod
def for_saas(cls):
    """Preset for SaaS applications."""
    return cls(
        api_port=8000,
        mcp_port=3001,
        enable_auth=True,
        enable_monitoring=True,
        rate_limit=10000,
        enable_http_transport=True,
        enable_sse_transport=True
    )

@classmethod
def for_internal_tools(cls):
    """Preset for internal business tools."""
    return cls(
        api_port=8000,
        enable_auth=True,
        enable_monitoring=True,
        enable_durability=False,
        rate_limit=None
    )
```

**Testing:**
```python
def test_presets_create_correct_configuration():
    """Verify each preset configures correctly."""
    dev = Nexus.for_development()
    assert dev._enable_auth is False

    prod = Nexus.for_production()
    assert prod._enable_auth is True
    assert prod._enable_monitoring is True

    saas = Nexus.for_saas()
    assert saas.rate_limit_config.get("limit") == 10000  # or however rate_limit is stored
```

---

### Task 2: Quick Deploy Method (Week 6-7, 10 hours)

**File to modify:** `apps/kailash-nexus/src/nexus/core.py`

**Add method:**
```python
def quick_deploy(self, host: str = "0.0.0.0", port: int = None):
    """Quick Mode deployment with auto-discovery."""

    if not self._auto_discovery_enabled:
        raise ValueError("Auto-discovery disabled")

    from .discovery import discover_workflows
    workflows = discover_workflows()

    for name, workflow in workflows.items():
        self.register(name, workflow)

    print(f"✅ Auto-discovered {len(workflows)} workflows")
    self.start(host=host, port=port or self._api_port)
```

**Testing:**
```python
def test_quick_deploy_discovers_and_starts():
    """Test quick_deploy finds and registers workflows."""
    # Create test workflows in current directory
    # Call quick_deploy()
    # Verify workflows registered
```

---

### Task 3: Enhanced Errors + Preflight (Week 7-8, 10 hours)

**File to modify:** `apps/kailash-nexus/src/nexus/core.py`

**Add methods:**
```python
def _preflight_checks(self) -> List[str]:
    """Run pre-flight checks before startup."""
    issues = []

    if self._enable_auth and not os.getenv("JWT_SECRET"):
        issues.append("Auth enabled but JWT_SECRET not set")

    if not self._workflows:
        issues.append("No workflows registered")

    return issues

def _get_registration_error_suggestions(self, error, workflow_name):
    """Get AI-friendly error suggestions."""
    suggestions = []

    if "build" in str(error).lower():
        suggestions.append(
            "Did you forget .build()?\n"
            "  workflow = WorkflowBuilder()...\n"
            "  nexus.register('name', workflow.build())  # ← Must call .build()"
        )

    return suggestions
```

---

## Subagent Workflow for Nexus Team

### Week 5: Planning

```bash
# Day 1
> Use the sdk-navigator subagent to locate Nexus initialization code and workflow registration logic

> Use the nexus-specialist subagent to understand current Nexus configuration patterns and identify simplification opportunities

> Use the requirements-analyst subagent to break down Nexus enhancements into configuration presets, quick deploy, and error improvements

# Day 2-3
> Use the todo-manager subagent to create detailed task breakdown for Nexus enhancements

> Use the tdd-implementer subagent to write comprehensive tests for configuration presets and quick_deploy() method before implementation
```

### Week 6: Implementation (Presets)

```bash
# Day 4-5
> Use the nexus-specialist subagent to implement configuration presets (for_development, for_production, for_saas, for_internal_tools)

> Use the gold-standards-validator subagent to validate presets follow Nexus patterns and maintain backward compatibility

> Use the intermediate-reviewer subagent to review preset implementations ensuring they meet IT team needs
```

### Week 7: Implementation (Quick Deploy + Errors)

```bash
# Day 6-7
> Use the nexus-specialist subagent to implement quick_deploy() method with auto-discovery

> Use the pattern-expert subagent to implement enhanced error messages and preflight checks

# Day 8
> Use the testing-specialist subagent to verify all Nexus enhancements with integration tests using real workflows
```

### Week 8: Testing and PR

```bash
# Day 9-10
> Use the gold-standards-validator subagent to run backward compatibility tests and ensure all existing Nexus usage patterns still work

> Use the documentation-validator subagent to update Nexus documentation with new presets and features

> Use the git-release-specialist subagent to create PR for Nexus enhancements with comprehensive tests and documentation

> Use the intermediate-reviewer subagent to perform final review before submitting PR
```

---

## Success Criteria

**Definition of Done:**
- [ ] 4 configuration presets implemented and tested
- [ ] quick_deploy() method working with auto-discovery
- [ ] Enhanced error messages with AI-friendly suggestions
- [ ] Preflight checks warn about common misconfigurations
- [ ] Enhanced startup messages show all endpoints
- [ ] 100% backward compatibility (all existing tests pass)
- [ ] Tests: 80%+ coverage
- [ ] Documentation updated

---

## Integration Points

**With Templates Team (Week 6):**
- Templates use `Nexus.for_saas()` preset
- Verify preset meets template needs
- Adjust if necessary

**With Quick Mode Team (Week 7):**
- Quick Mode uses `quick_deploy()` method
- Ensure auto-discovery works with Quick Mode workflows
- Test integration

---

## Timeline

**Week 5:** Planning + tests (16 hours)
**Week 6:** Presets implementation (12 hours)
**Week 7:** Quick deploy + errors (12 hours)
**Week 8:** Testing, docs, PR (10 hours)

**Total: 50 hours over 4 weeks**

---

**You are making Nexus accessible to IT teams who don't want to configure 10+ parameters. Make it dead simple.**
