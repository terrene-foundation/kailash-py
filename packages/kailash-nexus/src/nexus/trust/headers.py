"""EATP Header Extraction for Kailash Nexus.

This module provides components for extracting EATP (Extensible Agent Trust Protocol)
headers from HTTP requests and converting them to structured trust context objects.

EATP Headers:
    X-EATP-Trace-ID: Unique identifier for the request trace
    X-EATP-Agent-ID: Identifier of the requesting agent
    X-EATP-Human-Origin: Base64-encoded JSON with human origin info
    X-EATP-Delegation-Chain: Comma-separated or JSON array of agent IDs
    X-EATP-Delegation-Depth: Integer depth of delegation
    X-EATP-Constraints: Base64-encoded JSON with operation constraints
    X-EATP-Session-ID: Optional session identifier
    X-EATP-Signature: Optional cryptographic signature

Usage:
    from nexus.trust.headers import EATPHeaderExtractor, ExtractedEATPContext

    extractor = EATPHeaderExtractor()
    context = extractor.extract(request.headers)

    if context.is_valid():
        print(f"Valid request from agent: {context.agent_id}")

    # Forward headers to downstream services
    forwarded_headers = extractor.to_headers(context)
"""

import base64
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# EATP Header names (canonical case)
EATP_TRACE_ID = "X-EATP-Trace-ID"
EATP_AGENT_ID = "X-EATP-Agent-ID"
EATP_HUMAN_ORIGIN = "X-EATP-Human-Origin"
EATP_DELEGATION_CHAIN = "X-EATP-Delegation-Chain"
EATP_DELEGATION_DEPTH = "X-EATP-Delegation-Depth"
EATP_CONSTRAINTS = "X-EATP-Constraints"
EATP_SESSION_ID = "X-EATP-Session-ID"
EATP_SIGNATURE = "X-EATP-Signature"

# All EATP header names for filtering
EATP_HEADERS = [
    EATP_TRACE_ID,
    EATP_AGENT_ID,
    EATP_HUMAN_ORIGIN,
    EATP_DELEGATION_CHAIN,
    EATP_DELEGATION_DEPTH,
    EATP_CONSTRAINTS,
    EATP_SESSION_ID,
    EATP_SIGNATURE,
]


