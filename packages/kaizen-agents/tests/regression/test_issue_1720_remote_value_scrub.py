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

import base64
import datetime
import ipaddress
import json
import pathlib

import pytest

from kaizen.utils.credential_scrub import (
    scrub_credentials,
    scrub_local_error,
    scrub_remote_error,
)

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
class TestCommaInsideAValueIsNotATerminator:
    """A password containing a comma leaked in full through BOTH presets.

    The value class excluded `,`, so `password=ab,cdefghij` matched only `ab`
    — two characters, below the `{6,}` floor — and therefore matched NEITHER
    the conservative token rule NOR the aggressive prose rule. The length
    floor was measuring a truncated prefix instead of the value.
    """

    LEAKY = [
        pytest.param('"password": "ab,cdefghij"', id="quoted-json"),
        pytest.param("password=ab,cdefghij", id="bare-kv"),
        pytest.param("api_key=zz,yyxxwwvvuu", id="api-key"),
    ]

    @pytest.mark.parametrize("payload", LEAKY)
    def test_conservative_preset_claims_a_comma_bearing_value(
        self, payload: str
    ) -> None:
        secret = payload.split(",")[1].rstrip('"')
        assert secret not in scrub_local_error(Exception(payload)), (
            "a comma inside the value truncated the match below the length "
            "floor, so neither preset claimed it"
        )

    @pytest.mark.parametrize("payload", LEAKY)
    def test_aggressive_preset_claims_it_too(self, payload: str) -> None:
        secret = payload.split(",")[1].rstrip('"')
        assert secret not in scrub_credentials(payload)

    @pytest.mark.parametrize(
        "prose",
        [
            "secret: unavailable, retrying",
            "api_key: Optional[str]",
            "invalid value for 'api_key': expected string",
        ],
    )
    def test_prose_stays_diagnosable(self, prose: str) -> None:
        """CONTROL, and the reason a TRAILING comma is not a discriminator.

        Counting a trailing comma would blank every `secret: <word>,` in
        prose — the ~180-sink diagnosability regression the token rule's
        lookahead exists to avoid. Only an INTERNAL comma discriminates.
        """
        assert scrub_local_error(Exception(prose)) == prose

    def test_a_trailing_comma_is_not_swallowed_into_the_redaction(self) -> None:
        """The sentence's punctuation is not part of the value."""
        assert scrub_local_error(Exception("password=hunter2, ok")).endswith(", ok")


