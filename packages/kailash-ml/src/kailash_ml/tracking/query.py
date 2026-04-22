# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""W13 — Query primitives for ``ExperimentTracker``.

Implements ``specs/ml-tracking.md`` §5:

- §5.1 polars-DataFrame returns for ``list_runs`` / ``search_runs`` /
  ``list_experiments`` / ``list_metrics`` / ``list_artifacts`` (spec
  violation: legacy ``search_runs`` returned ``list[Run]``).
- §5.2 MLflow-compatible filter DSL (``metrics.<name> <op> <value>``
  / ``params.<name>`` / ``tags.<name>`` / ``attributes.<name>`` /
  ``env.<name>``) — parsed into safe SQL with parameterised values so
  injection is structurally impossible.
- §5.3 ``diff_runs(run_a, run_b) -> RunDiff`` frozen dataclass with
  ``reproducibility_risk`` typed bool.

Parsing invariants:

- Identifiers on both sides of the dot MUST match the same key regex
  W12 uses for metric / param / tag keys — the regex is the single
  enforcement point for "no injection via identifier".
- Column names reachable via ``attributes.<name>`` / ``env.<name>``
  come from a static allowlist, NEVER interpolated from user input.
- Values are always bound as SQL parameters — never interpolated.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "EnvDelta",
    "FilterParseError",
    "MetricDelta",
    "ParamDelta",
    "RunDiff",
    "RunRecord",
    "build_search_sql",
]


# ---------------------------------------------------------------------------
# Public value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunRecord:
    """Immutable snapshot of a run row returned by :meth:`get_run`.

    Spec §5.1: ``get_run`` returns a ``RunRecord`` (typed), not a
    ``dict``. Callers convert to dict explicitly when the MCP surface
    needs JSON (spec §11.2).
    """

    run_id: str
    experiment: str
    status: str
    tenant_id: Optional[str]
    parent_run_id: Optional[str]
    wall_clock_start: Optional[str]
    wall_clock_end: Optional[str]
    duration_seconds: Optional[float]
    params: Dict[str, Any]
    environment: Dict[str, Any]
    error_type: Optional[str]
    error_message: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        """Serialise to a plain ``dict`` for JSON emission."""
        return {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "status": self.status,
            "tenant_id": self.tenant_id,
            "parent_run_id": self.parent_run_id,
            "wall_clock_start": self.wall_clock_start,
            "wall_clock_end": self.wall_clock_end,
            "duration_seconds": self.duration_seconds,
            "params": dict(self.params),
            "environment": dict(self.environment),
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class ParamDelta:
    key: str
    value_a: Any
    value_b: Any
    changed: bool


@dataclass(frozen=True)
class MetricDelta:
    key: str
    value_a: Optional[float]
    value_b: Optional[float]
    delta: Optional[float]
    pct_change: Optional[float]
    per_step: Optional[Any] = None  # polars.DataFrame when both runs logged steps


@dataclass(frozen=True)
class EnvDelta:
    key: str
    value_a: Any
    value_b: Any
    changed: bool


@dataclass(frozen=True)
class RunDiff:
    run_id_a: str
    run_id_b: str
    params: Dict[str, ParamDelta]
    metrics: Dict[str, MetricDelta]
    environment: Dict[str, EnvDelta]
    reproducibility_risk: bool
    summary: str


class FilterParseError(ValueError):
    """Raised when a filter DSL string fails to parse.

    Per spec §5.2: ``search_runs`` MUST raise ``ValueError("invalid
    filter: …")`` on parse failure — silent accept-anything is BLOCKED.
    """


# ---------------------------------------------------------------------------
# Filter DSL parser
# ---------------------------------------------------------------------------

#: Same shape as ``runner._KEY_REGEX`` — identifiers are the union of
#: metric / param / tag key regexes. We validate at parse time so the
#: SQL emitter can safely interpolate the name into a JSON-extract path
#: (``$."<name>"``) without additional escaping.
_IDENT_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.\-]*$")

