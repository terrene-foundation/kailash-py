# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Self-contained HTML profiling report generator for DataExplorer.

Produces a single HTML file with inline CSS, inline JS, and embedded plotly
charts.  No external dependencies at render time (unless ``cdn=True``).

All user-provided content is escaped via :func:`html.escape` to prevent XSS.
"""
from __future__ import annotations

import html
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["generate_html_report"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_html_report(
    profile: Any,
    viz: Any,
    *,
    title: str = "Data Profile Report",
    cdn: bool = False,
) -> str:
    """Generate a self-contained HTML profiling report.

    Parameters
    ----------
    profile:
        A :class:`~kailash_ml.engines.data_explorer.DataProfile` instance.
    viz:
        A :class:`~kailash_ml.engines.data_explorer.VisualizationReport` instance.
    title:
        Page title shown in the browser tab and report header.
    cdn:
        If ``True``, load plotly.js from CDN (~3.5 MB savings).
        If ``False`` (default), embed the full plotly.js bundle for offline use.

    Returns
    -------
    str
        Complete, self-contained HTML document.
    """
    figures = viz.figures if viz and viz.figures else {}
    safe_title = html.escape(title)

    plotly_js = _plotly_js_block(cdn)
    nav = _build_nav(profile, figures)
    body = "\n".join(
        [
            _section_overview(profile),
            _section_alerts(profile),
            _section_variables(profile, figures),
            _section_correlations(profile, figures),
            _section_missing(profile),
            _section_sample(profile),
        ]
    )

    return _HTML_TEMPLATE.format(
        title=safe_title,
        plotly_js=plotly_js,
        css=_CSS,
        nav=nav,
        body=body,
    )


# ---------------------------------------------------------------------------
# Plotly JS embedding
# ---------------------------------------------------------------------------


def _plotly_js_block(cdn: bool) -> str:
    if cdn:
        return '<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>'
    try:
        import plotly

        js = plotly.offline.get_plotlyjs()
        return f"<script>{js}</script>"
    except Exception:
        logger.warning("plotly not available; charts will not render")
        return "<!-- plotly.js unavailable -->"


def _safe_uid(name: str) -> str:
    """Sanitize a column name into a safe HTML id."""
    import re

    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)[:80]


def _fig_to_div(fig: Any, uid: str) -> str:
    """Convert a plotly figure to an HTML div (no full page, no bundled JS)."""
    safe = _safe_uid(uid)
    try:
        return fig.to_html(full_html=False, include_plotlyjs=False, div_id=safe)
    except Exception:
        return (
            f'<div id="{html.escape(safe)}" class="chart-error">Chart unavailable</div>'
        )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

_SECTIONS = [
    ("overview", "Overview"),
    ("alerts", "Alerts"),
    ("variables", "Variables"),
    ("correlations", "Correlations"),
    ("missing", "Missing Values"),
    ("sample", "Sample"),
]


def _build_nav(profile: Any, figures: dict[str, Any]) -> str:
    items: list[str] = []
    for sid, label in _SECTIONS:
        if sid == "alerts" and not getattr(profile, "alerts", None):
            continue
        if (
            sid == "correlations"
            and not profile.correlation_matrix
            and not figures.get("correlation")
        ):
            continue
        items.append(f'<a href="#{sid}">{html.escape(label)}</a>')
    return "\n".join(items)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _section_overview(profile: Any) -> str:
    n_rows = profile.n_rows
    n_cols = profile.n_columns
    cols = profile.columns

    n_numeric = sum(1 for c in cols if c.mean is not None)
    n_categorical = sum(1 for c in cols if c.top_values is not None)
    n_other = n_cols - n_numeric - n_categorical
    total_nulls = sum(c.null_count for c in cols)
    total_cells = n_rows * n_cols if n_cols else 1
    null_pct = (total_nulls / total_cells * 100) if total_cells else 0
    dup_count = getattr(profile, "duplicate_count", None)

    rows = [
        ("Rows", f"{n_rows:,}"),
        ("Columns", f"{n_cols:,}"),
        ("Numeric columns", str(n_numeric)),
        ("Categorical columns", str(n_categorical)),
        ("Other columns", str(n_other)),
        ("Total missing cells", f"{total_nulls:,} ({null_pct:.1f}%)"),
    ]
    if dup_count is not None:
        rows.append(("Duplicate rows", f"{dup_count:,}"))

    profiled_at = getattr(profile, "profiled_at", "")
    if profiled_at:
        rows.append(("Profiled at", html.escape(str(profiled_at))))

    trs = "\n".join(
        f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in rows
    )
    return f"""