@pytest.mark.regression
class TestProbedOperandEchoVerdicts:
    """The doctrine's enumeration, PROBED — one class per family, per branch.

    The enumeration in `scrub_remote_error` listed four entries, so an author
    meeting a fifth type had to guess; the `re.compile` entry above is the
    record of what guessing produces. These probes run the real builtin and
    read the real message, so each returns the OTHER answer if CPython changes
    — at which point the classification is re-derived rather than inherited.

    The two NO-echo verdicts carry the weight. `Decimal` and `b64decode` both
    take a string the caller is trying to parse, which is the `float`/`int`
    shape exactly, and both feel like they must quote it back. Neither does —
    so a doctrine that says "parsers echo" would have mis-classified both.
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_decimal_does_not_echo_its_operand(self, secret: str) -> None:
        import decimal

        with pytest.raises(decimal.InvalidOperation) as excinfo:
            decimal.Decimal(secret)
        assert secret not in str(excinfo.value), (
            "Decimal now echoes its operand; sites parsing remote numerics "
            "with it must be re-classified REMOTE"
        )

    def test_decimal_non_string_branch_names_the_type_only(self) -> None:
        """Second branch. One branch is a sample, not a verdict."""
        import decimal

        with pytest.raises(TypeError) as excinfo:
            decimal.Decimal(AWS_SECRET_SHAPE.encode())
        assert AWS_SECRET_SHAPE not in str(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_b64decode_does_not_echo_its_operand(self, secret: str) -> None:
        import binascii

        with pytest.raises(binascii.Error) as excinfo:
            base64.b64decode("!" + secret, validate=True)
        assert secret not in str(excinfo.value), (
            "b64decode now echoes its operand; every site interpolating its "
            "error into a message must be re-classified REMOTE"
        )

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_b64decode_padding_branch_also_does_not_echo(self, secret: str) -> None:
        """Second branch — a different complaint, same verdict."""
        import binascii

        with pytest.raises(binascii.Error) as excinfo:
            base64.b64decode(secret + "a")
        assert secret not in str(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_strptime_echoes_the_data_operand(self, secret: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            datetime.datetime.strptime(secret, "%Y")
        assert secret in str(excinfo.value)
        assert secret in scrub_local_error(excinfo.value), (
            "premise check: the conservative preset must LEAK it, or a LOCAL "
            "classification here would have been harmless"
        )
        assert secret not in scrub_remote_error(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    @pytest.mark.parametrize(
        "fmt_prefix,branch",
        [("%Q ", "bad-directive"), ("% ", "stray-percent")],
    )
    def test_strptime_echoes_the_format_operand_too(
        self, secret: str, fmt_prefix: str, branch: str
    ) -> None:
        """BOTH arguments are operands. A remote FORMAT fails Test 2 alone.

        Two branches, because one branch is a sample: an unknown directive and
        a stray `%` raise DIFFERENT messages, and both quote the format
        verbatim.

        The prefixes end in a SPACE deliberately. Glued directly to the
        directive (`%Qa1b2...`), the hex shape stops being a standalone token
        and `_GENERIC_HEX_TOKEN`'s `\\b` anchor no longer matches it — so the
        scrub assertion below would fail for a reason that has nothing to do
        with the echo verdict under test. A real leaked operand sits at a word
        boundary; this construction keeps the probe measuring one thing.
        """
        with pytest.raises(ValueError) as excinfo:
            datetime.datetime.strptime("2020", f"{fmt_prefix}{secret}")
        assert secret in str(excinfo.value), (
            f"the {branch} branch no longer echoes the format operand"
        )
        assert secret not in scrub_remote_error(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_fromisoformat_echoes_its_operand(self, secret: str) -> None:
        """The strptime family's far more common sibling in this codebase."""
        with pytest.raises(ValueError) as excinfo:
            datetime.datetime.fromisoformat(secret)
        assert secret in str(excinfo.value)
        assert secret not in scrub_remote_error(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_ip_address_echoes_its_operand(self, secret: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            ipaddress.ip_address(secret)
        assert secret in str(excinfo.value)
        assert secret in scrub_local_error(excinfo.value)
        assert secret not in scrub_remote_error(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_ip_network_branch_echoes_too(self, secret: str) -> None:
        """Second entry point, same family — probed, not generalized."""
        with pytest.raises(ValueError) as excinfo:
            ipaddress.ip_network(secret)
        assert secret in str(excinfo.value)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_path_glob_no_branch_echoes_a_credential_bearing_pattern(
        self, secret: str
    ) -> None:
        """`Path.glob` — the family `glob_tool` passes a MODEL-supplied operand to.

        VERDICT: NO echo, which is why `glob_tool` keeps `scrub_local_error`.
        A no-echo result is a result, not an absence — this site is LOCAL on
        measured evidence, unlike `grep_tool` below which demonstrably leaked.

        Probed per BRANCH and across INTERPRETERS, because sampling is exactly
        what produced the wrong `re.compile` verdict above. Measured on CPython
        3.10 / 3.11 / 3.12 / 3.13 / 3.14, none echoes::

            misplaced-`**` -> "Invalid pattern: '**' can only be an entire
                              path component"      (3.10-3.12 only; gone 3.13+)
            empty/dot-only -> "Unacceptable pattern: ''"          (3.10-3.12, 3.14)
                              "Unacceptable pattern: PosixPath('.')"    (3.13)
            embedded NUL   -> "embedded null character in path"   (ValueError on
                              3.13 ONLY; not raised on 3.10-3.12, 3.14)
            absolute       -> "Non-relative patterns are unsupported"
                              (NotImplementedError, all five)

        The only raise that interpolates at all is "Unacceptable pattern",
        reachable ONLY when the pattern normalizes to no tail components
        (`""`, `"."`, `"./"`), none of which can carry a credential.

        Written as "whatever happens, the operand must not appear" rather than
        as per-branch `pytest.raises`, because the branch SET is not stable
        across the interpreters this package supports — asserting that a
        specific input raises would red on 3.12/3.14 for reasons that have
        nothing to do with the echo question under test. This formulation reads
        the REAL messages on whatever interpreter runs it, so a CPython that
        starts echoing returns the other answer instead of leaving the
        classification standing on a stale verdict.
        """
        base = pathlib.Path.cwd()
        candidates = [
            secret,
            f"./{secret}",
            f"{secret}/..",
            f"{secret}\x00",
            f"\x00{secret}",
            f"a/**{secret}/b",
            f"[{secret}",
            f"/{secret}/*",
            f"{secret}//",
        ]

        echoed: list[tuple[str, str, str]] = []
        for pattern in candidates:
            try:
                list(base.glob(pattern))
            except Exception as exc:  # every raise, not only ValueError
                if secret in str(exc):
                    echoed.append((pattern, type(exc).__name__, str(exc)))

        assert echoed == [], (
            "a Path.glob branch now echoes its pattern operand: "
            f"{echoed!r}. glob_tool's LOCAL classification was derived from "
            "the absence of exactly this, so it must be re-derived — the "
            "conservative preset does not claim a prefix-less credential."
        )

    def test_path_glob_absolute_pattern_is_NOT_a_value_error(self) -> None:
        """The branch an `except ValueError` cannot catch.

        A model-supplied absolute pattern raises `NotImplementedError`, which
        is a `RuntimeError` subclass, on all five interpreters probed.
        `glob_tool` caught only `ValueError`, so this escaped the tool's own
        contract entirely and surfaced to the model as an unactionable
        "failed with NotImplementedError".
        """
        assert not issubclass(NotImplementedError, ValueError)
        with pytest.raises(NotImplementedError):
            list(pathlib.Path.cwd().glob(f"/{AWS_SECRET_SHAPE}/*"))

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_key_error_str_is_the_repr_of_the_missing_key(self, secret: str) -> None:
        """The sharpest echoer: no message of its own to inspect.

        `f"missing field: {exc}"` prints the key verbatim with nothing in the
        source that looks like interpolation of the operand.
        """
        with pytest.raises(KeyError) as excinfo:
            {}[secret]
        assert secret in str(excinfo.value)
        assert secret in f"{excinfo.value}"
        assert secret in scrub_local_error(excinfo.value)
        assert secret not in scrub_remote_error(excinfo.value)


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

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_unknown_output_mode_is_scrubbed_too(self, secret: str) -> None:
        """The sibling operand on the same tool, swept when the class was closed.

        `output_mode` is a declared property of the tool's `parameters_schema`
        (`kwargs.get("output_mode", ...)`), so it is model-supplied exactly as
        `pattern` is, and the unknown-mode branch interpolated it raw while the
        branch 19 lines above already scrubbed. Lower RISK than the `pattern`
        or `command` operands — a model has no reason to put a credential in an
        enum-valued field — but the same CLASS, which is the reason it is
        fixed rather than a claim that it is equally dangerous.
        """
        from kaizen_agents.delegate.tools.grep_tool import GrepTool

        result = GrepTool().execute(pattern="x", output_mode=secret)

        assert result.is_error, "an unknown output_mode must fail"
        assert secret not in result.error


@pytest.mark.regression
class TestGlobToolPatternIsModelOutputAndProbedLocal:
    """`glob_tool.py`'s `pattern` AND `path` are both model-supplied.

    VERDICT: LOCAL, and that is the MEASURED answer rather than the inherited
    one. The probes in `TestProbedOperandEchoVerdicts` found NO `Path.glob`
    branch on CPython 3.10 / 3.11 / 3.12 / 3.13 / 3.14 that echoes a
    credential-bearing pattern. So unlike `grep_tool` — where the group-name
    branch demonstrably leaked — this site was never shipping a leak, and
    switching it to the REMOTE preset would have been a change with no effect
    on any supported interpreter, which then reads to the next author as
    "this site was found to echo". A no-echo result is a result.

    The site passes doctrine Test 1 (raised in-process by pathlib) and, on the
    evidence, Test 2 as well (no branch carries the operand) — which is what
    LOCAL means. The defense against a future CPython that starts echoing is
    the pinned probe, not a pre-emptive preset: the probe reads real messages
    and reds, forcing the classification to be re-derived.

    The `path` operand is separately covered by the doctrine's NAMED
    filesystem-path carve-out — `redact_paths=False` on BOTH presets, so
    scrubbing `:47`'s "Directory not found: {base}" would redact nothing.
    """

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_no_pattern_shape_leaks_a_prefixless_credential(self, secret: str) -> None:
        """Every failure-inducing shape, whatever this interpreter does with it.

        Deliberately NOT asserting `is_error` per shape: the NUL pattern raises
        `ValueError` on 3.13 ONLY and is accepted without raising on
        3.10-3.12 and 3.14, so pinning the failure would red on those for a
        reason unrelated to the leak question. What must hold on EVERY
        interpreter is that the operand never reaches the tool result.
        """
        from kaizen_agents.delegate.tools.glob_tool import GlobTool

        for pattern in (f"{secret}\x00", f"a/**{secret}/b", f"/{secret}/*"):
            result = GlobTool().execute(pattern=pattern)
            assert secret not in result.error, (
                f"glob_tool surfaced the model-supplied pattern {pattern!r} in "
                "its error; the conservative preset does not claim a "
                "prefix-less shape, so the LOCAL classification must be "
                "re-derived"
            )
            assert secret not in result.output

    def test_absolute_pattern_fails_as_a_tool_result_not_an_exception(self) -> None:
        """`NotImplementedError` is not a `ValueError` and escaped the tool.

        A model asking for `/etc/**/*.pem` raised out of `execute()` instead of
        returning a `ToolResult`. The agent loop degrades an escaping exception
        to a bare type name, so the model was told "GlobTool failed with
        NotImplementedError" — unactionable, and indistinguishable from a real
        defect in the tool.
        """
        from kaizen_agents.delegate.tools.glob_tool import GlobTool

        result = GlobTool().execute(pattern=f"/{AWS_SECRET_SHAPE}/*")

        assert result.is_error
        assert AWS_SECRET_SHAPE not in result.error

    def test_a_valid_pattern_still_works(self) -> None:
        """The scrub must not break the tool's normal path."""
        from kaizen_agents.delegate.tools.glob_tool import GlobTool

        result = GlobTool().execute(
            pattern="*.py", path=str(pathlib.Path(__file__).parent)
        )
        assert not result.is_error
        assert "test_issue_1720_remote_value_scrub.py" in result.output


@pytest.mark.regression
class TestBashToolDoesNotEchoTheModelSuppliedCommand:
    """LOW-6. Two sites interpolated the command raw; a third already scrubbed.

    The `OSError` branch of the same function was already routed through
    `scrub_remote_error`, so the contract was established for this function and
    these two were simply missed — which is the shape of a partial sweep, not a
    considered exemption.

    `command` is a REQUIRED field of the tool's own `parameters_schema`, so it
    arrives verbatim from a model tool call. A model that pastes a credential
    into a command it wants run (an `export`, a `curl -H`, a `psql` DSN) puts
    that credential into both messages below.
    """

    @staticmethod
    def _tool(allow: bool):
        from kaizen_agents.delegate.tools.bash_tool import BashTool

        return BashTool(permission_gate=lambda _cmd: allow)

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_permission_denied_message_scrubs_the_command(self, secret: str) -> None:
        result = self._tool(allow=False).execute(
            command=f"curl -H 'x-api-key: {secret}' https://example.invalid"
        )

        assert result.is_error
        assert secret not in result.error, (
            "the permission-denied message echoed the model-supplied command "
            "verbatim, so a credential in a command the gate REFUSED to run "
            "was disclosed by the refusal itself"
        )

    @pytest.mark.parametrize("secret", PREFIXLESS_SHAPES)
    def test_timeout_message_scrubs_the_command(self, secret: str) -> None:
        result = self._tool(allow=True).execute(
            command=f"sleep 30 # {secret}",
            timeout=1,
        )

        assert result.is_error
        assert "timed out" in result.error
        assert secret not in result.error

    def test_the_denied_message_stays_diagnosable(self) -> None:
        """Scrubbing must not blank an ordinary command."""
        result = self._tool(allow=False).execute(command="rm -rf /")
        assert "rm -rf /" in result.error
