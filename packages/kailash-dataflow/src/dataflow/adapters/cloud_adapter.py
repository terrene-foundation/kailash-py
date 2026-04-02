# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Cloud Source Adapter — S3, GCS, Azure Blob storage.

Connects to cloud object stores for reading/writing data. Provider
abstraction selects the correct client (boto3 for S3, google-cloud-storage
for GCS). All cloud SDKs are lazy-imported.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter
from dataflow.fabric.config import CloudSourceConfig

logger = logging.getLogger(__name__)

__all__ = ["CloudSourceAdapter"]


class CloudSourceAdapter(BaseSourceAdapter):
    """Source adapter for cloud object storage (S3, GCS, Azure Blob)."""

    def __init__(self, name: str, config: CloudSourceConfig) -> None:
        super().__init__(name, circuit_breaker=config.circuit_breaker)
        self.config = config
        self._client: Any = None
        self._last_etags: Dict[str, str] = {}

    @property
    def database_type(self) -> str:
        return f"cloud:{self.config.provider}"

    async def _connect(self) -> None:
        provider = self.config.provider

        if provider == "s3":
            try:
                import boto3
            except ImportError as exc:
                raise ImportError(
                    "boto3 is required for S3 sources. "
                    "Install with: pip install kailash-dataflow[cloud]"
                ) from exc
            self._client = boto3.client("s3")

        elif provider == "gcs":
            try:
                from google.cloud import storage as gcs_storage
            except ImportError as exc:
                raise ImportError(
                    "google-cloud-storage is required for GCS sources. "
                    "Install with: pip install kailash-dataflow[cloud]"
                ) from exc
            self._client = gcs_storage.Client()

        elif provider == "azure":
            try:
                from azure.storage.blob import BlobServiceClient
            except ImportError as exc:
                raise ImportError(
                    "azure-storage-blob is required for Azure Blob sources. "
                    "Install with: pip install azure-storage-blob"
                ) from exc
            self._client = BlobServiceClient.from_connection_string(self.config.bucket)
        else:
            raise ValueError(f"Unknown cloud provider: {provider}")

        logger.info(
            "Cloud adapter '%s' connected to %s bucket '%s'",
            self.name,
            provider,
            self.config.bucket,
        )

    async def _disconnect(self) -> None:
        if self.config.provider == "azure" and self._client is not None:
            self._client.close()
        self._client = None

    async def detect_change(self) -> bool:
        if self._client is None:
            raise ConnectionError(f"Cloud adapter '{self.name}' not connected")

        prefix = self.config.prefix
        changed = False

        if self.config.provider == "s3":
            response = self._client.list_objects_v2(
                Bucket=self.config.bucket, Prefix=prefix, MaxKeys=100
            )
            for obj in response.get("Contents", []):
                key = obj["Key"]
                etag = obj["ETag"]
                if self._last_etags.get(key) != etag:
                    self._last_etags[key] = etag
                    changed = True

        elif self.config.provider == "gcs":
            bucket = self._client.bucket(self.config.bucket)
            blobs = bucket.list_blobs(prefix=prefix, max_results=100)
            for blob in blobs:
                etag = blob.etag or ""
                if self._last_etags.get(blob.name) != etag:
                    self._last_etags[blob.name] = etag
                    changed = True

        elif self.config.provider == "azure":
            container = self._client.get_container_client(self.config.bucket)
            blobs = container.list_blobs(name_starts_with=prefix)
            for blob in blobs:
                etag = blob.etag or ""
                if self._last_etags.get(blob.name) != etag:
                    self._last_etags[blob.name] = etag
                    changed = True

        return changed

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        if self._client is None:
            raise ConnectionError(f"Cloud adapter '{self.name}' not connected")

        key = f"{self.config.prefix}{path}" if self.config.prefix else path
        if not key:
            raise ValueError("Cloud fetch requires a path (object key)")

        data: Any
        if self.config.provider == "s3":
            response = self._client.get_object(Bucket=self.config.bucket, Key=key)
            body = response["Body"].read()
            data = self._parse_content(key, body)

        elif self.config.provider == "gcs":
            bucket = self._client.bucket(self.config.bucket)
            blob = bucket.blob(key)
            body = blob.download_as_bytes()
            data = self._parse_content(key, body)

        elif self.config.provider == "azure":
            container = self._client.get_container_client(self.config.bucket)
            blob_client = container.get_blob_client(key)
            body = blob_client.download_blob().readall()
            data = self._parse_content(key, body)

        else:
            raise ValueError(f"Unknown provider: {self.config.provider}")

        self._record_successful_data(path, data)
        return data

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        if self._client is None:
            raise ConnectionError(f"Cloud adapter '{self.name}' not connected")

        prefix = f"{self.config.prefix}{path}" if self.config.prefix else path

        if self.config.provider == "s3":
            continuation_token = None
            while True:
                kwargs: Dict[str, Any] = {
                    "Bucket": self.config.bucket,
                    "Prefix": prefix,
                    "MaxKeys": page_size,
                }
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token

                response = self._client.list_objects_v2(**kwargs)
                contents = response.get("Contents", [])
                if contents:
                    yield [
                        {"Key": obj["Key"], "Size": obj["Size"], "ETag": obj["ETag"]}
                        for obj in contents
                    ]

                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")

        elif self.config.provider == "gcs":
            bucket = self._client.bucket(self.config.bucket)
            page_iter = bucket.list_blobs(prefix=prefix, max_results=page_size)
            page: List[Any] = []
            for blob in page_iter:
                page.append({"Key": blob.name, "Size": blob.size, "ETag": blob.etag})
                if len(page) >= page_size:
                    yield page
                    page = []
            if page:
                yield page

        elif self.config.provider == "azure":
            container = self._client.get_container_client(self.config.bucket)
            page_list: List[Any] = []
            for blob in container.list_blobs(name_starts_with=prefix):
                page_list.append(
                    {"Key": blob.name, "Size": blob.size, "ETag": blob.etag}
                )
                if len(page_list) >= page_size:
                    yield page_list
                    page_list = []
            if page_list:
                yield page_list

    async def list(self, prefix: str = "", limit: int = 1000) -> List[Any]:
        if self._client is None:
            raise ConnectionError(f"Cloud adapter '{self.name}' not connected")

        full_prefix = f"{self.config.prefix}{prefix}" if self.config.prefix else prefix
        items: List[Any] = []

        if self.config.provider == "s3":
            response = self._client.list_objects_v2(
                Bucket=self.config.bucket, Prefix=full_prefix, MaxKeys=limit
            )
            for obj in response.get("Contents", []):
                items.append(
                    {"Key": obj["Key"], "Size": obj["Size"], "ETag": obj["ETag"]}
                )

        elif self.config.provider == "gcs":
            bucket = self._client.bucket(self.config.bucket)
            for blob in bucket.list_blobs(prefix=full_prefix, max_results=limit):
                items.append({"Key": blob.name, "Size": blob.size, "ETag": blob.etag})

        elif self.config.provider == "azure":
            container = self._client.get_container_client(self.config.bucket)
            count = 0
            for blob in container.list_blobs(name_starts_with=full_prefix):
                items.append({"Key": blob.name, "Size": blob.size, "ETag": blob.etag})
                count += 1
                if count >= limit:
                    break

        return items

    async def write(self, path: str, data: Any) -> Any:
        if self._client is None:
            raise ConnectionError(f"Cloud adapter '{self.name}' not connected")

        key = f"{self.config.prefix}{path}" if self.config.prefix else path
        if not key:
            raise ValueError("Cloud write requires a path (object key)")

        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            content_type = "application/json"
        elif isinstance(data, str):
            body = data.encode("utf-8")
            content_type = "text/plain"
        elif isinstance(data, bytes):
            body = data
            content_type = "application/octet-stream"
        else:
            body = str(data).encode("utf-8")
            content_type = "text/plain"

        if self.config.provider == "s3":
            self._client.put_object(
                Bucket=self.config.bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        elif self.config.provider == "gcs":
            bucket = self._client.bucket(self.config.bucket)
            blob = bucket.blob(key)
            blob.upload_from_string(body, content_type=content_type)
        elif self.config.provider == "azure":
            container = self._client.get_container_client(self.config.bucket)
            container.upload_blob(key, body, overwrite=True)

        return {"key": key, "size": len(body)}

    def supports_feature(self, feature: str) -> bool:
        supported = {"detect_change", "fetch", "fetch_pages", "write", "list"}
        return feature in supported

    def _parse_content(self, key: str, body: bytes) -> Any:
        """Parse object content based on key extension."""
        lower_key = key.lower()

        if lower_key.endswith(".json"):
            return json.loads(body.decode("utf-8"))
        elif lower_key.endswith((".yaml", ".yml")):
            try:
                import yaml
            except ImportError as exc:
                raise ImportError(
                    "PyYAML is required for YAML parsing. "
                    "Install with: pip install pyyaml"
                ) from exc
            return yaml.safe_load(body.decode("utf-8"))
        elif lower_key.endswith(".csv"):
            import csv
            import io

            reader = csv.DictReader(io.StringIO(body.decode("utf-8")))
            return list(reader)
        else:
            # Return raw text for unknown types
            try:
                return body.decode("utf-8")
            except UnicodeDecodeError:
                return body
