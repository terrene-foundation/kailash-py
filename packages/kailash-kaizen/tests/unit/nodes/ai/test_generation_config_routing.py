"""Tier-1 unit tests for #900 same-bug-class sibling — temperature/max_tokens routing.

BaseAgent.to_workflow() previously wrote ``temperature`` and ``max_tokens`` as
TOP-LEVEL keys into the LLMAgentNode config. Neither key is a declared
``NodeParameter`` on LLMAgentNode — only ``generation_config: dict`` is, with the
description "Generation parameters (temperature, max_tokens, top_p)" pinning the
canonical contract. llm_agent.py reads ``self.config.get("generation_config", ...)``
at runtime; top-level ``temperature`` / ``max_tokens`` are never consulted.

The Kailash runtime validator (``src/kailash/nodes/base.py::_validate_inputs``)
emits a WARNING on the ``kailash.nodes.base`` logger for any config key not
declared in ``get_parameters()``. Because ``BaseAgentConfig.temperature``
defaults to ``0.1`` (non-None per ``config.py:50``), the legacy write site fired
this warning on EVERY BaseAgent execution — wider blast radius than #900 ever
had.

The fix (Option A) routes ``temperature`` and ``max_tokens`` INTO the
``generation_config`` dict at the ``BaseAgent.to_workflow()`` write site,
matching the existing NodeParameter declaration and the existing consumer at
``llm_agent.py``. These Tier-1 tests pin the no-warning behavior via caplog
field-membership checks against the kailash.nodes.base validator logger — the
same structural pattern used for ``credential_ref`` in
``test_credential_ref_param.py``.

Reference: ``rules/zero-tolerance.md`` Rule 1 (warnings are errors the framework
chose to keep running through); ``autonomous-execution.md`` Rule 4 (fix-immediately
when review surfaces a same-bug-class gap within shard budget).
"""

from __future__ import annotations

import logging

import pytest

from kaizen.nodes.ai import LLMAgentNode


@pytest.mark.regression
def test_llm_agent_node_with_top_level_temperature_emits_unknown_parameter_warning() -> (
    None
):
    """Baseline: top-level ``temperature`` IS still rejected by the validator.

    Locks the LLMAgentNode contract: ``temperature`` is NOT a declared top-level
    NodeParameter; it belongs inside ``generation_config``. If a future refactor
    promotes ``temperature`` to a top-level NodeParameter (Option B), this test
    will start passing for the wrong reason — at which point the test should be
    updated to assert the new declaration. The test exists to make any such
    contract change visible at the test boundary.
    """
    import logging as _logging

    caplog_logger = _logging.getLogger("kailash.nodes.base")
    records: list[_logging.LogRecord] = []

    class _Collector(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:  # type: ignore[override]
            records.append(record)

    handler = _Collector(level=_logging.WARNING)
    caplog_logger.addHandler(handler)
    original_level = caplog_logger.level
    caplog_logger.setLevel(_logging.WARNING)
    try:
        node = LLMAgentNode(
            provider="mock",
            model="mock-model",
            temperature=0.1,
            max_tokens=100,
        )
        node.execute(messages=[{"role": "user", "content": "hi"}])
    finally:
        caplog_logger.removeHandler(handler)
        caplog_logger.setLevel(original_level)

    unknown_messages = [
        rec.getMessage()
        for rec in records
        if rec.levelno >= _logging.WARNING and "Unknown parameter" in rec.getMessage()
    ]

    # Structural assertion: at least one Unknown-parameter warning fires that
    # names BOTH temperature and max_tokens. This pins the validator behavior
    # so any future change to the LLMAgentNode parameter declaration surface
    # forces the test to be updated.
    matching = [
        msg for msg in unknown_messages if "temperature" in msg and "max_tokens" in msg
    ]
    assert matching, (
        "Top-level temperature/max_tokens MUST still be flagged as Unknown by "
        "the Kailash validator. This baseline test pins the LLMAgentNode contract: "
        "these parameters belong inside generation_config, not at top-level. "
        f"Captured warnings: {unknown_messages!r}"
    )


@pytest.mark.regression
def test_llm_agent_node_with_generation_config_emits_no_unknown_parameter_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Behavioral: passing temperature/max_tokens via generation_config is clean.

    This is the post-fix surface: BaseAgent.to_workflow() routes the values
    through ``generation_config``, which IS a declared NodeParameter. The
    validator MUST NOT emit "Unknown parameter" warnings for either key.

    Structural caplog field-membership check (per
    ``rules/probe-driven-verification.md`` Rule 3: log records are structural,
    not prose).
    """
    caplog.set_level(logging.WARNING, logger="kailash.nodes.base")

    node = LLMAgentNode(
        provider="mock",
        model="mock-model",
        generation_config={"temperature": 0.1, "max_tokens": 100},
    )
    result = node.execute(messages=[{"role": "user", "content": "hello"}])
    assert (
        result.get("success") is True
    ), f"mock provider execution should succeed; got: {result.get('error')}"

    unknown_param_warnings = [
        rec
        for rec in caplog.records
        if rec.name == "kailash.nodes.base"
        and rec.levelno >= logging.WARNING
        and "Unknown parameter" in rec.getMessage()
        and ("temperature" in rec.getMessage() or "max_tokens" in rec.getMessage())
    ]

    assert not unknown_param_warnings, (
        "validate_inputs() emitted 'Unknown parameter' warning for "
        "temperature/max_tokens despite both being nested under the declared "
        "generation_config NodeParameter. Captured records:\n"
        + "\n".join(f"  - {r.getMessage()}" for r in unknown_param_warnings)
    )
