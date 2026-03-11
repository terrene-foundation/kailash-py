"""
Document Understanding Workflow - Complete Multi-Modal Pipeline

Demonstrates:
1. Image (document scan) → OCR
2. Extracted text → Analysis
3. Analysis → Summary
4. Cost tracking and provider selection

This is the complete multi-modal workflow for Phase 4.
"""

from dataclasses import dataclass
from pathlib import Path

from kaizen.agents.multi_modal.multi_modal_agent import (
    MultiModalAgent,
    MultiModalConfig,
)
from kaizen.cost.tracker import CostTracker
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField
from kaizen.signatures.multi_modal import ImageField, MultiModalSignature


# Step 1: OCR Signature
class DocumentOCRSignature(MultiModalSignature):
    """Extract text from document image."""

    image: ImageField = InputField(
        description="Document image to extract text from", max_size_mb=2.0
    )
    extracted_text: str = OutputField(description="Extracted text from document")
    confidence: float = OutputField(description="OCR confidence score")


# Step 2: Analysis Signature
class DocumentAnalysisSignature(MultiModalSignature):
    """Analyze extracted document text."""

    text: str = InputField(description="Extracted text to analyze")
    document_type: str = OutputField(description="Type of document")
    key_information: str = OutputField(description="Key information extracted")
    entities: str = OutputField(description="Named entities found")


# Step 3: Summary Signature
class DocumentSummarySignature(MultiModalSignature):
    """Summarize document analysis."""

    analysis: str = InputField(description="Document analysis to summarize")
    summary: str = OutputField(description="Brief summary")
    action_items: str = OutputField(description="Action items if any")


@dataclass
class DocumentUnderstandingConfig:
    """Configuration for document understanding workflow."""

    llm_provider: str = "ollama"  # Use Ollama by default (free)
    vision_model: str = "llava:13b"
    budget_limit: float = 5.0  # Safety limit
    enable_cost_tracking: bool = True
    store_in_memory: bool = True


class DocumentUnderstandingWorkflow:
    """
    Complete document understanding workflow.

    Pipeline:
    1. Document Image → OCR (vision processing)
    2. Extracted Text → Analysis (text processing)
    3. Analysis → Summary (text processing)
    """

    def __init__(self, config: DocumentUnderstandingConfig):
        """Initialize workflow with configuration."""
        self.config = config

        # Shared resources
        self.memory_pool = SharedMemoryPool()
        self.cost_tracker = CostTracker(
            budget_limit=config.budget_limit,
            warn_on_openai_usage=True,
            enable_cost_tracking=config.enable_cost_tracking,
        )

        # Step 1: OCR Agent
        ocr_config = MultiModalConfig(
            llm_provider=config.llm_provider,
            model=config.vision_model,
            prefer_local=True,
            enable_cost_tracking=config.enable_cost_tracking,
            budget_limit=config.budget_limit,
        )

        self.ocr_agent = MultiModalAgent(
            config=ocr_config,
            signature=DocumentOCRSignature(),
            cost_tracker=self.cost_tracker,
            shared_memory=self.memory_pool,
            agent_id="ocr_agent",
        )

        # Step 2: Analysis Agent
        analysis_config = MultiModalConfig(
            llm_provider=config.llm_provider,
            model="llama2" if config.llm_provider == "ollama" else "gpt-3.5-turbo",
            enable_cost_tracking=config.enable_cost_tracking,
        )

        self.analysis_agent = MultiModalAgent(
            config=analysis_config,
            signature=DocumentAnalysisSignature(),
            cost_tracker=self.cost_tracker,
            shared_memory=self.memory_pool,
            agent_id="analysis_agent",
        )

        # Step 3: Summary Agent
        summary_config = MultiModalConfig(
            llm_provider=config.llm_provider,
            model="llama2" if config.llm_provider == "ollama" else "gpt-3.5-turbo",
            enable_cost_tracking=config.enable_cost_tracking,
        )

        self.summary_agent = MultiModalAgent(
            config=summary_config,
            signature=DocumentSummarySignature(),
            cost_tracker=self.cost_tracker,
            shared_memory=self.memory_pool,
            agent_id="summary_agent",
        )

    def process_document(self, image_path: str, store_in_memory: bool = None) -> dict:
        """
        Process document through complete pipeline.

        Args:
            image_path: Path to document image
            store_in_memory: Store results in memory (default: from config)

        Returns:
            Dict with OCR, analysis, and summary results
        """
        store = (
            store_in_memory
            if store_in_memory is not None
            else self.config.store_in_memory
        )

        print(f"📄 Processing document: {Path(image_path).name}")
        print(
            f"💰 Provider: {self.config.llm_provider} (Cost tracking: {self.config.enable_cost_tracking})"
        )

        # Step 1: OCR
        print("\n🔍 Step 1: Extracting text (OCR)...")
        ocr_result = self.ocr_agent.analyze(image=image_path, store_in_memory=store)
        extracted_text = ocr_result.get("extracted_text", "")
        print(f"   ✓ Extracted {len(extracted_text)} characters")

        # Step 2: Analysis
        print("\n📊 Step 2: Analyzing document...")
        analysis_result = self.analysis_agent.analyze(
            text=extracted_text, store_in_memory=store
        )
        print(f"   ✓ Document type: {analysis_result.get('document_type', 'Unknown')}")

        # Step 3: Summary
        print("\n📝 Step 3: Generating summary...")
        analysis_text = (
            f"Type: {analysis_result.get('document_type', '')}\n"
            f"Key Info: {analysis_result.get('key_information', '')}\n"
            f"Entities: {analysis_result.get('entities', '')}"
        )
        summary_result = self.summary_agent.analyze(
            analysis=analysis_text, store_in_memory=store
        )
        print(f"   ✓ Summary: {summary_result.get('summary', '')[:100]}...")

        # Cost summary
        if self.config.enable_cost_tracking:
            cost_summary = self.cost_tracker.get_usage_stats()
            print("\n💵 Cost Summary:")
            print(f"   Total calls: {cost_summary['total_calls']}")
            print(f"   Ollama calls: {cost_summary['ollama_calls']} (FREE)")
            print(f"   OpenAI calls: {cost_summary['openai_calls']}")
            print(f"   Total cost: ${cost_summary['total_cost']:.3f}")

            if cost_summary["ollama_calls"] > 0:
                equivalent = self.cost_tracker.estimate_openai_equivalent_cost()
                print(f"   💡 OpenAI equivalent would cost: ${equivalent:.3f}")
                print(f"   💰 Savings: ${equivalent - cost_summary['total_cost']:.3f}")

        return {
            "ocr": ocr_result,
            "analysis": analysis_result,
            "summary": summary_result,
            "cost": cost_summary if self.config.enable_cost_tracking else None,
        }

    def batch_process_documents(
        self, image_paths: list, store_in_memory: bool = None
    ) -> list:
        """
        Process multiple documents in batch.

        Args:
            image_paths: List of document image paths
            store_in_memory: Store results in memory

        Returns:
            List of processing results
        """
        results = []

        print(f"\n📚 Batch processing {len(image_paths)} documents...")

        for i, image_path in enumerate(image_paths, 1):
            print(f"\n--- Document {i}/{len(image_paths)} ---")
            result = self.process_document(image_path, store_in_memory)
            results.append(result)

        # Overall cost summary
        if self.config.enable_cost_tracking:
            print("\n" + "=" * 60)
            print("📊 BATCH COST SUMMARY")
            print("=" * 60)
            cost_summary = self.cost_tracker.get_usage_stats()
            print(f"Total documents processed: {len(image_paths)}")
            print(f"Total API calls: {cost_summary['total_calls']}")
            print(f"Total cost: ${cost_summary['total_cost']:.3f}")

            equivalent = self.cost_tracker.estimate_openai_equivalent_cost()
            savings = equivalent - cost_summary["total_cost"]
            print(f"OpenAI equivalent cost: ${equivalent:.3f}")
            print(f"Total savings: ${savings:.3f} ({(savings/equivalent*100):.0f}%)")

        return results

    def get_memory_insights(self, limit: int = 10) -> list:
        """Get insights from shared memory."""
        memories = self.memory_pool.retrieve(limit=limit)
        return [
            {
                "agent_id": m.agent_id,
                "content": m.content,
                "tags": m.tags,
                "importance": m.importance,
                "timestamp": m.timestamp,
            }
            for m in memories
        ]


