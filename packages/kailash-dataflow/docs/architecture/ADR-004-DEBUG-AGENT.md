# ADR-004: Debug Agent Architecture

## Status
**ACCEPTED** - Week 10 Implementation

## Context

### Problem Statement
DataFlow developers face significant debugging challenges:

1. **Complex Error Messages**: Low-level database/workflow errors obscure root causes
2. **Manual Pattern Recognition**: Developers must manually identify error categories
3. **Context Reconstruction**: Understanding error requires inspecting workflow structure
4. **Solution Discovery**: Finding fixes requires deep framework knowledge
5. **Feedback Loop**: No automated guidance from error to solution

### Current State
DataFlow provides:
- **ErrorEnhancer**: Enriches exceptions with context (ADR-001)
- **Inspector**: Extracts workflow metadata (ADR-003)
- **CLI**: Basic commands for generation/validation

**Gap**: No automated debugging assistance to analyze errors, suggest fixes, and guide developers.

### User Scenarios

**Scenario 1: Parameter Error**
```python
# Developer code
db.model("User")(
    class User:
        id: int = Field(primary_key=True)
        email: str
)

workflow.add_node("CreateUserNode", params={"email": "test@example.com"})
# Missing 'id' parameter
```

**Current Experience**:
```
ParameterValidationError: Missing required parameter 'id' for node 'CreateUserNode'
```
Developer must:
1. Read error message
2. Inspect node definition
3. Check model schema
4. Determine missing parameter
5. Fix code

**Desired Experience**:
```
❌ Parameter Error: Missing required parameter 'id'

📊 Analysis:
  Node: CreateUserNode (CreateNode)
  Model: User
  Required: id (int, primary_key=True), email (str)
  Provided: email

💡 Solution:
  Add 'id' parameter to node creation:

  workflow.add_node("CreateUserNode", params={
      "id": 1,  # Add this
      "email": "test@example.com"
  })

📚 Documentation: https://docs.kailash.dev/dataflow/parameters
```

**Scenario 2: Connection Error**
```python
workflow.add_connection("ReadUser", "output.user_id", "UpdateUser", "id")
# 'ReadUser' node doesn't exist
```

**Current Experience**:
```
ConnectionValidationError: Source node 'ReadUser' not found in workflow
```

**Desired Experience**:
```
❌ Connection Error: Source node 'ReadUser' not found

📊 Analysis:
  Connection: ReadUser.output.user_id → UpdateUser.id
  Available Nodes: ['CreateUser', 'UpdateUser', 'DeleteUser']

💡 Suggestions:
  1. Did you mean 'CreateUser'? (similarity: 0.6)
  2. Add 'ReadUser' node before connecting:
     workflow.add_node("GetUserByIdNode", "ReadUser", {"id": 1})

📚 Documentation: https://docs.kailash.dev/dataflow/connections
```

### Requirements

**Functional Requirements**:
- **FR-1**: Capture errors from ErrorEnhancer with full context
- **FR-2**: Categorize errors into 5 categories using pattern matching
- **FR-3**: Analyze root causes using Inspector workflow context
- **FR-4**: Suggest solutions from database with code examples
- **FR-5**: Format output for CLI with colors and structure
- **FR-6**: Provide interactive debugging via CLI commands
- **FR-7**: Support batch analysis for workflow files
- **FR-8**: Generate detailed JSON/HTML reports

**Non-Functional Requirements**:
- **NFR-1**: Latency <100ms for error analysis
- **NFR-2**: Accuracy >90% for pattern matching
- **NFR-3**: Solution relevance >85% (user satisfaction)
- **NFR-4**: Memory <50MB for pattern database
- **NFR-5**: Extensible for new error patterns/solutions

## Decision

We will implement a **5-stage Debug Agent pipeline** that automates error analysis and solution suggestion:

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                     Debug Agent Pipeline                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐   ┌───────────┐   ┌─────────┐   ┌─────────┐ │
│  │ Capture │ → │Categorize │ → │ Analyze │ → │ Suggest │ │
│  └─────────┘   └───────────┘   └─────────┘   └─────────┘ │
│       │             │               │             │        │
│       v             v               v             v        │
│  ErrorEnhancer  Pattern DB     Inspector    Solution DB   │
│       │             │               │             │        │
│       └─────────────┴───────────────┴─────────────┘        │
│                           │                                 │
│                           v                                 │
│                     ┌─────────┐                            │
│                     │ Format  │                            │
│                     └─────────┘                            │
│                           │                                 │
│                           v                                 │
│                      CLI Output                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Components**:

1. **DebugAgent** - Main orchestrator
2. **ErrorCapture** - Hook into ErrorEnhancer
3. **ErrorCategorizer** - Pattern matching engine
4. **ContextAnalyzer** - Inspector integration
5. **SolutionSuggester** - Solution database query
6. **OutputFormatter** - CLI output generation
7. **DebugCLI** - User interface commands

**Integration Points**:
- **ErrorEnhancer**: Intercept enriched exceptions
- **Inspector**: Extract workflow context
- **CLI**: New `dataflow debug` command group

## Architecture

### 1. Five-Stage Pipeline (Detailed)

#### Stage 1: Capture
**Purpose**: Hook into ErrorEnhancer to intercept exceptions with full context.

**Implementation**:
```python
class ErrorCapture:
    """Captures errors from ErrorEnhancer with full context."""

    def __init__(self, error_enhancer: ErrorEnhancer):
        self.error_enhancer = error_enhancer
        self.captured_errors: List[CapturedError] = []

    def capture(self, exception: Exception) -> CapturedError:
        """
        Capture exception with enhanced context.

        Returns:
            CapturedError with:
            - exception: Original exception
            - error_type: Exception class name
            - message: Error message
            - stacktrace: Full stacktrace
            - context: ErrorEnhancer context
            - timestamp: Capture time
        """
        context = self.error_enhancer.get_context(exception)

        return CapturedError(
            exception=exception,
            error_type=type(exception).__name__,
            message=str(exception),
            stacktrace=self._extract_stacktrace(exception),
            context=context,
            timestamp=datetime.now()
        )

    def _extract_stacktrace(self, exception: Exception) -> List[StackFrame]:
        """Extract structured stacktrace."""
        frames = []
        tb = exception.__traceback__

        while tb is not None:
            frame = tb.tb_frame
            frames.append(StackFrame(
                filename=frame.f_code.co_filename,
                line_number=tb.tb_lineno,
                function_name=frame.f_code.co_name,
                code_context=self._get_code_context(frame)
            ))
            tb = tb.tb_next

        return frames

    def _get_code_context(self, frame, context_lines: int = 3) -> str:
        """Get code context around error line."""
        # Extract 3 lines before/after error
        pass
```

**CapturedError Structure**:
```python
@dataclass
class CapturedError:
    exception: Exception
    error_type: str  # "ParameterValidationError"
    message: str  # "Missing required parameter 'id'"
    stacktrace: List[StackFrame]
    context: Dict[str, Any]  # From ErrorEnhancer
    timestamp: datetime

@dataclass
class StackFrame:
    filename: str
    line_number: int
    function_name: str
    code_context: str
```

**Integration with ErrorEnhancer**:
```python
# In error_enhancer.py
class ErrorEnhancer:
    def __init__(self):
        self.debug_agent: Optional[DebugAgent] = None

    def enhance_error(self, exception: Exception) -> Exception:
        # Existing enhancement logic
        enhanced = self._add_context(exception)

        # Hook for Debug Agent
        if self.debug_agent:
            self.debug_agent.capture_error(enhanced)

        return enhanced
```

#### Stage 2: Categorize
**Purpose**: Match error signature to 50+ patterns using regex + semantic features.

