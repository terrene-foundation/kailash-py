"""
AI-Enhanced Threat Detection Node

Extends Core SDK's ThreatDetectionNode with LLM-powered capabilities for advanced
threat intelligence and natural language reporting.

Architecture:
- Foundation: kailash.nodes.security.ThreatDetectionNode (rule-based)
- Enhancement: LLM-powered threat intelligence and contextual assessment
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node
from kailash.nodes.security.threat_detection import ThreatDetectionNode

from kaizen.nodes.ai.llm_agent import LLMAgentNode

logger = logging.getLogger(__name__)


class AIThreatDetectionNode(Node):
    """
    AI-Enhanced Threat Detection for advanced security analysis.

    This node extends Core SDK's ThreatDetectionNode with LLM-powered capabilities:
    - Natural language threat reporting for security teams
    - Contextual threat assessment using semantic understanding
    - LLM-powered threat intelligence correlation
    - Advanced pattern recognition beyond rule-based detection

    **Architectural Pattern:**
    1. Core SDK ThreatDetectionNode performs rule-based detection (foundation)
    2. LLM analyzes detected threats for contextual insights (enhancement)
    3. Fallback to Core SDK if LLM unavailable (graceful degradation)

    **Usage:**
    ```python
    from kaizen.nodes.security import AIThreatDetectionNode

    workflow.add_node("ai_threat", AIThreatDetectionNode(
        provider="openai",
        model="gpt-4o-mini",
        enable_intelligence=True,
        enable_narratives=True,
        # Core SDK parameters
        detection_rules=["brute_force", "privilege_escalation", "data_exfiltration"],
        response_actions=["alert", "block_ip"],
        real_time=True,
        severity_threshold="medium"
    ))
    ```

    **Integration with Core SDK:**
    - Uses ThreatDetectionNode for rule-based foundation
    - Adds LLM layer for contextual threat intelligence
    - Maintains backward compatibility with Core SDK APIs
    - Gracefully degrades to Core SDK if LLM fails

    **Outputs:**
    - threats: List of detected threats with severity and details
    - threat_summary: High-level summary of security posture
    - ai_narrative: Natural language threat report (optional)
    - ai_recommendations: LLM-generated response recommendations (optional)
    - ai_intelligence: Correlated threat intelligence (optional)
    - rule_based_analysis: Core SDK foundation analysis results
    """

    def __init__(
        self,
        name: str = "ai_threat_detection",
        # AI Enhancement Parameters
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        enable_intelligence: bool = True,
        enable_narratives: bool = True,
        enable_recommendations: bool = True,
        narrative_style: str = "technical",  # "executive", "technical", "detailed"
        temperature: float = 0.3,
        # Core SDK Parameters (pass through to ThreatDetectionNode)
        detection_rules: Optional[List[str]] = None,
        response_actions: Optional[List[str]] = None,
        real_time: bool = True,
        severity_threshold: str = "medium",
        response_time_target_ms: int = 100,
        **kwargs,
    ):
        """
        Initialize AI-Enhanced Threat Detection Node.

        Args:
            name: Node identifier
            provider: LLM provider ("openai", "anthropic", "ollama")
            model: Model name (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022")
            enable_intelligence: Generate threat intelligence correlation
            enable_narratives: Generate natural language threat reports
            enable_recommendations: Generate response recommendations
            narrative_style: Report style (executive/technical/detailed)
            temperature: LLM temperature for response generation
            detection_rules: Threat types to detect
            response_actions: Automated response actions
            real_time: Enable real-time threat detection
            severity_threshold: Minimum severity for alerts
            response_time_target_ms: Target response time in milliseconds
        """
        super().__init__(name=name, **kwargs)

        # AI Enhancement Configuration
        self.provider = provider
        self.model = model
        self.enable_intelligence = enable_intelligence
        self.enable_narratives = enable_narratives
        self.enable_recommendations = enable_recommendations
        self.narrative_style = narrative_style
        self.temperature = temperature

        # Core SDK Foundation Configuration
        self.detection_rules = detection_rules or [
            "brute_force",
            "privilege_escalation",
            "data_exfiltration",
            "insider_threat",
            "anomalous_behavior",
        ]
        self.response_actions = response_actions or ["alert", "block_ip"]
        self.real_time = real_time
        self.severity_threshold = severity_threshold
        self.response_time_target_ms = response_time_target_ms

        # Initialize Core SDK foundation node (will be created at execution time)
        self._core_threat_node = None

        logger.info(
            f"Initialized AIThreatDetectionNode with provider={provider}, "
            f"model={model}, intelligence={enable_intelligence}, "
            f"narratives={enable_narratives}"
        )

    def _get_core_threat_node(self) -> ThreatDetectionNode:
        """Get or create Core SDK ThreatDetectionNode instance."""
        if self._core_threat_node is None:
            self._core_threat_node = ThreatDetectionNode(
                name=f"{self.name}_core",
                detection_rules=self.detection_rules,
                response_actions=self.response_actions,
                real_time=self.real_time,
                severity_threshold=self.severity_threshold,
                response_time_target_ms=self.response_time_target_ms,
            )
        return self._core_threat_node

    def _generate_system_prompt(self) -> str:
        """Generate system prompt for LLM threat analysis."""
        style_instructions = {
            "executive": "Provide high-level executive summary suitable for C-level stakeholders. Focus on business impact and strategic recommendations.",
            "technical": "Provide technical analysis suitable for security operations team. Include technical details and tactical response guidance.",
            "detailed": "Provide comprehensive analysis including technical details, context, and strategic recommendations. Suitable for incident reports.",
        }

        return f"""You are an expert cybersecurity threat analyst specializing in threat intelligence and incident response.

Your task is to analyze detected security threats and provide clear, actionable intelligence for security teams.

**Report Style:** {style_instructions.get(self.narrative_style, style_instructions['technical'])}

**Your Analysis Should Include:**
1. Threat narrative explaining what happened and why it matters
2. Contextual assessment of threat severity and potential impact
3. Correlation with known threat patterns and actor TTPs
4. Specific recommendations for response and mitigation

Focus on delivering intelligence that enables effective security decision-making and incident response.
"""

    def _generate_analysis_prompt(
        self,
        rule_based_results: Dict[str, Any],
        threats: List[Dict[str, Any]],
    ) -> str:
        """Generate prompt for LLM to analyze rule-based threat detection results."""
        threat_summary = "\n".join(
            [
                f"- {t.get('type', 'unknown').upper()}: Severity {t.get('severity', 'unknown')}, "
                f"Source: {t.get('source', 'N/A')}, "
                f"Details: {t.get('details', 'No details')}"
                for t in threats[:10]  # Limit to top 10 for context
            ]
        )

        return f"""Analyze the following threat detection results:

**Detection Summary:**
- Total Threats Detected: {len(threats)}
- High Severity: {sum(1 for t in threats if t.get('severity') == 'high')}
- Medium Severity: {sum(1 for t in threats if t.get('severity') == 'medium')}
- Low Severity: {sum(1 for t in threats if t.get('severity') == 'low')}

**Detected Threats:**
{threat_summary if threat_summary else "No threats detected"}

**Detection Context:**
- Real-time Detection: {self.real_time}
- Detection Rules: {', '.join(self.detection_rules)}
- Severity Threshold: {self.severity_threshold}
- Response Time Target: {self.response_time_target_ms}ms

Based on this threat detection data, provide:
1. Threat Narrative: Clear explanation of detected threats and their significance
2. Contextual Assessment: Analysis of threat patterns, potential attack campaigns, and business impact
3. Threat Intelligence: Correlation with known attack patterns, TTPs, and threat actors
4. Response Recommendations: Specific actions for security team (prioritized by impact)

Your analysis should help security teams understand:
- What threats were detected and why they matter
- How these threats fit into broader attack patterns
- What actions should be taken immediately vs. strategically
"""

    def _call_llm_for_intelligence(
        self,
        rule_based_results: Dict[str, Any],
        threats: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Call LLM for threat intelligence and contextual analysis.

        Uses LLMAgentNode to generate natural language threat reports and
        recommendations based on rule-based threat detection results.
        """
        try:
            # Generate prompts
            system_prompt = self._generate_system_prompt()
            analysis_prompt = self._generate_analysis_prompt(
                rule_based_results, threats
            )

            # Create LLM node and execute
            llm_node = LLMAgentNode()
            result = llm_node.execute(
                {
                    "provider": self.provider,
                    "model": self.model,
                    "messages": [{"role": "user", "content": analysis_prompt}],
                    "system_prompt": system_prompt,
                    "temperature": self.temperature,
                }
            )

            # Parse LLM response
            if "error" in result:
                logger.error(f"LLM threat intelligence failed: {result['error']}")
                return {
                    "ai_available": False,
                    "narrative": f"AI intelligence failed: {result['error']}",
                    "intelligence": {},
                    "recommendations": [],
                    "error": result["error"],
                }

            # Extract response content
            response_content = result.get("response", "")

            # Parse structured response
            # Expected format from LLM:
            # 1. Threat Narrative: ...
            # 2. Contextual Assessment: ...
            # 3. Threat Intelligence: ...
            # 4. Response Recommendations: ...

            narrative = response_content
            recommendations = []
            intelligence = {}

            # Try to extract recommendations from response
            if (
                "Response Recommendations:" in response_content
                or "recommendations:" in response_content.lower()
            ):
                lines = response_content.split("\n")
                in_recommendations = False
                for line in lines:
                    if "recommendation" in line.lower() and ":" in line:
                        in_recommendations = True
                        continue
                    if in_recommendations and line.strip().startswith(("-", "*", "•")):
                        recommendations.append(line.strip().lstrip("-*•").strip())

            # Try to extract threat intelligence section
            if "Threat Intelligence:" in response_content:
                intelligence_section = response_content.split("Threat Intelligence:")[1]
                if "Response Recommendations:" in intelligence_section:
                    intelligence_section = intelligence_section.split(
                        "Response Recommendations:"
                    )[0]
                intelligence = {"analysis": intelligence_section.strip()}

            return {
                "ai_available": True,
                "narrative": narrative,
                "intelligence": intelligence,
                "recommendations": recommendations,
                "error": None,
            }

        except Exception as e:
            logger.error(f"LLM threat intelligence failed: {e}", exc_info=True)
            return {
                "ai_available": False,
                "narrative": f"AI intelligence failed: {str(e)}",
                "intelligence": {},
                "recommendations": [],
                "error": str(e),
            }

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute AI-enhanced threat detection.

        Args:
            input_data: Must contain:
                - events: List of security events to analyze
                - Optional: context, baseline_data

        Returns:
            Dict containing:
                - threats: List of detected threats
                - threat_summary: High-level security posture summary
                - ai_narrative: Natural language threat report (if enabled)
                - ai_recommendations: Response recommendations (if enabled)
                - ai_intelligence: Threat intelligence correlation (if enabled)
                - rule_based_analysis: Core SDK foundation results
                - analysis_metadata: Execution details
        """
        try:
            logger.info("Executing AI threat detection")

            # Step 1: Execute Core SDK rule-based threat detection (foundation)
            core_node = self._get_core_threat_node()
            rule_based_results = core_node.execute(input_data)

            logger.info(
                f"Core SDK detection complete: {len(rule_based_results.get('threats', []))} threats, "
                f"highest_severity={rule_based_results.get('highest_severity', 'none')}"
            )

            # Step 2: Extract threats from rule-based analysis
            threats = rule_based_results.get("threats", [])
            threat_summary = rule_based_results.get("summary", {})

            # Step 3: Prepare result with foundation analysis
            result = {
                "threats": threats,
                "threat_summary": threat_summary,
                "rule_based_analysis": rule_based_results,
                "analysis_metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": self.provider,
                    "model": self.model,
                    "foundation": "Core SDK ThreatDetectionNode",
                    "detection_rules": self.detection_rules,
                    "real_time": self.real_time,
                },
            }

            # Step 4: Add AI enhancements if enabled and threats detected
            if (
                self.enable_intelligence
                or self.enable_narratives
                or self.enable_recommendations
            ) and threats:
                ai_analysis = self._call_llm_for_intelligence(
                    rule_based_results=rule_based_results,
                    threats=threats,
                )

                if ai_analysis.get("ai_available"):
                    if self.enable_narratives:
                        result["ai_narrative"] = ai_analysis.get("narrative", "")
                    if self.enable_intelligence:
                        result["ai_intelligence"] = ai_analysis.get("intelligence", {})
                    if self.enable_recommendations:
                        result["ai_recommendations"] = ai_analysis.get(
                            "recommendations", []
                        )
                    result["analysis_metadata"]["ai_enhanced"] = True
                else:
                    result["analysis_metadata"]["ai_enhanced"] = False
                    result["analysis_metadata"]["ai_error"] = ai_analysis.get(
                        "error", "Unknown"
                    )
            else:
                result["analysis_metadata"]["ai_enhanced"] = False
                result["analysis_metadata"]["ai_reason"] = (
                    "No threats detected" if not threats else "AI features disabled"
                )

            logger.info(
                f"AI threat detection complete: ai_enhanced={result['analysis_metadata'].get('ai_enhanced', False)}, "
                f"threats={len(threats)}, "
                f"highest_severity={threat_summary.get('highest_severity', 'none')}"
            )

            return result

        except Exception as e:
            logger.error(f"AI threat detection failed: {e}")
            return {
                "error": str(e),
                "threats": [],
                "threat_summary": {},
                "rule_based_analysis": {},
                "analysis_metadata": {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
