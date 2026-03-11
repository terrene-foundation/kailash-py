# Tool Mapping Infrastructure Developer Guide

The Tool Mapping infrastructure converts Kaizen tools (OpenAI function calling format) to provider-specific formats for different runtime adapters.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kaizen Tool Format                        │
│  (OpenAI Function Calling - Industry Standard)               │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ MCPToolMapper │    │OpenAIToolMapper│   │GeminiToolMapper│
│ (Claude Code) │    │ (Native)       │   │ (Google)       │
└───────────────┘    └───────────────┘    └───────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  MCP Format   │    │ OpenAI Format │    │ Gemini Format │
│  inputSchema  │    │  parameters   │    │ UPPERCASE types│
└───────────────┘    └───────────────┘    └───────────────┘
```

## Kaizen Tool Format (Base)

All Kaizen tools use OpenAI function calling format:

```python
kaizen_tool = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Search through indexed documents",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
}
```

## Tool Mappers

### MCPToolMapper (for Claude Code)

Converts to MCP (Model Context Protocol) format:

```python
from kaizen.runtime.adapters.tool_mapping import MCPToolMapper

# Convert to MCP format
mcp_tools = MCPToolMapper.to_mcp_format([kaizen_tool])

# Result:
# {
#     "name": "search_documents",
#     "description": "Search through indexed documents",
#     "inputSchema": {
#         "type": "object",
#         "properties": {...},
#         "required": ["query"]
#     }
# }

# Convert back to Kaizen format
kaizen_tools = MCPToolMapper.from_mcp_format(mcp_tools)
```

**Reserved Names**: Claude Code has native tools that cannot be overridden:

```python
RESERVED_NAMES = {
    "Read", "Write", "Edit", "Bash", "Glob", "Grep", "LS",
    "Task", "WebFetch", "WebSearch", "TodoWrite", "NotebookEdit"
}

# Check if name is reserved
if MCPToolMapper.is_reserved_name("Read"):
    print("Cannot use 'Read' - it's a Claude Code native tool")
```

**Strict Mode** (raises on reserved names):

```python
# Default: skip reserved names silently
mcp_tools = MCPToolMapper.to_mcp_format(tools, strict=False)

# Strict: raise exception on reserved names
try:
    mcp_tools = MCPToolMapper.to_mcp_format(tools, strict=True)
except ToolMappingError as e:
    print(f"Reserved name conflict: {e}")
```

### OpenAIToolMapper

Converts to/from OpenAI format (mostly identity since Kaizen uses OpenAI format):

```python
from kaizen.runtime.adapters.tool_mapping import OpenAIToolMapper

# Validate and normalize
openai_tools = OpenAIToolMapper.to_openai_format([kaizen_tool])

# Convert from OpenAI response
kaizen_tools = OpenAIToolMapper.from_openai_format(openai_tools)
```

### GeminiToolMapper

Converts to Google Gemini function declaration format:

```python
from kaizen.runtime.adapters.tool_mapping import GeminiToolMapper

# Convert to Gemini format
gemini_tools = GeminiToolMapper.to_gemini_format([kaizen_tool])

# Result (note UPPERCASE types):
# {
#     "name": "search_documents",
#     "description": "Search through indexed documents",
#     "parameters": {
#         "type": "OBJECT",
#         "properties": {
#             "query": {
#                 "type": "STRING",
#                 "description": "Search query"
#             },
#             "limit": {
#                 "type": "INTEGER",
#                 "description": "Maximum results to return"
#             }
#         },
#         "required": ["query"]
#     }
# }
```

**Type Mapping**:

| Kaizen/OpenAI | Gemini |
|---------------|--------|
| string | STRING |
| number | NUMBER |
| integer | INTEGER |
| boolean | BOOLEAN |
| array | ARRAY |
| object | OBJECT |

## Base Classes

### ToolMapper ABC

All mappers inherit from the abstract base:

```python
from abc import ABC, abstractmethod

class ToolMapper(ABC):
    """Abstract base for tool format mappers."""

    @classmethod
    @abstractmethod
    def to_runtime_format(cls, kaizen_tools: List[Dict]) -> List[Dict]:
        """Convert Kaizen tools to runtime format."""
        ...

    @classmethod
    @abstractmethod
    def from_runtime_format(cls, runtime_tools: List[Dict]) -> List[Dict]:
        """Convert runtime tools to Kaizen format."""
        ...

    @classmethod
    def validate_tool(cls, tool: Dict) -> bool:
        """Validate tool structure."""
        ...
```

### Helper Functions

```python
from kaizen.runtime.adapters.tool_mapping import (
    extract_tool_call,
    format_tool_result,
)

# Extract tool call from LLM response
tool_call = extract_tool_call(response)
# Returns: {"name": "search_documents", "arguments": {"query": "..."}}

