"""Issue #822 regression — signature_programming_enabled gate uniformity.

The gate at `agents.py::Agent._execute_direct_llm` MUST fire identically against
both shapes that `Kaizen.config` can return:

  * `KaizenConfig` (@dataclass, no `.get`) — explicit-config callers.
  * `ConfigWrapper(dict)` (has `.get`) — default / dict-config callers.

Prior implementation used `hasattr(self.kaizen.config, "get")` which silently
flipped the gate to False for typed-config users. This regression locks in
both behaviours. See journal/0003 for full root-cause.

Env-var isolation (rules/testing.md § Env-Var Test Isolation MUST): tests that
set KAIZEN_DEFAULT_MODEL via monkeypatch acquire the module-scope ``_ENV_LOCK``
via the ``_env_serialized`` fixture so xdist-parallel runs cannot race.
"""

import threading
from typing import Iterator

import pytest

import kaizen as kaizen_module
from kaizen import Kaizen
from kaizen.core.config import KaizenConfig

# Module-scope env lock per rules/testing.md.
_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    with _ENV_LOCK:
        yield


def _make_signatureless_agent(kaizen_inst):
    """Construct an Agent with no signature so the gate is exercised."""
    return kaizen_inst.create_agent("test_agent", config={})


@pytest.mark.regression
def test_gate_fires_against_kaizen_config_dataclass(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """Gate MUST fire when user passes explicit `KaizenConfig(...)` with the flag."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    config = KaizenConfig(signature_programming_enabled=True)
    kaizen_inst = Kaizen(config=config)
    agent = _make_signatureless_agent(kaizen_inst)
    with pytest.raises(ValueError, match="Agent must have a signature"):
        agent.execute(input="x")


@pytest.mark.regression
def test_gate_fires_against_dict_config(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """Gate fires with dict-config (existing path, regression guard).

    Uses ``kaizen.create_agent()`` (module-level) which routes through
    ``_global_config_manager.create_kaizen_config()`` so the global
    ``configure()`` call propagates into ``Kaizen.config``.
    """
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen_module.clear_global_config()
    kaizen_module.configure(signature_programming_enabled=True)
    try:
        agent = kaizen_module.create_agent("test_agent", config={})
        with pytest.raises(ValueError, match="Agent must have a signature"):
            agent.execute(input="x")
    finally:
        kaizen_module.clear_global_config()


@pytest.mark.regression
def test_gate_does_not_fire_when_flag_unset_kaizen_config(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """Gate stays quiet when KaizenConfig flag is False/absent (no false-positive)."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen_inst = Kaizen(config=KaizenConfig(signature_programming_enabled=False))
    agent = _make_signatureless_agent(kaizen_inst)
    # The gate is the only thing this test asserts — no ValueError raised.
    # The downstream _execute_direct_llm call may fail for env reasons (no model),
    # but it MUST NOT raise the gate's "Agent must have a signature" error.
    try:
        agent.execute(input="x")
    except ValueError as e:
        if "must have a signature" in str(e):
            pytest.fail(f"Gate fired against KaizenConfig with flag=False: {e!r}")
    except Exception:
        # Other errors (env, model) are allowed; gate-specific error is not.
        pass
