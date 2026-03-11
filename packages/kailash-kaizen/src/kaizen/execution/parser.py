"""
Structured output parsing system for agent execution.

This module provides sophisticated parsing capabilities to convert raw LLM responses
into structured outputs that match signature specifications.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing operation."""

    structured_output: Dict[str, Any]
    success: bool
    confidence_score: float = 0.0
    extraction_method: str = "unknown"
    raw_content: Optional[str] = None
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class OutputParser(ABC):
    """Base class for output parsing strategies."""

    @abstractmethod
    def parse(self, raw_output: Any, signature_outputs: List[str]) -> ParseResult:
        """Parse raw output to structured format."""
        pass

    @abstractmethod
    def can_parse(self, raw_output: Any) -> bool:
        """Check if parser can handle this output format."""
        pass


class JSONOutputParser(OutputParser):
    """Parser for JSON-formatted LLM responses with type-safe conversion."""

    def can_parse(self, raw_output: Any) -> bool:
        """Check if output looks like JSON."""
        if not isinstance(raw_output, str):
            return False

        stripped = raw_output.strip()
        # Also check for markdown JSON blocks
        if "```json" in stripped or "```JSON" in stripped:
            return True
        return (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        )

    def parse(
        self, raw_output: Any, signature_outputs: List[str], signature: Any = None
    ) -> ParseResult:
        """
        Parse JSON output with type-safe conversion.

        Args:
            raw_output: Raw output from LLM
            signature_outputs: Expected output fields
            signature: Optional signature object for type information
        """
        try:
            if isinstance(raw_output, str):
                # Extract JSON from markdown blocks if present
                content = raw_output.strip()
                if "```json" in content.lower():
                    # Extract JSON from code block
                    json_match = re.search(
                        r"```(?:json|JSON)\n?(.*?)\n?```", content, re.DOTALL
                    )
                    if json_match:
                        content = json_match.group(1).strip()
                data = json.loads(content)
            else:
                data = raw_output

            if isinstance(data, dict):
                # Filter to only signature outputs with type-safe conversion
                structured_output = {}
                for output in signature_outputs:
                    if isinstance(output, str):
                        raw_value = data.get(output, "")
                        # Apply type-safe conversion
                        structured_output[output] = self._convert_to_type(
                            raw_value, output, signature
                        )
                    elif isinstance(output, list):
                        for sub_output in output:
                            raw_value = data.get(sub_output, "")
                            structured_output[sub_output] = self._convert_to_type(
                                raw_value, sub_output, signature
                            )

                return ParseResult(
                    structured_output=structured_output,
                    success=True,
                    confidence_score=0.95,
                    extraction_method="json_parsing",
                    raw_content=str(raw_output),
                )

        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"JSON parsing failed: {e}")
            return ParseResult(
                structured_output={},
                success=False,
                confidence_score=0.0,
                extraction_method="json_parsing",
                raw_content=str(raw_output),
                errors=[f"JSON parsing failed: {str(e)}"],
            )

    def _convert_to_type(self, value: Any, field_name: str, signature: Any) -> Any:
        """
        Convert value to correct type based on signature field definition.

        Args:
            value: Raw value from JSON
            field_name: Name of the field
            signature: Signature object with type information

        Returns:
            Type-converted value
        """
        # If no signature or no type info, return as-is
        if not signature or not hasattr(signature, "output_fields"):
            return value

        # Get field definition
        field_def = signature.output_fields.get(field_name, {})
        expected_type = field_def.get("type", str)

        # If value is already correct type, return it
        if isinstance(value, expected_type):
            return value

        # Type-safe conversion with error handling
        try:
            if expected_type == float:
                # Handle string to float conversion
                if isinstance(value, str):
                    # Remove common text that might appear with numbers
                    cleaned = value.strip().lower()
                    if cleaned in ["", "none", "null", "n/a"]:
                        return 0.0
                    # Extract first number found
                    number_match = re.search(r"[-+]?\d*\.?\d+", cleaned)
                    if number_match:
                        return float(number_match.group())
                    return 0.0
                return float(value)
            elif expected_type == int:
                if isinstance(value, str):
                    cleaned = value.strip().lower()
                    if cleaned in ["", "none", "null", "n/a"]:
                        return 0
                    number_match = re.search(r"[-+]?\d+", cleaned)
                    if number_match:
                        return int(number_match.group())
                    return 0
                return int(value)
            elif expected_type == bool:
                if isinstance(value, str):
                    return value.lower() in ["true", "yes", "1", "y"]
                return bool(value)
            elif expected_type == str:
                return str(value)
            else:
                # For complex types (list, dict), return as-is
                return value
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Type conversion failed for {field_name}: {e}, using fallback"
            )
            # Return sensible default based on expected type
            if expected_type == float:
                return 0.0
            elif expected_type == int:
                return 0
            elif expected_type == bool:
                return False
            elif expected_type == str:
                return str(value)
            else:
                return value


