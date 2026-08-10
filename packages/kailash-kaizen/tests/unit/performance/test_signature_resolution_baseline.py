"""
Signature Resolution Performance Baseline Tests

Purpose: Establish performance baselines for signature resolution operations
Target: <100ms p95 latency for all signature operations
Context: TODO-151 Phase 1 - Signature Resolution Optimization

These tests use simple timing measurements to provide repeatable baselines
and regression detection for signature resolution performance.
"""

import statistics
import time

from kaizen.signatures import (
    InputField,
    OutputField,
    Signature,
    SignatureCompiler,
    SignatureParser,
    SignatureValidator,
)
from kaizen.signatures.enterprise import MultiModalSignature


def measure_performance(func, *args, iterations=50, **kwargs):
    """Helper to measure function performance."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        times.append((end - start) * 1000)  # Convert to ms

    return {
        "result": result,
        "mean": statistics.mean(times),
        "median": statistics.median(times),
        "min": min(times),
        "max": max(times),
        "p95": (
            statistics.quantiles(times, n=20)[18] if len(times) >= 20 else max(times)
        ),
    }


class TestSignatureParsingBaseline:
    """Baseline tests for signature parsing performance."""

    def test_simple_signature_parsing_baseline(self):
        """
        Baseline: Simple signature parsing should complete in <10ms.

        Target: <10ms per operation (well under 100ms p95 overall target)
        Current: ~0.13ms (66x faster than target)
        """
        parser = SignatureParser()
        signature_text = "question -> answer"

        perf = measure_performance(parser.parse, signature_text)

        assert perf["result"].is_valid
        assert perf["result"].inputs == ["question"]
        assert perf["result"].outputs == ["answer"]
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Simple parsing P95: {perf['p95']:.3f}ms (target: <10ms)")

    def test_complex_signature_parsing_baseline(self):
        """
        Baseline: Complex signature parsing should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.16ms (312x faster than target)
        """
        parser = SignatureParser()
        signature_text = "context, question, metadata -> reasoning, answer, confidence"

        perf = measure_performance(parser.parse, signature_text)

        assert perf["result"].is_valid
        assert len(perf["result"].inputs) == 3
        assert len(perf["result"].outputs) == 3
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Complex parsing P95: {perf['p95']:.3f}ms (target: <50ms)")

    def test_multimodal_signature_parsing_baseline(self):
        """
        Baseline: Multi-modal signature parsing should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.13ms (384x faster than target)
        """
        parser = SignatureParser()
        signature_text = "text, image -> analysis, visual_description"

        perf = measure_performance(parser.parse, signature_text)

        assert perf["result"].is_valid
        assert perf["result"].supports_multi_modal
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Multi-modal parsing P95: {perf['p95']:.3f}ms (target: <50ms)")

    def test_enterprise_signature_parsing_baseline(self):
        """
        Baseline: Enterprise signature parsing should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.12ms (416x faster than target)
        """
        parser = SignatureParser()
        signature_text = "customer_data -> privacy_checked_analysis, audit_trail"

        perf = measure_performance(parser.parse, signature_text)

        assert perf["result"].is_valid
        assert (
            perf["result"].requires_audit_trail or perf["result"].requires_privacy_check
        )
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Enterprise parsing P95: {perf['p95']:.3f}ms (target: <50ms)")


class TestSignatureCompilationBaseline:
    """Baseline tests for signature compilation performance."""

    def test_simple_signature_compilation_baseline(self):
        """
        Baseline: Simple signature compilation should complete in <10ms.

        Target: <10ms per operation
        Current: ~0.03ms (333x faster than target)
        """
        compiler = SignatureCompiler()
        signature = Signature(
            inputs=["question"], outputs=["answer"], signature_type="basic"
        )

        perf = measure_performance(compiler.compile_to_workflow_params, signature)

        assert "node_type" in perf["result"]
        assert "parameters" in perf["result"]
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Simple compilation P95: {perf['p95']:.3f}ms (target: <10ms)")

    def test_complex_signature_compilation_baseline(self):
        """
        Baseline: Complex signature compilation should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.03ms (1666x faster than target)
        """
        compiler = SignatureCompiler()
        signature = Signature(
            inputs=["context", "question", "metadata"],
            outputs=["reasoning", "answer", "confidence"],
            signature_type="complex",
        )

        perf = measure_performance(compiler.compile_to_workflow_params, signature)

        assert perf["result"]["parameters"]["inputs"] == [
            "context",
            "question",
            "metadata",
        ]
        assert len(perf["result"]["parameters"]["outputs"]) == 3
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Complex compilation P95: {perf['p95']:.3f}ms (target: <50ms)")

    def test_enterprise_signature_compilation_baseline(self):
        """
        Baseline: Enterprise signature compilation should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.03ms (1666x faster than target)
        """
        compiler = SignatureCompiler()
        signature = Signature(
            inputs=["customer_data"],
            outputs=["analysis", "audit_trail"],
            signature_type="enterprise",
            requires_privacy_check=True,
            requires_audit_trail=True,
        )

        perf = measure_performance(compiler.compile_to_workflow_params, signature)

        assert perf["result"]["parameters"].get("security_enabled") == True
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Enterprise compilation P95: {perf['p95']:.3f}ms (target: <50ms)")

    def test_multimodal_signature_compilation_baseline(self):
        """
        Baseline: Multi-modal signature compilation should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.04ms (1250x faster than target)
        """
        compiler = SignatureCompiler()
        signature = MultiModalSignature(
            inputs=["text", "image"],
            outputs=["analysis", "description"],
            signature_type="multi_modal",
            supports_multi_modal=True,
        )

        perf = measure_performance(compiler.compile_to_workflow_params, signature)

        assert perf["result"]["node_type"] == "MultiModalLLMNode"
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Multi-modal compilation P95: {perf['p95']:.3f}ms (target: <50ms)")


class TestSignatureValidationBaseline:
    """Baseline tests for signature validation performance."""

    def test_simple_signature_validation_baseline(self):
        """
        Baseline: Simple signature validation should complete in <10ms.

        Target: <10ms per operation
        Current: ~0.03ms (333x faster than target)
        """
        validator = SignatureValidator()
        signature = Signature(
            inputs=["question"], outputs=["answer"], signature_type="basic"
        )

        perf = measure_performance(validator.validate, signature)

        assert perf["result"].is_valid
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Simple validation P95: {perf['p95']:.3f}ms (target: <10ms)")

    def test_typed_signature_validation_baseline(self):
        """
        Baseline: Typed signature validation should complete in <10ms.

        Target: <10ms per operation
        Current: ~0.04ms (250x faster than target)
        """
        validator = SignatureValidator()
        signature = Signature(
            inputs=["question"],
            outputs=["answer"],
            signature_type="basic",
            input_types={"question": "text"},
            output_types={"answer": "text"},
        )

        perf = measure_performance(validator.validate, signature)

        assert perf["result"].is_valid
        assert perf["result"].has_type_checking
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Typed validation P95: {perf['p95']:.3f}ms (target: <10ms)")

    def test_multimodal_signature_validation_baseline(self):
        """
        Baseline: Multi-modal signature validation should complete in <10ms.

        Target: <10ms per operation
        Current: ~0.05ms (200x faster than target)
        """
        validator = SignatureValidator()
        signature = MultiModalSignature(
            inputs=["text", "image"],
            outputs=["analysis"],
            signature_type="multi_modal",
            supports_multi_modal=True,
            input_types={"text": "text", "image": "image"},
        )

        perf = measure_performance(validator.validate, signature)

        assert perf["result"].is_valid
        assert perf["result"].multi_modal_supported
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Multi-modal validation P95: {perf['p95']:.3f}ms (target: <10ms)")


class TestClassBasedSignatureBaseline:
    """Baseline tests for class-based signature creation performance."""

    def test_simple_class_signature_creation_baseline(self):
        """
        Baseline: Simple class-based signature creation should complete in <10ms.

        Target: <10ms per operation
        Current: ~0.04ms (250x faster than target)
        """

        def create_signature():
            class QASignature(Signature):
                question: str = InputField(desc="Question")
                answer: str = OutputField(desc="Answer")

            return QASignature()

        perf = measure_performance(create_signature)

        assert perf["result"].inputs == ["question"]
        assert perf["result"].outputs == ["answer"]
        assert perf["p95"] < 10, f"P95 latency {perf['p95']:.2f}ms exceeds 10ms target"
        print(f"  ✓ Simple class signature P95: {perf['p95']:.3f}ms (target: <10ms)")

    def test_complex_class_signature_creation_baseline(self):
        """
        Baseline: Complex class-based signature creation should complete in <50ms.

        Target: <50ms per operation
        Current: ~0.10ms (500x faster than target)
        """

        def create_signature():
            class ComplexSignature(Signature):
                context: str = InputField(desc="Context")
                question: str = InputField(desc="Question")
                metadata: str = InputField(desc="Metadata")
                reasoning: str = OutputField(desc="Reasoning")
                answer: str = OutputField(desc="Answer")
                confidence: float = OutputField(desc="Confidence")

            return ComplexSignature()

        perf = measure_performance(create_signature)

        assert len(perf["result"].inputs) == 3
        assert len(perf["result"].outputs) == 3
        assert perf["p95"] < 50, f"P95 latency {perf['p95']:.2f}ms exceeds 50ms target"
        print(f"  ✓ Complex class signature P95: {perf['p95']:.3f}ms (target: <50ms)")


class TestEndToEndResolutionBaseline:
    """Baseline tests for complete signature resolution pipeline."""

    def test_simple_end_to_end_resolution_baseline(self):
        """
        Baseline: Simple end-to-end resolution should complete in <100ms.

        Target: <100ms p95 (critical path)
        Current: ~0.17ms (588x faster than target)

        This is the CRITICAL PATH - complete signature resolution from
        text to compiled workflow parameters.
        """

        def resolve_signature(sig_text: str):
            parser = SignatureParser()
            compiler = SignatureCompiler()
            validator = SignatureValidator()

            # Parse
            parsed = parser.parse(sig_text)

            # Create signature
            sig = Signature(
                inputs=parsed.inputs,
                outputs=parsed.outputs,
                signature_type=parsed.signature_type,
            )

            # Validate
            validator.validate(sig)

            # Compile
            compiled = compiler.compile_to_workflow_params(sig)

            return compiled

        signature_text = "question -> answer"
        perf = measure_performance(resolve_signature, signature_text)

        assert "node_type" in perf["result"]
        assert "parameters" in perf["result"]
        assert (
            perf["p95"] < 100
        ), f"P95 latency {perf['p95']:.2f}ms exceeds 100ms target"
        print(f"  ✓ Simple end-to-end P95: {perf['p95']:.3f}ms (target: <100ms)")

    def test_complex_end_to_end_resolution_baseline(self):
        """
        Baseline: Complex end-to-end resolution should complete in <100ms.

        Target: <100ms p95
        Current: ~0.20ms (500x faster than target)
        """

        def resolve_signature(sig_text: str):
            parser = SignatureParser()
            compiler = SignatureCompiler()
            validator = SignatureValidator()

            parsed = parser.parse(sig_text)
            sig = Signature(
                inputs=parsed.inputs,
                outputs=parsed.outputs,
                signature_type=parsed.signature_type,
            )
            validator.validate(sig)
            compiled = compiler.compile_to_workflow_params(sig)

            return compiled

        signature_text = "context, question, metadata -> reasoning, answer, confidence"
        perf = measure_performance(resolve_signature, signature_text)

        assert len(perf["result"]["parameters"]["inputs"]) == 3
        assert len(perf["result"]["parameters"]["outputs"]) == 3
        assert (
            perf["p95"] < 100
        ), f"P95 latency {perf['p95']:.2f}ms exceeds 100ms target"
        print(f"  ✓ Complex end-to-end P95: {perf['p95']:.3f}ms (target: <100ms)")

    def test_multimodal_end_to_end_resolution_baseline(self):
        """
        Baseline: Multi-modal end-to-end resolution should complete in <100ms.

        Target: <100ms p95
        Current: ~0.17ms (588x faster than target)
        """

        def resolve_signature(sig_text: str):
            parser = SignatureParser()
            compiler = SignatureCompiler()
            validator = SignatureValidator()

            parsed = parser.parse(sig_text)
            sig = Signature(
                inputs=parsed.inputs,
                outputs=parsed.outputs,
                signature_type=parsed.signature_type,
                supports_multi_modal=parsed.supports_multi_modal,
                input_types=parsed.input_types,
            )
            validator.validate(sig)
            compiled = compiler.compile_to_workflow_params(sig)

            return compiled

        signature_text = "text, image -> analysis, visual_description"
        perf = measure_performance(resolve_signature, signature_text)

        assert perf["result"]["parameters"].get("supports_vision") == True
        assert (
            perf["p95"] < 100
        ), f"P95 latency {perf['p95']:.2f}ms exceeds 100ms target"
        print(f"  ✓ Multi-modal end-to-end P95: {perf['p95']:.3f}ms (target: <100ms)")


class TestRegressionDetection:
    """Regression detection tests with strict performance thresholds."""

    def test_parsing_performance_regression(self):
        """
        Regression test: Parsing must stay under 1ms (10x current baseline).

        Current: ~0.13ms
        Threshold: 1ms
        Alert: >0.5ms
        Fail: >1ms
        """
        parser = SignatureParser()
        signature_text = "context, question -> reasoning, answer, confidence"

        perf = measure_performance(parser.parse, signature_text, iterations=100)

        # Regression thresholds
        assert (
            perf["p95"] < 1.0
        ), f"REGRESSION: P95 latency {perf['p95']:.2f}ms exceeds 1ms threshold"
        if perf["p95"] > 0.5:
            print(
                f"  ⚠️  WARNING: P95 latency {perf['p95']:.2f}ms approaching 1ms threshold"
            )
        else:
            print(
                f"  ✓ Parsing regression check P95: {perf['p95']:.3f}ms (threshold: <1ms)"
            )

    def test_end_to_end_performance_regression(self):
        """
        Regression test: End-to-end resolution must stay under 2ms (10x current baseline).

        Current: ~0.17ms
        Threshold: 2ms
        Alert: >1ms
        Fail: >2ms
        """

        def resolve_signature(sig_text: str):
            parser = SignatureParser()
            compiler = SignatureCompiler()
            validator = SignatureValidator()

            parsed = parser.parse(sig_text)
            sig = Signature(
                inputs=parsed.inputs,
                outputs=parsed.outputs,
                signature_type=parsed.signature_type,
            )
            validator.validate(sig)
            compiled = compiler.compile_to_workflow_params(sig)

            return compiled

        signature_text = "context, question, metadata -> reasoning, answer, confidence"
        perf = measure_performance(resolve_signature, signature_text, iterations=100)

        # Regression thresholds
        assert (
            perf["p95"] < 2.0
        ), f"REGRESSION: P95 latency {perf['p95']:.2f}ms exceeds 2ms threshold"
        if perf["p95"] > 1.0:
            print(
                f"  ⚠️  WARNING: P95 latency {perf['p95']:.2f}ms approaching 2ms threshold"
            )
        else:
            print(
                f"  ✓ End-to-end regression check P95: {perf['p95']:.3f}ms (threshold: <2ms)"
            )


# Performance baseline summary (for reference):
#
# Parsing:
# - Simple: ~0.13ms (target: <10ms) ✅
# - Complex: ~0.16ms (target: <50ms) ✅
# - Multi-modal: ~0.13ms (target: <50ms) ✅
# - Enterprise: ~0.12ms (target: <50ms) ✅
#
# Compilation:
# - Simple: ~0.03ms (target: <10ms) ✅
# - Complex: ~0.03ms (target: <50ms) ✅
# - Enterprise: ~0.03ms (target: <50ms) ✅
# - Multi-modal: ~0.04ms (target: <50ms) ✅
#
# Validation:
# - Simple: ~0.03ms (target: <10ms) ✅
# - Typed: ~0.04ms (target: <10ms) ✅
# - Multi-modal: ~0.05ms (target: <10ms) ✅
#
# End-to-End (CRITICAL PATH):
# - Simple: ~0.17ms (target: <100ms) ✅
# - Complex: ~0.20ms (target: <100ms) ✅
# - Multi-modal: ~0.17ms (target: <100ms) ✅
#
# Regression Thresholds:
# - Parsing: <1ms (10x baseline)
# - End-to-end: <2ms (10x baseline)
