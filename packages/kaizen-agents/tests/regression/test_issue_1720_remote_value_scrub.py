# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Round-3 Findings 2 + 3: the scrub was applied to the harmless half.

FINDING 2 — structured-output adapters interpolated a scrubbed EXCEPTION next
to a RAW provider response body::

    raise ValueError(
        f"LLM response is not valid JSON: {scrub_local_error(exc)}. "
        f"Content: {content[:500]}"          # <-- the entire credential risk
    )

`str(json.JSONDecodeError)` is `Expecting value: line 1 column 1 (char 0)` — a
position, carrying no credential. `content` is raw provider output. So the
scrub protected the half that was never at risk and left the whole risk
interpolated verbatim. The `isinstance(parsed, dict)` sibling two lines below
had NO scrub call at all, which is why it was invisible to any sweep keyed on
`scrub_*` call sites.

FINDING 3 — `float(x)` / `int(x)` EMBED x in the message they raise, and in
`handoff.py` x is LLM output. Classifying those sites LOCAL because the raise
is in-process was wrong: the rule is where the exception can be RAISED **and**
whether it carries a remote-derived operand.

THE SHAPE THAT DISCRIMINATES: a vendor-prefixed key (`sk-`, `AKIA`) is caught
by BOTH presets, so a test written with one cannot tell a correct
classification from an incorrect one. Only a PREFIX-LESS credential — a bare
AWS secret access key, or the bare 32+ hex run an Azure OpenAI `api-key` is —
separates them, because those are exactly the two rules the conservative preset
switches off. Every case below therefore uses a prefix-less shape.
"""

from __future__ import annotations

import json

import pytest

from kaizen.utils.credential_scrub import scrub_local_error, scrub_remote_error

#: AWS's own published example secret key — a documentation constant, not a
#: live credential. Prefix-less by construction: nothing but the 40-char
#: contiguous-run rule claims it, and that rule is OFF under the conservative
#: preset.
AWS_SECRET_SHAPE = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

#: The shape of an Azure OpenAI ``api-key`` value: a bare 32-char hex run.
#: Claimed ONLY by ``_GENERIC_HEX_TOKEN``, also OFF under the conservative
#: preset.
AZURE_KEY_SHAPE = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

PREFIXLESS_SHAPES = [
    pytest.param(AWS_SECRET_SHAPE, id="bare-aws-secret"),
    pytest.param(AZURE_KEY_SHAPE, id="bare-hex-azure-api-key"),
]


@pytest.mark.regression
class TestThePresetsActuallyDifferOnPrefixlessShapes:
    """Establishes the discriminating premise every test below relies on.

    If this class ever fails, the rest of this file has become vacuous — the
    two presets would be redacting identically and no assertion could tell a
    LOCAL misclassification from a REMOTE one.
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_conservative_preset_lets_prefixless_shapes_through(
        self, secret: str
    ) -> None:
        assert secret in scrub_local_error(f"boom: {secret}"), (
            "the conservative preset now redacts prefix-less shapes; the "
            "LOCAL/REMOTE distinction these tests probe has collapsed and "
            "they can no longer discriminate"
        )

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_remote_preset_redacts_prefixless_shapes(self, secret: str) -> None:
        assert secret not in scrub_remote_error(f"boom: {secret}")

    def test_a_vendor_prefixed_key_would_NOT_discriminate(self) -> None:
        """Why these tests do not use `sk-...`: both presets catch it."""
        vendor = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
        text = f"boom: {vendor}"
        assert vendor not in scrub_local_error(text)
        assert vendor not in scrub_remote_error(text)


def _structured_adapter_message(content: str) -> str:
    """Reproduce the adapters' JSONDecodeError branch verbatim."""
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return (
            f"LLM response is not valid JSON: {scrub_remote_error(exc)}.  "
            f"Content: {scrub_remote_error(content[:500])}"
        )
    raise AssertionError("fixture content must not be valid JSON")


