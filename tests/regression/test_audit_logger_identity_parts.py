"""Original name components remain separate until automatic log redaction."""

import importlib
import logging

import pytest

from kailash.nodes.security.audit_log import AuditLogNode
from kailash.nodes.security.security_event import SecurityEventNode

SECRET = "audit-sibling-canary-582419"
JSON_NAME = '{"password":"' + SECRET + '"}'
URL_NAME = f"https://user:{SECRET}@host.invalid/?token={SECRET}"
PRODUCERS = [
    ("kailash.nodes.security.behavior_analysis", "BehaviorAnalysisNode", {}, 2),
    ("kailash.nodes.security.threat_detection", "ThreatDetectionNode", {}, 2),
    (
        "kailash.nodes.security.abac_evaluator",
        "ABACPermissionEvaluatorNode",
        {"ai_reasoning": False},
        1,
    ),
    ("kailash.nodes.auth.mfa", "MultiFactorAuthNode", {}, 2),
    ("kailash.nodes.auth.directory_integration", "DirectoryIntegrationNode", {}, 2),
    ("kailash.nodes.auth.sso", "SSOAuthenticationNode", {}, 2),
    (
        "kailash.nodes.auth.enterprise_auth_provider",
        "EnterpriseAuthProviderNode",
        {"enabled_methods": ["sso"]},
        2,
    ),
    ("kailash.nodes.auth.session_management", "SessionManagementNode", {}, 2),
    ("kailash.nodes.compliance.gdpr", "GDPRComplianceNode", {}, 1),
    ("kailash.nodes.compliance.data_retention", "DataRetentionPolicyNode", {}, 2),
    (
        "kailash.nodes.monitoring.performance_benchmark",
        "PerformanceBenchmarkNode",
        {},
        2,
    ),
    ("kaizen.nodes.compliance.gdpr", "GDPRComplianceNode", {"ai_analysis": False}, 1),
]


def sinks(node):
    return [
        value
        for value in vars(node).values()
        if isinstance(value, (AuditLogNode, SecurityEventNode))
    ]


def emit_and_assert(children, caplog):
    for child in children:
        result = child.execute(message="ordinary event")
        assert result.get("logged", True)
    assert caplog.records
    for record in caplog.records:
        assert SECRET not in record.name
        assert SECRET not in record.getMessage()
        assert record.name.isprintable()
        assert len(record.name) <= 512


@pytest.mark.parametrize("module,classname,options,count", PRODUCERS)
@pytest.mark.parametrize(
    "name", [JSON_NAME, URL_NAME, URL_NAME + "\nFORGED\u202e", "ordinary"]
)
def test_actual_producer_retains_identity_and_masks_child_names(
    caplog, module, classname, options, count, name
):
    caplog.set_level(logging.INFO)
    node = getattr(importlib.import_module(module), classname)(name=name, **options)
    assert node.metadata.name == name
    children = sinks(node)
    assert len(children) == count
    for child in children:
        assert child.metadata.name.startswith(name + "_")
        if name == "ordinary":
            prefix = "audit." if isinstance(child, AuditLogNode) else "security."
            assert child.logger.name == prefix + child.metadata.name
    emit_and_assert(children, caplog)


@pytest.mark.parametrize("name", [JSON_NAME, URL_NAME, URL_NAME + "\nFORGED\u202e"])
def test_enterprise_multihop_preserves_original_components(caplog, name):
    from kailash.nodes.auth import mfa
    from kailash.nodes.auth.enterprise_auth_provider import EnterpriseAuthProviderNode

    mfa._WARNED_ONCE.clear()
    caplog.set_level(logging.INFO)
    node = EnterpriseAuthProviderNode(name=name, enabled_methods=["sso"])
    grandchildren = []
    children = [
        value for value in vars(node).values() if hasattr(value, "_log_name_parts")
    ]
    assert len(children) == 4
    for child in children:
        assert child.metadata.name.startswith(name + "_")
        actual = sinks(child)
        assert len(actual) == 2
        assert all(
            sink.metadata.name.startswith(child.metadata.name + "_") for sink in actual
        )
        grandchildren.extend(actual)
    emit_and_assert(sinks(node) + grandchildren, caplog)
    assert any("authorization is DISABLED" in r.getMessage() for r in caplog.records)
    assert "actor_disabled:" + name + "_mfa" in mfa._WARNED_ONCE


