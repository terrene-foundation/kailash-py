# Constraint Extensibility Design: Plugin Architecture for Custom Dimensions (v2.0)

> **SECURITY WARNING (Second-Pass Red Team Finding, CRITICAL)**: The original v1.0 design allowed arbitrary Python code execution via the `ConstraintDimension` protocol. The `_security_review()` method was a placeholder returning `passed=True`, and RestrictedPython has known bypasses. **v2.0 restricts v1 to declarative-only constraints. Full plugin extensibility with Python code execution is deferred to v2+ pending WASM sandboxing.** See Section "V1 Declarative Architecture" below.

## Executive Summary

This document defines a constraint extensibility system that allows organizations to add custom constraint dimensions beyond the five built-in categories. The design enables plugin development while maintaining security properties and validation guarantees.

**Key Principle**: Custom constraints must be as secure and verifiable as built-in constraints. Extensibility must not create security gaps.

**Complexity Score**: Enterprise (24 points) - Requires careful security design.

**v2.0 Security Decision**: The original arbitrary Python plugin interface is **DEPRECATED** for v1. Organizations requiring custom constraint dimensions in v1 MUST use the declarative constraint system (pre-defined operators, JSON/YAML-configurable, no code execution). The full Protocol-based plugin architecture is deferred to v2+ and will require WASM sandboxing, organization-level signing, and capability-based security.

---

## Design Goals

1. **Extensibility**: Organizations can define new constraint dimensions
2. **Security**: Custom constraints are validated and sandboxed
3. **Interoperability**: Custom constraints work with built-in constraints
4. **Auditability**: Custom constraint evaluations are fully logged
5. **Versioning**: Constraint dimensions can evolve over time
6. **Discoverability**: Available constraint types are introspectable

---

## Architecture Overview

```
+---------------------------+
|  Constraint Registry      |  <- All registered constraint dimensions
+-----------+---------------+
            |
    +-------+-------+
    |               |
    v               v
+-------+     +-----------+
|Built-in|    |  Custom   |
|Dims    |    |  Plugins  |
+-------+     +-----------+
    |               |
    +-------+-------+
            |
            v
+---------------------------+
| Constraint Envelope       |  <- Unified evaluation interface
+-----------+---------------+
            |
            v
+---------------------------+
| Validation Pipeline       |  <- Schema + semantic + security validation
+---------------------------+
```

---

## Constraint Dimension Interface

### Core Protocol

Every constraint dimension (built-in or custom) must implement the `ConstraintDimension` protocol:

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

class ConstraintCheckResult(Enum):
    """Result of a constraint check."""
    PERMITTED = "permitted"
    SOFT_LIMIT = "soft_limit"       # Warn but allow
    HARD_LIMIT = "hard_limit"       # Block
    REQUIRES_APPROVAL = "requires_approval"

@dataclass
class ConstraintEvaluationContext:
    """Context provided to constraint evaluators."""

    agent_id: str
    action: str
    resource: Optional[str]
    timestamp: datetime
    execution_context: Dict[str, Any]
    constraint_envelope: "ConstraintEnvelope"
    action_history: List["Action"]
    delegation_chain: List[str]

@dataclass
class ConstraintCheckOutput:
    """Output from a constraint check."""

    result: ConstraintCheckResult
    dimension: str
    constraint_id: str
    reason: Optional[str]
    metadata: Dict[str, Any]
    utilization: float              # 0.0-1.0, how close to limit

class ConstraintDimension(ABC):
    """
    Protocol for constraint dimensions.

    All constraint dimensions (built-in or custom) must implement this interface.
    """

    @property
    @abstractmethod
    def dimension_id(self) -> str:
        """Unique identifier for this dimension (e.g., 'financial', 'reputational')."""
        pass

    @property
    @abstractmethod
    def dimension_version(self) -> str:
        """Semantic version of this dimension (e.g., '1.0.0')."""
        pass

    @property
    @abstractmethod
    def schema(self) -> "ConstraintSchema":
        """JSON Schema for constraint configuration in this dimension."""
        pass

    @abstractmethod
    async def evaluate(
        self,
        config: Dict[str, Any],
        context: ConstraintEvaluationContext
    ) -> ConstraintCheckOutput:
        """
        Evaluate constraint against an action.

        Args:
            config: Constraint configuration for this dimension
            context: Evaluation context

        Returns:
            ConstraintCheckOutput with result and metadata
        """
        pass

    @abstractmethod
    async def validate_config(
        self,
        config: Dict[str, Any]
    ) -> "ValidationResult":
        """
        Validate constraint configuration.

        Args:
            config: Constraint configuration to validate

        Returns:
            ValidationResult with errors if invalid
        """
        pass

    @abstractmethod
    def can_tighten_to(
        self,
        parent_config: Dict[str, Any],
        child_config: Dict[str, Any]
    ) -> "TighteningResult":
        """
        Check if child config is a valid tightening of parent config.

        Args:
            parent_config: Parent constraint configuration
            child_config: Proposed child configuration

        Returns:
            TighteningResult indicating validity
        """
        pass

    @abstractmethod
    def get_utilization(
        self,
        config: Dict[str, Any],
        current_state: Dict[str, Any]
    ) -> float:
        """
        Calculate current utilization of constraint (0.0-1.0).

        Args:
            config: Constraint configuration
            current_state: Current usage state

        Returns:
            Utilization ratio (0.0 = unused, 1.0 = at limit)
        """
        pass
