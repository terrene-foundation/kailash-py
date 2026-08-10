# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Two consumer-facing breaks: the declared floor, and the gated-tool schema.

FINDING A — THE VERSION FLOOR IS PART OF THE CODE, NOT PACKAGING TRIVIA.
``kaizen-agents`` imports symbols from ``kailash-kaizen`` at MODULE scope, so a
symbol that post-dates the declared floor is not a degraded feature — it is an
``ImportError`` on ``import kaizen_agents`` for every user who upgrades one
package without the other. The floor is therefore an executable claim, and this
file makes it one: it re-derives every module-scope ``kaizen.*`` import from
source and asserts each resolves, so a future cross-package import cannot land
without someone confronting the floor.

The trap it closes is specific. It is NOT enough to check that the MODULE exists
at the floor — ``kaizen.core.tool_formatters`` predates 2.36.0 while
``normalize_tool_input_schema`` (added below, for Finding B) does not. Only a
SYMBOL-level check catches that, and the module-level version of this sweep
would have passed while shipping the break.

Two properties of the INSTRUMENTS here, because a check that cannot return the
other answer is not evidence:

1. The sweep matches BOTH ``ast.ImportFrom`` AND ``ast.Import``. Matching only
   the former reported CLEAN over a module-scope ``import kaizen.<module>``,
   which breaks consumers identically.
   ``test_the_sweep_sees_plain_module_imports_not_only_from_imports`` is what
   reds when that blindness returns; the real-tree assertions cannot, because
   the tree currently contains no such import.
2. The floor is checked TWICE, and the two tests prove different things. The
   pyproject-vs-constant check is STRUCTURAL — it catches a silent lowering of
   the declared floor and nothing else, because it resolves symbols against the
   local editable tree, which carries every symbol no matter what any release
   contains. The claim "no published release below the floor is missing these
   symbols" is made by the git-tag probe, which reads published tags and reds
   if the floor is lowered onto one of them.

FINDING B — ``.get(key, default)`` DOES NOT FIRE ON A PRESENT-BUT-EMPTY VALUE.
A permission-gated MCP tool advertises ``inputSchema: {}``. Every converter read
it as ``tool.get("inputSchema", {})``, whose default fires only when the key is
ABSENT — so the empty dict flowed through untouched. Anthropic's
``InputSchemaTyped`` declares ``type: Required[Literal["object"]]``, so
``input_schema: {}`` is REJECTED; and even where an empty schema is accepted the
model loses every argument name for that tool.

This is the documented configuration, not an edge case: the pattern
``required_permission=f"tools.{tool_name}"`` in the MCP architecture docs gates
EVERY tool.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.regression

_HERE = pathlib.Path(__file__).resolve()
_AGENTS_SRC = _HERE.parents[2] / "src"
_PYPROJECT = _HERE.parents[2] / "pyproject.toml"
_REPO_ROOT = _HERE.parents[4]
_KAIZEN_SRC_PREFIX = "packages/kailash-kaizen/src"

#: Sentinel symbol for `import kaizen.foo` (a whole-module import, no symbol).
#: The pair is then ("kaizen.foo", MODULE_ONLY) and resolution means "the module
#: itself must import", not "the module must expose an attribute".
MODULE_ONLY = ""


def _is_kaizen(module: str) -> bool:
    """True for `kaizen` and `kaizen.*`, False for the `kaizen_agents` sibling."""
    return module == "kaizen" or module.startswith("kaizen.")