@dataclass
class ExtractedEATPContext:
    """Structured representation of extracted EATP headers.

    This dataclass holds all EATP trust context information extracted from
    HTTP headers. It provides methods to validate the context and check
    for human origin.

    Attributes:
        trace_id: Unique identifier for the request trace
        agent_id: Identifier of the requesting agent
        human_origin: Decoded JSON object with human origin information
        delegation_chain: List of agent IDs in the delegation chain
        delegation_depth: Integer depth of delegation (0 = direct)
        constraints: Decoded JSON object with operation constraints
        session_id: Optional session identifier
        signature: Optional cryptographic signature
        raw_headers: Dictionary of original EATP headers (for forwarding)
    """

    trace_id: Optional[str]
    agent_id: Optional[str]
    human_origin: Optional[Dict[str, Any]]
    delegation_chain: List[str] = field(default_factory=list)
    delegation_depth: int = 0
    constraints: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    signature: Optional[str] = None
    raw_headers: Dict[str, str] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if the context has required fields for valid EATP trust.

        A valid EATP context must have both trace_id and agent_id present.

        Returns:
            True if trace_id AND agent_id are present, False otherwise.
        """
        return self.trace_id is not None and self.agent_id is not None

    def has_human_origin(self) -> bool:
        """Check if the request has verified human origin.

        Returns:
            True if human_origin is not None, False otherwise.
        """
        return self.human_origin is not None


class EATPHeaderExtractor:
    """Extracts and parses EATP headers from HTTP requests.

    This class handles the extraction and parsing of EATP (Extensible Agent
    Trust Protocol) headers, providing robust error handling for malformed
    data while maintaining maximum information extraction.

    Usage:
        extractor = EATPHeaderExtractor()

        # Extract from request headers
        context = extractor.extract(request.headers)

        if context.is_valid():
            # Process trusted agent request
            ...

        # Convert context back to headers for forwarding
        headers = extractor.to_headers(context)
    """

    def __init__(self) -> None:
        """Initialize the EATP header extractor."""
        self._header_map: Dict[str, str] = {}

    def _get_header(
        self, headers: Dict[str, str], name: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Get a header value case-insensitively.

        Args:
            headers: Dictionary of HTTP headers
            name: Header name to look for (case-insensitive)
            default: Default value if header not found

        Returns:
            Header value or default if not found.
        """
        name_lower = name.lower()
        for key, value in headers.items():
            if key.lower() == name_lower:
                return value
        return default

    def _decode_base64_json(
        self, value: str, field_name: str
    ) -> Optional[Dict[str, Any]]:
        """Decode a base64-encoded JSON value.

        First tries base64 decoding, then falls back to direct JSON parsing.

        Args:
            value: The potentially base64-encoded JSON string
            field_name: Name of the field (for logging)

        Returns:
            Decoded JSON object or None if decoding fails.
        """
        if not value:
            return None

        # Try base64 decoding first
        try:
            decoded_bytes = base64.b64decode(value)
            decoded_str = decoded_bytes.decode("utf-8")
            return json.loads(decoded_str)
        except (base64.binascii.Error, UnicodeDecodeError):
            # Base64 decoding failed, try direct JSON parsing
            logger.debug(
                f"Base64 decoding failed for {field_name}, trying direct JSON parse"
            )
        except json.JSONDecodeError as e:
            # Base64 worked but JSON parsing failed
            logger.warning(f"Malformed JSON in {field_name} after base64 decode: {e}")
            return None

        # Fallback: try direct JSON parsing
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse {field_name} as JSON: {e}")
            return None

    def _parse_delegation_chain(self, value: str) -> List[str]:
        """Parse delegation chain from comma-separated or JSON array format.

        Args:
            value: The delegation chain string (comma-separated or JSON array)

        Returns:
            List of agent IDs in the delegation chain.
        """
        if not value or not value.strip():
            return []

        value = value.strip()

        # Try JSON array format first
        if value.startswith("["):
            try:
                chain = json.loads(value)
                if isinstance(chain, list):
                    return [str(item).strip() for item in chain if item]
            except json.JSONDecodeError:
                logger.debug(
                    "Delegation chain is not valid JSON array, trying comma format"
                )

        # Fall back to comma-separated format
        parts = value.split(",")
        return [part.strip() for part in parts if part.strip()]

    def _parse_delegation_depth(self, value: Optional[str]) -> int:
        """Parse delegation depth as integer.

        Args:
            value: The delegation depth string

        Returns:
            Integer delegation depth, or 0 if parsing fails.
        """
        if not value:
            return 0

        try:
            return int(value)
        except (ValueError, TypeError):
            logger.warning(f"Invalid delegation depth value: {value}, defaulting to 0")
            return 0

    def _extract_raw_eatp_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Extract only EATP headers from the full headers dict.

        Args:
            headers: Full HTTP headers dictionary

        Returns:
            Dictionary containing only EATP headers.
        """
        raw_eatp = {}
        for name in EATP_HEADERS:
            value = self._get_header(headers, name)
            if value is not None:
                raw_eatp[name] = value
        return raw_eatp

    def extract(self, headers: Dict[str, str]) -> ExtractedEATPContext:
        """Extract EATP headers from a request headers dictionary.

        This method parses all EATP headers, handling malformed data gracefully
        by logging warnings and using default values where appropriate.

        Args:
            headers: Dictionary of HTTP headers from the request

        Returns:
            ExtractedEATPContext with parsed EATP information.
        """
        # Extract simple string headers
        trace_id = self._get_header(headers, EATP_TRACE_ID)
        agent_id = self._get_header(headers, EATP_AGENT_ID)
        session_id = self._get_header(headers, EATP_SESSION_ID)
        signature = self._get_header(headers, EATP_SIGNATURE)

        # Extract and decode base64 JSON headers
        human_origin_raw = self._get_header(headers, EATP_HUMAN_ORIGIN)
        human_origin = self._decode_base64_json(human_origin_raw, EATP_HUMAN_ORIGIN)

        constraints_raw = self._get_header(headers, EATP_CONSTRAINTS)
        constraints = self._decode_base64_json(constraints_raw, EATP_CONSTRAINTS)
        if constraints is None:
            constraints = {}

        # Extract delegation chain
        delegation_chain_raw = self._get_header(headers, EATP_DELEGATION_CHAIN)
        delegation_chain = self._parse_delegation_chain(delegation_chain_raw or "")

        # Extract delegation depth
        delegation_depth_raw = self._get_header(headers, EATP_DELEGATION_DEPTH)
        delegation_depth = self._parse_delegation_depth(delegation_depth_raw)

        # Extract raw EATP headers for forwarding
        raw_headers = self._extract_raw_eatp_headers(headers)

        return ExtractedEATPContext(
            trace_id=trace_id,
            agent_id=agent_id,
            human_origin=human_origin,
            delegation_chain=delegation_chain,
            delegation_depth=delegation_depth,
            constraints=constraints,
            session_id=session_id,
            signature=signature,
            raw_headers=raw_headers,
        )

    def to_headers(self, context: ExtractedEATPContext) -> Dict[str, str]:
        """Convert an ExtractedEATPContext back to HTTP headers.

        This is useful for forwarding EATP trust context to downstream services.
        Only includes headers for non-None/non-empty values.

        Args:
            context: The ExtractedEATPContext to convert

        Returns:
            Dictionary of HTTP headers suitable for forwarding.
        """
        headers: Dict[str, str] = {}

        # Simple string headers
        if context.trace_id is not None:
            headers[EATP_TRACE_ID] = context.trace_id

        if context.agent_id is not None:
            headers[EATP_AGENT_ID] = context.agent_id

        if context.session_id is not None:
            headers[EATP_SESSION_ID] = context.session_id

        if context.signature is not None:
            headers[EATP_SIGNATURE] = context.signature

        # Base64-encoded JSON headers
        if context.human_origin is not None:
            encoded = base64.b64encode(
                json.dumps(context.human_origin).encode()
            ).decode()
            headers[EATP_HUMAN_ORIGIN] = encoded

        if context.constraints:
            encoded = base64.b64encode(
                json.dumps(context.constraints).encode()
            ).decode()
            headers[EATP_CONSTRAINTS] = encoded

        # Delegation chain as JSON array
        if context.delegation_chain:
            headers[EATP_DELEGATION_CHAIN] = json.dumps(context.delegation_chain)

        # Delegation depth
        if context.delegation_depth > 0:
            headers[EATP_DELEGATION_DEPTH] = str(context.delegation_depth)

        return headers
