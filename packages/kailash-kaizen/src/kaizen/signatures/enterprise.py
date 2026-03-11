"""
Enterprise Signature Programming Extensions - BLOCKER-002

This module implements enterprise-grade signature features that exceed DSPy capabilities:
1. Enterprise Security Validation
2. Multi-Modal Signature Support
3. Signature Composition for Complex Workflows
4. Audit and Compliance Features
5. Privacy-First Design
6. Advanced Type System

These features position Kaizen as superior to DSPy by providing enterprise-ready
signature programming with security, compliance, and advanced composition capabilities.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .core import Signature, SignatureValidator, ValidationResult

logger = logging.getLogger(__name__)


class EnterpriseSignatureValidator(SignatureValidator):
    """
    Enterprise-grade signature validator with security and compliance features.

    Extends base validator with:
    - Security validation
    - Privacy compliance checking
    - Audit readiness validation
    - Enterprise policy enforcement
    """

    def __init__(self):
        """Initialize enterprise signature validator."""
        super().__init__()

        # Enterprise security requirements
        self.security_requirements = {
            "encryption_required": ["customer_data", "personal_info", "financial_data"],
            "audit_required": ["compliance", "financial", "medical", "legal"],
            "privacy_required": ["pii", "personal", "customer", "user_data"],
        }

        # Compliance frameworks
        self.compliance_frameworks = {
            "gdpr": ["personal_data", "privacy", "consent"],
            "hipaa": ["medical", "health", "patient"],
            "sox": ["financial", "audit", "compliance"],
            "pci": ["payment", "credit_card", "financial"],
        }

    def validate(
        self, signature: Union[Signature, "SignatureComposition"]
    ) -> ValidationResult:
        """
        Validate signature with enterprise security and compliance checks.

        Args:
            signature: Signature or composition to validate

        Returns:
            ValidationResult with enterprise validation details
        """
        # Start with base validation
        result = super().validate(signature)

        # Add enterprise validation
        if hasattr(signature, "signatures"):  # SignatureComposition
            self._validate_enterprise_composition(signature, result)
        else:
            self._validate_enterprise_signature(signature, result)

        return result

    def _validate_enterprise_signature(
        self, signature: Signature, result: ValidationResult
    ):
        """Validate enterprise requirements for a single signature."""
        # Security validation
        security_errors = self._validate_security_requirements(signature)
        result.errors.extend(security_errors)
        result.security_validated = len(security_errors) == 0

        # Privacy compliance validation
        privacy_errors = self._validate_privacy_compliance(signature)
        result.errors.extend(privacy_errors)
        result.privacy_compliance = len(privacy_errors) == 0

        # Audit readiness validation
        audit_errors = self._validate_audit_readiness(signature)
        result.errors.extend(audit_errors)
        result.audit_ready = len(audit_errors) == 0

        # Update overall validity
        result.is_valid = len(result.errors) == 0

    def _validate_enterprise_composition(self, composition, result: ValidationResult):
        """Validate enterprise requirements for signature composition."""
        for signature in composition.signatures:
            self._validate_enterprise_signature(signature, result)

        # Additional composition-level enterprise checks
        composition_errors = self._validate_composition_security(composition)
        result.errors.extend(composition_errors)

    def _validate_security_requirements(self, signature: Signature) -> List[str]:
        """Validate security requirements for signature."""
        errors = []

        # Check if signature handles sensitive data
        sensitive_inputs = self._identify_sensitive_inputs(signature)
        if sensitive_inputs:
            # Ensure encryption is configured
            security_config = signature.parameters.get("security_config", {})
            if not security_config.get(
                "encryption", True
            ):  # Default to True, fail if explicitly False
                errors.append(
                    f"Encryption required for sensitive inputs: {sensitive_inputs}"
                )

            # Ensure audit logging is enabled
            if not signature.requires_audit_trail:
                errors.append("Audit trail required for sensitive data processing")

        # Check for enterprise signature type compliance
        if signature.signature_type == "enterprise":
            security_config = signature.parameters.get("security_config", {})
            if not security_config:
                errors.append(
                    "Enterprise signature type requires security configuration"
                )
            elif security_config.get("encryption") is False:
                errors.append("Enterprise signatures cannot disable encryption")

        return errors

    def _validate_privacy_compliance(self, signature: Signature) -> List[str]:
        """Validate privacy compliance requirements."""
        errors = []

        # Check for PII handling
        pii_inputs = self._identify_pii_inputs(signature)
        if pii_inputs:
            if not signature.requires_privacy_check:
                errors.append(f"Privacy check required for PII inputs: {pii_inputs}")

            # Check for data minimization
            if len(signature.outputs) > 3:
                errors.append(
                    "Data minimization: Consider reducing outputs for PII processing"
                )

        # Check compliance framework requirements
        for framework, keywords in self.compliance_frameworks.items():
            if any(
                keyword in str(signature.inputs + signature.outputs).lower()
                for keyword in keywords
            ):
                if not self._check_framework_compliance(signature, framework):
                    errors.append(
                        f"{framework.upper()} compliance requirements not met"
                    )

        return errors

    def _validate_audit_readiness(self, signature: Signature) -> List[str]:
        """Validate audit readiness requirements."""
        errors = []

        # Check for audit-sensitive operations
        audit_keywords = ["compliance", "financial", "medical", "legal", "audit"]
        signature_text = str(signature.inputs + signature.outputs).lower()

        if any(keyword in signature_text for keyword in audit_keywords):
            if not signature.requires_audit_trail:
                errors.append(
                    "Audit trail required for compliance-sensitive operations"
                )

            # Check for proper metadata tracking
            if "metadata" not in str(signature.outputs).lower():
                errors.append("Metadata output recommended for audit compliance")

        return errors

    def _validate_composition_security(self, composition) -> List[str]:
        """Validate security requirements for signature composition."""
        errors = []

        # Check for data flow security
        for i in range(len(composition.signatures) - 1):
            current_sig = composition.signatures[i]
            next_sig = composition.signatures[i + 1]

            # Ensure sensitive data doesn't flow to less secure components
            if self._has_sensitive_outputs(
                current_sig
            ) and not self._has_security_config(next_sig):
                errors.append(
                    f"Sensitive data flow from step {i} to less secure step {i+1}"
                )

        return errors

    def _identify_sensitive_inputs(self, signature: Signature) -> List[str]:
        """Identify sensitive inputs that require encryption."""
        sensitive_inputs = []
        for input_name in signature.inputs:
            input_lower = input_name.lower()
            for keyword_list in self.security_requirements.values():
                if any(keyword in input_lower for keyword in keyword_list):
                    sensitive_inputs.append(input_name)
                    break
        return sensitive_inputs

    def _identify_pii_inputs(self, signature: Signature) -> List[str]:
        """Identify PII inputs that require privacy protection."""
        pii_keywords = [
            "name",
            "email",
            "phone",
            "address",
            "ssn",
            "id",
            "personal",
            "customer",
            "user",
        ]
        pii_inputs = []

        for input_name in signature.inputs:
            input_lower = input_name.lower()
            if any(keyword in input_lower for keyword in pii_keywords):
                pii_inputs.append(input_name)

        return pii_inputs

    def _check_framework_compliance(self, signature: Signature, framework: str) -> bool:
        """Check compliance with specific framework."""
        if framework == "gdpr":
            return (
                signature.requires_privacy_check
                and signature.requires_audit_trail
                and "consent" in str(signature.parameters).lower()
            )
        elif framework == "hipaa":
            return (
                signature.parameters.get("security_config", {}).get("encryption")
                and signature.requires_audit_trail
            )
        elif framework == "sox":
            return signature.requires_audit_trail
        elif framework == "pci":
            return signature.parameters.get("security_config", {}).get("encryption")

        return False

    def _has_sensitive_outputs(self, signature: Signature) -> bool:
        """Check if signature has sensitive outputs."""
        sensitive_keywords = ["customer", "personal", "financial", "medical", "private"]
        outputs_text = str(signature.outputs).lower()
        return any(keyword in outputs_text for keyword in sensitive_keywords)

    def _has_security_config(self, signature: Signature) -> bool:
        """Check if signature has security configuration."""
        return (
            signature.parameters.get("security_config") is not None
            or signature.requires_privacy_check
            or signature.requires_audit_trail
        )


class MultiModalSignature(Signature):
    """
    Multi-modal signature supporting text, image, audio, and video inputs.

    Extends base signature with multi-modal capabilities that exceed DSPy:
    - Vision support (images, videos)
    - Audio processing support
    - Multi-modal coordination
    - Cross-modal reasoning
    """

    def __init__(
        self,
        inputs: List[str],
        outputs: List[Union[str, List[str]]],
        input_types: Optional[Dict[str, str]] = None,
        signature_type: str = "multi_modal",
        supported_modalities: Optional[List[str]] = None,
        cross_modal_reasoning: bool = False,
        **kwargs,
    ):
        """
        Initialize multi-modal signature.

        Args:
            inputs: List of input parameter names
            outputs: List of output parameter names
            input_types: Type mapping for inputs (text, image, audio, video)
            signature_type: Should be "multi_modal"
            supported_modalities: Explicitly supported modalities
            cross_modal_reasoning: Enable cross-modal reasoning capabilities
            **kwargs: Additional signature parameters
        """
        # Remove supports_multi_modal from kwargs if present to avoid duplicate
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k != "supports_multi_modal"
        }

        # Set default input_types if not provided
        if input_types is None:
            input_types = {}
            for input_name in inputs:
                # Auto-detect type based on name
                if any(
                    keyword in input_name.lower()
                    for keyword in ["image", "img", "picture", "photo"]
                ):
                    input_types[input_name] = "image"
                elif any(
                    keyword in input_name.lower()
                    for keyword in ["audio", "sound", "speech", "voice"]
                ):
                    input_types[input_name] = "audio"
                elif any(
                    keyword in input_name.lower()
                    for keyword in ["video", "clip", "movie"]
                ):
                    input_types[input_name] = "video"
                elif any(
                    keyword in input_name.lower()
                    for keyword in ["3d", "model", "mesh", "object"]
                ):
                    # Detect unsupported modalities
                    input_types[input_name] = "3d_model"
                else:
                    input_types[input_name] = "text"

        super().__init__(
            inputs=inputs,
            outputs=outputs,
            signature_type=signature_type,
            input_types=input_types,
            supports_multi_modal=True,
            **filtered_kwargs,
        )

        self.supported_modalities = supported_modalities or list(
            set(input_types.values())
        )
        self.cross_modal_reasoning = cross_modal_reasoning

        # Multi-modal processing configuration
        self.modality_config = {
            "image": {
                "max_resolution": "1024x1024",
                "supported_formats": ["jpg", "png", "gif", "webp"],
                "processing_model": "vision-capable",
            },
            "audio": {
                "max_duration": 300,  # seconds
                "supported_formats": ["mp3", "wav", "ogg"],
                "processing_model": "audio-capable",
            },
            "video": {
                "max_duration": 600,  # seconds
                "max_resolution": "1080p",
                "supported_formats": ["mp4", "avi", "mov"],
                "processing_model": "video-capable",
            },
        }

    def validate_modality_support(self) -> Tuple[bool, List[str]]:
        """
        Validate that all input modalities are supported.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        supported_types = {"text", "image", "audio", "video"}

        for input_name, input_type in self.input_types.items():
            if input_type not in supported_types:
                errors.append(
                    f"Unsupported modality '{input_type}' for input '{input_name}'"
                )

        return len(errors) == 0, errors

    def get_modality_requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get processing requirements for each modality."""
        requirements = {}

        for input_name, input_type in self.input_types.items():
            if input_type in self.modality_config:
                requirements[input_name] = self.modality_config[input_type]

        return requirements

    def requires_special_model(self) -> bool:
        """Check if signature requires special model capabilities."""
        non_text_modalities = {t for t in self.input_types.values() if t != "text"}
        return len(non_text_modalities) > 0


class SignatureComposition:
    """
    Composition system for combining multiple signatures into complex workflows.

    Enables signature-based workflow orchestration that exceeds DSPy capabilities:
    - Sequential composition
    - Parallel composition
    - Conditional composition
    - Data flow management
    - Error handling and recovery
    """

    def __init__(
        self,
        signatures: List[Signature],
        composition_type: str = "sequential",
        name: Optional[str] = None,
        error_handling: str = "fail_fast",
    ):
        """
        Initialize signature composition.

        Args:
            signatures: List of signatures to compose
            composition_type: Type of composition (sequential, parallel, conditional)
            name: Optional composition name
            error_handling: Error handling strategy (fail_fast, continue, retry)
        """
        self.signatures = signatures
        self.composition_type = composition_type
        self.name = name or f"composition_{int(time.time())}"
        self.error_handling = error_handling

        # Composition metadata
        self.data_flow_mapping = self._build_data_flow_mapping()
        self.execution_plan = self._build_execution_plan()
        self.dependencies = self._analyze_dependencies()

    def _build_data_flow_mapping(self) -> Dict[str, Any]:
        """Build data flow mapping between signatures."""
        mapping = {
            "flows": [],
            "inputs": self._get_composition_inputs(),
            "outputs": self._get_composition_outputs(),
        }

        if self.composition_type == "sequential":
            for i in range(len(self.signatures) - 1):
                current_sig = self.signatures[i]
                next_sig = self.signatures[i + 1]

                # Find output->input mappings
                flow = {
                    "from_signature": i,
                    "to_signature": i + 1,
                    "mappings": self._find_compatible_mappings(current_sig, next_sig),
                }
                mapping["flows"].append(flow)

        return mapping

    def _build_execution_plan(self) -> List[Dict[str, Any]]:
        """Build execution plan for composition."""
        plan = []

        if self.composition_type == "sequential":
            for i, signature in enumerate(self.signatures):
                step = {
                    "step_id": i,
                    "signature": signature,
                    "depends_on": [i - 1] if i > 0 else [],
                    "provides_inputs_to": (
                        [i + 1] if i < len(self.signatures) - 1 else []
                    ),
                }
                plan.append(step)

        elif self.composition_type == "parallel":
            for i, signature in enumerate(self.signatures):
                step = {
                    "step_id": i,
                    "signature": signature,
                    "depends_on": [],
                    "provides_inputs_to": [],
                    "parallel_execution": True,
                }
                plan.append(step)

        return plan

    def _analyze_dependencies(self) -> Dict[str, List[str]]:
        """Analyze data dependencies between signatures."""
        dependencies = {}

        for i, signature in enumerate(self.signatures):
            deps = []

            # Check which previous signatures provide required inputs
            for j in range(i):
                prev_signature = self.signatures[j]
                prev_outputs = self._flatten_outputs(prev_signature.outputs)

                if any(input_name in prev_outputs for input_name in signature.inputs):
                    deps.append(f"signature_{j}")

            dependencies[f"signature_{i}"] = deps

        return dependencies

    def _get_composition_inputs(self) -> List[str]:
        """Get external inputs required by composition."""
        all_inputs = set()
        all_outputs = set()

        # Collect all inputs and outputs
        for signature in self.signatures:
            all_inputs.update(signature.inputs)
            all_outputs.update(self._flatten_outputs(signature.outputs))

        # External inputs are inputs not provided by any signature output
        external_inputs = all_inputs - all_outputs
        return list(external_inputs)

    def _get_composition_outputs(self) -> List[str]:
        """Get final outputs produced by composition."""
        if self.composition_type == "sequential":
            # Outputs of the last signature
            return self._flatten_outputs(self.signatures[-1].outputs)
        elif self.composition_type == "parallel":
            # Combined outputs of all signatures
            all_outputs = []
            for signature in self.signatures:
                all_outputs.extend(self._flatten_outputs(signature.outputs))
            return all_outputs
        else:
            return []

    def _find_compatible_mappings(
        self, sig1: Signature, sig2: Signature
    ) -> Dict[str, str]:
        """Find compatible output->input mappings between signatures."""
        mappings = {}
        sig1_outputs = self._flatten_outputs(sig1.outputs)

        for output in sig1_outputs:
            if output in sig2.inputs:
                mappings[output] = output

        return mappings

    def _flatten_outputs(self, outputs: List[Union[str, List[str]]]) -> List[str]:
        """Flatten nested output lists."""
        flattened = []
        for output in outputs:
            if isinstance(output, list):
                flattened.extend(output)
            else:
                flattened.append(output)
        return flattened

    def validate_composition(self) -> Tuple[bool, List[str]]:
        """
        Validate the composition for correctness.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate individual signatures
        validator = SignatureValidator()
        for i, signature in enumerate(self.signatures):
            result = validator.validate(signature)
            if not result.is_valid:
                errors.extend([f"Signature {i}: {error}" for error in result.errors])

        # Validate composition-specific requirements
        if self.composition_type == "sequential":
            errors.extend(self._validate_sequential_composition())
        elif self.composition_type == "parallel":
            errors.extend(self._validate_parallel_composition())

        return len(errors) == 0, errors

    def _validate_sequential_composition(self) -> List[str]:
        """Validate sequential composition requirements."""
        errors = []

        for i in range(len(self.signatures) - 1):
            current_sig = self.signatures[i]
            next_sig = self.signatures[i + 1]

            # Check for data flow compatibility
            mappings = self._find_compatible_mappings(current_sig, next_sig)
            required_inputs = set(next_sig.inputs) - set(self._get_composition_inputs())
            provided_outputs = set(mappings.keys())

            missing_inputs = required_inputs - provided_outputs
            if missing_inputs:
                errors.append(f"Step {i+1} missing required inputs: {missing_inputs}")

        return errors

    def _validate_parallel_composition(self) -> List[str]:
        """Validate parallel composition requirements."""
        errors = []

        # Check for input conflicts
        all_inputs = []
        for signature in self.signatures:
            all_inputs.extend(signature.inputs)

        # Ensure all parallel signatures can get their required inputs
        external_inputs = set(self._get_composition_inputs())
        for i, signature in enumerate(self.signatures):
            required_inputs = set(signature.inputs)
            if not required_inputs.issubset(external_inputs):
                missing = required_inputs - external_inputs
                errors.append(
                    f"Parallel signature {i} missing external inputs: {missing}"
                )

        return errors

    def get_execution_order(self) -> List[int]:
        """Get execution order for signatures based on dependencies."""
        if self.composition_type == "sequential":
            return list(range(len(self.signatures)))
        elif self.composition_type == "parallel":
            return list(range(len(self.signatures)))  # All execute in parallel
        else:
            # For conditional or custom compositions, implement topological sort
            return self._topological_sort()

    def _topological_sort(self) -> List[int]:
        """Perform topological sort based on dependencies."""
        # Simplified topological sort implementation
        visited = set()
        order = []

        def visit(node):
            if node in visited:
                return
            visited.add(node)

            # Visit dependencies first (simplified)
            deps = self.dependencies.get(f"signature_{node}", [])
            for dep in deps:
                dep_index = int(dep.split("_")[1])
                visit(dep_index)

            order.append(node)

        for i in range(len(self.signatures)):
            visit(i)

        return order


