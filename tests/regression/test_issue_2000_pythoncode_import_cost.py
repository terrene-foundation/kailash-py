"""Regression tests for issue #2000 — PythonCodeNode first-execution import cost.

`PythonCodeNode`'s first execution in a process used to take 7-11 seconds because
two independent code paths eagerly imported every heavy optional dependency that
happened to be installed:

1. ``kailash.security._get_cached_allowed_types()`` imported torch, sklearn,
   scipy, pandas, xgboost, lightgbm, ... to learn the *type identities* it puts
   in ``sanitize_input()``'s allow-list.
2. ``CodeExecutor.execute_code()`` imported every module in ``ALLOWED_MODULES``
   into the sandbox namespace on every execution, whether or not the user's code
   referenced any of them.

WHAT THESE TESTS PIN, AND WHY IT IS NOT A CLOCK
-----------------------------------------------
The invariant is "the heavy module is not imported", not "the call was fast".
A wall-clock assertion would pass on a fast host with the defect present and
fail on a loaded host with it absent, so it cannot distinguish the fix from the
machine. ``"torch" not in sys.modules`` is deterministic and is the actual
property.

Both poles are asserted. A test that only checked "torch is not imported" would
also pass if the fix had been to delete the allow-list entirely, so the
counterpart tests assert that the type allow-list still rejects what it should
reject and still admits a framework's types once that framework is loaded.
"""

import logging
import subprocess
import sys
import textwrap

import pytest

from kailash.security import SecurityError, _get_cached_allowed_types, sanitize_input

HEAVY_MODULES = ("torch", "sklearn", "scipy", "pandas")


def _run_in_cold_interpreter(body: str) -> subprocess.CompletedProcess:
    """Execute ``body`` in a fresh interpreter with this session's sys.path.

    A cold interpreter is mandatory: inside the pytest process torch/sklearn are
    already in ``sys.modules`` (other tests import them), so an in-process check
    would report "not imported by me" as "not imported at all" — an instrument
    that cannot produce the failing answer.
    """
    script = "import sys\nsys.path[:] = %r\n%s" % (sys.path, textwrap.dedent(body))
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.unit
class TestNoHeavyImportsOnNodeExecution:
    """Pole 1: the common path must not drag in the ML stack."""

    def test_executing_a_python_code_node_does_not_import_torch_or_sklearn(self):
        """A trivial PythonCodeNode execution imports no heavy ML dependency."""
        proc = _run_in_cold_interpreter(
            """
            from kailash.runtime.local import LocalRuntime
            from kailash.workflow.builder import WorkflowBuilder

            wf = WorkflowBuilder()
            wf.add_node("PythonCodeNode", "n0", {"code": "result = {'ok': True}"})
            with LocalRuntime() as rt:
                results, _run_id = rt.execute(wf.build())

            assert results["n0"]["result"] == {"ok": True}, results
            loaded = [m for m in %r if m in sys.modules]
            print("RESULT_OK")
            print("LOADED:" + ",".join(loaded))
            """
            % (HEAVY_MODULES,)
        )
        assert (
            proc.returncode == 0
        ), f"cold-start subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        assert "RESULT_OK" in proc.stdout, proc.stdout
        loaded_line = [
            line for line in proc.stdout.splitlines() if line.startswith("LOADED:")
        ][0]
        loaded = [m for m in loaded_line[len("LOADED:") :].split(",") if m]
        assert loaded == [], (
            "PythonCodeNode execution imported heavy optional dependencies "
            f"{loaded}. Issue #2000: they must only be imported when the user's "
            "code actually references them."
        )

    def test_allowed_types_resolution_imports_nothing(self):
        """The sanitize_input allow-list is resolved without importing anything."""
        proc = _run_in_cold_interpreter(
            """
            from kailash.security import _get_cached_allowed_types

            types_ = _get_cached_allowed_types()
            assert str in types_ and dict in types_, types_
            loaded = [m for m in %r if m in sys.modules]
            print("LOADED:" + ",".join(loaded))
            """
            % (HEAVY_MODULES,)
        )
        assert (
            proc.returncode == 0
        ), f"subprocess failed:\nstdout={proc.stdout}\nstderr={proc.stderr}"
        loaded_line = [
            line for line in proc.stdout.splitlines() if line.startswith("LOADED:")
        ][0]
        loaded = [m for m in loaded_line[len("LOADED:") :].split(",") if m]
        assert loaded == [], (
            f"_get_cached_allowed_types() imported {loaded}. It must read type "
            "identities from already-loaded modules only (issue #2000)."
        )