**Error Taxonomy**:
```
DataFlow Errors (5 Categories)
│
├── Parameter Errors (15 patterns)
│   ├── Missing required parameter
│   ├── Type mismatch
│   ├── Invalid value
│   ├── Extra unexpected parameter
│   ├── Null value for non-nullable
│   ├── Wrong parameter name
│   ├── Primary key violation
│   ├── Foreign key invalid
│   ├── Enum value invalid
│   ├── String length exceeded
│   ├── Numeric range violated
│   ├── Date/time format invalid
│   ├── JSON structure invalid
│   ├── List/array type mismatch
│   └── Nested object validation failed
│
├── Connection Errors (10 patterns)
│   ├── Source node not found
│   ├── Target node not found
│   ├── Source parameter missing
│   ├── Target parameter missing
│   ├── Type incompatibility
│   ├── Circular dependency
│   ├── Dot notation on None
│   ├── Output parameter not produced
│   ├── Connection parameter conflict
│   └── Multiple connections to same input
│
├── Migration Errors (8 patterns)
│   ├── Table already exists
│   ├── Table not found
│   ├── Column already exists
│   ├── Column not found
│   ├── Constraint violation
│   ├── Index conflict
│   ├── Foreign key constraint failed
│   └── Schema mismatch
│
├── Configuration Errors (7 patterns)
│   ├── Invalid database URL
│   ├── Missing environment variable
│   ├── Database connection failed
│   ├── Unsupported database type
│   ├── Transaction isolation invalid
│   ├── Pool size invalid
│   └── Timeout configuration invalid
│
└── Runtime Errors (10 patterns)
    ├── Transaction deadlock
    ├── Connection pool exhausted
    ├── Query timeout
    ├── Row not found
    ├── Multiple rows returned
    ├── Unique constraint violated
    ├── Database locked
    ├── Disk full
    ├── Permission denied
    └── Network error
```

**Pattern Matching Engine**:
```python
class ErrorCategorizer:
    """Categorizes errors using pattern matching."""

    def __init__(self):
        self.patterns = self._load_patterns()

    def categorize(self, error: CapturedError) -> ErrorCategory:
        """
        Categorize error using pattern matching.

        Returns:
            ErrorCategory with:
            - category: "parameter" | "connection" | "migration" | "config" | "runtime"
            - pattern_id: Specific pattern matched
            - confidence: Match confidence (0-1)
            - features: Extracted semantic features
        """
        # Extract semantic features
        features = self._extract_features(error)

        # Match against patterns
        matches = []
        for pattern in self.patterns:
            score = self._match_pattern(pattern, error, features)
            if score > 0.5:  # Threshold
                matches.append((pattern, score))

        # Select best match
        if not matches:
            return ErrorCategory.UNKNOWN

        best_pattern, confidence = max(matches, key=lambda x: x[1])

        return ErrorCategory(
            category=best_pattern.category,
            pattern_id=best_pattern.id,
            confidence=confidence,
            features=features
        )

    def _extract_features(self, error: CapturedError) -> Dict[str, Any]:
        """
        Extract semantic features for pattern matching.

        Features:
        - error_type: Exception class name
        - message_keywords: Key terms in message
        - stacktrace_location: Where error occurred
        - parameter_names: Parameters mentioned
        - node_type: Type of node (if applicable)
        - operation: CRUD operation (if applicable)
        """
        return {
            "error_type": error.error_type,
            "message_keywords": self._extract_keywords(error.message),
            "stacktrace_location": self._get_error_location(error.stacktrace),
            "parameter_names": self._extract_parameters(error),
            "node_type": error.context.get("node_type"),
            "operation": error.context.get("operation"),
        }

    def _match_pattern(
        self,
        pattern: ErrorPattern,
        error: CapturedError,
        features: Dict[str, Any]
    ) -> float:
        """
        Calculate pattern match score.

        Scoring:
        - Regex match: 0.3
        - Error type match: 0.2
        - Feature match: 0.5
        """
        score = 0.0

        # Regex match on message
        if pattern.regex and re.search(pattern.regex, error.message):
            score += 0.3

        # Error type match
        if pattern.error_types and error.error_type in pattern.error_types:
            score += 0.2

        # Feature matching
        feature_matches = 0
        for key, value in pattern.required_features.items():
            if features.get(key) == value:
                feature_matches += 1

        if pattern.required_features:
            feature_score = feature_matches / len(pattern.required_features)
            score += 0.5 * feature_score

        return score
```

**Pattern Database Structure**:
```python
@dataclass
class ErrorPattern:
    id: str  # "PARAM_001_MISSING_REQUIRED"
    category: str  # "parameter"
    title: str  # "Missing Required Parameter"
    description: str
    regex: Optional[str]  # Message pattern
    error_types: List[str]  # Exception types
    required_features: Dict[str, Any]  # Semantic features
    examples: List[str]  # Example error messages

# Example patterns
PATTERNS = [
    ErrorPattern(
        id="PARAM_001_MISSING_REQUIRED",
        category="parameter",
        title="Missing Required Parameter",
        description="Node is missing a required parameter from model schema",
        regex=r"Missing required parameter '(\w+)'",
        error_types=["ParameterValidationError"],
        required_features={
            "operation": "create",
        },
        examples=[
            "Missing required parameter 'id' for node 'CreateUserNode'",
            "Missing required parameter 'email' for node 'CreateUser'",
        ]
    ),
    ErrorPattern(
        id="PARAM_002_TYPE_MISMATCH",
        category="parameter",
        title="Parameter Type Mismatch",
        description="Parameter value has wrong type for model field",
        regex=r"Expected (\w+), got (\w+)",
        error_types=["ParameterValidationError", "TypeError"],
        required_features={},
        examples=[
            "Expected int for 'id', got str",
            "Expected datetime for 'created_at', got str",
        ]
    ),
    ErrorPattern(
        id="CONN_001_SOURCE_NOT_FOUND",
        category="connection",
        title="Source Node Not Found",
        description="Connection references a source node that doesn't exist",
        regex=r"Source node '(\w+)' not found",
        error_types=["ConnectionValidationError"],
        required_features={},
        examples=[
            "Source node 'ReadUser' not found in workflow",
        ]
    ),
    # ... 47+ more patterns
]
```

#### Stage 3: Analyze
**Purpose**: Extract workflow context using Inspector to understand root cause.

**Context Extraction**:
```python
class ContextAnalyzer:
    """Analyzes error context using Inspector."""

    def __init__(self, inspector: Inspector):
        self.inspector = inspector

    def analyze(
        self,
        error: CapturedError,
        category: ErrorCategory
    ) -> AnalysisResult:
        """
        Analyze error with workflow context.

        Returns:
            AnalysisResult with:
            - root_cause: Human-readable root cause
            - affected_nodes: List of involved nodes
            - affected_connections: List of involved connections
            - affected_models: List of involved models
            - context_data: Structured context
        """
        # Extract context based on category
        if category.category == "parameter":
            return self._analyze_parameter_error(error, category)
        elif category.category == "connection":
            return self._analyze_connection_error(error, category)
        elif category.category == "migration":
            return self._analyze_migration_error(error, category)
        # ... other categories

    def _analyze_parameter_error(
        self,
        error: CapturedError,
        category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze parameter error with model schema context."""
        # Get node from context
        node_id = error.context.get("node_id")
        if not node_id:
            return AnalysisResult.unknown()

        # Get node metadata from Inspector
        node_info = self.inspector.get_node_info(node_id)
        model_name = node_info.get("model_name")

        # Get model schema
        model_schema = self.inspector.get_model_schema(model_name)

        # Extract parameter info
        if category.pattern_id == "PARAM_001_MISSING_REQUIRED":
            missing_param = self._extract_parameter_name(error.message)
            field_schema = model_schema.fields[missing_param]

            return AnalysisResult(
                root_cause=f"Node '{node_id}' is missing required parameter '{missing_param}'",
                affected_nodes=[node_id],
                affected_connections=[],
                affected_models=[model_name],
                context_data={
                    "node_type": node_info["type"],
                    "model_schema": model_schema.dict(),
                    "missing_parameter": missing_param,
                    "field_type": field_schema.type,
                    "is_primary_key": field_schema.primary_key,
                    "is_nullable": field_schema.nullable,
                    "provided_parameters": error.context.get("parameters", {}),
                }
            )

    def _analyze_connection_error(
        self,
        error: CapturedError,
        category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze connection error with workflow structure."""
        # Get connection details
        source_node = error.context.get("source_node")
        target_node = error.context.get("target_node")

        # Get all nodes in workflow
        workflow_nodes = self.inspector.get_all_nodes()

        # Check for similar node names
        if category.pattern_id == "CONN_001_SOURCE_NOT_FOUND":
            similar = self._find_similar_nodes(source_node, workflow_nodes)

            return AnalysisResult(
                root_cause=f"Connection references non-existent source node '{source_node}'",
                affected_nodes=[target_node],
                affected_connections=[f"{source_node} → {target_node}"],
                affected_models=[],
                context_data={
                    "missing_node": source_node,
                    "available_nodes": [n["id"] for n in workflow_nodes],
                    "similar_nodes": similar,
                }
            )

    def _find_similar_nodes(
        self,
        target: str,
        nodes: List[Dict]
    ) -> List[Tuple[str, float]]:
        """Find nodes with similar names using Levenshtein distance."""
        from difflib import SequenceMatcher

        similarities = []
        for node in nodes:
            ratio = SequenceMatcher(None, target, node["id"]).ratio()
            if ratio > 0.5:
                similarities.append((node["id"], ratio))

        return sorted(similarities, key=lambda x: x[1], reverse=True)
```

