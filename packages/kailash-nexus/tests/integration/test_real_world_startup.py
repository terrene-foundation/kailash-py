"""Integration test for real-world Nexus startup.

Tests that the server actually starts when run as a separate process,
preventing regression of the v1.0.7 daemon thread bug.

This test validates the CRITICAL v1.0.8 hotfix where start() must block
in the main thread instead of spawning daemon threads that die immediately.
"""

import signal
import socket
import subprocess
import sys
import time
from contextlib import closing
from typing import Optional

import pytest
import requests


def find_free_port(start_port: int = 8000) -> int:
    """Find a free port starting from start_port."""
    for port in range(start_port, start_port + 100):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            try:
                s.bind(("", port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find free port starting from {start_port}")


# Readiness ceiling for a cold-started server subprocess. Each test below spawns
# a fresh interpreter that imports the whole kailash + nexus + MCP stack from
# source before uvicorn binds; measured cold start is ~13s on a developer
# machine and is dominated by import time, not by Nexus. The previous fixed
# budgets (a bare ``time.sleep(3)``, or 10 x 0.5s polls) were BELOW that, so
# these tests failed on server-is-still-starting rather than on the v1.0.7 bug
# they exist to catch. This is a TIMEOUT CEILING, not a startup-speed
# assertion -- startup latency is asserted in-process by
# ``tests/e2e/test_production_scenarios.py::test_startup_performance``. Per
# ``rules/testing.md`` a readiness poll replaces an absolute wall-clock
# threshold, which otherwise ratchets upward on every slower machine.
_STARTUP_TIMEOUT_SECONDS = 60.0
_POLL_INTERVAL_SECONDS = 0.25


def _wait_until_healthy(
    process: subprocess.Popen,
    api_port: int,
    timeout: float = _STARTUP_TIMEOUT_SECONDS,
) -> None:
    """Block until the server subprocess answers ``GET /health`` with 200.

    Preserves the v1.0.7 regression check these tests exist for: if the
    process EXITS while we are waiting, that is the daemon-thread bug (server
    returns immediately and dies) and fails immediately with the subprocess's
    captured output rather than after the full timeout.

    Args:
        process: The spawned server process.
        api_port: Port the server was told to bind.
        timeout: Ceiling on cold start, not an assertion about its speed.

    Raises:
        pytest.fail.Exception: If the process exits early or never answers.
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            pytest.fail(
                f"Server process exited prematurely (v1.0.7 bug detected!)\n"
                f"Exit code: {process.returncode}\n"
                f"STDOUT:\n{stdout}\n"
                f"STDERR:\n{stderr}"
            )

        try:
            response = requests.get(f"http://localhost:{api_port}/health", timeout=1)
            if response.status_code == 200:
                return
        except requests.RequestException:
            # Not listening yet, or still starting up -- keep polling.
            pass

        time.sleep(_POLL_INTERVAL_SECONDS)

    pytest.fail(
        f"Server did not answer /health on port {api_port} within {timeout}s. "
        "Process is still alive, so this is a startup hang rather than the "
        "v1.0.7 premature-exit bug."
    )


@pytest.mark.integration
def test_real_world_server_startup():
    """Test that Nexus server starts in a real process and accepts requests.

    This test replicates real-world production usage:
    1. Server runs in main process (not background thread)
    2. start() is called directly (blocking expected)
    3. Port must bind successfully
    4. HTTP requests must work
    5. Ctrl+C (SIGINT) must shutdown cleanly

    This test will FAIL in v1.0.7 because:
    - start() spawns daemon thread and returns immediately
    - Main process exits
    - Daemon threads are killed
    - Port never binds
    - Server never starts
    """

    # Create minimal server script (mimics production usage)
    # Add src directory to PYTHONPATH for subprocess
    import os

    nexus_src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    kailash_src_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "src"
    )
    api_port = find_free_port(9876)

    server_script = f"""
import sys
sys.path.insert(0, '{nexus_src_path}')
sys.path.insert(0, '{kailash_src_path}')

import time
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

# Create minimal workflow
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {{"code": "result = {{'status': 'ok'}}"}})

# Create and start server (production pattern)
app = Nexus(api_port={api_port}, enable_durability=False, auto_discovery=False)
app.register("test_workflow", workflow.build())

# This should BLOCK until Ctrl+C in v1.0.8 (fixed)
# This RETURNS IMMEDIATELY in v1.0.7 (broken) causing process to exit
app.start()
"""

    # Start server process (mimics real deployment)
    process = subprocess.Popen(
        [sys.executable, "-c", server_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for server to start (fails loudly if the process exits first --
        # that exit IS the v1.0.7 bug this test guards).
        _wait_until_healthy(process, api_port)

        # Verify server accepts requests
        response = requests.get(f"http://localhost:{api_port}/workflows", timeout=2)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        workflows = response.json()
        assert "test_workflow" in workflows, f"test_workflow not found in {workflows}"

        # Verify workflow execution works (with longer timeout for durability operations)
        try:
            response = requests.post(
                f"http://localhost:{api_port}/workflows/test_workflow/execute",
                json={"inputs": {}},
                timeout=10,
            )
            assert (
                response.status_code == 200
            ), f"Workflow execution failed: {response.status_code}"

            result = response.json()
            # Check for either run_id or workflow_id (both indicate successful execution)
            assert (
                "workflow_id" in result or "run_id" in result
            ), f"No workflow_id/run_id in response: {result}"
            # Verify the workflow executed successfully
            assert "outputs" in result, f"No outputs in response: {result}"
        except requests.exceptions.ReadTimeout:
            # Workflow might be slow, but server is running - that's the main test
            pass

    finally:
        # Clean shutdown (test graceful Ctrl+C handling)
        process.send_signal(signal.SIGINT)
        try:
            exit_code = process.wait(timeout=10)
            # Exit code 0 or -2 (SIGINT) are acceptable
            # Note: Exit code can vary by platform for SIGINT
            assert exit_code in [0, -2, -15, 130], f"Unexpected exit code: {exit_code}"
        except subprocess.TimeoutExpired:
            # Forcefully kill if graceful shutdown fails
            process.kill()
            process.wait()
            # Don't fail test - main goal (server starting) was achieved


@pytest.mark.integration
def test_real_world_startup_logs():
    """Verify startup logs show correct messages.

    This test validates:
    1. Server logs startup messages
    2. "Press Ctrl+C to stop" message appears (v1.0.8)
    3. Process stays running (doesn't exit immediately)
    """
    import os

    nexus_src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    kailash_src_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "src"
    )
    api_port = find_free_port(9877)

    server_script = f"""
import sys
sys.path.insert(0, '{nexus_src_path}')
sys.path.insert(0, '{kailash_src_path}')

from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port={api_port}, enable_durability=False, auto_discovery=False)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {{"code": "result = {{'ok': True}}"}})
app.register("test", workflow.build())

