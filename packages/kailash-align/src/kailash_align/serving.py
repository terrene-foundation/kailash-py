# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AlignmentServing: GGUF export, Ollama deployment, vLLM config generation.

Handles the serving pipeline from trained adapter to deployed model.
Uses llama-cpp-python for GGUF operations (R2-01) -- no compiled binary needed.
llama-cpp-python and gguf are [serve] optional extras.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from kailash_align.config import ServingConfig
from kailash_align.exceptions import (
    GGUFConversionError,
    OllamaNotAvailableError,
    ServingError,
)

logger = logging.getLogger(__name__)

__all__ = ["AlignmentServing"]

# Supported architectures with known-good GGUF conversion (R1-02, R2 Section 3.1)
SUPPORTED_ARCHITECTURES = {
    "LlamaForCausalLM": "fully_supported",
    "MistralForCausalLM": "fully_supported",
    "Phi3ForCausalLM": "supported",
    "Qwen2ForCausalLM": "supported",
}

QUANTIZATION_TYPES = {
    "f16": None,
    "q4_k_m": "q4_k_m",
    "q8_0": "q8_0",
}


class AlignmentServing:
    """Handles GGUF export, Ollama deployment, and vLLM config generation.

    Requires [serve] extra: pip install kailash-align[serve]
    The [serve] extra provides llama-cpp-python (quantization + validation)
    and gguf (HF-to-GGUF conversion).

    Args:
        adapter_registry: AdapterRegistry for tracking GGUF paths.
        config: ServingConfig with deployment parameters.
    """

    def __init__(
        self, adapter_registry: Any = None, config: Optional[ServingConfig] = None
    ) -> None:
        self._registry = adapter_registry
        self._config = config or ServingConfig()

    async def deploy(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        model_name: Optional[str] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Unified deployment dispatch.

        For Ollama: export GGUF -> deploy to Ollama -> verify.
        For vLLM: generate config file + launch script.

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            model_name: Name for the deployed model. Defaults to adapter_name.
            **kwargs: Passed to target-specific method.

        Returns:
            dict with deployment details.
        """
        model_name = model_name or adapter_name
        if self._config.target == "ollama":
            return await self.deploy_ollama(adapter_name, version, model_name, **kwargs)
        elif self._config.target == "vllm":
            return await self.generate_vllm_config(adapter_name, version, **kwargs)
        else:
            raise ServingError(f"Unknown deployment target: {self._config.target}")

    async def export_gguf(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        output_dir: Optional[str] = None,
        quantization: Optional[str] = None,
    ) -> Path:
        """Export adapter to GGUF format.

        Steps:
        1. Ensure adapter is merged (raise if not)
        2. Check model architecture against supported list
        3. Convert HF model to F16 GGUF
        4. Quantize to target format via llama-cpp-python
        5. Validate GGUF: load and run single-prompt inference (R1-02)
        6. Update AdapterRegistry with gguf_path

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            output_dir: Directory for GGUF files. Defaults to merged_path/../gguf/.
            quantization: Override config quantization. Default: config.quantization.

        Returns:
            Path to the final GGUF file.

        Raises:
            ImportError: If [serve] extra not installed.
            GGUFConversionError: If conversion or validation fails.
        """
        self._check_serve_deps()
        quantization = quantization or self._config.quantization

        # Get adapter from registry
        adapter_version = await self._get_adapter_version(adapter_name, version)

        # Ensure merged
        if adapter_version.merge_status == "separate":
            raise ServingError(
                f"Adapter {adapter_name} v{adapter_version.version} is not merged. "
                f"Run adapter merge (ALN-302) first, or use deploy() which handles "
                f"this automatically."
            )
        merged_path = Path(adapter_version.merged_model_path)

        # Check architecture
        self._check_architecture(merged_path)

        # Convert to F16 GGUF
        gguf_output_dir = Path(output_dir or merged_path.parent / "gguf")
        gguf_output_dir.mkdir(parents=True, exist_ok=True)
        f16_path = gguf_output_dir / f"{adapter_name}-f16.gguf"

        logger.info("Converting %s to F16 GGUF...", merged_path)
        self._convert_hf_to_gguf(merged_path, f16_path)

        # Quantize (if not F16)
        if quantization == "f16":
            final_path = f16_path
        else:
            final_path = gguf_output_dir / f"{adapter_name}-{quantization}.gguf"
            logger.info("Quantizing to %s...", quantization)
            self._quantize_gguf(f16_path, final_path, quantization)

        # Validate (R1-02 MANDATORY)
        if self._config.validate_gguf:
            logger.info("Validating GGUF output...")
            self._validate_gguf(final_path)

        # Update registry
        if self._registry is not None:
            await self._registry.update_gguf_path(
                adapter_name,
                adapter_version.version,
                str(final_path),
                quantization_config={"method": quantization},
            )

        logger.info("GGUF export complete: %s", final_path)
        return final_path

    async def deploy_ollama(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        model_name: Optional[str] = None,
        gguf_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Deploy model to Ollama.

        Normal path: export GGUF -> write Modelfile -> ollama create -> verify.
        BYOG path: gguf_path provided -> skip conversion -> write Modelfile -> deploy.

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            model_name: Name for the Ollama model. Defaults to adapter_name.
            gguf_path: 'Bring your own GGUF' path (R1-02). Skips conversion.

        Returns:
            dict with model_name, ollama_host, status.

        Raises:
            OllamaNotAvailableError: If Ollama CLI not found or not running.
            GGUFConversionError: If GGUF conversion fails.
        """
        self._check_ollama_available()
        model_name = model_name or adapter_name

        # BYOG escape hatch (R1-02)
        if gguf_path is not None:
            gguf_file = Path(gguf_path)
            if not gguf_file.exists():
                raise ServingError(f"GGUF file not found: {gguf_path}")
            logger.info("Using provided GGUF file: %s", gguf_path)
        else:
            gguf_file = await self.export_gguf(adapter_name, version)

        # Write Modelfile
        modelfile_path = gguf_file.parent / "Modelfile"
        self._write_modelfile(modelfile_path, gguf_file)

        # Create Ollama model
        self._ollama_create(model_name, modelfile_path)

        # Verify
        self._ollama_verify(model_name)

        return {
            "model_name": model_name,
            "ollama_host": self._config.ollama_host,
            "gguf_path": str(gguf_file),
            "status": "deployed",
        }

    async def generate_vllm_config(
        self,
        adapter_name: str,
        version: Optional[str] = None,
        output_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate vLLM serving configuration.

        Produces a JSON config file and a launch script. Does NOT start vLLM.
        vLLM uses the HuggingFace model directly (no GGUF needed).
        vLLM is CUDA-only in practice (R2-03).

        Args:
            adapter_name: Name of adapter in registry.
            version: Specific version (None = latest).
            output_path: Output directory. Defaults to merged_path/../vllm/.

        Returns:
            dict with config_path, launch_script_path, config contents.
        """
        adapter_version = await self._get_adapter_version(adapter_name, version)

        if adapter_version.merge_status == "separate":
            raise ServingError(
                f"Adapter {adapter_name} v{adapter_version.version} is not merged. "
                f"Merge the adapter first for vLLM deployment."
            )

        model_path = adapter_version.merged_model_path
        output_dir = Path(output_path or Path(model_path).parent / "vllm")
        output_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "model": model_path,
            "dtype": "bfloat16",
            "tensor-parallel-size": 1,
            "max-model-len": 4096,
            "gpu-memory-utilization": 0.9,
            "host": "0.0.0.0",
            "port": 8000,
        }

        config_path = output_dir / "vllm-config.json"
        config_path.write_text(json.dumps(config, indent=2))

        launch_script = output_dir / "launch_vllm.sh"
        launch_script.write_text(
            "#!/bin/bash\n"
            f"# Generated by kailash-align for adapter: {adapter_name}\n"
            f"# NOTE: vLLM requires CUDA. Not recommended for Apple Silicon (R2-03).\n"
            f"python -m vllm.entrypoints.openai.api_server \\\n"
            f"  --config {config_path}\n"
        )
        launch_script.chmod(0o755)

        logger.info("vLLM config generated: %s", config_path)
        return {
            "config_path": str(config_path),
            "launch_script_path": str(launch_script),
            "config": config,
        }

    # --- Internal methods ---

    def _check_serve_deps(self) -> None:
        """Check that [serve] extra dependencies are installed."""
        try:
            import llama_cpp  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "GGUF export requires llama-cpp-python and gguf. "
                "Install with: pip install kailash-align[serve]"
            ) from exc

    def _check_ollama_available(self) -> None:
        """Check that Ollama CLI is installed and the server is running."""
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise OllamaNotAvailableError(
                    f"Ollama CLI returned error: {result.stderr.strip()}"
                )
        except FileNotFoundError:
            raise OllamaNotAvailableError(
                "Ollama CLI not found. Install from https://ollama.ai"
            )
        except subprocess.TimeoutExpired:
            raise OllamaNotAvailableError(
                "Ollama server not responding. Start with: ollama serve"
            )

    def _check_architecture(self, model_path: Path) -> None:
        """Check if model architecture is in the supported list (R1-02)."""
        from transformers import AutoConfig

        config = AutoConfig.from_pretrained(str(model_path))
        architectures = config.architectures if config.architectures else []
        arch = architectures[0] if architectures else "unknown"

        if arch not in SUPPORTED_ARCHITECTURES:
            logger.warning(
                "Model architecture '%s' is not in the tested list: %s. "
                "GGUF conversion may fail or produce incorrect results. "
                "Consider using the 'bring your own GGUF' option instead.",
                arch,
                list(SUPPORTED_ARCHITECTURES.keys()),
            )
        else:
            support_level = SUPPORTED_ARCHITECTURES[arch]
            logger.info("Architecture %s: %s", arch, support_level)

    def _convert_hf_to_gguf(self, model_path: Path, output_path: Path) -> None:
        """Convert HuggingFace model to F16 GGUF using llama-cpp-python (R2-01)."""
        import sys

        import llama_cpp

        convert_script = (
            Path(llama_cpp.__file__).parent
            / "vendor"
            / "llama.cpp"
            / "convert_hf_to_gguf.py"
        )
        if not convert_script.exists():
            convert_script = None

        if convert_script:
            result = subprocess.run(
                [
                    sys.executable,
                    str(convert_script),
                    str(model_path),
                    "--outfile",
                    str(output_path),
                    "--outtype",
                    "f16",
                ],
                capture_output=True,
                text=True,
                timeout=3600,
            )
        else:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "gguf",
                    str(model_path),
                    "--outfile",
                    str(output_path),
                    "--outtype",
                    "f16",
                ],
                capture_output=True,
                text=True,
                timeout=3600,
            )
        if result.returncode != 0:
            raise GGUFConversionError(
                f"HF-to-GGUF conversion failed.\n"
                f"Model: {model_path}\n"
                f"Error: {result.stderr.strip()}\n"
                f"If this model architecture is not supported, use the "
                f"'bring your own GGUF' option: deploy_ollama(gguf_path=...)"
            )

    def _quantize_gguf(
        self, input_path: Path, output_path: Path, quant_type: str
    ) -> None:
        """Quantize GGUF file using llama-cpp-python (R2-01)."""
        import llama_cpp

        ftype_map = {
            "q4_k_m": getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q4_K_M", 15),
            "q8_0": getattr(llama_cpp, "LLAMA_FTYPE_MOSTLY_Q8_0", 7),
        }
        if quant_type not in ftype_map:
            raise GGUFConversionError(f"Unsupported quantization type: {quant_type}")

        params = llama_cpp.llama_model_quantize_default_params()
        params.nthread = 4
        params.ftype = ftype_map[quant_type]

        ret = llama_cpp.llama_model_quantize(
            str(input_path).encode(), str(output_path).encode(), params
        )
        if ret != 0:
            raise GGUFConversionError(
                f"Quantization to {quant_type} failed with return code {ret}"
            )

    def _validate_gguf(self, gguf_path: Path) -> None:
        """Post-conversion validation: load GGUF and run single-prompt inference (R1-02).

        Verifies:
        1. GGUF file can be loaded without crash
        2. Model generates at least one token
        3. Output is not garbage (non-empty, contains printable characters)
        """
        import llama_cpp

        logger.info("Loading GGUF for validation: %s", gguf_path)
        start = time.monotonic()

        try:
            model = llama_cpp.Llama(
                model_path=str(gguf_path),
                n_ctx=256,
                n_batch=1,
                verbose=False,
            )
        except Exception as exc:
            raise GGUFConversionError(
                f"Failed to load GGUF file: {exc}\n"
                f"The GGUF file may be corrupted. "
                f"Try re-exporting or use the 'bring your own GGUF' option."
            ) from exc

        try:
            output = model.create_completion(
                "Hello, ",
                max_tokens=10,
                temperature=0.0,
            )
            text = output["choices"][0]["text"]
            if not text or not text.strip():
                raise GGUFConversionError(
                    "GGUF validation failed: model produced empty output. "
                    "The conversion may have produced a malformed file. "
                    "Try a different quantization method or use 'bring your own GGUF'."
                )
            printable_ratio = sum(1 for c in text if c.isprintable()) / len(text)
            if printable_ratio < 0.5:
                logger.warning(
                    "GGUF validation warning: output is %.0f%% non-printable characters. "
                    "Output: %r. The model may not be functioning correctly.",
                    (1 - printable_ratio) * 100,
                    text[:50],
                )
        except GGUFConversionError:
            raise
        except Exception as exc:
            raise GGUFConversionError(
                f"GGUF validation inference failed: {exc}"
            ) from exc
        finally:
            del model

        duration = time.monotonic() - start
        logger.info("GGUF validation passed in %.1fs", duration)

    def _write_modelfile(self, path: Path, gguf_path: Path) -> None:
        """Write Ollama Modelfile."""
        lines = [f"FROM {gguf_path}"]
        if self._config.system_prompt:
            lines.append(f'SYSTEM """{self._config.system_prompt}"""')
        lines.append("")  # Trailing newline
        path.write_text("\n".join(lines))
        logger.info("Modelfile written to %s", path)

    def _ollama_create(self, model_name: str, modelfile_path: Path) -> None:
        """Run ollama create to register the model."""
        # H-NEW-03: validate model_name before passing to subprocess
        import re

        if not re.match(r"^[a-zA-Z0-9_:.-]+$", model_name):
            raise ServingError(
                f"Invalid model name '{model_name}': must contain only "
                f"alphanumeric characters, underscores, dots, colons, and hyphens"
            )
        result = subprocess.run(
            ["ollama", "create", model_name, "-f", str(modelfile_path)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise ServingError(f"ollama create failed: {result.stderr.strip()}")
        logger.info("Ollama model '%s' created", model_name)

    def _ollama_verify(self, model_name: str) -> None:
        """Verify model is registered in Ollama."""
        result = subprocess.run(
            ["ollama", "show", model_name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise ServingError(
                f"Ollama model verification failed for '{model_name}': "
                f"{result.stderr.strip()}"
            )
        logger.info("Ollama model '%s' verified", model_name)

    async def _get_adapter_version(
        self, adapter_name: str, version: Optional[str]
    ) -> Any:
        """Get adapter version from registry."""
        if self._registry is None:
            raise ServingError("AdapterRegistry is required for serving operations")
        return await self._registry.get_adapter(adapter_name, version)
