"""``km.from_brief`` provider-resolution surface — kaizen-FREE by construction (#2022).

WHY THIS FILE IMPORTS NO KAIZEN
------------------------------
`from_brief.py`'s own module header states the contract:

    kaizen is a SEPARATE downstream package (kailash-kaizen); kailash-ml
    MUST NOT import it at module scope ... breaking every kailash-ml CI test
    at collection time when kaizen is absent.

The `Base` CI job installs `kailash-ml[dev]`, which does NOT include kaizen
(it lives in the optional `agents` / `kaizen-judges` extras). A module-scope
`import kaizen` in a test here is therefore a COLLECTION error, and a
collection error interrupts the whole run rather than failing one test.

That is not hypothetical: the first version of this file did exactly that and
took all five matrix jobs red. The first test below pins the contract so the
next person cannot repeat it.

The BEHAVIOURAL half of provider resolution — that an unresolvable provider
raises an actionable `ConfigurationError` naming the component and the kwarg —
is exercised in `packages/kailash-kaizen/tests/unit/core/`
`test_issue_2022_config_error_not_swallowed.py::TestCrossPackageCallSite`,
using `DataFlow.from_brief`, because the kaizen CI job installs
kailash-dataflow and can actually run it. No CI job installs both kailash-ml
and kailash-kaizen, so that is where real cross-package coverage can live.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


class TestLazyKaizenImportContract:
    """`kailash_ml` must import without kaizen present.

    This is the regression guard for the CI failure this file itself caused.
    """

    def test_from_brief_module_has_no_module_scope_kaizen_import(self):
        """AST, not grep: a kaizen import inside a function body is CORRECT."""
        import kailash_ml.from_brief as mod

        source = Path(inspect.getfile(mod)).read_text()
        tree = ast.parse(source)

        offenders = []
        for node in tree.body:  # module scope ONLY — nested bodies are fine
            if isinstance(node, ast.Import):
                offenders += [
                    a.name for a in node.names if a.name.split(".")[0] == "kaizen"
                ]
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "kaizen":
                    offenders.append(node.module)

        assert not offenders, (
            f"module-scope kaizen import(s) {offenders} in {mod.__file__} — this "
            "breaks kailash-ml CI collection wherever kaizen is not installed"
        )

    def test_importing_kailash_ml_does_not_require_kaizen(self):
        """NEGATIVE CONTROL — the import must genuinely succeed here."""
        import kailash_ml
        from kailash_ml.from_brief import from_brief

        assert callable(from_brief)
        assert kailash_ml is not None


class TestProviderKwargIsExposed:
    """`llm_provider` must be reachable by callers.

    `resolve_agent_provider`'s error tells the user to "pass llm_provider=
    explicitly". That advice is only followable if `from_brief` actually
    accepts it — it did not until #2022.
    """

    def test_from_brief_accepts_llm_provider(self):
        from kailash_ml.from_brief import from_brief

        params = inspect.signature(from_brief).parameters
        assert "llm_provider" in params, (
            "from_brief must expose llm_provider — the ConfigurationError raised "
            "on an unresolvable model instructs callers to pass it"
        )
        assert params["llm_provider"].default is None, "must stay optional"
        assert params["llm_provider"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_llm_provider_is_threaded_to_the_agent_config(self):
        """Structural: the kwarg must reach BaseAgentConfig, not be accepted and dropped.

        A documented kwarg with no effect on the body is the silent-fallback
        mode at the API surface (`rules/zero-tolerance.md` Rule 3c). Verified by
        AST rather than by calling, since calling requires kaizen.
        """
        import kailash_ml.from_brief as mod

        tree = ast.parse(Path(inspect.getfile(mod)).read_text())

        constructions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "BaseAgentConfig"
        ]
        assert constructions, "no BaseAgentConfig construction found in from_brief.py"

        for call in constructions:
            kwargs = {kw.arg for kw in call.keywords}
            assert "llm_provider" in kwargs, (
                "BaseAgentConfig built without llm_provider — this is the #2022 "
                "defect: the provider falls back to env detection, resolves to "
                "None keyless, and the failure is reported as a malformed plan"
            )