#: Allowlist of run-row columns reachable via ``attributes.<name>`` or
#: ``env.<name>``. Missing keys → :class:`FilterParseError`. The list is
#: a SUBSET of the schema columns — callers can't query every row field
#: (``git_dirty`` is boolean-as-int; users should use the typed tag).
_RUN_COLUMN_ALLOWLIST: frozenset = frozenset(
    {
        "status",
        "experiment",
        "tenant_id",
        "parent_run_id",
        "host",
        "python_version",
        "kailash_ml_version",
        "lightning_version",
        "torch_version",
        "cuda_version",
        "git_sha",
        "git_branch",
        "device_used",
        "accelerator",
        "precision",
        "device_family",
        "device_backend",
        "duration_seconds",
        "wall_clock_start",
        "wall_clock_end",
    }
)

_COMPARISON_OPS = {"=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"}

#: Columns that the diff's environment block compares. Frozen so a
#: diff-audit is deterministic — changing this set is a spec edit.
_ENV_DIFF_COLUMNS: Tuple[str, ...] = (
    "python_version",
    "kailash_ml_version",
    "lightning_version",
    "torch_version",
    "cuda_version",
    "git_sha",
    "git_branch",
    "host",
    "accelerator",
    "precision",
)


@dataclass
class _Token:
    kind: str  # "ident" | "op" | "number" | "string" | "lparen" | "rparen" | "comma" | "and" | "or" | "dot"
    value: Any


def _tokenize(source: str) -> List[_Token]:
    """Tokenise the DSL source.

    Raises :class:`FilterParseError` on any invalid character.
    """
    tokens: List[_Token] = []
    i, n = 0, len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
            continue
        if c == ".":
            tokens.append(_Token("dot", "."))
            i += 1
            continue
        if c == "(":
            tokens.append(_Token("lparen", "("))
            i += 1
            continue
        if c == ")":
            tokens.append(_Token("rparen", ")"))
            i += 1
            continue
        if c == ",":
            tokens.append(_Token("comma", ","))
            i += 1
            continue
        if c == "'":
            j = i + 1
            buf: List[str] = []
            while j < n and source[j] != "'":
                # Escaped single quote: ''
                if source[j] == "\\" and j + 1 < n:
                    buf.append(source[j + 1])
                    j += 2
                    continue
                buf.append(source[j])
                j += 1
            if j >= n:
                raise FilterParseError(
                    f"invalid filter: unterminated string literal at offset {i}"
                )
            tokens.append(_Token("string", "".join(buf)))
            i = j + 1
            continue
        if c in "=<>!":
            if c == "!" and i + 1 < n and source[i + 1] == "=":
                tokens.append(_Token("op", "!="))
                i += 2
                continue
            if c in "<>" and i + 1 < n and source[i + 1] == "=":
                tokens.append(_Token("op", f"{c}="))
                i += 2
                continue
            if c == "=":
                tokens.append(_Token("op", "="))
                i += 1
                continue
            if c in "<>":
                tokens.append(_Token("op", c))
                i += 1
                continue
            raise FilterParseError(
                f"invalid filter: unexpected character {c!r} at offset {i}"
            )
        if c.isdigit() or (c == "-" and i + 1 < n and source[i + 1].isdigit()):
            j = i + 1
            while j < n and (source[j].isdigit() or source[j] in ".eE+-"):
                j += 1
            literal = source[i:j]
            try:
                if "." in literal or "e" in literal or "E" in literal:
                    value: Any = float(literal)
                else:
                    value = int(literal)
            except ValueError as exc:
                raise FilterParseError(
                    f"invalid filter: bad number {literal!r} at offset {i}"
                ) from exc
            tokens.append(_Token("number", value))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            # Identifiers do NOT consume '.' — dots are their own token
            # so ``metrics.val.loss`` tokenises as
            # ident / dot / ident / dot / ident. The parser glues the
            # name-side idents back together per spec §5.2.
            while j < n and (
                source[j].isalnum() or source[j] == "_" or source[j] == "-"
            ):
                j += 1
            word = source[i:j]
            upper = word.upper()
            if upper in {"AND", "OR"}:
                tokens.append(_Token(upper.lower(), upper))
            elif upper in {"LIKE", "IN"}:
                tokens.append(_Token("op", upper))
            else:
                tokens.append(_Token("ident", word))
            i = j
            continue
        raise FilterParseError(
            f"invalid filter: unexpected character {c!r} at offset {i}"
        )
    return tokens


