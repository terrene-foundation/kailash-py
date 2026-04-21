# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for tool hydration (S7).

Covers:
    - ToolHydrator lifecycle (hydrate/dehydrate)
    - BM25 search accuracy (keyword matching)
    - Threshold behaviour (below threshold = all tools)
    - Multi-round hydration (search, hydrate, search again)
    - Integration with AgentLoop (mock LLM that calls search_tools)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from kaizen_agents.delegate.config.loader import KzConfig
from kaizen_agents.delegate.loop import AgentLoop, ToolRegistry
from kaizen_agents.delegate.tools.hydrator import (
    _DEFAULT_THRESHOLD,
    ToolHydrator,
    _bm25_score,
    _build_index,
    _tokenize,
    _ToolDoc,
)
from kaizen_agents.delegate.tools.search import (
    SEARCH_TOOLS_SCHEMA,
    create_search_tools_executor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_def(name: str, description: str) -> dict[str, Any]:
    """Create an OpenAI-format tool definition."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": {}},
        },
    }


async def _noop_executor(**kwargs: Any) -> str:
    return json.dumps({"status": "ok"})


def _build_registry(
    tool_count: int,
) -> tuple[ToolRegistry, dict[str, dict[str, Any]], dict[str, Any]]:
    """Build a ToolRegistry with N tools, returning (registry, defs, executors)."""
    registry = ToolRegistry()
    all_defs: dict[str, dict[str, Any]] = {}
    all_executors: dict[str, Any] = {}

    # Add base tools
    base_tools = [
        ("file_read", "Read a file from the filesystem"),
        ("file_write", "Write content to a file"),
        ("file_edit", "Edit a file with string replacement"),
        ("glob", "Find files matching a glob pattern"),
        ("grep", "Search file contents with regex"),
        ("bash", "Execute a shell command"),
    ]

    for name, desc in base_tools:
        registry.register(
            name, desc, {"type": "object", "properties": {}}, _noop_executor
        )

    # Add extra tools up to tool_count
    extra_tools = [
        ("mcp_github_create_issue", "Create a new GitHub issue in a repository"),
        ("mcp_github_list_prs", "List pull requests for a GitHub repository"),
        ("mcp_github_merge_pr", "Merge a pull request on GitHub"),
        ("mcp_slack_send_message", "Send a message to a Slack channel"),
        ("mcp_slack_list_channels", "List available Slack channels"),
        ("mcp_jira_create_ticket", "Create a new Jira ticket"),
        ("mcp_jira_search", "Search Jira tickets with JQL"),
        ("mcp_kubernetes_deploy", "Deploy a container to Kubernetes"),
        ("mcp_kubernetes_get_pods", "List pods in a Kubernetes namespace"),
        ("mcp_kubernetes_logs", "Get logs from a Kubernetes pod"),
        ("mcp_database_query", "Execute a SQL query against a database"),
        ("mcp_database_schema", "Get the schema of a database table"),
        ("mcp_email_send", "Send an email message"),
        ("mcp_email_list_inbox", "List messages in an email inbox"),
        ("mcp_calendar_create_event", "Create a calendar event"),
        ("mcp_calendar_list_events", "List upcoming calendar events"),
        ("mcp_aws_s3_upload", "Upload a file to AWS S3"),
        ("mcp_aws_s3_list", "List objects in an S3 bucket"),
        ("mcp_aws_lambda_invoke", "Invoke an AWS Lambda function"),
        ("mcp_docker_run", "Run a Docker container"),
        ("mcp_docker_ps", "List running Docker containers"),
        ("mcp_docker_logs", "Get logs from a Docker container"),
        ("mcp_redis_get", "Get a value from Redis"),
        ("mcp_redis_set", "Set a value in Redis"),
        ("mcp_prometheus_query", "Query Prometheus metrics"),
        ("mcp_grafana_dashboard", "Get a Grafana dashboard"),
        ("mcp_terraform_plan", "Run Terraform plan"),
        ("mcp_terraform_apply", "Apply a Terraform configuration"),
        ("mcp_vault_read", "Read a secret from HashiCorp Vault"),
        ("mcp_vault_write", "Write a secret to HashiCorp Vault"),
    ]

    needed = tool_count - len(base_tools)
    for i, (name, desc) in enumerate(extra_tools):
        if i >= needed:
            break
        registry.register(
            name, desc, {"type": "object", "properties": {}}, _noop_executor
        )

    # If we need even more tools, generate synthetic ones
    for i in range(needed - len(extra_tools)):
        if i < 0:
            break
        name = f"mcp_synthetic_tool_{i}"
        desc = f"Synthetic tool number {i} for testing"
        registry.register(
            name, desc, {"type": "object", "properties": {}}, _noop_executor
        )

    # Build defs and executors dicts
    for tool_def in registry._tools.values():
        all_defs[tool_def.name] = tool_def.to_openai_format()
        all_executors[tool_def.name] = registry._executors[tool_def.name]

    return registry, all_defs, all_executors


# =====================================================================
# Tokenizer
# =====================================================================


class TestTokenize:
    def test_basic(self) -> None:
        tokens = _tokenize("Hello World 123")
        assert tokens == ["hello", "world", "123"]

    def test_special_chars(self) -> None:
        tokens = _tokenize("mcp_github_create-issue.v2")
        assert tokens == ["mcp", "github", "create", "issue", "v2"]

    def test_empty(self) -> None:
        assert _tokenize("") == []
        assert _tokenize("   ") == []


# =====================================================================
# BM25 Scoring
# =====================================================================


class TestBM25Score:
    def test_exact_match_scores_higher(self) -> None:
        docs = {
            "github": _ToolDoc(
                "github", "Create GitHub issues", _tokenize("github create issues")
            ),
            "slack": _ToolDoc(
                "slack", "Send Slack messages", _tokenize("slack send messages")
            ),
        }
        df = _build_index(docs)
        n_docs = len(docs)
        avgdl = sum(len(d.tokens) for d in docs.values()) / n_docs

        github_score = _bm25_score(
            _tokenize("github"), docs["github"], df, n_docs, avgdl
        )
        slack_score = _bm25_score(_tokenize("github"), docs["slack"], df, n_docs, avgdl)
        assert github_score > slack_score
        assert slack_score == 0.0

    def test_empty_query_scores_zero(self) -> None:
        doc = _ToolDoc("test", "A test tool", _tokenize("test tool"))
        score = _bm25_score([], doc, {"test": 1}, 1, 2.0)
        assert score == 0.0

    def test_empty_corpus_scores_zero(self) -> None:
        doc = _ToolDoc("test", "A test tool", [])
        score = _bm25_score(_tokenize("test"), doc, {}, 0, 0.0)
        assert score == 0.0


# =====================================================================
# ToolHydrator — lifecycle
# =====================================================================


class TestToolHydratorLifecycle:
    def test_below_threshold_not_active(self) -> None:
        hydrator = ToolHydrator(threshold=30)
        _, defs, executors = _build_registry(10)
        hydrator.load_tools(defs, executors)
        assert not hydrator.is_active
        assert hydrator.total_tool_count == 10

    def test_above_threshold_is_active(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)
        assert hydrator.is_active
        assert hydrator.total_tool_count == 15

    def test_below_threshold_returns_all_tools(self) -> None:
        hydrator = ToolHydrator(threshold=30)
        _, defs, executors = _build_registry(10)
        hydrator.load_tools(defs, executors)
        active = hydrator.get_active_tool_defs()
        assert len(active) == 10

    def test_above_threshold_returns_only_base_tools(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)
        active = hydrator.get_active_tool_defs()
        # Should only have base tools (those in the base_tool_names set)
        active_names = {d["function"]["name"] for d in active}
        base_names = hydrator.base_tool_names & set(defs.keys())
        assert active_names == base_names
        assert len(active) < 20

    def test_hydrate_adds_tools(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        before = len(hydrator.get_active_tool_defs())
        hydrated = hydrator.hydrate(
            ["mcp_github_create_issue", "mcp_slack_send_message"]
        )
        after = len(hydrator.get_active_tool_defs())

        assert len(hydrated) == 2
        assert after == before + 2

    def test_hydrate_ignores_unknown_tools(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        hydrated = hydrator.hydrate(["nonexistent_tool", "also_fake"])
        assert hydrated == []

    def test_hydrate_ignores_base_tools(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        hydrated = hydrator.hydrate(["file_read", "grep"])
        # Base tools cannot be hydrated (they are always available)
        assert hydrated == []

    def test_dehydrate_resets_to_base(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        hydrator.hydrate(["mcp_github_create_issue", "mcp_slack_send_message"])
        hydrator.dehydrate()

        active = hydrator.get_active_tool_defs()
        active_names = {d["function"]["name"] for d in active}
        base_names = hydrator.base_tool_names & set(defs.keys())
        assert active_names == base_names

    def test_get_active_executor_respects_hydration(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        # Before hydration, deferred tool executor should not be accessible
        assert hydrator.get_active_executor("mcp_github_create_issue") is None

        # After hydration, it should be accessible
        hydrator.hydrate(["mcp_github_create_issue"])
        assert hydrator.get_active_executor("mcp_github_create_issue") is not None

    def test_get_executor_force_always_works(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        # Even without hydration, force lookup works
        assert hydrator.get_executor_force("mcp_github_create_issue") is not None

    def test_has_executor(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        assert hydrator.has_executor("file_read")
        assert hydrator.has_executor("mcp_github_create_issue")
        assert not hydrator.has_executor("nonexistent")


# =====================================================================
# ToolHydrator — search
# =====================================================================


class TestToolHydratorSearch:
    def test_search_finds_relevant_tools(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("github issue")
        names = [r["name"] for r in results]
        assert "mcp_github_create_issue" in names

    def test_search_returns_scored_results(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("kubernetes deploy")
        assert len(results) > 0
        # Results should be sorted by score descending
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_respects_top_n(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("mcp", top_n=3)
        assert len(results) <= 3

    def test_search_empty_query(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("")
        assert results == []

    def test_search_no_matches(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("zzzznonexistentzzzz")
        assert results == []

    def test_search_does_not_include_base_tools(self) -> None:
        """Base tools are excluded from the search index."""
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        results = hydrator.search("file read")
        names = [r["name"] for r in results]
        # file_read is a base tool, should not appear in search
        assert "file_read" not in names


# =====================================================================
# search_tools executor
# =====================================================================


class TestSearchToolsExecutor:
    @pytest.fixture
    def hydrator_with_tools(self) -> ToolHydrator:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)
        return hydrator

    @pytest.mark.asyncio
    async def test_search_returns_results(
        self, hydrator_with_tools: ToolHydrator
    ) -> None:
        executor = create_search_tools_executor(hydrator_with_tools)
        result_str = await executor(query="github issue")
        result = json.loads(result_str)

        assert "results" in result
        assert len(result["results"]) > 0
        assert "hydrated" in result

    @pytest.mark.asyncio
    async def test_search_auto_hydrates(
        self, hydrator_with_tools: ToolHydrator
    ) -> None:
        executor = create_search_tools_executor(hydrator_with_tools)

        # Before search, the tool is not in the active set
        assert (
            hydrator_with_tools.get_active_executor("mcp_github_create_issue") is None
        )

        await executor(query="github issue")

        # After search, the tool should be hydrated
        assert (
            hydrator_with_tools.get_active_executor("mcp_github_create_issue")
            is not None
        )

    @pytest.mark.asyncio
    async def test_search_empty_query(self, hydrator_with_tools: ToolHydrator) -> None:
        executor = create_search_tools_executor(hydrator_with_tools)
        result_str = await executor(query="")
        result = json.loads(result_str)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_no_matches(self, hydrator_with_tools: ToolHydrator) -> None:
        executor = create_search_tools_executor(hydrator_with_tools)
        result_str = await executor(query="zzzznonexistentzzzz")
        result = json.loads(result_str)
        assert result["results"] == []
        assert "No matching tools" in result["message"]

    @pytest.mark.asyncio
    async def test_search_top_n(self, hydrator_with_tools: ToolHydrator) -> None:
        executor = create_search_tools_executor(hydrator_with_tools)
        result_str = await executor(query="mcp", top_n=2)
        result = json.loads(result_str)
        assert len(result["results"]) <= 2


# =====================================================================
# Multi-round hydration
# =====================================================================


class TestMultiRoundHydration:
    def test_search_hydrate_search_accumulates(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        # Round 1: search and hydrate GitHub tools
        results1 = hydrator.search("github")
        hydrator.hydrate([r["name"] for r in results1])
        count_after_round1 = len(hydrator.get_active_tool_defs())

        # Round 2: search and hydrate Kubernetes tools
        results2 = hydrator.search("kubernetes")
        hydrator.hydrate([r["name"] for r in results2])
        count_after_round2 = len(hydrator.get_active_tool_defs())

        # Round 2 should have accumulated more tools
        assert count_after_round2 >= count_after_round1

    def test_dehydrate_between_rounds_resets(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        base_count = len(hydrator.get_active_tool_defs())

        # Round 1
        results1 = hydrator.search("github")
        hydrator.hydrate([r["name"] for r in results1])

        # Dehydrate
        hydrator.dehydrate()
        assert len(hydrator.get_active_tool_defs()) == base_count


# =====================================================================
# SEARCH_TOOLS_SCHEMA validation
# =====================================================================


class TestSearchToolsSchema:
    def test_schema_has_required_fields(self) -> None:
        assert SEARCH_TOOLS_SCHEMA["type"] == "function"
        func = SEARCH_TOOLS_SCHEMA["function"]
        assert func["name"] == "search_tools"
        assert "description" in func
        assert "parameters" in func
        assert "query" in func["parameters"]["properties"]
        assert "query" in func["parameters"]["required"]


# =====================================================================
# AgentLoop integration
# =====================================================================


class TestAgentLoopHydrationIntegration:
    """Test that AgentLoop correctly integrates with ToolHydrator."""

    def test_no_hydration_below_threshold(self) -> None:
        """Below threshold, no hydrator is created."""
        registry = ToolRegistry()
        registry.register("file_read", "Read a file", {}, _noop_executor)
        registry.register("bash", "Run shell command", {}, _noop_executor)

        config = KzConfig(model="test-model")
        loop = AgentLoop(
            config=config,
            tools=registry,
            client=MagicMock(),
        )
        # Hydrator should not be set up since we only have 2 tools
        assert loop.hydrator is None

    def test_hydration_auto_activates_above_threshold(self) -> None:
        """Above threshold, hydrator is auto-created and search_tools is injected."""
        registry, _, _ = _build_registry(35)

        config = KzConfig(model="test-model")
        loop = AgentLoop(
            config=config,
            tools=registry,
            client=MagicMock(),
        )
        assert loop.hydrator is not None
        assert loop.hydrator.is_active
        # search_tools should have been injected
        assert registry.has_tool("search_tools")

    def test_explicit_hydrator_used(self) -> None:
        """An explicitly provided hydrator is used."""
        registry, _, _ = _build_registry(10)
        hydrator = ToolHydrator(threshold=5)

        config = KzConfig(model="test-model")
        loop = AgentLoop(
            config=config,
            tools=registry,
            client=MagicMock(),
            hydrator=hydrator,
        )
        assert loop.hydrator is hydrator
        assert hydrator.is_active  # 10 > threshold of 5

    def test_explicit_hydrator_with_low_count(self) -> None:
        """An explicit hydrator still respects is_active based on loaded tools."""
        registry = ToolRegistry()
        registry.register("file_read", "Read a file", {}, _noop_executor)

        hydrator = ToolHydrator(threshold=30)
        config = KzConfig(model="test-model")
        loop = AgentLoop(
            config=config,
            tools=registry,
            client=MagicMock(),
            hydrator=hydrator,
        )
        assert loop.hydrator is hydrator
        # With only 2 tools (file_read + search_tools), not active
        assert not hydrator.is_active


# =====================================================================
# Threshold configurability
# =====================================================================


class TestThresholdConfiguration:
    def test_default_threshold(self) -> None:
        hydrator = ToolHydrator()
        assert hydrator.threshold == _DEFAULT_THRESHOLD

    def test_custom_threshold(self) -> None:
        hydrator = ToolHydrator(threshold=50)
        assert hydrator.threshold == 50

    def test_threshold_boundary_exact(self) -> None:
        """At exactly the threshold, hydration is NOT active."""
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(10)
        hydrator.load_tools(defs, executors)
        assert not hydrator.is_active

    def test_threshold_boundary_plus_one(self) -> None:
        """One above threshold, hydration IS active."""
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(11)
        hydrator.load_tools(defs, executors)
        assert hydrator.is_active

    def test_custom_base_tool_names(self) -> None:
        hydrator = ToolHydrator(
            threshold=5,
            base_tool_names=frozenset({"file_read", "bash"}),
        )
        _, defs, executors = _build_registry(10)
        hydrator.load_tools(defs, executors)

        active = hydrator.get_active_tool_defs()
        active_names = {d["function"]["name"] for d in active}
        assert active_names == {"file_read", "bash"}


# =====================================================================
# pre_hydrate_from_query — Issue #579 discovery-tax elimination
# =====================================================================


class TestPreHydrateFromQuery:
    """Pre-hydrate the active tool set from the user's query.

    Issue #579: eliminate the 2-of-N turn tax where the LLM spends turn 1
    on a ``search_tools`` meta-call before reaching a real data tool.
    """

    def test_hydrates_bm25_top_k_for_matching_query(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        hydrated = hydrator.pre_hydrate_from_query(
            "create a github issue for the bug", top_k=5
        )

        assert "mcp_github_create_issue" in hydrated
        # All hydrated names are now in the active set
        active = hydrator.get_active_tool_defs()
        active_names = {d["function"]["name"] for d in active}
        assert "mcp_github_create_issue" in active_names

    def test_respects_top_k_cap(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        hydrated = hydrator.pre_hydrate_from_query(
            "create github issue merge pull request list", top_k=2
        )
        # BM25 returns at most top_k candidates
        assert len(hydrated) <= 2

    def test_noop_when_hydrator_inactive(self) -> None:
        """Below threshold -> pre_hydrate_from_query is a no-op.

        Sub-threshold registries already expose every tool to the LLM; no
        pre-hydrate work to do.
        """
        hydrator = ToolHydrator(threshold=30)
        _, defs, executors = _build_registry(10)
        hydrator.load_tools(defs, executors)

        hydrated = hydrator.pre_hydrate_from_query("create a github issue", top_k=5)
        assert hydrated == []
        assert not hydrator.is_active

    def test_noop_on_empty_query(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        assert hydrator.pre_hydrate_from_query("", top_k=5) == []
        assert hydrator.pre_hydrate_from_query("   ", top_k=5) == []

    def test_noop_on_no_bm25_match(self) -> None:
        """Query with no relevant terms returns empty, does not mutate state."""
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        before = hydrator.get_active_tool_defs()
        hydrated = hydrator.pre_hydrate_from_query("zzzznonexistentzzzz qqqqq", top_k=5)
        after = hydrator.get_active_tool_defs()

        assert hydrated == []
        # Active set unchanged
        assert {d["function"]["name"] for d in before} == {
            d["function"]["name"] for d in after
        }

    def test_idempotent_on_repeated_query(self) -> None:
        """Calling twice with the same query leaves the active set stable.

        Idempotence is at the ACTIVE SET level, not the return-value level:
        ``hydrate()`` returns every registry hit whether or not it was
        already hydrated, but the underlying ``_hydrated_names`` is a set
        — no duplicates accrue.
        """
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        hydrator.pre_hydrate_from_query("deploy to kubernetes", top_k=5)
        active_after_first = {
            d["function"]["name"] for d in hydrator.get_active_tool_defs()
        }

        hydrator.pre_hydrate_from_query("deploy to kubernetes", top_k=5)
        active_after_second = {
            d["function"]["name"] for d in hydrator.get_active_tool_defs()
        }

        assert active_after_first == active_after_second
        # And at least one kubernetes-matching tool was hydrated.
        assert any("kubernetes" in n for n in active_after_first)

    def test_search_tools_remains_available_as_escape_hatch(self) -> None:
        """Pre-hydrate doesn't remove search_tools; LLM can still discover
        tools the BM25 pre-hydrate missed.
        """
        hydrator = ToolHydrator(threshold=10)
        _, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        hydrator.pre_hydrate_from_query("github issue", top_k=5)
        active = hydrator.get_active_tool_defs()
        active_names = {d["function"]["name"] for d in active}
        # Base tool set (including search_tools surrogate) remains available.
        # search_tools itself is registered by AgentLoop, not ToolHydrator;
        # here we verify the ``file_read`` base tool is still present as a
        # proxy for "base set preserved".
        assert "file_read" in active_names


class TestAgentLoopCallsPreHydrate:
    """AgentLoop.run_turn MUST call pre_hydrate_from_query on the user
    message before the first LLM completion (issue #579).
    """

    def test_run_turn_invokes_pre_hydrate_when_hydrator_active(self) -> None:
        hydrator = ToolHydrator(threshold=10)
        registry, defs, executors = _build_registry(20)
        hydrator.load_tools(defs, executors)

        # Track calls to pre_hydrate_from_query without mocking the method
        # (that would replace the behavior we care about).
        pre_hydrate_calls: list[tuple[str, int]] = []
        original = hydrator.pre_hydrate_from_query

        def spy(query: str, *, top_k: int = 5) -> list[str]:
            pre_hydrate_calls.append((query, top_k))
            return original(query, top_k=top_k)

        hydrator.pre_hydrate_from_query = spy  # type: ignore[method-assign]

        loop = AgentLoop(
            config=KzConfig(max_turns=1),
            tools=registry,
            client=MagicMock(),
            adapter=MagicMock(),
            hydrator=hydrator,
        )

        # Drive one turn with a short-circuit stream (no tool calls -> loop exits)
        async def fake_stream() -> Any:
            if False:
                yield  # make this an async generator

        with patch.object(loop, "_stream_completion", side_effect=fake_stream):
            asyncio.run(_drain(loop.run_turn("create a github issue for the bug")))

        assert len(pre_hydrate_calls) == 1
        assert pre_hydrate_calls[0][0] == "create a github issue for the bug"
        assert pre_hydrate_calls[0][1] == 5

    def test_run_turn_skips_pre_hydrate_when_hydrator_inactive(self) -> None:
        """Sub-threshold registry -> hydrator.is_active is False -> no
        pre_hydrate call (all tools are already visible to the LLM).
        """
        hydrator = ToolHydrator(threshold=50)
        registry, defs, executors = _build_registry(15)
        hydrator.load_tools(defs, executors)

        pre_hydrate_calls: list[tuple[str, int]] = []
        original = hydrator.pre_hydrate_from_query

        def spy(query: str, *, top_k: int = 5) -> list[str]:
            pre_hydrate_calls.append((query, top_k))
            return original(query, top_k=top_k)

        hydrator.pre_hydrate_from_query = spy  # type: ignore[method-assign]

        loop = AgentLoop(
            config=KzConfig(max_turns=1),
            tools=registry,
            client=MagicMock(),
            adapter=MagicMock(),
            hydrator=hydrator,
        )

        async def fake_stream() -> Any:
            if False:
                yield

        with patch.object(loop, "_stream_completion", side_effect=fake_stream):
            asyncio.run(_drain(loop.run_turn("anything")))

        assert pre_hydrate_calls == []


async def _drain(gen: Any) -> None:
    """Exhaust an async generator, discarding yields."""
    async for _ in gen:
        pass
