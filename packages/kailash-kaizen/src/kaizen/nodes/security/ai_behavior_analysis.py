"""
AI-Enhanced Behavior Analysis Node

Extends Core SDK's BehaviorAnalysisNode with LLM-powered capabilities for advanced
behavioral analysis and natural language explanations.

Architecture:
- Foundation: kailash.nodes.security.BehaviorAnalysisNode (statistical ML-based)
- Enhancement: LLM-powered contextual analysis and natural language reporting
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node
from kailash.nodes.security.behavior_analysis import BehaviorAnalysisNode

from kaizen.nodes.ai.llm_agent import LLMAgentNode

logger = logging.getLogger(__name__)


class AIBehaviorAnalysisNode(Node):
    """
    AI-Enhanced Behavior Analysis for advanced anomaly detection.

    This node extends Core SDK's BehaviorAnalysisNode with LLM-powered capabilities:
    - Natural language explanations for anomalies
    - Contextual risk assessment using semantic understanding
    - Advanced pattern recognition beyond statistical methods
    - Multi-factor correlation with LLM reasoning

    **Architectural Pattern:**
    1. Core SDK BehaviorAnalysisNode performs statistical analysis (foundation)
    2. LLM analyzes statistical results for contextual insights (enhancement)
    3. Fallback to Core SDK if LLM unavailable (graceful degradation)

    **Usage:**
    ```python
    from kaizen.nodes.security import AIBehaviorAnalysisNode

    workflow.add_node("ai_behavior", AIBehaviorAnalysisNode(
        provider="openai",
        model="gpt-4o-mini",
        enable_explanations=True,
        risk_threshold=0.7,
        # Core SDK parameters
        baseline_period=timedelta(days=30),
        anomaly_threshold=0.8,
        learning_enabled=True
    ))
    ```

    **Integration with Core SDK:**
    - Uses BehaviorAnalysisNode for statistical foundation
    - Adds LLM layer for contextual analysis
    - Maintains backward compatibility with Core SDK APIs
    - Gracefully degrades to Core SDK if LLM fails

    **Outputs:**
    - anomalies: List of detected anomalies with severity scores
    - risk_score: Overall risk assessment (0.0-1.0)
    - ai_explanation: Natural language explanation of findings (optional)
    - ai_recommendations: LLM-generated security recommendations (optional)
    - statistical_analysis: Core SDK foundation analysis results
    """

    def __init__(
        self,
        name: str = "ai_behavior_analysis",
        # AI Enhancement Parameters
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        enable_explanations: bool = True,
        enable_recommendations: bool = True,
        explanation_depth: str = "detailed",  # "brief", "detailed", "technical"
        temperature: float = 0.3,
        # Core SDK Parameters (pass through to BehaviorAnalysisNode)
        baseline_period: timedelta = timedelta(days=30),
        anomaly_threshold: float = 0.8,
        learning_enabled: bool = True,
        ml_model: Optional[str] = None,
        max_profile_history: int = 10000,
        risk_threshold: float = 0.7,
        **kwargs,
    ):
        """
        Initialize AI-Enhanced Behavior Analysis Node.

        Args:
            name: Node identifier
            provider: LLM provider ("openai", "anthropic", "ollama")
            model: Model name (e.g., "gpt-4o-mini", "claude-3-5-sonnet-20241022")
            enable_explanations: Generate natural language explanations
            enable_recommendations: Generate security recommendations
            explanation_depth: Level of detail in explanations
            temperature: LLM temperature for response generation
            baseline_period: Time period for establishing behavioral baseline
            anomaly_threshold: Threshold for anomaly detection (0.0-1.0)
            learning_enabled: Enable continuous learning from user behavior
            ml_model: Statistical ML model type (None = "statistical")
            max_profile_history: Maximum behavioral history to retain
            risk_threshold: Threshold for high-risk classification
        """
        super().__init__(name=name, **kwargs)

        # AI Enhancement Configuration
        self.provider = provider
        self.model = model
        self.enable_explanations = enable_explanations
        self.enable_recommendations = enable_recommendations
        self.explanation_depth = explanation_depth
        self.temperature = temperature

        # Core SDK Foundation Configuration
        self.baseline_period = baseline_period
        self.anomaly_threshold = anomaly_threshold
        self.learning_enabled = learning_enabled
        self.ml_model = ml_model
        self.max_profile_history = max_profile_history
        self.risk_threshold = risk_threshold

        # Initialize Core SDK foundation node (will be created at execution time)
        self._core_behavior_node = None

        logger.info(
            f"Initialized AIBehaviorAnalysisNode with provider={provider}, "
            f"model={model}, explanations={enable_explanations}"
        )

    def _get_core_behavior_node(self) -> BehaviorAnalysisNode:
        """Get or create Core SDK BehaviorAnalysisNode instance."""
        if self._core_behavior_node is None:
            self._core_behavior_node = BehaviorAnalysisNode(
                name=f"{self.name}_core",
                baseline_period=self.baseline_period,
                anomaly_threshold=self.anomaly_threshold,
                learning_enabled=self.learning_enabled,
                ml_model=self.ml_model,
                max_profile_history=self.max_profile_history,
            )
        return self._core_behavior_node

    def _generate_system_prompt(self, user_profile: Dict[str, Any]) -> str:
        """Generate system prompt for LLM analysis."""
        depth_instructions = {
            "brief": "Provide a concise 1-2 sentence explanation.",
            "detailed": "Provide a comprehensive explanation with key factors and context.",
            "technical": "Provide a detailed technical analysis with statistical details and correlation patterns.",
        }

        return f"""You are an expert security analyst specializing in behavioral anomaly detection.