@pytest.mark.unit
class TestSecurityCheckStillRuns:
    """Pole 2: the allow-list must still be an allow-list.

    These tests pass both before and after the fix by design — they are the
    guard that the speed-up was not obtained by deleting the check. They go RED
    if the allow-list is emptied, bypassed, or made to admit everything.
    """

    def test_unknown_type_is_still_rejected(self):
        class NotAllowed:
            pass

        with pytest.raises(SecurityError, match="Input type not allowed"):
            sanitize_input(NotAllowed())

    def test_builtin_types_still_pass(self):
        assert sanitize_input("plain") == "plain"
        assert sanitize_input(7) == 7
        assert sanitize_input({"a": [1, 2]}) == {"a": [1, 2]}

    def test_string_sanitization_still_applies(self):
        assert "<script>" not in sanitize_input("<script>alert(1)</script>hello")

    def test_loaded_framework_types_are_admitted(self):
        """A framework that IS loaded contributes its types to the allow-list."""
        numpy = pytest.importorskip("numpy")

        types_ = _get_cached_allowed_types()
        assert numpy.ndarray in types_, (
            "numpy is imported in this process but numpy.ndarray is absent from "
            "the allow-list — presence-keyed resolution is broken."
        )
        # And the value itself survives sanitization rather than raising.
        value = numpy.int64(5)
        assert sanitize_input(value) is value

    def test_framework_imported_after_first_call_is_picked_up(self):
        """The cache must not freeze the allow-list at first-call state.

        Presence-keyed resolution is only correct if the key is re-read. A cache
        that froze on the first call would permanently reject values from any
        framework imported later — a real regression, in the fail-closed
        direction but wrong.
        """
        import kailash.security as security

        class _FakeType:
            pass

        fake_module = type(sys)("kailash_test_issue_2000_fake_fw")
        probe = fake_module.__name__
        original_groups = security._OPTIONAL_TYPE_GROUPS
        original_probes = security._OPTIONAL_PROBE_NAMES
        original_cache = security._ALLOWED_TYPES_CACHE
        try:
            security._OPTIONAL_TYPE_GROUPS = original_groups + (
                ((probe,), lambda: [_FakeType]),
            )
            security._OPTIONAL_PROBE_NAMES = original_probes + (probe,)
            security._ALLOWED_TYPES_CACHE = None

            assert probe not in sys.modules
            before = security._get_cached_allowed_types()
            assert _FakeType not in before

            sys.modules[probe] = fake_module
            after = security._get_cached_allowed_types()
            assert _FakeType in after, (
                "A framework imported after the allow-list was first computed was "
                "not picked up; the cache key is not being re-read."
            )

            del sys.modules[probe]
            restored = security._get_cached_allowed_types()
            assert _FakeType not in restored
        finally:
            sys.modules.pop(probe, None)
            security._OPTIONAL_TYPE_GROUPS = original_groups
            security._OPTIONAL_PROBE_NAMES = original_probes
            security._ALLOWED_TYPES_CACHE = original_cache

    def test_resolution_failure_is_loud_and_fails_closed(self, caplog):
        """A loaded framework whose types cannot be resolved WARNs and is omitted.

        Silently pretending the group resolved would leave the allow-list looking
        complete while the types were missing. Omitting them rejects such values
        (fail closed) and says so.
        """
        import kailash.security as security

        fake_module = type(sys)("kailash_test_issue_2000_broken_fw")
        probe = fake_module.__name__

        def _broken_resolver():
            raise AttributeError("no such attribute in this build")

        original_groups = security._OPTIONAL_TYPE_GROUPS
        original_probes = security._OPTIONAL_PROBE_NAMES
        original_cache = security._ALLOWED_TYPES_CACHE
        try:
            security._OPTIONAL_TYPE_GROUPS = original_groups + (
                ((probe,), _broken_resolver),
            )
            security._OPTIONAL_PROBE_NAMES = original_probes + (probe,)
            security._ALLOWED_TYPES_CACHE = None
            sys.modules[probe] = fake_module

            with caplog.at_level(logging.WARNING, logger="kailash.security"):
                types_ = security._get_cached_allowed_types()

            assert str in types_, "base types must survive a broken resolver"
            assert any(
                probe in record.message and record.levelno >= logging.WARNING
                for record in caplog.records
            ), (
                "A resolver failure was swallowed silently. Expected a WARNING "
                f"naming {probe}; got {[r.message for r in caplog.records]}"
            )
        finally:
            sys.modules.pop(probe, None)
            security._OPTIONAL_TYPE_GROUPS = original_groups
            security._OPTIONAL_PROBE_NAMES = original_probes
            security._ALLOWED_TYPES_CACHE = original_cache


