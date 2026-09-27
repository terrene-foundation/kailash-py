"""Regression: issue #2173 -- sanitize_input(context="python_exec") transforms nothing.

CodeQL raised four HIGH ``py/bad-tag-filter`` alerts (131-134) against the regexes
in :func:`kailash.security.sanitize_input`. The open question was whether any
``context="python_exec"`` output reaches an HTML sink. It does not: the only two
call sites passing that context live in ``kailash/nodes/code/python.py``, and the
values land in an ``exec()`` namespace and in ``**kwargs`` of a Python callable --
never in markup.

The tag stripping on that branch was therefore deleted rather than repaired. It
was labelled "XSS prevention" and was not that: it was blind to event-handler
payloads, and -- because a single-pass ``re.sub`` lets the fragments either side
of a deleted match join -- it FUSED a live ``<script>`` tag out of input that
contained none. A control that manufactures the token it exists to remove is
worse than no control, and it was guarding a sink that does not exist.

These tests pin the decided behaviour:

  * ``python_exec`` is a pass-through for strings, so nothing can be re-read as
    an XSS control and nothing can synthesize a tag, and
  * ``generic`` and ``shell_exec`` keep their character-class strips, which are
    what actually make those branches resistant to tag injection (alerts 133 and
    134 sit behind them and are NOT resolved by the python_exec deletion).

If a future change routes python_exec output into HTML, the fix is to escape AT
THE RENDERING SINK. These tests must then be revisited deliberately, not deleted.
"""

import pytest

from kailash.security import SecurityConfig, sanitize_input

pytestmark = pytest.mark.regression


@pytest.fixture
def config() -> SecurityConfig:
    # Audit logging off: that path stringifies the pre-sanitization value, which
    # is a separate (log-injection) concern tracked outside this issue.
    return SecurityConfig(enable_audit_logging=False)


# Event-handler XSS needs no <script>/<iframe>/<object>/<embed> tag, so the tag
# list that used to live on this branch could never see it.
EVENT_HANDLER_PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "<svg onload=alert(1)>",
    "<body onload=alert(1)>",
]

# Nesting payloads. The BARE form is the one that moved: it denies the DOTALL
# `<script.*?</script>` regex any match, so the tag regex spliced `<scr` + `ipt>`
# into a live `<script>`. The CLOSED form was always stripped to "" instead --
# a test written against it would have passed for the wrong reason, which is why
# both are pinned here.
BARE_NESTED = "<scr<script>ipt>"
BARE_NESTED_WITH_PAYLOAD = "<scr<script>ipt>alert(1)"
CLOSED_NESTED = "<scr<script>ipt>alert(1)</scr</script>ipt>"


@pytest.mark.parametrize(
    "payload",
    EVENT_HANDLER_PAYLOADS
    + [
        BARE_NESTED,
        BARE_NESTED_WITH_PAYLOAD,
        CLOSED_NESTED,
        "<script>alert(1)</script>",
        "javajavascript:script:alert(1)",
        "if a < b and c > d: pass",
        "total = $x; run(a & b) | `cmd`",
    ],
)
def test_python_exec_is_a_pass_through(payload, config):
    """python_exec returns strings byte-identical. Decided, not accidental.

    Asserting identity is the point: it forecloses both failure directions at
    once -- nobody can re-read this branch as an XSS control, and no removal can
    be reintroduced that synthesizes a tag out of nested input.
    """
    assert sanitize_input(payload, config=config, context="python_exec") == payload


def test_python_exec_no_longer_manufactures_a_live_script_tag(config):
    """The net-negative transform is gone.

    Before the fix this returned ``"<script>alert(1)"`` -- a valid script element
    built out of an input that contained no such tag. The assertion names that
    exact former output so a regression is unmistakable in the failure message.
    """
    result = sanitize_input(
        BARE_NESTED_WITH_PAYLOAD, config=config, context="python_exec"
    )
    assert result != "<script>alert(1)"
    assert result == BARE_NESTED_WITH_PAYLOAD


def test_python_exec_does_not_html_escape(config):
    """The branch must not start escaping: that would corrupt Python payloads."""
    value = "if a < b and c > d: pass"
    result = sanitize_input(value, config=config, context="python_exec")
    assert "&lt;" not in result and "&gt;" not in result and "&amp;" not in result


def test_python_exec_still_enforces_length_and_type(config):
    """Deleting the transform must not weaken the checks that do carry weight."""
    from kailash.security import SecurityError

    with pytest.raises(SecurityError):
        sanitize_input("x" * 51, max_length=50, config=config, context="python_exec")
    with pytest.raises(SecurityError):
        sanitize_input(object(), config=config, context="python_exec")


@pytest.mark.parametrize("payload", EVENT_HANDLER_PAYLOADS + [BARE_NESTED])
def test_generic_branch_keeps_its_angle_bracket_backstop(payload, config):
    """Untouched by #2173. This strip is why alert 134 is defence-in-depth."""
    result = sanitize_input(payload, config=config, context="generic")
    assert "<" not in result and ">" not in result


@pytest.mark.parametrize("payload", EVENT_HANDLER_PAYLOADS + [BARE_NESTED])
def test_shell_exec_branch_keeps_its_metacharacter_strip(payload, config):
    """Untouched by #2173. This strip is why alert 133 is unreachable as a tag filter."""
    result = sanitize_input(payload, config=config, context="shell_exec")
    assert "<" not in result and ">" not in result


def test_generic_still_preserves_shell_metacharacters(config):
    """Guards the backward-compatibility contract the two no-context callers rely on."""
    value = "total = $x; run(a & b) | `cmd`"
    assert sanitize_input(value, config=config, context="generic") == value
