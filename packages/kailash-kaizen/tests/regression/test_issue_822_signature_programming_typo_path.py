"""Issue #822 regression — typo'd dict-config keys must NOT enable gate.

Same Rule 3 silent-fallback bug class as the KaizenConfig dataclass path:
if `kaizen.configure(signature_programming_enabld=True)` (typo) silently
flipped the gate to True OR True→False, the gate would have undocumented
behaviour. The unified read MUST only honor the canonical key.

Env-var isolation per rules/testing.md.
"""

import threading
from typing import Iterator

import pytest

import kaizen as kaizen_module

_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    with _ENV_LOCK:
        yield


@pytest.mark.regression
def test_typo_key_does_not_enable_gate(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """A typo'd dict-config key MUST NOT enable the signature-programming gate."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen_module.clear_global_config()
    kaizen_module.configure(signature_programming_enabld=True)  # NOTE: typo
    try:
        agent = kaizen_module.create_agent("test_agent", config={})

        # Gate should NOT fire — the typo'd key is a no-op.
        try:
            agent.execute(input="x")
        except ValueError as e:
            if "must have a signature" in str(e):
                pytest.fail(
                    f"Gate fired against typo'd key: {e!r} — "
                    "typo'd dict-config keys must not silently enable the gate."
                )
        except Exception:
            # Other errors (env, model) are allowed; gate-specific error is not.
            pass
    finally:
        kaizen_module.clear_global_config()


@pytest.mark.regression
def test_canonical_key_enables_gate(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """Sibling assertion — canonical key DOES enable the gate."""
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen_module.clear_global_config()
    kaizen_module.configure(signature_programming_enabled=True)  # canonical
    try:
        # Use module-level helper to route through _global_config_manager
        agent = kaizen_module.create_agent("test_agent", config={})
        with pytest.raises(ValueError, match="Agent must have a signature"):
            agent.execute(input="x")
    finally:
        kaizen_module.clear_global_config()