# ---------------------------------------------------------------------------
# Finding A — the declared floor must cover every module-scope kaizen import
# ---------------------------------------------------------------------------
def _kaizen_imports_in_source(source: str) -> set[tuple[str, str]]:
    """Every (module, symbol) `kaizen.*` import at MODULE scope in `source`.

    BOTH statement forms are swept, because BOTH break `import kaizen_agents`
    when the target does not exist at the declared floor:

      * ``from kaizen.x import Y``  -> ("kaizen.x", "Y")     [ast.ImportFrom]
      * ``import kaizen.x``         -> ("kaizen.x", MODULE_ONLY)  [ast.Import]
      * ``import kaizen.x as z``    -> ("kaizen.x", MODULE_ONLY)  [ast.Import]

    An ``ast.Import``-only sweep was the original defect here: a module-scope
    ``import kaizen.<new_module>`` breaks every consumer of kaizen-agents
    identically to a ``from``-import, and the ImportFrom-only walk reported
    CLEAN over it. Latent at the time of the fix (no such import existed in
    the tree), which is exactly when a blind instrument is cheapest to fix and
    hardest to notice.

    Module scope only: a function-local import is lazy, so it degrades at call
    time rather than breaking `import kaizen_agents`. `kaizen_agents.*` is a
    DIFFERENT distribution and is excluded (`_is_kaizen` rejects it: the
    underscore means it never matches the "kaizen." dotted prefix).
    """
    pairs: set[tuple[str, str]] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - defensive
        return pairs
    for node in tree.body:  # top level ONLY
        if isinstance(node, ast.ImportFrom):
            # `node.level == 0` excludes relative imports (`from .x import y`),
            # which resolve inside kaizen-agents and cross no package boundary.
            if node.level == 0 and node.module and _is_kaizen(node.module):
                for alias in node.names:
                    pairs.add((node.module, alias.name))
        elif isinstance(node, ast.Import):
            # `alias.name` is the full dotted module path; `alias.asname` is
            # irrelevant to whether the target resolves.
            for alias in node.names:
                if _is_kaizen(alias.name):
                    pairs.add((alias.name, MODULE_ONLY))
    return pairs


def _module_scope_kaizen_imports(
    root: pathlib.Path | None = None,
) -> set[tuple[str, str]]:
    """`_kaizen_imports_in_source` applied across a source tree.

    `root` is injectable ONLY so the sweep itself can be tested against a
    synthetic tree; production callers use the default (kaizen-agents/src).
    """
    src = _AGENTS_SRC if root is None else root
    pairs: set[tuple[str, str]] = set()
    for path in src.rglob("*.py"):
        pairs |= _kaizen_imports_in_source(path.read_text(encoding="utf-8"))
    return pairs


# ---------------------------------------------------------------------------
# The floor's evidence base.
#
# Each symbol below carries the commit that FIRST introduced it, derived with
# `git log -S'<symbol>' -- <path>` (not from memory, not from a changelog). All
# three commits are ancestors of HEAD, and all three POST-DATE `kaizen-v2.45.0`
# (commit ba3cc1994, 2026-07-25) — the newest published kailash-kaizen tag in
# this repository. There is no `kaizen-v2.46.0` tag: the declared floor names a
# version that has not been released yet, which is why the tag-based probe
# below asserts a strict lower bound rather than "the floor version has them".
#
#   scrub_local_error / scrub_remote_error
#       b2d3acce55cbd8075c70817d8a69c53a9df06b7f  2026-08-04
#       ("fix(kaizen): the 180-site scrub sweep opened a credential hole ...")
#       NB the module file arrived earlier (c0c99b589064, 2026-07-26); these
#       two functions did not. The per-SYMBOL commit is the load-bearing one.
#   ReasoningDegradedError
#       0066e4fcbf170e2699ff727362e6bcb58d3650f1  2026-07-26
#       ("fix(kaizen,dataflow,nexus,core): drain the #1970-#1981 forest")
#   normalize_tool_input_schema
#       269038fd9df1888fe580c355733def685ce29a6d  2026-08-04
#       ("fix(kaizen-agents): release-blocking version floor + gated tools ...")
# ---------------------------------------------------------------------------
_REQUIRED_POST_FLOOR_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("kaizen.utils.credential_scrub", "scrub_local_error"),
    ("kaizen.utils.credential_scrub", "scrub_remote_error"),
    ("kaizen.llm.reasoning", "ReasoningDegradedError"),
    ("kaizen.core.tool_formatters", "normalize_tool_input_schema"),
)

#: The floor recorded when the symbols above were swept. A structural pin only
#: — see `test_declared_floor_is_readable_and_at_least_the_recorded_value` for
#: exactly what it does and does not establish.
_RECORDED_FLOOR = (2, 46, 0)


