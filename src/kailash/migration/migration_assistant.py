"""Migration assistant for automated LocalRuntime configuration conversion.

This module provides comprehensive automation for migrating existing LocalRuntime
configurations to the enhanced version, including parameter conversion, optimization
recommendations, and configuration validation.
"""

import ast
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .compatibility_checker import (
    CompatibilityChecker,
    CompatibilityIssue,
    IssueSeverity,
)


@dataclass
class MigrationStep:
    """Represents a single migration step."""

    step_id: str
    description: str
    file_path: str
    original_code: str
    migrated_code: str
    automated: bool = True
    validation_required: bool = False
    rollback_available: bool = True


@dataclass
class MigrationPlan:
    """Complete migration plan with all steps."""

    steps: List[MigrationStep] = field(default_factory=list)
    estimated_duration_minutes: int = 0
    risk_level: str = "low"  # low, medium, high
    prerequisites: List[str] = field(default_factory=list)
    post_migration_tests: List[str] = field(default_factory=list)
    backup_required: bool = True


@dataclass
class MigrationResult:
    """Results of migration execution."""

    success: bool
    steps_completed: int
    steps_failed: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    backup_path: Optional[str] = None
    rollback_available: bool = True


class MigrationAssistant:
    """Automated assistant for LocalRuntime migration."""

    def __init__(self, dry_run: bool = True, create_backups: bool = True):
        """Initialize the migration assistant.

        Args:
            dry_run: If True, only plan migration without executing changes
            create_backups: If True, create backups before making changes
        """
        self.dry_run = dry_run
        self.create_backups = create_backups
        self.compatibility_checker = CompatibilityChecker()

        # Configuration mapping for automated conversion
        self.parameter_mappings = {
            "debug_mode": "debug",
            "enable_parallel": "max_concurrency",
            "thread_pool_size": "max_concurrency",
            "parallel_execution": "max_concurrency",
            "enable_security_audit": "enable_audit",
            "connection_pooling": "enable_connection_sharing",
            "persistent_resources": "persistent_mode",
            "memory_limit": "resource_limits",
            "timeout": "resource_limits",
            "retry_count": "retry_policy_config",
        }

        # Value transformations
        self.value_transformations = {
            "enable_parallel": self._transform_parallel_to_concurrency,
            "thread_pool_size": self._transform_thread_pool_size,
            "memory_limit": self._transform_memory_limit,
            "timeout": self._transform_timeout,
            "retry_count": self._transform_retry_count,
        }

        # Method migrations
        self.method_migrations = {
            "execute_sync": self._migrate_execute_sync,
            "execute_async": self._migrate_execute_async,
            "get_results": self._migrate_get_results,
            "set_context": self._migrate_set_context,
        }

        # Enterprise upgrade suggestions
        self.enterprise_upgrades = {
            "basic_monitoring": self._suggest_enterprise_monitoring,
            "simple_auth": self._suggest_enterprise_auth,
            "basic_caching": self._suggest_enterprise_caching,
            "error_handling": self._suggest_enterprise_error_handling,
        }

    def create_migration_plan(
        self,
        root_path: Union[str, Path],
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ) -> MigrationPlan:
        """Create a comprehensive migration plan.

        Args:
            root_path: Root directory to analyze
            include_patterns: File patterns to include
            exclude_patterns: File patterns to exclude

        Returns:
            Complete migration plan with all steps
        """
        root_path = Path(root_path)

        # First, analyze compatibility
        analysis_result = self.compatibility_checker.analyze_codebase(
            root_path, include_patterns, exclude_patterns
        )

        plan = MigrationPlan()

        # Group issues by file for efficient processing
        issues_by_file = {}
        for issue in analysis_result.issues:
            file_path = issue.file_path
            if file_path not in issues_by_file:
                issues_by_file[file_path] = []
            issues_by_file[file_path].append(issue)

        # Create migration steps for each file
        step_id = 1
        for file_path, issues in issues_by_file.items():
            file_steps = self._create_file_migration_steps(file_path, issues, step_id)
            plan.steps.extend(file_steps)
            step_id += len(file_steps)

        # Calculate plan metadata
        self._calculate_plan_metadata(plan, analysis_result)

        return plan

    def execute_migration(self, plan: MigrationPlan) -> MigrationResult:
        """Execute the migration plan.

        Args:
            plan: Migration plan to execute

        Returns:
            Migration execution results
        """
        result = MigrationResult(success=True, steps_completed=0, steps_failed=0)

        # Create backup if requested
        if self.create_backups and not self.dry_run:
            try:
                result.backup_path = self._create_backup(plan)
            except Exception as e:
                result.errors.append(f"Failed to create backup: {str(e)}")
                result.success = False
                return result

        # Execute migration steps
        for step in plan.steps:
            try:
                if self.dry_run:
                    # Just validate the step
                    self._validate_migration_step(step)
                    result.steps_completed += 1
                else:
                    # Execute the actual migration
                    self._execute_migration_step(step)
                    result.steps_completed += 1

            except Exception as e:
                result.steps_failed += 1
                result.errors.append(f"Step {step.step_id} failed: {str(e)}")

                # Decide whether to continue or abort
                if step.validation_required:
                    result.success = False
                    break
                else:
                    result.warnings.append(
                        f"Non-critical step {step.step_id} failed, continuing"
                    )

        # Final validation
        if result.success and not self.dry_run:
            validation_errors = self._validate_migration_result(plan)
            if validation_errors:
                result.errors.extend(validation_errors)
                result.success = False

        return result

    def _create_file_migration_steps(
        self, file_path: str, issues: List[CompatibilityIssue], start_id: int
    ) -> List[MigrationStep]:
        """Create migration steps for a single file."""
        steps = []
        current_id = start_id

        # Read the original file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                original_content = f.read()
        except Exception as e:
            # Create error step
            error_step = MigrationStep(
                step_id=f"error_{current_id}",
                description=f"Failed to read file {file_path}: {str(e)}",
                file_path=file_path,
                original_code="",
                migrated_code="",
                automated=False,
                validation_required=True,
            )
            return [error_step]

        # Group issues by type for efficient processing
        parameter_issues = [i for i in issues if "parameter" in i.description.lower()]
        method_issues = [
            i
            for i in issues
            if any(method in i.description for method in self.method_migrations.keys())
        ]
        config_issues = [i for i in issues if "configuration" in i.description.lower()]

        # Create steps for different types of issues
        if parameter_issues:
            step = self._create_parameter_migration_step(
                f"param_{current_id}", file_path, original_content, parameter_issues
            )
            steps.append(step)
            current_id += 1

        if method_issues:
            step = self._create_method_migration_step(
                f"method_{current_id}", file_path, original_content, method_issues
            )
            steps.append(step)
            current_id += 1

        if config_issues:
            step = self._create_config_migration_step(
                f"config_{current_id}", file_path, original_content, config_issues
            )
            steps.append(step)
            current_id += 1

        return steps

    def _create_parameter_migration_step(
        self,
        step_id: str,
        file_path: str,
        content: str,
        issues: List[CompatibilityIssue],
    ) -> MigrationStep:
        """Create migration step for parameter changes."""
        migrated_content = content

        for issue in issues:
            # Find the parameter name from the issue description
            for old_param, new_param in self.parameter_mappings.items():
                if old_param in issue.code_snippet:
                    # Apply parameter transformation
                    if old_param in self.value_transformations:
                        migrated_content = self.value_transformations[old_param](
                            migrated_content, issue
                        )
                    else:
                        # Simple parameter rename
                        migrated_content = migrated_content.replace(
                            f"{old_param}=", f"{new_param}="
                        )

        return MigrationStep(
            step_id=step_id,
            description=f"Migrate parameters in {file_path}",
            file_path=file_path,
            original_code=content,
            migrated_code=migrated_content,
            automated=True,
            validation_required=False,
        )

    def _create_method_migration_step(
        self,
        step_id: str,
        file_path: str,
        content: str,
        issues: List[CompatibilityIssue],
    ) -> MigrationStep:
        """Create migration step for method changes."""
        migrated_content = content

        for issue in issues:
            for old_method, migration_func in self.method_migrations.items():
                if old_method in issue.code_snippet:
                    migrated_content = migration_func(migrated_content, issue)

        return MigrationStep(
            step_id=step_id,
            description=f"Migrate methods in {file_path}",
            file_path=file_path,
            original_code=content,
            migrated_code=migrated_content,
            automated=True,
            validation_required=True,  # Method changes need validation
        )

    def _create_config_migration_step(
        self,
        step_id: str,
        file_path: str,
        content: str,
        issues: List[CompatibilityIssue],
    ) -> MigrationStep:
        """Create migration step for configuration changes."""
        migrated_content = content

        # Handle dictionary-style configuration conversion
        if "dictionary-style configuration" in " ".join(i.description for i in issues):
            migrated_content = self._convert_dict_config_to_parameters(migrated_content)

        return MigrationStep(
            step_id=step_id,
            description=f"Migrate configuration in {file_path}",
            file_path=file_path,
            original_code=content,
            migrated_code=migrated_content,
            automated=True,
            validation_required=True,
        )

    def _transform_parallel_to_concurrency(
        self, content: str, issue: CompatibilityIssue
    ) -> str:
        """Transform enable_parallel to max_concurrency."""
        import re

        # Find the enable_parallel parameter and convert to max_concurrency
        pattern = r"enable_parallel\s*=\s*(True|False)"

        def replacement(match):
            value = match.group(1)
            if value == "True":
                return "max_concurrency=10"  # Default reasonable value
            else:
                return "max_concurrency=1"  # Sequential execution

        return re.sub(pattern, replacement, content)

    def _transform_thread_pool_size(
        self, content: str, issue: CompatibilityIssue
    ) -> str:
        """Transform thread_pool_size to max_concurrency."""
        import re

        pattern = r"thread_pool_size\s*=\s*(\d+)"
        return re.sub(pattern, r"max_concurrency=\1", content)

    def _transform_memory_limit(self, content: str, issue: CompatibilityIssue) -> str:
        """Transform memory_limit to resource_limits."""
        import re

        pattern = r"memory_limit\s*=\s*(\d+)"

        def replacement(match):
            value = match.group(1)
            return f'resource_limits={{"memory_mb": {value}}}'

        return re.sub(pattern, replacement, content)

    def _transform_timeout(self, content: str, issue: CompatibilityIssue) -> str:
        """Transform timeout to resource_limits."""
        import re

        pattern = r"timeout\s*=\s*(\d+)"

        def replacement(match):
            value = match.group(1)
            return f'resource_limits={{"timeout_seconds": {value}}}'

        return re.sub(pattern, replacement, content)

    def _transform_retry_count(self, content: str, issue: CompatibilityIssue) -> str:
        """Transform retry_count to retry_policy_config."""
        import re

        pattern = r"retry_count\s*=\s*(\d+)"

        def replacement(match):
            value = match.group(1)
            return (
                f'retry_policy_config={{"max_retries": {value}, "backoff_factor": 1.0}}'
            )

        return re.sub(pattern, replacement, content)

    def _migrate_execute_sync(self, content: str, issue: CompatibilityIssue) -> str:
        """Migrate execute_sync to execute."""
        import re

        # Replace execute_sync calls with execute
        pattern = r"\.execute_sync\s*\("
        return re.sub(pattern, ".execute(", content)

    def _migrate_execute_async(self, content: str, issue: CompatibilityIssue) -> str:
        """Migrate execute_async to execute with async configuration."""
        import re

        # Replace execute_async with execute and add async configuration note
        pattern = r"\.execute_async\s*\("
        replacement = ".execute(  # Note: Set enable_async=True in constructor\n"
        return re.sub(pattern, replacement, content)

    def _migrate_get_results(self, content: str, issue: CompatibilityIssue) -> str:
        """Migrate get_results to direct result access."""
        import re

        # Replace get_results() calls with direct result access
        pattern = r"\.get_results\s*\(\s*\)"
        return re.sub(pattern, "[0]  # Results now returned directly", content)

    def _migrate_set_context(self, content: str, issue: CompatibilityIssue) -> str:
        """Migrate set_context to constructor parameter."""
        import re

        # Add comment about moving context to constructor
        pattern = r"\.set_context\s*\("
        replacement = "# MIGRATION NOTE: Move context to LocalRuntime constructor\n# .set_context("
        return re.sub(pattern, replacement, content)

    def _convert_dict_config_to_parameters(self, content: str) -> str:
        """Convert dictionary-style configuration to named parameters."""
        import re

        # This is a complex transformation that would need AST manipulation
        # For now, add a comment indicating manual conversion needed
        pattern = r"LocalRuntime\s*\(\s*\{[^}]+\}"

        def replacement(match):
            return f"# MIGRATION NOTE: Convert dictionary config to named parameters\n{match.group(0)}"

        return re.sub(pattern, replacement, content, flags=re.DOTALL)

    def _calculate_plan_metadata(self, plan: MigrationPlan, analysis_result) -> None:
        """Calculate plan metadata like duration and risk level."""
        # Estimate duration based on number of steps and complexity
        base_minutes_per_step = 2
        complex_step_bonus = 3

        total_minutes = 0
        critical_issues = 0

        for step in plan.steps:
            total_minutes += base_minutes_per_step
            if step.validation_required:
                total_minutes += complex_step_bonus
            if not step.automated:
                total_minutes += 10  # Manual steps take longer

        # Add time for testing and validation
        total_minutes += 15  # Base testing time

        plan.estimated_duration_minutes = total_minutes

        # Calculate risk level
        critical_count = analysis_result.summary.get("critical_issues", 0)
        breaking_changes = analysis_result.summary.get("breaking_changes", 0)

        if critical_count > 5 or breaking_changes > 3:
            plan.risk_level = "high"
        elif critical_count > 2 or breaking_changes > 1:
            plan.risk_level = "medium"
        else:
            plan.risk_level = "low"

        # Set prerequisites
        plan.prerequisites = [
            "Create backup of codebase",
            "Ensure all tests pass before migration",
            "Review migration plan with team",
            "Prepare rollback strategy",
        ]

        # Set post-migration tests
        plan.post_migration_tests = [
            "Run existing test suite",
            "Validate LocalRuntime instantiation",
            "Test workflow execution",
            "Check performance benchmarks",
            "Verify enterprise features if enabled",
        ]

    def _create_backup(self, plan: MigrationPlan) -> str:
        """Create backup of files that will be modified."""
        backup_dir = tempfile.mkdtemp(prefix="kailash_migration_backup_")

        files_to_backup = set(step.file_path for step in plan.steps)

        for file_path in files_to_backup:
            src_path = Path(file_path)
            if src_path.exists():
                # Create relative path structure in backup
                rel_path = src_path.relative_to(src_path.anchor)
                backup_path = Path(backup_dir) / rel_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, backup_path)

        return backup_dir

    def _validate_migration_step(self, step: MigrationStep) -> None:
        """Validate a migration step without executing it."""
        # Check if the original file exists
        if not Path(step.file_path).exists():
            raise FileNotFoundError(f"Source file not found: {step.file_path}")

        # Validate that migrated code is syntactically valid Python
        try:
            ast.parse(step.migrated_code)
        except SyntaxError as e:
            raise ValueError(f"Migrated code has syntax errors: {str(e)}")

    def _execute_migration_step(self, step: MigrationStep) -> None:
        """Execute a single migration step."""
        # Validate first
        self._validate_migration_step(step)

        # Write the migrated code
        with open(step.file_path, "w", encoding="utf-8") as f:
            f.write(step.migrated_code)

    def _validate_migration_result(self, plan: MigrationPlan) -> List[str]:
        """Validate the overall migration result."""
        errors = []

        # Check that all modified files are syntactically valid
        files_modified = set(step.file_path for step in plan.steps)

        for file_path in files_modified:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                ast.parse(content)
            except Exception as e:
                errors.append(f"File {file_path} is invalid after migration: {str(e)}")

        return errors

    def rollback_migration(self, result: MigrationResult) -> bool:
        """Rollback a migration using the backup."""
        if not result.backup_path or not result.rollback_available:
            return False

        try:
            backup_path = Path(result.backup_path)
            if not backup_path.exists():
                return False

            # Restore all files from backup
            for backup_file in backup_path.rglob("*"):
                if backup_file.is_file():
                    # Calculate original path
                    rel_path = backup_file.relative_to(backup_path)
                    original_path = Path("/") / rel_path

                    # Restore the file
                    original_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_file, original_path)

            return True

        except Exception:
            return False

    def generate_migration_report(
        self, plan: MigrationPlan, result: Optional[MigrationResult] = None
    ) -> str:
        """Generate a comprehensive migration report.

        Args:
            plan: The migration plan
            result: Optional execution result

        Returns:
            Formatted migration report
        """
        report = []
        report.append("=" * 60)
        report.append("LocalRuntime Migration Report")
        report.append("=" * 60)
        report.append("")

        # Plan summary
        report.append("MIGRATION PLAN SUMMARY")
        report.append("-" * 25)
        report.append(f"Total Steps: {len(plan.steps)}")
        report.append(f"Estimated Duration: {plan.estimated_duration_minutes} minutes")
        report.append(f"Risk Level: {plan.risk_level.upper()}")
        report.append(f"Backup Required: {'Yes' if plan.backup_required else 'No'}")
        report.append("")

        # Execution results (if available)
        if result:
            report.append("EXECUTION RESULTS")
            report.append("-" * 20)
            report.append(f"Success: {'Yes' if result.success else 'No'}")
            report.append(f"Steps Completed: {result.steps_completed}")
            report.append(f"Steps Failed: {result.steps_failed}")

            if result.backup_path:
                report.append(f"Backup Location: {result.backup_path}")

            if result.errors:
                report.append("")
                report.append("ERRORS:")
                for error in result.errors:
                    report.append(f"  • {error}")

            if result.warnings:
                report.append("")
                report.append("WARNINGS:")
                for warning in result.warnings:
                    report.append(f"  • {warning}")

            report.append("")

        # Prerequisites
        if plan.prerequisites:
            report.append("PREREQUISITES")
            report.append("-" * 15)
            for prereq in plan.prerequisites:
                report.append(f"• {prereq}")
            report.append("")

        # Detailed steps
        report.append("MIGRATION STEPS")
        report.append("-" * 18)
        for i, step in enumerate(plan.steps, 1):
            report.append(f"{i}. {step.description}")
            report.append(f"   File: {step.file_path}")
            report.append(f"   Automated: {'Yes' if step.automated else 'No'}")
            report.append(
                f"   Validation Required: {'Yes' if step.validation_required else 'No'}"
            )
            report.append("")

        # Post-migration tests
        if plan.post_migration_tests:
            report.append("POST-MIGRATION VALIDATION")
            report.append("-" * 27)
            for test in plan.post_migration_tests:
                report.append(f"• {test}")
            report.append("")

        return "\n".join(report)

    # Enterprise upgrade suggestion methods
    def _suggest_enterprise_monitoring(self, content: str) -> str:
        """Suggest enterprise monitoring upgrades."""
        suggestions = [
            "Consider enabling enterprise monitoring with: enable_monitoring=True",
            "Add performance benchmarking with PerformanceBenchmarkNode",
            "Implement real-time metrics with MetricsCollectorNode",
        ]
        return "\n".join(f"# ENTERPRISE UPGRADE: {s}" for s in suggestions)

    def _suggest_enterprise_auth(self, content: str) -> str:
        """Suggest enterprise authentication upgrades."""
        suggestions = [
            "Upgrade to enterprise authentication with UserContext",
            "Enable access control with enable_security=True",
            "Consider RBAC with role-based permissions",
        ]
        return "\n".join(f"# ENTERPRISE UPGRADE: {s}" for s in suggestions)

    def _suggest_enterprise_caching(self, content: str) -> str:
        """Suggest enterprise caching upgrades."""
        suggestions = [
            "Replace basic caching with enterprise CacheNode",
            "Consider Redis integration for distributed caching",
            "Implement cache invalidation strategies",
        ]
        return "\n".join(f"# ENTERPRISE UPGRADE: {s}" for s in suggestions)

    def _suggest_enterprise_error_handling(self, content: str) -> str:
        """Suggest enterprise error handling upgrades."""
        suggestions = [
            "Upgrade error handling with EnhancedErrorFormatter",
            "Implement circuit breaker patterns",
            "Add comprehensive audit logging with enable_audit=True",
        ]
        return "\n".join(f"# ENTERPRISE UPGRADE: {s}" for s in suggestions)