<section id="overview">
  <h2>Overview</h2>
  <table class="stats-table">{trs}</table>
</section>"""


def _section_alerts(profile: Any) -> str:
    alerts: list[dict[str, Any]] | None = getattr(profile, "alerts", None)
    if not alerts:
        return ""
    items: list[str] = []
    for alert in alerts:
        parts = [alert.get("type", "alert")]
        if "column" in alert:
            parts.append(f"column: {alert['column']}")
        if "columns" in alert:
            parts.append(f"columns: {', '.join(alert['columns'])}")
        val = alert.get("value")
        if isinstance(val, float):
            parts.append(f"value: {val:.2%}")
        elif val is not None:
            parts.append(f"value: {val}")
        msg = html.escape(" \u2014 ".join(parts))
        level = str(alert.get("severity", "info")).lower()
        css_cls = "alert-warning" if level == "warning" else "alert-info"
        items.append(f'<div class="alert {css_cls}">{msg}</div>')
    return f"""
<section id="alerts">
  <h2>Alerts</h2>
  {"".join(items)}
</section>"""


def _section_variables(profile: Any, figures: dict[str, Any]) -> str:
    cards: list[str] = []
    for col in profile.columns:
        name = html.escape(col.name)
        dtype = html.escape(col.dtype)
        is_numeric = col.mean is not None

        badge_cls = "badge-num" if is_numeric else "badge-cat"
        badge_label = "Numeric" if is_numeric else "Categorical"
        if not is_numeric and col.top_values is None:
            badge_label = "Other"
            badge_cls = "badge-other"

        stat_rows = [
            ("Count", f"{col.count:,}"),
            ("Missing", f"{col.null_count:,} ({col.null_pct:.1%})"),
            ("Distinct", f"{col.unique_count:,}"),
        ]
        if is_numeric:
            stat_rows += [
                ("Mean", _fmt(col.mean)),
                ("Std", _fmt(col.std)),
                ("Min", _fmt(col.min_val)),
                ("Q25", _fmt(col.q25)),
                ("Median", _fmt(col.q50)),
                ("Q75", _fmt(col.q75)),
                ("Max", _fmt(col.max_val)),
            ]
        elif col.top_values:
            for val, cnt in col.top_values[:5]:
                stat_rows.append((html.escape(str(val)), f"{cnt:,}"))

        trs = "\n".join(
            f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
            for k, v in stat_rows
        )

        chart_html = ""
        fig = figures.get(col.name)
        if fig is not None:
            chart_html = (
                f'<div class="chart-wrap">{_fig_to_div(fig, f"fig-{col.name}")}</div>'
            )

        cards.append(
            f"""
<div class="var-card">
  <div class="var-header">
    <h3>{name}</h3>
    <span class="badge {badge_cls}">{badge_label}</span>
    <span class="badge badge-dtype">{dtype}</span>
  </div>
  <div class="var-body">
    <table class="stats-table">{trs}</table>
    {chart_html}
  </div>
</div>"""
        )

    return f"""
<section id="variables">
  <h2>Variables</h2>
  {"".join(cards)}
</section>"""


def _section_correlations(profile: Any, figures: dict[str, Any]) -> str:
    parts: list[str] = []

    # Pearson (from viz figures)
    pearson_fig = figures.get("correlation")
    if pearson_fig is not None:
        parts.append(
            f'<div class="corr-panel"><h3>Pearson Correlation</h3>'
            f'{_fig_to_div(pearson_fig, "fig-corr-pearson")}</div>'
        )

    # Spearman (from profile if available)
    spearman = getattr(profile, "spearman_matrix", None)
    if spearman and pearson_fig is not None:
        parts.append(_matrix_table("Spearman Correlation", spearman))

    # Categorical associations (Cramer's V)
    cat_assoc = getattr(profile, "categorical_associations", None)
    if cat_assoc:
        parts.append(_matrix_table("Categorical Associations (Cramer's V)", cat_assoc))

    if not parts:
        return ""

    return f"""
<section id="correlations">
  <h2>Correlations</h2>
  <div class="corr-grid">{"".join(parts)}</div>
