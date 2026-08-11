"""`DataFlow.from_brief` provider-resolution surface — kaizen-FREE (#2022).

`from_brief.py` gained `llm_provider` as the sibling of the kailash-ml fix
(`rules/security.md` § Multi-Site Kwarg Plumbing: every call site of a plumbed
kwarg lands in the SAME PR). This file is that fix's coverage on the dataflow
side.

WHY NO KAIZEN IMPORT HERE
-------------------------
The DataFlow CI job installs root `kailash` plus `packages/kailash-dataflow[dev]`
and NOTHING ELSE — kaizen is absent, and kailash-dataflow does not declare it.
A module-scope `import kaizen` in this file would be a COLLECTION error, which
interrupts the entire run rather than failing one test. That is not
hypothetical: the kailash-ml sibling of this file did exactly that and took
five matrix jobs red before it was rewritten this way.

WHERE THE BEHAVIOURAL COVERAGE LIVES
------------------------------------
Asserting that an unresolvable provider RAISES requires importing kaizen, so it
cannot live here. It lives in
`packages/kailash-kaizen/tests/unit/core/test_issue_2022_config_error_not_swallowed.py`
::TestCrossPackageCallSite, which drives THIS function
(`DataFlow.from_brief`) and asserts the error names both the component and the
`llm_provider` kwarg — because the kaizen CI job DOES install
kailash-dataflow. A `grep` for `llm_provider` under this package's tests will
therefore not find that assertion; it is deliberately on the other side of the
boundary, in the only job that installs both.

What CAN be verified without kaizen is the structural half: the kwarg exists,
is optional and keyword-only, and is actually threaded into `BaseAgentConfig`
rather than accepted and dropped (`rules/zero-tolerance.md` Rule 3c).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path


def _from_brief_module():
    import dataflow.from_brief as mod

    return mod


class TestLazyKaizenImportContract:
    """`dataflow` must import without kaizen present."""

    def test_no_module_scope_kaizen_import(self):
        """AST, not grep: a kaizen import inside a function body is CORRECT."""
        mod = _from_brief_module()
        tree = ast.parse(Path(inspect.getfile(mod)).read_text())

        offenders = []
        for node in tree.body:  # module scope ONLY
            if isinstance(node, ast.Import):
                offenders += [
                    a.name for a in node.names if a.name.split(".")[0] == "kaizen"
                ]
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "").split(".")[0] == "kaizen":
                    offenders.append(node.module)

        assert not offenders, (
            f"module-scope kaizen import(s) {offenders} in {mod.__file__} — this "
            "breaks DataFlow CI collection, where kaizen is not installed"
        )


class TestProviderKwargIsExposedAndThreaded:
    def test_from_brief_accepts_llm_provider(self):
        from dataflow.from_brief import from_brief

        params = inspect.signature(from_brief).parameters
        assert "llm_provider" in params, (
            "from_brief must expose llm_provider — the ConfigurationError raised "
            "on an unresolvable model instructs callers to pass it"
        )
        assert params["llm_provider"].default is None, "must stay optional"
        assert params["llm_provider"].kind is inspect.Parameter.KEYWORD_ONLY

    def test_llm_provider_reaches_the_agent_config(self):
        """The #2022 defect itself: BaseAgentConfig built with no provider."""
        mod = _from_brief_module()
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
            assert "llm_provider" in {kw.arg for kw in call.keywords}, (
                "BaseAgentConfig built without llm_provider — the provider then "
                "falls back to env detection, resolves to None keyless, and the "
                "failure is reported to the user as a malformed plan"
            )
