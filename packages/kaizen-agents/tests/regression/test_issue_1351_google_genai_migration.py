"""Regression test for issue #1351 — Gemini adapters off deprecated SDK.

Bug: the Gemini code paths imported the **deprecated** ``google.generativeai``
package, and that package was declared **only** in ``[dev]`` extras — not as a
runtime dependency. Two failure modes:

1. Deprecation: ``google.generativeai`` is end-of-life; consumers break at
   import once Google removes it.
2. Undeclared runtime dependency: a normal ``pip install kaizen-agents``
   (without ``[dev]``) does not install the SDK, so the Gemini path raises
   ``ImportError`` at adapter construction.

The fix migrates both adapters to the supported ``google.genai`` SDK and
declares the provider SDKs (``google-genai`` + the sibling ``anthropic``, which
had the identical undeclared-runtime-dep defect) as **runtime** dependencies.

These tests assert behaviour (the constructed client is a ``google.genai``
client; the adapter builds ``google.genai`` ``Tool`` objects) plus the manifest
contract (runtime deps declared; deprecated dep gone). Deterministic + offline:
``genai.Client(api_key=...)`` performs no network I/O at construction.
"""

from __future__ import annotations

import asyncio
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


@pytest.mark.regression
def test_google_stream_adapter_uses_google_genai_client():
    """GoogleStreamAdapter constructs a ``google.genai`` Client (not the old SDK)."""
    from google import genai

    from kaizen_agents.delegate.adapters.google_adapter import GoogleStreamAdapter

    adapter = GoogleStreamAdapter(api_key="dummy-key", default_model="gemini-2.0-flash")
    assert isinstance(adapter._client, genai.Client)


@pytest.mark.regression
def test_gemini_cli_adapter_initializes_google_genai_client():
    """GeminiCLIAdapter.ensure_initialized builds a ``google.genai`` Client."""
    from google import genai
    from google.genai import types

    from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(api_key="dummy-key", model="gemini-2.0-flash")
    asyncio.run(adapter.ensure_initialized())
    assert isinstance(adapter._client, genai.Client)
    assert adapter._types is types


@pytest.mark.regression
def test_build_tools_produces_google_genai_tool_objects():
    """_build_tools emits ``google.genai`` types.Tool (code-exec + functions)."""
    from google.genai import types

    from kaizen_agents.runtime_adapters.gemini_cli import GeminiCLIAdapter

    adapter = GeminiCLIAdapter(
        api_key="dummy-key",
        model="gemini-2.0-flash",
        enable_code_execution=True,
        custom_tools=[
            {
                "name": "t",
                "description": "d",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )
    asyncio.run(adapter.ensure_initialized())
    tools = adapter._build_tools(SimpleNamespace(tools=None))
    assert tools and all(isinstance(t, types.Tool) for t in tools)
    # Folds into a real GenerateContentConfig without raising.
    cfg = adapter._build_generate_config(tools)
    assert isinstance(cfg, types.GenerateContentConfig)
    assert len(cfg.tools) == len(tools)


@pytest.mark.regression
def test_google_stream_adapter_tools_coerce_into_config():
    """_convert_tools_for_gemini output coerces into GenerateContentConfig.tools."""
    from google.genai import types

    from kaizen_agents.delegate.adapters.google_adapter import _convert_tools_for_gemini

    tools = _convert_tools_for_gemini(
        [
            {
                "function": {
                    "name": "f",
                    "description": "d",
                    "parameters": {"type": "object", "properties": {}},
                }
            }
        ]
    )
    cfg = types.GenerateContentConfig(tools=tools)
    assert isinstance(cfg.tools[0], types.Tool)


@pytest.mark.regression
def test_no_deprecated_generativeai_import_in_adapter_modules():
    """Importing the migrated modules must not pull in google.generativeai."""
    # Importing the adapters must not register the deprecated package.
    import kaizen_agents.delegate.adapters.google_adapter  # noqa: F401
    import kaizen_agents.runtime_adapters.gemini_cli  # noqa: F401

    assert "google.generativeai" not in sys.modules


@pytest.mark.regression
def test_provider_sdks_declared_as_runtime_dependencies():
    """google-genai + anthropic are runtime deps; deprecated SDK is gone."""
    data = tomllib.loads(_PYPROJECT.read_text())
    runtime = data["project"]["dependencies"]
    dev = data["project"].get("optional-dependencies", {}).get("dev", [])

    def _names(specs: list[str]) -> set[str]:
        out = set()
        for spec in specs:
            name = spec.split(">=")[0].split("==")[0].split("[")[0].strip()
            out.add(name)
        return out

    runtime_names = _names(runtime)
    assert "google-genai" in runtime_names, runtime
    assert "anthropic" in runtime_names, runtime
    # The deprecated SDK must not appear anywhere in the manifest.
    assert "google-generativeai" not in runtime_names
    assert "google-generativeai" not in _names(dev)