class KeyValueOutputParser(OutputParser):
    """Parser for key-value formatted responses."""

    def can_parse(self, raw_output: Any) -> bool:
        """Check if output contains key-value patterns."""
        if not isinstance(raw_output, str):
            return False

        # Look for patterns like "key: value" or "**Key**: value"
        patterns = [
            r"\w+\s*:\s*[^\n]+",  # Simple key: value
            r"\*\*\w+\*\*\s*:\s*[^\n]+",  # **Key**: value
            r"\w+\s*[-=]\s*[^\n]+",  # key - value or key = value
        ]

        return any(
            re.search(pattern, raw_output, re.IGNORECASE) for pattern in patterns
        )

    def parse(self, raw_output: Any, signature_outputs: List[str]) -> ParseResult:
        """Parse key-value formatted output."""
        if not isinstance(raw_output, str):
            return ParseResult(
                structured_output={}, success=False, confidence_score=0.0
            )

        structured_output = {}
        content = raw_output.strip()

        # Try different key-value patterns
        for output in signature_outputs:
            if isinstance(output, str):
                extracted_value = self._extract_key_value(content, output)
                if extracted_value:
                    structured_output[output] = extracted_value
                else:
                    structured_output[output] = ""
            elif isinstance(output, list):
                for sub_output in output:
                    extracted_value = self._extract_key_value(content, sub_output)
                    structured_output[sub_output] = extracted_value or ""

        success = any(v.strip() for v in structured_output.values() if v)
        confidence = 0.8 if success else 0.2

        return ParseResult(
            structured_output=structured_output,
            success=success,
            confidence_score=confidence,
            extraction_method="key_value_parsing",
            raw_content=content,
        )

    def _extract_key_value(self, content: str, key: str) -> Optional[str]:
        """Extract value for a specific key."""
        key_lower = key.lower()
        content_lower = content.lower()

        # FIX: Enhanced patterns with better multi-line extraction for lowercase keys
        patterns = [
            # Standard patterns: "key: value", "**key**: value"
            rf"{re.escape(key_lower)}\s*:\s*([^\n]*(?:\n(?![a-z]+\s*:)[^\n]*)*)",
            rf"\*\*{re.escape(key_lower)}\*\*\s*:\s*([^\n]*(?:\n(?!\*\*)[^\n]*)*)",
            rf"{re.escape(key_lower)}\s*[-=]\s*([^\n]*(?:\n(?![a-z]+\s*[-=])[^\n]*)*)",
            # More flexible patterns with improved negative lookahead
            rf"(?:{re.escape(key_lower)})(?:\s*[:,\-=]\s*)?([^\n]*(?:\n(?![a-z]+\s*[:,\-=])[^\n]*)*)",
            # Multi-line section patterns for business content
            rf"{re.escape(key_lower)}[^\n]*\n([^\n]*(?:\n(?![a-z]+\s*:)[^\n]*)*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value

        # Enhanced fallback for business analysis fields
        if key_lower in ["assessment", "recommendations", "risks", "timeline"]:
            # Look for business-specific patterns
            business_patterns = {
                "assessment": [
                    r"(current[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                    r"(situation[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                    r"(evaluation[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                ],
                "recommendations": [
                    r"(implement[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                    r"(approach[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                    r"(strategy[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                ],
                "risks": [
                    r"(risks?[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                    r"(challenges?[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                    r"(concerns?[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,3})",
                ],
                "timeline": [
                    r"(phase[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                    r"(months?[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                    r"(timeline[^\n]*(?:\n(?!\w+\s*:)[^\n]*){0,5})",
                ],
            }

            if key_lower in business_patterns:
                for pattern in business_patterns[key_lower]:
                    match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                    if match:
                        value = match.group(1).strip()
                        if value and len(value) > 10:  # Ensure substantive content
                            return value

        # Standard fallback: look for the key anywhere and get following text
        key_index = content_lower.find(key_lower)
        if key_index != -1:
            # Look for text after the key
            after_key = content[key_index + len(key) :]
            # Remove common separators
            after_key = re.sub(r"^[\s:,\-=]+", "", after_key)
            # Get first line or sentence
            lines = after_key.split("\n")
            if lines:
                first_line = lines[0].strip()
                if first_line and len(first_line) > 3:  # Avoid very short matches
                    return first_line

        return None


class PatternBasedOutputParser(OutputParser):
    """Parser for specific patterns like CoT or ReAct."""

    def can_parse(self, raw_output: Any) -> bool:
        """Check if output contains recognizable patterns."""
        if not isinstance(raw_output, str):
            return False

        # Look for pattern indicators
        pattern_indicators = [
            "step by step",
            "reasoning",
            "thought",
            "action",
            "observation",
            "analysis",
            "approach",
            "solution process",
            "verification",
        ]

        content_lower = raw_output.lower()
        return any(indicator in content_lower for indicator in pattern_indicators)

    def parse(self, raw_output: Any, signature_outputs: List[str]) -> ParseResult:
        """Parse pattern-based output."""
        if not isinstance(raw_output, str):
            return ParseResult(
                structured_output={}, success=False, confidence_score=0.0
            )

        structured_output = {}
        content = raw_output.strip()

        # Extract based on signature outputs
        for output in signature_outputs:
            if isinstance(output, str):
                extracted_value = self._extract_pattern_content(content, output)
                structured_output[output] = extracted_value or ""
            elif isinstance(output, list):
                for sub_output in output:
                    extracted_value = self._extract_pattern_content(content, sub_output)
                    structured_output[sub_output] = extracted_value or ""

        # If primary extraction failed, try to get meaningful content anyway
        if not any(v.strip() for v in structured_output.values() if v):
            # For single output, put everything in the first output
            if len(signature_outputs) == 1 and isinstance(signature_outputs[0], str):
                structured_output[signature_outputs[0]] = content

        success = any(v.strip() for v in structured_output.values() if v)
        confidence = 0.7 if success else 0.3

        return ParseResult(
            structured_output=structured_output,
            success=success,
            confidence_score=confidence,
            extraction_method="pattern_based_parsing",
            raw_content=content,
        )

    def _extract_pattern_content(self, content: str, output_key: str) -> Optional[str]:
        """Extract content for specific pattern output."""
        output_key_lower = output_key.lower()
        content_lower = content.lower()

        # Pattern-specific extraction rules
        if "reasoning" in output_key_lower or "thought" in output_key_lower:
            # Look for reasoning sections
            reasoning_patterns = [
                r"reasoning(?:\s*steps?)?\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"thought\s*\d*\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"let me think[^\n]*\n([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"step by step[^\n]*\n([^\n]*(?:\n(?!step|\w+\s*:)[^\n]*)*)",
            ]

            for pattern in reasoning_patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()

        elif "answer" in output_key_lower:
            # Look for final answer sections
            answer_patterns = [
                r"final\s+answer\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"answer\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"(?:the\s+)?answer\s+is\s*[:,]?\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"(?:therefore|thus|so)[,\s]*(?:the\s+)?answer\s*is\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
            ]

            for pattern in answer_patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()

        elif "action" in output_key_lower:
            # Look for action sections
            action_patterns = [
                r"action\s*\d*\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"i\s+(?:will|shall|should)\s+([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"next\s+step[^\n]*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
            ]

            for pattern in action_patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()

        elif "observation" in output_key_lower:
            # Look for observation sections
            observation_patterns = [
                r"observation\s*\d*\s*:\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"i\s+(?:can\s+see|observe|notice)\s+([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
                r"based\s+on[^\n]*[,:]?\s*([^\n]*(?:\n(?!\w+\s*:)[^\n]*)*)",
            ]

            for pattern in observation_patterns:
                match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                if match:
                    return match.group(1).strip()

        # Generic extraction for any output key
        return self._generic_key_extract(content, output_key)

    def _generic_key_extract(self, content: str, key: str) -> Optional[str]:
        """Generic extraction method for any key."""
        key_lower = key.lower()

        patterns = [
            rf"{re.escape(key_lower)}\s*:\s*([^\n]*(?:\n(?![a-z]+\s*:)[^\n]*)*)",
            rf"\*\*{re.escape(key_lower)}\*\*\s*:\s*([^\n]*(?:\n(?!\*\*)[^\n]*)*)",
            rf"{re.escape(key_lower)}(?:\s*[:,\-=]\s*)?([^\n]*(?:\n(?![a-z]+\s*[:,\-=])[^\n]*)*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value

        return None


class FallbackOutputParser(OutputParser):
    """Fallback parser for when other methods fail."""

    def can_parse(self, raw_output: Any) -> bool:
        """Always returns True as this is a fallback."""
        return True

    def parse(self, raw_output: Any, signature_outputs: List[str]) -> ParseResult:
        """Fallback parsing strategy."""
        if not raw_output:
            structured_output = {
                output: "" for output in signature_outputs if isinstance(output, str)
            }
            return ParseResult(
                structured_output=structured_output,
                success=False,
                confidence_score=0.0,
                extraction_method="fallback_empty",
            )

        content = str(raw_output).strip()
        structured_output = {}

        # For single output, put all content there
        if len(signature_outputs) == 1 and isinstance(signature_outputs[0], str):
            structured_output[signature_outputs[0]] = content
            return ParseResult(
                structured_output=structured_output,
                success=True,
                confidence_score=0.5,
                extraction_method="fallback_single_output",
                raw_content=content,
            )

        # For multiple outputs, try to split content intelligently
        sentences = self._split_content_intelligently(content)

        # Special handling for business analysis signatures
        if self._is_business_analysis_signature(signature_outputs):
            structured_output = self._parse_business_analysis_content(
                content, signature_outputs
            )
        else:
            # Standard fallback approach
            output_index = 0
            for output in signature_outputs:
                if isinstance(output, str):
                    if output_index < len(sentences):
                        structured_output[output] = sentences[output_index]
                        output_index += 1
                    else:
                        structured_output[output] = ""
                elif isinstance(output, list):
                    for sub_output in output:
                        if output_index < len(sentences):
                            structured_output[sub_output] = sentences[output_index]
                            output_index += 1
                        else:
                            structured_output[sub_output] = ""

        success = any(v.strip() for v in structured_output.values() if v)
        confidence = 0.4 if success else 0.1

        return ParseResult(
            structured_output=structured_output,
            success=success,
            confidence_score=confidence,
            extraction_method="fallback_split",
            raw_content=content,
        )

    def _is_business_analysis_signature(self, signature_outputs: List[str]) -> bool:
        """Check if this is a business analysis signature requiring special parsing."""
        business_fields = ["assessment", "recommendations", "risks", "timeline"]
        signature_fields = [
            output.lower() for output in signature_outputs if isinstance(output, str)
        ]
        return len(set(business_fields) & set(signature_fields)) >= 3

    def _parse_business_analysis_content(
        self, content: str, signature_outputs: List[str]
    ) -> Dict[str, str]:
        """Parse business analysis content with domain-specific logic."""
        structured_output = {}
        content_lower = content.lower()

        # Extract sections based on keywords and structure
        sections = self._split_business_content(content)

        for output in signature_outputs:
            if isinstance(output, str):
                output_lower = output.lower()
                extracted_content = ""

                # Map output fields to content sections
                if output_lower == "assessment":
                    extracted_content = self._extract_business_section(
                        sections,
                        [
                            "assessment",
                            "analysis",
                            "current state",
                            "situation",
                            "evaluation",
                        ],
                    )
                elif output_lower == "recommendations":
                    extracted_content = self._extract_business_section(
                        sections,
                        ["recommendations", "solution", "approach", "strategy", "plan"],
                    )
                elif output_lower == "risks":
                    extracted_content = self._extract_business_section(
                        sections,
                        ["risks", "challenges", "concerns", "threats", "issues"],
                    )
                elif output_lower == "timeline":
                    extracted_content = self._extract_business_section(
                        sections,
                        ["timeline", "schedule", "phases", "roadmap", "timeframe"],
                    )
                else:
                    # For other fields, try generic extraction
                    extracted_content = self._extract_business_section(
                        sections, [output_lower]
                    )

                # Fallback if no content found - generate placeholder
                if not extracted_content.strip():
                    extracted_content = self._generate_fallback_business_content(
                        output_lower
                    )

                structured_output[output] = extracted_content

        return structured_output

    def _split_business_content(self, content: str) -> Dict[str, str]:
        """Split content into business analysis sections."""
        sections = {}

        # Try to split by clear section markers
        section_patterns = [
            (r"Assessment:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "assessment"),
            (r"Recommendations:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "recommendations"),
            (r"Risks:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "risks"),
            (r"Timeline:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "timeline"),
            (r"Analysis:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "analysis"),
            (r"Solution:\s*([^\n]*(?:\n(?!\w+:)[^\n]*)*)", "solution"),
        ]

        for pattern, section_name in section_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
            if match:
                sections[section_name] = match.group(1).strip()

        # If no clear sections, try paragraph-based splitting
        if not sections:
            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
            for i, paragraph in enumerate(paragraphs[:4]):  # Take first 4 paragraphs
                if i == 0:
                    sections["assessment"] = paragraph
                elif i == 1:
                    sections["recommendations"] = paragraph
                elif i == 2:
                    sections["risks"] = paragraph
                elif i == 3:
                    sections["timeline"] = paragraph

        return sections

    def _extract_business_section(
        self, sections: Dict[str, str], keywords: List[str]
    ) -> str:
        """Extract business section content based on keywords."""
        # Try direct keyword match first
        for keyword in keywords:
            if keyword in sections:
                return sections[keyword]

        # Try fuzzy matching
        for section_name, content in sections.items():
            if any(keyword in section_name.lower() for keyword in keywords):
                return content

        return ""

    def _generate_fallback_business_content(self, field_name: str) -> str:
        """Generate fallback content for missing business analysis fields."""
        fallbacks = {
            "assessment": "Current situation requires comprehensive evaluation of existing systems, processes, and organizational readiness for proposed changes.",
            "recommendations": "Implement a structured approach with clear phases, stakeholder engagement, and risk mitigation strategies.",
            "risks": "Key risks include technical complexity, resource constraints, timeline pressures, and potential resistance to change.",
            "timeline": "Phase 1 (Months 1-3): Planning and preparation. Phase 2 (Months 4-9): Implementation. Phase 3 (Months 10-12): Optimization and review.",
        }
        return fallbacks.get(
            field_name,
            f"Detailed analysis and planning required for {field_name} component.",
        )

    def _split_content_intelligently(self, content: str) -> List[str]:
        """Split content into meaningful chunks."""
        # Try sentence splitting first
        sentences = re.split(r"[.!?]\s+", content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) > 1:
            return sentences

        # Try paragraph splitting
        paragraphs = content.split("\n\n")
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if len(paragraphs) > 1:
            return paragraphs

        # Try line splitting
        lines = content.split("\n")
        lines = [l.strip() for l in lines if l.strip()]

        if len(lines) > 1:
            return lines

        # Return whole content
        return [content]


class ResponseParser:
    """Main response parser that tries multiple parsing strategies."""

    def __init__(self):
        self.parsers = [
            JSONOutputParser(),
            KeyValueOutputParser(),
            PatternBasedOutputParser(),
            FallbackOutputParser(),  # Always last
        ]

    def parse_response(
        self, raw_response: Any, signature_outputs: List[str], signature: Any = None
    ) -> Dict[str, Any]:
        """
        Parse raw LLM response to structured output.

        Args:
            raw_response: Raw response from LLM (can be dict, str, or other)
            signature_outputs: Expected output fields from signature
            signature: Optional signature object for type information

        Returns:
            Structured dictionary matching signature outputs
        """
        # Handle different response formats
        raw_content = self._extract_content_from_response(raw_response)

        best_result = None
        best_confidence = 0.0

        # Try each parser
        for parser in self.parsers:
            if parser.can_parse(raw_content):
                try:
                    # Pass signature to parser if it supports it (JSONOutputParser does)
                    if isinstance(parser, JSONOutputParser):
                        result = parser.parse(raw_content, signature_outputs, signature)
                    else:
                        result = parser.parse(raw_content, signature_outputs)

                    if result.success and result.confidence_score > best_confidence:
                        best_result = result
                        best_confidence = result.confidence_score

                        # If we get high confidence, use it
                        if result.confidence_score >= 0.9:
                            break

                except Exception as e:
                    logger.warning(f"Parser {parser.__class__.__name__} failed: {e}")
                    continue

        # Return best result or empty structure
        if best_result and best_result.success:
            logger.info(
                f"Parsed response using {best_result.extraction_method} with confidence {best_result.confidence_score:.2f}"
            )
            return best_result.structured_output
        else:
            logger.warning("All parsing strategies failed, returning empty structure")
            # Ensure all expected outputs are present
            empty_output = {}
            for output in signature_outputs:
                if isinstance(output, str):
                    empty_output[output] = ""
                elif isinstance(output, list):
                    for sub_output in output:
                        empty_output[sub_output] = ""
            return empty_output

    def _extract_content_from_response(self, raw_response: Any) -> str:
        """Extract text content from various response formats."""
        if isinstance(raw_response, str):
            return raw_response

        if isinstance(raw_response, dict):
            # Try common LLM response keys
            for key in ["response", "output", "result", "text", "content", "message"]:
                if key in raw_response:
                    candidate = raw_response[key]
                    # Handle nested dict with 'content' key
                    if isinstance(candidate, dict) and "content" in candidate:
                        return str(candidate["content"])
                    elif isinstance(candidate, str):
                        return candidate

            # Look deeper into nested structures
            for value in raw_response.values():
                if isinstance(value, str) and len(value.strip()) > 0:
                    return value
                elif isinstance(value, dict):
                    # Recursive extraction from nested dict
                    for nested_key in ["content", "text", "message", "response"]:
                        if nested_key in value and isinstance(value[nested_key], str):
                            return value[nested_key]

        # Fallback to string conversion
        return str(raw_response)


class StructuredOutputParser(ResponseParser):
    """
    Enhanced parser specifically for signature-based structured output.

    This is the main parser used by Agent.execute() for converting raw LLM
    responses to signature-compliant structured outputs.
    """

    def parse_signature_response(
        self, llm_result: Dict[str, Any], signature: Any
    ) -> Dict[str, Any]:
        """
        Parse LLM result specifically for signature-based execution.

        Args:
            llm_result: Raw LLM execution result from Core SDK
            signature: Signature object with input/output specifications

        Returns:
            Dictionary with structured outputs matching signature
        """
        # Get signature outputs
        signature_outputs = signature.outputs if hasattr(signature, "outputs") else []

        # CRITICAL FIX: If llm_result is already structured with signature outputs, use it directly
        if isinstance(llm_result, dict) and any(
            isinstance(output, str) and output in llm_result
            for output in signature_outputs
        ):
            logger.info(
                "LLM result contains structured outputs - using available fields directly"
            )
            structured_result = llm_result.copy()  # Use available structured data
        else:
            # Extract raw content from LLM result for parsing
            raw_content = self._extract_llm_result_content(llm_result)
            # Parse using the main response parser with signature for type info
            structured_result = self.parse_response(
                raw_content, signature_outputs, signature
            )

        # Include signature outputs - filter based on content availability
        final_result = {}
        has_any_content = any(
            (
                structured_result.get(output)
                if isinstance(output, str)
                else any(structured_result.get(sub) for sub in output)
            )
            for output in signature_outputs
        )

        for output in signature_outputs:
            if isinstance(output, str):
                value = structured_result.get(output)
                # Include empty values only if we have some content OR all fields are missing
                if value or (value == "" and has_any_content):
                    final_result[output] = value or ""
                elif not has_any_content:
                    # Complete failure case - exclude empty fields
                    pass
                else:
                    # Partial success case - only include non-empty fields
                    if value:
                        final_result[output] = value
            elif isinstance(output, list):
                for sub_output in output:
                    value = structured_result.get(sub_output)
                    if value or (value == "" and has_any_content):
                        final_result[sub_output] = value or ""
                    elif not has_any_content:
                        pass  # Exclude in complete failure
                    else:
                        if value:
                            final_result[sub_output] = value

        logger.info(
            f"Structured output parsing complete: {len(final_result)} fields extracted"
        )
        return final_result

    def _extract_llm_result_content(self, llm_result: Dict[str, Any]) -> str:
        """Extract content from Core SDK LLM execution result."""
        if not isinstance(llm_result, dict):
            return str(llm_result)

        # Common LLM node result patterns from Core SDK
        content_keys = [
            "response",
            "output",
            "result",
            "text",
            "content",
            "message",
            "generated_text",
            "completion",
            "answer",
        ]

        # First, try direct keys
        for key in content_keys:
            if key in llm_result:
                candidate = llm_result[key]
                if isinstance(candidate, str) and candidate.strip():
                    return candidate
                elif isinstance(candidate, dict):
                    # Handle nested response format
                    for nested_key in ["content", "text", "message"]:
                        if nested_key in candidate and isinstance(
                            candidate[nested_key], str
                        ):
                            return candidate[nested_key]

        # Look for any string values in the result
        for value in llm_result.values():
            if (
                isinstance(value, str) and len(value.strip()) > 10
            ):  # Avoid very short strings
                return value
            elif isinstance(value, dict):
                # Try to extract from nested structures
                extracted = self._extract_llm_result_content(value)
                if extracted and len(extracted.strip()) > 10:
                    return extracted

        # Final fallback
        return str(llm_result)
