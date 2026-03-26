# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""VerificationBundle — self-contained export for independent verification.

A VerificationBundle packages everything needed to independently verify
a TrustPlane project's trust chain without access to the TrustPlane
installation or EATP SDK.

Bundle contents:
- Genesis Record (full)
- Constraint Envelope (full)
- All Audit Anchors in chain order
- Reasoning Traces (filtered by confidentiality ceiling)
- Public key of the originating authority

Security: All user-provided data is HTML-escaped before interpolation
in to_html() to prevent XSS in verification bundles.
- Chain hash for integrity verification
- Bundle metadata

Design decision: prototype in TrustPlane first, extract to EATP SDK
after the abstraction proves correct in real use.
"""

import errno
import hashlib
import hmac as hmac_mod
import html as html_mod
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kailash.trust.reasoning.traces import ConfidentialityLevel

from kailash.trust._locking import safe_read_json

logger = logging.getLogger(__name__)


# Confidentiality ordering for filtering
_CONFIDENTIALITY_ORDER = {
    ConfidentialityLevel.PUBLIC: 0,
    ConfidentialityLevel.RESTRICTED: 1,
    ConfidentialityLevel.CONFIDENTIAL: 2,
    ConfidentialityLevel.SECRET: 3,
    ConfidentialityLevel.TOP_SECRET: 4,
}


def _level_value(level: ConfidentialityLevel) -> int:
    return _CONFIDENTIALITY_ORDER.get(level, 0)


class VerificationBundle:
    """Self-contained verification package for a TrustPlane project."""

    def __init__(
        self,
        genesis: dict[str, Any],
        constraint_envelope: dict[str, Any] | None,
        anchors: list[dict[str, Any]],
        reasoning_traces: list[dict[str, Any]],
        public_key: str,
        chain_hash: str,
        project_metadata: dict[str, Any],
        mirror_summary: dict[str, Any] | None = None,
    ) -> None:
        self.genesis = genesis
        self.constraint_envelope = constraint_envelope
        self.anchors = anchors
        self.reasoning_traces = reasoning_traces
        self.public_key = public_key
        self.chain_hash = chain_hash
        self.project_metadata = project_metadata
        self.mirror_summary = mirror_summary
        self.created_at = datetime.now(timezone.utc)
        self.version = "1.0"

    @classmethod
    async def create(
        cls,
        project: Any,  # TrustProject — avoid circular import
        confidentiality_ceiling: ConfidentialityLevel = ConfidentialityLevel.PUBLIC,
    ) -> "VerificationBundle":
        """Create a VerificationBundle from a TrustProject.

        Args:
            project: The TrustProject to export
            confidentiality_ceiling: Maximum confidentiality level to include.
                Reasoning traces above this level are redacted.

        Returns:
            A complete VerificationBundle
        """
        trust_dir = project._dir

        # Load genesis
        genesis_path = trust_dir / "genesis.json"
        genesis = {}
        if genesis_path.exists():
            genesis = safe_read_json(genesis_path)

        # Load constraint envelope
        envelope = None
        if project.manifest.constraint_envelope:
            envelope = project.manifest.constraint_envelope.to_dict()

        # Load all anchors in order
        anchors_dir = trust_dir / "anchors"
        anchors: list[dict[str, Any]] = []
        reasoning_traces: list[dict[str, Any]] = []

        if anchors_dir.exists():
            for af in sorted(anchors_dir.glob("*.json")):
                data = safe_read_json(af)

                # Extract and filter reasoning trace
                trace = data.get("reasoning_trace")
                if trace:
                    trace_conf = trace.get("confidentiality", "public")
                    try:
                        trace_level = ConfidentialityLevel(trace_conf)
                    except ValueError:
                        trace_level = ConfidentialityLevel.PUBLIC

                    if _level_value(trace_level) <= _level_value(
                        confidentiality_ceiling
                    ):
                        reasoning_traces.append(trace)
                    else:
                        # Redact: preserve hash for chain integrity, remove content
                        content_str = json.dumps(trace, sort_keys=True, default=str)
                        redacted = {
                            "redacted": True,
                            "confidentiality": trace_conf,
                            "content_hash": hashlib.sha256(
                                content_str.encode()
                            ).hexdigest(),
                        }
                        reasoning_traces.append(redacted)

                # Strip reasoning_trace from anchor copy (it's separate)
                anchor_copy = {k: v for k, v in data.items() if k != "reasoning_trace"}
                anchors.append(anchor_copy)

        # Public key (symlink-safe read)
        pub_key_path = trust_dir / "keys" / "public.key"
        public_key = ""
        if pub_key_path.exists():
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(str(pub_key_path), flags)
            except OSError as e:
                if e.errno == errno.ELOOP:
                    raise OSError(
                        f"Refusing to read symlink (possible attack): {pub_key_path}"
                    ) from e
                raise
            try:
                f = os.fdopen(fd, "r")
            except Exception:
                os.close(fd)
                raise
            with f:
                public_key = f.read()

        # Compute chain hash from anchors
        chain_content = json.dumps(
            [a.get("anchor_id", "") for a in anchors], sort_keys=True
        )
        chain_hash = hashlib.sha256(chain_content.encode()).hexdigest()

        # Project metadata
        m = project.manifest
        metadata = {
            "project_id": m.project_id,
            "project_name": m.project_name,
            "author": m.author,
            "created_at": m.created_at.isoformat(),
            "total_decisions": m.total_decisions,
            "total_milestones": m.total_milestones,
            "total_audits": m.total_audits,
        }

        # Mirror summary if available
        mirror_summary = None
        try:
            from kailash.trust.plane.mirror import build_competency_map

            records = project.get_mirror_records()
            total_mirror = sum(len(v) for v in records.values())
            if total_mirror > 0:
                mirror_summary = build_competency_map(
                    records, project_name=m.project_name
                )
        except Exception:
            logger.debug("Mirror summary unavailable for bundle", exc_info=True)

        return cls(
            genesis=genesis,
            constraint_envelope=envelope,
            anchors=anchors,
            reasoning_traces=reasoning_traces,
            public_key=public_key,
            chain_hash=chain_hash,
            project_metadata=metadata,
            mirror_summary=mirror_summary,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize bundle to a dict."""
        return {
            "bundle_version": self.version,
            "created_at": self.created_at.isoformat(),
            "project": self.project_metadata,
            "genesis": self.genesis,
            "constraint_envelope": self.constraint_envelope,
            "anchors": self.anchors,
            "reasoning_traces": self.reasoning_traces,
            "public_key": self.public_key,
            "chain_hash": self.chain_hash,
            "anchor_count": len(self.anchors),
            "mirror_summary": self.mirror_summary,
            "verification": {
                "algorithm": "SHA-256 chain hash over ordered anchor IDs",
                "instructions": (
                    "To verify: compute SHA-256 of JSON array of anchor_id values "
                    "in order. Result must match chain_hash."
                ),
            },
        }

    def to_json(self) -> str:
        """Export as JSON string."""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_html(self) -> str:
        """Export as self-contained HTML with inline verification."""
        data = self.to_dict()
        m = data["project"]

        # Build decision timeline (all values HTML-escaped to prevent XSS)
        esc = html_mod.escape
        timeline_rows = ""
        for i, anchor in enumerate(data["anchors"]):
            action = esc(str(anchor.get("action", "unknown")))
            ts = esc(str(anchor.get("timestamp", "")))
            resource = esc(str(anchor.get("resource", "")))
            timeline_rows += (
                f"<tr><td>{i + 1}</td><td>{ts}</td>"
                f"<td>{action}</td><td>{resource}</td></tr>\n"
            )

        bundle_json = esc(json.dumps(data, indent=2, default=str))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>TrustPlane Verification Bundle — {esc(str(m.get("project_name", "Unknown")))}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }}
