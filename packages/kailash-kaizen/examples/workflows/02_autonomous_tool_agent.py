"""
Autonomous Tool-Calling Agent

This example shows:
- How to enable MCP tool calling (auto-connects to kaizen_builtin)
- How to discover available tools
- How to execute single tools
- How to chain multiple tools for complex workflows
- How approval workflows work for dangerous operations

Prerequisites:
- OPENAI_API_KEY in .env file
- pip install kailash-kaizen python-dotenv
"""

import asyncio
import os
import tempfile
from dataclasses import dataclass

from dotenv import load_dotenv

# Step 1: Load environment
load_dotenv()

# Step 2: Import Kaizen components
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


# Step 3: Define signature for file analysis
class FileAnalysisSignature(Signature):
    """Signature for analyzing files."""

    task: str = InputField(description="Task description")
    result: str = OutputField(description="Task result")


# Step 4: Configuration
@dataclass
class FileAgentConfig:
    """Configuration for file analysis agent."""

    llm_provider: str = "openai"
    model: str = "gpt-4"  # Use GPT-4 for better reasoning with tools
    temperature: float = 0.3  # Lower temp for more deterministic tool usage
    max_tokens: int = 1000


# Step 5: Create tool-enabled agent
class FileAnalysisAgent(BaseAgent):
    """
    Agent that can autonomously work with files.

    This agent has access to 12 builtin tools:
    - File operations: read_file, write_file, delete_file, list_directory, file_exists
    - HTTP requests: http_get, http_post, http_put, http_delete
    - System: bash_command
    - Web: fetch_url, extract_links
    """

    def __init__(self, config: FileAgentConfig):
        """
        Initialize agent with tool support.

        Args:
            config: Agent configuration
        """
        super().__init__(
            config=config,
            signature=FileAnalysisSignature(),
        )

    async def analyze_directory(self, directory_path: str) -> dict:
        """
        Analyze a directory and its contents.

        This demonstrates autonomous tool usage:
        1. List directory contents (SAFE - auto-approved)
        2. Read file contents (LOW - auto-approved)
        3. Analyze and report

        Args:
            directory_path: Path to directory

        Returns:
            dict with analysis results
        """
        print(f"\n📁 Analyzing directory: {directory_path}")

        # Step 1: Discover available file tools
        print("\n🔍 Discovering available file tools...")
        file_tools = await self.discover_tools(category="file")
        print(f"✓ Found {len(file_tools)} file tools:")
        for tool in file_tools:
            print(f"  - {tool['name']} ({tool['danger_level']})")

        # Step 2: List directory (SAFE - no approval needed)
        print("\n📋 Listing directory contents...")
        list_result = await self.execute_tool(
            "list_directory", {"path": directory_path}
        )

        if not list_result.success:
            print(f"❌ Failed to list directory: {list_result.error}")
            return {"error": list_result.error}

        files = list_result.result.get("files", [])
        print(f"✓ Found {len(files)} items")

        # Step 3: Read text files (LOW - auto-approved)
        print("\n📖 Reading text files...")
        file_contents = {}

        for file_info in files:
            file_path = file_info.get("path")
            file_name = file_info.get("name")
            is_file = file_info.get("is_file", False)

            # Only read .txt files for this example
            if is_file and file_name.endswith(".txt"):
                print(f"  Reading: {file_name}")

                read_result = await self.execute_tool("read_file", {"path": file_path})

                if read_result.success:
                    content = read_result.result.get("content", "")
                    file_contents[file_name] = content
                    print(f"    ✓ Read {len(content)} characters")
                else:
                    print(f"    ❌ Failed: {read_result.error}")

        return {
            "directory": directory_path,
            "total_items": len(files),
            "files_read": len(file_contents),
            "contents": file_contents,
        }

    async def create_and_analyze_workflow(self, temp_dir: str) -> dict:
        """
        Demonstrate multi-tool chaining.

        This workflow:
        1. Creates a test file (MEDIUM - requires approval in production)
        2. Reads the file (LOW - auto-approved)
        3. Analyzes content
        4. Reports results

        Args:
            temp_dir: Temporary directory for test files

        Returns:
            dict with workflow results
        """
        print("\n🔧 Running multi-tool workflow...")

        # For this example, we'll chain tools manually to show the flow
        # In production, agents can autonomously select and chain tools

        # Step 1: Create test file
        test_file_path = os.path.join(temp_dir, "test_analysis.txt")
        test_content = """This is a test file for Kaizen tool calling.

Features demonstrated:
- Autonomous tool discovery
- Safe file operations
- Tool chaining
- Approval workflows
"""

        print(f"\n1️⃣  Creating test file: {test_file_path}")
        write_result = await self.execute_tool(
            "write_file", {"path": test_file_path, "content": test_content}
        )

        if not write_result.success:
            print(f"❌ Failed to create file: {write_result.error}")
            if not write_result.approved:
                print("   (Operation was not approved)")
            return {"error": write_result.error}

        print("✓ File created successfully")

        # Step 2: Read file back
        print("\n2️⃣  Reading file back...")
        read_result = await self.execute_tool("read_file", {"path": test_file_path})

        if not read_result.success:
            print(f"❌ Failed to read file: {read_result.error}")
            return {"error": read_result.error}

        content = read_result.result.get("content", "")
        print(f"✓ Read {len(content)} characters")

        # Step 3: Analyze content
        print("\n3️⃣  Analyzing content...")
        word_count = len(content.split())
        line_count = len(content.split("\n"))

        analysis = {
            "file_path": test_file_path,
            "word_count": word_count,
            "line_count": line_count,
            "character_count": len(content),
            "preview": content[:100] + "..." if len(content) > 100 else content,
        }

        print("✓ Analysis complete:")
        print(f"  - Words: {word_count}")
        print(f"  - Lines: {line_count}")
        print(f"  - Characters: {len(content)}")

        return analysis