class SignatureRegistry:
    """
    Enterprise signature registry for managing and versioning signatures.

    Provides:
    - Signature storage and retrieval
    - Version management
    - Template libraries
    - Sharing and collaboration
    - Performance analytics
    """

    def __init__(self):
        """Initialize signature registry."""
        self.signatures: Dict[str, Dict[str, Any]] = {}
        self.templates: Dict[str, "SignatureTemplate"] = {}
        self.compositions: Dict[str, SignatureComposition] = {}
        self.performance_data: Dict[str, List[Dict[str, Any]]] = {}

    def register_signature(
        self,
        name: str,
        signature: Signature,
        version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Register a signature in the registry.

        Args:
            name: Signature name
            signature: Signature instance
            version: Version string
            metadata: Optional metadata

        Returns:
            Signature ID for retrieval
        """
        signature_id = f"{name}:{version}"

        self.signatures[signature_id] = {
            "signature": signature,
            "name": name,
            "version": version,
            "metadata": metadata or {},
            "created_at": time.time(),
            "usage_count": 0,
            "performance_history": [],
        }

        logger.info(f"Registered signature: {signature_id}")
        return signature_id

    def get_signature(
        self, name: str, version: Optional[str] = None
    ) -> Optional[Signature]:
        """
        Retrieve signature from registry.

        Args:
            name: Signature name
            version: Optional version (latest if not specified)

        Returns:
            Signature instance or None if not found
        """
        if version:
            signature_id = f"{name}:{version}"
            if signature_id in self.signatures:
                self.signatures[signature_id]["usage_count"] += 1
                return self.signatures[signature_id]["signature"]
        else:
            # Find latest version
            matching_sigs = [
                (sig_id, sig_data)
                for sig_id, sig_data in self.signatures.items()
                if sig_data["name"] == name
            ]

            if matching_sigs:
                # Sort by version and get latest
                latest = max(matching_sigs, key=lambda x: x[1]["version"])
                latest[1]["usage_count"] += 1
                return latest[1]["signature"]

        return None

    def list_signatures(
        self, filter_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List registered signatures.

        Args:
            filter_type: Optional signature type filter

        Returns:
            List of signature metadata
        """
        signatures = []

        for sig_id, sig_data in self.signatures.items():
            if not filter_type or sig_data["signature"].signature_type == filter_type:
                signatures.append(
                    {
                        "id": sig_id,
                        "name": sig_data["name"],
                        "version": sig_data["version"],
                        "type": sig_data["signature"].signature_type,
                        "usage_count": sig_data["usage_count"],
                        "created_at": sig_data["created_at"],
                    }
                )

        return sorted(signatures, key=lambda x: x["usage_count"], reverse=True)

    def register_template(self, template: "SignatureTemplate") -> str:
        """Register a signature template."""
        template_id = f"template_{template.name}"
        self.templates[template_id] = template
        logger.info(f"Registered template: {template_id}")
        return template_id

    def get_template(self, name: str) -> Optional["SignatureTemplate"]:
        """Retrieve signature template by name."""
        template_id = f"template_{name}"
        return self.templates.get(template_id)

    def register_composition(self, composition: SignatureComposition) -> str:
        """Register a signature composition."""
        composition_id = f"composition_{composition.name}"
        self.compositions[composition_id] = composition
        logger.info(f"Registered composition: {composition_id}")
        return composition_id

    def get_composition(self, name: str) -> Optional[SignatureComposition]:
        """Retrieve signature composition by name."""
        composition_id = f"composition_{name}"
        return self.compositions.get(composition_id)

    def record_performance(self, signature_id: str, performance_data: Dict[str, Any]):
        """Record performance data for a signature."""
        if signature_id not in self.performance_data:
            self.performance_data[signature_id] = []

        performance_record = {"timestamp": time.time(), "data": performance_data}

        self.performance_data[signature_id].append(performance_record)

        # Keep only last 100 records
        if len(self.performance_data[signature_id]) > 100:
            self.performance_data[signature_id] = self.performance_data[signature_id][
                -100:
            ]

    def get_performance_analytics(self, signature_id: str) -> Dict[str, Any]:
        """Get performance analytics for a signature."""
        if signature_id not in self.performance_data:
            return {}

        records = self.performance_data[signature_id]
        if not records:
            return {}

        # Calculate basic analytics
        execution_times = [r["data"].get("execution_time", 0) for r in records]
        token_usage = [r["data"].get("token_usage", 0) for r in records]

        analytics = {
            "total_executions": len(records),
            "avg_execution_time": (
                sum(execution_times) / len(execution_times) if execution_times else 0
            ),
            "avg_token_usage": (
                sum(token_usage) / len(token_usage) if token_usage else 0
            ),
            "last_30_days": len(
                [r for r in records if time.time() - r["timestamp"] < 2592000]
            ),
        }

        return analytics
