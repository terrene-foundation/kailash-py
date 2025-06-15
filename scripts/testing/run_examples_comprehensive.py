#!/usr/bin/env python3
"""
Comprehensive Examples Test Runner
Runs all examples folder by folder with detailed pass/fail records and timing

Features:
- Folder-by-folder execution with detailed timing
- Pass/fail tracking with error categorization
- Performance metrics and statistics
- Detailed reporting with HTML output
- Parallel execution support
- Retry mechanisms for flaky tests
- Integration with CI/CD systems
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class TestResult:
    """Data class for individual test results."""

    file_path: str
    folder: str
    status: str  # "pass", "fail", "skip", "timeout"
    execution_time: float
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    retry_count: int = 0


@dataclass
class FolderSummary:
    """Data class for folder-level summaries."""

    folder_name: str
    total_files: int
    passed: int
    failed: int
    skipped: int
    timeout: int
    total_time: float
    avg_time: float
    files: List[TestResult]


@dataclass
class OverallSummary:
    """Data class for overall test summary."""

    total_folders: int
    total_files: int
    total_passed: int
    total_failed: int
    total_skipped: int
    total_timeout: int
    total_execution_time: float
    start_time: str
    end_time: str
    folders: List[FolderSummary]


class ExamplesTestRunner:
    """Comprehensive test runner for examples directory."""

    def __init__(
        self,
        examples_root: Path,
        max_workers: int = 4,
        timeout: int = 120,
        retry_count: int = 2,
        parallel: bool = True,
        verbose: bool = True,
    ):
        self.examples_root = examples_root
        self.max_workers = max_workers
        self.timeout = timeout
        self.retry_count = retry_count
        self.parallel = parallel
        self.verbose = verbose

        # Results storage
        self.folder_results: Dict[str, FolderSummary] = {}
        self.start_time = datetime.now()

        # Setup logging
        self.setup_logging()

        # File patterns to test
        self.test_patterns = ["*_test.py", "*_example.py", "*_demo.py"]
        self.exclude_patterns = ["__pycache__", "*.pyc", ".git", "node_modules"]

    def setup_logging(self):
        """Setup logging configuration."""
        log_level = logging.DEBUG if self.verbose else logging.INFO
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler("examples_test_run.log"),
            ],
        )
        self.logger = logging.getLogger(__name__)

    def find_example_files(self) -> Dict[str, List[Path]]:
        """Find all example files organized by folder."""
        folder_files = {}

        for root, dirs, files in os.walk(self.examples_root):
            # Skip excluded directories
            dirs[:] = [
                d
                for d in dirs
                if not any(
                    d.startswith(pattern.rstrip("*"))
                    for pattern in self.exclude_patterns
                )
            ]

            folder_path = Path(root)
            relative_folder = folder_path.relative_to(self.examples_root)

            # Find Python files that match our patterns
            example_files = []
            for file in files:
                file_path = folder_path / file
                if any(file_path.match(pattern) for pattern in self.test_patterns):
                    example_files.append(file_path)

            if example_files:
                folder_files[str(relative_folder)] = example_files

        return folder_files

    def run_single_file(self, file_path: Path, folder: str) -> TestResult:
        """Run a single example file and return results."""
        start_time = time.time()

        self.logger.debug(f"Running: {file_path}")

        try:
            # Run the Python file
            result = subprocess.run(
                [sys.executable, str(file_path)],
                cwd=self.examples_root,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return TestResult(
                    file_path=str(file_path.relative_to(self.examples_root)),
                    folder=folder,
                    status="pass",
                    execution_time=execution_time,
                    stdout=(
                        result.stdout[:1000] if result.stdout else None
                    ),  # Truncate for storage
                    stderr=result.stderr[:1000] if result.stderr else None,
                )
            else:
                return TestResult(
                    file_path=str(file_path.relative_to(self.examples_root)),
                    folder=folder,
                    status="fail",
                    execution_time=execution_time,
                    error_message=result.stderr or "Non-zero exit code",
                    error_type="execution_error",
                    stdout=result.stdout[:1000] if result.stdout else None,
                    stderr=result.stderr[:1000] if result.stderr else None,
                )

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            return TestResult(
                file_path=str(file_path.relative_to(self.examples_root)),
                folder=folder,
                status="timeout",
                execution_time=execution_time,
                error_message=f"Timeout after {self.timeout}s",
                error_type="timeout",
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return TestResult(
                file_path=str(file_path.relative_to(self.examples_root)),
                folder=folder,
                status="fail",
                execution_time=execution_time,
                error_message=str(e),
                error_type=type(e).__name__,
            )

    def run_with_retry(self, file_path: Path, folder: str) -> TestResult:
        """Run a file with retry logic."""
        last_result = None

        for attempt in range(self.retry_count + 1):
            result = self.run_single_file(file_path, folder)
            result.retry_count = attempt

            if result.status == "pass":
                return result

            last_result = result

            if attempt < self.retry_count:
                self.logger.warning(
                    f"Retry {attempt + 1}/{self.retry_count} for {file_path}: {result.error_message}"
                )
                time.sleep(1)  # Brief delay between retries

        return last_result

    def run_folder_parallel(self, folder: str, files: List[Path]) -> FolderSummary:
        """Run all files in a folder in parallel."""
        start_time = time.time()

        self.logger.info(f"📁 Testing folder: {folder} ({len(files)} files)")

        if self.parallel and len(files) > 1:
            with ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(files))
            ) as executor:
                futures = [
                    executor.submit(self.run_with_retry, file_path, folder)
                    for file_path in files
                ]
                results = [future.result() for future in futures]
        else:
            results = [self.run_with_retry(file_path, folder) for file_path in files]

        total_time = time.time() - start_time

        # Calculate statistics
        passed = sum(1 for r in results if r.status == "pass")
        failed = sum(1 for r in results if r.status == "fail")
        skipped = sum(1 for r in results if r.status == "skip")
        timeout = sum(1 for r in results if r.status == "timeout")

        avg_time = (
            sum(r.execution_time for r in results) / len(results) if results else 0
        )

        summary = FolderSummary(
            folder_name=folder,
            total_files=len(files),
            passed=passed,
            failed=failed,
            skipped=skipped,
            timeout=timeout,
            total_time=total_time,
            avg_time=avg_time,
            files=results,
        )

        # Log folder results
        self.logger.info(
            f"  ✅ {passed} passed, ❌ {failed} failed, ⏸️ {skipped} skipped, ⏰ {timeout} timeout"
        )
        self.logger.info(f"  ⏱️ Total: {total_time:.1f}s, Avg: {avg_time:.1f}s")

        return summary

    def run_all_folders(self) -> OverallSummary:
        """Run tests on all folders."""
        self.logger.info("🚀 Starting comprehensive examples testing")
        self.logger.info(
            f"📊 Configuration: max_workers={self.max_workers}, timeout={self.timeout}s, parallel={self.parallel}"
        )

        folder_files = self.find_example_files()

        if not folder_files:
            self.logger.warning("No example files found!")
            return OverallSummary(
                total_folders=0,
                total_files=0,
                total_passed=0,
                total_failed=0,
                total_skipped=0,
                total_timeout=0,
                total_execution_time=0,
                start_time=self.start_time.isoformat(),
                end_time=datetime.now().isoformat(),
                folders=[],
            )

        self.logger.info(f"📁 Found {len(folder_files)} folders with example files")

        # Sort folders for consistent execution order
        sorted_folders = sorted(folder_files.items())
        folder_summaries = []

        total_start_time = time.time()

        for folder, files in sorted_folders:
            try:
                summary = self.run_folder_parallel(folder, files)
                folder_summaries.append(summary)
                self.folder_results[folder] = summary

            except Exception as e:
                self.logger.error(f"❌ Failed to test folder {folder}: {e}")
                traceback.print_exc()

                # Create error summary
                error_summary = FolderSummary(
                    folder_name=folder,
                    total_files=len(files),
                    passed=0,
                    failed=len(files),
                    skipped=0,
                    timeout=0,
                    total_time=0,
                    avg_time=0,
                    files=[
                        TestResult(
                            file_path=str(f.relative_to(self.examples_root)),
                            folder=folder,
                            status="fail",
                            execution_time=0,
                            error_message=str(e),
                            error_type=type(e).__name__,
                        )
                        for f in files
                    ],
                )
                folder_summaries.append(error_summary)

        total_execution_time = time.time() - total_start_time
        end_time = datetime.now()

        # Calculate overall statistics
        total_files = sum(s.total_files for s in folder_summaries)
        total_passed = sum(s.passed for s in folder_summaries)
        total_failed = sum(s.failed for s in folder_summaries)
        total_skipped = sum(s.skipped for s in folder_summaries)
        total_timeout = sum(s.timeout for s in folder_summaries)

        return OverallSummary(
            total_folders=len(folder_summaries),
            total_files=total_files,
            total_passed=total_passed,
            total_failed=total_failed,
            total_skipped=total_skipped,
            total_timeout=total_timeout,
            total_execution_time=total_execution_time,
            start_time=self.start_time.isoformat(),
            end_time=end_time.isoformat(),
            folders=folder_summaries,
        )

    def generate_reports(self, summary: OverallSummary, output_dir: Path):
        """Generate comprehensive reports."""
        output_dir.mkdir(exist_ok=True)

        # JSON Report
        json_report_path = output_dir / "examples_test_results.json"
        with open(json_report_path, "w") as f:
            json.dump(asdict(summary), f, indent=2, default=str)

        # HTML Report
        html_report_path = output_dir / "examples_test_results.html"
        self.generate_html_report(summary, html_report_path)

        # CSV Report
        csv_report_path = output_dir / "examples_test_results.csv"
        self.generate_csv_report(summary, csv_report_path)

        self.logger.info("📊 Reports generated:")
        self.logger.info(f"  • JSON: {json_report_path}")
        self.logger.info(f"  • HTML: {html_report_path}")
        self.logger.info(f"  • CSV: {csv_report_path}")

    def generate_html_report(self, summary: OverallSummary, output_path: Path):
        """Generate HTML report."""
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kailash Examples Test Results</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #333; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .pass {{ color: #28a745; }}
        .fail {{ color: #dc3545; }}
        .skip {{ color: #ffc107; }}
        .timeout {{ color: #fd7e14; }}
        .folder {{ margin-bottom: 30px; border: 1px solid #e0e0e0; border-radius: 8px; }}
        .folder-header {{ background: #f8f9fa; padding: 15px; border-bottom: 1px solid #e0e0e0; }}
        .folder-title {{ font-size: 1.2em; font-weight: bold; }}
        .folder-stats {{ font-size: 0.9em; color: #666; margin-top: 5px; }}
        .files {{ padding: 15px; }}
        .file {{ display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #f0f0f0; }}
        .file:last-child {{ border-bottom: none; }}
        .file-name {{ font-family: monospace; }}
        .file-status {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8em; color: white; }}
        .status-pass {{ background: #28a745; }}
        .status-fail {{ background: #dc3545; }}
        .status-skip {{ background: #ffc107; }}
        .status-timeout {{ background: #fd7e14; }}
        .file-time {{ color: #666; font-size: 0.9em; }}
        .error-details {{ margin-top: 10px; padding: 10px; background: #f8f8f8; border-radius: 4px; font-family: monospace; font-size: 0.8em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Kailash Examples Test Results</h1>
            <p>Generated on {summary.end_time}</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-number">{summary.total_folders}</div>
                <div class="stat-label">Folders Tested</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{summary.total_files}</div>
                <div class="stat-label">Total Files</div>
            </div>
            <div class="stat-card">
                <div class="stat-number pass">{summary.total_passed}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number fail">{summary.total_failed}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-number skip">{summary.total_skipped}</div>
                <div class="stat-label">Skipped</div>
            </div>
            <div class="stat-card">
                <div class="stat-number timeout">{summary.total_timeout}</div>
                <div class="stat-label">Timeout</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{summary.total_execution_time:.1f}s</div>
                <div class="stat-label">Total Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-number">{(summary.total_passed/summary.total_files*100) if summary.total_files > 0 else 0:.1f}%</div>
                <div class="stat-label">Success Rate</div>
            </div>
        </div>

        <h2>📁 Folder Results</h2>
"""

        for folder in summary.folders:
            success_rate = (
                (folder.passed / folder.total_files * 100)
                if folder.total_files > 0
                else 0
            )

            html_content += f"""
        <div class="folder">
            <div class="folder-header">
                <div class="folder-title">📁 {folder.folder_name}</div>
                <div class="folder-stats">
                    {folder.total_files} files •
                    <span class="pass">{folder.passed} passed</span> •
                    <span class="fail">{folder.failed} failed</span> •
                    <span class="skip">{folder.skipped} skipped</span> •
                    <span class="timeout">{folder.timeout} timeout</span> •
                    {success_rate:.1f}% success rate •
                    {folder.total_time:.1f}s total
                </div>
            </div>
            <div class="files">
"""

            for file_result in folder.files:
                status_class = f"status-{file_result.status}"
                html_content += f"""
                <div class="file">
                    <div class="file-name">{file_result.file_path}</div>
                    <div>
                        <span class="file-status {status_class}">{file_result.status.upper()}</span>
                        <span class="file-time">{file_result.execution_time:.2f}s</span>
                    </div>
                </div>
"""

                if file_result.error_message:
                    html_content += f"""
                <div class="error-details">
                    <strong>Error:</strong> {file_result.error_message}
                </div>
"""

            html_content += """
            </div>
        </div>
"""

        html_content += """
    </div>
</body>
</html>
"""

        with open(output_path, "w") as f:
            f.write(html_content)

    def generate_csv_report(self, summary: OverallSummary, output_path: Path):
        """Generate CSV report."""
        import csv

        with open(output_path, "w", newline="") as csvfile:
            fieldnames = [
                "folder",
                "file_path",
                "status",
                "execution_time",
                "error_type",
                "error_message",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for folder in summary.folders:
                for file_result in folder.files:
                    writer.writerow(
                        {
                            "folder": file_result.folder,
                            "file_path": file_result.file_path,
                            "status": file_result.status,
                            "execution_time": file_result.execution_time,
                            "error_type": file_result.error_type or "",
                            "error_message": file_result.error_message or "",
                        }
                    )

    def print_summary(self, summary: OverallSummary):
        """Print detailed summary to console."""
        self.logger.info("\n" + "=" * 80)
        self.logger.info("🎯 COMPREHENSIVE EXAMPLES TEST RESULTS")
        self.logger.info("=" * 80)

        # Overall statistics
        success_rate = (
            (summary.total_passed / summary.total_files * 100)
            if summary.total_files > 0
            else 0
        )

        self.logger.info("📊 Overall Results:")
        self.logger.info(f"  • Folders tested: {summary.total_folders}")
        self.logger.info(f"  • Total files: {summary.total_files}")
        self.logger.info(f"  • ✅ Passed: {summary.total_passed}")
        self.logger.info(f"  • ❌ Failed: {summary.total_failed}")
        self.logger.info(f"  • ⏸️ Skipped: {summary.total_skipped}")
        self.logger.info(f"  • ⏰ Timeout: {summary.total_timeout}")
        self.logger.info(f"  • 📈 Success rate: {success_rate:.1f}%")
        self.logger.info(f"  • ⏱️ Total time: {summary.total_execution_time:.1f}s")

        # Top performing folders
        self.logger.info("\n🏆 Top Performing Folders:")
        sorted_folders = sorted(
            summary.folders,
            key=lambda f: (f.passed / f.total_files if f.total_files > 0 else 0),
            reverse=True,
        )
        for i, folder in enumerate(sorted_folders[:5], 1):
            folder_success_rate = (
                (folder.passed / folder.total_files * 100)
                if folder.total_files > 0
                else 0
            )
            self.logger.info(
                f"  {i}. {folder.folder_name}: {folder_success_rate:.1f}% ({folder.passed}/{folder.total_files})"
            )

        # Problematic folders
        problem_folders = [f for f in summary.folders if f.failed > 0 or f.timeout > 0]
        if problem_folders:
            self.logger.info("\n⚠️ Folders with Issues:")
            for folder in problem_folders:
                self.logger.info(
                    f"  • {folder.folder_name}: {folder.failed} failed, {folder.timeout} timeout"
                )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Comprehensive Examples Test Runner")
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=Path("examples"),
        help="Root directory of examples (default: examples)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("test_results"),
        help="Output directory for reports (default: test_results)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Maximum parallel workers (default: 4)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout per file in seconds (default: 120)",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=2,
        help="Number of retries for failed tests (default: 2)",
    )
    parser.add_argument(
        "--no-parallel", action="store_true", help="Disable parallel execution"
    )
    parser.add_argument("--quiet", action="store_true", help="Reduce output verbosity")
    parser.add_argument(
        "--folder",
        type=str,
        help="Test only specific folder (relative to examples root)",
    )

    args = parser.parse_args()

    # Convert to absolute paths
    examples_root = args.examples_root.resolve()
    output_dir = args.output_dir.resolve()

    if not examples_root.exists():
        print(f"❌ Examples directory not found: {examples_root}")
        return 1

    # Initialize runner
    runner = ExamplesTestRunner(
        examples_root=examples_root,
        max_workers=args.max_workers,
        timeout=args.timeout,
        retry_count=args.retry_count,
        parallel=not args.no_parallel,
        verbose=not args.quiet,
    )

    # Run tests
    try:
        summary = runner.run_all_folders()

        # Generate reports
        runner.generate_reports(summary, output_dir)

        # Print summary
        runner.print_summary(summary)

        # Return appropriate exit code
        return 0 if summary.total_failed == 0 and summary.total_timeout == 0 else 1

    except KeyboardInterrupt:
        runner.logger.info("\n❌ Test run interrupted by user")
        return 130
    except Exception as e:
        runner.logger.error(f"❌ Test run failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