# Step 6: Usage example
async def main():
    """Main async function demonstrating tool calling."""

    print("=" * 80)
    print("KAIZEN AUTONOMOUS TOOL-CALLING AGENT - Example 2")
    print("=" * 80)

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not found")
        return

    # Create tool registry with builtin tools
    print("\n🔧 Setting up tool registry...")
    print(f"✓ Registered {registry.count()} builtin tools")

    # Create agent with tool support
    config = FileAgentConfig()
    agent = FileAnalysisAgent(config)
    print("✓ Agent initialized with tool support")

    # Create temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"\n📁 Using temporary directory: {temp_dir}")

        # Create some test files
        test_files = {
            "notes.txt": "Meeting notes from today's standup.",
            "ideas.txt": "Product ideas: AI assistant, automation tools.",
            "README.txt": "This is a test directory for Kaizen examples.",
        }

        print("\n📝 Creating test files...")
        for filename, content in test_files.items():
            file_path = os.path.join(temp_dir, filename)
            with open(file_path, "w") as f:
                f.write(content)
            print(f"  ✓ Created: {filename}")

        # Example 1: Analyze directory
        print("\n" + "=" * 80)
        print("EXAMPLE 1: Analyze Directory")
        print("=" * 80)

        analysis_result = await agent.analyze_directory(temp_dir)

        if "error" not in analysis_result:
            print("\n📊 Analysis Results:")
            print(f"  Total items: {analysis_result['total_items']}")
            print(f"  Files read: {analysis_result['files_read']}")
            print("\n  File contents:")
            for filename, content in analysis_result["contents"].items():
                print(f"    - {filename}: {len(content)} characters")

        # Example 2: Multi-tool workflow
        print("\n" + "=" * 80)
        print("EXAMPLE 2: Multi-Tool Workflow")
        print("=" * 80)

        workflow_result = await agent.create_and_analyze_workflow(temp_dir)

        if "error" not in workflow_result:
            print("\n✅ Workflow completed successfully!")

    print("\n" + "=" * 80)
    print("✓ Tool-calling examples completed!")
    print("=" * 80)


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