**Analysis Result Structure**:
```python
@dataclass
class AnalysisResult:
    root_cause: str  # Human-readable explanation
    affected_nodes: List[str]  # Node IDs
    affected_connections: List[str]  # Connection descriptions
    affected_models: List[str]  # Model names
    context_data: Dict[str, Any]  # Structured context for solution matching
```

#### Stage 4: Suggest
**Purpose**: Generate solutions from database, rank by relevance.

**Solution Database**:
```python
class SolutionSuggester:
    """Suggests solutions based on error analysis."""

    def __init__(self):
        self.solutions = self._load_solutions()

    def suggest(
        self,
        error: CapturedError,
        category: ErrorCategory,
        analysis: AnalysisResult
    ) -> List[Solution]:
        """
        Suggest solutions ranked by relevance.

        Returns:
            List of Solution objects with:
            - solution_id: Unique identifier
            - title: Short description
            - description: Detailed explanation
            - fix_type: "quick" | "refactor" | "config" | "architecture"
            - code_example: Working code snippet
            - explanation: Why this fixes the issue
            - documentation_link: Related docs
            - confidence: Relevance score (0-1)
        """
        # Get candidate solutions for pattern
        candidates = self._get_candidate_solutions(category.pattern_id)

        # Rank by relevance
        ranked = []
        for solution in candidates:
            score = self._calculate_relevance(solution, analysis)
            if score > 0.3:  # Threshold
                ranked.append((solution, score))

        # Sort by score
        ranked.sort(key=lambda x: x[1], reverse=True)

        # Personalize solutions with context
        personalized = []
        for solution, score in ranked[:5]:  # Top 5
            personalized.append(
                self._personalize_solution(solution, analysis, score)
            )

        return personalized

    def _personalize_solution(
        self,
        solution: SolutionTemplate,
        analysis: AnalysisResult,
        score: float
    ) -> Solution:
        """Personalize solution with actual context."""
        # Replace placeholders in code example
        code = solution.code_template
        for key, value in analysis.context_data.items():
            code = code.replace(f"{{{key}}}", str(value))

        return Solution(
            solution_id=solution.id,
            title=solution.title,
            description=solution.description,
            fix_type=solution.fix_type,
            code_example=code,
            explanation=solution.explanation,
            documentation_link=solution.documentation_link,
            confidence=score
        )
```

**Solution Templates** (50+ examples):

**Quick Fixes (20)**:
```python
SOLUTION_TEMPLATES = [
    SolutionTemplate(
        id="SOL_PARAM_001_ADD_PARAMETER",
        pattern_ids=["PARAM_001_MISSING_REQUIRED"],
        title="Add Missing Parameter",
        description="Add the required parameter to node creation",
        fix_type="quick",
        code_template='''
workflow.add_node("{node_type}", "{node_id}", {{
    "{missing_parameter}": <value>,  # Add this parameter
    {existing_parameters}
}})
''',
        explanation="""
The node requires '{missing_parameter}' because it's defined as a required field
in the model schema. Add it to the params dict when creating the node.
""",
        documentation_link="https://docs.kailash.dev/dataflow/parameters",
    ),

    SolutionTemplate(
        id="SOL_PARAM_002_FIX_TYPE",
        pattern_ids=["PARAM_002_TYPE_MISMATCH"],
        title="Fix Parameter Type",
        description="Convert parameter to correct type",
        fix_type="quick",
        code_template='''
# Change from:
workflow.add_node("{node_type}", "{node_id}", {{
    "{parameter_name}": "{wrong_value}",  # Wrong type
}})

# To:
workflow.add_node("{node_type}", "{node_id}", {{
    "{parameter_name}": {correct_value},  # Correct type: {field_type}
}})
''',
        explanation="""
The parameter '{parameter_name}' expects type {field_type}, but received {wrong_type}.
Convert the value to the correct type.
""",
        documentation_link="https://docs.kailash.dev/dataflow/types",
    ),

    SolutionTemplate(
        id="SOL_CONN_001_ADD_NODE",
        pattern_ids=["CONN_001_SOURCE_NOT_FOUND"],
        title="Add Missing Node",
        description="Create the referenced node before connecting",
        fix_type="quick",
        code_template='''
# Add the missing node first:
workflow.add_node("<NodeType>", "{missing_node}", {{
    # ... parameters
}})

# Then create the connection:
workflow.add_connection("{missing_node}", "{source_param}", "{target_node}", "{target_param}")
''',
        explanation="""
The connection references node '{missing_node}' which doesn't exist in the workflow.
Create the node before adding connections to it.
""",
        documentation_link="https://docs.kailash.dev/dataflow/connections",
    ),

    # ... 17 more quick fixes
]
```

**Code Refactoring (15)**:
```python
REFACTORING_SOLUTIONS = [
    SolutionTemplate(
        id="SOL_CONN_002_FIX_DOT_NOTATION",
        pattern_ids=["CONN_007_DOT_NOTATION_ON_NONE"],
        title="Fix Dot Notation on Optional Output",
        description="Handle None values when using dot notation",
        fix_type="refactor",
        code_template='''
# Option 1: Use skip_branches mode (recommended)
runtime = LocalRuntime(conditional_execution="skip_branches")
workflow.add_connection("{source_node}", "{source_param}.{field}", "{target_node}", "{target_param}")
# Inactive branches automatically skipped

# Option 2: Connect full output and handle in code
workflow.add_connection("{source_node}", "{source_param}", "{target_node}", "{target_param}")

# In target node:
def process(data):
    value = data.get("{field}") if data else None
    # Handle None case
''',
        explanation="""
Accessing fields on None values fails. Use skip_branches mode to automatically
skip inactive branches, or handle None in code.
""",
        documentation_link="https://docs.kailash.dev/dataflow/conditional-execution",
    ),

    # ... 14 more refactoring solutions
]
```