class _Parser:
    def __init__(self, tokens: List[_Token]) -> None:
        self._tokens = tokens
        self._pos = 0
        self._where_fragments: List[str] = []
        self._bind_params: List[Any] = []

    def _peek(self, offset: int = 0) -> Optional[_Token]:
        idx = self._pos + offset
        return self._tokens[idx] if idx < len(self._tokens) else None

    def _advance(self) -> _Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, kind: str) -> _Token:
        tok = self._peek()
        if tok is None or tok.kind != kind:
            raise FilterParseError(
                f"invalid filter: expected {kind}, got "
                f"{tok.kind if tok else 'end-of-input'}"
            )
        return self._advance()

    def parse(self) -> Tuple[str, List[Any]]:
        self._parse_filter()
        if self._pos != len(self._tokens):
            tok = self._tokens[self._pos]
            raise FilterParseError(
                f"invalid filter: unexpected token {tok.value!r} after expression"
            )
        where = " ".join(self._where_fragments)
        return where, list(self._bind_params)

    def _parse_filter(self) -> None:
        self._parse_term()
        while True:
            tok = self._peek()
            if tok is None or tok.kind not in ("and", "or"):
                break
            glue = self._advance().value  # "AND" / "OR"
            self._where_fragments.append(glue)
            self._parse_term()

    def _parse_term(self) -> None:
        prefix_tok = self._expect("ident")
        prefix = prefix_tok.value.lower()
        if prefix not in {"metrics", "params", "tags", "attributes", "env"}:
            raise FilterParseError(
                f"invalid filter: unknown prefix {prefix!r}; "
                f"allowed: metrics, params, tags, attributes, env"
            )
        self._expect("dot")
        # Glue dotted name fragments back together per spec §5.2 — the
        # tokenizer splits ``val.loss`` into ident/dot/ident so we
        # reassemble greedily while the next token pair is dot + ident.
        name_tok = self._expect("ident")
        name_parts: List[str] = [name_tok.value]
        while True:
            nxt = self._peek()
            after = self._peek(1)
            if (
                nxt is not None
                and nxt.kind == "dot"
                and after is not None
                and after.kind == "ident"
            ):
                self._advance()  # consume dot
                name_parts.append(self._advance().value)
                continue
            break
        name = ".".join(name_parts)
        if not _IDENT_REGEX.match(name):
            raise FilterParseError(
                f"invalid filter: identifier {name!r} failed regex validation"
            )
        op_tok = self._expect("op")
        op = op_tok.value
        if op not in _COMPARISON_OPS:
            raise FilterParseError(f"invalid filter: unknown operator {op!r}")
        value = self._parse_value(op)
        self._emit(prefix, name, op, value)

    def _parse_value(self, op: str) -> Any:
        tok = self._peek()
        if tok is None:
            raise FilterParseError("invalid filter: expected value, got end-of-input")
        if op == "IN":
            self._expect("lparen")
            values: List[Any] = []
            first = self._peek()
            if first is None or first.kind == "rparen":
                raise FilterParseError("invalid filter: empty IN (...) list")
            while True:
                nxt = self._peek()
                if nxt is None or nxt.kind not in ("number", "string"):
                    raise FilterParseError(
                        "invalid filter: IN list must contain numbers or strings"
                    )
                values.append(self._advance().value)
                sep = self._peek()
                if sep is not None and sep.kind == "comma":
                    self._advance()
                    continue
                break
            self._expect("rparen")
            return values
        if tok.kind not in ("number", "string"):
            raise FilterParseError(
                f"invalid filter: expected number or string value, got {tok.kind}"
            )
        return self._advance().value

    def _emit(self, prefix: str, name: str, op: str, value: Any) -> None:
        # Maps the MLflow prefix + name to a SQL fragment + bound
        # parameters. All identifier safety lives here:
        #   - ``attributes`` / ``env`` names must be in the allowlist
        #   - ``metrics`` / ``params`` / ``tags`` names are validated
        #     via _IDENT_REGEX (done at _parse_term)
        if prefix in ("attributes", "env"):
            if name not in _RUN_COLUMN_ALLOWLIST:
                raise FilterParseError(
                    f"invalid filter: column {name!r} not in allowlist; "
                    f"allowed: {sorted(_RUN_COLUMN_ALLOWLIST)}"
                )
            fragment, binds = _emit_run_column(name, op, value)
        elif prefix == "metrics":
            fragment, binds = _emit_metric(name, op, value)
        elif prefix == "params":
            fragment, binds = _emit_param(name, op, value)
        elif prefix == "tags":
            fragment, binds = _emit_tag(name, op, value)
        else:
            raise FilterParseError(f"invalid filter: unknown prefix {prefix!r}")
        self._where_fragments.append(fragment)
        self._bind_params.extend(binds)


