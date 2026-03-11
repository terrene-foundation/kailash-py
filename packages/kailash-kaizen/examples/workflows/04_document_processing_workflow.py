"""
Production-Ready Document Processing Workflow

Real-world use case: Extract text from documents, analyze content, generate insights
This agent autonomously processes documents, extracts entities, summarizes content, and generates reports.
"""

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()

from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import InputField, OutputField, Signature


class DocumentProcessingSignature(Signature):
    document_path: str = InputField(description="Path to document")
    analysis: dict = OutputField(description="Document analysis results")
    entities: List[dict] = OutputField(description="Extracted entities")
    summary: str = OutputField(description="Document summary")


@dataclass
class DocumentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.2
    max_doc_size: int = 1_000_000
    chunk_size: int = 4000


class DocumentProcessor(BaseAgent):
    """Production document processing agent with NLP capabilities."""

    def __init__(self, config: DocumentConfig):
        super().__init__(
            config=config,
            signature=DocumentProcessingSignature(),
        )
        self.max_size = config.max_doc_size
        self.chunk_size = config.chunk_size

    async def read_document(self, path: str) -> Dict:
        """Read and validate document."""

        exists_result = await self.execute_tool("file_exists", {"path": path})

        if not exists_result.success or not exists_result.result.get("exists"):
            return {"status": "error", "error": f"Document not found: {path}"}

        read_result = await self.execute_tool("read_file", {"path": path})

        if not read_result.success:
            return {"status": "error", "error": read_result.error}

        content = read_result.result.get("content", "")

        if len(content) > self.max_size:
            return {
                "status": "error",
                "error": f"Document too large: {len(content)} bytes (max: {self.max_size})",
            }

        return {
            "status": "success",
            "content": content,
            "size": len(content),
            "path": path,
        }

    def extract_entities(self, text: str) -> Dict:
        """Extract named entities from text."""

        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        url_pattern = r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)"
        phone_pattern = (
            r"\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b"
        )
        date_pattern = r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b"

        return {
            "emails": list(set(re.findall(email_pattern, text))),
            "urls": list(set(re.findall(url_pattern, text))),
            "phones": list(set(re.findall(phone_pattern, text))),
            "dates": list(set(re.findall(date_pattern, text))),
        }

    def analyze_content(self, text: str) -> Dict:
        """Analyze document content structure."""

        lines = text.split("\n")
        words = text.split()
        sentences = re.split(r"[.!?]+", text)

        word_freq = {}
        for word in words:
            cleaned = re.sub(r"[^\w]", "", word.lower())
            if len(cleaned) > 3:
                word_freq[cleaned] = word_freq.get(cleaned, 0) + 1

        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "line_count": len(lines),
            "word_count": len(words),
            "sentence_count": len([s for s in sentences if s.strip()]),
            "char_count": len(text),
            "avg_word_length": sum(len(w) for w in words) / len(words) if words else 0,
            "avg_sentence_length": len(words) / len(sentences) if sentences else 0,
            "top_words": [{"word": w, "count": c} for w, c in top_words],
            "blank_lines": len([l for l in lines if not l.strip()]),
        }

    def generate_summary(self, text: str, max_length: int = 500) -> str:
        """Generate extractive summary."""

        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return "No content to summarize."

        if len(sentences) <= 3:
            return ". ".join(sentences) + "."

        sentence_scores = {}
        for i, sentence in enumerate(sentences):
            words = sentence.lower().split()
            score = len(words)
            if i == 0:
                score *= 1.5
            if i < 3:
                score *= 1.2

            sentence_scores[i] = score

        top_sentences = sorted(
            sentence_scores.items(), key=lambda x: x[1], reverse=True
        )[:3]
        top_sentences = sorted(top_sentences, key=lambda x: x[0])

        summary = ". ".join([sentences[i] for i, _ in top_sentences]) + "."

        if len(summary) > max_length:
            summary = summary[:max_length] + "..."

        return summary

    async def process_document(self, path: str, output_dir: str) -> Dict:
        """Complete document processing pipeline."""

        results = {"document": path, "status": "processing"}

        doc_result = await self.read_document(path)

        if doc_result["status"] == "error":
            results["status"] = "error"
            results["error"] = doc_result["error"]
            return results

        content = doc_result["content"]
        results["size"] = doc_result["size"]

        results["entities"] = self.extract_entities(content)
        results["analysis"] = self.analyze_content(content)
        results["summary"] = self.generate_summary(content)

        report = self._generate_report(path, results)

        doc_name = Path(path).stem
        report_path = os.path.join(output_dir, f"{doc_name}_analysis.txt")

        write_result = await self.execute_tool(
            "write_file", {"path": report_path, "content": report}
        )

        if write_result.success:
            results["report_path"] = report_path
            results["status"] = "success"
        else:
            results["status"] = "partial"
            results["write_error"] = write_result.error

        return results

    async def batch_process(
        self, input_dir: str, output_dir: str, file_pattern: str = "*.txt"
    ) -> Dict:
        """Process multiple documents in batch."""

        results = {
            "processed": [],
            "failed": [],
            "stats": {"total": 0, "success": 0, "failed": 0},
        }

        list_result = await self.execute_tool("list_directory", {"path": input_dir})

        if not list_result.success:
            return {"error": f"Cannot access directory: {list_result.error}"}

        files = list_result.result.get("files", [])
        extension = file_pattern.replace("*", "")

        target_files = [f for f in files if f.endswith(extension)]

        results["stats"]["total"] = len(target_files)

        os.makedirs(output_dir, exist_ok=True)

        for file_name in target_files:
            file_path = os.path.join(input_dir, file_name)

            try:
                doc_result = await self.process_document(file_path, output_dir)

                if doc_result["status"] in ["success", "partial"]:
                    results["processed"].append(
                        {
                            "file": file_name,
                            "size": doc_result.get("size"),
                            "report": doc_result.get("report_path"),
                            "word_count": doc_result.get("analysis", {}).get(
                                "word_count"
                            ),
                        }
                    )
                    results["stats"]["success"] += 1
                else:
                    results["failed"].append(
                        {"file": file_name, "error": doc_result.get("error")}
                    )
                    results["stats"]["failed"] += 1

            except Exception as e:
                results["failed"].append({"file": file_name, "error": str(e)})
                results["stats"]["failed"] += 1

        return results

    def _generate_report(self, path: str, results: Dict) -> str:
        """Generate document analysis report."""

        analysis = results.get("analysis", {})
        entities = results.get("entities", {})

        report_lines = [
            "=" * 80,
            "DOCUMENT ANALYSIS REPORT",
            "=" * 80,
            f"Document: {path}",
            f"Size: {results.get('size', 0)} bytes",
            "",
            "=" * 80,
            "CONTENT STATISTICS",
            "=" * 80,
            f"Words: {analysis.get('word_count', 0)}",
            f"Lines: {analysis.get('line_count', 0)}",
            f"Sentences: {analysis.get('sentence_count', 0)}",
            f"Characters: {analysis.get('char_count', 0)}",
            f"Average Word Length: {analysis.get('avg_word_length', 0):.2f}",
            f"Average Sentence Length: {analysis.get('avg_sentence_length', 0):.2f}",
            "",
            "=" * 80,
            "TOP WORDS",
            "=" * 80,
        ]

        for word_data in analysis.get("top_words", [])[:10]:
            report_lines.append(f"  {word_data['word']}: {word_data['count']}")

        report_lines.extend(
            [
                "",
                "=" * 80,
                "EXTRACTED ENTITIES",
                "=" * 80,
                f"Emails: {len(entities.get('emails', []))}",
                f"URLs: {len(entities.get('urls', []))}",
                f"Phone Numbers: {len(entities.get('phones', []))}",
                f"Dates: {len(entities.get('dates', []))}",
            ]
        )

        if entities.get("emails"):
            report_lines.append("\nEmails:")
            for email in entities["emails"][:5]:
                report_lines.append(f"  - {email}")

        if entities.get("urls"):
            report_lines.append("\nURLs:")
            for url in entities["urls"][:5]:
                report_lines.append(f"  - {url}")

        report_lines.extend(
            [
                "",
                "=" * 80,
                "SUMMARY",
                "=" * 80,
                results.get("summary", "No summary available"),
                "",
                "=" * 80,
            ]
        )

        return "\n".join(report_lines)


