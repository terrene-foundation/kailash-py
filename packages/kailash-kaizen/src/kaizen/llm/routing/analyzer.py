"""
Task Analysis for LLM Routing.

Analyzes task complexity and type to inform model selection decisions.
Uses a combination of heuristics and optional LLM-based analysis.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class TaskComplexity(str, Enum):
    """Task complexity levels for routing decisions.

    Complexity affects which model tier is selected:
    - TRIVIAL/LOW: Can use faster, cheaper models
    - MEDIUM: Standard models
    - HIGH/EXPERT: Requires premium models
    """

    TRIVIAL = "trivial"  # One-word answers, yes/no questions
    LOW = "low"  # Basic Q&A, simple lookups
    MEDIUM = "medium"  # Analysis, summaries, moderate reasoning
    HIGH = "high"  # Multi-step reasoning, complex tasks
    EXPERT = "expert"  # Domain expertise, research-level tasks


class TaskType(str, Enum):
    """Task type for specialty-based routing.

    Different task types may benefit from specialized models:
    - CODE: Code generation, debugging, refactoring
    - ANALYSIS: Data analysis, evaluation, interpretation
    - CREATIVE: Writing, content generation
    - STRUCTURED: JSON output, formatting, extraction
    - SIMPLE_QA: Simple question answering
    - REASONING: Complex logical reasoning
    - MULTIMODAL: Tasks involving images, audio
    """

    SIMPLE_QA = "simple_qa"
    CODE = "code"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    STRUCTURED = "structured"
    REASONING = "reasoning"
    MULTIMODAL = "multimodal"


@dataclass
class TaskAnalysis:
    """Result of task analysis.

    Contains complexity, type, and capability requirements
    to inform model routing decisions.
    """

    complexity: TaskComplexity = TaskComplexity.MEDIUM
    type: TaskType = TaskType.SIMPLE_QA
    requires_vision: bool = False
    requires_audio: bool = False
    requires_tools: bool = False
    requires_structured: bool = False
    estimated_tokens: int = 500
    specialties_needed: List[str] = field(default_factory=list)
    confidence: float = 0.5  # How confident is the analysis (0.0-1.0)
    reasoning: str = ""  # Explanation of analysis

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "complexity": self.complexity.value,
            "type": self.type.value,
            "requires_vision": self.requires_vision,
            "requires_audio": self.requires_audio,
            "requires_tools": self.requires_tools,
            "requires_structured": self.requires_structured,
            "estimated_tokens": self.estimated_tokens,
            "specialties_needed": self.specialties_needed,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


class TaskAnalyzer:
    """Analyzes tasks to determine complexity and type for routing.

    Uses a multi-signal approach combining:
    1. Structural analysis (length, structure)
    2. Content indicators (domain-specific patterns)
    3. Context signals (tools, attachments)
    4. Optional LLM-based analysis for ambiguous cases

    Example:
        >>> analyzer = TaskAnalyzer()
        >>> analysis = analyzer.analyze(
        ...     "Write a Python function to sort a list using quicksort",
        ...     context={}
        ... )
        >>> analysis.type
        TaskType.CODE
        >>> analysis.complexity
        TaskComplexity.MEDIUM
    """

    # Indicators for code-related tasks
    CODE_INDICATORS: Set[str] = {
        "function",
        "class",
        "method",
        "code",
        "program",
        "script",
        "implement",
        "debug",
        "fix bug",
        "refactor",
        "optimize",
        "algorithm",
        "python",
        "javascript",
        "typescript",
        "java",
        "rust",
        "golang",
        "sql",
        "api",
        "endpoint",
        "database",
        "query",
        "git",
        "test",
        "unittest",
        "docker",
        "kubernetes",
    }

    # Indicators for analysis tasks
    ANALYSIS_INDICATORS: Set[str] = {
        "analyze",
        "evaluate",
        "assess",
        "compare",
        "review",
        "examine",
        "investigate",
        "interpret",
        "explain",
        "breakdown",
        "decompose",
        "study",
        "research",
        "report",
        "findings",
        "data",
        "metrics",
        "statistics",
        "trends",
        "patterns",
    }

    # Indicators for creative tasks
    CREATIVE_INDICATORS: Set[str] = {
        "write",
        "compose",
        "create",
        "generate",
        "story",
        "poem",
        "essay",
        "article",
        "blog",
        "content",
        "creative",
        "narrative",
        "fiction",
        "description",
        "marketing",
        "copy",
        "slogan",
        "headline",
        "brainstorm",
        "ideas",
    }

    # Indicators for structured output
    STRUCTURED_INDICATORS: Set[str] = {
        "json",
        "yaml",
        "xml",
        "csv",
        "format",
        "structured",
        "schema",
        "table",
        "list",
        "extract",
        "parse",
        "convert",
        "transform",
        "mapping",
        "template",
    }

    # Indicators for reasoning tasks
    REASONING_INDICATORS: Set[str] = {
        "reason",
        "logic",
        "prove",
        "derive",
        "deduce",
        "infer",
        "conclude",
        "argue",
        "justify",
        "because",
        "therefore",
        "step by step",
        "think through",
        "consider",
        "evaluate options",
        "trade-offs",
        "pros and cons",
        "decision",
        "choose",
    }

    # Indicators for high complexity
    HIGH_COMPLEXITY_INDICATORS: Set[str] = {
        "complex",
        "complicated",
        "advanced",
        "sophisticated",
        "comprehensive",
        "thorough",
        "detailed",
        "in-depth",
        "multi-step",
        "multi-part",
        "architecture",
        "design system",
        "scalable",
        "production",
        "enterprise",
        "optimize for performance",
        "security considerations",
    }

    # Indicators for low complexity
    LOW_COMPLEXITY_INDICATORS: Set[str] = {
        "simple",
        "basic",
        "quick",
        "brief",
        "short",
        "one-liner",
        "example",
        "sample",
        "demo",
        "hello world",
        "yes or no",
        "true or false",
        "what is",
        "define",
        "meaning of",
    }

    def __init__(
        self,
        llm_analyzer: Optional[Callable[[str, Dict], TaskAnalysis]] = None,
        use_llm_for_ambiguous: bool = False,
        ambiguity_threshold: float = 0.4,
    ):
        """Initialize TaskAnalyzer.

        Args:
            llm_analyzer: Optional LLM-based analyzer for ambiguous cases
            use_llm_for_ambiguous: Whether to use LLM for ambiguous tasks
            ambiguity_threshold: Confidence below which to use LLM analysis
        """
        self._llm_analyzer = llm_analyzer
        self._use_llm_for_ambiguous = use_llm_for_ambiguous
        self._ambiguity_threshold = ambiguity_threshold

    def analyze(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> TaskAnalysis:
        """Analyze a task to determine its characteristics.

        Args:
            task: The task description or prompt
            context: Optional context dict with:
                - has_images: bool - Whether images are attached
                - has_audio: bool - Whether audio is attached
                - has_tools: bool - Whether tools are available
                - history_length: int - Number of previous turns
                - max_tokens: int - Expected output length

        Returns:
            TaskAnalysis with complexity, type, and requirements
        """
        context = context or {}

        # Normalize task for analysis
        task_lower = task.lower()
        task_words = set(task_lower.split())

        # Analyze different aspects
        task_type = self._detect_type(task_lower, task_words, context)
        complexity = self._detect_complexity(task_lower, task_words, task_type, context)
        requirements = self._detect_requirements(task, context)

        # Estimate tokens
        estimated_tokens = self._estimate_output_tokens(task, complexity, task_type)

        # Determine specialties needed
        specialties = self._determine_specialties(task_type, complexity)

        # Calculate confidence
        confidence = self._calculate_confidence(task_lower, task_words, task_type)

        analysis = TaskAnalysis(
            complexity=complexity,
            type=task_type,
            requires_vision=requirements["vision"],
            requires_audio=requirements["audio"],
            requires_tools=requirements["tools"],
            requires_structured=requirements["structured"],
            estimated_tokens=estimated_tokens,
            specialties_needed=specialties,
            confidence=confidence,
            reasoning=self._build_reasoning(task_type, complexity, requirements),
        )

        # Use LLM analysis for ambiguous cases if configured
        if (
            self._use_llm_for_ambiguous
            and self._llm_analyzer
            and confidence < self._ambiguity_threshold
        ):
            try:
                llm_analysis = self._llm_analyzer(task, context)
                if llm_analysis.confidence > analysis.confidence:
                    analysis = llm_analysis
                    analysis.reasoning = f"LLM analysis: {analysis.reasoning}"
            except Exception as e:
                logger.warning(f"LLM analysis failed, using heuristic: {e}")

        logger.debug(
            f"Task analysis: type={analysis.type.value}, "
            f"complexity={analysis.complexity.value}, "
            f"confidence={analysis.confidence:.2f}"
        )

        return analysis

    def _detect_type(
        self, task_lower: str, task_words: Set[str], context: Dict
    ) -> TaskType:
        """Detect the primary task type."""
        # Check for multimodal first (context-based)
        if context.get("has_images") or context.get("has_audio"):
            return TaskType.MULTIMODAL

        # Count indicator matches for each type
        scores = {
            TaskType.CODE: self._count_matches(
                task_lower, task_words, self.CODE_INDICATORS
            ),
            TaskType.ANALYSIS: self._count_matches(
                task_lower, task_words, self.ANALYSIS_INDICATORS
            ),
            TaskType.CREATIVE: self._count_matches(
                task_lower, task_words, self.CREATIVE_INDICATORS
            ),
            TaskType.STRUCTURED: self._count_matches(
                task_lower, task_words, self.STRUCTURED_INDICATORS
            ),
            TaskType.REASONING: self._count_matches(
                task_lower, task_words, self.REASONING_INDICATORS
            ),
        }

        # Get highest scoring type
        max_score = max(scores.values())
        if max_score == 0:
            return TaskType.SIMPLE_QA

        # Return highest scoring type
        for task_type, score in scores.items():
            if score == max_score:
                return task_type

        return TaskType.SIMPLE_QA

    def _detect_complexity(
        self,
        task_lower: str,
        task_words: Set[str],
        task_type: TaskType,
        context: Dict,
    ) -> TaskComplexity:
        """Detect task complexity."""
        # Start with base complexity by type
        base_complexity = {
            TaskType.SIMPLE_QA: TaskComplexity.LOW,
            TaskType.CODE: TaskComplexity.MEDIUM,
            TaskType.ANALYSIS: TaskComplexity.MEDIUM,
            TaskType.CREATIVE: TaskComplexity.MEDIUM,
            TaskType.STRUCTURED: TaskComplexity.LOW,
            TaskType.REASONING: TaskComplexity.HIGH,
            TaskType.MULTIMODAL: TaskComplexity.MEDIUM,
        }
        complexity = base_complexity.get(task_type, TaskComplexity.MEDIUM)

        # Check for low complexity indicators
        low_matches = self._count_matches(
            task_lower, task_words, self.LOW_COMPLEXITY_INDICATORS
        )
        if low_matches >= 2:
            complexity = TaskComplexity.LOW
        elif low_matches >= 1 and complexity != TaskComplexity.HIGH:
            # Reduce by one level
            if complexity == TaskComplexity.HIGH:
                complexity = TaskComplexity.MEDIUM
            elif complexity == TaskComplexity.MEDIUM:
                complexity = TaskComplexity.LOW

        # Check for high complexity indicators
        high_matches = self._count_matches(
            task_lower, task_words, self.HIGH_COMPLEXITY_INDICATORS
        )
        if high_matches >= 3:
            complexity = TaskComplexity.EXPERT
        elif high_matches >= 2:
            complexity = TaskComplexity.HIGH
        elif high_matches >= 1 and complexity in (
            TaskComplexity.LOW,
            TaskComplexity.TRIVIAL,
        ):
            complexity = TaskComplexity.MEDIUM

        # Adjust based on task length
        word_count = len(task_lower.split())
        if word_count > 200:
            # Very long tasks are likely complex
            if complexity.value < TaskComplexity.HIGH.value:
                complexity = TaskComplexity.HIGH
        elif word_count < 10:
            # Very short tasks are likely simple
            if complexity == TaskComplexity.MEDIUM:
                complexity = TaskComplexity.LOW
            elif complexity == TaskComplexity.HIGH:
                complexity = TaskComplexity.MEDIUM

        # Check for question patterns indicating triviality
        trivial_patterns = [
            r"^what is\b",
            r"^who is\b",
            r"^when did\b",
            r"^where is\b",
            r"^yes or no\b",
            r"\?$",  # Single question mark at end (simple question)
        ]
        for pattern in trivial_patterns:
            if re.search(pattern, task_lower) and word_count < 15:
                if complexity in (TaskComplexity.LOW, TaskComplexity.MEDIUM):
                    complexity = TaskComplexity.TRIVIAL
                break

        return complexity

    def _detect_requirements(self, task: str, context: Dict) -> Dict[str, bool]:
        """Detect capability requirements."""
        task_lower = task.lower()

        # Vision requirement
        vision_patterns = [
            r"\bimage\b",
            r"\bpicture\b",
            r"\bphoto\b",
            r"\bscreenshot\b",
            r"\bdiagram\b",
            r"\bchart\b",
            r"\bgraph\b",
            r"\bvisualize\b",
            r"\blook at\b",
            r"\bsee\b.*\battached\b",
        ]
        requires_vision = context.get("has_images", False) or any(
            re.search(p, task_lower) for p in vision_patterns
        )

        # Audio requirement
        audio_patterns = [
            r"\baudio\b",
            r"\bsound\b",
            r"\bmusic\b",
            r"\bvoice\b",
            r"\bspoken\b",
            r"\blisten\b",
            r"\btranscribe\b",
        ]
        requires_audio = context.get("has_audio", False) or any(
            re.search(p, task_lower) for p in audio_patterns
        )

        # Tool requirement
        tool_patterns = [
            r"\bexecute\b",
            r"\brun\b.*\bcode\b",
            r"\bapi\b.*\bcall\b",
            r"\bfetch\b",
            r"\bsearch\b.*\bweb\b",
            r"\bfile\b.*\b(read|write)\b",
            r"\bdatabase\b.*\bquery\b",
        ]
        requires_tools = context.get("has_tools", False) or any(
            re.search(p, task_lower) for p in tool_patterns
        )

        # Structured output requirement
        structured_patterns = [
            r"\bjson\b",
            r"\byaml\b",
            r"\bxml\b",
            r"\bcsv\b",
            r"\bformat\s*as\b",
            r"\boutput\s*format\b",
            r"\bschema\b",
            r"\bstructured\b",
        ]
        requires_structured = any(re.search(p, task_lower) for p in structured_patterns)

        return {
            "vision": requires_vision,
            "audio": requires_audio,
            "tools": requires_tools,
            "structured": requires_structured,
        }

    def _count_matches(
        self, task_lower: str, task_words: Set[str], indicators: Set[str]
    ) -> int:
        """Count how many indicators match the task."""
        count = 0
        for indicator in indicators:
            if " " in indicator:
                # Multi-word indicator - check phrase
                if indicator in task_lower:
                    count += 1
            else:
                # Single word - check word set
                if indicator in task_words:
                    count += 1
        return count

    def _estimate_output_tokens(
        self, task: str, complexity: TaskComplexity, task_type: TaskType
    ) -> int:
        """Estimate expected output tokens."""
        # Base estimates by complexity
        base_tokens = {
            TaskComplexity.TRIVIAL: 50,
            TaskComplexity.LOW: 200,
            TaskComplexity.MEDIUM: 500,
            TaskComplexity.HIGH: 1500,
            TaskComplexity.EXPERT: 3000,
        }
        estimate = base_tokens.get(complexity, 500)

        # Adjust by task type
        type_multipliers = {
            TaskType.SIMPLE_QA: 0.5,
            TaskType.CODE: 1.5,
            TaskType.ANALYSIS: 1.2,
            TaskType.CREATIVE: 1.5,
            TaskType.STRUCTURED: 0.8,
            TaskType.REASONING: 1.3,
            TaskType.MULTIMODAL: 1.0,
        }
        estimate = int(estimate * type_multipliers.get(task_type, 1.0))

        return estimate

    def _determine_specialties(
        self, task_type: TaskType, complexity: TaskComplexity
    ) -> List[str]:
        """Determine specialties needed for the task."""
        specialties = []

        # Map task types to specialties
        type_specialties = {
            TaskType.CODE: ["code"],
            TaskType.ANALYSIS: ["analysis", "reasoning"],
            TaskType.CREATIVE: ["creative"],
            TaskType.REASONING: ["reasoning", "math"],
            TaskType.MULTIMODAL: ["vision", "multimodal"],
            TaskType.SIMPLE_QA: ["general"],
            TaskType.STRUCTURED: ["general"],
        }
        specialties.extend(type_specialties.get(task_type, []))

        # Add reasoning for high complexity
        if complexity in (TaskComplexity.HIGH, TaskComplexity.EXPERT):
            if "reasoning" not in specialties:
                specialties.append("reasoning")

        return specialties

    def _calculate_confidence(
        self, task_lower: str, task_words: Set[str], task_type: TaskType
    ) -> float:
        """Calculate confidence in the analysis."""
        # Base confidence from indicator match strength
        all_indicators = (
            self.CODE_INDICATORS
            | self.ANALYSIS_INDICATORS
            | self.CREATIVE_INDICATORS
            | self.STRUCTURED_INDICATORS
            | self.REASONING_INDICATORS
        )

        total_matches = self._count_matches(task_lower, task_words, all_indicators)

        # More matches = higher confidence
        if total_matches >= 5:
            confidence = 0.9
        elif total_matches >= 3:
            confidence = 0.7
        elif total_matches >= 1:
            confidence = 0.5
        else:
            confidence = 0.3

        # Reduce confidence for very short tasks (might be ambiguous)
        word_count = len(task_lower.split())
        if word_count < 5:
            confidence *= 0.7

        return min(confidence, 1.0)

    def _build_reasoning(
        self, task_type: TaskType, complexity: TaskComplexity, requirements: Dict
    ) -> str:
        """Build a reasoning explanation for the analysis."""
        parts = [
            f"Detected as {task_type.value} task",
            f"with {complexity.value} complexity",
        ]

        reqs = []
        if requirements["vision"]:
            reqs.append("vision")
        if requirements["audio"]:
            reqs.append("audio")
        if requirements["tools"]:
            reqs.append("tools")
        if requirements["structured"]:
            reqs.append("structured output")

        if reqs:
            parts.append(f"requiring: {', '.join(reqs)}")

        return "; ".join(parts)