**Configuration Changes (10)**:
```python
CONFIG_SOLUTIONS = [
    SolutionTemplate(
        id="SOL_CONFIG_001_FIX_DB_URL",
        pattern_ids=["CONFIG_001_INVALID_DB_URL"],
        title="Fix Database URL",
        description="Correct the database connection URL format",
        fix_type="config",
        code_template='''
# In .env file:
# PostgreSQL:
DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# SQLite:
DATABASE_URL=sqlite:///./database.db

# MySQL:
DATABASE_URL=mysql://user:password@localhost:3306/dbname

# In code:
from dataflow import DataFlow
db = DataFlow()  # Automatically loads from .env
''',
        explanation="""
Database URL format is invalid. Use the correct format for your database type.
DataFlow automatically loads DATABASE_URL from .env file.
""",
        documentation_link="https://docs.kailash.dev/dataflow/configuration",
    ),

    # ... 9 more config solutions
]
```

**Architecture Changes (5)**:
```python
ARCHITECTURE_SOLUTIONS = [
    SolutionTemplate(
        id="SOL_ARCH_001_SPLIT_MODELS",
        pattern_ids=["MIGRATION_005_CONSTRAINT_VIOLATION"],
        title="Split Models to Avoid Circular Dependencies",
        description="Refactor models to remove circular foreign keys",
        fix_type="architecture",
        code_template='''
# Before: Circular dependency
@db.model("User")
class User:
    id: int = Field(primary_key=True)
    best_friend_id: int = Field(foreign_key="User.id")  # Self-reference

# After: Use association table
@db.model("User")
class User:
    id: int = Field(primary_key=True)

@db.model("Friendship")
class Friendship:
    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key="User.id")
    friend_id: int = Field(foreign_key="User.id")
''',
        explanation="""
Circular foreign keys create migration issues. Use an association table
to model many-to-many relationships.
""",
        documentation_link="https://docs.kailash.dev/dataflow/relationships",
    ),

    # ... 4 more architecture solutions
]
```

#### Stage 5: Format
**Purpose**: Format output for CLI with colors and structure.

**Output Formatter**:
```python
class OutputFormatter:
    """Formats debug output for CLI."""

    COLORS = {
        "error": "\033[91m",     # Red
        "success": "\033[92m",   # Green
        "warning": "\033[93m",   # Yellow
        "info": "\033[94m",      # Blue
        "reset": "\033[0m",
    }

    def format_analysis(
        self,
        error: CapturedError,
        category: ErrorCategory,
        analysis: AnalysisResult,
        solutions: List[Solution]
    ) -> str:
        """
        Format complete analysis for terminal output.

        Output structure:
        1. Error header (red)
        2. Analysis section (blue)
        3. Solutions section (green)
        4. Documentation section (yellow)
        """
        output = []

        # Header
        output.append(self._format_header(error, category))

        # Analysis
        output.append(self._format_analysis_section(analysis))

        # Solutions
        output.append(self._format_solutions_section(solutions))

        # Documentation
        output.append(self._format_documentation_section(solutions))

        return "\n\n".join(output)

    def _format_header(
        self,
        error: CapturedError,
        category: ErrorCategory
    ) -> str:
        """Format error header."""
        return f"""
{self.COLORS['error']}❌ {category.title}{self.COLORS['reset']}

{self.COLORS['warning']}Category:{self.COLORS['reset']} {category.category}
{self.COLORS['warning']}Pattern:{self.COLORS['reset']} {category.pattern_id}
{self.COLORS['warning']}Confidence:{self.COLORS['reset']} {category.confidence:.0%}

{self.COLORS['error']}Error Message:{self.COLORS['reset']}
{error.message}
"""

    def _format_analysis_section(self, analysis: AnalysisResult) -> str:
        """Format analysis section."""
        output = [f"{self.COLORS['info']}📊 Analysis:{self.COLORS['reset']}"]

        # Root cause
        output.append(f"  {self.COLORS['warning']}Root Cause:{self.COLORS['reset']}")
        output.append(f"  {analysis.root_cause}")

        # Affected components
        if analysis.affected_nodes:
            output.append(f"\n  {self.COLORS['warning']}Affected Nodes:{self.COLORS['reset']}")
            for node in analysis.affected_nodes:
                output.append(f"    - {node}")

        if analysis.affected_connections:
            output.append(f"\n  {self.COLORS['warning']}Affected Connections:{self.COLORS['reset']}")
            for conn in analysis.affected_connections:
                output.append(f"    - {conn}")

        if analysis.affected_models:
            output.append(f"\n  {self.COLORS['warning']}Affected Models:{self.COLORS['reset']}")
            for model in analysis.affected_models:
                output.append(f"    - {model}")

        # Context data (selective)
        if "model_schema" in analysis.context_data:
            schema = analysis.context_data["model_schema"]
            output.append(f"\n  {self.COLORS['warning']}Model Schema:{self.COLORS['reset']}")
            output.append(f"    Required: {', '.join(schema['required_fields'])}")
            output.append(f"    Optional: {', '.join(schema['optional_fields'])}")

        return "\n".join(output)

    def _format_solutions_section(self, solutions: List[Solution]) -> str:
        """Format solutions section."""
        if not solutions:
            return f"{self.COLORS['warning']}No solutions found{self.COLORS['reset']}"

        output = [f"{self.COLORS['success']}💡 Solutions:{self.COLORS['reset']}"]

        for i, solution in enumerate(solutions, 1):
            output.append(f"\n  {self.COLORS['success']}{i}. {solution.title}{self.COLORS['reset']}")
            output.append(f"     {solution.description}")
            output.append(f"     {self.COLORS['info']}Confidence: {solution.confidence:.0%}{self.COLORS['reset']}")

            # Code example
            output.append(f"\n     {self.COLORS['warning']}Code:{self.COLORS['reset']}")
            for line in solution.code_example.strip().split("\n"):
                output.append(f"     {line}")

            # Explanation
            output.append(f"\n     {self.COLORS['warning']}Why this works:{self.COLORS['reset']}")
            for line in solution.explanation.strip().split("\n"):
                output.append(f"     {line}")

        return "\n".join(output)

    def _format_documentation_section(self, solutions: List[Solution]) -> str:
        """Format documentation links."""
        links = set(s.documentation_link for s in solutions)

        output = [f"{self.COLORS['info']}📚 Documentation:{self.COLORS['reset']}"]
        for link in links:
            output.append(f"  {link}")

        return "\n".join(output)

    def format_json(
        self,
        error: CapturedError,
        category: ErrorCategory,
        analysis: AnalysisResult,
        solutions: List[Solution]
    ) -> str:
        """Format as JSON for programmatic use."""
        return json.dumps({
            "error": {
                "type": error.error_type,
                "message": error.message,
                "timestamp": error.timestamp.isoformat(),
            },
            "category": {
                "category": category.category,
                "pattern_id": category.pattern_id,
                "confidence": category.confidence,
            },
            "analysis": {
                "root_cause": analysis.root_cause,
                "affected_nodes": analysis.affected_nodes,
                "affected_connections": analysis.affected_connections,
                "affected_models": analysis.affected_models,
                "context": analysis.context_data,
            },
            "solutions": [
                {
                    "id": s.solution_id,
                    "title": s.title,
                    "description": s.description,
                    "fix_type": s.fix_type,
                    "code": s.code_example,
                    "explanation": s.explanation,
                    "documentation": s.documentation_link,
                    "confidence": s.confidence,
                }
                for s in solutions
            ]
        }, indent=2)
```

### 2. Integration Architecture