def _emit_run_column(name: str, op: str, value: Any) -> Tuple[str, List[Any]]:
    """Emit a WHERE fragment against a fixed ``experiment_runs`` column."""
    if op == "IN":
        assert isinstance(value, list)
        placeholders = ", ".join(["?"] * len(value))
        return f"r.{name} IN ({placeholders})", list(value)
    return f"r.{name} {op} ?", [value]


def _emit_metric(name: str, op: str, value: Any) -> Tuple[str, List[Any]]:
    """Emit an EXISTS sub-select against ``experiment_metrics`` picking the
    latest-logged row per ``(run_id, key)``.

    "Latest" == row with the highest ``id`` for a given ``(run_id, key)``
    — append-only rowid ordering per spec §4.2. Binding ``key`` as a
    parameter is safe; the comparison operator is interpolated from the
    allowlist in :data:`_COMPARISON_OPS`.
    """
    if op == "IN":
        assert isinstance(value, list)
        placeholders = ", ".join(["?"] * len(value))
        inner = (
            f"SELECT 1 FROM experiment_metrics m "
            f"WHERE m.run_id = r.run_id AND m.key = ? "
            f"AND m.id = (SELECT MAX(id) FROM experiment_metrics "
            f"WHERE run_id = r.run_id AND key = ?) "
            f"AND m.value IN ({placeholders})"
        )
        return f"EXISTS ({inner})", [name, name, *value]
    inner = (
        f"SELECT 1 FROM experiment_metrics m "
        f"WHERE m.run_id = r.run_id AND m.key = ? "
        f"AND m.id = (SELECT MAX(id) FROM experiment_metrics "
        f"WHERE run_id = r.run_id AND key = ?) "
        f"AND m.value {op} ?"
    )
    return f"EXISTS ({inner})", [name, name, value]


def _emit_param(name: str, op: str, value: Any) -> Tuple[str, List[Any]]:
    """Emit a JSON-extract comparison against ``experiment_runs.params``.

    ``name`` has passed :data:`_IDENT_REGEX`, so it cannot contain the
    double-quote / backslash characters that would break the JSON path.
    """
    path = f'$."{name}"'
    if op == "IN":
        assert isinstance(value, list)
        placeholders = ", ".join(["?"] * len(value))
        return f"json_extract(r.params, ?) IN ({placeholders})", [path, *value]
    return f"json_extract(r.params, ?) {op} ?", [path, value]


def _emit_tag(name: str, op: str, value: Any) -> Tuple[str, List[Any]]:
    """Emit an EXISTS sub-select against ``experiment_tags``."""
    if op == "IN":
        assert isinstance(value, list)
        placeholders = ", ".join(["?"] * len(value))
        inner = (
            f"SELECT 1 FROM experiment_tags t "
            f"WHERE t.run_id = r.run_id AND t.key = ? "
            f"AND t.value IN ({placeholders})"
        )
        return f"EXISTS ({inner})", [name, *value]
    inner = (
        f"SELECT 1 FROM experiment_tags t "
        f"WHERE t.run_id = r.run_id AND t.key = ? AND t.value {op} ?"
    )
    return f"EXISTS ({inner})", [name, value]


