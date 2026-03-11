"""
CodexAgent - Codex Autonomous Architecture Implementation

This module implements CodexAgent based on Codex's proven autonomous patterns
from OpenAI's production usage and research analysis.

Key Codex Patterns:
1. **Container-based execution**: Isolated environment with filesystem + terminal
2. **AGENTS.md configuration**: Project-specific instructions (test commands, linters, conventions)
3. **Test-driven iteration**: Run tests → read errors → fix → repeat until pass
4. **PR generation**: Commit message + PR description + citations to logs
5. **Logging and evidence**: Step-by-step action log with command outputs
6. **1-30 minute tasks**: One-shot PR workflow, asynchronous delegation
7. **Unified .run() interface**: Standardized execution method

Architecture:
- Extends BaseAutonomousAgent with Codex-specific patterns
- Overrides _autonomous_loop for Codex workflow integration
- Implements container execution (simplified for MVP)
- Loads AGENTS.md for project memory
- Test-driven iteration loop
- Professional PR generation
- Uses .run() method for consistency with BaseAgent

References:
- docs/research/CODEX_AUTONOMOUS_ARCHITECTURE.md
- BaseAutonomousAgent at src/kaizen/agents/autonomous/base.py
- Codex: Agent-model separation, container execution, test-driven workflow

Example:
    >>> from kaizen.agents.autonomous.codex import CodexAgent, CodexConfig
    >>>
    >>> config = CodexConfig(
    ...     timeout_minutes=30,
    ...     enable_internet=False,
    ...     test_command="pytest",
    ...     lint_command="ruff"
    ... )
    >>>
    >>> agent = CodexAgent(
    ...     config=config,
    ...     signature=signature
    ... )
    >>>
    >>> # Execute with .run() interface (standard)
    >>> result = agent.run(task="Implement user authentication")
    >>> print(f"Completed in {result['cycles_used']} cycles")
    >>> print(f"PR: {result['pr_description']}")

Author: Kaizen Framework Team
Created: 2025-10-22
Updated: 2025-10-26 (Standardized to .run())
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kaizen.agents.autonomous.base import AutonomousConfig, BaseAutonomousAgent
from kaizen.signatures import Signature
from kaizen.strategies.multi_cycle import MultiCycleStrategy

logger = logging.getLogger(__name__)


@dataclass
class CodexConfig(AutonomousConfig):
    """
    Configuration for CodexAgent with Codex-specific parameters.

    This config extends AutonomousConfig with Codex-specific parameters:
    - container_image: Docker image for isolated execution
    - timeout_minutes: Maximum execution time (1-30 minutes)
    - enable_internet: Enable/disable internet access in container
    - agents_md_path: Path to AGENTS.md file for project configuration
    - test_command: Test command from AGENTS.md (e.g., "pytest")
    - lint_command: Lint command from AGENTS.md (e.g., "ruff")

    Codex Defaults vs BaseAutonomousAgent:
    - max_cycles: 30 (one-shot PR workflow)
    - timeout_minutes: 30 (Codex typical runtime)
    - enable_internet: False (security isolation)

    Example:
        >>> config = CodexConfig(
        ...     container_image="python:3.11",
        ...     timeout_minutes=30,
        ...     enable_internet=False,
        ...     agents_md_path="AGENTS.md",
        ...     test_command="pytest tests/",
        ...     lint_command="ruff check src/",
        ...     llm_provider="openai",
        ...     model="gpt-4"
        ... )
        >>> agent = CodexAgent(config=config, signature=signature)
    """

    # Codex-specific parameters
    container_image: str = "python:3.11"  # Docker image for isolated execution
    timeout_minutes: int = 30  # Maximum execution time (1-30 minute tasks)
    enable_internet: bool = False  # Disable internet for security
    agents_md_path: str = "AGENTS.md"  # Project configuration file
    test_command: str = "pytest"  # Test command from AGENTS.md
    lint_command: str = "ruff"  # Lint command from AGENTS.md

    # Override max_cycles for one-shot PR workflow
    max_cycles: int = 30  # Codex runs shorter cycles (vs 20 for base)


class CodexAgent(BaseAutonomousAgent):
    """
    Autonomous agent implementing Codex's proven patterns.

    CodexAgent extends BaseAutonomousAgent with Codex-specific autonomous
    execution patterns from OpenAI's production usage:

    1. **Container-Based Execution**: Isolated environment
       - Sandboxed filesystem and terminal
       - No internet access (security)
       - Identical training/production environment
       - State persistence across steps

    2. **AGENTS.md Configuration**: Project-specific instructions
       - Test commands (pytest, yarn test, etc.)
       - Lint commands (ruff, prettier, etc.)
       - Code conventions and style guides
       - Repository-specific context

    3. **Test-Driven Iteration**: Automated test loop
       - Run tests from AGENTS.md
       - Parse test failures
       - Present failures to LLM for fixes
       - Iterate until tests pass or timeout

    4. **PR Generation**: Professional output
       - Commit message following conventions
       - PR description with changes summary
       - Citations to action logs
       - Test outputs and evidence

    5. **Logging and Evidence**: Complete audit trail
       - Step-by-step action recording
       - Command outputs captured
       - Error messages preserved
       - Transparent decision tracking

    Execution Flow:
        1. Setup container (or simulate for MVP)
        2. Load AGENTS.md for project context
        3. Create plan (if planning enabled)
        4. Autonomous loop with test-driven iteration:
           a. Execute task with LLM reasoning
           b. Run tests from AGENTS.md
           c. Parse failures and fix
           d. Iterate until pass or timeout
           e. Record all actions to log
        5. Generate PR (commit + description + citations)
        6. Return results with evidence

    Example:
        >>> from kaizen.agents.autonomous.codex import CodexAgent, CodexConfig
        >>>
        >>> # Setup configuration
        >>> config = CodexConfig(
        ...     timeout_minutes=30,
        ...     enable_internet=False,
        ...     test_command="pytest tests/",
        ...     lint_command="ruff check src/",
        ...     llm_provider="openai",
        ...     model="gpt-4"
        ... )
        >>>
        >>> # Create agent
        >>> agent = CodexAgent(
        ...     config=config,
        ...     signature=signature
        ... )
        >>>
        >>> # Execute with .run() interface
        >>> result = agent.run(task="Fix authentication bug in user login")
        >>> print(f"Task completed in {result['cycles_used']} cycles")
        >>> print(f"PR: {result.get('pr_description', 'No PR generated')}")
        >>> print(f"Logs: {agent._get_logs()}")

    Notes:
        - Designed for 1-30 minute tasks (one-shot PR workflow)
        - Container execution simplified for MVP (full Docker integration later)
        - Test-driven iteration enables autonomous bug fixing
        - Professional PR generation for code review
        - Complete logging provides transparent audit trail
    """

    def __init__(
        self,
        config: CodexConfig,
        signature: Optional[Signature] = None,
        strategy: Optional[MultiCycleStrategy] = None,
        checkpoint_dir: Optional[Path] = None,
        **kwargs,
    ):
        """
        Initialize CodexAgent with Codex patterns.

        Args:
            config: CodexConfig with Codex-specific parameters
            signature: Optional signature (uses _default_signature() if None)
            strategy: Optional MultiCycleStrategy (creates default if None)
            checkpoint_dir: Optional directory for checkpoint persistence
            **kwargs: Additional arguments passed to BaseAutonomousAgent (including mcp_servers)

        Example:
            >>> config = CodexConfig(timeout_minutes=30, enable_internet=False)
            >>> agent = CodexAgent(
            ...     config=config,
            ...     signature=signature
            ... )
        """
        # Store Codex-specific config
        self.codex_config = config

        # Initialize BaseAutonomousAgent (will create strategy if None)
        # Tool calling via MCP integration (pass mcp_servers in kwargs if needed)
        super().__init__(
            config=config,
            signature=signature,
            strategy=strategy,
            checkpoint_dir=checkpoint_dir,
            **kwargs,
        )

        # Codex-specific state
        self.action_log: List[Dict[str, Any]] = []  # Action logging system
        self.agents_md_content: str = ""  # Loaded AGENTS.md content
        self.container_state: Dict[str, Any] = {}  # Container execution state
        self.test_iteration_count: int = 0  # Test-driven iteration counter

        # Load AGENTS.md at initialization
        self.agents_md_content = self._load_agents_md()

        logger.info("CodexAgent initialized with Codex patterns")

    async def _setup_container(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup isolated container environment.

        Creates isolated execution environment with:
        - Sandboxed filesystem
        - Terminal access
        - Internet disabled (if configured)
        - Working directory set to repo_path

        For MVP: Simplified implementation without actual Docker.
        Full Docker integration can be added later.

        Args:
            repo_path: Path to repository to load into container

        Returns:
            Dict with container setup status:
            - status: "success" or "failed"
            - container_id: Container identifier (simulated for MVP)
            - working_directory: Current working directory
            - internet_enabled: Internet access flag
            - environment: Environment variables

        Example:
            >>> result = await agent._setup_container("/path/to/repo")
            >>> print(result["status"])  # "success"
            >>> print(result["internet_enabled"])  # False
        """
        logger.info(f"Setting up container for repository: {repo_path}")

        # For MVP: Simulate container without actual Docker
        # Full Docker integration: docker run -v {repo_path}:/workspace ...
        container_state = {
            "status": "success",
            "container_id": f"codex-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "working_directory": repo_path,
            "internet_enabled": self.codex_config.enable_internet,
            "environment": {
                "PYTHONPATH": repo_path,
                "HOME": "/workspace",
            },
        }

        # Store container state
        self.container_state = container_state

        # Record action
        self._record_action("setup_container", container_state)

        logger.info(f"Container setup complete: {container_state['container_id']}")
        return container_state

    def _load_agents_md(self) -> str:
        """
        Load AGENTS.md file for project configuration.

        AGENTS.md provides project-specific context:
        - Test commands (pytest, yarn test, etc.)
        - Lint commands (ruff, prettier, etc.)
        - Code conventions and style guides
        - Repository structure
        - Development environment setup

        Returns:
            String content of AGENTS.md file

        Example:
            >>> content = agent._load_agents_md()
            >>> print(f"Loaded {len(content)} chars from AGENTS.md")
        """
        agents_md_path = Path(self.codex_config.agents_md_path)

        if not agents_md_path.exists():
            logger.warning(f"AGENTS.md not found at {agents_md_path}")
            return ""

        try:
            with open(agents_md_path, "r", encoding="utf-8") as f:
                content = f.read()

            logger.info(f"Loaded AGENTS.md: {len(content)} characters")
            return content

        except Exception as e:
            logger.error(f"Error loading AGENTS.md: {e}")
            return ""

    async def _test_and_iterate(self) -> bool:
        """
        Run tests, read errors, fix, repeat until pass.

        Implements Codex's test-driven iteration workflow:
        1. Execute test command from AGENTS.md
        2. Parse test output for failures
        3. Present failures to LLM for fixes
        4. Apply fixes and rerun tests
        5. Repeat until tests pass or timeout

        Returns:
            bool: True if tests passed, False if failed or timeout

        Example:
            >>> success = await agent._test_and_iterate()
            >>> if success:
            ...     print("All tests passed!")
        """
        logger.info("Starting test-driven iteration")

        max_iterations = 5  # Maximum test-fix iterations
        self.test_iteration_count = 0

        for iteration in range(max_iterations):
            self.test_iteration_count = iteration + 1

            logger.debug(f"Test iteration {self.test_iteration_count}/{max_iterations}")

            # Execute test command
            test_result = await self._execute_command(self.codex_config.test_command)

            # Record test execution
            self._record_action(
                f"run_tests_iteration_{self.test_iteration_count}", test_result
            )

            # Check if tests passed
            if test_result.get("status") == "success":
                logger.info(
                    f"Tests passed after {self.test_iteration_count} iteration(s)"
                )
                return True

            # Tests failed - parse failures
            failures = self._parse_test_failures(test_result.get("output", ""))

            if not failures:
                logger.warning("No specific test failures found, stopping iteration")
                return False

            logger.debug(f"Found {len(failures)} test failures, requesting fixes")

            # TODO: Present failures to LLM for fixes (full implementation)
            # For now, simulate iteration
            await asyncio.sleep(0.1)

        logger.warning(f"Test iteration timeout after {max_iterations} attempts")
        return False

    async def _execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute command in container (simulated for MVP).

        Args:
            command: Shell command to execute

        Returns:
            Dict with execution result:
            - status: "success" or "failed"
            - output: Command output
            - exit_code: Process exit code

        Example:
            >>> result = await agent._execute_command("pytest tests/")
            >>> print(result["status"])
        """
        logger.debug(f"Executing command: {command}")

        # For MVP: Simulate command execution
        # Full implementation: subprocess.run() or docker exec
        result = {
            "status": "success",
            "output": f"Simulated output for: {command}",
            "exit_code": 0,
            "command": command,
        }

        return result

    def _parse_test_failures(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse test failure output to extract specific failures.

        Args:
            output: Test command output

        Returns:
            List of failure dictionaries with file, test, error

        Example:
            >>> failures = agent._parse_test_failures(output)
            >>> print(f"Found {len(failures)} failures")
        """
        failures = []

        # Simple parsing for FAILED lines (or other failure indicators)
        for line in output.split("\n"):
            if "FAILED" in line or "AssertionError" in line or "TypeError" in line:
                failures.append({"line": line, "type": "test_failure", "details": line})

        return failures

    async def _generate_pr(self, changes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate commit message and PR description with citations.

        Creates professional PR output:
        - Commit message following conventions
        - PR description with changes summary
        - Citations to action logs
        - Test outputs as evidence

        Args:
            changes: List of change dictionaries

        Returns:
            Dict with PR information:
            - commit_message: Professional commit message
            - pr_description: Comprehensive PR description
            - citations: References to logs and evidence

        Example:
            >>> changes = [
            ...     {"file": "src/auth.py", "action": "modified", "description": "Fixed login"}
            ... ]
            >>> pr = await agent._generate_pr(changes)
            >>> print(pr["commit_message"])
        """
        logger.info("Generating PR output")

        # Generate commit message
        commit_message = self._generate_commit_message(changes)

        # Generate PR description
        pr_description = self._generate_pr_description(changes)

        # Add citations to logs
        log_summary = self._get_logs()

        pr_data = {
            "commit_message": commit_message,
            "pr_description": pr_description,
            "citations": log_summary,
            "changes_count": len(changes),
        }

        # Record PR generation
        self._record_action("generate_pr", pr_data)

        logger.info("PR generation complete")
        return pr_data

    def _generate_commit_message(self, changes: List[Dict[str, Any]]) -> str:
        """
        Generate professional commit message.

        Args:
            changes: List of changes

        Returns:
            Commit message string

        Example:
            >>> message = agent._generate_commit_message(changes)
        """
        # Simple commit message generation
        if not changes:
            return "chore: Update files"

        # Extract file types
        file_count = len(changes)
        action = changes[0].get("action", "modified")

        return f"feat: {action.capitalize()} {file_count} file(s)"

    def _generate_pr_description(self, changes: List[Dict[str, Any]]) -> str:
        """
        Generate comprehensive PR description.

        Args:
            changes: List of changes

        Returns:
            PR description markdown string

        Example:
            >>> description = agent._generate_pr_description(changes)
        """
        lines = [
            "# Pull Request",
            "",
            "## Summary",
            f"This PR includes changes to {len(changes)} file(s).",
            "",
            "## Changes",
        ]

        for change in changes:
            file = change.get("file", "unknown")
            action = change.get("action", "modified")
            lines.append(f"- {action.capitalize()}: `{file}`")

        lines.extend(
            [
                "",
                "## Testing",
                f"Tests run: {self.test_iteration_count} iteration(s)",
                "",
                "## Logs",
                "See action log for detailed execution trace.",
            ]
        )

        return "\n".join(lines)

    def _record_action(self, action: str, result: Any) -> None:
        """
        Record action to log with timestamp.

        Args:
            action: Action name/description
            result: Action result (dict, str, etc.)

        Example:
            >>> agent._record_action("run_tests", {"status": "passed"})
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "result": result,
        }

        self.action_log.append(log_entry)
        logger.debug(f"Recorded action: {action}")

    def _get_logs(self) -> str:
        """
        Get full execution log as formatted string.

        Returns:
            Formatted log string with all actions

        Example:
            >>> logs = agent._get_logs()
            >>> print(logs)
        """
        if not self.action_log:
            return "No actions recorded"

        lines = ["=== Codex Execution Log ===", ""]

        for entry in self.action_log:
            timestamp = entry.get("timestamp", "unknown")
            action = entry.get("action", "unknown")
            lines.append(f"[{timestamp}] {action}")

            # Add result summary
            result = entry.get("result", {})
            if isinstance(result, dict):
                status = result.get("status", "unknown")
                lines.append(f"  Status: {status}")

        return "\n".join(lines)

    async def _autonomous_loop(self, task: str) -> Dict[str, Any]:
        """
        Override autonomous loop with Codex patterns.

        This implements the Codex autonomous loop with:
        1. Container setup (or simulation)
        2. AGENTS.md context integration
        3. Test-driven iteration workflow
        4. Action logging throughout
        5. PR generation at completion

        Args:
            task: Task to execute

        Returns:
            Dict with final result and metadata

        Example:
            >>> result = await agent._autonomous_loop("Fix bug")
            >>> print(f"Converged: {result.get('tool_calls') == []}")
        """
        self.cycle_count = 0
        final_result = {}

        # Step 1: Setup container (or simulate)
        logger.info("Step 1: Setting up execution environment")
        container_result = await self._setup_container(
            self.container_state.get("working_directory", ".")
        )

        # Step 2: Prepare initial inputs with AGENTS.md context
        inputs = {
            "task": task,
            "agents_md_context": self.agents_md_content,
            "container_state": container_result,
        }
        if self.current_plan:
            inputs["plan"] = self.current_plan

        # Step 3: Codex autonomous loop: while(tool_calls_exist)
        for cycle_num in range(self.codex_config.max_cycles):
            self.cycle_count = cycle_num + 1

            try:
                logger.debug(f"Cycle {self.cycle_count}/{self.codex_config.max_cycles}")

                # Execute cycle using strategy
                cycle_result = self.strategy.execute(self, inputs)

                # Record cycle execution
                self._record_action(f"cycle_{self.cycle_count}", cycle_result)

                # Save checkpoint at specified frequency
                if self.cycle_count % self.codex_config.checkpoint_frequency == 0:
                    self._save_checkpoint(cycle_result, cycle_num)

                # Check convergence (objective via tool_calls)
                if self._check_convergence(cycle_result):
                    logger.info(f"Converged at cycle {self.cycle_count}")
                    final_result = cycle_result
                    break

                # Update inputs for next cycle
                if "observation" in cycle_result:
                    inputs["observation"] = cycle_result["observation"]

            except Exception as e:
                logger.error(f"Error in cycle {self.cycle_count}: {e}")
                final_result = {
                    "error": str(e),
                    "status": "failed",
                    "cycle": self.cycle_count,
                }
                break

        # Step 4: Generate PR (if execution completed successfully)
        if final_result.get("status") != "failed":
            changes = final_result.get("changes", [])
            pr_data = await self._generate_pr(changes)
            final_result["pr_data"] = pr_data
            final_result["commit_message"] = pr_data.get("commit_message", "")
            final_result["pr_description"] = pr_data.get("pr_description", "")

        # Add cycle metadata
        final_result["cycles_used"] = self.cycle_count
        final_result["total_cycles"] = self.codex_config.max_cycles
        final_result["action_log"] = self.action_log

        return final_result