</section>"""


def _section_missing(profile: Any) -> str:
    cols = profile.columns
    has_missing = any(c.null_count > 0 for c in cols)
    patterns = profile.missing_patterns

    if not has_missing and not patterns:
        return ""

    # Bar chart: null percentage per column
    bars: list[str] = []
    for c in cols:
        pct = c.null_pct * 100
        color = "#4caf50" if pct == 0 else "#ff9800" if pct < 20 else "#f44336"
        name = html.escape(c.name)
        bars.append(
            f'<div class="miss-row">'
            f'<span class="miss-label">{name}</span>'
            f'<div class="miss-bar-bg"><div class="miss-bar" style="width:{min(pct, 100):.1f}%;background:{color}"></div></div>'
            f'<span class="miss-pct">{pct:.1f}%</span>'
            f"</div>"
        )

    pattern_html = ""
    if patterns:
        p_rows: list[str] = []
        for p in patterns:
            col_names = ", ".join(html.escape(str(c)) for c in p.get("columns", []))
            count = p.get("count", 0)
            p_rows.append(f"<tr><td>{col_names}</td><td>{count:,}</td></tr>")
        pattern_html = (
            "<h3>Missing Patterns (co-occurring nulls)</h3>"
            '<table class="stats-table"><tr><th>Columns</th><th>Count</th></tr>'
            f'{"".join(p_rows)}</table>'
        )

    return f"""
<section id="missing">
  <h2>Missing Values</h2>
  <div class="miss-chart">{"".join(bars)}</div>
  {pattern_html}
</section>"""


def _section_sample(profile: Any) -> str:
    head = getattr(profile, "sample_head", None)
    tail = getattr(profile, "sample_tail", None)
    if not head and not tail:
        return ""

    parts: list[str] = []
    if head:
        parts.append(f"<h3>Head</h3>{_df_table(head)}")
    if tail:
        parts.append(f"<h3>Tail</h3>{_df_table(tail)}")

    return f"""
<section id="sample">
  <h2>Sample Data</h2>
  {"".join(parts)}
</section>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt(v: float | None) -> str:
    if v is None:
        return "-"
    if abs(v) >= 1e6 or (0 < abs(v) < 0.001):
        return f"{v:.4e}"
    return f"{v:.4f}"


def _matrix_table(title: str, matrix: dict[str, dict[str, float | None]]) -> str:
    labels = list(matrix.keys())
    header = "".join(f"<th>{html.escape(l)}</th>" for l in labels)
    rows: list[str] = []
    for r in labels:
        cells_list: list[str] = []
        for c in labels:
            val = matrix[r].get(c)
            bg = _corr_color(val)
            if val is None:
                cell_text = "N/A"
                tooltip = (
                    ' title="Correlation undefined (constant or insufficient data)"'
                )
            else:
                cell_text = f"{val:.2f}"
                tooltip = ""
            cells_list.append(f'<td style="background:{bg}"{tooltip}>{cell_text}</td>')
        rows.append(f"<tr><th>{html.escape(r)}</th>{''.join(cells_list)}</tr>")
    return (
        f'<div class="corr-panel"><h3>{html.escape(title)}</h3>'
        f'<table class="corr-table"><tr><th></th>{header}</tr>'
        f'{"".join(rows)}</table></div>'
    )


def _corr_color(v: float | None) -> str:
    """Map correlation [-1, 1] to a background colour."""
    import math

    if v is None or not math.isfinite(v):
        return "rgba(128,128,128,0.2)"
    if v >= 0:
        intensity = int(min(v, 1.0) * 180)
        return f"rgba(33,150,243,{intensity / 255:.2f})"
    intensity = int(min(abs(v), 1.0) * 180)
    return f"rgba(244,67,54,{intensity / 255:.2f})"