def build_search_sql(
    filter_str: Optional[str],
    *,
    tenant_id: Optional[str],
    order_by: Optional[str],
    limit: int,
) -> Tuple[str, List[Any]]:
    """Parse a filter string and assemble a full ``SELECT`` statement.

    The statement aliases ``experiment_runs`` as ``r`` so emitter-
    generated sub-selects can join unambiguously. Tenant scoping is
    applied as an additional AND clause when ``tenant_id`` is non-None;
    callers MUST pass the resolved default tenant explicitly (Missing
    tenant handling is ``ExperimentTracker`` scope, not parser scope).

    Returns ``(sql, params)``.
    """
    if limit < 0:
        raise ValueError(f"limit must be non-negative, got {limit}")

    clauses: List[str] = []
    params: List[Any] = []

    if tenant_id is not None:
        clauses.append("r.tenant_id = ?")
        params.append(tenant_id)

    if filter_str:
        tokens = _tokenize(filter_str)
        if not tokens:
            raise FilterParseError("invalid filter: empty expression")
        parser = _Parser(tokens)
        where, binds = parser.parse()
        clauses.append(f"({where})")
        params.extend(binds)

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    if order_by is not None:
        order_sql = _build_order_by(order_by)
    else:
        order_sql = " ORDER BY r.wall_clock_end DESC"

    sql = "SELECT r.* FROM experiment_runs r" + where_sql + order_sql + " LIMIT ?"
    params.append(int(limit))
    return sql, params


def _build_order_by(order_by: str) -> str:
    """Validate + emit an ORDER BY clause.

    Accepts ``"<column> [ASC|DESC]"`` where ``<column>`` is in
    :data:`_RUN_COLUMN_ALLOWLIST`. Unvalidated identifiers are BLOCKED
    — callers with dynamic sort keys should add to the allowlist.
    """
    parts = order_by.strip().split()
    if not parts or len(parts) > 2:
        raise FilterParseError(
            f"invalid filter: order_by must be '<column> [ASC|DESC]', got {order_by!r}"
        )
    col = parts[0]
    direction = parts[1].upper() if len(parts) == 2 else "ASC"
    if direction not in {"ASC", "DESC"}:
        raise FilterParseError(
            f"invalid filter: order_by direction must be ASC or DESC, got {direction!r}"
        )
    if col not in _RUN_COLUMN_ALLOWLIST:
        raise FilterParseError(
            f"invalid filter: order_by column {col!r} not in allowlist"
        )
    return f" ORDER BY r.{col} {direction}"


# ---------------------------------------------------------------------------
# Row → RunRecord conversion
# ---------------------------------------------------------------------------


def run_record_from_row(row: Mapping[str, Any]) -> RunRecord:
    """Build a :class:`RunRecord` from a backend row dict."""
    params_raw = row.get("params")
    if isinstance(params_raw, dict):
        params = dict(params_raw)
    elif isinstance(params_raw, str):
        try:
            params = json.loads(params_raw) if params_raw else {}
        except (TypeError, ValueError):
            params = {}
    else:
        params = {}
    environment = {col: row.get(col) for col in _ENV_DIFF_COLUMNS}
    return RunRecord(
        run_id=row["run_id"],
        experiment=row["experiment"],
        status=row.get("status", "RUNNING"),
        tenant_id=row.get("tenant_id"),
        parent_run_id=row.get("parent_run_id"),
        wall_clock_start=row.get("wall_clock_start"),
        wall_clock_end=row.get("wall_clock_end"),
        duration_seconds=row.get("duration_seconds"),
        params=params,
        environment=environment,
        error_type=row.get("error_type"),
        error_message=row.get("error_message"),
    )


# ---------------------------------------------------------------------------
# Diff computation
# ---------------------------------------------------------------------------