async def main():
    """Production document processing workflow."""

    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY required")
        return

    config = DocumentConfig()
    processor = DocumentProcessor(config)

    input_dir = os.getenv("INPUT_DIR", "/tmp/documents")
    output_dir = os.getenv("OUTPUT_DIR", "/tmp/document_analysis")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    sample_docs = {
        "sample1.txt": """This is a sample document for testing.
Contact us at support@example.com or visit https://example.com.
Call 555-123-4567 for more information.
Meeting scheduled for 2025-10-21.""",
        "sample2.txt": """Production deployment guide.
Important: Backup data before proceeding.
For assistance, email devops@company.com.
""",
    }

    for filename, content in sample_docs.items():
        with open(os.path.join(input_dir, filename), "w") as f:
            f.write(content)

    print(f"Processing documents from {input_dir}...")
    results = await processor.batch_process(input_dir, output_dir, "*.txt")

    if "error" in results:
        print(f"Batch processing failed: {results['error']}")
        return

    print("\nProcessing Complete:")
    print(f"  Processed: {results['stats']['success']}/{results['stats']['total']}")
    print(f"  Failed: {results['stats']['failed']}/{results['stats']['total']}")

    if results["processed"]:
        print("\nAnalyzed documents:")
        for doc in results["processed"]:
            print(f"  - {doc['file']}: {doc.get('word_count', 0)} words")
            print(f"    Report: {doc['report']}")

    print(f"\nReports saved to: {output_dir}")


if __name__ == "__main__":
    asyncio.run(main())
