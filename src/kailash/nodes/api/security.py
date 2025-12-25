"""Security scanning and audit nodes for security assessment."""

import socket
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import requests
from kailash.nodes.base import Node, NodeParameter, register_node


@register_node()
class SecurityScannerNode(Node):
    """
    Performs security scans and vulnerability assessments.

    This node provides comprehensive security scanning capabilities for web
    applications, networks, and systems. It replaces DataTransformer with
    embedded Python code for security audit tasks, offering standardized
    security assessment patterns.

    Design Philosophy:
        Security assessment requires consistent, thorough scanning with proper
        reporting. This node eliminates the need for custom security scanning
        code in DataTransformer nodes by providing dedicated, configurable
        security assessment capabilities with industry-standard checks.

    Upstream Dependencies:
        - Target discovery nodes
        - Configuration nodes with scan parameters
        - Authentication credential nodes
        - Scope definition nodes

    Downstream Consumers:
        - Vulnerability reporting nodes
        - Risk assessment nodes
        - Compliance checking nodes
        - Alert generation nodes
        - Remediation workflow nodes

    Configuration:
        - Scan types and targets
        - Vulnerability databases
        - Scan intensity and depth
        - Authentication parameters
        - Exclusion patterns

    Implementation Details:
        - Multiple scan types (port, web, SSL, etc.)
        - Vulnerability classification
        - Risk scoring and prioritization
        - Compliance framework mapping
        - Detailed finding documentation

    Error Handling:
        - Network timeout management
        - Permission error handling
        - Invalid target handling
        - Partial scan completion

    Side Effects:
        - Network requests to target systems
        - File system access for local scans
        - Process execution for external tools
        - Logging of scan activities

    Examples:
        >>> # Web application security scan
        >>> scanner = SecurityScannerNode(
        ...     scan_types=['web_security', 'ssl_check'],
        ...     targets=['https://example.com', 'https://app.example.com'],
        ...     scan_depth='basic'
        ... )
        >>> result = scanner.execute()
        >>> assert 'security_findings' in result
        >>> assert result['scan_summary']['total_targets'] == 2
        >>>
        >>> # Network security scan
        >>> scanner = SecurityScannerNode(
        ...     scan_types=['port_scan', 'service_detection'],
        ...     targets=['192.168.1.0/24'],
        ...     ports='1-1024'
        ... )
        >>> result = scanner.execute()
        >>> assert 'security_findings' in result
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "scan_types": NodeParameter(
                name="scan_types",
                type=list,
                required=True,
                description="Types of security scans to perform",
            ),
            "targets": NodeParameter(
                name="targets",
                type=list,
                required=True,
                description="List of targets to scan (URLs, IPs, domains)",
            ),
            "scan_depth": NodeParameter(
                name="scan_depth",
                type=str,
                required=False,
                default="basic",
                description="Scan depth: basic, standard, or comprehensive",
            ),
            "ports": NodeParameter(
                name="ports",
                type=str,
                required=False,
                default="common",
                description="Port range to scan (e.g., '1-1024', 'common', 'all')",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=60,
                description="Timeout in seconds for each scan",
            ),
            "include_compliance": NodeParameter(
                name="include_compliance",
                type=bool,
                required=False,
                default=True,
                description="Include compliance framework mapping",
            ),
            "risk_scoring": NodeParameter(
                name="risk_scoring",
                type=bool,
                required=False,
                default=True,
                description="Calculate risk scores for findings",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        scan_types = kwargs["scan_types"]
        targets = kwargs["targets"]
        scan_depth = kwargs.get("scan_depth", "basic")
        ports = kwargs.get("ports", "common")
        timeout = kwargs.get("timeout", 60)
        include_compliance = kwargs.get("include_compliance", True)
        risk_scoring = kwargs.get("risk_scoring", True)

        start_time = time.time()
        all_findings = []
        scan_results = {}

        for target in targets:
            target_findings = []

            for scan_type in scan_types:
                try:
                    findings = self._perform_scan(
                        scan_type, target, scan_depth, ports, timeout
                    )
                    target_findings.extend(findings)
                except Exception as e:
                    # Log scan error but continue with other scans
                    error_finding = {
                        "type": "scan_error",
                        "target": target,
                        "scan_type": scan_type,
                        "severity": "info",
                        "title": f"Scan Error: {scan_type}",
                        "description": f"Failed to complete {scan_type} scan: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                    }
                    target_findings.append(error_finding)

            # Post-process findings
            if risk_scoring:
                target_findings = self._calculate_risk_scores(target_findings)

            if include_compliance:
                target_findings = self._add_compliance_mapping(target_findings)

            all_findings.extend(target_findings)
            scan_results[target] = target_findings

        execution_time = time.time() - start_time

        # Generate summary
        scan_summary = self._generate_scan_summary(
            all_findings, targets, scan_types, execution_time
        )

        return {
            "security_findings": all_findings,
            "scan_results": scan_results,
            "scan_summary": scan_summary,
            "total_findings": len(all_findings),
            "high_risk_findings": len(
                [f for f in all_findings if f.get("risk_score", 0) >= 8]
            ),
            "medium_risk_findings": len(
                [f for f in all_findings if 4 <= f.get("risk_score", 0) < 8]
            ),
            "low_risk_findings": len(
                [f for f in all_findings if 1 <= f.get("risk_score", 0) < 4]
            ),
            "execution_time": execution_time,
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }

    def _perform_scan(
        self, scan_type: str, target: str, scan_depth: str, ports: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Perform a specific type of security scan."""

        if scan_type == "web_security":
            return self._scan_web_security(target, scan_depth, timeout)
        elif scan_type == "ssl_check":
            return self._scan_ssl(target, timeout)
        elif scan_type == "port_scan":
            return self._scan_ports(target, ports, timeout)
        elif scan_type == "service_detection":
            return self._scan_services(target, ports, timeout)
        elif scan_type == "vulnerability_check":
            return self._scan_vulnerabilities(target, scan_depth, timeout)
        elif scan_type == "header_analysis":
            return self._scan_headers(target, timeout)
        else:
            return [
                {
                    "type": "unsupported_scan",
                    "target": target,
                    "severity": "info",
                    "title": f"Unsupported Scan Type: {scan_type}",
                    "description": f"Scan type '{scan_type}' is not supported",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            ]

    def _scan_web_security(
        self, target: str, scan_depth: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Perform web application security scan."""
        findings = []

        try:
            response = requests.get(target, timeout=timeout, allow_redirects=True)

            # Check for common security issues
            findings.extend(self._check_security_headers(target, response))
            findings.extend(self._check_ssl_redirect(target, response))
            findings.extend(self._check_directory_listing(target, response))

            if scan_depth in ["standard", "comprehensive"]:
                findings.extend(self._check_common_files(target, timeout))
                findings.extend(self._check_injection_points(target, timeout))

            if scan_depth == "comprehensive":
                findings.extend(self._check_authentication(target, timeout))

        except requests.RequestException as e:
            findings.append(
                {
                    "type": "connection_error",
                    "target": target,
                    "severity": "medium",
                    "title": "Connection Error",
                    "description": f"Failed to connect to target: {str(e)}",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _scan_ssl(self, target: str, timeout: int) -> list[dict[str, Any]]:
        """Perform SSL/TLS security scan."""
        findings = []

        try:
            parsed_url = urlparse(target)
            hostname = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)

            if parsed_url.scheme != "https":
                findings.append(
                    {
                        "type": "ssl_not_used",
                        "target": target,
                        "severity": "medium",
                        "title": "SSL/TLS Not Used",
                        "description": "Target does not use HTTPS encryption",
                        "recommendation": "Implement SSL/TLS encryption",
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                    }
                )
                return findings

            # Check SSL certificate using OpenSSL (if available)
            try:
                import ssl

                context = ssl.create_default_context()
                with socket.create_connection(
                    (hostname, port), timeout=timeout
                ) as sock:
                    with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                        cert = ssock.getpeercert()

                        # Check certificate expiration
                        not_after = datetime.strptime(
                            cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                        )
                        days_until_expiry = (not_after - datetime.now()).days

                        if days_until_expiry < 30:
                            findings.append(
                                {
                                    "type": "ssl_expiring",
                                    "target": target,
                                    "severity": (
                                        "high" if days_until_expiry < 7 else "medium"
                                    ),
                                    "title": "SSL Certificate Expiring",
                                    "description": f"SSL certificate expires in {days_until_expiry} days",
                                    "details": {"expiry_date": cert["notAfter"]},
                                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                                }
                            )

            except Exception as e:
                findings.append(
                    {
                        "type": "ssl_check_error",
                        "target": target,
                        "severity": "low",
                        "title": "SSL Check Error",
                        "description": f"Failed to perform detailed SSL check: {str(e)}",
                        "timestamp": datetime.now(UTC).isoformat() + "Z",
                    }
                )

        except Exception as e:
            findings.append(
                {
                    "type": "ssl_scan_error",
                    "target": target,
                    "severity": "low",
                    "title": "SSL Scan Error",
                    "description": f"SSL scan failed: {str(e)}",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _scan_ports(
        self, target: str, ports: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Perform port scan."""
        findings = []

        # Parse target to get hostname/IP
        if target.startswith(("http://", "https://")):
            hostname = urlparse(target).hostname
        else:
            hostname = target

        # Define port ranges
        if ports == "common":
            port_list = [
                21,
                22,
                23,
                25,
                53,
                80,
                110,
                143,
                443,
                993,
                995,
                1433,
                3306,
                3389,
                5432,
                6379,
            ]
        elif ports == "all":
            port_list = range(1, 65536)
        elif "-" in ports:
            start, end = map(int, ports.split("-"))
            port_list = range(start, end + 1)
        else:
            port_list = [
                int(p.strip()) for p in ports.split(",") if p.strip().isdigit()
            ]

        open_ports = []
        for port in port_list:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(
                    min(timeout / len(port_list), 1)
                )  # Adjust timeout per port
                result = sock.connect_ex((hostname, port))
                sock.close()

                if result == 0:
                    open_ports.append(port)

                    # Check for potentially risky open ports
                    risky_ports = {
                        21: ("FTP", "medium"),
                        23: ("Telnet", "high"),
                        25: ("SMTP", "low"),
                        1433: ("SQL Server", "medium"),
                        3306: ("MySQL", "medium"),
                        3389: ("RDP", "high"),
                        5432: ("PostgreSQL", "medium"),
                        6379: ("Redis", "medium"),
                    }

                    if port in risky_ports:
                        service, severity = risky_ports[port]
                        findings.append(
                            {
                                "type": "open_port",
                                "target": target,
                                "severity": severity,
                                "title": f"Potentially Risky Open Port: {port}",
                                "description": f"Port {port} ({service}) is open and accessible",
                                "details": {"port": port, "service": service},
                                "recommendation": f"Ensure {service} service is properly secured",
                                "timestamp": datetime.now(UTC).isoformat() + "Z",
                            }
                        )

            except Exception:
                continue  # Port closed or filtered

        # Add summary finding
        if open_ports:
            findings.append(
                {
                    "type": "port_scan_summary",
                    "target": target,
                    "severity": "info",
                    "title": "Port Scan Results",
                    "description": f"Found {len(open_ports)} open ports",
                    "details": {
                        "open_ports": open_ports,
                        "total_scanned": len(port_list),
                    },
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _scan_services(
        self, target: str, ports: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Perform service detection scan."""
        # For now, this is a simplified version
        # In a full implementation, you would use nmap or similar tools
        return self._scan_ports(target, ports, timeout)

    def _scan_vulnerabilities(
        self, target: str, scan_depth: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Perform vulnerability scan using known CVE patterns."""
        findings = []

        try:
            response = requests.get(target, timeout=timeout)

            # Check for common vulnerability indicators
            server_header = response.headers.get("Server", "").lower()

            # Check for outdated software versions (simplified)
            vulnerable_patterns = {
                "apache/2.2": {"cve": "CVE-2012-0053", "severity": "medium"},
                "nginx/1.0": {"cve": "CVE-2013-2028", "severity": "medium"},
                "iis/7.0": {"cve": "CVE-2010-1256", "severity": "high"},
            }

            for pattern, vuln_info in vulnerable_patterns.items():
                if pattern in server_header:
                    findings.append(
                        {
                            "type": "potential_vulnerability",
                            "target": target,
                            "severity": vuln_info["severity"],
                            "title": "Potentially Vulnerable Server Version",
                            "description": f"Server header indicates potentially vulnerable version: {server_header}",
                            "details": {
                                "server_header": server_header,
                                "potential_cve": vuln_info["cve"],
                            },
                            "recommendation": "Update server software to latest version",
                            "timestamp": datetime.now(UTC).isoformat() + "Z",
                        }
                    )

        except Exception as e:
            findings.append(
                {
                    "type": "vulnerability_scan_error",
                    "target": target,
                    "severity": "low",
                    "title": "Vulnerability Scan Error",
                    "description": f"Failed to perform vulnerability scan: {str(e)}",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _scan_headers(self, target: str, timeout: int) -> list[dict[str, Any]]:
        """Perform HTTP security headers analysis."""
        findings = []

        try:
            response = requests.get(target, timeout=timeout)
            headers = response.headers

            # Check for missing security headers
            security_headers = {
                "X-Frame-Options": "Clickjacking protection",
                "X-Content-Type-Options": "MIME type sniffing protection",
                "X-XSS-Protection": "XSS protection",
                "Strict-Transport-Security": "HTTPS enforcement",
                "Content-Security-Policy": "Content injection protection",
                "Referrer-Policy": "Referrer information control",
            }

            for header, description in security_headers.items():
                if header not in headers:
                    findings.append(
                        {
                            "type": "missing_security_header",
                            "target": target,
                            "severity": "medium",
                            "title": f"Missing Security Header: {header}",
                            "description": f"Missing {header} header for {description}",
                            "recommendation": f"Implement {header} header",
                            "timestamp": datetime.now(UTC).isoformat() + "Z",
                        }
                    )

        except Exception as e:
            findings.append(
                {
                    "type": "header_scan_error",
                    "target": target,
                    "severity": "low",
                    "title": "Header Scan Error",
                    "description": f"Failed to analyze headers: {str(e)}",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _check_security_headers(
        self, target: str, response: requests.Response
    ) -> list[dict[str, Any]]:
        """Check for security headers in response."""
        return self._scan_headers(target, 30)  # Reuse header scan logic

    def _check_ssl_redirect(
        self, target: str, response: requests.Response
    ) -> list[dict[str, Any]]:
        """Check if HTTP redirects to HTTPS."""
        findings = []

        if target.startswith("http://") and not response.url.startswith("https://"):
            findings.append(
                {
                    "type": "no_ssl_redirect",
                    "target": target,
                    "severity": "medium",
                    "title": "No HTTPS Redirect",
                    "description": "HTTP requests are not redirected to HTTPS",
                    "recommendation": "Implement automatic HTTPS redirect",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _check_directory_listing(
        self, target: str, response: requests.Response
    ) -> list[dict[str, Any]]:
        """Check for directory listing vulnerabilities."""
        findings = []

        if "Index of /" in response.text or "Directory listing for" in response.text:
            findings.append(
                {
                    "type": "directory_listing",
                    "target": target,
                    "severity": "medium",
                    "title": "Directory Listing Enabled",
                    "description": "Directory listing is enabled, potentially exposing sensitive files",
                    "recommendation": "Disable directory listing",
                    "timestamp": datetime.now(UTC).isoformat() + "Z",
                }
            )

        return findings

    def _check_common_files(self, target: str, timeout: int) -> list[dict[str, Any]]:
        """Check for common sensitive files."""
        findings = []

        common_files = [
            ".env",
            "config.php",
            "wp-config.php",
            ".htaccess",
            "robots.txt",
            "sitemap.xml",
            "admin/",
            "backup/",
        ]

        base_url = target.rstrip("/")
        for file_path in common_files:
            try:
                url = f"{base_url}/{file_path}"
                response = requests.get(url, timeout=timeout)
                if response.status_code == 200:
                    findings.append(
                        {
                            "type": "sensitive_file_exposed",
                            "target": target,
                            "severity": (
                                "medium"
                                if file_path in [".env", "config.php", "wp-config.php"]
                                else "low"
                            ),
                            "title": f"Sensitive File Accessible: {file_path}",
                            "description": f"Sensitive file {file_path} is publicly accessible",
                            "details": {"file_path": file_path, "url": url},
                            "recommendation": "Restrict access to sensitive files",
                            "timestamp": datetime.now(UTC).isoformat() + "Z",
                        }
                    )
            except:
                continue

        return findings

    def _check_injection_points(
        self, target: str, timeout: int
    ) -> list[dict[str, Any]]:
        """Check for basic injection vulnerabilities."""
        # This is a simplified check - real implementations would be much more thorough
        findings = []

        test_payloads = [
            "' OR '1'='1",
            "<script>alert('xss')</script>",
            "../../../etc/passwd",
        ]

        for payload in test_payloads:
            try:
                response = requests.get(
                    target, params={"test": payload}, timeout=timeout
                )

                # Very basic detection - real scanners would be much more sophisticated
                if payload in response.text:
                    findings.append(
                        {
                            "type": "potential_injection",
                            "target": target,
                            "severity": "high",
                            "title": "Potential Injection Vulnerability",
                            "description": f"Test payload reflected in response: {payload[:50]}...",
                            "recommendation": "Implement proper input validation and sanitization",
                            "timestamp": datetime.now(UTC).isoformat() + "Z",
                        }
                    )
                    break  # Don't continue testing if one is found
            except:
                continue

        return findings

    def _check_authentication(self, target: str, timeout: int) -> list[dict[str, Any]]:
        """Check for authentication-related issues."""
        findings = []

        # Check for login pages without HTTPS
        if target.startswith("http://"):
            login_paths = ["/login", "/admin", "/wp-admin", "/signin"]
            for path in login_paths:
                try:
                    url = f"{target.rstrip('/')}{path}"
                    response = requests.get(url, timeout=timeout)
                    if (
                        response.status_code == 200
                        and "password" in response.text.lower()
                    ):
                        findings.append(
                            {
                                "type": "insecure_login",
                                "target": target,
                                "severity": "high",
                                "title": "Insecure Login Page",
                                "description": f"Login page at {path} is not using HTTPS",
                                "details": {"login_path": path},
                                "recommendation": "Use HTTPS for all authentication pages",
                                "timestamp": datetime.now(UTC).isoformat() + "Z",
                            }
                        )
                except:
                    continue

        return findings

    def _calculate_risk_scores(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Calculate risk scores for findings."""
        severity_scores = {
            "critical": 10,
            "high": 8,
            "medium": 5,
            "low": 2,
            "info": 1,
        }

        for finding in findings:
            severity = finding.get("severity", "info")
            base_score = severity_scores.get(severity, 1)

            # Adjust score based on finding type
            type_modifiers = {
                "ssl_expiring": 1.2,
                "potential_vulnerability": 1.5,
                "insecure_login": 1.3,
                "directory_listing": 1.1,
            }

            finding_type = finding.get("type", "")
            modifier = type_modifiers.get(finding_type, 1.0)

            finding["risk_score"] = min(10, base_score * modifier)

        return findings

    def _add_compliance_mapping(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Add compliance framework mapping to findings."""
        compliance_mapping = {
            "missing_security_header": ["OWASP Top 10", "PCI DSS"],
            "ssl_not_used": ["PCI DSS", "HIPAA", "SOX"],
            "insecure_login": ["PCI DSS", "HIPAA", "GDPR"],
            "potential_vulnerability": ["OWASP Top 10", "NIST"],
            "directory_listing": ["OWASP Top 10"],
        }

        for finding in findings:
            finding_type = finding.get("type", "")
            if finding_type in compliance_mapping:
                finding["compliance_frameworks"] = compliance_mapping[finding_type]

        return findings

    def _generate_scan_summary(
        self,
        findings: list[dict],
        targets: list[str],
        scan_types: list[str],
        execution_time: float,
    ) -> dict[str, Any]:
        """Generate summary of security scan results."""

        # Count findings by severity
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}

        for finding in findings:
            severity = finding.get("severity", "info")
            if severity in severity_counts:
                severity_counts[severity] += 1

        # Count findings by type
        type_counts = {}
        for finding in findings:
            finding_type = finding.get("type", "unknown")
            type_counts[finding_type] = type_counts.get(finding_type, 0) + 1

        # Calculate overall risk level
        if severity_counts["critical"] > 0:
            overall_risk = "critical"
        elif severity_counts["high"] > 0:
            overall_risk = "high"
        elif severity_counts["medium"] > 0:
            overall_risk = "medium"
        elif severity_counts["low"] > 0:
            overall_risk = "low"
        else:
            overall_risk = "minimal"

        return {
            "total_targets": len(targets),
            "scan_types": scan_types,
            "total_findings": len(findings),
            "severity_breakdown": severity_counts,
            "finding_types": type_counts,
            "overall_risk_level": overall_risk,
            "execution_time": execution_time,
            "scan_completed": True,
        }
