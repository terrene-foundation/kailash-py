"""Regression: an agent's A2A description must be injectable, not only derived (#2010).

#2010 surfaced as a stale-test TypeError::

    TypeError: BaseAgent.__init__() got an unexpected keyword argument 'description'

The tempting fix is to delete the kwarg from the caller. That would be wrong,
and these tests pin why.

``description`` is NOT an invented kwarg. It is a REAL, CONSUMED field of the
A2A capability card BaseAgent auto-generates: ``A2AAgentCard.description`` is a
declared field, it is serialized by ``A2AAgentCard.to_dict()``, and it feeds the
``capability_description`` used for semantic capability matching. Its only
producer was ``A2AMixin._get_agent_description()``, which can derive it from
exactly one place -- the CLASS docstring.

That derivation cannot express per-INSTANCE identity. The originating E2E
registers three specialists (billing / technical / sales) that are all the SAME
class with ``signature=None``, so all three derived the byte-identical
description "Autonomous agent with tool-calling loops and planning
capabilities." -- capability cards that cannot tell billing from sales, which
defeats the routing they exist to drive.

So the defect is the missing injection point, and the fix must ACTUALLY CONSUME
the kwarg: accepting it and dropping it would be the ``rules/zero-tolerance.md``
Rule 3c silent-fallback shape (a documented kwarg with zero effect on the body).

The negative control below pins that the docstring-derived path is UNCHANGED
when no description is supplied -- the fix adds a source of truth, it does not
replace one.

``llm_provider='mock'`` throughout: no live call is made and no deployment model
is selected, so no model literal is read from ``.env``.
"""

from __future__ import annotations

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig


class _SpecialistAgent(BaseAgent):
    """Shared-class specialist used by several instances."""


def _config() -> BaseAgentConfig:
    return BaseAgentConfig(llm_provider="mock", model="mock-model")


def test_base_agent_accepts_description_kwarg():
    """The kwarg the E2E passes is accepted (this is the #2010 TypeError)."""
    agent = BaseAgent(config=_config(), description="Handles billing disputes")

    assert agent.description == "Handles billing disputes"


def test_description_is_consumed_by_the_a2a_description_producer():
    """Rule 3c: the kwarg must reach the field it exists to set, not be dropped."""
    agent = BaseAgent(config=_config(), description="Handles billing disputes")

    assert agent._get_agent_description() == "Handles billing disputes"


def test_explicit_description_wins_over_the_class_docstring():
    """Per-instance identity must override the shared class-level derivation."""
    agent = _SpecialistAgent(
        config=_config(), description="Specialist in invoices and refunds"
    )

    assert agent._get_agent_description() == "Specialist in invoices and refunds"
    assert "Shared-class specialist" not in agent._get_agent_description()


def test_same_class_instances_get_distinguishable_descriptions():
    """The originating E2E's actual shape: one class, three distinct specialists."""
    descriptions = [
        _SpecialistAgent(config=_config(), description=text)._get_agent_description()
        for text in (
            "Specialist in billing issues, invoices, refunds, and payments",
            "Specialist in API issues, authentication errors, and troubleshooting",
            "Specialist in enterprise pricing, SLA agreements, and sales",
        )
    ]

    assert len(set(descriptions)) == 3, descriptions


def test_negative_control_docstring_derivation_unchanged_without_description():
    """NEGATIVE CONTROL: absent the kwarg, the pre-existing derivation still runs."""
    agent = _SpecialistAgent(config=_config())

    assert agent.description is None
    assert (
        agent._get_agent_description()
        == "Shared-class specialist used by several instances."
    )


def test_negative_control_blank_description_does_not_shadow_derivation():
    """An empty string is not an identity; it must not blank out the card field."""
    agent = _SpecialistAgent(config=_config(), description="")

    assert (
        agent._get_agent_description()
        == "Shared-class specialist used by several instances."
    )
