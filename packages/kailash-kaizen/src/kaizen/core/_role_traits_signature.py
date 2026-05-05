"""LLM-first derivation of agent behavioral traits from a role description.

Private implementation detail of :class:`kaizen.core.framework.Kaizen`.
Not exported from ``kaizen/__init__.py::__all__``. Consumers should use
``Kaizen.create_specialized_agent(name, role, config)`` and read
``agent.behavior_traits`` rather than instantiating this Signature directly.

See ``specs/kaizen-core.md`` § 7.5 for the full derivation contract.
"""

from kaizen.signatures import InputField, OutputField, Signature


class RoleToTraitsSignature(Signature):
    """LLM-first derivation of behavioral traits from an agent role description."""

    role: str = InputField(
        description=(
            "Agent role description (free-form natural language). "
            'Examples: "data analyst", "creative copywriter", '
            '"machine learning researcher", "compliance auditor".'
        )
    )
    traits_csv: str = OutputField(
        description=(
            "Comma-separated list of 3 to 5 behavioral traits this agent should "
            "embody. Each trait is one to three words, lowercase, snake_case if "
            "multi-word (e.g., 'analytical, evidence_based, methodical'). "
            "Output ONLY the traits, comma-separated, no prose."
        )
    )