@pytest.mark.parametrize("sink", [AuditLogNode, SecurityEventNode])
@pytest.mark.parametrize("parts", [JSON_NAME, [JSON_NAME], {"password": SECRET}])
def test_parts_reject_non_tuple(sink, parts):
    with pytest.raises(TypeError, match="log_name_parts must be a tuple"):
        sink("public-name", log_name_parts=parts)


@pytest.mark.parametrize("sink", [AuditLogNode, SecurityEventNode])
def test_parts_reject_tuple_subclass(sink):
    class Parts(tuple):
        def __iter__(self):
            raise AssertionError("untrusted iterator must not execute")

    with pytest.raises(TypeError, match="log_name_parts must be a tuple"):
        sink("public-name", log_name_parts=Parts((JSON_NAME,)))


@pytest.mark.parametrize("sink", [AuditLogNode, SecurityEventNode])
def test_component_values_are_safe_and_final_namespace_bounded(caplog, sink):
    class Opaque:
        def __str__(self):
            raise AssertionError("untrusted str must not execute")

        def __repr__(self):
            raise AssertionError("untrusted repr must not execute")

    caplog.set_level(logging.INFO)
    node = sink(
        "public-name", log_name_parts=(JSON_NAME.encode(), "_", Opaque(), "_雪" * 1000)
    )
    assert node.metadata.name == "public-name"
    emit_and_assert([node], caplog)


@pytest.mark.parametrize(
    "module,classname,options,count",
    [
        p
        for p in PRODUCERS
        if p[1]
        in {
            "MultiFactorAuthNode",
            "DirectoryIntegrationNode",
            "SSOAuthenticationNode",
            "SessionManagementNode",
        }
    ],
)
def test_intermediate_parts_validate_shape(module, classname, options, count):
    with pytest.raises(TypeError, match="log_name_parts must be a tuple"):
        getattr(importlib.import_module(module), classname)(
            name="public", log_name_parts=JSON_NAME, **options
        )


def test_masked_names_keep_separate_audit_levels(caplog):
    caplog.set_level(logging.INFO)
    alpha_name = "https://user:synthetic-alpha@host.invalid/"
    beta_name = "https://user:synthetic-beta@host.invalid/"
    alpha = AuditLogNode(alpha_name, "INFO")
    assert alpha.logger.isEnabledFor(logging.INFO)
    beta = AuditLogNode(beta_name, "ERROR")
    assert alpha.logger is not beta.logger
    assert alpha.logger.isEnabledFor(logging.INFO)
    assert not beta.logger.isEnabledFor(logging.INFO)
    alpha.execute(message="alpha still emits")
    assert any(r.getMessage().find("alpha still emits") >= 0 for r in caplog.records)
    assert "synthetic-alpha" not in alpha.logger.name
    assert "synthetic-beta" not in beta.logger.name
    same = AuditLogNode(alpha_name, "INFO")
    assert same.logger is alpha.logger


@pytest.mark.parametrize("sink", [AuditLogNode, SecurityEventNode])
def test_changed_component_names_have_stable_distinct_namespaces(sink):
    alpha = sink(JSON_NAME + "_audit", log_name_parts=(JSON_NAME, "_audit"))
    beta = sink(
        JSON_NAME.replace(SECRET, "another-canary") + "_audit",
        log_name_parts=(JSON_NAME.replace(SECRET, "another-canary"), "_audit"),
    )
    repeat = sink(JSON_NAME + "_audit", log_name_parts=(JSON_NAME, "_audit"))
    assert alpha.logger is repeat.logger
    assert alpha.logger is not beta.logger
    assert SECRET not in alpha.logger.name
    assert "another-canary" not in beta.logger.name


def test_literal_cannot_alias_an_existing_masked_namespace():
    masked = AuditLogNode(JSON_NAME, "INFO")
    literal_name = masked.logger.name.removeprefix("audit.")
    literal = AuditLogNode(literal_name, "ERROR")
    assert literal.logger is not masked.logger
    assert masked.logger.isEnabledFor(logging.INFO)