def compute_run_diff(
    record_a: RunRecord,
    record_b: RunRecord,
    metrics_a: Sequence[Mapping[str, Any]],
    metrics_b: Sequence[Mapping[str, Any]],
) -> RunDiff:
    """Produce a :class:`RunDiff` from two records + their metric rows.

    ``metrics_*`` comes from
    :meth:`SQLiteTrackerBackend.list_metrics` — ordered by
    ``(key, step, id)`` so per-step frames can be assembled without a
    resort. The spec (§5.3) defines ``reproducibility_risk`` as
    ``True`` when the git_sha AND the cuda_version differ AND any
    metric's ``pct_change`` exceeds 5 %.
    """
    # Params — union of keys
    params_diff: Dict[str, ParamDelta] = {}
    all_param_keys = set(record_a.params) | set(record_b.params)
    for key in sorted(all_param_keys):
        va = record_a.params.get(key)
        vb = record_b.params.get(key)
        params_diff[key] = ParamDelta(
            key=key, value_a=va, value_b=vb, changed=(va != vb)
        )

    # Environment — explicit column list
    env_diff: Dict[str, EnvDelta] = {}
    for col in _ENV_DIFF_COLUMNS:
        va = record_a.environment.get(col)
        vb = record_b.environment.get(col)
        env_diff[col] = EnvDelta(key=col, value_a=va, value_b=vb, changed=(va != vb))

    # Metrics — union of keys, latest value per key, per-step frame when both
    metric_diff: Dict[str, MetricDelta] = {}
    by_key_a = _group_metrics_by_key(metrics_a)
    by_key_b = _group_metrics_by_key(metrics_b)
    all_metric_keys = set(by_key_a) | set(by_key_b)
    max_pct: float = 0.0
    for key in sorted(all_metric_keys):
        rows_a = by_key_a.get(key, [])
        rows_b = by_key_b.get(key, [])
        latest_a = rows_a[-1]["value"] if rows_a else None
        latest_b = rows_b[-1]["value"] if rows_b else None
        delta: Optional[float] = None
        pct_change: Optional[float] = None
        if latest_a is not None and latest_b is not None:
            delta = float(latest_b) - float(latest_a)
            if float(latest_a) != 0.0:
                pct_change = (delta / float(latest_a)) * 100.0
                max_pct = max(max_pct, abs(pct_change))
        per_step = _build_per_step_frame(rows_a, rows_b)
        metric_diff[key] = MetricDelta(
            key=key,
            value_a=latest_a,
            value_b=latest_b,
            delta=delta,
            pct_change=pct_change,
            per_step=per_step,
        )

    git_changed = env_diff["git_sha"].changed
    cuda_changed = env_diff["cuda_version"].changed
    reproducibility_risk = git_changed and cuda_changed and max_pct > 5.0

    params_changed = sum(1 for d in params_diff.values() if d.changed)
    env_changed = sum(1 for d in env_diff.values() if d.changed)
    summary = (
        f"{params_changed}/{len(params_diff)} params changed, "
        f"{env_changed}/{len(env_diff)} env fields changed, "
        f"max |pct_change|={max_pct:.2f}%"
    )
    return RunDiff(
        run_id_a=record_a.run_id,
        run_id_b=record_b.run_id,
        params=params_diff,
        metrics=metric_diff,
        environment=env_diff,
        reproducibility_risk=reproducibility_risk,
        summary=summary,
    )


def _group_metrics_by_key(
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Mapping[str, Any]]]:
    grouped: Dict[str, List[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["key"], []).append(row)
    return grouped


def _build_per_step_frame(
    rows_a: Sequence[Mapping[str, Any]],
    rows_b: Sequence[Mapping[str, Any]],
) -> Optional[Any]:
    """Return a polars DataFrame of step-aligned values, or ``None``.

    ``None`` when either side lacks step-indexed rows (spec §5.3 —
    ``per_step`` is optional). The frame has columns ``step``,
    ``value_a``, ``value_b``.
    """
    steps_a = {r["step"]: r["value"] for r in rows_a if r.get("step") is not None}
    steps_b = {r["step"]: r["value"] for r in rows_b if r.get("step") is not None}
    if not steps_a or not steps_b:
        return None
    import polars as pl  # noqa: PLC0415 — polars imported lazily per module budget

    steps = sorted(set(steps_a) | set(steps_b))
    return pl.DataFrame(
        {
            "step": steps,
            "value_a": [steps_a.get(s) for s in steps],
            "value_b": [steps_b.get(s) for s in steps],
        }
    )