# Format tool result for LLM
formatted = format_tool_result(
    tool_name="search_documents",
    result={"documents": [...], "count": 5}
)
# Returns: {"role": "tool", "name": "search_documents", "content": "..."}
```

## Creating a Custom Mapper

### Step 1: Implement the Mapper

```python
from kaizen.runtime.adapters.tool_mapping.base import ToolMapper

class MyServiceToolMapper(ToolMapper):
    """Mapper for MyService tool format."""

    @classmethod
    def to_runtime_format(cls, kaizen_tools: List[Dict]) -> List[Dict]:
        """Convert Kaizen tools to MyService format."""
        result = []
        for tool in kaizen_tools:
            if tool.get("type") != "function":
                continue

            func = tool.get("function", {})
            converted = {
                "tool_name": func.get("name"),
                "tool_description": func.get("description"),
                "parameters": cls._convert_params(func.get("parameters", {})),
            }
            result.append(converted)
        return result

    @classmethod
    def from_runtime_format(cls, runtime_tools: List[Dict]) -> List[Dict]:
        """Convert MyService tools to Kaizen format."""
        result = []
        for tool in runtime_tools:
            converted = {
                "type": "function",
                "function": {
                    "name": tool.get("tool_name"),
                    "description": tool.get("tool_description"),
                    "parameters": cls._unconvert_params(tool.get("parameters", {})),
                }
            }
            result.append(converted)
        return result

    @classmethod
    def _convert_params(cls, params: Dict) -> Dict:
        # Custom conversion logic
        return params

    @classmethod
    def _unconvert_params(cls, params: Dict) -> Dict:
        # Reverse conversion logic
        return params
```

### Step 2: Add Validation

```python
class MyServiceToolMapper(ToolMapper):

    @classmethod
    def validate_tool(cls, tool: Dict) -> bool:
        """Validate tool structure for MyService."""
        if not isinstance(tool, dict):
            return False

        if tool.get("type") != "function":
            return False

        func = tool.get("function", {})
        if not func.get("name"):
            return False

        return True
```

### Step 3: Register with Exports

```python
# tool_mapping/__init__.py
from kaizen.runtime.adapters.tool_mapping.myservice import MyServiceToolMapper

__all__ = [
    # ... existing
    "MyServiceToolMapper",
]
```

## Error Handling

```python
from kaizen.runtime.adapters.tool_mapping import ToolMappingError

try:
    mcp_tools = MCPToolMapper.to_mcp_format(tools, strict=True)
except ToolMappingError as e:
    print(f"Mapping error: {e}")
    # Handle gracefully - perhaps skip the problematic tool
```

Common errors:
- `ToolMappingError`: Reserved name conflict, invalid structure
- `ValueError`: Missing required fields
- `TypeError`: Wrong input type

## Testing Tool Mappings

```python
import pytest
from kaizen.runtime.adapters.tool_mapping import (
    MCPToolMapper,
    OpenAIToolMapper,
    GeminiToolMapper,
)

def test_round_trip_conversion():
    """Test that conversion is reversible."""
    original = {
        "type": "function",
        "function": {
            "name": "my_tool",
            "description": "Does something",
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string"}
                },
                "required": ["input"]
            }
        }
    }

    # Convert to MCP and back
    mcp = MCPToolMapper.to_mcp_format([original])
    restored = MCPToolMapper.from_mcp_format(mcp)

    assert restored[0]["function"]["name"] == original["function"]["name"]
    assert restored[0]["function"]["description"] == original["function"]["description"]


def test_gemini_type_conversion():
    """Test Gemini UPPERCASE type conversion."""
    tool = {
        "type": "function",
        "function": {
            "name": "test",
            "parameters": {
                "type": "object",
                "properties": {
                    "s": {"type": "string"},
                    "n": {"type": "number"},
                    "i": {"type": "integer"},
                    "b": {"type": "boolean"},
                }
            }
        }
    }

    gemini = GeminiToolMapper.to_gemini_format([tool])[0]
    props = gemini["parameters"]["properties"]

    assert props["s"]["type"] == "STRING"
    assert props["n"]["type"] == "NUMBER"
    assert props["i"]["type"] == "INTEGER"
    assert props["b"]["type"] == "BOOLEAN"
```

## Best Practices

1. **Use the appropriate mapper** for each runtime adapter
2. **Validate tools before conversion** to catch issues early
3. **Handle reserved names** when targeting Claude Code
4. **Test round-trip conversion** to ensure data integrity
5. **Use strict mode** during development to catch conflicts
6. **Log conversion errors** for debugging
7. **Keep custom tools simple** - complex nested schemas may not convert cleanly

## File Organization

```
src/kaizen/runtime/adapters/tool_mapping/
├── __init__.py      # Public exports
├── base.py          # ToolMapper ABC, helper functions
├── mcp.py           # MCPToolMapper (Claude Code)
├── openai.py        # OpenAIToolMapper
└── gemini.py        # GeminiToolMapper
```