@pytest.mark.unit
class TestSandboxNamespaceStillComplete:
    """Pole 2 for the sandbox half: laziness must not remove any binding."""

    def test_binding_set_does_not_depend_on_the_code(self):
        """Every name bound for one snippet is bound for every other snippet."""
        from kailash.nodes.code.python import CodeExecutor

        executor = CodeExecutor()
        trivial = set(executor._build_module_bindings("result = {'ok': True}"))
        heavy = set(
            executor._build_module_bindings("result = numpy.array([1]).tolist()")
        )
        assert trivial == heavy, (
            "Lazy binding changed WHICH names are available to user code. It may "
            "only change when they are imported. Difference: "
            f"{trivial.symmetric_difference(heavy)}"
        )
        assert "numpy" in trivial and "math" in trivial

    def test_unreferenced_module_is_bound_but_not_imported(self):
        """An allow-listed module the code never mentions is a lazy proxy."""
        import types as pytypes

        from kailash.nodes.code.python import CodeExecutor, _LazyModule

        executor = CodeExecutor()
        bindings = executor._build_module_bindings("result = {'ok': True}")
        assert isinstance(bindings["numpy"], _LazyModule), type(bindings["numpy"])

        referenced = executor._build_module_bindings("result = numpy.array([1])")
        assert isinstance(referenced["numpy"], pytypes.ModuleType), type(
            referenced["numpy"]
        )

    def test_lazy_proxy_resolves_the_real_module_on_attribute_access(self):
        from kailash.nodes.code.python import _LazyModule

        proxy = _LazyModule("json")
        assert "not loaded" in repr(proxy)
        assert proxy.dumps({"a": 1}) == '{"a": 1}'
        assert "loaded" in repr(proxy)

    def test_user_code_can_use_an_allowed_module_without_importing_it(self):
        """The convenience the eager preload provided is preserved."""
        from kailash.nodes.code import PythonCodeNode

        node = PythonCodeNode(
            name="t", code="result = {'v': int(numpy.array([1, 2, 3]).sum())}"
        )
        assert node.execute()["result"] == {"v": 6}

    def test_user_code_can_use_an_allowed_module_from_a_nested_function(self):
        from kailash.nodes.code import PythonCodeNode

        node = PythonCodeNode(
            name="t",
            code="def f():\n    return math.floor(2.7)\nresult = {'v': f()}",
        )
        assert node.execute()["result"] == {"v": 2}

    def test_non_allowlisted_module_is_still_unbound(self):
        """torch is not in ALLOWED_MODULES, so it stays a NameError."""
        from kailash.nodes.code import PythonCodeNode
        from kailash.sdk_exceptions import NodeExecutionError

        node = PythonCodeNode(name="t", code="result = {'x': torch.zeros(1)}")
        with pytest.raises(NodeExecutionError, match="torch"):
            node.execute()


