"""WebSocket-powered live dashboard for workflow monitoring.

Unlike the page-reload approach in :mod:`kailash.visualization.dashboard`,
this module generates a dashboard page that uses a WebSocket connection to
receive real-time metric updates without full page reloads.

The generated HTML connects to ``/api/v1/metrics/ws`` and updates the DOM
on every incoming message.  It can be served as a static file or mounted
on a :class:`~kailash.servers.workflow_server.WorkflowServer` at
``/dashboard``.

Usage::

    from kailash.visualization.live_dashboard import LiveDashboard

    live = LiveDashboard(ws_url="ws://localhost:8000/api/v1/metrics/ws")
    html = live.render()

    # Or write to file:
    live.write("dashboard.html")
"""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["LiveDashboard"]


class LiveDashboard:
    """Generates an HTML dashboard page with WebSocket-driven live updates.

    Args:
        ws_url: WebSocket endpoint URL.  Defaults to a relative URL that
            auto-detects the host from ``window.location``.
        title: Page title.
        theme: ``"light"`` or ``"dark"``.
        reconnect_interval_ms: Milliseconds between reconnect attempts
            if the WebSocket connection drops.
    """

    def __init__(
        self,
        ws_url: Optional[str] = None,
        title: str = "Kailash Live Dashboard",
        theme: str = "light",
        reconnect_interval_ms: int = 3000,
    ) -> None:
        self.ws_url = ws_url
        self.title = title
        self.theme = theme
        self.reconnect_interval_ms = reconnect_interval_ms

    def render(self) -> str:
        """Return the full HTML page as a string."""
        colors = _THEME_COLORS.get(self.theme, _THEME_COLORS["light"])

        # If no explicit ws_url, derive from the page's own location
        if self.ws_url:
            ws_url_js = f'"{self.ws_url}"'
        else:
            ws_url_js = (
                '((window.location.protocol === "https:" ? "wss:" : "ws:") '
                '+ "//" + window.location.host + "/api/v1/metrics/ws")'
            )

        return _HTML_TEMPLATE.format(
            title=self.title,
            bg=colors["bg"],
            card_bg=colors["card_bg"],
            text=colors["text"],
            border=colors["border"],
            primary=colors["primary"],
            success=colors["success"],
            danger=colors["danger"],
            warning=colors["warning"],
            ws_url_js=ws_url_js,
            reconnect_interval_ms=self.reconnect_interval_ms,
        )

    def write(self, path: str | Path) -> Path:
        """Write the rendered HTML to *path*.

        Parent directories are created automatically.

        Returns:
            Resolved :class:`Path` of the written file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        logger.info("Live dashboard written to %s", path)
        return path.resolve()


# ---------------------------------------------------------------------------
# Theme colours
# ---------------------------------------------------------------------------
_THEME_COLORS = {
    "light": {
        "bg": "#f8f9fa",
        "card_bg": "#ffffff",
        "text": "#333333",
        "border": "#e9ecef",
        "primary": "#007bff",
        "success": "#28a745",
        "danger": "#dc3545",
        "warning": "#ffc107",
    },
    "dark": {
        "bg": "#121212",
        "card_bg": "#1e1e1e",
        "text": "#ffffff",
        "border": "#333333",
        "primary": "#1976d2",
        "success": "#4caf50",
        "danger": "#f44336",
        "warning": "#ff9800",
    },
}

# ---------------------------------------------------------------------------
# HTML template (Python str.format placeholders use doubled braces for
# literal JS braces)
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: {bg}; color: {text}; line-height: 1.6;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
    header {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 20px; background: {card_bg}; border-radius: 8px;
      border: 1px solid {border}; margin-bottom: 24px;
    }}
    header h1 {{ color: {primary}; font-size: 1.6em; }}
    #ws-status {{ font-weight: bold; }}
    .connected {{ color: {success}; }}
    .disconnected {{ color: {danger}; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px; margin-bottom: 24px;
    }}
    .card {{
      text-align: center; padding: 20px; background: {card_bg};
      border-radius: 8px; border: 1px solid {border};
    }}
    .card .value {{ display: block; font-size: 2em; font-weight: bold; color: {primary}; }}
    .card .label {{ display: block; font-size: 0.85em; opacity: 0.8; }}
    section {{
      padding: 20px; background: {card_bg}; border-radius: 8px;
      border: 1px solid {border}; margin-bottom: 24px;
    }}
    section h2 {{ margin-bottom: 12px; color: {primary}; }}
    #log {{
      max-height: 300px; overflow-y: auto; font-family: monospace;
      font-size: 0.85em; padding: 8px; background: {bg};
      border-radius: 4px; border: 1px solid {border};
    }}
    #log div {{ padding: 2px 0; border-bottom: 1px solid {border}; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{title}</h1>
      <span id="ws-status" class="disconnected">Disconnected</span>
    </header>

    <div class="grid">
      <div class="card"><span class="value" id="active">--</span><span class="label">Active Tasks</span></div>
      <div class="card"><span class="value" id="completed">--</span><span class="label">Completed</span></div>
      <div class="card"><span class="value" id="failed">--</span><span class="label">Failed</span></div>
      <div class="card"><span class="value" id="throughput">--</span><span class="label">Tasks/Min</span></div>
      <div class="card"><span class="value" id="cpu">--</span><span class="label">Avg CPU</span></div>
      <div class="card"><span class="value" id="memory">--</span><span class="label">Memory MB</span></div>
    </div>

    <section>
      <h2>Event Log</h2>
      <div id="log"></div>
    </section>
  </div>

  <script>
    (function() {{
      var wsUrl = {ws_url_js};
      var reconnectMs = {reconnect_interval_ms};
      var ws;
      var logEl = document.getElementById("log");
      var statusEl = document.getElementById("ws-status");
      var MAX_LOG = 200;

      function connect() {{
        ws = new WebSocket(wsUrl);
        ws.onopen = function() {{
          statusEl.textContent = "Connected";
          statusEl.className = "connected";
          addLog("WebSocket connected");
        }};
        ws.onclose = function() {{
          statusEl.textContent = "Disconnected";
          statusEl.className = "disconnected";
          addLog("WebSocket disconnected -- reconnecting in " + reconnectMs + "ms");
          setTimeout(connect, reconnectMs);
        }};
        ws.onerror = function(e) {{
          addLog("WebSocket error");
        }};
        ws.onmessage = function(evt) {{
          var data = JSON.parse(evt.data);
          if (data.type === "metrics" || data.active_tasks !== undefined) {{
            document.getElementById("active").textContent = data.active_tasks;
            document.getElementById("completed").textContent = data.completed_tasks;
            document.getElementById("failed").textContent = data.failed_tasks;
            document.getElementById("throughput").textContent =
              (data.throughput != null ? data.throughput.toFixed(1) : "--");
            document.getElementById("cpu").textContent =
              (data.total_cpu_usage != null ? data.total_cpu_usage.toFixed(1) + "%" : "--");
            document.getElementById("memory").textContent =
              (data.total_memory_usage != null ? data.total_memory_usage.toFixed(0) : "--");
            addLog("Update: " + data.active_tasks + " active, "
                    + data.completed_tasks + " completed, "
                    + data.failed_tasks + " failed");
          }}
        }};
      }}

      function addLog(msg) {{
        var d = document.createElement("div");
        d.textContent = new Date().toLocaleTimeString() + "  " + msg;
        logEl.prepend(d);
        while (logEl.children.length > MAX_LOG) {{
          logEl.removeChild(logEl.lastChild);
        }}
      }}

      connect();
    }})();
  </script>
</body>
</html>
"""