def _git(*args: str) -> str | None:
    """Run a read-only git command; None on any failure. Never raises."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - defensive
        return None
    return proc.stdout if proc.returncode == 0 else None


def _published_kaizen_tags() -> list[tuple[tuple[int, int, int], str]]:
    """Published `kaizen-vX.Y.Z` tags, highest version first.

    `kaizen-v*` is the kailash-kaizen distribution's own tag namespace; the
    bare `vX.Y.Z` tags belong to the core `kailash` package and are a DIFFERENT
    version line that must not be mixed in here.
    """
    out = _git("tag", "--list", "kaizen-v*")
    if out is None:
        return []
    tags: list[tuple[tuple[int, int, int], str]] = []
    for line in out.splitlines():
        tag = line.strip()
        m = re.fullmatch(r"kaizen-v(\d+)\.(\d+)\.(\d+)", tag)
        if m:
            major, minor, patch = (int(g) for g in m.groups())
            tags.append(((major, minor, patch), tag))
    return sorted(tags, reverse=True)


def _module_to_repo_path(module: str) -> str:
    """`kaizen.utils.credential_scrub` -> the repo-relative source path."""
    return f"{_KAIZEN_SRC_PREFIX}/{module.replace('.', '/')}.py"


def _defines_symbol(source: str, symbol: str) -> bool:
    """True if `source` binds `symbol` at MODULE scope.

    Structural (AST), not lexical: a mention of the name in a docstring, a
    comment, or a nested function must not read as a definition.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # pragma: no cover - defensive
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    return True
        elif isinstance(node, (ast.AnnAssign, ast.ImportFrom, ast.Import)):
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == symbol:
                    return True
            else:
                for alias in node.names:
                    if (alias.asname or alias.name.split(".")[0]) == symbol:
                        return True
    return False


def _required_symbols_absent_at(tag: str) -> set[str]:
    """Which required symbols are MISSING from the tree at `tag`."""
    absent: set[str] = set()
    sources: dict[str, str | None] = {}
    for module, symbol in _REQUIRED_POST_FLOOR_SYMBOLS:
        if module not in sources:
            sources[module] = _git("show", f"{tag}:{_module_to_repo_path(module)}")
        source = sources[module]
        # `None` means the file does not exist at that tag at all -> absent.
        if source is None or not _defines_symbol(source, symbol):
            absent.add(f"{module}.{symbol}")
    return absent


def _declared_floor() -> tuple[int, ...]:
    text = _PYPROJECT.read_text(encoding="utf-8")
    m = re.search(r'"kailash-kaizen>=(\d+)\.(\d+)\.(\d+)"', text)
    assert m, "no kailash-kaizen floor declared in kaizen-agents/pyproject.toml"
    return tuple(int(g) for g in m.groups())