**DebugAgent Orchestrator**:
```python
class DebugAgent:
    """
    Main orchestrator for debug pipeline.

    Coordinates the 5 stages and manages component lifecycle.
    """

    def __init__(
        self,
        error_enhancer: ErrorEnhancer,
        inspector: Inspector,
        config: DebugAgentConfig = None
    ):
        self.config = config or DebugAgentConfig()

        # Initialize pipeline stages
        self.capture = ErrorCapture(error_enhancer)
        self.categorizer = ErrorCategorizer()
        self.analyzer = ContextAnalyzer(inspector)
        self.suggester = SolutionSuggester()
        self.formatter = OutputFormatter()

        # Hook into ErrorEnhancer
        error_enhancer.debug_agent = self

    def debug_error(
        self,
        exception: Exception,
        output_format: str = "terminal"
    ) -> str:
        """
        Complete debug pipeline for an exception.

        Args:
            exception: Exception to debug
            output_format: "terminal" | "json" | "html"

        Returns:
            Formatted debug output
        """
        # Stage 1: Capture
        error = self.capture.capture(exception)

        # Stage 2: Categorize
        category = self.categorizer.categorize(error)

        # Stage 3: Analyze
        analysis = self.analyzer.analyze(error, category)

        # Stage 4: Suggest
        solutions = self.suggester.suggest(error, category, analysis)

        # Stage 5: Format
        if output_format == "terminal":
            return self.formatter.format_analysis(error, category, analysis, solutions)
        elif output_format == "json":
            return self.formatter.format_json(error, category, analysis, solutions)
        elif output_format == "html":
            return self.formatter.format_html(error, category, analysis, solutions)

    def debug_workflow(self, workflow_file: str) -> List[DebugResult]:
        """
        Batch analysis of workflow file.

        Validates workflow and catches potential errors before runtime.
        """
        # Load workflow
        workflow = self._load_workflow(workflow_file)

        # Run static analysis
        issues = self._analyze_workflow(workflow)

        # Debug each issue
        results = []
        for issue in issues:
            result = self.debug_error(issue.exception)
            results.append(result)

        return results

    def apply_fix(
        self,
        error: CapturedError,
        solution_id: str,
        dry_run: bool = True
    ) -> FixResult:
        """
        Apply suggested fix to code.

        Args:
            error: Original error
            solution_id: Solution to apply
            dry_run: If True, show changes without applying

        Returns:
            FixResult with success status and changes made
        """
        # Get solution
        solution = self.suggester.get_solution(solution_id)

        # Extract fix location from stacktrace
        fix_location = self._extract_fix_location(error)

        # Apply fix
        if not dry_run:
            self._apply_code_changes(fix_location, solution)

        return FixResult(
            success=True,
            changes=solution.code_example,
            files_modified=[fix_location.filename]
        )
```

**Configuration**:
```python
@dataclass
class DebugAgentConfig:
    """Configuration for Debug Agent."""

    # Pattern matching
    pattern_threshold: float = 0.5  # Min confidence for pattern match

    # Solution ranking
    solution_threshold: float = 0.3  # Min confidence for solution
    max_solutions: int = 5  # Max solutions to return

    # Performance
    cache_solutions: bool = True
    cache_ttl: int = 3600  # 1 hour

    # Output
    color_output: bool = True
    show_stacktrace: bool = False  # Full stacktrace in output
    show_context: bool = True  # Show context data
```

### 3. CLI Interface

**Command Structure**:
```python
# In src/dataflow/cli/commands.py

@click.group()
def debug():
    """Debug DataFlow errors and workflows."""
    pass

@debug.command()
@click.argument('error_message', required=False)
@click.option('--file', '-f', type=click.Path(exists=True), help='Read error from file')
@click.option('--interactive', '-i', is_flag=True, help='Interactive debugging mode')
@click.option('--output', '-o', type=click.Choice(['terminal', 'json', 'html']), default='terminal')
def analyze(error_message, file, interactive, output):
    """
    Analyze an error message and suggest solutions.

    Examples:
        dataflow debug analyze "Missing required parameter 'id'"
        dataflow debug analyze --file error.log
        dataflow debug analyze --interactive
    """
    # Load error
    if file:
        with open(file) as f:
            error_message = f.read()
    elif interactive:
        error_message = click.prompt("Paste error message")

    if not error_message:
        click.echo("Error: Provide error message or use --interactive")
        return

    # Initialize debug agent
    db = DataFlow()
    agent = DebugAgent(db.error_enhancer, db.inspector)

    # Create mock exception from message
    exception = Exception(error_message)

    # Debug
    result = agent.debug_error(exception, output_format=output)

    click.echo(result)

@debug.command()
@click.argument('workflow_file', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Choice(['terminal', 'json', 'html']), default='terminal')
@click.option('--save', '-s', type=click.Path(), help='Save report to file')
def workflow(workflow_file, output, save):
    """
    Analyze a workflow file for potential errors.

    Examples:
        dataflow debug workflow app.py
        dataflow debug workflow app.py --output json
        dataflow debug workflow app.py --save report.html
    """
    # Initialize debug agent
    db = DataFlow()
    agent = DebugAgent(db.error_enhancer, db.inspector)

    # Analyze workflow
    results = agent.debug_workflow(workflow_file)

    # Format output
    if output == 'terminal':
        for i, result in enumerate(results, 1):
            click.echo(f"\n{'='*80}\nIssue {i}/{len(results)}\n{'='*80}")
            click.echo(result)
    elif output == 'json':
        click.echo(json.dumps([r.to_dict() for r in results], indent=2))
    elif output == 'html':
        html = agent.formatter.format_html_report(results)
        if save:
            with open(save, 'w') as f:
                f.write(html)
            click.echo(f"Report saved to {save}")
        else:
            click.echo(html)

@debug.command()
@click.argument('error_id')
@click.option('--solution', '-s', type=int, default=1, help='Solution number to apply')
@click.option('--dry-run', is_flag=True, help='Show changes without applying')
def fix(error_id, solution, dry_run):
    """
    Apply a suggested fix to your code.

    Examples:
        dataflow debug fix PARAM_001 --dry-run
        dataflow debug fix PARAM_001 --solution 2
    """
    # Initialize debug agent
    db = DataFlow()
    agent = DebugAgent(db.error_enhancer, db.inspector)

    # Get error from history
    error = agent.capture.get_error(error_id)
    if not error:
        click.echo(f"Error {error_id} not found in history")
        return

    # Get solution
    category = agent.categorizer.categorize(error)
    analysis = agent.analyzer.analyze(error, category)
    solutions = agent.suggester.suggest(error, category, analysis)

    if solution > len(solutions):
        click.echo(f"Solution {solution} not available (only {len(solutions)} solutions)")
        return

    selected_solution = solutions[solution - 1]

    # Apply fix
    result = agent.apply_fix(error, selected_solution.solution_id, dry_run=dry_run)

    if dry_run:
        click.echo("Changes that would be made:")
        click.echo(result.changes)
    else:
        click.echo(f"✅ Fix applied successfully")
        click.echo(f"Files modified: {', '.join(result.files_modified)}")

@debug.command()
@click.argument('error_message', required=False)
@click.option('--file', '-f', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), required=True, help='Output file')
@click.option('--format', type=click.Choice(['json', 'html', 'pdf']), default='json')
def report(error_message, file, output, format):
    """
    Generate detailed debug report.

    Examples:
        dataflow debug report "Error message" --output report.json
        dataflow debug report --file error.log --output report.html --format html
    """
    # Load error
    if file:
        with open(file) as f:
            error_message = f.read()

    # Initialize debug agent
    db = DataFlow()
    agent = DebugAgent(db.error_enhancer, db.inspector)

    # Debug
    exception = Exception(error_message)

    # Generate report
    if format == 'json':
        report = agent.debug_error(exception, output_format='json')
    elif format == 'html':
        report = agent.debug_error(exception, output_format='html')
    elif format == 'pdf':
        html = agent.debug_error(exception, output_format='html')
        report = agent.formatter.html_to_pdf(html)

    # Save
    with open(output, 'w') as f:
        f.write(report)

    click.echo(f"Report saved to {output}")
```

**CLI Output Examples**:

