# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tool hydration for large tool sets.

When an agent has access to many tools (e.g. MCP-discovered tools from
multiple servers), sending all tool schemas on every LLM call wastes
tokens and degrades model accuracy. The :class:`ToolHydrator` splits
tools into an always-available base set and a deferred set that the LLM
can pull in on demand via the ``search_tools`` meta-tool.

Architecture
------------
The hydrator sits between the :class:`~kaizen_agents.delegate.loop.ToolRegistry`
and the LLM call. When the total tool count exceeds the configurable
*threshold* (default 30), the hydrator activates:

- **Base tools** (~15) are always sent to the LLM.
- **Deferred tools** are indexed but not sent until the LLM calls
  ``search_tools`` with a query.
- The LLM decides when it needs more tools — no deterministic routing.

Below threshold, all tools are passed directly (existing behaviour).
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default base tools — these are always available regardless of hydration
# ---------------------------------------------------------------------------

_DEFAULT_BASE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "file_read",
        "file_write",
        "file_edit",
        "glob",
        "grep",
        "bash",
        "search_tools",
    }
)

_DEFAULT_THRESHOLD: int = 30


# ---------------------------------------------------------------------------
# BM25-style scoring (stdlib only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ToolDoc:
    """A searchable document for one tool."""

    name: str
    description: str
    tokens: list[str]


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase alpha-numeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _build_index(tools: dict[str, _ToolDoc]) -> dict[str, int]:
    """Build document-frequency index across all tool docs."""
    df: Counter[str] = Counter()
    for doc in tools.values():
        unique = set(doc.tokens)
        for token in unique:
            df[token] += 1
    return dict(df)


