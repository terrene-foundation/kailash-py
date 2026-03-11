"""
Production-Ready Monitoring and Alerting Workflow

Real-world use case: Monitor system health, check endpoints, detect anomalies, send alerts
This agent autonomously monitors targets, detects failures, and generates alerts.
"""

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class MonitoringSignature(Signature):
    targets: List[str] = InputField(description="Monitoring targets")
    health_status: dict = OutputField(description="System health status")
    alerts: List[dict] = OutputField(description="Generated alerts")


@dataclass
class MonitorConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.0
    check_timeout: int = 10
    alert_threshold: int = 2
    check_interval: int = 60


class SystemMonitor(BaseAgent):
    """Production system monitoring agent with alerting capabilities."""

    def __init__(self, config: MonitorConfig):
        super().__init__(
            config=config,
            signature=MonitoringSignature(),
        )
        self.timeout = config.check_timeout
        self.alert_threshold = config.alert_threshold
        self.failure_counts = {}

    async def check_endpoint(self, endpoint: str) -> Dict:
        """Check single endpoint health."""

        result = await self.execute_tool(
            "http_get", {"url": endpoint, "timeout": self.timeout}
        )

        status_code = result.result.get("status_code", 0) if result.success else 0
        is_healthy = result.success and 200 <= status_code < 400

        check_result = {
            "endpoint": endpoint,
            "timestamp": datetime.utcnow().isoformat(),
            "healthy": is_healthy,
            "status_code": status_code,
            "response_time": (
                result.result.get("elapsed", 0) if result.success else None
            ),
            "error": result.error if not result.success else None,
        }

        if not is_healthy:
            self.failure_counts[endpoint] = self.failure_counts.get(endpoint, 0) + 1
        else:
            self.failure_counts[endpoint] = 0

        return check_result

    async def check_file_system(self, paths: List[str]) -> Dict:
        """Check file system health."""

        results = {"healthy": True, "checks": [], "issues": []}

        for path in paths:
            exists_result = await self.execute_tool("file_exists", {"path": path})

            check = {
                "path": path,
                "exists": (
                    exists_result.result.get("exists", False)
                    if exists_result.success
                    else False
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }

            results["checks"].append(check)

            if not check["exists"]:
                results["healthy"] = False
                results["issues"].append(f"Missing: {path}")

        return results

    async def run_health_checks(
        self,
        endpoints: Optional[List[str]] = None,
        file_paths: Optional[List[str]] = None,
    ) -> Dict:
        """Execute all health checks."""

        results = {
            "timestamp": datetime.utcnow().isoformat(),
            "endpoints": [],
            "file_system": None,
            "overall_health": True,
            "alerts": [],
        }

        if endpoints:
            endpoint_tasks = [self.check_endpoint(ep) for ep in endpoints]
            endpoint_results = await asyncio.gather(
                *endpoint_tasks, return_exceptions=True
            )

            for result in endpoint_results:
                if isinstance(result, Exception):
                    results["overall_health"] = False
                    results["alerts"].append(
                        {
                            "severity": "critical",
                            "message": f"Check failed: {str(result)}",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                else:
                    results["endpoints"].append(result)

                    if not result["healthy"]:
                        results["overall_health"] = False

                        failure_count = self.failure_counts.get(result["endpoint"], 0)

                        if failure_count >= self.alert_threshold:
                            results["alerts"].append(
                                {
                                    "severity": "high",
                                    "endpoint": result["endpoint"],
                                    "message": f"Endpoint down: {failure_count} consecutive failures",
                                    "status_code": result.get("status_code"),
                                    "error": result.get("error"),
                                    "timestamp": result["timestamp"],
                                }
                            )

        if file_paths:
            fs_result = await self.check_file_system(file_paths)
            results["file_system"] = fs_result

            if not fs_result["healthy"]:
                results["overall_health"] = False

                for issue in fs_result["issues"]:
                    results["alerts"].append(
                        {
                            "severity": "medium",
                            "message": f"File system issue: {issue}",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

        return results

    async def generate_alert_report(
        self, check_results: Dict, output_path: str
    ) -> Dict:
        """Generate and save alert report."""

        report_lines = [
            "=" * 80,
            "SYSTEM MONITORING REPORT",
            "=" * 80,
            f"Generated: {check_results['timestamp']}",
            f"Overall Health: {'✓ HEALTHY' if check_results['overall_health'] else '✗ UNHEALTHY'}",
            "",
        ]

        if check_results["alerts"]:
            report_lines.extend(
                [
                    "=" * 80,
                    f"ALERTS ({len(check_results['alerts'])})",
                    "=" * 80,
                ]
            )

            for alert in sorted(
                check_results["alerts"], key=lambda x: x.get("severity"), reverse=True
            ):
                severity = alert.get("severity", "unknown").upper()
                message = alert.get("message", "No message")
                timestamp = alert.get("timestamp", "")

                report_lines.append(f"\n[{severity}] {timestamp}")
                report_lines.append(f"  {message}")

                if "endpoint" in alert:
                    report_lines.append(f"  Endpoint: {alert['endpoint']}")
                if "status_code" in alert:
                    report_lines.append(f"  Status Code: {alert['status_code']}")
                if "error" in alert:
                    report_lines.append(f"  Error: {alert['error']}")

        if check_results["endpoints"]:
            report_lines.extend(
                [
                    "",
                    "=" * 80,
                    f"ENDPOINT CHECKS ({len(check_results['endpoints'])})",
                    "=" * 80,
                ]
            )

            for endpoint in check_results["endpoints"]:
                status = "✓" if endpoint["healthy"] else "✗"
                report_lines.append(
                    f"{status} {endpoint['endpoint']} (Status: {endpoint.get('status_code', 'N/A')})"
                )

                if endpoint.get("response_time"):
                    report_lines.append(
                        f"  Response Time: {endpoint['response_time']:.3f}s"
                    )

        if check_results["file_system"]:
            report_lines.extend(
                [
                    "",
                    "=" * 80,
                    "FILE SYSTEM CHECKS",
                    "=" * 80,
                ]
            )

            for check in check_results["file_system"]["checks"]:
                status = "✓" if check["exists"] else "✗"
                report_lines.append(f"{status} {check['path']}")

        report_lines.extend(["", "=" * 80])
        report_content = "\n".join(report_lines)

        write_result = await self.execute_tool(
            "write_file", {"path": output_path, "content": report_content}
        )

        if write_result.success:
            return {
                "status": "success",
                "path": output_path,
                "alerts_count": len(check_results["alerts"]),
            }
        else:
            return {"status": "error", "error": write_result.error}

    async def continuous_monitoring(
        self, endpoints: List[str], interval: int, duration: int, output_dir: str
    ) -> Dict:
        """Run continuous monitoring for specified duration."""

        results = {
            "start_time": datetime.utcnow().isoformat(),
            "checks_performed": 0,
            "alerts_generated": 0,
            "reports": [],
        }

        os.makedirs(output_dir, exist_ok=True)

        elapsed = 0
        while elapsed < duration:
            check_results = await self.run_health_checks(endpoints=endpoints)
            results["checks_performed"] += 1
            results["alerts_generated"] += len(check_results["alerts"])

            if check_results["alerts"]:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                report_path = os.path.join(output_dir, f"alert_{timestamp}.txt")

                report_result = await self.generate_alert_report(
                    check_results, report_path
                )

                if report_result["status"] == "success":
                    results["reports"].append(report_path)

            await asyncio.sleep(interval)
            elapsed += interval

        results["end_time"] = datetime.utcnow().isoformat()
        return results


async def main():
    """Production monitoring workflow."""

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required")
        return

    config = MonitorConfig()
    monitor = SystemMonitor(config)

    endpoints = os.getenv("MONITOR_ENDPOINTS", "").split(",")
    if not endpoints or endpoints == [""]:
        endpoints = [
            "https://api.github.com",
            "https://httpbin.org/status/200",
            "https://httpbin.org/delay/1",
        ]

    output_dir = os.getenv("MONITOR_OUTPUT_DIR", "/tmp/monitoring_reports")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Running health checks on {len(endpoints)} endpoints...")
    check_results = await monitor.run_health_checks(endpoints=endpoints)

    print("\nHealth Check Results:")
    print(
        f"  Overall Health: {'✓ HEALTHY' if check_results['overall_health'] else '✗ UNHEALTHY'}"
    )
    print(f"  Alerts: {len(check_results['alerts'])}")

    report_path = os.path.join(
        output_dir,
        f"monitoring_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt",
    )
    report_result = await monitor.generate_alert_report(check_results, report_path)

    if report_result["status"] == "success":
        print(f"\nReport saved: {report_path}")
        print(f"  Alerts: {report_result['alerts_count']}")


if __name__ == "__main__":
    asyncio.run(main())
