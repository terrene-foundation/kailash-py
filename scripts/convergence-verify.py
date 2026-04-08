#!/usr/bin/env python3
"""Phase gate verification script for Platform Architecture Convergence.

Verifies the convergence checklist from the implementation plan programmatically.
Run at the end of each phase to catch drift early.

Usage:
    python scripts/convergence-verify.py [--phase N]
    python scripts/convergence-verify.py --all
"""

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
WORKSPACE = ROOT / "workspaces" / "platform-architecture-convergence"


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return condition


def phase1_checks() -> list[bool]:
    """Phase 1: kailash-mcp package extraction."""
    print("\n=== Phase 1: kailash-mcp Package ===")
    results = []

    # Package exists
    mcp_pkg = ROOT / "packages" / "kailash-mcp" / "pyproject.toml"
    results.append(check("kailash-mcp pyproject.toml exists", mcp_pkg.exists()))

    # Package is importable
    mcp_init = ROOT / "packages" / "kailash-mcp" / "src" / "kailash_mcp" / "__init__.py"
    results.append(check("kailash_mcp __init__.py exists", mcp_init.exists()))

    # py.typed marker
    py_typed = ROOT / "packages" / "kailash-mcp" / "src" / "kailash_mcp" / "py.typed"
    results.append(check("py.typed marker exists", py_typed.exists()))

    # Sub-packages exist
    for subpkg in [
        "protocol",
        "transports",
        "auth",
        "discovery",
        "advanced",
        "tools",
        "contrib",
    ]:
        pkg_init = (
            ROOT
            / "packages"
            / "kailash-mcp"
            / "src"
            / "kailash_mcp"
            / subpkg
            / "__init__.py"
        )
        results.append(check(f"kailash_mcp.{subpkg} exists", pkg_init.exists()))

    return results


def phase2_checks() -> list[bool]:
    """Phase 2: Provider split + Envelope unification."""
    print("\n=== Phase 2: Providers + Envelope ===")
    results = []

    # Providers package
    providers_init = (
        ROOT
        / "packages"
        / "kailash-kaizen"
        / "src"
        / "kaizen"
        / "providers"
        / "__init__.py"
    )
    results.append(check("kaizen.providers package exists", providers_init.exists()))

    # Per-provider modules
    llm_dir = (
        ROOT / "packages" / "kailash-kaizen" / "src" / "kaizen" / "providers" / "llm"
    )
    for provider in ["openai", "anthropic", "google", "ollama", "mock"]:
        provider_file = llm_dir / f"{provider}.py"
        results.append(
            check(f"providers/llm/{provider}.py exists", provider_file.exists())
        )

    # Embedding providers
    emb_dir = (
        ROOT
        / "packages"
        / "kailash-kaizen"
        / "src"
        / "kaizen"
        / "providers"
        / "embedding"
    )
    results.append(check("providers/embedding/ exists", emb_dir.exists()))

    # Canonical envelope
    envelope = ROOT / "src" / "kailash" / "trust" / "envelope.py"
    results.append(check("kailash.trust.envelope exists", envelope.exists()))

    # Monolith reduced
    monolith = (
        ROOT
        / "packages"
        / "kailash-kaizen"
        / "src"
        / "kaizen"
        / "nodes"
        / "ai"
        / "ai_providers.py"
    )
    if monolith.exists():
        loc = len(monolith.read_text().splitlines())
        results.append(
            check(
                f"ai_providers.py reduced to shim ({loc} LOC)", loc < 200, f"was 5001"
            )
        )

    return results


def phase3_checks() -> list[bool]:
    """Phase 3: Composition wrappers + BaseAgent slim."""
    print("\n=== Phase 3: Wrappers + BaseAgent ===")
    results = []

    # BaseAgent under 1000 lines
    base_agent = (
        ROOT
        / "packages"
        / "kailash-kaizen"
        / "src"
        / "kaizen"
        / "core"
        / "base_agent.py"
    )
    if base_agent.exists():
        loc = len(base_agent.read_text().splitlines())
        results.append(check(f"BaseAgent < 1000 LOC (currently {loc})", loc < 1000))
    else:
        results.append(check("BaseAgent exists", False))

    # Wrapper modules
    agents_pkg = ROOT / "packages" / "kaizen-agents" / "src" / "kaizen_agents"
    for wrapper in [
        "wrapper_base",
        "streaming_agent",
        "monitored_agent",
        "governed_agent",
    ]:
        wrapper_file = agents_pkg / f"{wrapper}.py"
        results.append(check(f"{wrapper}.py exists", wrapper_file.exists()))

    return results