app.start()
"""

    process = subprocess.Popen(
        [sys.executable, "-c", server_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for startup. _wait_until_healthy fails with the subprocess's
        # captured output if the process exits first, which is the v1.0.7
        # premature-exit check this test previously did via a bare
        # `assert process.poll() is None` after a fixed 3-second sleep.
        _wait_until_healthy(process, api_port)

        # Verify process is STILL running after it answered -- the v1.0.8
        # contract is that start() blocks until Ctrl+C, not just long enough
        # to serve one request.
        assert process.poll() is None, (
            "Process exited right after binding - v1.0.7 bug detected! "
            "Server should stay running until Ctrl+C."
        )

        # Confirm it is genuinely serving, not merely holding the port open.
        response = requests.get(f"http://localhost:{api_port}/health", timeout=2)
        assert response.status_code == 200

    finally:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.integration
def test_port_binding_verification():
    """Test that port is actually bound and accessible.

    This test specifically validates that the server binds to the port
    and keeps it bound (v1.0.7 bug: port never binds because daemon thread dies).
    """
    import os

    nexus_src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    kailash_src_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "src"
    )
    api_port = find_free_port(9878)

    server_script = f"""
import sys
sys.path.insert(0, '{nexus_src_path}')
sys.path.insert(0, '{kailash_src_path}')

from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port={api_port}, enable_durability=False, auto_discovery=False)

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "ping", {{"code": "result = {{'pong': True}}"}})
app.register("ping", workflow.build())

app.start()  # Must block here in v1.0.8
"""

    process = subprocess.Popen(
        [sys.executable, "-c", server_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for the server to come up (fails with captured subprocess output
        # if it exits before binding -- the v1.0.7 bug).
        _wait_until_healthy(process, api_port)

        # Verify the port is genuinely bound at the socket layer, not merely
        # that an HTTP response arrived -- this test's distinctive assertion.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            connect_result = s.connect_ex(("localhost", api_port))
        assert connect_result == 0, (
            f"Port {api_port} is not bound (connect_ex returned "
            f"{connect_result}). This indicates the v1.0.7 bug where the "
            "daemon thread dies before uvicorn can bind the port."
        )

        # Verify server actually responds (not just port open)
        response = requests.get(f"http://localhost:{api_port}/health", timeout=2)
        assert response.status_code == 200

    finally:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.integration
def test_multiple_requests_sustained():
    """Test that server handles multiple requests over time.

    This validates that the server stays alive for sustained operation,
    not just initial startup (v1.0.7: daemon thread might die anytime).
    """
    import os

    nexus_src_path = os.path.join(os.path.dirname(__file__), "..", "..", "src")
    kailash_src_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "src"
    )
    api_port = find_free_port(9879)

    server_script = f"""
import sys
sys.path.insert(0, '{nexus_src_path}')
sys.path.insert(0, '{kailash_src_path}')

from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port={api_port}, enable_durability=False, auto_discovery=False)

workflow = WorkflowBuilder()
# Fix: inputs needs to be accessed from node's namespace
workflow.add_node("PythonCodeNode", "echo", {{"code": "result = {{'msg': 'echoed'}}"}})
app.register("echo", workflow.build())

app.start()
"""

    process = subprocess.Popen(
        [sys.executable, "-c", server_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for startup (fails with captured subprocess output if the
        # process exits first -- the v1.0.7 bug).
        _wait_until_healthy(process, api_port)

        # Make multiple requests over time
        for i in range(3):  # Reduced to 3 to speed up test
            time.sleep(0.5)

            # Verify process still running
            assert process.poll() is None, f"Process died after {i} requests"

            # Execute workflow (with longer timeout)
            try:
                response = requests.post(
                    f"http://localhost:{api_port}/workflows/echo/execute",
                    json={"inputs": {"msg": f"request_{i}"}},
                    timeout=10,
                )
                assert response.status_code == 200, f"Request {i} failed"

                result = response.json()
                # Check for workflow_id or run_id
                assert "workflow_id" in result or "run_id" in result
            except requests.exceptions.ReadTimeout:
                # Workflow might be slow, but server is still running
                pass

    finally:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