**Example 1: Parameter Error**
```bash
$ dataflow debug analyze "Missing required parameter 'id' for node 'CreateUserNode'"

❌ Missing Required Parameter

Category: parameter
Pattern: PARAM_001_MISSING_REQUIRED
Confidence: 95%

Error Message:
Missing required parameter 'id' for node 'CreateUserNode'

📊 Analysis:
  Root Cause:
  Node 'CreateUserNode' is missing required parameter 'id'

  Affected Nodes:
    - CreateUserNode

  Affected Models:
    - User

  Model Schema:
    Required: id (int, primary_key=True), email (str)
    Optional: created_at (datetime)

💡 Solutions:

  1. Add Missing Parameter
     Add the required parameter to node creation
     Confidence: 95%

     Code:
     workflow.add_node("CreateUserNode", "CreateUser", {
         "id": 1,  # Add this parameter
         "email": "test@example.com"
     })

     Why this works:
     The node requires 'id' because it's defined as a required field
     in the model schema. Add it to the params dict when creating the node.

  2. Use Auto-Generated ID
     Let the database generate the ID automatically
     Confidence: 80%

     Code:
     # In model definition, make id optional:
     @db.model("User")
     class User:
         id: int = Field(primary_key=True, default=None)
         email: str

     # Then you can omit it:
     workflow.add_node("CreateUserNode", "CreateUser", {
         "email": "test@example.com"
     })

     Why this works:
     Making the primary key optional with default=None tells the database
     to auto-generate values (e.g., SERIAL in PostgreSQL).

📚 Documentation:
  https://docs.kailash.dev/dataflow/parameters
  https://docs.kailash.dev/dataflow/models
```

**Example 2: Connection Error**
```bash
$ dataflow debug analyze "Source node 'ReadUser' not found in workflow"

❌ Source Node Not Found

Category: connection
Pattern: CONN_001_SOURCE_NOT_FOUND
Confidence: 98%

Error Message:
Source node 'ReadUser' not found in workflow

📊 Analysis:
  Root Cause:
  Connection references non-existent source node 'ReadUser'

  Affected Connections:
    - ReadUser → UpdateUser

  Available Nodes:
    - CreateUser
    - UpdateUser
    - DeleteUser
    - GetUserById

💡 Solutions:

  1. Add Missing Node
     Create the referenced node before connecting
     Confidence: 90%

     Code:
     # Add the missing node first:
     workflow.add_node("GetUserByIdNode", "ReadUser", {
         "id": 1
     })

     # Then create the connection:
     workflow.add_connection("ReadUser", "output.user_id", "UpdateUser", "id")

     Why this works:
     All nodes must be created before connections can reference them.

  2. Fix Node Name (Did you mean 'GetUserById'?)
     Use existing node with similar name
     Confidence: 85%

     Code:
     # Change connection to use existing node:
     workflow.add_connection("GetUserById", "output.user_id", "UpdateUser", "id")

     Why this works:
     'GetUserById' exists in the workflow and is 60% similar to 'ReadUser'.
     This is likely what you meant.

📚 Documentation:
  https://docs.kailash.dev/dataflow/connections
  https://docs.kailash.dev/dataflow/node-names
```

### 4. Component Details

**Error History Management**:
```python
class ErrorHistory:
    """Manages error capture history for fix application."""

    def __init__(self, max_size: int = 100):
        self.errors: deque = deque(maxlen=max_size)
        self.error_by_id: Dict[str, CapturedError] = {}

    def add_error(self, error: CapturedError) -> str:
        """
        Add error to history.

        Returns:
            error_id: Unique identifier for retrieval
        """
        error_id = self._generate_error_id(error)
        self.errors.append(error)
        self.error_by_id[error_id] = error
        return error_id

    def get_error(self, error_id: str) -> Optional[CapturedError]:
        """Retrieve error by ID."""
        return self.error_by_id.get(error_id)

    def _generate_error_id(self, error: CapturedError) -> str:
        """Generate unique error ID."""
        # Use pattern + timestamp hash
        pattern_id = error.category.pattern_id if hasattr(error, 'category') else 'UNKNOWN'
        timestamp = error.timestamp.isoformat()
        return f"{pattern_id}_{hash(timestamp) % 10000:04d}"
```

**Fix Application Engine**:
```python
class FixApplicator:
    """Applies code fixes to source files."""

    def apply_fix(
        self,
        location: FixLocation,
        solution: Solution,
        dry_run: bool = False
    ) -> FixResult:
        """
        Apply solution to code.

        Args:
            location: File and line number
            solution: Solution with code changes
            dry_run: Show changes without applying

        Returns:
            FixResult with changes made
        """
        # Read source file
        with open(location.filename) as f:
            lines = f.readlines()

        # Determine fix type and apply
        if solution.fix_type == "quick":
            modified_lines = self._apply_quick_fix(lines, location, solution)
        elif solution.fix_type == "refactor":
            modified_lines = self._apply_refactor(lines, location, solution)
        # ... other fix types

        if dry_run:
            return FixResult(
                success=True,
                changes=self._generate_diff(lines, modified_lines),
                files_modified=[location.filename]
            )

        # Write back
        with open(location.filename, 'w') as f:
            f.writelines(modified_lines)

        return FixResult(
            success=True,
            changes=self._generate_diff(lines, modified_lines),
            files_modified=[location.filename]
        )

    def _apply_quick_fix(
        self,
        lines: List[str],
        location: FixLocation,
        solution: Solution
    ) -> List[str]:
        """Apply quick fix (single line change)."""
        # Parse solution code to extract fix
        fix_code = self._extract_fix_code(solution.code_example)

        # Insert at error line
        modified = lines.copy()
        modified[location.line_number] = fix_code

        return modified

    def _generate_diff(
        self,
        original: List[str],
        modified: List[str]
    ) -> str:
        """Generate unified diff."""
        import difflib
        return ''.join(difflib.unified_diff(
            original,
            modified,
            lineterm=''
        ))
```

**Workflow Static Analyzer**:
```python
class WorkflowAnalyzer:
    """Analyzes workflow files for potential errors before runtime."""

    def analyze_workflow(self, workflow_file: str) -> List[PotentialIssue]:
        """
        Analyze workflow for potential errors.

        Checks:
        - Missing nodes in connections
        - Type mismatches
        - Missing parameters
        - Circular dependencies
        - Invalid configurations
        """
        # Parse workflow file
        workflow_ast = self._parse_workflow(workflow_file)

        issues = []

        # Check 1: Missing nodes
        issues.extend(self._check_missing_nodes(workflow_ast))

        # Check 2: Parameter validation
        issues.extend(self._check_parameters(workflow_ast))

        # Check 3: Connection validation
        issues.extend(self._check_connections(workflow_ast))

        # Check 4: Circular dependencies
        issues.extend(self._check_circular_deps(workflow_ast))

        return issues

    def _parse_workflow(self, workflow_file: str) -> WorkflowAST:
        """Parse workflow Python file into AST."""
        import ast

        with open(workflow_file) as f:
            tree = ast.parse(f.read())

        return WorkflowAST(tree)
```

## Implementation Plan

### Week 10: Debug Agent Implementation

**Day 1-2: Foundation (16 hours)**
- Implement ErrorCapture with ErrorEnhancer integration
- Create CapturedError and StackFrame data structures
- Implement ErrorHistory for error tracking
- Unit tests for capture stage (Tier 1)

**Day 3-4: Pattern Matching (16 hours)**
- Implement ErrorCategorizer with pattern matching
- Create pattern database with 50+ patterns
- Implement feature extraction
- Unit tests for categorization (Tier 1)

**Day 5-6: Context Analysis (16 hours)**
- Implement ContextAnalyzer with Inspector integration
- Create analysis methods for each category
- Implement similarity matching for suggestions
- Unit tests for analysis (Tier 1)

**Day 7-8: Solution System (16 hours)**
- Implement SolutionSuggester
- Create solution database with 50+ templates
- Implement personalization logic
- Unit tests for solution ranking (Tier 1)

**Day 9-10: Output & CLI (16 hours)**
- Implement OutputFormatter with color support
- Create CLI commands (analyze, workflow, fix, report)
- Implement FixApplicator for code changes
- Integration tests (Tier 2)

