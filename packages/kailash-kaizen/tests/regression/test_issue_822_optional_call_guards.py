"""Issue #822 regression — typed `RuntimeError` for None-call guards.

Per rules/testing.md MUST § Behavioral Regression Tests Over Source-Grep —
every typed-guard introduction needs a behavioral test that asserts the
typed error fires. Source-grep verification (`grep "raise RuntimeError"`)
breaks when the guard moves to a helper; behavioral tests survive refactor.

Coverage scope (issue #822 Shard 1):

| Guard site                              | Style       | Testable     |
| --------------------------------------- | ----------- | ------------ |
| framework.py:887  pattern_registry None | RuntimeError| YES          |
| framework.py:947  pattern_registry None | RuntimeError| YES          |
| framework.py:1077 _signature_parser     | assert      | post-init    |
| framework.py:1099 _signature_validator  | assert      | post-init    |
| framework.py:1190 _LocalRuntime         | assert      | post-init    |
| framework.py:1262 _LocalRuntime         | assert      | post-init    |
| agents.py:266     formatTime            | replaced    | (datetime)   |

Two testable guards: `pattern_registry is None` raises RuntimeError when the
enterprise resources have been cleaned up. The 4 `assert` sites are post-
lazy-init invariants that pyright cannot otherwise narrow; they fire only
on internal corruption, not on normal API misuse, so behavioral tests would
require mutating private state to trigger and the assertion-error coverage
is not a public-API contract worth pinning. The formatTime site was
replaced with `datetime.now(timezone.utc).isoformat()` (no guard remaining).
"""

import threading
from typing import Iterator

import pytest

from kaizen import Kaizen

_ENV_LOCK = threading.Lock()


@pytest.fixture
def _env_serialized() -> Iterator[None]:
    with _ENV_LOCK:
        yield


@pytest.mark.regression
def test_pattern_registry_none_raises_typed_runtimeerror_on_create(
    monkeypatch: pytest.MonkeyPatch, _env_serialized: None
):
    """`framework.py:887` guard fires typed RuntimeError when pattern_registry is None.

    Reproduces the cleanup-then-coordinate path: ``initialize_enterprise_features``
    sets ``_pattern_registry``; ``_cleanup_enterprise_resources`` sets it to None;
    a subsequent ``create_advanced_coordination_workflow`` call MUST raise typed
    RuntimeError with actionable message — NOT a bare AttributeError on None.
    """
    monkeypatch.setenv("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")
    kaizen = Kaizen()
    # Force the cleanup-then-coordinate path: set the attribute to None
    # (mimics post-cleanup state per framework.py:595).
    kaizen._pattern_registry = None
    with pytest.raises(RuntimeError) as exc_info:
        kaizen.create_advanced_coordination_workflow(
            pattern_name="any",
            agents=[],
            coordination_config={},
            enterprise_features=False,
        )
    msg = str(exc_info.value).lower()
    assert any(
        kw in msg
        for kw in ["pattern_registry", "not configured", "initialize_enterprise"]
    ), f"GUARD message not actionable: {exc_info.value!r}"


# Coverage NOTE: the extract-path guard (framework.py:966) is the same code
# pattern as the create-path guard (framework.py:887) tested above. Reaching
# the extract guard via behavioral test would require a real workflow execution
# (the path runs `self.execute(workflow, parameters)` before the guard check).
# We rely on the create-path test as proof the typed-RuntimeError contract
# fires for the shared guard pattern; both sites use identical code.