def main():
    """Example usage of document understanding workflow."""
    import tempfile

    from PIL import Image, ImageDraw

    # Create a sample invoice image
    print("🎨 Creating sample invoice image...")
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Add invoice content
    invoice_text = """
    INVOICE #INV-2025-001

    Date: January 15, 2025
    Due Date: February 15, 2025

    Bill To:
    Acme Corporation
    123 Business St
    San Francisco, CA 94105

    Items:
    - Software License (Annual)     $5,000.00
    - Support Services              $1,500.00
    - Training Sessions             $2,000.00

    Subtotal:                        $8,500.00
    Tax (8.5%):                        $722.50
    -------------------------------------------
    TOTAL:                           $9,222.50

    Payment Terms: Net 30
    """

    y_position = 50
    for line in invoice_text.strip().split("\n"):
        draw.text((50, y_position), line.strip(), fill="black")
        y_position += 20

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        img.save(tmp.name)
        invoice_path = tmp.name

    print(f"   ✓ Sample invoice created: {invoice_path}")

    # Create workflow with Ollama (free)
    print("\n🚀 Initializing document understanding workflow...")
    config = DocumentUnderstandingConfig(
        llm_provider="ollama",
        vision_model="llava:13b",
        budget_limit=5.0,
        enable_cost_tracking=True,
        store_in_memory=True,
    )

    workflow = DocumentUnderstandingWorkflow(config)

    # Process single document
    print("\n" + "=" * 60)
    print("SINGLE DOCUMENT PROCESSING")
    print("=" * 60)

    result = workflow.process_document(invoice_path)

    print("\n" + "=" * 60)
    print("📋 FINAL RESULTS")
    print("=" * 60)
    print(f"\n📝 Summary: {result['summary'].get('summary', 'N/A')}")
    print(f"✅ Action Items: {result['summary'].get('action_items', 'N/A')}")

    # Get memory insights
    print("\n" + "=" * 60)
    print("🧠 MEMORY INSIGHTS")
    print("=" * 60)
    insights = workflow.get_memory_insights(limit=5)
    for i, insight in enumerate(insights, 1):
        print(f"\n{i}. Agent: {insight['agent_id']}")
        print(f"   Tags: {insight['tags']}")
        print(f"   Importance: {insight['importance']}")

    print("\n✨ Document understanding workflow complete!")


if __name__ == "__main__":
    main()
