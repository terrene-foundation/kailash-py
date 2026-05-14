# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for SSRF protection.
"""

from __future__ import annotations

import pytest

from dataflow.fabric.ssrf import SSRFError, validate_url_safe


class TestSSRFProtection:
    def test_public_url_passes(self):
        assert (
            validate_url_safe("https://api.example.com/v1")
            == "https://api.example.com/v1"
        )

    def test_http_url_passes(self):
        assert validate_url_safe("http://api.example.com") == "http://api.example.com"

    def test_private_ip_10_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://10.0.0.1/admin")

    def test_private_ip_172_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://172.16.0.1/admin")

    def test_private_ip_192_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://192.168.1.1/admin")

    def test_localhost_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://127.0.0.1/admin")

    def test_ipv6_loopback_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://[::1]/admin")

    def test_link_local_blocked(self):
        with pytest.raises(SSRFError, match="blocked IP range"):
            validate_url_safe("http://169.254.1.1/metadata")

    def test_path_traversal_blocked(self):
        with pytest.raises(SSRFError, match="Path traversal"):
            validate_url_safe("https://api.example.com/../../../etc/passwd")

    def test_no_scheme_raises(self):
        with pytest.raises(ValueError, match="http or https"):
            validate_url_safe("ftp://bad.com")

    def test_no_hostname_raises(self):
        with pytest.raises(ValueError, match="no hostname"):
            validate_url_safe("http://")

    def test_domain_names_pass(self):
        assert (
            validate_url_safe("https://salesforce.com/api/v1")
            == "https://salesforce.com/api/v1"
        )
