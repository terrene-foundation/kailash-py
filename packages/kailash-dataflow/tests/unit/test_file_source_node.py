# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for TSG-102: FileSourceNode."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio

from dataflow.nodes.file_source import (
    EXTENSION_MAP,
    SUPPORTED_FORMATS,
    DataFlowDependencyError,
    FileSourceNode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def node():
    return FileSourceNode()


@pytest.fixture
def csv_file(tmp_path):
    p = tmp_path / "users.csv"
    p.write_text("name,email,age\nAlice,alice@example.com,30\nBob,bob@example.com,25\n")
    return str(p)


@pytest.fixture
def tsv_file(tmp_path):
    p = tmp_path / "users.tsv"
    p.write_text(
        "name\temail\tage\nAlice\talice@example.com\t30\nBob\tbob@example.com\t25\n"
    )
    return str(p)


@pytest.fixture
def json_file(tmp_path):
    p = tmp_path / "users.json"
    data = [
        {"name": "Alice", "email": "alice@example.com", "age": 30},
        {"name": "Bob", "email": "bob@example.com", "age": 25},
    ]
    p.write_text(json.dumps(data))
    return str(p)


@pytest.fixture
def jsonl_file(tmp_path):
    p = tmp_path / "users.jsonl"
    lines = [
        json.dumps({"name": "Alice", "email": "alice@example.com", "age": 30}),
        json.dumps({"name": "Bob", "email": "bob@example.com", "age": 25}),
    ]
    p.write_text("\n".join(lines) + "\n")
    return str(p)


# ---------------------------------------------------------------------------
# Format auto-detection
# ---------------------------------------------------------------------------


class TestFormatDetection:
    def test_extension_map_completeness(self):
        """All documented extensions are mapped."""
        assert ".csv" in EXTENSION_MAP
        assert ".tsv" in EXTENSION_MAP
        assert ".xlsx" in EXTENSION_MAP
        assert ".xls" in EXTENSION_MAP
        assert ".parquet" in EXTENSION_MAP
        assert ".json" in EXTENSION_MAP
        assert ".jsonl" in EXTENSION_MAP

    def test_auto_detection_csv(self, node):
        assert node._detect_format("/data/file.csv", "auto") == "csv"

    def test_auto_detection_tsv(self, node):
        assert node._detect_format("/data/file.tsv", "auto") == "tsv"

    def test_auto_detection_excel(self, node):
        assert node._detect_format("/data/file.xlsx", "auto") == "excel"
        assert node._detect_format("/data/file.xls", "auto") == "excel"

    def test_auto_detection_parquet(self, node):
        assert node._detect_format("/data/file.parquet", "auto") == "parquet"

    def test_auto_detection_json(self, node):
        assert node._detect_format("/data/file.json", "auto") == "json"

    def test_auto_detection_jsonl(self, node):
        assert node._detect_format("/data/file.jsonl", "auto") == "jsonl"

    def test_unknown_extension_raises(self, node):
        with pytest.raises(ValueError, match="Cannot detect format"):
            node._detect_format("/data/file.xyz", "auto")

    def test_manual_override(self, node):
        assert node._detect_format("/data/file.txt", "csv") == "csv"

    def test_unsupported_format_raises(self, node):
        with pytest.raises(ValueError, match="Unsupported format"):
            node._detect_format("/data/file.txt", "xml")


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------


class TestCSVParsing:
    @pytest.mark.asyncio
    async def test_basic_csv(self, node, csv_file):
        result = await node.async_run(file_path=csv_file)
        assert result["count"] == 2
        assert result["records"][0]["name"] == "Alice"
        assert result["records"][1]["email"] == "bob@example.com"
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_tsv_auto_detection(self, node, tsv_file):
        result = await node.async_run(file_path=tsv_file)
        assert result["count"] == 2
        assert result["records"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_skip_rows(self, node, tmp_path):
        p = tmp_path / "with_header.csv"
        p.write_text("# comment line\nname,age\nAlice,30\n")
        result = await node.async_run(file_path=str(p), skip_rows=1)
        assert result["count"] == 1
        assert result["records"][0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


class TestJSONParsing:
    @pytest.mark.asyncio
    async def test_json_list(self, node, json_file):
        result = await node.async_run(file_path=json_file)
        assert result["count"] == 2
        assert result["records"][0]["name"] == "Alice"
        assert result["records"][1]["age"] == 25

    @pytest.mark.asyncio
    async def test_json_not_list_raises(self, node, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text('{"key": "value"}')
        with pytest.raises(ValueError, match="list of objects"):
            await node.async_run(file_path=str(p))


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------


class TestJSONLParsing:
    @pytest.mark.asyncio
    async def test_jsonl(self, node, jsonl_file):
        result = await node.async_run(file_path=jsonl_file)
        assert result["count"] == 2
        assert result["records"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_jsonl_blank_lines_skipped(self, node, tmp_path):
        p = tmp_path / "with_blanks.jsonl"
        p.write_text('{"a":1}\n\n{"b":2}\n')
        result = await node.async_run(file_path=str(p))
        assert result["count"] == 2


# ---------------------------------------------------------------------------
# Excel lazy import
# ---------------------------------------------------------------------------


class TestExcelLazyImport:
    @pytest.mark.asyncio
    async def test_missing_openpyxl_error(self, node, tmp_path):
        p = tmp_path / "test.xlsx"
        p.write_text("")  # Dummy file
        with patch.dict("sys.modules", {"openpyxl": None}):
            with pytest.raises(DataFlowDependencyError, match="openpyxl"):
                await node.async_run(file_path=str(p))


# ---------------------------------------------------------------------------
# Parquet lazy import
# ---------------------------------------------------------------------------


class TestParquetLazyImport:
    @pytest.mark.asyncio
    async def test_missing_pyarrow_error(self, node, tmp_path):
        p = tmp_path / "test.parquet"
        p.write_text("")  # Dummy file
        with patch.dict("sys.modules", {"pyarrow": None, "pyarrow.parquet": None}):
            with pytest.raises(DataFlowDependencyError, match="pyarrow"):
                await node.async_run(file_path=str(p))


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


class TestColumnMapping:
    @pytest.mark.asyncio
    async def test_mapping_renames(self, node, csv_file):
        result = await node.async_run(
            file_path=csv_file,
            column_mapping={"name": "full_name", "email": "email_address"},
        )
        assert "full_name" in result["records"][0]
        assert "email_address" in result["records"][0]
        assert "name" not in result["records"][0]

    @pytest.mark.asyncio
    async def test_mapping_before_coercion(self, node, csv_file):
        """Mapping is applied before coercion."""
        result = await node.async_run(
            file_path=csv_file,
            column_mapping={"age": "user_age"},
            type_coercion={"user_age": "int"},
        )
        assert result["records"][0]["user_age"] == 30
        assert isinstance(result["records"][0]["user_age"], int)


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


class TestTypeCoercion:
    @pytest.mark.asyncio
    async def test_int_coercion(self, node, csv_file):
        result = await node.async_run(
            file_path=csv_file,
            type_coercion={"age": "int"},
        )
        assert result["records"][0]["age"] == 30
        assert isinstance(result["records"][0]["age"], int)

    @pytest.mark.asyncio
    async def test_float_coercion(self, node, csv_file):
        result = await node.async_run(
            file_path=csv_file,
            type_coercion={"age": "float"},
        )
        assert result["records"][0]["age"] == 30.0
        assert isinstance(result["records"][0]["age"], float)

    @pytest.mark.asyncio
    async def test_bool_coercion(self, node, tmp_path):
        p = tmp_path / "bools.csv"
        p.write_text("active\ntrue\nfalse\n1\n0\nyes\n")
        result = await node.async_run(
            file_path=str(p),
            type_coercion={"active": "bool"},
        )
        assert result["records"][0]["active"] is True
        assert result["records"][1]["active"] is False
        assert result["records"][2]["active"] is True
        assert result["records"][3]["active"] is False
        assert result["records"][4]["active"] is True

    @pytest.mark.asyncio
    async def test_coercion_failure_soft(self, node, tmp_path):
        p = tmp_path / "bad_ints.csv"
        p.write_text("value\n42\nnot_a_number\n99\n")
        result = await node.async_run(
            file_path=str(p),
            type_coercion={"value": "int"},
        )
        # Good values coerced
        assert result["records"][0]["value"] == 42
        assert result["records"][2]["value"] == 99
        # Bad value kept as string
        assert result["records"][1]["value"] == "not_a_number"
        # Error recorded
        assert len(result["errors"]) == 1
        assert "not_a_number" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_file_not_found(self, node):
        with pytest.raises(FileNotFoundError):
            await node.async_run(file_path="/nonexistent/file.csv")
