"""#2089 — an unpinned JWT issuer must be reported where an operator sees it.

The signal existed before this fix, so the code looked defensible on
inspection: it detected the unset issuer and said so. It said so at INFO, once
per validated token -- below every default alert threshold, below most
production log-shipping filters, and in a per-operation shape that reads as
transient and gets filtered. Nothing observable happened at a level where
anyone would act.

Both polarities are pinned, as the issue's AC#3 requires: unset -> the loud
signal fires; set -> no spurious signal.
"""

import ast
import logging
import pathlib

import pytest

import kailash.nodes.auth.enterprise_auth_provider as eap
from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PROVIDER_SRC = REPO_ROOT / "src/kailash/nodes/auth/enterprise_auth_provider.py"

SECRET = "k" * 32


@pytest.fixture(autouse=True)
def _rearm_the_latch():
    """Re-arm the one-time-per-process latch so each test observes a fresh
    process. Clearing the module latch set is the supported reset path."""
    eap._WARNED_ONCE.clear()
    yield
    eap._WARNED_ONCE.clear()


def _issuer_records(caplog):
    return [r for r in caplog.records if "issuer is NOT pinned" in r.getMessage()]


class TestUnsetIssuerIsLoud:
    def test_it_fires_at_WARNING_not_INFO(self, caplog):
        with caplog.at_level(logging.DEBUG):
            EnterpriseAuthProviderNode(
                name="p1", enabled_methods=["jwt"], jwt_config={"secret": SECRET}
            )
        hits = _issuer_records(caplog)
        assert hits, "no signal at all"
        assert hits[0].levelno >= logging.WARNING, hits[0].levelname

    def test_it_names_the_missing_config_and_the_exact_wiring(self, caplog):
        with caplog.at_level(logging.DEBUG):
            EnterpriseAuthProviderNode(
                name="p2", enabled_methods=["jwt"], jwt_config={"secret": SECRET}
            )
        message = _issuer_records(caplog)[0].getMessage()
        assert "jwt_config['issuer']" in message
        assert "EnterpriseAuthProviderNode(jwt_config=" in message
        assert "any token signed with the configured key is accepted" in message.lower()

    def test_it_fires_at_CONSTRUCTION_not_only_on_the_first_token(self, caplog):
        """A deployment that never validated a token before the incident
        never saw the signal at all."""
        with caplog.at_level(logging.DEBUG):
            EnterpriseAuthProviderNode(
                name="p3", enabled_methods=["jwt"], jwt_config={"secret": SECRET}
            )
        assert _issuer_records(caplog), "nothing was said at construction"

    def test_it_is_once_per_PROCESS_not_per_node_and_not_per_operation(self, caplog):
        """A per-request message reads as transient and gets filtered -- the
        mistake #2035 already made and corrected."""
        with caplog.at_level(logging.DEBUG):
            node = EnterpriseAuthProviderNode(
                name="p4", enabled_methods=["jwt"], jwt_config={"secret": SECRET}
            )
            EnterpriseAuthProviderNode(
                name="p5", enabled_methods=["jwt"], jwt_config={"secret": SECRET}
            )
            for _ in range(5):
                node._warn_if_issuer_unpinned()
        assert len(_issuer_records(caplog)) == 1, [
            r.getMessage() for r in _issuer_records(caplog)
        ]


class TestPinnedIssuerIsSilent:
    def test_a_pinned_issuer_emits_no_signal(self, caplog):
        """The other polarity: a check that fires either way is not evidence."""
        with caplog.at_level(logging.DEBUG):
            EnterpriseAuthProviderNode(
                name="q1",
                enabled_methods=["jwt"],
                jwt_config={"secret": SECRET, "issuer": "https://idp.example.com"},
            )
        assert not _issuer_records(caplog)

    def test_a_provider_with_jwt_disabled_emits_no_signal(self, caplog):
        """No-false-positive: an unset issuer is irrelevant when JWT auth is
        not an enabled method."""
        with caplog.at_level(logging.DEBUG):
            EnterpriseAuthProviderNode(name="q2", enabled_methods=["sso"])
        assert not _issuer_records(caplog)


class TestTheSiblingSweep:
    """AC#4: sweep the other auth-config validations for protections reported
    below WARN.

    Verdict, recorded as an executable assertion rather than prose: every
    OTHER site that reports a missing protection also REFUSES the operation,
    so those are fail-closed refusals reported per request, which is the
    correct level. The issuer site was the only one where a protection is off
    and the operation proceeds.
    """

    def test_every_other_missing_protection_report_also_refuses(self):
        source = PROVIDER_SRC.read_text()
        tree = ast.parse(source)
        lines = source.splitlines()

        # Every `self.log_info(...)` whose message describes a configuration
        # that is missing / not configured / not recognised.
        suspicious = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "log_info"
            ):
                text = " ".join(
                    a.value
                    for a in ast.walk(node)
                    if isinstance(a, ast.Constant) and isinstance(a.value, str)
                ).lower()
                if any(
                    phrase in text
                    for phrase in (
                        "not configured",
                        "no ",
                        "unset",
                        "missing",
                        "not recognised",
                    )
                ):
                    suspicious.append(node.lineno)

        assert suspicious, "the sweep found nothing; it proves nothing"

        for lineno in suspicious:
            window = "\n".join(lines[lineno - 1 : lineno + 14])
            assert '"authenticated": False' in window or "return {" in window, (
                f"{PROVIDER_SRC.name}:{lineno} reports a missing protection at "
                "INFO without refusing the operation -- same class as #2089"
            )

    def test_the_issuer_site_no_longer_reports_at_info(self):
        source = PROVIDER_SRC.read_text()
        assert (
            "JWT accepted without an issuer check" not in source
        ), "the INFO-level issuer report is still present"
        assert "_warn_if_issuer_unpinned" in source
