"""
Data structures for DataFlow AI Debug Agent.

Classes:
- ErrorAnalysis: Error analysis result from ErrorAnalysisEngine
- ErrorSolution: Solution from error catalog
- RankedSolution: Solution ranked by relevance
- Diagnosis: Complete diagnosis result from DebugAgent
- WorkflowContext: Workflow context from Inspector
- NodeInfo: Node metadata from Inspector
- KnowledgeBase: Pattern storage for solution ranking
- FeedbackData: Feedback tracking for learning
- SolutionFeedback: Feedback for a single solution
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ErrorSolution:
    """Solution from error catalog."""

    description: str  # What this solution does
    code_template: str  # Code example
    auto_fixable: bool  # Can be auto-applied?
    priority: int  # Original priority (1-5)


@dataclass
class ErrorAnalysis:
    """Error analysis result from ErrorAnalysisEngine."""

    error_code: str  # DF-XXX
    category: str  # parameter, connection, migration, etc.
    message: str  # Human-readable error message
    context: Dict[str, Any]  # Extracted context (node_id, parameter, etc.)
    causes: List[str]  # 3-5 possible causes from catalog
    solutions: List[ErrorSolution]  # 3-5 solutions from catalog
    severity: str  # error, warning
    docs_url: str  # Documentation link


@dataclass
class RankedSolution:
    """Solution ranked by relevance."""

    solution: ErrorSolution  # Original solution from catalog
    relevance_score: float  # 0.0-1.0 (how relevant to this error)
    reasoning: str  # Why this solution is ranked here
    confidence: float  # 0.0-1.0 (confidence in ranking)
    effectiveness_score: float = 0.0  # -1.0 to 1.0 (learned from feedback)

    @property
    def combined_score(self) -> float:
        """Combined score: relevance * confidence * (1 + effectiveness)."""
        return self.relevance_score * self.confidence * (1 + self.effectiveness_score)


@dataclass
class Diagnosis:
    """Complete diagnosis result from DebugAgent."""

    diagnosis: str  # Root cause explanation
    ranked_solutions: List[RankedSolution]  # Top 3 solutions
    confidence: float  # Overall confidence (0.0-1.0)
    next_steps: List[str]  # Specific actions to take
    inspector_hints: Optional[List[str]] = None  # Inspector-based hints (if available)


@dataclass
class NodeInfo:
    """Node metadata from Inspector."""

    node_id: str
    node_type: str
    model_name: str
    expected_params: Dict[str, Any]
    output_params: Dict[str, Any]
    connections_in: List[Dict[str, str]]
    connections_out: List[Dict[str, str]]


@dataclass
class WorkflowContext:
    """Workflow context from Inspector."""

    nodes: List[str] = field(default_factory=list)  # List of node IDs
    connections: List[Dict[str, str]] = field(
        default_factory=list
    )  # Connection details
    broken_connections: List[str] = field(
        default_factory=list
    )  # Broken connections (if any)
    missing_parameters: List[str] = field(
        default_factory=list
    )  # Missing required parameters
    node_metadata: Optional[NodeInfo] = None  # Metadata for error node
    parameter_trace: Optional[List[str]] = None  # Parameter flow trace
    node_type: Optional[str] = None  # Node type (CreateNode, UpdateNode, etc.)


@dataclass
class SolutionFeedback:
    """Feedback for a single solution."""

    used: int = 0  # Times solution was used
    thumbs_up: int = 0  # Positive feedback
    thumbs_down: int = 0  # Negative feedback


@dataclass
class FeedbackData:
    """Feedback data for a pattern."""

    solution_feedback: Dict[int, SolutionFeedback] = field(default_factory=dict)

    def record(self, solution_index: int, feedback_type: str):
        """Record feedback for solution."""
        if solution_index not in self.solution_feedback:
            self.solution_feedback[solution_index] = SolutionFeedback()

        feedback = self.solution_feedback[solution_index]

        if feedback_type == "used":
            feedback.used += 1
        elif feedback_type == "thumbs_up":
            feedback.thumbs_up += 1
        elif feedback_type == "thumbs_down":
            feedback.thumbs_down += 1

    def get_solution_feedback(self, solution_index: int) -> Dict[str, int]:
        """Get feedback stats for solution."""
        feedback = self.solution_feedback.get(solution_index, SolutionFeedback())
        return {
            "used": feedback.used,
            "thumbs_up": feedback.thumbs_up,
            "thumbs_down": feedback.thumbs_down,
        }


class KnowledgeBase:
    """
    Stores error-to-solution patterns and learns from feedback.

    Storage:
    - In-memory: Dict cache for fast lookups (default)
    - Persistent: SQLite database for cross-session learning (optional)

    Learning:
    - Implicit feedback: Track which solutions were used
    - Explicit feedback: Thumbs up/down from users
    - Effectiveness score: (thumbs_up - thumbs_down) / total_uses
    """

    def __init__(self, storage_type: str = "memory"):
        """
        Initialize Knowledge Base.

        Args:
            storage_type: "memory" (default) or "persistent" (SQLite)
        """
        self.storage_type = storage_type

        if storage_type == "memory":
            self.patterns: Dict[str, List[RankedSolution]] = {}
            self.feedback: Dict[str, FeedbackData] = {}
        else:
            self.db = self._init_database()

    def get_ranking(self, pattern_key: str) -> Optional[List[RankedSolution]]:
        """
        Get cached ranking for pattern.

        Returns:
            List of RankedSolution (top 3) if cached, None otherwise
        """
        if self.storage_type == "memory":
            return self.patterns.get(pattern_key)
        else:
            return self._query_database(pattern_key)

    def store_ranking(self, pattern_key: str, ranked_solutions: List[RankedSolution]):
        """Store ranking for future use."""
        if self.storage_type == "memory":
            self.patterns[pattern_key] = ranked_solutions
        else:
            self._insert_database(pattern_key, ranked_solutions)

    def record_feedback(
        self,
        pattern_key: str,
        solution_index: int,
        feedback_type: str,  # "used", "thumbs_up", "thumbs_down"
    ):
        """
        Record user feedback for solution.

        Args:
            pattern_key: Pattern key
            solution_index: Index of solution (0-2)
            feedback_type: "used", "thumbs_up", "thumbs_down"
        """
        if pattern_key not in self.feedback:
            self.feedback[pattern_key] = FeedbackData()

        feedback = self.feedback[pattern_key]
        feedback.record(solution_index, feedback_type)

        # Update effectiveness scores
        self._update_effectiveness_scores(pattern_key)

    def _update_effectiveness_scores(self, pattern_key: str):
        """
        Update effectiveness scores based on feedback.

        Effectiveness score formula:
        - score = (thumbs_up - thumbs_down) / total_uses
        - Range: -1.0 (all thumbs down) to 1.0 (all thumbs up)
        - Used to re-rank solutions over time
        """
        if pattern_key not in self.feedback or pattern_key not in self.patterns:
            return

        feedback = self.feedback[pattern_key]
        ranked_solutions = self.patterns[pattern_key]

        for i, solution in enumerate(ranked_solutions):
            solution_feedback = feedback.get_solution_feedback(i)

            thumbs_up = solution_feedback["thumbs_up"]
            thumbs_down = solution_feedback["thumbs_down"]
            total_uses = solution_feedback["used"]

            if total_uses > 0:
                effectiveness = (thumbs_up - thumbs_down) / total_uses
                solution.effectiveness_score = effectiveness

    def _init_database(self):
        """Initialize persistent SQLite database for cross-session learning."""
        import json
        import sqlite3

        db_path = self._get_db_path()
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS solution_rankings (
                pattern_key TEXT PRIMARY KEY,
                solutions_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS solution_feedback (
                pattern_key TEXT NOT NULL,
                solution_index INTEGER NOT NULL,
                feedback_type TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_feedback_pattern
            ON solution_feedback(pattern_key)
        """
        )
        conn.commit()

        # Also maintain in-memory cache for fast lookups
        self.patterns: Dict[str, List[RankedSolution]] = {}
        self.feedback: Dict[str, FeedbackData] = {}

        # Load existing data into memory
        cursor = conn.execute(
            "SELECT pattern_key, solutions_json FROM solution_rankings"
        )
        for row in cursor:
            try:
                solutions_data = json.loads(row[1])
                self.patterns[row[0]] = [
                    RankedSolution(
                        solution=ErrorSolution(
                            description=s["description"],
                            code_template=s["code_template"],
                            auto_fixable=s["auto_fixable"],
                            priority=s["priority"],
                        ),
                        relevance_score=s["relevance_score"],
                        reasoning=s["reasoning"],
                        confidence=s["confidence"],
                        effectiveness_score=s.get("effectiveness_score", 0.0),
                    )
                    for s in solutions_data
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.debug(
                    "Failed to load cached solutions from database: %s",
                    type(e).__name__,
                )

        return conn

    def _query_database(self, pattern_key: str) -> Optional[List[RankedSolution]]:
        """Query persistent database for cached rankings."""
        # Check in-memory cache first
        if pattern_key in self.patterns:
            return self.patterns[pattern_key]

        import json

        cursor = self.db.execute(
            "SELECT solutions_json FROM solution_rankings WHERE pattern_key = ?",
            (pattern_key,),
        )
        row = cursor.fetchone()
        if row is None:
            return None

        try:
            solutions_data = json.loads(row[0])
            solutions = [
                RankedSolution(
                    solution=ErrorSolution(
                        description=s["description"],
                        code_template=s["code_template"],
                        auto_fixable=s["auto_fixable"],
                        priority=s["priority"],
                    ),
                    relevance_score=s["relevance_score"],
                    reasoning=s["reasoning"],
                    confidence=s["confidence"],
                    effectiveness_score=s.get("effectiveness_score", 0.0),
                )
                for s in solutions_data
            ]
            # Cache in memory
            self.patterns[pattern_key] = solutions
            return solutions
        except (json.JSONDecodeError, KeyError) as e:
            logger.debug("Failed to query cached solutions: %s", type(e).__name__)
            return None

    def _insert_database(
        self, pattern_key: str, ranked_solutions: List[RankedSolution]
    ):
        """Insert or update rankings in persistent database."""
        import json

        solutions_data = [
            {
                "description": s.solution.description,
                "code_template": s.solution.code_template,
                "auto_fixable": s.solution.auto_fixable,
                "priority": s.solution.priority,
                "relevance_score": s.relevance_score,
                "reasoning": s.reasoning,
                "confidence": s.confidence,
                "effectiveness_score": s.effectiveness_score,
            }
            for s in ranked_solutions
        ]

        now = datetime.utcnow().isoformat()
        self.db.execute(
            """INSERT OR REPLACE INTO solution_rankings
               (pattern_key, solutions_json, updated_at)
               VALUES (?, ?, ?)""",
            (pattern_key, json.dumps(solutions_data), now),
        )
        self.db.commit()

        # Update in-memory cache
        self.patterns[pattern_key] = ranked_solutions

    @staticmethod
    def _get_db_path() -> str:
        """Get path for the persistent SQLite database."""
        import os

        # Use XDG data dir or home directory
        data_dir = os.environ.get(
            "DATAFLOW_DATA_DIR",
            os.path.join(os.path.expanduser("~"), ".dataflow"),
        )
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "debug_knowledge.db")