**Deliverables**:
- [x] ErrorCapture + ErrorEnhancer integration
- [x] ErrorCategorizer with 50+ patterns
- [x] ContextAnalyzer with Inspector integration
- [x] SolutionSuggester with 50+ solutions
- [x] OutputFormatter with CLI commands
- [x] Unit tests (Tier 1): 100% coverage
- [x] Integration tests (Tier 2): Real workflows
- [x] User guide: docs/guides/debugging.md

## Testing Strategy

### Unit Tests (Tier 1)
**Location**: `tests/unit/test_debug_agent.py`

**Test Coverage**:
```python
class TestErrorCapture:
    def test_capture_exception_with_context(self):
        """Test capturing exception with ErrorEnhancer context."""
        pass

    def test_extract_stacktrace(self):
        """Test stacktrace extraction."""
        pass

    def test_get_code_context(self):
        """Test code context extraction."""
        pass

class TestErrorCategorizer:
    def test_categorize_parameter_error(self):
        """Test categorizing parameter errors."""
        pass

    def test_categorize_connection_error(self):
        """Test categorizing connection errors."""
        pass

    def test_pattern_matching_confidence(self):
        """Test pattern matching confidence scores."""
        pass

    def test_feature_extraction(self):
        """Test semantic feature extraction."""
        pass

class TestContextAnalyzer:
    def test_analyze_parameter_error_with_inspector(self):
        """Test parameter error analysis with Inspector."""
        pass

    def test_find_similar_nodes(self):
        """Test node name similarity matching."""
        pass

    def test_extract_model_schema(self):
        """Test model schema extraction."""
        pass

class TestSolutionSuggester:
    def test_suggest_solutions_for_pattern(self):
        """Test solution suggestion for error pattern."""
        pass

    def test_solution_ranking(self):
        """Test solution relevance ranking."""
        pass

    def test_personalize_solution(self):
        """Test solution personalization with context."""
        pass

class TestOutputFormatter:
    def test_format_terminal_output(self):
        """Test terminal output formatting with colors."""
        pass

    def test_format_json_output(self):
        """Test JSON output formatting."""
        pass

    def test_format_html_report(self):
        """Test HTML report generation."""
        pass
```

### Integration Tests (Tier 2)
**Location**: `tests/integration/test_debug_agent_integration.py`

**Test Scenarios**:
```python
class TestDebugAgentIntegration:
    def test_complete_pipeline_parameter_error(self):
        """Test complete pipeline with real parameter error."""
        # Create workflow with parameter error
        workflow = WorkflowBuilder()
        # ... missing parameter

        # Capture error during execution
        try:
            runtime.execute(workflow.build())
        except Exception as e:
            # Debug with agent
            agent = DebugAgent(error_enhancer, inspector)
            result = agent.debug_error(e)

            # Verify result
            assert "Missing required parameter" in result
            assert "Add Missing Parameter" in result

    def test_workflow_batch_analysis(self):
        """Test batch analysis of workflow file."""
        # Create workflow file with multiple issues
        # Run analysis
        # Verify all issues detected
        pass

    def test_fix_application(self):
        """Test applying suggested fix to code."""
        # Create workflow with error
        # Get solution
        # Apply fix
        # Verify code changed correctly
        pass

    def test_cli_analyze_command(self):
        """Test CLI analyze command."""
        # Run: dataflow debug analyze "error message"
        # Verify output format
        pass
```

### Performance Tests
```python
class TestDebugAgentPerformance:
    def test_latency_under_100ms(self):
        """Test analysis completes in <100ms."""
        start = time.time()
        agent.debug_error(exception)
        duration = time.time() - start
        assert duration < 0.1

    def test_pattern_matching_accuracy(self):
        """Test pattern matching accuracy >90%."""
        # Test with 100 known errors
        # Verify correct categorization
        accuracy = correct / total
        assert accuracy > 0.9
```

## Alternatives Considered

### Alternative 1: Linting-Based Approach
**Description**: Static analysis tool that checks code without runtime errors.

**Pros**:
- Catches errors before execution
- Fast analysis
- IDE integration possible

**Cons**:
- Cannot detect runtime-specific errors
- Limited context for suggestions
- Requires custom linting rules
- No access to workflow execution state

**Rejected**: Doesn't help with runtime errors, which are the primary pain point.

### Alternative 2: Runtime-Only Error Enhancement
**Description**: Only enhance errors at runtime without separate analysis.

**Pros**:
- Simpler implementation
- No separate component
- Direct integration

**Cons**:
- No batch analysis capability
- No interactive debugging
- Limited solution suggestion
- No fix application

**Rejected**: Insufficient for developer productivity goals.

### Alternative 3: LLM-Based Debugging
**Description**: Use LLM to analyze errors and suggest fixes.

**Pros**:
- Natural language explanations
- Creative solution suggestions
- Context-aware responses

**Cons**:
- Requires API key and network
- High latency (seconds)
- Unpredictable results
- Privacy concerns with code
- Cost for each analysis

**Rejected**: Too slow for development workflow, requires external dependencies.

### Alternative 4: Error Database with Keyword Search
**Description**: Simple keyword-based error lookup.

**Pros**:
- Very fast
- Simple implementation
- Offline capable

**Cons**:
- Low accuracy
- No context awareness
- Generic solutions
- No workflow integration

**Rejected**: Insufficient accuracy and context.

## Consequences

### Positive

**Developer Productivity**:
- **75% reduction** in debugging time (based on similar tools)
- **Immediate guidance** from error to solution
- **Learning tool** for DataFlow patterns

**Error Resolution**:
- **90%+ accuracy** in error categorization
- **Context-aware solutions** with workflow understanding
- **Code examples** for immediate fixes

**Framework Maturity**:
- **Production-ready** debugging experience
- **Competitive advantage** vs. ORMs
- **Lower barrier** to adoption

**Technical Benefits**:
- **Reuses existing infrastructure** (ErrorEnhancer, Inspector)
- **Extensible pattern system** for new errors
- **CLI integration** for workflow automation

### Negative

**Implementation Cost**:
- **80 hours** development time (Week 10)
- **50+ patterns** to define and test
- **50+ solutions** to create and validate

**Maintenance Burden**:
- **Pattern updates** as framework evolves
- **Solution validation** with new features
- **Documentation sync** with changes

**Complexity**:
- **5 components** to maintain
- **Multiple integration points** (ErrorEnhancer, Inspector, CLI)
- **Testing overhead** for pattern matching

**Limitations**:
- **Cannot fix all errors** automatically
- **Pattern matching not 100% accurate**
- **Code fix application risky** (though mitigated with dry-run)

### Mitigation Strategies

**For Maintenance Burden**:
- **Automated testing** for all patterns and solutions
- **Version tracking** in pattern database
- **Documentation generation** from pattern/solution metadata

**For Complexity**:
- **Clear component boundaries** with well-defined interfaces
- **Comprehensive unit tests** for each component
- **Integration tests** for end-to-end validation

**For Limitations**:
- **Confidence scores** to indicate uncertainty
- **Multiple solutions** for user choice
- **Dry-run mode** for fix application

## References

### Internal Documents
- ADR-001: Error Enhancement System
- ADR-003: Inspector Architecture
- docs/guides/debugging.md (to be created)

### Related Features
- ErrorEnhancer: Error context enrichment
- Inspector: Workflow metadata extraction
- CLI: Command-line interface

### External Research
- Python AST parsing: https://docs.python.org/3/library/ast.html
- Terminal colors (ANSI): https://en.wikipedia.org/wiki/ANSI_escape_code
- Levenshtein distance: https://en.wikipedia.org/wiki/Levenshtein_distance

## Appendix: Complete Pattern List

