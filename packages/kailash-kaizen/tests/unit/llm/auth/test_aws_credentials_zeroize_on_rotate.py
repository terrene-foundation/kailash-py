# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Zeroize-on-rotate test for `AwsSigV4.refresh()`.

Round-2 MED-3 6.8 amendment: after `refresh()` swaps the credential slot,
the OLD `AwsCredentials` object's `SecretStr` fields MUST be cleared so
any lingering reference held by an observer gets "" rather than the real
rotated-out credential.

Python strings are immutable -- we can't truly zero memory. "Zeroize"
here means: overwrite the SecretStr wrapper's internal `_secret_value`
attribute with `""` so `get_secret_value()` returns `""` post-rotation.
The rule is structural defense against "someone captured a reference to
the old AwsCredentials object and checked `get_secret_value()` hours
later"; after zeroize, they get "".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.aws import AwsCredentials, AwsSigV4


@pytest.mark.asyncio
async def test_old_awscredentials_zeroized_after_refresh() -> None:
    """After refresh(), the OLD credential's SecretStr fields MUST return
    empty string from `get_secret_value()`.

    Mechanism: we hold a reference to the OLD AwsCredentials before
    refresh() runs, call refresh(), then assert the old reference's
    SecretStr fields are cleared.
    """
    old_creds = AwsCredentials(
        access_key_id=SecretStr("AKIAOLDACCESSKEYZEROIZE"),
        secret_access_key=SecretStr("OLDSECRETTOZEROIZE"),
        session_token=SecretStr("OLDSESSIONTOZEROIZE"),
        region="us-east-1",
    )
    sig = AwsSigV4(old_creds)

    # Keep an external reference to the OLD credentials dataclass so we
    # can check it after refresh swaps in the new one.
    old_ref = sig.credentials
    assert old_ref is old_creds  # sanity: pre-refresh reference is the same obj

    new_botocore_creds = MagicMock()
    new_botocore_creds.access_key = "AKIANEW"
    new_botocore_creds.secret_key = "NEWSECRET"
    new_botocore_creds.token = None

    session_mock = MagicMock()
    session_mock.get_credentials.return_value = new_botocore_creds

    with patch("botocore.session.Session", return_value=session_mock):
        await sig.refresh()

    # The NEW credentials are installed.
    assert sig.credentials is not old_ref
    assert sig.credentials.access_key_id.get_secret_value() == "AKIANEW"

    # The OLD credentials' SecretStr fields are now zeroized.
    # get_secret_value() on each returns "" -- the zeroize best-effort
    # overwrite of _secret_value took effect.
    assert old_ref.access_key_id.get_secret_value() == ""
    assert old_ref.secret_access_key.get_secret_value() == ""
    assert old_ref.session_token is not None
    assert old_ref.session_token.get_secret_value() == ""


@pytest.mark.asyncio
async def test_old_awscredentials_with_no_session_token_zeroizes_cleanly() -> None:
    """Zeroize MUST be safe when `session_token` is None (the caller-supplied
    static-credential flow where no STS token is present).
    """
    old_creds = AwsCredentials(
        access_key_id=SecretStr("AKIANOSESSION"),
        secret_access_key=SecretStr("NOSESSIONSECRET"),
        session_token=None,
        region="us-east-1",
    )
    sig = AwsSigV4(old_creds)

    new_botocore_creds = MagicMock()
    new_botocore_creds.access_key = "AKIAROTATED"
    new_botocore_creds.secret_key = "ROTATEDSECRET"
    new_botocore_creds.token = None

    session_mock = MagicMock()
    session_mock.get_credentials.return_value = new_botocore_creds

    with patch("botocore.session.Session", return_value=session_mock):
        await sig.refresh()  # must not raise

    assert old_creds.access_key_id.get_secret_value() == ""
    assert old_creds.secret_access_key.get_secret_value() == ""
    # Zeroize skipped for None session_token -- still None, no AttributeError.
    assert old_creds.session_token is None