Your task is to analyze user behavior patterns and provide clear, actionable insights.

**User Profile Summary:**
- User ID: {user_profile.get('user_id', 'Unknown')}
- Analysis Period: {user_profile.get('analysis_period', 'Unknown')}
- Behavioral Baseline: {user_profile.get('baseline_summary', 'Not established')}

**Analysis Depth:** {depth_instructions.get(self.explanation_depth, depth_instructions['detailed'])}

**Your Response Should Include:**
1. Clear explanation of detected anomalies and their significance
2. Risk assessment with reasoning
3. Specific security recommendations if high-risk patterns detected

Focus on actionable insights that security teams can use to make informed decisions.
"""

    def _generate_analysis_prompt(
        self,
        statistical_results: Dict[str, Any],
        anomalies: List[Dict[str, Any]],
    ) -> str:
        """Generate prompt for LLM to analyze statistical results."""
        anomaly_summary = "\n".join(
            [
                f"- {a.get('type', 'unknown')}: Severity {a.get('severity', 0):.2f}, "
                f"Details: {a.get('details', 'No details')}"
                for a in anomalies[:10]  # Limit to top 10 for context
            ]
        )

        return f"""Analyze the following behavioral anomaly detection results:

**Statistical Analysis Results:**
- Overall Risk Score: {statistical_results.get('risk_score', 0):.2f}
- Anomalies Detected: {len(anomalies)}
- Detection Threshold: {self.anomaly_threshold}

**Top Anomalies:**
{anomaly_summary if anomaly_summary else "No significant anomalies detected"}

**Additional Context:**
- Baseline Period: {self.baseline_period.days} days
- Learning Enabled: {self.learning_enabled}
- Analysis Method: {statistical_results.get('analysis_method', 'Statistical ML')}

Based on this statistical analysis, provide:
1. A clear explanation of what these patterns indicate about user behavior
2. Assessment of security risk level and reasoning
3. Specific recommendations for security team action (if applicable)