def _bm25_score(
    query_tokens: list[str],
    doc: _ToolDoc,
    df: dict[str, int],
    n_docs: int,
    avgdl: float,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compute BM25 relevance score for a single document.

    Parameters
    ----------
    query_tokens:
        Tokenized search query.
    doc:
        The tool document to score.
    df:
        Document frequency map (token -> number of docs containing it).
    n_docs:
        Total number of documents in the corpus.
    avgdl:
        Average document length (in tokens) across the corpus.
    k1:
        Term saturation parameter.
    b:
        Length normalization parameter.
    """
    if avgdl == 0:
        return 0.0

    score = 0.0
    doc_len = len(doc.tokens)
    tf_map: Counter[str] = Counter(doc.tokens)

    for term in query_tokens:
        if term not in tf_map:
            continue
        tf = tf_map[term]
        doc_freq = df.get(term, 0)
        # IDF with floor to avoid negative scores for very common terms
        idf = max(0.0, math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0))
        # BM25 TF component
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * (doc_len / avgdl))
        score += idf * (numerator / denominator)

    # Boost for exact name match
    name_tokens = set(_tokenize(doc.name))
    for term in query_tokens:
        if term in name_tokens:
            score += 2.0

    return score


# ---------------------------------------------------------------------------
# ToolHydrator
# ---------------------------------------------------------------------------


@dataclass
class ToolHydrator:
    """Manages tool hydration for large tool sets.

    When the total number of registered tools exceeds *threshold*, only
    the base tools are sent to the LLM. The LLM can discover and
    hydrate additional tools by calling ``search_tools``.

    Parameters
    ----------
    threshold:
        Minimum tool count to activate hydration. Below this, all tools
        are passed through directly. Default: 30.
    base_tool_names:
        Names of tools that are always available. Defaults to the
        standard kz tool set plus ``search_tools``.
    """

    threshold: int = _DEFAULT_THRESHOLD
    base_tool_names: frozenset[str] = field(
        default_factory=lambda: _DEFAULT_BASE_TOOL_NAMES
    )

    # Internal state
    _all_tool_defs: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _all_tool_executors: dict[str, Any] = field(default_factory=dict, repr=False)
    _hydrated_names: set[str] = field(default_factory=set, repr=False)
    _search_index: dict[str, _ToolDoc] = field(default_factory=dict, repr=False)
    _df: dict[str, int] = field(default_factory=dict, repr=False)
    _avgdl: float = field(default=0.0, repr=False)

    @property
    def is_active(self) -> bool:
        """Whether hydration is active (tool count exceeds threshold)."""
        return len(self._all_tool_defs) > self.threshold

    @property
    def total_tool_count(self) -> int:
        """Total number of registered tools."""
        return len(self._all_tool_defs)

    def load_tools(
        self,
        tool_defs: dict[str, dict[str, Any]],
        tool_executors: dict[str, Any],
    ) -> None:
        """Load the full tool set into the hydrator.

        Parameters
        ----------
        tool_defs:
            Mapping of tool name to OpenAI function-calling format dict.
        tool_executors:
            Mapping of tool name to async executor callable.
        """
        self._all_tool_defs = dict(tool_defs)
        self._all_tool_executors = dict(tool_executors)
        self._hydrated_names = set()
        self._build_search_index()
        logger.info(
            "ToolHydrator loaded %d tools (threshold=%d, active=%s)",
            len(self._all_tool_defs),
            self.threshold,
            self.is_active,
        )

    def _build_search_index(self) -> None:
        """Build the BM25 search index over all deferred tools."""
        self._search_index = {}
        for name, tool_def in self._all_tool_defs.items():
            if name in self.base_tool_names:
                continue
            func_info = tool_def.get("function", {})
            desc = func_info.get("description", "")
            text = f"{name} {desc}"
            tokens = _tokenize(text)
            self._search_index[name] = _ToolDoc(
                name=name, description=desc, tokens=tokens
            )

        self._df = _build_index(self._search_index)
        total_tokens = sum(len(doc.tokens) for doc in self._search_index.values())
        n_docs = len(self._search_index)
        self._avgdl = total_tokens / n_docs if n_docs > 0 else 0.0

    def get_active_tool_defs(self) -> list[dict[str, Any]]:
        """Return OpenAI-format tool defs for currently active tools.

        If hydration is not active (below threshold), returns all tools.
        Otherwise returns base tools + currently hydrated tools.
        """
        if not self.is_active:
            return list(self._all_tool_defs.values())

        active_names = self._get_active_names()
        return [
            self._all_tool_defs[name]
            for name in active_names
            if name in self._all_tool_defs
        ]

    def get_active_executor(self, name: str) -> Any | None:
        """Return the executor for a tool if it is currently active or if hydration is off.

        Parameters
        ----------
        name:
            Tool name to look up.

        Returns
        -------
        The async executor callable, or None if the tool is not active.
        """
        if not self.is_active:
            return self._all_tool_executors.get(name)

        if name in self._get_active_names():
            return self._all_tool_executors.get(name)

        return None

    def has_executor(self, name: str) -> bool:
        """Check if a tool exists (regardless of hydration state)."""
        return name in self._all_tool_executors

    def get_executor_force(self, name: str) -> Any | None:
        """Return executor for any registered tool, bypassing hydration check.

        Used internally when the loop needs to execute a tool that was
        just hydrated in the same turn.
        """
        return self._all_tool_executors.get(name)

    def hydrate(self, tool_names: list[str]) -> list[str]:
        """Add tools to the active set.

        Parameters
        ----------
        tool_names:
            Names of tools to hydrate (make available to the LLM).

        Returns
        -------
        List of tool names that were successfully hydrated (exist in
        the registry).
        """
        hydrated: list[str] = []
        for name in tool_names:
            if name in self._all_tool_defs and name not in self.base_tool_names:
                self._hydrated_names.add(name)
                hydrated.append(name)
                logger.debug("Hydrated tool: %s", name)

        logger.info("Hydrated %d tools: %s", len(hydrated), hydrated)
        return hydrated

    def dehydrate(self) -> None:
        """Reset the active set to base tools only."""
        count = len(self._hydrated_names)
        self._hydrated_names.clear()
        logger.info("Dehydrated %d tools, reset to base set", count)

    def search(self, query: str, *, top_n: int = 10) -> list[dict[str, Any]]:
        """Search over tool names and descriptions.

        Parameters
        ----------
        query:
            Free-text search query.
        top_n:
            Maximum number of results to return.

        Returns
        -------
        List of dicts with ``name``, ``description``, and ``score``
        keys, sorted by relevance (highest first).
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        n_docs = len(self._search_index)
        if n_docs == 0:
            return []

        scored: list[tuple[float, str, str]] = []
        for name, doc in self._search_index.items():
            score = _bm25_score(
                query_tokens,
                doc,
                self._df,
                n_docs,
                self._avgdl,
            )
            if score > 0:
                scored.append((score, name, doc.description))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: list[dict[str, Any]] = []
        for score, name, description in scored[:top_n]:
            results.append(
                {
                    "name": name,
                    "description": description,
                    "score": round(score, 3),
                }
            )

        return results

    def _get_active_names(self) -> set[str]:
        """Return the set of currently active tool names."""
        active = set()
        for name in self.base_tool_names:
            if name in self._all_tool_defs:
                active.add(name)
        active.update(self._hydrated_names)
        return active
