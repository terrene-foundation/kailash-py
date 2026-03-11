"""Tests for production monitoring and observability.

PROD-008: Health Checks
PROD-009: Performance Metrics
PROD-010: Monitoring Dashboards

Following TDD methodology - Tests written FIRST before implementation.
"""

import json
import time
from pathlib import Path

import pytest
import yaml


# Helper to get project root
def get_project_root():
    """Get absolute path to project root."""
    return Path(__file__).parent.parent.parent.resolve()


class TestHealthChecks:
    """Test PROD-008: Health check implementation."""

    def test_health_module_exists(self):
        """PROD-008.1: Health check module exists."""
        project_root = get_project_root()
        health_module = project_root / "src" / "kaizen" / "production" / "health.py"
        assert health_module.exists(), "src/kaizen/production/health.py must exist"

    def test_health_endpoint_implementation(self):
        """PROD-008.2: Health endpoint implementation exists."""
        project_root = get_project_root()
        health_module = project_root / "src" / "kaizen" / "production" / "health.py"

        with open(health_module) as f:
            content = f.read()
            assert "liveness" in content.lower(), "Must implement liveness probe"
            assert "readiness" in content.lower(), "Must implement readiness probe"
            assert (
                "startup" in content.lower() or "health" in content.lower()
            ), "Must implement startup/health probe"

    def test_health_check_returns_status(self):
        """PROD-008.3: Health check returns proper status."""
        project_root = get_project_root()

        # Import health module
        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()
        status = health.check()

        assert "status" in status, "Health check must return status"
        assert status["status"] in [
            "healthy",
            "unhealthy",
            "degraded",
        ], "Status must be one of: healthy, unhealthy, degraded"

    def test_liveness_probe_implementation(self):
        """PROD-008.4: Liveness probe checks basic process health."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()
        liveness = health.liveness()

        assert (
            "alive" in liveness or "status" in liveness
        ), "Liveness probe must return alive status"

    def test_readiness_probe_implementation(self):
        """PROD-008.5: Readiness probe checks if service can handle requests."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()
        readiness = health.readiness()

        assert (
            "ready" in readiness or "status" in readiness
        ), "Readiness probe must return ready status"

    def test_startup_probe_implementation(self):
        """PROD-008.6: Startup probe checks if service has started successfully."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()
        startup = health.startup()

        assert (
            "started" in startup or "status" in startup
        ), "Startup probe must return started status"

    def test_dependency_health_checks(self):
        """PROD-008.7: Health checks include dependency status."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()

        # Add mock dependencies
        health.add_dependency("database", lambda: True)
        health.add_dependency("cache", lambda: True)

        status = health.check()

        assert "dependencies" in status, "Health check must include dependency status"
        assert "database" in status["dependencies"], "Must check database dependency"
        assert "cache" in status["dependencies"], "Must check cache dependency"

    def test_health_check_timeout_handling(self):
        """PROD-008.8: Health checks handle slow dependencies with timeout."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()

        # Add slow dependency
        def slow_check():
            time.sleep(5)
            return True

        health.add_dependency("slow_service", slow_check, timeout=1)

        start = time.time()
        status = health.check()
        duration = time.time() - start

        # Should timeout within 2 seconds (1 second timeout + overhead)
        assert duration < 2.0, "Health check should timeout on slow dependencies"
        assert (
            status["dependencies"]["slow_service"]["status"] == "timeout"
        ), "Should mark slow dependency as timeout"

    def test_health_check_error_handling(self):
        """PROD-008.9: Health checks handle dependency errors gracefully."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.health import HealthCheck

        health = HealthCheck()

        # Add failing dependency
        def failing_check():
            raise Exception("Connection failed")

        health.add_dependency("failing_service", failing_check)

        # Should not raise, should return error in status
        status = health.check()

        assert (
            status["dependencies"]["failing_service"]["status"] == "unhealthy"
        ), "Should mark failing dependency as unhealthy"
        assert (
            "error" in status["dependencies"]["failing_service"]
        ), "Should include error message"

    def test_health_endpoint_in_k8s_deployment(self):
        """PROD-008.10: Kubernetes deployment uses health endpoints."""
        project_root = get_project_root()
        deployment = project_root / "k8s" / "deployment.yaml"

        with open(deployment) as f:
            doc = yaml.safe_load(f)
            containers = doc["spec"]["template"]["spec"]["containers"]

            for container in containers:
                if "livenessProbe" in container:
                    probe = container["livenessProbe"]
                    # Check for HTTP or exec probe
                    has_health_check = (
                        "httpGet" in probe
                        and "/health" in probe["httpGet"].get("path", "")
                    ) or ("exec" in probe)
                    assert (
                        has_health_check
                    ), f"Container {container['name']} liveness probe should use health endpoint"