h1 {{ color: #1a1a2e; }}
h2 {{ color: #16213e; border-bottom: 1px solid #e0e0e0; padding-bottom: 0.3rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
th {{ background: #f5f5f5; }}
.valid {{ color: #27ae60; font-weight: bold; }}
.invalid {{ color: #e74c3c; font-weight: bold; }}
pre {{ background: #f8f9fa; padding: 1rem; overflow-x: auto; font-size: 0.85rem; }}
#verify-result {{ margin: 1rem 0; padding: 1rem; border-radius: 4px; }}
</style>
</head>
<body>
<h1>TrustPlane Verification Bundle</h1>
<h2>Project: {esc(str(m.get("project_name", "Unknown")))}</h2>
<table>
<tr><td><strong>Project ID</strong></td><td>{esc(str(m.get("project_id", "")))}</td></tr>
<tr><td><strong>Author</strong></td><td>{esc(str(m.get("author", "")))}</td></tr>
<tr><td><strong>Created</strong></td><td>{esc(str(m.get("created_at", "")))}</td></tr>
<tr><td><strong>Decisions</strong></td><td>{m.get("total_decisions", 0)}</td></tr>
<tr><td><strong>Milestones</strong></td><td>{m.get("total_milestones", 0)}</td></tr>
<tr><td><strong>Audit Anchors</strong></td><td>{data.get("anchor_count", 0)}</td></tr>
<tr><td><strong>Chain Hash</strong></td><td><code>{esc(str(data.get("chain_hash", "")))}</code></td></tr>
</table>

<h2>Anchor Timeline</h2>
<table>
<tr><th>#</th><th>Timestamp</th><th>Action</th><th>Resource</th></tr>
{timeline_rows}
</table>

<h2>Verification</h2>
<p>{esc(str(data["verification"]["instructions"]))}</p>
<button onclick="verifyBundle()">Verify Chain Integrity</button>
<div id="verify-result"></div>

<h2>Raw Bundle (JSON)</h2>
<pre id="bundle-json">{bundle_json}</pre>

<script>
async function verifyBundle() {{
    const resultDiv = document.getElementById('verify-result');
    try {{
        const bundle = JSON.parse(document.getElementById('bundle-json').textContent);
        const anchorIds = bundle.anchors.map(a => a.anchor_id);
        const data = JSON.stringify(anchorIds);
        const encoder = new TextEncoder();
        const hashBuffer = await crypto.subtle.digest('SHA-256', encoder.encode(data));
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const computed = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');

        if (computed === bundle.chain_hash) {{
            resultDiv.textContent = 'VALID — Chain hash matches.';
            resultDiv.style.background = '#e8f5e9';
            resultDiv.style.color = '#2e7d32';
        }} else {{
            resultDiv.textContent = 'INVALID — Chain hash mismatch! Expected: '
                + bundle.chain_hash + ' Computed: ' + computed;
            resultDiv.style.background = '#ffebee';
            resultDiv.style.color = '#c62828';
        }}
    }} catch(e) {{
        resultDiv.textContent = 'ERROR: Verification failed';
        resultDiv.style.background = '#ffebee';
        resultDiv.style.color = '#c62828';
    }}
}}
</script>
</body>
</html>"""
        return html

    @classmethod
    def verify(cls, bundle_json: str) -> dict[str, Any]:
        """Verify a bundle's integrity from JSON.

        Performs:
        1. Chain hash verification (recompute from anchor IDs)
        2. Parent chain continuity (each anchor's parent matches previous)

        Args:
            bundle_json: JSON string of a VerificationBundle

        Returns:
            Dict with 'valid', 'chain_hash_valid', 'parent_chain_valid',
            'issues', and 'summary'
        """
        data = json.loads(bundle_json)
        issues: list[str] = []

        # 1. Chain hash verification
        anchors = data.get("anchors", [])
        anchor_ids = [a.get("anchor_id", "") for a in anchors]
        content = json.dumps(anchor_ids, sort_keys=True)
        computed_hash = hashlib.sha256(content.encode()).hexdigest()
        chain_hash_valid = hmac_mod.compare_digest(
            computed_hash, data.get("chain_hash", "")
        )

        if not chain_hash_valid:
            issues.append(
                f"Chain hash mismatch: expected {data.get('chain_hash')}, "
                f"computed {computed_hash}"
            )

        # 2. Parent chain continuity
        parent_chain_valid = True
        expected_parent = None
        for i, anchor in enumerate(anchors):
            parent = anchor.get("parent_anchor_id")
            if parent != expected_parent:
                issues.append(
                    f"Anchor {i}: parent chain broken "
                    f"(expected {expected_parent}, got {parent})"
                )
                parent_chain_valid = False
            expected_parent = anchor.get("anchor_id")

        valid = chain_hash_valid and parent_chain_valid

        return {
            "valid": valid,
            "chain_hash_valid": chain_hash_valid,
            "parent_chain_valid": parent_chain_valid,
            "anchor_count": len(anchors),
            "issues": issues,
            "project": data.get("project", {}),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
