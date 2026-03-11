"""
Tier 3 (E2E) tests for System 2: Structured Logging & Audit Enhancement.

Tests complete ELK (Elasticsearch + Logstash + Kibana) integration:
- Elasticsearch ingests JSON logs from LoggingHook
- Kibana search by trace_id works (optional)

Total: 2 tests

IMPORTANT: NO MOCKING - uses real Docker containers for Elasticsearch/Kibana.
"""

import json
import logging
import time
import uuid
from datetime import datetime
from io import StringIO

import pytest
from kaizen.core.autonomy.hooks import HookEvent, HookManager
from kaizen.core.autonomy.hooks.builtin.logging_hook import LoggingHook

# Check if optional E2E dependencies are available
try:
    import elasticsearch  # noqa: F401

    import docker  # noqa: F401

    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False


# ==============================================================================
# Category 1: Elasticsearch Integration (1 test)
# ==============================================================================


class TestElasticsearchIntegration:
    """Test Elasticsearch ingests and indexes JSON logs from LoggingHook"""

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.requires_docker
    @pytest.mark.skipif(
        not ELASTICSEARCH_AVAILABLE,
        reason="elasticsearch and docker libraries not installed",
    )
    @pytest.mark.asyncio
    async def test_elasticsearch_ingests_json_logs(self):
        """
        Test 1.1: Elasticsearch ingests JSON logs and supports trace_id queries.

        Requirement: Complete ELK integration for production log aggregation.
        Expected: JSON logs can be sent to Elasticsearch and queried by trace_id.

        Setup:
        1. Start Elasticsearch container (Docker)
        2. Configure LoggingHook to output JSON
        3. Generate logs via agent execution
        4. Send logs to Elasticsearch
        5. Verify Elasticsearch indexed logs
        6. Query by trace_id
        7. Validate JSON schema

        Note: This is a comprehensive E2E test that verifies the entire pipeline.
        """
        # Use existing Elasticsearch container from kailash_sdk test environment
        import docker

        client = docker.from_env()

        # Check if kailash_sdk Elasticsearch container is running
        es_container = None
        try:
            es_container = client.containers.get("kailash_sdk_test_elasticsearch")
            if es_container.status != "running":
                es_container.start()
                time.sleep(10)  # Wait for ES to start
        except docker.errors.NotFound:
            pytest.skip(
                "kailash_sdk_test_elasticsearch container not found - start docker test environment first"
            )

        # Wait for Elasticsearch to be ready
        from elasticsearch import Elasticsearch

        es_client = Elasticsearch(["http://localhost:9200"])
        max_wait = 30
        waited = 0
        while waited < max_wait:
            try:
                if es_client.ping():
                    break
            except Exception:
                pass
            time.sleep(1)
            waited += 1

        if waited >= max_wait:
            pytest.skip("Elasticsearch not responding within timeout")

        try:
            # Elasticsearch client already initialized above

            # Verify connection
            assert es_client.ping(), "Elasticsearch not reachable"

            # Create index for logs
            index_name = "kaizen_logs_test"
            if es_client.indices.exists(index=index_name):
                es_client.indices.delete(index=index_name)

            # Create index with mapping for trace_id
            es_client.indices.create(
                index=index_name,
                body={
                    "mappings": {
                        "properties": {
                            "timestamp": {"type": "date"},
                            "level": {"type": "keyword"},
                            "message": {"type": "text"},
                            "agent_id": {"type": "keyword"},
                            "trace_id": {"type": "keyword"},  # For filtering
                            "event_type": {"type": "keyword"},
                            "data": {
                                "type": "object",
                                "enabled": False,
                            },  # Store but don't index
                            "metadata": {"type": "object", "enabled": False},
                        }
                    }
                },
            )

            # Generate JSON logs with LoggingHook
            manager = HookManager()
            hook = LoggingHook(format="json")

            manager.register(HookEvent.PRE_AGENT_LOOP, hook)
            manager.register(HookEvent.PRE_TOOL_USE, hook)
            manager.register(HookEvent.POST_TOOL_USE, hook)
            manager.register(HookEvent.POST_AGENT_LOOP, hook)

            # Capture log output
            log_capture = StringIO()
            handler = logging.StreamHandler(log_capture)
            handler.setLevel(logging.INFO)

            logger = logging.getLogger(
                "kaizen.core.autonomy.hooks.builtin.logging_hook"
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

            try:
                # Generate logs with specific trace_id
                test_trace_id = str(uuid.uuid4())

                await manager.trigger(
                    event_type=HookEvent.PRE_AGENT_LOOP,
                    agent_id="elk_test_agent",
                    data={"iteration": 1, "task": "document_processing"},
                    trace_id=test_trace_id,
                )

                await manager.trigger(
                    event_type=HookEvent.PRE_TOOL_USE,
                    agent_id="elk_test_agent",
                    data={"tool_name": "document_reader", "file": "report.pdf"},
                    trace_id=test_trace_id,
                )

                await manager.trigger(
                    event_type=HookEvent.POST_TOOL_USE,
                    agent_id="elk_test_agent",
                    data={"result": "success", "pages": 10},
                    trace_id=test_trace_id,
                )

                await manager.trigger(
                    event_type=HookEvent.POST_AGENT_LOOP,
                    agent_id="elk_test_agent",
                    data={"status": "completed", "duration_ms": 1234.56},
                    trace_id=test_trace_id,
                )

                # Get log output
                log_output = log_capture.getvalue()
                log_lines = [line for line in log_output.strip().split("\n") if line]

                assert (
                    len(log_lines) >= 4
                ), f"Expected 4+ log lines, got {len(log_lines)}"

                # Parse and send logs to Elasticsearch
                for line in log_lines:
                    log_data = json.loads(line)

                    # Add @timestamp field for Elasticsearch
                    log_data["@timestamp"] = datetime.utcnow().isoformat()

                    # Index document
                    es_client.index(index=index_name, document=log_data)

                # Refresh index to make documents searchable
                es_client.indices.refresh(index=index_name)

                # Wait for indexing to complete
                time.sleep(2)

                # Query by trace_id
                search_response = es_client.search(
                    index=index_name,
                    body={"query": {"term": {"trace_id": test_trace_id}}},
                )

                # Verify results
                hits = search_response["hits"]["hits"]
                assert len(hits) >= 4, f"Expected 4+ documents, found {len(hits)}"

                # Verify all results have correct trace_id
                for hit in hits:
                    source = hit["_source"]
                    assert source["trace_id"] == test_trace_id
                    assert "timestamp" in source
                    assert "agent_id" in source
                    assert source["agent_id"] == "elk_test_agent"
                    assert "event_type" in source

                # Verify JSON schema compliance
                # Note: structlog uses 'event' field, not 'message'
                required_fields = [
                    "timestamp",
                    "level",
                    "event",  # structlog uses 'event', not 'message'
                    "agent_id",
                    "trace_id",
                    "event_type",
                ]
                for hit in hits:
                    source = hit["_source"]
                    for field in required_fields:
                        assert field in source, f"Missing required field: {field}"

                # Verify we can filter by event_type
                tool_search = es_client.search(
                    index=index_name,
                    body={
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"trace_id": test_trace_id}},
                                    {"term": {"event_type": "pre_tool_use"}},
                                ]
                            }
                        }
                    },
                )

                tool_hits = tool_search["hits"]["hits"]
                assert len(tool_hits) >= 1
                assert tool_hits[0]["_source"]["event_type"] == "pre_tool_use"

                # Verify timestamp format (ISO 8601)
                timestamp_str = hits[0]["_source"]["timestamp"]
                # Should be parseable as datetime
                datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))

            finally:
                logger.removeHandler(handler)

        finally:
            # Cleanup
            if es_container:
                try:
                    es_container.stop(timeout=10)
                except Exception:
                    pass