class TestDeclaredFloorCoversEveryCrossPackageImport:
    def test_the_sweep_is_not_vacuous(self) -> None:
        """The enumeration must find something, or every claim below is empty."""
        pairs = _module_scope_kaizen_imports()
        assert len(pairs) >= 50, (
            f"only {len(pairs)} module-scope kaizen imports found; the AST walk "
            "is not reaching the tree and the resolution claim below would pass "
            "vacuously"
        )

    def test_the_sweep_sees_plain_module_imports_not_only_from_imports(self) -> None:
        """The sweep must catch BOTH import statement forms.

        This is the direct guard on the sweep's own blind spot. A sweep that
        matches only `ast.ImportFrom` reports CLEAN over a module-scope
        `import kaizen.<anything>` — which breaks `import kaizen_agents` just
        as hard. Because that shape is (currently) absent from the real tree,
        NOTHING in the real-tree assertions can red when the sweep goes blind
        to it; only a synthetic source can. Feeding a fixed source string also
        keeps the check independent of what the real tree happens to contain.
        """
        source = (
            "from kaizen.core.tool_formatters import normalize_tool_input_schema\n"
            "import kaizen.llm.reasoning\n"
            "import kaizen.utils.credential_scrub as scrub\n"
            "import kaizen\n"
            "import kaizen_agents.runtime_adapters\n"  # sibling distribution
            "from kaizen_agents.patterns import Blackboard\n"  # sibling
            "from . import sibling_module\n"  # relative, crosses no boundary
            "def f():\n"
            "    import kaizen.function_local_is_lazy\n"  # not module scope
            "    from kaizen.also_lazy import Thing\n"
        )
        assert _kaizen_imports_in_source(source) == {
            ("kaizen.core.tool_formatters", "normalize_tool_input_schema"),
            ("kaizen.llm.reasoning", MODULE_ONLY),
            ("kaizen.utils.credential_scrub", MODULE_ONLY),
            ("kaizen", MODULE_ONLY),
        }

    def test_every_module_scope_symbol_resolves(self) -> None:
        """The installed kailash-kaizen actually provides every symbol.

        Catches the SHAPE of the bug at head: a module-scope import of a symbol
        the depended-on package does not export.
        """
        missing = []
        for module, symbol in sorted(_module_scope_kaizen_imports()):
            try:
                mod = importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001 - reporting, not control flow
                missing.append(f"{module} (module import failed: {exc!r})")
                continue
            # MODULE_ONLY == `import kaizen.x`: importing the module IS the
            # whole contract, so the successful import above already proved it.
            if symbol != MODULE_ONLY and not hasattr(mod, symbol):
                missing.append(f"{module}.{symbol}")
        assert missing == [], (
            "kaizen-agents imports these at MODULE scope but the installed "
            f"kailash-kaizen does not provide them: {missing}. Every one is an "
            "ImportError at `import kaizen_agents`."
        )

    def test_declared_floor_is_readable_and_at_least_the_recorded_value(
        self,
    ) -> None:
        """STRUCTURAL ONLY. Reads the declared floor; compares to a constant.

        WHAT THIS PROVES: `kaizen-agents/pyproject.toml` declares a
        `kailash-kaizen>=X.Y.Z` floor, it parses, and X.Y.Z has not been
        silently LOWERED below the value recorded when the floor was set.

        WHAT THIS DOES **NOT** PROVE — read before trusting it: it does NOT
        prove that kailash-kaizen 2.46.0 carries the required symbols. It
        cannot. `_REQUIRED_POST_FLOOR_SYMBOLS` resolves against the LOCAL
        EDITABLE source tree, which always has every symbol regardless of what
        any released artifact contains, so no outcome of THIS assertion
        distinguishes "2.46.0 carries them" from "it does not". The constant
        below is a recorded decision, not a measurement.

        The claim this test cannot make is made instead by
        `test_floor_exceeds_every_published_tag_missing_a_required_symbol`,
        which reads published git tags and CAN return the other answer.
        """
        text = _PYPROJECT.read_text(encoding="utf-8")
        m = re.search(r'"kailash-kaizen>=(\d+)\.(\d+)\.(\d+)"', text)
        assert m, "no kailash-kaizen floor declared in kaizen-agents/pyproject.toml"
        floor = tuple(int(g) for g in m.groups())
        assert floor >= _RECORDED_FLOOR, (
            f"declared floor {floor} is below the recorded floor "
            f"{_RECORDED_FLOOR}, which was set because the module-scope symbols "
            "kaizen-agents imports are absent from every published "
            "kailash-kaizen release (see _REQUIRED_POST_FLOOR_SYMBOLS for the "
            "per-symbol first-carrying commit). Users who upgrade kaizen-agents "
            "alone break at import."
        )

    def test_floor_exceeds_every_published_tag_missing_a_required_symbol(
        self,
    ) -> None:
        """DISCRIMINATING. Resolves the symbols against PUBLISHED git tags.

        The instrument this test replaces compared the floor to a hardcoded
        tuple while resolving symbols against the local editable tree — so no
        result it could produce distinguished "the floor is right" from "the
        floor is wrong". This one reads the release tags: it finds the HIGHEST
        published `kaizen-v*` tag whose tree is MISSING at least one required
        symbol, and asserts the declared floor is strictly above it.

        It CAN return the other answer. Lower the floor in pyproject.toml to
        2.45.0 (or any published version missing a symbol) and this REDS,
        naming the tag and the absent symbol. That is the property the
        hardcoded-tuple check never had.

        Hermetic and offline: `git show <tag>:<path>` reads objects already in
        the local repository — no network, no index lookup, no wheel download.
        Where the tags are unavailable (shallow clone, `fetch-depth: 1`, an
        exported tarball) the probe SKIPS with an explicit reason rather than
        degrading into a check that passes for the wrong reason.
        """
        if shutil.which("git") is None:
            pytest.skip("probe-unavailable: git not on PATH")
        if _git("rev-parse", "--git-dir") is None:
            pytest.skip("probe-unavailable: not a git checkout")
        tags = _published_kaizen_tags()
        if not tags:
            pytest.skip(
                "probe-unavailable: no kaizen-v* tags in this checkout "
                "(shallow clone or tags not fetched)"
            )

        floor = _declared_floor()
        for version, tag in tags:  # highest published version first
            absent = _required_symbols_absent_at(tag)
            if not absent:
                continue
            assert floor > version, (
                f"declared floor {floor} does NOT exceed published tag {tag}, "
                f"whose tree is missing {sorted(absent)}. A user resolving "
                f"kailash-kaizen=={'.'.join(map(str, version))} against this "
                "floor gets an ImportError at `import kaizen_agents`."
            )
            return
        pytest.skip(
            "probe-inconclusive: every scanned published tag carries every "
            "required symbol, so no tag constrains the floor from below"
        )

    @pytest.mark.parametrize(("module", "symbol"), _REQUIRED_POST_FLOOR_SYMBOLS)
    def test_the_specific_post_floor_symbols_exist(
        self, module: str, symbol: str
    ) -> None:
        """Named explicitly so the floor's rationale stays checkable.

        Scope note: this resolves against the INSTALLED kailash-kaizen, which
        in this repo is the local editable tree — so it proves the symbol
        exists AT HEAD, not that any released version carries it. That is
        still the assertion worth having: if one of these is ever removed from
        kailash-kaizen, it reds here rather than at a consumer's first import.
        """
        assert hasattr(importlib.import_module(module), symbol)