@pytest.mark.unit
class TestLazyProxyDoesNotWidenTheSandbox:
    """Adversarial review findings F1/F2 on the lazy-binding change.

    F1: the proxy CLASS is reachable from sandboxed code. `type` is an
    allow-listed builtin and a user-defined function's `__globals__` exposes the
    execution namespace, so code can take a proxy's class WITHOUT naming its
    module (naming it would make it a real module) and call that constructor
    with any string. The blocked module name then appears only inside a string
    literal, where the AST checker cannot see it.

    F2: the egress filter strips modules from node outputs by isinstance against
    types.ModuleType. A proxy that is not a ModuleType escapes it and then fails
    the JSON-serialisability validator, breaking a node that used to succeed.
    """

    # Reaches a lazily-bound proxy without naming any module.
    PRELUDE = (
        "def _f():\n"
        "    pass\n"
        "_g = _f.__globals__\n"
        "_p = None\n"
        "for _k in list(_g):\n"
        "    _v = _g[_k]\n"
        "    if type(_v).__name__ == '_LazyModule':\n"
        "        _p = _v\n"
        "        break\n"
    )

    def test_the_proxy_is_reachable_at_all(self):
        """Pins the PREMISE of F1. If this ever fails the payloads below are
        vacuous -- they would be 'blocked' only because they found no proxy."""
        from kailash.nodes.code import PythonCodeNode

        node = PythonCodeNode(
            name="t", code=self.PRELUDE + "result = {'cls': type(_p).__name__}\n"
        )
        assert node.execute()["result"] == {"cls": "_LazyModule"}

    @pytest.mark.parametrize(
        "attack,body",
        [
            (
                "constructor",
                "_m = type(_p)('subprocess')\nresult = {'got': _m.check_output.__name__}\n",
            ),
            (
                "new-without-init",
                "_c = type(_p)\n_m = _c.__new__(_c)\nresult = {'got': _m.check_output.__name__}\n",
            ),
            (
                "dict-mutation",
                "_p.__dict__['__name__'] = 'subprocess'\n"
                "_p.__dict__['_kailash_module'] = None\n"
                "result = {'got': _p.check_output.__name__}\n",
            ),
            (
                "second-blocked-module",
                "_m = type(_p)('multiprocessing')\nresult = {'got': str(_m)}\n",
            ),
        ],
    )
    def test_blocked_module_is_unreachable_through_the_proxy(self, attack, body):
        """No route through the proxy may import a COMPLETELY_BLOCKED_MODULE."""
        from kailash.nodes.code import PythonCodeNode
        from kailash.sdk_exceptions import NodeExecutionError

        node = PythonCodeNode(name="t", code=self.PRELUDE + body)
        with pytest.raises(NodeExecutionError) as excinfo:
            node.execute()
        # And specifically NOT because the payload silently produced nothing.
        assert "check_output" not in str(excinfo.value) or "allow-list" in str(
            excinfo.value
        ), f"{attack}: unexpected failure mode: {excinfo.value}"

    def test_allow_listed_module_still_constructible_through_the_proxy(self):
        """The guard blocks what was blocked before -- and nothing more.

        `os` is allow-listed and was already bound as a real module, so reaching
        it this way grants no capability the sandbox did not already have. If
        this goes red the guard has over-tightened.
        """
        from kailash.nodes.code import PythonCodeNode

        node = PythonCodeNode(
            name="t",
            code=self.PRELUDE + "_m = type(_p)('os')\nresult = {'sep': _m.path.sep}\n",
        )
        assert node.execute()["result"] == {"sep": "/"}

    def test_proxy_is_a_module_type(self):
        """Structural pin: the egress filter's isinstance check depends on this."""
        import types as pytypes

        from kailash.nodes.code.python import _LazyModule

        assert issubclass(_LazyModule, pytypes.ModuleType)

    def test_proxy_does_not_escape_into_node_outputs(self):
        """F2. With no `result` variable every non-private local is returned, so
        this is the path where the egress filter actually decides."""
        from kailash.nodes.code import PythonCodeNode

        code = self.PRELUDE.replace("_p = None", "leaked = None").replace(
            "_p = _v", "leaked = _v"
        )
        outputs = PythonCodeNode(name="t", code=code).execute()
        assert "leaked" not in outputs, (
            "A lazily-bound module proxy escaped into node outputs: "
            f"{type(outputs.get('leaked')).__name__}. It must be stripped exactly "
            "as a real module is."
        )

    def test_real_module_is_still_stripped(self):
        """Control for the test above: proves the filter was doing this before."""
        from kailash.nodes.code import PythonCodeNode

        outputs = PythonCodeNode(name="t", code="leaked = math").execute()
        assert "leaked" not in outputs


