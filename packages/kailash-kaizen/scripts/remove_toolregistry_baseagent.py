"""
Script to remove all ToolRegistry/ToolExecutor references from base_agent.py.

This removes:
1. Tool prompt generation code (lines 1112-1153)
2. has_tool_support() method
3. discover_tools() ToolRegistry logic
4. execute_tool() method
5. execute_tool_chain() method
6. Tool cleanup code

After running, only MCP tool methods remain.
"""

import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
BASE_AGENT_FILE = BASE_DIR / "src" / "kaizen" / "core" / "base_agent.py"


def remove_toolregistry_code():
    """Remove all ToolRegistry code from base_agent.py."""
    with open(BASE_AGENT_FILE, "r") as f:
        content = f.read()

    # 1. Remove tool prompt generation section (TODO-162)
    pattern1 = r"        # TODO-162 Phase 2:.*?^\s+return base_prompt"
    content = re.sub(
        pattern1,
        "        # Note: Tool documentation now handled by MCP auto-discovery\n        return base_prompt",
        content,
        flags=re.DOTALL | re.MULTILINE,
    )

    # 2. Remove has_tool_support() method
    pattern2 = r"    def has_tool_support\(self\) -> bool:.*?return self\._tool_registry is not None\n"
    content = re.sub(pattern2, "", content, flags=re.DOTALL)

    # 3. Remove tool_registry logic from discover_tools()
    pattern3 = r"        # Discover builtin tools if registry configured.*?all_tools\.extend\(renamed_tools\)\n"
    content = re.sub(pattern3, "", content, flags=re.DOTALL)

    # 4. Remove tool source error check
    pattern4 = r"        # Raise error if no tool sources configured.*?to enable tool discovery\.\"\n            \)\n"
    content = re.sub(pattern4, "", content, flags=re.DOTALL)

    # 5. Remove execute_tool() method entirely
    pattern5 = r"    async def execute_tool\(.*?return result\n"
    content = re.sub(pattern5, "", content, flags=re.DOTALL)

    # 6. Remove execute_tool_chain() method entirely
    pattern6 = r"    async def execute_tool_chain\(.*?return results\n"
    content = re.sub(pattern6, "", content, flags=re.DOTALL)

    # 7. Remove tool executor cleanup
    pattern7 = (
        r"        # Clear tool executor references.*?self\._tool_executor = None\n"
    )
    content = re.sub(pattern7, "", content, flags=re.DOTALL)

    # 8. Remove tool registry cleanup
    pattern8 = (
        r'        if hasattr\(self, "_tool_registry"\).*?self\._tool_registry = None\n'
    )
    content = re.sub(pattern8, "", content, flags=re.DOTALL)

    # Write back
    with open(BASE_AGENT_FILE, "w") as f:
        f.write(content)

    print(f"✅ Removed ToolRegistry code from {BASE_AGENT_FILE.name}")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("REMOVING TOOLREGISTRY FROM BASE_AGENT.PY")
    print("=" * 60)
    remove_toolregistry_code()
    print("\n✅ Complete! Run tests to verify no breakage.")