@pytest.mark.regression
class TestProviderResponseBodyIsScrubbed:
    """The raw provider body must not reach the raised message."""

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_json_decode_branch_scrubs_the_body(self, secret: str) -> None:
        body = f"upstream error: key={secret} please retry"
        message = _structured_adapter_message(body)

        assert secret not in message, (
            "the raw provider response body carried a prefix-less credential "
            "into the raised ValueError. The JSONDecodeError beside it carries "
            "only a position — scrubbing that half protects nothing."
        )

    def test_the_exception_half_never_carried_the_risk(self) -> None:
        """Documents WHY the original fix aimed at the wrong half."""
        try:
            json.loads("not json at all")
        except json.JSONDecodeError as exc:
            assert str(exc) == "Expecting value: line 1 column 1 (char 0)", (
                "JSONDecodeError's message shape changed; if it now echoes the "
                "input, the exception half becomes a real risk too"
            )


@pytest.mark.regression
class TestAdaptersAndLlmSitesAreWired:
    """The fix must be in the SHIPPED modules, not only in this file.

    Behavioral, not source-grep: the adapters' parse helper is exercised
    through a stub client so the real branch runs.
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_openai_adapter_scrubs_body_on_bad_json(self, secret: str) -> None:
        from kaizen_agents.orchestration import adapters as _adapters

        body = f"upstream error: key={secret}"

        class _Result:
            content = body

        class _Adapter(_adapters.OpenAIStructuredAdapter):
            def __init__(self):  # bypass real client construction
                pass

            def complete(self, **kwargs):
                return _Result()

        with pytest.raises(ValueError) as excinfo:
            _Adapter().complete_structured(
                messages=[{"role": "user", "content": "x"}],
                schema={"type": "object", "properties": {}},
            )

        assert secret not in str(excinfo.value), (
            "the SHIPPED adapter still interpolates the raw provider body; "
            "this test file's local reproduction is not the code that runs"
        )

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_non_object_json_branch_scrubs_body(self, secret: str) -> None:
        """The sibling branch that had NO scrub call at all."""
        from kaizen_agents.orchestration import adapters as _adapters

        # Valid JSON, but a LIST — takes the `isinstance(parsed, dict)` branch.
        body = json.dumps([f"key={secret}"])

        class _Result:
            content = body

        class _Adapter(_adapters.OpenAIStructuredAdapter):
            def __init__(self):
                pass

            def complete(self, **kwargs):
                return _Result()

        with pytest.raises(ValueError) as excinfo:
            _Adapter().complete_structured(
                messages=[{"role": "user", "content": "x"}],
                schema={"type": "object", "properties": {}},
            )

        assert secret not in str(excinfo.value), (
            "the `Expected a JSON object` branch interpolates the raw body "
            "unscrubbed — it had no scrub call at all, so no sweep keyed on "
            "scrub_* call sites could see it"
        )


@pytest.mark.regression
class TestFloatAndIntEmbedTheirOperand:
    """Finding 3's premise, and the handoff sites that depend on it."""

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_float_embeds_its_argument_in_the_message(self, secret: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            float(secret)
        assert secret in str(excinfo.value), (
            "float() no longer echoes its operand; the LOCAL/REMOTE doctrine "
            "amendment was written for a behavior that has changed"
        )

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_int_embeds_its_argument_in_the_message(self, secret: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            int(secret)
        assert secret in str(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_conservative_preset_leaks_such_an_operand(self, secret: str) -> None:
        """THE TEETH for the doctrine amendment.

        A site that classifies `float(llm_output)` as LOCAL leaks the operand.
        """
        try:
            float(secret)
        except ValueError as exc:
            assert secret in scrub_local_error(exc), (
                "premise check: if the conservative preset caught this, the "
                "LOCAL classification would have been harmless"
            )
            assert secret not in scrub_remote_error(exc), (
                "the REMOTE preset must claim the embedded operand — it is the "
                "only preset with the prefix-less rules ON"
            )


@pytest.mark.regression
class TestHandoffParseSitesScrubModelOutput:
    """The three `handoff.py` sites, driven through the real methods."""

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    @pytest.mark.parametrize(
        "field,method",
        [
            ("complexity_score", "evaluate_task"),
            ("confidence", "execute_task"),
        ],
    )
    def test_unparseable_model_output_is_not_logged_raw(
        self, secret: str, field: str, method: str, caplog
    ) -> None:
        from kaizen_agents.patterns.patterns import handoff as _handoff

        # `__new__` bypasses the real __init__ (which needs a live
        # BaseAgentConfig + SharedMemoryPool and emits a DeprecationWarning).
        # The parse branch under test reads only these four attributes.
        agent = _handoff.HandoffAgent.__new__(_handoff.HandoffAgent)
        agent.tier_level = 1
        agent.agent_id = "t1"
        agent.shared_memory = None
        agent.signature = None

        payload = {
            "can_handle": "yes",
            "reasoning": "r",
            "result": "",
            "execution_metadata": "{}",
            field: secret,
        }
        agent.run = lambda **kwargs: payload

        with caplog.at_level("DEBUG"):
            getattr(agent, method)(task="t")

        logged = "\n".join(r.getMessage() for r in caplog.records)
        assert secret not in logged, (
            f"{method}() logged unparseable MODEL OUTPUT for {field!r} raw. "
            "Both the exception (float() embeds its operand) and the raw "
            "interpolation beside it must go through the REMOTE preset."
        )


@pytest.mark.regression
class TestReCompileEchoesItsOperandOnGroupNameBranches:
    """The doctrine's `re.compile` claim was EMPIRICALLY WRONG.

    `scrub_remote_error`'s docstring called `re.compile` "the trap": it feels
    like it must echo the pattern, "but `str()` of it is purely positional".
    That is true of the branches it sampled (`missing )`, `nothing to repeat`)
    and FALSE of the group-name branches, which interpolate the offending name
    verbatim. The doctrine committed the exact error it warns against —
    reasoning about the echo from a sample instead of probing every branch —
    and `grep_tool.py` was classified LOCAL on the strength of it.

    These probes ARE the discriminating instrument: they run the real builtin
    and read the real message, so they return the other answer if a future
    CPython stops echoing (in which case the classification should be
    revisited, not silently kept).
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_unknown_group_name_branch_echoes_the_operand(self, secret: str) -> None:
        import re as _re

        with pytest.raises(_re.error) as excinfo:
            _re.compile(f"(?P={secret})")
        assert secret in str(excinfo.value), (
            "the group-name branch is expected to echo the pattern operand; "
            "if CPython changed this, the grep_tool classification below "
            "should be re-derived rather than assumed"
        )

    def test_positional_branches_do_not_echo(self) -> None:
        """CONTROL. Not every branch echoes — which is why sampling misled."""
        import re as _re

        with pytest.raises(_re.error) as excinfo:
            _re.compile(f"{AWS_SECRET_SHAPE}(")
        assert AWS_SECRET_SHAPE not in str(excinfo.value)


@pytest.mark.regression
class TestGrepToolPatternIsModelOutputAndMustBeScrubbedRemote:
    """`grep_tool.py` compiles an LLM-supplied regex and reports the error.

    `pattern` is a REQUIRED field of the tool's own `parameters_schema`, so it
    arrives verbatim from a model tool call — remote-derived by construction.
    Under the corrected two-test doctrine (raised in-process AND carrying no
    remote-derived operand) this site fails Test 2 and is REMOTE.

    NOT covered by the filesystem-path carve-out: that carve-out is justified
    by `redact_paths=False` on BOTH presets, so switching a path-echoing site
    gains nothing. A regex pattern is not a path — the two shape-only rules
    the REMOTE preset turns ON are exactly what claims a prefix-less
    credential inside one.
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_invalid_regex_error_does_not_leak_a_prefixless_credential(
        self, secret: str
    ) -> None:
        from kaizen_agents.delegate.tools.grep_tool import GrepTool

        result = GrepTool().execute(pattern=f"(?P={secret})")

        # `is_error`, NOT `result.success`: `success` is a CLASSMETHOD
        # constructor on ToolResult, so `result.success` is a bound method and
        # is ALWAYS truthy — an assertion on it cannot return the other answer
        # and is not evidence. `is_error` is the real boolean field.
        assert result.is_error, "the invalid pattern must fail, not match"
        assert secret not in result.error, (
            "grep_tool surfaced a model-supplied regex operand verbatim in its "
            "error. `re.compile` echoes the operand on the group-name branch, "
            "and the conservative preset does not claim a prefix-less shape."
        )
