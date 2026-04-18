# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring test for `AwsSigV4` (#498 S4b-i).

Per `rules/facade-manager-detection.md` § 2, the wiring file lives at its
canonical path so absence is grep-able. `AwsSigV4` is the manager-shape
class for Bedrock SigV4 auth; this test exercises the end-to-end path
from constructed credentials through botocore canonicalization to the
installed `Authorization: AWS4-HMAC-SHA256 ...` header.

The live-completion path is gated on real AWS credentials
(`AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`). Without them we exercise
only the structural wiring: the auth strategy's `sign()` runs against
botocore's real `SigV4Auth` and the header shape is correct.
"""

from __future__ import annotations

import os

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.aws import AwsCredentials, AwsSigV4


@pytest.mark.integration
def test_awssigv4_structural_wiring_signs_request_against_real_botocore() -> None:
    """Structural: construct AwsSigV4 with dummy but well-formed credentials
    and assert botocore's SigV4Auth returns a canonical Authorization
    header of the expected shape.
    """
    creds = AwsCredentials(
        access_key_id=SecretStr(
            os.environ.get("AWS_ACCESS_KEY_ID", "AKIAIOSFODNN7EXAMPLE")
        ),
        secret_access_key=SecretStr(
            os.environ.get(
                "AWS_SECRET_ACCESS_KEY",
                "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )
        ),
        session_token=(
            SecretStr(os.environ["AWS_SESSION_TOKEN"])
            if "AWS_SESSION_TOKEN" in os.environ
            else None
        ),
        region=os.environ.get("AWS_REGION", "us-east-1"),
    )
    sig = AwsSigV4(creds)
    signed = sig.sign(
        method="POST",
        url=f"https://bedrock-runtime.{creds.region}.amazonaws.com/model/x/invoke",
        headers={"Content-Type": "application/json"},
        body=b'{"prompt": "hello"}',
    )
    assert "Authorization" in signed
    assert signed["Authorization"].startswith("AWS4-HMAC-SHA256")
    # x-amz-date header is case-insensitive; botocore installs it.
    assert "x-amz-date" in signed or "X-Amz-Date" in signed or "X-AMZ-DATE" in signed


@pytest.mark.integration
@pytest.mark.asyncio
async def test_awssigv4_live_bedrock_signed_completion() -> None:
    """Live Bedrock SigV4 completion -- skipped without real credentials.

    When S3 lands `LlmClient.complete()`, this test will exercise a real
    one-token completion against Bedrock using SigV4 signing.
    """
    if not os.environ.get("AWS_ACCESS_KEY_ID") or not os.environ.get(
        "AWS_SECRET_ACCESS_KEY"
    ):
        pytest.skip(
            "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY not set; live SigV4 "
            "wiring requires real credentials"
        )
    pytest.skip(
        "LlmClient.complete() wire-send path is implemented in session 3 (S3); "
        "this test flips on when complete() lands."
    )