# ---------------------------------------------------------------------------
# Finding B — a gated tool's empty inputSchema must never reach a provider
# ---------------------------------------------------------------------------
#: What a permission-GATED MCP tool advertises: the key is PRESENT and EMPTY.
GATED_TOOL = {"name": "search_docs", "description": "gated", "inputSchema": {}}

#: An ordinary tool, for the control direction.
FULL_TOOL = {
    "name": "search_docs",
    "description": "ordinary",
    "inputSchema": {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
}


def _converters():
    from kaizen.core.tool_formatters import (
        convert_mcp_to_anthropic_tools,
        convert_mcp_to_openai_tools,
    )
    from kaizen_agents.runtime_adapters.tool_mapping.mcp import MCPToolMapper

    return {
        "anthropic": lambda t: convert_mcp_to_anthropic_tools([t])[0]["input_schema"],
        "openai": lambda t: convert_mcp_to_openai_tools([t])[0]["function"][
            "parameters"
        ],
        "kaizen_mcp_mapper": lambda t: MCPToolMapper._from_mcp_tool(t)["function"][
            "parameters"
        ],
    }


class TestGatedToolSchemaIsValidForEveryConverter:
    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_gated_tool_emits_a_valid_object_schema(self, name: str) -> None:
        schema = _converters()[name](GATED_TOOL)
        assert schema.get("type") == "object", (
            f"{name} emitted {schema!r} for a permission-gated tool. Anthropic's "
            "InputSchemaTyped declares type: Required[Literal['object']], so an "
            "empty schema is rejected outright; and any provider that accepts it "
            "leaves the model with no argument names at all."
        )
        assert "properties" in schema

    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_ordinary_tool_schema_is_passed_through_unchanged(self, name: str) -> None:
        """CONTROL. Normalization must not rewrite a real schema.

        A fix that stamped `{"type": "object", "properties": {}}` over every
        tool would pass the assertion above while destroying every real tool's
        parameters.
        """
        assert _converters()[name](FULL_TOOL) == FULL_TOOL["inputSchema"]

    @pytest.mark.parametrize("name", sorted(_converters()))
    def test_absent_key_still_handled(self, name: str) -> None:
        """The pre-existing `.get(..., {})` case must not regress."""
        schema = _converters()[name]({"name": "x", "description": "d"})
        assert schema.get("type") == "object"

    def test_schema_with_properties_but_no_type_is_completed(self) -> None:
        """JSON Schema leaves a missing `type` unconstrained; the tool APIs
        all mean `object` in this position."""
        from kaizen.core.tool_formatters import normalize_tool_input_schema

        out = normalize_tool_input_schema({"properties": {"q": {"type": "string"}}})
        assert out["type"] == "object"
        assert out["properties"] == {"q": {"type": "string"}}

    def test_normalizer_does_not_mutate_its_argument(self) -> None:
        """The caller's dict is shared with the MCP client's tool cache."""
        from kaizen.core.tool_formatters import normalize_tool_input_schema

        original = {"properties": {"q": {"type": "string"}}}
        snapshot = {"properties": {"q": {"type": "string"}}}
        normalize_tool_input_schema(original)
        assert original == snapshot

    def test_every_converter_shares_one_normalizer(self) -> None:
        """Three converters that 'must agree' is the defect; one is the fix.

        Pins that no converter grew a private copy of the empty-schema rule.
        """
        import kaizen.core.tool_formatters as tf
        import kaizen_agents.runtime_adapters.tool_mapping.mcp as mcp_map

        assert mcp_map.normalize_tool_input_schema is tf.normalize_tool_input_schema