class TestPerformanceMetrics:
    """Test PROD-009: Performance metrics and monitoring."""

    def test_metrics_module_exists(self):
        """PROD-009.1: Metrics collection module exists."""
        project_root = get_project_root()
        metrics_module = project_root / "src" / "kaizen" / "production" / "metrics.py"
        assert metrics_module.exists(), "src/kaizen/production/metrics.py must exist"

    def test_prometheus_client_available(self):
        """PROD-009.2: Prometheus client library is available."""
        try:
            import prometheus_client

            assert True
        except ImportError:
            pytest.fail("prometheus_client must be installed for metrics")

    def test_red_metrics_implementation(self):
        """PROD-009.3: RED metrics (Rate, Errors, Duration) are implemented."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Rate metrics
        assert hasattr(metrics, "request_rate") or hasattr(
            metrics, "track_request"
        ), "Must track request rate"

        # Error metrics
        assert hasattr(metrics, "error_rate") or hasattr(
            metrics, "track_error"
        ), "Must track error rate"

        # Duration metrics
        assert hasattr(metrics, "request_duration") or hasattr(
            metrics, "track_duration"
        ), "Must track request duration"

    def test_request_counter_metric(self):
        """PROD-009.4: Request counter metric is properly configured."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Record some requests
        metrics.track_request("qa_agent", "success")
        metrics.track_request("qa_agent", "success")
        metrics.track_request("qa_agent", "error")

        # Should be able to get current value
        total = metrics.get_request_count("qa_agent")
        assert total >= 3, "Should track all requests"

    def test_error_counter_metric(self):
        """PROD-009.5: Error counter metric is properly configured."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Record some errors
        metrics.track_error("qa_agent", "timeout")
        metrics.track_error("qa_agent", "validation")

        # Should be able to get error count
        errors = metrics.get_error_count("qa_agent")
        assert errors >= 2, "Should track all errors"

    def test_duration_histogram_metric(self):
        """PROD-009.6: Duration histogram metric is properly configured."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Record some durations
        metrics.track_duration("qa_agent", 0.5)
        metrics.track_duration("qa_agent", 1.2)
        metrics.track_duration("qa_agent", 0.8)

        # Should be able to get statistics
        stats = metrics.get_duration_stats("qa_agent")
        assert "count" in stats, "Should track count"
        assert "sum" in stats, "Should track sum"

    def test_custom_business_metrics(self):
        """PROD-009.7: Custom business metrics can be defined."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Define custom metric
        metrics.define_gauge("active_agents", "Number of active agents")

        # Update custom metric
        metrics.set_gauge("active_agents", 5)

        # Read custom metric
        value = metrics.get_gauge("active_agents")
        assert value == 5, "Should track custom gauge metrics"

    def test_metrics_labeling(self):
        """PROD-009.8: Metrics support labels for dimensionality."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Track with labels
        metrics.track_request(
            "agent", "success", labels={"model": "gpt-4", "env": "prod"}
        )
        metrics.track_request(
            "agent", "success", labels={"model": "gpt-3.5", "env": "prod"}
        )

        # Should be able to query by labels (must include status since that's part of the label set)
        gpt4_count = metrics.get_request_count(
            "agent", labels={"status": "success", "model": "gpt-4", "env": "prod"}
        )
        assert gpt4_count >= 1, "Should track labeled metrics"

        # Also verify total count across all labels
        total_count = metrics.get_request_count("agent")
        assert (
            total_count >= 2
        ), "Should track total requests across all label combinations"

    def test_metrics_endpoint_available(self):
        """PROD-009.9: Prometheus metrics endpoint is available."""
        project_root = get_project_root()

        import sys

        sys.path.insert(0, str(project_root / "src"))
        from kaizen.production.metrics import MetricsCollector

        metrics = MetricsCollector()

        # Should be able to export metrics in Prometheus format
        export = metrics.export_prometheus()

        assert isinstance(export, (str, bytes)), "Should export metrics as text"
        assert len(export) > 0, "Export should contain metrics data"

    def test_metrics_config_in_deployment(self):
        """PROD-009.10: Deployment includes metrics configuration."""
        project_root = get_project_root()

        # Check if metrics port is exposed
        deployment = project_root / "k8s" / "deployment.yaml"
        with open(deployment) as f:
            doc = yaml.safe_load(f)
            containers = doc["spec"]["template"]["spec"]["containers"]

            has_metrics_port = False
            for container in containers:
                if "ports" in container:
                    for port in container["ports"]:
                        if (
                            port.get("name") == "metrics"
                            or port.get("containerPort") == 9090
                        ):
                            has_metrics_port = True
                            break

            assert has_metrics_port, "Deployment should expose metrics port"