@pytest.mark.unit
class TestVerdictsPreservedOrDocumented:
    """Review findings F4/F6."""

    def test_name_based_dataframe_allow_does_not_require_pandas_loaded(self):
        """F4. A non-pandas frame whose class is named DataFrame (polars, spark)
        was accepted before, because the name-based branch ran whenever pandas
        was INSTALLED. Gating that branch on pandas being LOADED would reject it.
        """
        import kailash.security as security

        class DataFrame:  # stands in for polars.DataFrame
            pass

        if not security._module_is_installed("pandas"):
            pytest.skip("pandas not installed; the historic branch would not run")

        value = DataFrame()
        assert security.sanitize_input(value) is value

    def test_partial_resolution_failure_is_not_cached_permanently(self):
        """F6. A framework caught mid-initialisation must not be rejected for the
        rest of the process."""
        import kailash.security as security

        class _FakeType:
            pass

        fake_module = type(sys)("kailash_test_issue_2000_flaky_fw")
        probe = fake_module.__name__
        calls = {"n": 0}

        def _flaky_resolver():
            calls["n"] += 1
            if calls["n"] == 1:
                raise AttributeError("still initialising")
            return [_FakeType]

        original_groups = security._OPTIONAL_TYPE_GROUPS
        original_probes = security._OPTIONAL_PROBE_NAMES
        original_cache = security._ALLOWED_TYPES_CACHE
        try:
            security._OPTIONAL_TYPE_GROUPS = original_groups + (
                ((probe,), _flaky_resolver),
            )
            security._OPTIONAL_PROBE_NAMES = original_probes + (probe,)
            security._ALLOWED_TYPES_CACHE = None
            sys.modules[probe] = fake_module

            first = security._get_cached_allowed_types()
            assert _FakeType not in first  # failed, fails closed

            second = security._get_cached_allowed_types()
            assert _FakeType in second, (
                "A transient resolution failure was cached for the process "
                "lifetime; the framework can never become usable again."
            )
        finally:
            sys.modules.pop(probe, None)
            security._OPTIONAL_TYPE_GROUPS = original_groups
            security._OPTIONAL_PROBE_NAMES = original_probes
            security._ALLOWED_TYPES_CACHE = original_cache


@pytest.mark.unit
def test_optional_type_groups_probe_the_module_that_defines_their_types():
    """Structural guard on the presence-keyed design.

    Every group must declare at least one probe module name. A group with no
    probe would never resolve (types silently missing) or, if defaulted to
    always-on, would reintroduce the eager import.
    """
    from kailash.security import _OPTIONAL_TYPE_GROUPS

    assert _OPTIONAL_TYPE_GROUPS, "optional type groups must not be empty"
    for probes, resolver in _OPTIONAL_TYPE_GROUPS:
        assert probes, f"group with resolver {resolver!r} declares no probe module"
        assert all(isinstance(p, str) and p for p in probes), probes
        assert callable(resolver)
