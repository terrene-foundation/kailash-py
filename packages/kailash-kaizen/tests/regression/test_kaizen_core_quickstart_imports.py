"""
Regression: ``from kaizen.core import BaseAgent, Signature, InputField, OutputField``
MUST succeed on a fresh install.

Surfaced by /sweep Sweep 6 (spec-vs-code drift, 2026-04-30) — both
``specs/kaizen-core.md`` §3 BaseAgent and the project rule
``rules/patterns.md`` § Kaizen Quick Start advertise this exact import as
the canonical first line every Kaizen agent author writes. Pre-fix it
raised ``ImportError`` because ``kaizen.core.__init__`` did not re-export
the four symbols (``BaseAgent`` lives at ``kaizen.core.base_agent``;
``Signature`` / ``InputField`` / ``OutputField`` live in
``kaizen.signatures``).

This test pins the spec/rule contract structurally — if a future refactor
removes any of the four re-exports, the documented Quick Start crashes
again and this test fails loudly instead of every fresh install.
"""

import pytest


@pytest.mark.regression
def test_kaizen_core_quickstart_imports_succeed():
    """Spec/rule-mandated imports MUST resolve."""
    from kaizen.core import BaseAgent, InputField, OutputField, Signature

    # Sanity: each symbol is actually the canonical class, not a placeholder.
    assert BaseAgent.__name__ == "BaseAgent"
    assert Signature.__name__ == "Signature"
    assert InputField.__name__ == "InputField"
    assert OutputField.__name__ == "OutputField"


@pytest.mark.regression
def test_kaizen_core_all_includes_quickstart_symbols():
    """Per orphan-detection.md §6: eagerly-imported public symbols MUST appear in __all__."""
    import kaizen.core

    for symbol in ("BaseAgent", "Signature", "InputField", "OutputField"):
        assert symbol in kaizen.core.__all__, (
            f"{symbol!r} missing from kaizen.core.__all__ "
            "(orphan-detection.md §6 violation — Sphinx + `from pkg import *` drop it)"
        )


@pytest.mark.regression
def test_kaizen_core_baseagent_resolves_to_canonical_module():
    """Structural invariant: BaseAgent re-export MUST resolve to kaizen.core.base_agent.BaseAgent.

    If a future refactor moves BaseAgent to a different module, the Quick Start
    re-export still works (this test verifies kaizen.core.BaseAgent IS the canonical
    class), but the test alerts us to the move so we can update spec + rule docs.
    """
    from kaizen.core import BaseAgent
    from kaizen.core.base_agent import BaseAgent as CanonicalBaseAgent

    assert BaseAgent is CanonicalBaseAgent, (
        "kaizen.core.BaseAgent diverged from kaizen.core.base_agent.BaseAgent — "
        "spec/rule docs may need updating to reflect the canonical module path."
    )
