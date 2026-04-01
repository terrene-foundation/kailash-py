# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""DataFlow model field definitions for kailash-align.

These define the schema for AlignAdapter and AlignAdapterVersion records.
Fields use TEXT for JSON storage (same pattern as kailash-ml MLModelVersion.metrics_json).
"""
from __future__ import annotations

__all__ = [
    "ALIGN_ADAPTER_FIELDS",
    "ALIGN_ADAPTER_VERSION_FIELDS",
]

ALIGN_ADAPTER_FIELDS = {
    "id": "TEXT PRIMARY KEY",
    "name": "TEXT NOT NULL",
    "model_type": "TEXT NOT NULL DEFAULT 'alignment'",
    "base_model_id": "TEXT NOT NULL",
    "base_model_revision": "TEXT",
    "lora_config_json": "TEXT NOT NULL",
    "training_data_ref": "TEXT",
    "tags_json": "TEXT DEFAULT '[]'",
    "onnx_status": "TEXT NOT NULL DEFAULT 'not_applicable'",
    "created_at": "TEXT NOT NULL",
}

ALIGN_ADAPTER_VERSION_FIELDS = {
    "id": "TEXT PRIMARY KEY",
    "adapter_id": "TEXT NOT NULL",
    "version": "TEXT NOT NULL",
    "stage": "TEXT NOT NULL DEFAULT 'staging'",
    "adapter_path": "TEXT NOT NULL",
    "base_model_id": "TEXT NOT NULL",
    "lora_config_json": "TEXT NOT NULL",
    "training_metrics_json": "TEXT DEFAULT '{}'",
    "merge_status": "TEXT NOT NULL DEFAULT 'separate'",
    "merged_model_path": "TEXT",
    "gguf_path": "TEXT",
    "quantization_config_json": "TEXT",
    "eval_results_json": "TEXT",
    "created_at": "TEXT NOT NULL",
}