def _df_table(data: list[dict[str, Any]] | Any) -> str:
    """Render a list-of-dicts (or polars DataFrame) as an HTML table."""
    rows: list[dict[str, Any]]
    try:
        if isinstance(data, list):
            rows = data
        elif hasattr(data, "to_dicts"):
            rows = data.to_dicts()  # type: ignore[union-attr]
        else:
            rows = list(data)
    except Exception:
        return "<p>Sample data unavailable.</p>"

    if not rows:
        return "<p>No rows.</p>"

    cols = list(rows[0].keys())
    header = "".join(f"<th>{html.escape(str(c))}</th>" for c in cols)
    body_rows: list[str] = []
    for row in rows[:20]:
        cells = "".join(f"<td>{html.escape(str(row.get(c, '')))}</td>" for c in cols)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        f'<table class="stats-table"><tr>{header}</tr>' f'{"".join(body_rows)}</table>'
    )


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#fff;--fg:#1a1a2e;--card:#f8f9fa;--border:#dee2e6;--accent:#2196f3;
--warn:#f44336;--info:#ff9800;--ok:#4caf50;--sidebar:250px;--font:-apple-system,
BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
@media(prefers-color-scheme:dark){:root{--bg:#1a1a2e;--fg:#e0e0e0;--card:#16213e;
--border:#374151;--accent:#64b5f6;--warn:#ef5350;--info:#ffb74d;--ok:#66bb6a}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:var(--font);background:var(--bg);color:var(--fg);display:flex;min-height:100vh}
nav{position:sticky;top:0;height:100vh;width:var(--sidebar);min-width:var(--sidebar);
background:var(--card);border-right:1px solid var(--border);padding:1rem 0;overflow-y:auto}
nav a{display:block;padding:.6rem 1.2rem;color:var(--fg);text-decoration:none;font-size:.9rem}
nav a:hover{background:var(--accent);color:#fff;border-radius:0 4px 4px 0}
main{flex:1;padding:2rem 2.5rem;max-width:1200px;overflow-x:auto}
h1{font-size:1.6rem;margin-bottom:1.5rem;border-bottom:2px solid var(--accent);padding-bottom:.5rem}
h2{font-size:1.3rem;margin:2rem 0 1rem;padding-bottom:.3rem;border-bottom:1px solid var(--border)}
h3{font-size:1.05rem;margin:1rem 0 .5rem}
section{margin-bottom:2rem}
.stats-table{border-collapse:collapse;width:100%;margin:.5rem 0}
.stats-table th,.stats-table td{text-align:left;padding:.4rem .7rem;border-bottom:1px solid var(--border);font-size:.88rem}
.stats-table tr:hover{background:var(--card)}
.var-card{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:1rem;margin-bottom:1rem}
.var-header{display:flex;align-items:center;gap:.6rem;margin-bottom:.6rem}
.var-header h3{margin:0}
.var-body{display:flex;gap:1.5rem;flex-wrap:wrap}
.var-body .stats-table{flex:0 0 320px;max-width:400px}
.chart-wrap{flex:1;min-width:300px}
.badge{font-size:.72rem;padding:.2rem .5rem;border-radius:3px;font-weight:600;text-transform:uppercase}
.badge-num{background:#e3f2fd;color:#1565c0}.badge-cat{background:#fce4ec;color:#c62828}
.badge-other{background:#f3e5f5;color:#6a1b9a}.badge-dtype{background:var(--border);color:var(--fg)}
@media(prefers-color-scheme:dark){.badge-num{background:#0d47a1;color:#bbdefb}
.badge-cat{background:#b71c1c;color:#ffcdd2}.badge-other{background:#4a148c;color:#e1bee7}}
.alert{padding:.7rem 1rem;border-radius:4px;margin-bottom:.5rem;font-size:.9rem}
.alert-warning{background:#ffebee;color:#c62828;border-left:4px solid var(--warn)}
.alert-info{background:#fff8e1;color:#e65100;border-left:4px solid var(--info)}
@media(prefers-color-scheme:dark){.alert-warning{background:#4a1010;color:#ef9a9a}
.alert-info{background:#4a3000;color:#ffe0b2}}
.corr-grid{display:flex;gap:1.5rem;flex-wrap:wrap}
.corr-panel{flex:1;min-width:320px}
.corr-table{border-collapse:collapse;font-size:.8rem}
.corr-table th,.corr-table td{padding:.3rem .5rem;border:1px solid var(--border);text-align:center}
.miss-chart{margin:.5rem 0}
.miss-row{display:flex;align-items:center;gap:.5rem;margin-bottom:.25rem;font-size:.88rem}
.miss-label{width:160px;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.miss-bar-bg{flex:1;height:16px;background:var(--border);border-radius:3px;overflow:hidden}
.miss-bar{height:100%;border-radius:3px}
.miss-pct{width:55px;text-align:right;font-size:.82rem}
.chart-error{padding:1rem;color:var(--info);font-style:italic}
@media(max-width:768px){nav{display:none}main{padding:1rem}
.var-body{flex-direction:column}.var-body .stats-table{max-width:100%}}
"""

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
{plotly_js}
<style>{css}</style>
</head>
<body>
<nav>{nav}</nav>
<main>
<h1>{title}</h1>
{body}
</main>
</body>
</html>"""