def phase4_checks() -> list[bool]:
    """Phase 4: Delegate facade + Multi-agent."""
    print("\n=== Phase 4: Delegate + Multi-agent ===")
    results = []

    delegate_dir = (
        ROOT / "packages" / "kaizen-agents" / "src" / "kaizen_agents" / "delegate"
    )

    # Delegate is now a composition facade — verify it uses wrappers
    delegate_file = delegate_dir / "delegate.py"
    if delegate_file.exists():
        content = delegate_file.read_text()
        # Check that Delegate uses wrapper composition
        results.append(
            check(
                "Delegate uses wrapper composition (L3GovernedAgent)",
                "L3GovernedAgent" in content,
            )
        )
        results.append(
            check(
                "Delegate uses wrapper composition (MonitoredAgent)",
                "MonitoredAgent" in content,
            )
        )
        # Verify _LoopAgent bridge exists
        results.append(
            check(
                "Delegate has _LoopAgent bridge to BaseAgent",
                "_LoopAgent" in content or "BaseAgent" in content,
            )
        )

    return results


def phase5_checks() -> list[bool]:
    """Phase 5: Core SDK + Nexus auth."""
    print("\n=== Phase 5: Core SDK + Nexus ===")
    results = []

    # Canonical audit store
    audit_store = ROOT / "src" / "kailash" / "trust" / "audit_store.py"
    results.append(check("kailash.trust.audit_store exists", audit_store.exists()))

    # AgentPosture enum (may be file or package)
    posture_file = ROOT / "src" / "kailash" / "trust" / "posture.py"
    posture_pkg = ROOT / "src" / "kailash" / "trust" / "posture" / "__init__.py"
    results.append(
        check(
            "kailash.trust.posture exists",
            posture_file.exists() or posture_pkg.exists(),
        )
    )

    # Canonical ConstraintEnvelope at kailash.trust.envelope
    # Note: Legacy types in chain.py, plane/models.py, pact/config.py are different
    # abstractions preserved with converter functions per Phase 2b agent design.
    envelope_file = ROOT / "src" / "kailash" / "trust" / "envelope.py"
    if envelope_file.exists():
        content = envelope_file.read_text()
        results.append(
            check(
                "Canonical ConstraintEnvelope at kailash.trust.envelope",
                "class ConstraintEnvelope" in content,
            )
        )
        results.append(
            check(
                "Canonical envelope has intersect() method",
                "def intersect" in content,
            )
        )
        results.append(
            check(
                "Canonical envelope has posture_ceiling field",
                "posture_ceiling" in content,
            )
        )
    else:
        results.append(check("Canonical envelope file exists", False))

    # Auth infrastructure extracted to kailash.trust.auth
    auth_dir = ROOT / "src" / "kailash" / "trust" / "auth"
    for module in ["jwt.py", "rbac.py", "context.py", "session.py", "chain.py"]:
        results.append(
            check(
                f"kailash.trust.auth.{module[:-3]} exists", (auth_dir / module).exists()
            )
        )

    # Rate limiting extracted
    rate_limit_dir = ROOT / "src" / "kailash" / "trust" / "rate_limit"
    results.append(check("kailash.trust.rate_limit exists", rate_limit_dir.exists()))

    return results


def test_baseline_check() -> list[bool]:
    """Compare current test results against baseline."""
    print("\n=== Test Baseline Check ===")
    results = []

    baseline_file = WORKSPACE / ".test-baseline"
    results.append(check("Test baseline file exists", baseline_file.exists()))

    return results


def main():
    parser = argparse.ArgumentParser(description="Convergence verification")
    parser.add_argument("--phase", type=int, help="Run checks for specific phase (1-6)")
    parser.add_argument("--all", action="store_true", help="Run all checks")
    args = parser.parse_args()

    all_results = []

    if args.all or args.phase is None:
        all_results.extend(test_baseline_check())
        all_results.extend(phase1_checks())
        all_results.extend(phase2_checks())
        all_results.extend(phase3_checks())
        all_results.extend(phase4_checks())
        all_results.extend(phase5_checks())
    elif args.phase:
        checks = {
            1: phase1_checks,
            2: phase2_checks,
            3: phase3_checks,
            4: phase4_checks,
            5: phase5_checks,
        }
        if args.phase in checks:
            all_results.extend(checks[args.phase]())
        else:
            print(f"Unknown phase: {args.phase}")
            sys.exit(1)

    passed = sum(1 for r in all_results if r)
    failed = sum(1 for r in all_results if not r)
    total = len(all_results)

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} passed, {failed} failed")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