```

### Schema Definition

```python
@dataclass
class ConstraintSchema:
    """JSON Schema definition for a constraint dimension."""

    json_schema: Dict[str, Any]                # JSON Schema object
    required_fields: List[str]
    optional_fields: List[str]
    field_descriptions: Dict[str, str]
    examples: List[Dict[str, Any]]

    def validate(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate config against schema."""
        # Use jsonschema library
        try:
            jsonschema.validate(config, self.json_schema)
            return ValidationResult(valid=True)
        except jsonschema.ValidationError as e:
            return ValidationResult(valid=False, errors=[str(e)])
```

---

## Built-In Dimension Implementations

### Financial Dimension

```python
class FinancialConstraintDimension(ConstraintDimension):
    """Built-in financial constraint dimension."""

    @property
    def dimension_id(self) -> str:
        return "financial"

    @property
    def dimension_version(self) -> str:
        return "1.0.0"

    @property
    def schema(self) -> ConstraintSchema:
        return ConstraintSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "max_transaction": {"type": "number", "minimum": 0},
                    "daily_limit": {"type": "number", "minimum": 0},
                    "monthly_limit": {"type": "number", "minimum": 0},
                    "approval_threshold": {"type": "number", "minimum": 0},
                    "vendor_limits": {
                        "type": "object",
                        "additionalProperties": {"type": "number"}
                    },
                    "currency": {"type": "string", "default": "USD"}
                }
            },
            required_fields=[],
            optional_fields=[
                "max_transaction", "daily_limit", "monthly_limit",
                "approval_threshold", "vendor_limits", "currency"
            ],
            field_descriptions={
                "max_transaction": "Maximum single transaction value",
                "daily_limit": "Maximum daily cumulative spending",
                "monthly_limit": "Maximum monthly cumulative spending",
                "approval_threshold": "Amount above which approval is required",
                "vendor_limits": "Per-vendor spending limits",
                "currency": "Currency for all values"
            },
            examples=[
                {
                    "max_transaction": 5000,
                    "daily_limit": 25000,
                    "monthly_limit": 100000,
                    "approval_threshold": 2500,
                    "currency": "USD"
                }
            ]
        )

    async def evaluate(
        self,
        config: Dict[str, Any],
        context: ConstraintEvaluationContext
    ) -> ConstraintCheckOutput:
        """Evaluate financial constraint."""
        # Extract action metadata
        transaction_amount = context.execution_context.get("amount", 0)
        vendor = context.execution_context.get("vendor")

        # Check max_transaction
        if "max_transaction" in config:
            if transaction_amount > config["max_transaction"]:
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult.HARD_LIMIT,
                    dimension="financial",
                    constraint_id="max_transaction",
                    reason=f"Transaction ${transaction_amount} exceeds limit ${config['max_transaction']}",
                    metadata={"amount": transaction_amount, "limit": config["max_transaction"]},
                    utilization=transaction_amount / config["max_transaction"]
                )

        # Check approval_threshold
        if "approval_threshold" in config:
            if transaction_amount > config["approval_threshold"]:
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult.REQUIRES_APPROVAL,
                    dimension="financial",
                    constraint_id="approval_threshold",
                    reason=f"Transaction ${transaction_amount} requires approval (threshold: ${config['approval_threshold']})",
                    metadata={"amount": transaction_amount, "threshold": config["approval_threshold"]},
                    utilization=transaction_amount / config["max_transaction"]
                )

        # Check daily_limit (requires state)
        if "daily_limit" in config:
            daily_spent = await self._get_daily_spent(context.agent_id)
            projected = daily_spent + transaction_amount
            if projected > config["daily_limit"]:
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult.HARD_LIMIT,
                    dimension="financial",
                    constraint_id="daily_limit",
                    reason=f"Daily limit would be exceeded: ${projected} > ${config['daily_limit']}",
                    metadata={"projected": projected, "limit": config["daily_limit"]},
                    utilization=projected / config["daily_limit"]
                )

        # All checks passed
        return ConstraintCheckOutput(
            result=ConstraintCheckResult.PERMITTED,
            dimension="financial",
            constraint_id="all",
            reason=None,
            metadata={},
            utilization=self.get_utilization(config, {"amount": transaction_amount})
        )

    def can_tighten_to(
        self,
        parent_config: Dict[str, Any],
        child_config: Dict[str, Any]
    ) -> TighteningResult:
        """Check if child is valid tightening of parent."""
        violations = []

        # Numeric fields must be <= parent
        for field in ["max_transaction", "daily_limit", "monthly_limit", "approval_threshold"]:
            if field in child_config and field in parent_config:
                if child_config[field] > parent_config[field]:
                    violations.append(
                        f"{field}: child {child_config[field]} > parent {parent_config[field]}"
                    )

        # Vendor limits must be <= parent
        if "vendor_limits" in child_config and "vendor_limits" in parent_config:
            for vendor, limit in child_config["vendor_limits"].items():
                parent_limit = parent_config["vendor_limits"].get(vendor, float("inf"))
                if limit > parent_limit:
                    violations.append(
                        f"vendor_limits[{vendor}]: child {limit} > parent {parent_limit}"
                    )

        return TighteningResult(
            valid=len(violations) == 0,
            violations=violations
        )
```

---

## Custom Dimension Plugin API

### Plugin Registration

```python
class ConstraintDimensionRegistry:
    """Registry for constraint dimensions."""

    def __init__(self):
        self._dimensions: Dict[str, ConstraintDimension] = {}
        self._built_in = {
            "financial", "operational", "temporal", "data_access", "communication"
        }

    def register(
        self,
        dimension: ConstraintDimension,
    ) -> None:
        """
        Register a constraint dimension.

        Args:
            dimension: The dimension to register

        Raises:
            ConstraintRegistrationError: If registration fails validation
            ConstraintSecurityError: If built-in override attempted or non-declarative dimension in v1
        """
        dim_id = dimension.dimension_id

        # SECURITY (v2.0): Built-in dimensions can NEVER be overridden.
        # This prevents malicious plugins from replacing core constraint
        # evaluation with permissive implementations.
        if dim_id in self._built_in:
            raise ConstraintRegistrationError(
                f"Cannot override built-in dimension '{dim_id}'. "
                f"Built-in dimensions are immutable for security."
            )

        # Validate dimension
        validation = self._validate_dimension(dimension)
        if not validation.valid:
            raise ConstraintRegistrationError(
                f"Dimension validation failed: {validation.errors}"
            )

        # Security review for custom dimensions
        if dim_id not in self._built_in:
            security_result = self._security_review(dimension)
            if not security_result.passed:
                raise ConstraintSecurityError(
                    f"Dimension failed security review: {security_result.reason}"
                )

        self._dimensions[dim_id] = dimension

    def get(self, dimension_id: str) -> Optional[ConstraintDimension]:
        """Get a registered dimension."""
        return self._dimensions.get(dimension_id)

    def list_dimensions(self) -> List[str]:
        """List all registered dimension IDs."""
        return list(self._dimensions.keys())

    def get_schema(self, dimension_id: str) -> Optional[ConstraintSchema]:
        """Get schema for a dimension."""
        dim = self._dimensions.get(dimension_id)
        return dim.schema if dim else None

    def _validate_dimension(self, dimension: ConstraintDimension) -> ValidationResult:
        """Validate dimension implementation."""
        errors = []

        # Check required methods are implemented
        required_methods = [
            "evaluate", "validate_config", "can_tighten_to", "get_utilization"
        ]
        for method in required_methods:
            if not hasattr(dimension, method) or not callable(getattr(dimension, method)):
                errors.append(f"Missing required method: {method}")

        # Check schema is valid JSON Schema
        try:
            jsonschema.Draft7Validator.check_schema(dimension.schema.json_schema)
        except jsonschema.SchemaError as e:
            errors.append(f"Invalid JSON Schema: {e}")

        # Check version is semantic
        if not self._is_semver(dimension.dimension_version):
            errors.append(f"Invalid version format: {dimension.dimension_version}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _security_review(self, dimension: ConstraintDimension) -> SecurityReviewResult:
        """
        Security review for custom dimensions.

        SECURITY (v2.0): In v1, only DeclarativeConstraintDimension instances
        are permitted. Arbitrary Python ConstraintDimension subclasses are
        rejected until WASM sandboxing is implemented in v2.

        Checks:
        1. Dimension must be DeclarativeConstraintDimension (v1)
        2. No arbitrary code execution in evaluate()
        3. No network calls without explicit permission
        4. No file system access without explicit permission
        5. Bounded execution time
        6. No information leakage
        """
        # v1: Only declarative dimensions are permitted
        if not isinstance(dimension, DeclarativeConstraintDimension):
            return SecurityReviewResult(
                passed=False,
                reason=(
                    "v1 only permits DeclarativeConstraintDimension instances. "
                    "Arbitrary Python ConstraintDimension subclasses require "
                    "WASM sandboxing (planned for v2). Use declarative operators "
                    "or request an exception from your security team."
                )
            )
        # Declarative dimensions use pre-defined operators only - no code execution
        return SecurityReviewResult(passed=True)
```

### Plugin Definition Example: Reputational Risk

```python
class ReputationalConstraintDimension(ConstraintDimension):
    """
    Custom constraint dimension for reputational risk.

    Example of how organizations can extend the constraint system
    with domain-specific constraint types.
    """

    def __init__(
        self,
        risk_scorer: "ReputationalRiskScorer",
        brand_guidelines: "BrandGuidelines"
    ):
        self.risk_scorer = risk_scorer
        self.brand_guidelines = brand_guidelines

    @property
    def dimension_id(self) -> str:
        return "reputational"

    @property
    def dimension_version(self) -> str:
        return "1.0.0"

    @property
    def schema(self) -> ConstraintSchema:
        return ConstraintSchema(
            json_schema={
                "type": "object",
                "properties": {
                    "risk_threshold": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Maximum acceptable reputational risk score"
                    },
                    "brand_values": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Brand values that must be respected"
                    },
                    "sensitive_topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Topics requiring extra scrutiny"
                    },
                    "media_scrutiny_mode": {
                        "type": "string",
                        "enum": ["assume_always", "high_profile_only", "disabled"],
                        "default": "high_profile_only"
                    },
                    "stakeholder_sensitivity": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                        "description": "Sensitivity levels per stakeholder group"
                    }
                },
                "required": ["risk_threshold"]
            },
            required_fields=["risk_threshold"],
            optional_fields=[
                "brand_values", "sensitive_topics",
                "media_scrutiny_mode", "stakeholder_sensitivity"
            ],
            field_descriptions={
                "risk_threshold": "Actions with risk score above this are blocked",
                "brand_values": "Core brand values that actions must align with",
                "sensitive_topics": "Topics requiring human review",
                "media_scrutiny_mode": "How to handle potential media exposure",
                "stakeholder_sensitivity": "Per-stakeholder sensitivity weights"
            },
            examples=[
                {
                    "risk_threshold": 0.3,
                    "brand_values": ["innovation", "integrity", "customer-first"],
                    "sensitive_topics": ["politics", "religion", "legal"],
                    "media_scrutiny_mode": "assume_always",
                    "stakeholder_sensitivity": {
                        "regulators": 0.9,
                        "customers": 0.7,
                        "partners": 0.6
                    }
                }
            ]
        )

    async def evaluate(
        self,
        config: Dict[str, Any],
        context: ConstraintEvaluationContext
    ) -> ConstraintCheckOutput:
        """Evaluate reputational constraint."""

        # Score the action's reputational risk
        risk_score = await self.risk_scorer.score_action(
            action=context.action,
            resource=context.resource,
            context=context.execution_context
        )

        # Check against threshold
        if risk_score > config["risk_threshold"]:
            return ConstraintCheckOutput(
                result=ConstraintCheckResult.HARD_LIMIT,
                dimension="reputational",
                constraint_id="risk_threshold",
                reason=f"Action has reputational risk score {risk_score:.2f} > threshold {config['risk_threshold']}",
                metadata={
                    "risk_score": risk_score,
                    "threshold": config["risk_threshold"],
                    "risk_factors": await self.risk_scorer.get_risk_factors(context.action)
                },
                utilization=risk_score / config["risk_threshold"]
            )

        # Check brand value alignment
        if "brand_values" in config:
            alignment = await self._check_brand_alignment(
                context.action,
                config["brand_values"]
            )
            if not alignment.aligned:
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult.REQUIRES_APPROVAL,
                    dimension="reputational",
                    constraint_id="brand_values",
                    reason=f"Action may conflict with brand value: {alignment.conflicting_value}",
                    metadata={"alignment": alignment.to_dict()},
                    utilization=0.8  # Arbitrary for approval case
                )

        # Check sensitive topics
        if "sensitive_topics" in config:
            topic_match = await self._check_sensitive_topics(
                context.action,
                config["sensitive_topics"]
            )
            if topic_match:
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult.REQUIRES_APPROVAL,
                    dimension="reputational",
                    constraint_id="sensitive_topics",
                    reason=f"Action involves sensitive topic: {topic_match}",
                    metadata={"matched_topic": topic_match},
                    utilization=0.8
                )

        # Passed all checks
        return ConstraintCheckOutput(
            result=ConstraintCheckResult.PERMITTED,
            dimension="reputational",
            constraint_id="all",
            reason=None,
            metadata={"risk_score": risk_score},
            utilization=risk_score  # Use risk score as utilization
        )

    async def validate_config(
        self,
        config: Dict[str, Any]
    ) -> ValidationResult:
        """Validate configuration."""
        # Schema validation
        schema_result = self.schema.validate(config)
        if not schema_result.valid:
            return schema_result

        # Semantic validation
        errors = []

        # Check risk_threshold is reasonable
        if config.get("risk_threshold", 0) == 0:
            errors.append("risk_threshold of 0 would block all actions")
        if config.get("risk_threshold", 0) > 0.9:
            errors.append("risk_threshold > 0.9 provides minimal protection")

        # Check brand_values are known
        if "brand_values" in config:
            unknown_values = [
                v for v in config["brand_values"]
                if v not in self.brand_guidelines.known_values
            ]
            if unknown_values:
                errors.append(f"Unknown brand values: {unknown_values}")

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def can_tighten_to(
        self,
        parent_config: Dict[str, Any],
        child_config: Dict[str, Any]
    ) -> TighteningResult:
        """Check if child is valid tightening."""
        violations = []

        # Risk threshold must be <= parent
        if child_config.get("risk_threshold", 1) > parent_config.get("risk_threshold", 1):
            violations.append(
                f"risk_threshold: child {child_config['risk_threshold']} > parent {parent_config['risk_threshold']}"
            )

        # Brand values must be superset of parent (more values = more restrictions)
        parent_values = set(parent_config.get("brand_values", []))
        child_values = set(child_config.get("brand_values", []))
        if not parent_values.issubset(child_values):
            missing = parent_values - child_values
            violations.append(
                f"brand_values: child is missing parent values: {missing}"
            )

        # Sensitive topics must be superset
        parent_topics = set(parent_config.get("sensitive_topics", []))
        child_topics = set(child_config.get("sensitive_topics", []))
        if not parent_topics.issubset(child_topics):
            missing = parent_topics - child_topics
            violations.append(
                f"sensitive_topics: child is missing parent topics: {missing}"
            )

        return TighteningResult(
            valid=len(violations) == 0,
            violations=violations
        )

    def get_utilization(
        self,
        config: Dict[str, Any],
        current_state: Dict[str, Any]
    ) -> float:
        """Calculate utilization based on risk score."""
        risk_score = current_state.get("risk_score", 0)
        threshold = config.get("risk_threshold", 1)
        return min(risk_score / threshold, 1.0) if threshold > 0 else 1.0
```

---

## Interaction Rules Between Dimensions

### Dimension Interaction Model

When multiple constraint dimensions apply to an action, they must be evaluated together. The interaction model defines how results combine.

```python
class DimensionInteractionMode(Enum):
    """How dimension results combine."""

    ALL_MUST_PASS = "all_must_pass"            # Default: all dimensions must permit
    ANY_CAN_BLOCK = "any_can_block"            # Same as ALL_MUST_PASS
    WEIGHTED_VOTE = "weighted_vote"            # Weighted combination
    HIERARCHICAL = "hierarchical"              # Some dimensions override others

@dataclass
class DimensionInteractionConfig:
    """Configuration for dimension interaction."""

    mode: DimensionInteractionMode
    dimension_weights: Dict[str, float]        # For WEIGHTED_VOTE mode
    dimension_hierarchy: List[str]             # For HIERARCHICAL mode

class MultiDimensionEvaluator:
    """Evaluates constraints across multiple dimensions."""

    def __init__(
        self,
        registry: ConstraintDimensionRegistry,
        interaction_config: DimensionInteractionConfig
    ):
        self.registry = registry
        self.config = interaction_config

    async def evaluate(
        self,
        envelope: ConstraintEnvelope,
        context: ConstraintEvaluationContext
    ) -> MultiDimensionResult:
        """
        Evaluate all dimensions in the envelope.
        """
        results = {}

        # Evaluate each dimension
        for dim_id, dim_config in envelope.dimensions.items():
            dimension = self.registry.get(dim_id)
            if dimension:
                result = await dimension.evaluate(dim_config, context)
                results[dim_id] = result

        # Combine results based on interaction mode
        final_result = self._combine_results(results)

        return MultiDimensionResult(
            dimension_results=results,
            combined_result=final_result
        )

    def _combine_results(
        self,
        results: Dict[str, ConstraintCheckOutput]
    ) -> ConstraintCheckResult:
        """Combine dimension results based on interaction mode."""

        if self.config.mode == DimensionInteractionMode.ALL_MUST_PASS:
            # Any HARD_LIMIT blocks
            if any(r.result == ConstraintCheckResult.HARD_LIMIT for r in results.values()):
                return ConstraintCheckResult.HARD_LIMIT
            # Any REQUIRES_APPROVAL requires approval
            if any(r.result == ConstraintCheckResult.REQUIRES_APPROVAL for r in results.values()):
                return ConstraintCheckResult.REQUIRES_APPROVAL
            # Any SOFT_LIMIT warns
            if any(r.result == ConstraintCheckResult.SOFT_LIMIT for r in results.values()):
                return ConstraintCheckResult.SOFT_LIMIT
            return ConstraintCheckResult.PERMITTED

        elif self.config.mode == DimensionInteractionMode.WEIGHTED_VOTE:
            # Calculate weighted score
            total_weight = 0
            block_weight = 0
            for dim_id, result in results.items():
                weight = self.config.dimension_weights.get(dim_id, 1.0)
                total_weight += weight
                if result.result in [ConstraintCheckResult.HARD_LIMIT, ConstraintCheckResult.REQUIRES_APPROVAL]:
                    block_weight += weight

            if total_weight > 0 and block_weight / total_weight > 0.5:
                return ConstraintCheckResult.HARD_LIMIT
            return ConstraintCheckResult.PERMITTED

        elif self.config.mode == DimensionInteractionMode.HIERARCHICAL:
            # Check dimensions in hierarchy order; first non-PERMITTED wins
            for dim_id in self.config.dimension_hierarchy:
                if dim_id in results:
                    if results[dim_id].result != ConstraintCheckResult.PERMITTED:
                        return results[dim_id].result
            return ConstraintCheckResult.PERMITTED
```

---

## V1 Declarative Architecture (Second-Pass Hardening)

> **This section supersedes the arbitrary Python plugin interface for v1 deployments.** The Protocol-based `ConstraintDimension` interface above remains as the v2+ design target. For v1, ALL custom dimensions MUST use the declarative system below.

### Rationale

The red team review identified that the original `ConstraintDimension.evaluate()` method allows arbitrary Python code execution. Combined with the placeholder `_security_review()`, this creates a direct code injection pathway. The declarative architecture eliminates this risk by restricting custom dimensions to pre-defined operators that cannot execute arbitrary code.

### DeclarativeConstraintDimension

```python
class DeclarativeOperator(Enum):
    """Pre-defined operators for declarative constraints. No code execution."""
    LESS_THAN = "lt"
    LESS_EQUAL = "le"
    GREATER_THAN = "gt"
    GREATER_EQUAL = "ge"
    EQUAL = "eq"
    NOT_EQUAL = "ne"
    IN_SET = "in"
    NOT_IN_SET = "not_in"
    CONTAINS = "contains"
    MATCHES_REGEX = "regex"          # Pre-compiled, bounded execution, ReDoS-safe
    BETWEEN = "between"              # Inclusive range check

    def evaluate(self, value: Any, threshold: Any) -> bool:
        """Evaluate operator. All operators are O(n) or better — no arbitrary code."""
        if self == DeclarativeOperator.MATCHES_REGEX:
            return self._safe_regex_match(value, threshold)
        # ... other operators use simple comparisons ...

    @staticmethod
    def _safe_regex_match(value: str, pattern: str, timeout_ms: int = 50) -> bool:
        """ReDoS-safe regex matching with defense-in-depth.

        Defense layers (ordered by priority):
        1. Static analysis: reject patterns with super-linear complexity
        2. Engine selection: prefer google-re2 (linear-time guarantee)
        3. Execution timeout: 50ms signal-based fallback for stdlib re
        4. Pattern complexity limits: max 100 chars

        Static analysis uses three complementary techniques:
        - Heuristic regex for common nested quantifier patterns
        - Optional rxxr2 integration for formal super-linear detection
        - Pattern length limit as coarse-grained backstop
        """
        # Layer 1a: Pattern length limit (coarse-grained)
        if len(pattern) > 100:
            raise ConstraintConfigError(
                f"Regex pattern too complex: {len(pattern)} chars (max 100)."
            )

        # Layer 1b: Heuristic nested quantifier detection
        DANGEROUS_PATTERNS = re.compile(r'(\(.+[\*\+]\)[\*\+\?])|(\(\?[^)]*\))')
        if DANGEROUS_PATTERNS.search(pattern):
            raise ConstraintConfigError(
                f"Regex pattern rejected: nested quantifiers detected. "
                f"Pattern '{pattern}' could cause exponential backtracking (ReDoS)."
            )

        # Layer 1c: Formal static analysis via rxxr2 (if available)
        # rxxr2 detects super-linear regex behavior that heuristics miss.
        # Install: pip install rxxr2 (optional dependency)
        # Reference: https://github.com/superhuman/rxxr2
        try:
            from rxxr2 import is_vulnerable
            if is_vulnerable(pattern):
                raise ConstraintConfigError(
                    f"Regex pattern rejected by rxxr2 static analysis: "
                    f"super-linear backtracking detected in '{pattern}'."
                )
        except ImportError:
            pass  # rxxr2 not installed — rely on heuristic + re2/timeout

        # Layer 2: Prefer google-re2 (guarantees linear-time matching)
        try:
            import re2
            return bool(re2.match(pattern, str(value)))
        except ImportError:
            pass

        # Layer 3: stdlib re with signal-based timeout (Unix) or
        # thread-based timeout (Windows) to cap execution at timeout_ms
        import signal
        import platform

        compiled = re.compile(pattern)

        if platform.system() != "Windows":
            # Unix: use SIGALRM for precise timeout
            def _timeout_handler(signum, frame):
                raise ConstraintConfigError(
                    f"Regex execution timed out after {timeout_ms}ms. "
                    f"Pattern '{pattern}' may have super-linear complexity."
                )

            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            # signal.setitimer provides sub-second precision
            signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000.0)
            try:
                result = bool(compiled.match(str(value)))
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)  # Cancel timer
                signal.signal(signal.SIGALRM, old_handler)
            return result
        else:
            # Windows: thread-based timeout (best-effort)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(compiled.match, str(value))
                try:
                    match = future.result(timeout=timeout_ms / 1000.0)
                    return bool(match)
                except concurrent.futures.TimeoutError:
                    raise ConstraintConfigError(
                        f"Regex execution timed out after {timeout_ms}ms. "
                        f"Pattern '{pattern}' may have super-linear complexity."
                    )

class DeclarativeConstraintDimension(ConstraintDimension):
    """
    Safe, declarative constraint dimension for v1.

    Uses pre-defined operators instead of arbitrary Python code.
    Can be defined entirely via JSON/YAML configuration.

    Example YAML:
        dimension_id: "reputational"
        version: "1.0.0"
        rules:
          - field: "risk_score"
            operator: "le"
            threshold: 0.3
            result: "hard_limit"
            reason: "Risk score {value} exceeds threshold {threshold}"
          - field: "topic"
            operator: "not_in"
            values: ["politics", "religion"]
            result: "requires_approval"
    """

    def __init__(self, config: Dict[str, Any]):
        self._id = config["dimension_id"]
        self._version = config.get("version", "1.0.0")
        self._rules = [DeclarativeRule.from_dict(r) for r in config["rules"]]
        self._schema = self._build_schema(config)

    async def evaluate(
        self, config: Dict[str, Any], context: ConstraintEvaluationContext
    ) -> ConstraintCheckOutput:
        """Evaluate using pre-defined operators only. No code execution."""
        for rule in self._rules:
            value = self._extract_value(rule.field, config, context)
            if rule.operator.evaluate(value, rule.threshold):
                return ConstraintCheckOutput(
                    result=ConstraintCheckResult(rule.result),
                    dimension=self._id,
                    constraint_id=rule.field,
                    reason=rule.reason.format(value=value, threshold=rule.threshold),
                    metadata={"field": rule.field, "value": value},
                    utilization=self._compute_utilization(value, rule),
                )
        return ConstraintCheckOutput(
            result=ConstraintCheckResult.PERMITTED,
            dimension=self._id, constraint_id="all",
            reason=None, metadata={}, utilization=0.0,
        )
```

### YAML-Based Dimension Definition

Organizations can define custom dimensions without writing Python code:

```yaml
# reputational_constraint.yaml
dimension_id: "reputational"
version: "1.0.0"
description: "Reputational risk constraint dimension"

schema:
  risk_threshold:
    type: number
    min: 0.0
    max: 1.0
    required: true
  sensitive_topics:
    type: list
    items: string
    required: false

rules:
  - field: "context.risk_score"
    operator: "gt"
    threshold_field: "risk_threshold"
    result: "hard_limit"
    reason: "Risk score {value} exceeds threshold {threshold}"

  - field: "context.topic"
    operator: "in"
    values_field: "sensitive_topics"
    result: "requires_approval"
    reason: "Action involves sensitive topic: {value}"

tightening_rules:
  - field: "risk_threshold"
    direction: "child_must_be_le"
  - field: "sensitive_topics"
    direction: "child_must_be_superset"
```

### v2+ Plugin Roadmap

The full Protocol-based plugin architecture (arbitrary Python `ConstraintDimension` subclasses) is deferred to v2+ with these prerequisites:

1. **WASM Sandboxing**: Replace RestrictedPython with WebAssembly sandbox (e.g., Wasmtime)
2. **Organization-Level Signing**: All plugins must be signed by the organization's security team
3. **Capability-Based Security**: Plugins must declare capabilities (network, filesystem, etc.)
4. **Plugin Audit**: All plugin evaluations logged with input/output hashes
5. **Plugin Marketplace Security**: Supply chain verification for shared plugins

Until these are implemented, the declarative system provides safe extensibility without code execution risk.

---

## Security Considerations

### Plugin Sandboxing (v2+ Only)

> **Note**: This section describes the v2+ sandboxing design. In v1, sandboxing is not needed because only declarative dimensions (pre-defined operators) are permitted.

Custom constraint dimensions run in a sandboxed environment:

```python
@dataclass
class PluginSandboxConfig:
    """Security configuration for plugin execution."""

    max_execution_time: timedelta = timedelta(seconds=5)
    max_memory_mb: int = 100
    network_allowed: bool = False
    filesystem_allowed: bool = False
    subprocess_allowed: bool = False
    allowed_imports: List[str] = field(default_factory=lambda: [
        "typing", "dataclasses", "datetime", "enum", "json", "re"
    ])

class PluginSandbox:
    """Sandboxed execution environment for plugins."""

    async def execute(
        self,
        plugin: ConstraintDimension,
        method: str,
        args: tuple,
        kwargs: dict,
        config: PluginSandboxConfig
    ) -> Any:
        """
        Execute plugin method in sandbox.
        """
        # Use RestrictedPython or similar for Python sandboxing
        # Or containerization for stronger isolation
        pass
```

### Audit Logging

All custom dimension evaluations are logged:

```python
@dataclass
class ConstraintEvaluationLog:
    """Audit log entry for constraint evaluation."""

    timestamp: datetime
    agent_id: str
    action: str
    dimension_id: str
    dimension_version: str
    config_hash: str                           # Hash of config (not config itself)
    result: ConstraintCheckResult
    evaluation_time_ms: float
    is_custom_dimension: bool
    errors: Optional[List[str]]
```

---

## SDK-Level APIs

### Dimension Registration

```python
from kaizen.trust.constraints import (
    ConstraintDimensionRegistry,
    ConstraintDimension
)

# Get the registry
registry = ConstraintDimensionRegistry.get_instance()

# Register a custom dimension
registry.register(
    ReputationalConstraintDimension(
        risk_scorer=my_risk_scorer,
        brand_guidelines=my_brand_guidelines
    )
)

# List available dimensions
dimensions = registry.list_dimensions()
# ['financial', 'operational', 'temporal', 'data_access', 'communication', 'reputational']

# Get schema for a dimension
schema = registry.get_schema("reputational")
```

### Envelope Construction

```python
from kaizen.trust.constraints import ConstraintEnvelope

# Create envelope with custom dimension
envelope = ConstraintEnvelope(
    agent_id="agent-001",
    dimensions={
        "financial": {
            "max_transaction": 5000,
            "daily_limit": 25000
        },
        "reputational": {  # Custom dimension
            "risk_threshold": 0.3,
            "brand_values": ["innovation", "integrity"],
            "sensitive_topics": ["legal", "compliance"]
        }
    }
)

# Validate envelope
validation = envelope.validate()
if not validation.valid:
    raise ValueError(f"Invalid envelope: {validation.errors}")
```

### Evaluation

```python
from kaizen.trust.constraints import MultiDimensionEvaluator

evaluator = MultiDimensionEvaluator(
    registry=registry,
    interaction_config=DimensionInteractionConfig(
        mode=DimensionInteractionMode.ALL_MUST_PASS
    )
)

# Evaluate action against envelope
result = await evaluator.evaluate(
    envelope=envelope,
    context=ConstraintEvaluationContext(
        agent_id="agent-001",
        action="send_email",
        resource="customer_complaint",
        timestamp=datetime.now(timezone.utc),
        execution_context={"amount": 1000, "topic": "complaint_response"}
    )
)

if result.combined_result == ConstraintCheckResult.PERMITTED:
    # Proceed with action
    pass
elif result.combined_result == ConstraintCheckResult.REQUIRES_APPROVAL:
    # Request human approval
    pass
else:
    # Block action
    raise ConstraintViolationError(result)
```

---

## Implementation Roadmap

### Phase 1: Declarative Constraint System — v1 (SDK)

1. Define `ConstraintDimension` protocol (interface only)
2. Implement `DeclarativeConstraintDimension` with pre-defined operators
3. Implement `ConstraintDimensionRegistry` (built-in override blocked)
4. Implement YAML/JSON dimension definition loader
5. Implement `MultiDimensionEvaluator`
6. Refactor built-in dimensions to use protocol

### Phase 2: Audit and Monitoring (SDK + Platform)

1. Implement audit logging for all dimension evaluations
2. Implement dimension utilization dashboards
3. Create declarative dimension testing framework
4. Document dimension development guide (YAML-based)

### Phase 3: Full Plugin Architecture — v2 (SDK + Platform, DEFERRED)

> **Prerequisites**: WASM sandboxing, organization-level signing, capability-based security

1. Implement WASM sandbox for arbitrary Python dimensions
2. Implement plugin signing and verification
3. Implement capability-based security declarations
4. Create security review automation (replacing placeholder)
5. Create plugin testing framework with adversarial tests

### Phase 4: Ecosystem — v2+ (Community, DEFERRED)

1. Publish plugin SDK with WASM toolchain
2. Create plugin marketplace with supply chain verification
3. Establish plugin certification process
4. Community plugin contributions with review workflow

---

## Summary

The constraint extensibility design enables organizations to define custom constraint dimensions while maintaining security and verifiability. Key design decisions:

1. **Protocol-based**: All dimensions implement a common interface
2. **Schema-driven**: Configurations are validated against JSON Schema
3. **Declarative-first (v1)**: Custom dimensions use pre-defined operators only — no code execution
4. **Sandboxed (v2+)**: Full plugin extensibility deferred until WASM sandboxing is implemented
5. **Immutable built-ins**: Built-in dimensions can never be overridden (prevents malicious replacement)
6. **Auditable**: All evaluations are logged
7. **Composable**: Multiple dimensions interact through defined rules

This architecture allows the constraint system to evolve with organizational needs while preserving the security guarantees that EATP requires. The v1/v2 split ensures that the highest-risk feature (arbitrary code execution in plugins) is properly secured before deployment.