class TestMonitoringDashboards:
    """Test PROD-010: Monitoring dashboards and alerting."""

    def test_grafana_directory_exists(self):
        """PROD-010.1: Grafana dashboards directory exists."""
        project_root = get_project_root()
        grafana_dir = project_root / "monitoring" / "grafana"
        assert grafana_dir.exists(), "monitoring/grafana/ must exist"

    def test_prometheus_config_exists(self):
        """PROD-010.2: Prometheus configuration exists."""
        project_root = get_project_root()
        prometheus_config = (
            project_root / "monitoring" / "prometheus" / "prometheus.yml"
        )
        assert (
            prometheus_config.exists()
        ), "monitoring/prometheus/prometheus.yml must exist"

    def test_prometheus_config_valid(self):
        """PROD-010.3: Prometheus configuration is valid YAML."""
        project_root = get_project_root()
        prometheus_config = (
            project_root / "monitoring" / "prometheus" / "prometheus.yml"
        )

        with open(prometheus_config) as f:
            config = yaml.safe_load(f)
            assert "global" in config, "Prometheus config must have global section"
            assert (
                "scrape_configs" in config
            ), "Prometheus config must have scrape_configs"

    def test_prometheus_scrapes_kaizen(self):
        """PROD-010.4: Prometheus is configured to scrape Kaizen metrics."""
        project_root = get_project_root()
        prometheus_config = (
            project_root / "monitoring" / "prometheus" / "prometheus.yml"
        )

        with open(prometheus_config) as f:
            config = yaml.safe_load(f)

            scrape_configs = config.get("scrape_configs", [])
            has_kaizen_job = False

            for job in scrape_configs:
                if "kaizen" in job.get("job_name", "").lower():
                    has_kaizen_job = True
                    break

            assert has_kaizen_job, "Prometheus must have Kaizen scrape job"

    def test_alerting_rules_exist(self):
        """PROD-010.5: Prometheus alerting rules are defined."""
        project_root = get_project_root()
        alert_rules = project_root / "monitoring" / "prometheus" / "alerts.yml"
        assert alert_rules.exists(), "monitoring/prometheus/alerts.yml must exist"

    def test_alerting_rules_valid(self):
        """PROD-010.6: Alerting rules are valid YAML."""
        project_root = get_project_root()
        alert_rules = project_root / "monitoring" / "prometheus" / "alerts.yml"

        with open(alert_rules) as f:
            rules = yaml.safe_load(f)
            assert "groups" in rules, "Alert rules must have groups"
            assert len(rules["groups"]) > 0, "Must have at least one alert group"

    def test_critical_alerts_defined(self):
        """PROD-010.7: Critical alerts are defined for key metrics."""
        project_root = get_project_root()
        alert_rules = project_root / "monitoring" / "prometheus" / "alerts.yml"

        with open(alert_rules) as f:
            rules = yaml.safe_load(f)

            all_alerts = []
            for group in rules["groups"]:
                all_alerts.extend([r["alert"] for r in group.get("rules", [])])

            # Check for critical alerts
            assert any(
                "error" in a.lower() or "failure" in a.lower() for a in all_alerts
            ), "Must have error rate alerts"
            assert any(
                "latency" in a.lower() or "duration" in a.lower() for a in all_alerts
            ), "Must have latency alerts"

    def test_grafana_dashboard_exists(self):
        """PROD-010.8: Grafana dashboard JSON exists."""
        project_root = get_project_root()
        dashboards_dir = project_root / "monitoring" / "grafana" / "dashboards"

        assert dashboards_dir.exists(), "monitoring/grafana/dashboards/ must exist"

        # Check for at least one dashboard
        dashboards = list(dashboards_dir.glob("*.json"))
        assert len(dashboards) > 0, "Must have at least one Grafana dashboard"

    def test_grafana_dashboard_valid_json(self):
        """PROD-010.9: Grafana dashboard is valid JSON."""
        project_root = get_project_root()
        dashboards_dir = project_root / "monitoring" / "grafana" / "dashboards"

        dashboards = list(dashboards_dir.glob("*.json"))
        assert len(dashboards) > 0, "Must have dashboards to test"

        # Validate first dashboard
        with open(dashboards[0]) as f:
            dashboard = json.load(f)
            assert (
                "title" in dashboard or "dashboard" in dashboard
            ), "Dashboard must have title or dashboard object"

    def test_grafana_dashboard_has_panels(self):
        """PROD-010.10: Grafana dashboard has monitoring panels."""
        project_root = get_project_root()
        dashboards_dir = project_root / "monitoring" / "grafana" / "dashboards"

        dashboards = list(dashboards_dir.glob("*.json"))
        assert len(dashboards) > 0, "Must have dashboards to test"

        # Check first dashboard has panels
        with open(dashboards[0]) as f:
            data = json.load(f)

            # Handle both dashboard structure formats
            if "dashboard" in data:
                dashboard = data["dashboard"]
            else:
                dashboard = data

            assert "panels" in dashboard, "Dashboard must have panels"
            assert (
                len(dashboard["panels"]) > 0
            ), "Dashboard must have at least one panel"

    def test_monitoring_docker_compose_exists(self):
        """PROD-010.11: Docker Compose for monitoring stack exists."""
        project_root = get_project_root()
        monitoring_compose = project_root / "monitoring" / "docker-compose.yml"
        assert monitoring_compose.exists(), "monitoring/docker-compose.yml must exist"

    def test_monitoring_docker_compose_valid(self):
        """PROD-010.12: Monitoring Docker Compose is valid."""
        project_root = get_project_root()
        monitoring_compose = project_root / "monitoring" / "docker-compose.yml"

        with open(monitoring_compose) as f:
            compose = yaml.safe_load(f)

            assert "services" in compose, "docker-compose.yml must have services"
            assert (
                "prometheus" in compose["services"]
            ), "Must include Prometheus service"
            assert "grafana" in compose["services"], "Must include Grafana service"

    def test_monitoring_readme_exists(self):
        """PROD-010.13: Monitoring setup README exists."""
        project_root = get_project_root()
        monitoring_readme = project_root / "monitoring" / "README.md"
        assert monitoring_readme.exists(), "monitoring/README.md must exist"

    def test_monitoring_readme_has_instructions(self):
        """PROD-010.14: Monitoring README has setup instructions."""
        project_root = get_project_root()
        monitoring_readme = project_root / "monitoring" / "README.md"

        with open(monitoring_readme) as f:
            content = f.read()
            assert "prometheus" in content.lower(), "README must mention Prometheus"
            assert "grafana" in content.lower(), "README must mention Grafana"
            assert (
                "docker-compose" in content.lower()
            ), "README must have docker-compose instructions"