# ==============================================================================
# Category 2: Kibana Search (1 test - optional)
# ==============================================================================


class TestKibanaIntegration:
    """Test Kibana UI search by trace_id (optional test)"""

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.requires_docker
    @pytest.mark.skip(reason="Optional - requires Kibana container (slow startup)")
    @pytest.mark.asyncio
    async def test_kibana_search_by_trace_id(self):
        """
        Test 2.1: Kibana search by trace_id works via API.

        Requirement: Support operational log analysis via Kibana.
        Expected: Kibana can search and display logs filtered by trace_id.

        Setup:
        1. Start Elasticsearch container
        2. Start Kibana container (linked to ES)
        3. Generate logs
        4. Index logs in Elasticsearch
        5. Search via Kibana API
        6. Validate results

        Note: This test is optional due to Kibana's slow startup time (60s+).
        Skipped by default to keep test suite fast.
        """
        import requests

        import docker

        client = docker.from_env()

        # Start Elasticsearch
        es_container = None
        kibana_container = None

        try:
            # Start Elasticsearch first
            es_container = client.containers.run(
                "docker.elastic.co/elasticsearch/elasticsearch:8.11.0",
                name="kaizen_test_elasticsearch_kibana",
                detach=True,
                ports={"9200/tcp": 9200},
                environment={
                    "discovery.type": "single-node",
                    "xpack.security.enabled": "false",
                    "ES_JAVA_OPTS": "-Xms512m -Xmx512m",
                },
                remove=True,
            )

            # Wait for ES to be ready
            time.sleep(15)

            # Start Kibana
            kibana_container = client.containers.run(
                "docker.elastic.co/kibana/kibana:8.11.0",
                name="kaizen_test_kibana",
                detach=True,
                ports={"5601/tcp": 5601},
                environment={
                    "ELASTICSEARCH_HOSTS": "http://kaizen_test_elasticsearch_kibana:9200",
                    "xpack.security.enabled": "false",
                },
                links={"kaizen_test_elasticsearch_kibana": "elasticsearch"},
                remove=True,
            )

            # Wait for Kibana to be ready (can take 60+ seconds)
            max_wait = 120
            waited = 0
            kibana_ready = False

            while waited < max_wait:
                try:
                    response = requests.get(
                        "http://localhost:5601/api/status", timeout=5
                    )
                    if response.status_code == 200:
                        kibana_ready = True
                        break
                except Exception:
                    pass
                time.sleep(5)
                waited += 5

            if not kibana_ready:
                pytest.skip("Kibana failed to start within timeout")

            # Generate and index logs (similar to test 1.1)
            from elasticsearch import Elasticsearch

            es_client = Elasticsearch(["http://localhost:9200"])

            index_name = "kaizen_logs_kibana_test"
            es_client.indices.create(index=index_name)

            # Generate logs with trace_id
            test_trace_id = str(uuid.uuid4())

            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": "INFO",
                "message": "Test log for Kibana search",
                "agent_id": "kibana_test_agent",
                "trace_id": test_trace_id,
                "event_type": "pre_tool_use",
                "data": {"tool": "test"},
            }

            es_client.index(index=index_name, document=log_data)
            es_client.indices.refresh(index=index_name)

            # Search via Kibana API
            time.sleep(2)

            # Use Kibana's search API
            search_url = f"http://localhost:5601/api/console/proxy?path=/{index_name}/_search&method=GET"

            search_body = {"query": {"term": {"trace_id": test_trace_id}}}

            response = requests.post(
                search_url,
                json=search_body,
                headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
            )

            assert response.status_code == 200
            results = response.json()

            # Verify results
            hits = results["hits"]["hits"]
            assert len(hits) >= 1
            assert hits[0]["_source"]["trace_id"] == test_trace_id

        finally:
            # Cleanup containers
            if kibana_container:
                try:
                    kibana_container.stop(timeout=10)
                except Exception:
                    pass

            if es_container:
                try:
                    es_container.stop(timeout=10)
                except Exception:
                    pass