Your analysis should help security teams understand:
- What behavioral changes are significant
- Why these patterns matter for security
- What actions should be taken (if any)
"""

    def _call_llm_for_analysis(
        self,
        statistical_results: Dict[str, Any],
        anomalies: List[Dict[str, Any]],
        user_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Call LLM for contextual analysis of statistical results.

        Uses LLMAgentNode to generate natural language explanations and
        recommendations based on statistical anomaly detection results.
        """
        try:
            # Generate prompts
            system_prompt = self._generate_system_prompt(user_profile)
            analysis_prompt = self._generate_analysis_prompt(
                statistical_results, anomalies
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
                logger.error(f"LLM analysis failed: {result['error']}")
                return {
                    "ai_available": False,
                    "explanation": f"AI analysis failed: {result['error']}",
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

            explanation = response_content
            recommendations = []

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

            return {
                "ai_available": True,
                "explanation": explanation,
                "recommendations": recommendations,
                "error": None,
            }

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}", exc_info=True)
            return {
                "ai_available": False,
                "explanation": f"AI analysis failed: {str(e)}",
                "recommendations": [],
                "error": str(e),
            }

    def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute AI-enhanced behavior analysis.

        Args:
            input_data: Must contain:
                - user_id: User identifier
                - events: List of user activity events
                - Optional: user_profile, baseline_data

        Returns:
            Dict containing:
                - anomalies: List of detected anomalies
                - risk_score: Overall risk assessment (0.0-1.0)
                - ai_explanation: Natural language explanation (if enabled)
                - ai_recommendations: Security recommendations (if enabled)
                - statistical_analysis: Core SDK foundation results
                - analysis_metadata: Execution details
        """
        try:
            logger.info(
                f"Executing AI behavior analysis for user {input_data.get('user_id', 'Unknown')}"
            )

            # Step 1: Execute Core SDK statistical analysis (foundation)
            core_node = self._get_core_behavior_node()
            statistical_results = core_node.execute(input_data)

            logger.info(
                f"Core SDK analysis complete: {len(statistical_results.get('anomalies', []))} anomalies, "
                f"risk_score={statistical_results.get('risk_score', 0):.2f}"
            )

            # Step 2: Extract anomalies and risk score from statistical analysis
            anomalies = statistical_results.get("anomalies", [])
            risk_score = statistical_results.get("risk_score", 0.0)

            # Step 3: Prepare result with foundation analysis
            result = {
                "anomalies": anomalies,
                "risk_score": risk_score,
                "statistical_analysis": statistical_results,
                "analysis_metadata": {
                    "user_id": input_data.get("user_id"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": self.provider,
                    "model": self.model,
                    "foundation": "Core SDK BehaviorAnalysisNode",
                },
            }

            # Step 4: Add AI enhancements if enabled and anomalies detected
            if (self.enable_explanations or self.enable_recommendations) and anomalies:
                user_profile = input_data.get(
                    "user_profile",
                    {
                        "user_id": input_data.get("user_id"),
                        "analysis_period": f"last {self.baseline_period.days} days",
                        "baseline_summary": "Statistical baseline from Core SDK",
                    },
                )

                ai_analysis = self._call_llm_for_analysis(
                    statistical_results=statistical_results,
                    anomalies=anomalies,
                    user_profile=user_profile,
                )

                if ai_analysis.get("ai_available"):
                    if self.enable_explanations:
                        result["ai_explanation"] = ai_analysis.get("explanation", "")
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
                    "No anomalies detected" if not anomalies else "AI features disabled"
                )

            logger.info(
                f"AI behavior analysis complete: ai_enhanced={result['analysis_metadata'].get('ai_enhanced', False)}, "
                f"anomalies={len(anomalies)}, risk_score={risk_score:.2f}"
            )

            return result

        except Exception as e:
            logger.error(f"AI behavior analysis failed: {e}")
            return {
                "error": str(e),
                "anomalies": [],
                "risk_score": 0.0,
                "statistical_analysis": {},
                "analysis_metadata": {
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