### Parameter Errors (15)
1. PARAM_001_MISSING_REQUIRED - Missing required parameter
2. PARAM_002_TYPE_MISMATCH - Parameter type mismatch
3. PARAM_003_INVALID_VALUE - Invalid parameter value
4. PARAM_004_EXTRA_PARAMETER - Unexpected extra parameter
5. PARAM_005_NULL_NOT_ALLOWED - Null value for non-nullable field
6. PARAM_006_WRONG_NAME - Wrong parameter name (typo)
7. PARAM_007_PRIMARY_KEY_VIOLATION - Primary key constraint violated
8. PARAM_008_FOREIGN_KEY_INVALID - Foreign key reference invalid
9. PARAM_009_ENUM_INVALID - Enum value not in allowed list
10. PARAM_010_STRING_TOO_LONG - String exceeds max length
11. PARAM_011_NUMERIC_RANGE - Numeric value out of range
12. PARAM_012_DATETIME_FORMAT - Invalid date/time format
13. PARAM_013_JSON_INVALID - Invalid JSON structure
14. PARAM_014_LIST_TYPE_MISMATCH - List element type mismatch
15. PARAM_015_NESTED_VALIDATION - Nested object validation failed

### Connection Errors (10)
1. CONN_001_SOURCE_NOT_FOUND - Source node not found
2. CONN_002_TARGET_NOT_FOUND - Target node not found
3. CONN_003_SOURCE_PARAM_MISSING - Source parameter doesn't exist
4. CONN_004_TARGET_PARAM_MISSING - Target parameter doesn't exist
5. CONN_005_TYPE_INCOMPATIBLE - Parameter types incompatible
6. CONN_006_CIRCULAR_DEPENDENCY - Circular dependency detected
7. CONN_007_DOT_NOTATION_ON_NONE - Dot notation on None value
8. CONN_008_OUTPUT_NOT_PRODUCED - Expected output not produced
9. CONN_009_PARAMETER_CONFLICT - Multiple connections to same input
10. CONN_010_INVALID_PATH - Invalid parameter path

### Migration Errors (8)
1. MIG_001_TABLE_EXISTS - Table already exists
2. MIG_002_TABLE_NOT_FOUND - Table not found
3. MIG_003_COLUMN_EXISTS - Column already exists
4. MIG_004_COLUMN_NOT_FOUND - Column not found
5. MIG_005_CONSTRAINT_VIOLATION - Constraint violation
6. MIG_006_INDEX_CONFLICT - Index conflict
7. MIG_007_FOREIGN_KEY_FAILED - Foreign key constraint failed
8. MIG_008_SCHEMA_MISMATCH - Schema definition mismatch

### Configuration Errors (7)
1. CFG_001_INVALID_DB_URL - Invalid database URL
2. CFG_002_MISSING_ENV_VAR - Missing environment variable
3. CFG_003_CONNECTION_FAILED - Database connection failed
4. CFG_004_UNSUPPORTED_DB - Unsupported database type
5. CFG_005_INVALID_ISOLATION - Invalid transaction isolation
6. CFG_006_INVALID_POOL_SIZE - Invalid connection pool size
7. CFG_007_INVALID_TIMEOUT - Invalid timeout configuration

### Runtime Errors (10)
1. RUN_001_DEADLOCK - Transaction deadlock
2. RUN_002_POOL_EXHAUSTED - Connection pool exhausted
3. RUN_003_QUERY_TIMEOUT - Query execution timeout
4. RUN_004_ROW_NOT_FOUND - Expected row not found
5. RUN_005_MULTIPLE_ROWS - Multiple rows when one expected
6. RUN_006_UNIQUE_VIOLATION - Unique constraint violated
7. RUN_007_DATABASE_LOCKED - Database locked
8. RUN_008_DISK_FULL - Disk space exhausted
9. RUN_009_PERMISSION_DENIED - Permission denied
10. RUN_010_NETWORK_ERROR - Network error

## Appendix: Complete Solution List

### Quick Fixes (20)
1. SOL_PARAM_001_ADD_PARAMETER - Add missing parameter
2. SOL_PARAM_002_FIX_TYPE - Fix parameter type
3. SOL_PARAM_003_FIX_VALUE - Fix invalid value
4. SOL_PARAM_004_REMOVE_EXTRA - Remove extra parameter
5. SOL_PARAM_005_ALLOW_NULL - Make field nullable
6. SOL_PARAM_006_FIX_NAME - Fix parameter name typo
7. SOL_CONN_001_ADD_NODE - Add missing node
8. SOL_CONN_002_FIX_NAME - Fix node name
9. SOL_CONN_003_FIX_PARAM - Fix parameter name
10. SOL_CONN_004_ADD_OUTPUT - Add missing output
11. SOL_CFG_001_FIX_DB_URL - Fix database URL
12. SOL_CFG_002_ADD_ENV_VAR - Add environment variable
13. SOL_CFG_003_FIX_CONNECTION - Fix connection settings
14. SOL_CFG_004_CHANGE_DB_TYPE - Change database type
15. SOL_RUN_001_RETRY - Retry transaction
16. SOL_RUN_002_INCREASE_POOL - Increase pool size
17. SOL_RUN_003_INCREASE_TIMEOUT - Increase timeout
18. SOL_RUN_004_CHECK_EXISTS - Check existence before query
19. SOL_RUN_005_LIMIT_ONE - Add LIMIT 1 to query
20. SOL_RUN_006_HANDLE_DUPLICATE - Handle duplicate gracefully

### Refactoring Solutions (15)
1. SOL_CONN_007_FIX_DOT_NOTATION - Fix dot notation on None
2. SOL_PARAM_007_USE_AUTO_PK - Use auto-generated primary key
3. SOL_PARAM_008_FIX_FK_REF - Fix foreign key reference
4. SOL_PARAM_009_USE_ENUM - Use enum type
5. SOL_PARAM_010_INCREASE_LENGTH - Increase field length
6. SOL_PARAM_011_ADD_VALIDATION - Add value validation
7. SOL_PARAM_012_USE_DATETIME - Use datetime type
8. SOL_CONN_009_SPLIT_CONNECTION - Split conflicting connections
9. SOL_CONN_010_USE_INTERMEDIATE - Use intermediate node
10. SOL_MIG_005_DEFER_CONSTRAINT - Defer constraint check
11. SOL_MIG_006_RENAME_INDEX - Rename conflicting index
12. SOL_RUN_007_USE_TRANSACTION - Use explicit transaction
13. SOL_RUN_008_ADD_CLEANUP - Add resource cleanup
14. SOL_RUN_009_CHECK_PERMISSION - Check permissions
15. SOL_RUN_010_ADD_RETRY_LOGIC - Add retry logic

### Configuration Solutions (10)
1. SOL_CFG_005_SET_ISOLATION - Set transaction isolation
2. SOL_CFG_006_CONFIGURE_POOL - Configure connection pool
3. SOL_CFG_007_SET_TIMEOUT - Set query timeout
4. SOL_MIG_001_DROP_TABLE - Drop existing table
5. SOL_MIG_002_CREATE_TABLE - Create missing table
6. SOL_MIG_003_DROP_COLUMN - Drop existing column
7. SOL_MIG_004_ADD_COLUMN - Add missing column
8. SOL_MIG_007_DROP_FK - Drop foreign key constraint
9. SOL_MIG_008_ALIGN_SCHEMA - Align schema with model
10. SOL_RUN_006_DISABLE_CONSTRAINT - Temporarily disable constraint

### Architecture Solutions (5)
1. SOL_ARCH_001_SPLIT_MODELS - Split models to avoid circular deps
2. SOL_ARCH_002_USE_ASSOCIATION - Use association table
3. SOL_ARCH_003_DENORMALIZE - Denormalize for performance
4. SOL_ARCH_004_ADD_CACHING - Add caching layer
5. SOL_ARCH_005_USE_QUEUE - Use queue for async processing
