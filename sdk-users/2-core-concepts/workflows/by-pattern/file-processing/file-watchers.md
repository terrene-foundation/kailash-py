# File Processing Patterns Guide

## Overview

This guide provides comprehensive patterns for file processing workflows in Kailash, including file watching, document parsing, image processing, and real-time monitoring. Each pattern includes production-ready examples with proper error handling, retry logic, and system integration.

## Table of Contents

1. [File Watching and Auto-Processing](#file-watching-and-auto-processing)
2. [Document Parsing](#document-parsing)
3. [Image Processing with Computer Vision](#image-processing)
4. [Archive Management](#archive-management)
5. [Real-Time File Monitoring](#real-time-monitoring)
6. [Production Considerations](#production-considerations)
7. [Integration Patterns](#integration-patterns)

## File Watching and Auto-Processing {#file-watching-and-auto-processing}

### Basic File Watcher Pattern

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes import PythonCodeNode, SwitchNode
from kailash.runtime import CyclicRunner
import time
import os
from pathlib import Path

# File watcher workflow with auto-processing
workflow = WorkflowBuilder()

# Monitor directory for new files
watch_code = """
import os
import time
from pathlib import Path

# Get previous state
prev_files = cycle_info.get("node_state", {}).get("known_files", set())
watch_dir = Path(watch_directory)

# Scan directory
current_files = set()
new_files = []

if watch_dir.exists():
    for file_path in watch_dir.glob(file_pattern):
        current_files.add(str(file_path))
        if str(file_path) not in prev_files:
            new_files.append({
                "path": str(file_path),
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "modified": file_path.stat().st_mtime
            })

# Store state for next iteration
result = {
    "new_files": new_files,
    "total_files": len(current_files),
    "has_new_files": len(new_files) > 0,
    "_state": {"known_files": current_files}
}
"""

watcher = PythonCodeNode(
    name="file_watcher",
    code=watch_code,
    input_types={
        "watch_directory": str,
        "file_pattern": str,
        "cycle_info": dict
    }
)

# Process new files
process_code = """
import json
import mimetypes
from pathlib import Path

processed_files = []
errors = []

for file_info in new_files:
    try:
        file_path = Path(file_info["path"])
        mime_type, _ = mimetypes.guess_type(str(file_path))

        # Basic processing based on file type
        if mime_type and mime_type.startswith("text/"):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                processed_files.append({
                    "path": str(file_path),
                    "type": "text",
                    "size": len(content),
                    "lines": content.count('\\n'),
                    "preview": content[:200]
                })
        elif mime_type and mime_type.startswith("image/"):
            processed_files.append({
                "path": str(file_path),
                "type": "image",
                "size": file_info["size"],
                "mime_type": mime_type
            })
        else:
            processed_files.append({
                "path": str(file_path),
                "type": "unknown",
                "size": file_info["size"]
            })
    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e)
        })

result = {
    "processed_files": processed_files,
    "error_count": len(errors),
    "errors": errors,
    "continue_watching": True
}
"""

processor = PythonCodeNode(
    name="file_processor",
    code=process_code,
    input_types={
        "new_files": list
    }
)

# Decision node for continuing watch
decider = SwitchNode(
    name="continue_decider",
    condition_field="continue_watching"
)

# Connect workflow with cycle
workflow.add_node(watcher)
workflow.add_node(processor)
workflow.add_node(decider)

workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with file watching
runner = CyclicRunner(max_iterations=100)
result = runner.execute(
    workflow,
    parameters={
        "file_watcher.watch_directory": "/path/to/watch",
        "file_watcher.file_pattern": "*.txt",
        "file_watcher.cycle_info": {}
    }
)

```

### Advanced File Watcher with Filters

```python
# Advanced watcher with size limits, age filters, and pattern matching
advanced_watch_code = """
import os
import time
import re
from pathlib import Path
from datetime import datetime, timedelta

# Configuration
max_file_size = max_size_mb * 1024 * 1024
min_age = timedelta(seconds=min_age_seconds)
now = datetime.now()

# Get state
prev_state = cycle_info.get("node_state", {})
processed_files = set(prev_state.get("processed_files", []))
watch_dir = Path(watch_directory)

# Compile patterns
include_patterns = [re.compile(p) for p in include_patterns_list]
exclude_patterns = [re.compile(p) for p in exclude_patterns_list]

# Scan with filters
candidates = []
skipped = {"too_large": 0, "too_new": 0, "excluded": 0}

if watch_dir.exists():
    for file_path in watch_dir.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip already processed
        if str(file_path) in processed_files:
            continue

        # Check size
        if file_path.stat().st_size > max_file_size:
            skipped["too_large"] += 1
            continue

        # Check age
        file_age = now - datetime.fromtimestamp(file_path.stat().st_mtime)
        if file_age < min_age:
            skipped["too_new"] += 1
            continue

        # Check patterns
        file_str = str(file_path)
        if include_patterns and not any(p.search(file_str) for p in include_patterns):
            skipped["excluded"] += 1
            continue
        if exclude_patterns and any(p.search(file_str) for p in exclude_patterns):
            skipped["excluded"] += 1
            continue

        # Add candidate
        candidates.append({
            "path": str(file_path),
            "name": file_path.name,
            "size": file_path.stat().st_size,
            "modified": file_path.stat().st_mtime,
            "age_seconds": file_age.total_seconds()
        })

# Sort by priority (oldest first)
candidates.sort(key=lambda x: x["modified"])

# Take batch
batch = candidates[:batch_size]
new_processed = processed_files.copy()
for item in batch:
    new_processed.add(item["path"])

result = {
    "files_to_process": batch,
    "remaining_count": len(candidates) - len(batch),
    "skipped_stats": skipped,
    "_state": {"processed_files": list(new_processed)}
}
"""

advanced_watcher = PythonCodeNode(
    name="advanced_watcher",
    code=advanced_watch_code,
    input_types={
        "watch_directory": str,
        "include_patterns_list": list,
        "exclude_patterns_list": list,
        "max_size_mb": float,
        "min_age_seconds": int,
        "batch_size": int,
        "cycle_info": dict
    }
)

```

## Document Parsing {#document-parsing}

### PDF Processing Pattern

```python
# PDF document parser with text extraction and metadata
pdf_parser_code = """
import PyPDF2
import pdfplumber
from pathlib import Path
import json

parsed_documents = []
errors = []

for file_info in pdf_files:
    try:
        pdf_path = Path(file_info["path"])
        doc_data = {
            "path": str(pdf_path),
            "name": pdf_path.name,
            "pages": [],
            "metadata": {},
            "text_content": "",
            "tables": []
        }

        # Try pdfplumber first (better text extraction)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Extract metadata
                doc_data["metadata"] = {
                    "pages": len(pdf.pages),
                    "metadata": pdf.metadata
                }

                # Extract text and tables from each page
                full_text = []
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    full_text.append(page_text)

                    # Extract tables
                    tables = page.extract_tables()
                    if tables:
                        doc_data["tables"].extend([{
                            "page": i + 1,
                            "table_index": j,
                            "data": table
                        } for j, table in enumerate(tables)])

                    doc_data["pages"].append({
                        "page_num": i + 1,
                        "text": page_text,
                        "char_count": len(page_text)
                    })

                doc_data["text_content"] = "\\n\\n".join(full_text)

        except Exception as e:
            # Fallback to PyPDF2
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                doc_data["metadata"]["pages"] = len(reader.pages)

                full_text = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    full_text.append(text)
                    doc_data["pages"].append({
                        "page_num": i + 1,
                        "text": text,
                        "char_count": len(text)
                    })

                doc_data["text_content"] = "\\n\\n".join(full_text)

        # Calculate statistics
        doc_data["statistics"] = {
            "total_characters": len(doc_data["text_content"]),
            "total_words": len(doc_data["text_content"].split()),
            "total_lines": doc_data["text_content"].count("\\n"),
            "table_count": len(doc_data["tables"])
        }

        parsed_documents.append(doc_data)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "pdf_parsing_error"
        })

result = {
    "parsed_documents": parsed_documents,
    "success_count": len(parsed_documents),
    "error_count": len(errors),
    "errors": errors
}
"""

pdf_parser = PythonCodeNode(
    name="pdf_parser",
    code=pdf_parser_code,
    input_types={
        "pdf_files": list
    }
)

### Word Document Processing

```python
# Word document parser with formatting preservation
word_parser_code = """
import docx
from pathlib import Path
import json

parsed_docs = []
errors = []

for file_info in word_files:
    try:
        doc_path = Path(file_info["path"])
        doc = docx.Document(doc_path)

        doc_data = {
            "path": str(doc_path),
            "name": doc_path.name,
            "paragraphs": [],
            "tables": [],
            "headers": [],
            "sections": []
        }

        # Extract paragraphs with formatting
        for para in doc.paragraphs:
            if para.text.strip():
                para_data = {
                    "text": para.text,
                    "style": para.style.name if para.style else None,
                    "alignment": str(para.alignment) if para.alignment else None,
                    "runs": []
                }

                # Extract run-level formatting
                for run in para.runs:
                    if run.text:
                        para_data["runs"].append({
                            "text": run.text,
                            "bold": run.bold,
                            "italic": run.italic,
                            "underline": run.underline,
                            "font_name": run.font.name,
                            "font_size": run.font.size.pt if run.font.size else None
                        })

                doc_data["paragraphs"].append(para_data)

                # Identify headers
                if para.style and "Heading" in para.style.name:
                    doc_data["headers"].append({
                        "level": para.style.name,
                        "text": para.text
                    })

        # Extract tables
        for table_idx, table in enumerate(doc.tables):
            table_data = {
                "index": table_idx,
                "rows": [],
                "dimensions": {
                    "rows": len(table.rows),
                    "cols": len(table.columns)
                }
            }

            for row in table.rows:
                row_data = []
                for cell in row.cells:
                    row_data.append(cell.text.strip())
                table_data["rows"].append(row_data)

            doc_data["tables"].append(table_data)

        # Extract sections
        for section in doc.sections:
            doc_data["sections"].append({
                "start_type": str(section.start_type),
                "orientation": str(section.orientation),
                "page_width": section.page_width,
                "page_height": section.page_height
            })

        # Calculate statistics
        full_text = " ".join([p["text"] for p in doc_data["paragraphs"]])
        doc_data["statistics"] = {
            "total_characters": len(full_text),
            "total_words": len(full_text.split()),
            "paragraph_count": len(doc_data["paragraphs"]),
            "table_count": len(doc_data["tables"]),
            "header_count": len(doc_data["headers"])
        }

        parsed_docs.append(doc_data)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "word_parsing_error"
        })

result = {
    "parsed_documents": parsed_docs,
    "success_count": len(parsed_docs),
    "error_count": len(errors),
    "errors": errors
}
"""

word_parser = PythonCodeNode(
    name="word_parser",
    code=word_parser_code,
    input_types={
        "word_files": list
    }
)
```

### Text Extraction with OCR

```python
# OCR-based text extraction for scanned documents
ocr_extractor_code = """
import pytesseract
from PIL import Image
import cv2
import numpy as np
from pathlib import Path

extracted_texts = []
errors = []

for file_info in image_files:
    try:
        img_path = Path(file_info["path"])

        # Load and preprocess image
        image = cv2.imread(str(img_path))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply preprocessing based on options
        if apply_denoise:
            gray = cv2.fastNlMeansDenoising(gray)

        if apply_threshold:
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        if apply_deskew:
            # Simple deskewing
            coords = np.column_stack(np.where(gray > 0))
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if angle != 0:
                (h, w) = gray.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

        # Convert back to PIL Image
        pil_image = Image.fromarray(gray)

        # Extract text with different modes
        text_data = {
            "path": str(img_path),
            "name": img_path.name,
            "text": "",
            "confidence": 0,
            "languages": languages,
            "blocks": []
        }

        # Basic text extraction
        text_data["text"] = pytesseract.image_to_string(pil_image, lang="+".join(languages))

        # Detailed extraction with confidence
        details = pytesseract.image_to_data(pil_image, lang="+".join(languages), output_type=pytesseract.Output.DICT)

        # Group by blocks
        n_boxes = len(details['text'])
        valid_confidences = []
        current_block = {"text": [], "confidence": []}

        for i in range(n_boxes):
            if int(details['conf'][i]) > 0:
                valid_confidences.append(int(details['conf'][i]))

                if details['text'][i].strip():
                    current_block["text"].append(details['text'][i])
                    current_block["confidence"].append(int(details['conf'][i]))
                elif current_block["text"]:
                    # End of block
                    text_data["blocks"].append({
                        "text": " ".join(current_block["text"]),
                        "avg_confidence": sum(current_block["confidence"]) / len(current_block["confidence"])
                    })
                    current_block = {"text": [], "confidence": []}

        # Add last block
        if current_block["text"]:
            text_data["blocks"].append({
                "text": " ".join(current_block["text"]),
                "avg_confidence": sum(current_block["confidence"]) / len(current_block["confidence"])
            })

        # Calculate overall confidence
        if valid_confidences:
            text_data["confidence"] = sum(valid_confidences) / len(valid_confidences)

        # Word and character count
        text_data["statistics"] = {
            "character_count": len(text_data["text"]),
            "word_count": len(text_data["text"].split()),
            "line_count": text_data["text"].count("\\n"),
            "block_count": len(text_data["blocks"])
        }

        extracted_texts.append(text_data)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "ocr_extraction_error"
        })

result = {
    "extracted_texts": extracted_texts,
    "success_count": len(extracted_texts),
    "error_count": len(errors),
    "errors": errors
}
"""

ocr_extractor = PythonCodeNode(
    name="ocr_extractor",
    code=ocr_extractor_code,
    input_types={
        "image_files": list,
        "languages": list,
        "apply_denoise": bool,
        "apply_threshold": bool,
        "apply_deskew": bool
    }
)

```

## Image Processing with Computer Vision {#image-processing}

### Image Analysis Pipeline

```python
# Comprehensive image analysis with computer vision
image_analyzer_code = """
import cv2
import numpy as np
from PIL import Image
import imagehash
from pathlib import Path
import json

analyzed_images = []
errors = []

for file_info in image_files:
    try:
        img_path = Path(file_info["path"])

        # Load image
        image = cv2.imread(str(img_path))
        pil_image = Image.open(img_path)

        analysis = {
            "path": str(img_path),
            "name": img_path.name,
            "properties": {},
            "quality_metrics": {},
            "content_analysis": {},
            "hashes": {}
        }

        # Basic properties
        height, width = image.shape[:2]
        analysis["properties"] = {
            "width": width,
            "height": height,
            "channels": image.shape[2] if len(image.shape) > 2 else 1,
            "format": pil_image.format,
            "mode": pil_image.mode,
            "size_bytes": img_path.stat().st_size
        }

        # Quality metrics
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) > 2 else image

        # Blur detection (Laplacian variance)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        analysis["quality_metrics"]["sharpness_score"] = float(laplacian_var)
        analysis["quality_metrics"]["is_blurry"] = laplacian_var < blur_threshold

        # Brightness and contrast
        analysis["quality_metrics"]["brightness"] = float(np.mean(gray))
        analysis["quality_metrics"]["contrast"] = float(np.std(gray))

        # Noise estimation
        noise = cv2.Laplacian(gray, cv2.CV_64F)
        analysis["quality_metrics"]["noise_level"] = float(np.std(noise))

        # Content analysis
        if perform_content_analysis:
            # Color distribution
            if len(image.shape) > 2:
                # Calculate color histogram
                hist_b = cv2.calcHist([image], [0], None, [256], [0, 256])
                hist_g = cv2.calcHist([image], [1], None, [256], [0, 256])
                hist_r = cv2.calcHist([image], [2], None, [256], [0, 256])

                # Dominant colors
                analysis["content_analysis"]["dominant_colors"] = {
                    "blue": int(np.argmax(hist_b)),
                    "green": int(np.argmax(hist_g)),
                    "red": int(np.argmax(hist_r))
                }

                # Color statistics
                analysis["content_analysis"]["color_stats"] = {
                    "mean_rgb": [float(np.mean(image[:,:,i])) for i in range(3)],
                    "std_rgb": [float(np.std(image[:,:,i])) for i in range(3)]
                }

            # Edge detection
            edges = cv2.Canny(gray, 100, 200)
            analysis["content_analysis"]["edge_density"] = float(np.sum(edges > 0) / (width * height))

            # Corner detection
            corners = cv2.goodFeaturesToTrack(gray, maxCorners=1000, qualityLevel=0.01, minDistance=10)
            analysis["content_analysis"]["corner_count"] = len(corners) if corners is not None else 0

        # Perceptual hashing for duplicate detection
        analysis["hashes"] = {
            "average_hash": str(imagehash.average_hash(pil_image)),
            "perceptual_hash": str(imagehash.phash(pil_image)),
            "difference_hash": str(imagehash.dhash(pil_image)),
            "wavelet_hash": str(imagehash.whash(pil_image))
        }

        # Face detection if requested
        if detect_faces:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            analysis["content_analysis"]["face_count"] = len(faces)
            analysis["content_analysis"]["face_regions"] = [
                {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
                for (x, y, w, h) in faces
            ]

        analyzed_images.append(analysis)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "image_analysis_error"
        })

result = {
    "analyzed_images": analyzed_images,
    "success_count": len(analyzed_images),
    "error_count": len(errors),
    "errors": errors
}
"""

image_analyzer = PythonCodeNode(
    name="image_analyzer",
    code=image_analyzer_code,
    input_types={
        "image_files": list,
        "blur_threshold": float,
        "perform_content_analysis": bool,
        "detect_faces": bool
    }
)

### Image Transformation Pipeline

```python
# Image transformation and optimization
image_transformer_code = """
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
from pathlib import Path

transformed_images = []
errors = []

for file_info in image_files:
    try:
        img_path = Path(file_info["path"])
        output_dir = Path(output_directory)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load image
        image = cv2.imread(str(img_path))
        pil_image = Image.open(img_path)

        transformation_log = {
            "source": str(img_path),
            "transformations": []
        }

        # Resize if needed
        if resize_config["enabled"]:
            target_width = resize_config.get("width")
            target_height = resize_config.get("height")
            max_dimension = resize_config.get("max_dimension")

            if max_dimension:
                # Resize keeping aspect ratio
                h, w = image.shape[:2]
                if w > h:
                    new_w = max_dimension
                    new_h = int(h * (max_dimension / w))
                else:
                    new_h = max_dimension
                    new_w = int(w * (max_dimension / h))
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)
                pil_image = pil_image.resize((new_w, new_h), Image.LANCZOS)
                transformation_log["transformations"].append(f"Resized to {new_w}x{new_h}")
            elif target_width and target_height:
                image = cv2.resize(image, (target_width, target_height))
                pil_image = pil_image.resize((target_width, target_height))
                transformation_log["transformations"].append(f"Resized to {target_width}x{target_height}")

        # Apply filters
        if filters["sharpen"]:
            kernel = np.array([[-1,-1,-1],
                              [-1, 9,-1],
                              [-1,-1,-1]])
            image = cv2.filter2D(image, -1, kernel)
            transformation_log["transformations"].append("Applied sharpening filter")

        if filters["blur"]:
            image = cv2.GaussianBlur(image, (5, 5), 0)
            transformation_log["transformations"].append("Applied Gaussian blur")

        if filters["edge_enhance"]:
            edges = cv2.Canny(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 100, 200)
            edges_colored = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
            image = cv2.addWeighted(image, 0.8, edges_colored, 0.2, 0)
            transformation_log["transformations"].append("Enhanced edges")

        # Color adjustments using PIL
        if adjustments["brightness"] != 1.0:
            enhancer = ImageEnhance.Brightness(pil_image)
            pil_image = enhancer.enhance(adjustments["brightness"])
            transformation_log["transformations"].append(f"Adjusted brightness: {adjustments['brightness']}")

        if adjustments["contrast"] != 1.0:
            enhancer = ImageEnhance.Contrast(pil_image)
            pil_image = enhancer.enhance(adjustments["contrast"])
            transformation_log["transformations"].append(f"Adjusted contrast: {adjustments['contrast']}")

        if adjustments["saturation"] != 1.0:
            enhancer = ImageEnhance.Color(pil_image)
            pil_image = enhancer.enhance(adjustments["saturation"])
            transformation_log["transformations"].append(f"Adjusted saturation: {adjustments['saturation']}")

        # Convert PIL back to CV2 format if needed
        if len(transformation_log["transformations"]) > 3:  # If we did PIL operations
            image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

        # Auto-enhancement
        if auto_enhance:
            # Auto white balance
            result = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            avg_a = np.average(result[:, :, 1])
            avg_b = np.average(result[:, :, 2])
            result[:, :, 1] = result[:, :, 1] - ((avg_a - 128) * (result[:, :, 0] / 255.0) * 1.1)
            result[:, :, 2] = result[:, :, 2] - ((avg_b - 128) * (result[:, :, 0] / 255.0) * 1.1)
            image = cv2.cvtColor(result, cv2.COLOR_LAB2BGR)
            transformation_log["transformations"].append("Applied auto white balance")

            # Auto contrast
            lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            l = clahe.apply(l)
            image = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
            transformation_log["transformations"].append("Applied adaptive histogram equalization")

        # Save transformed image
        output_filename = f"{img_path.stem}_transformed{output_format}"
        output_path = output_dir / output_filename

        # Save with quality settings
        if output_format in ['.jpg', '.jpeg']:
            cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        elif output_format == '.png':
            cv2.imwrite(str(output_path), image, [cv2.IMWRITE_PNG_COMPRESSION, png_compression])
        else:
            cv2.imwrite(str(output_path), image)

        transformation_log["output"] = str(output_path)
        transformation_log["output_size"] = output_path.stat().st_size
        transformed_images.append(transformation_log)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "transformation_error"
        })

result = {
    "transformed_images": transformed_images,
    "success_count": len(transformed_images),
    "error_count": len(errors),
    "errors": errors
}
"""

image_transformer = PythonCodeNode(
    name="image_transformer",
    code=image_transformer_code,
    input_types={
        "image_files": list,
        "output_directory": str,
        "output_format": str,
        "resize_config": dict,
        "filters": dict,
        "adjustments": dict,
        "auto_enhance": bool,
        "jpeg_quality": int,
        "png_compression": int
    }
)
```

## Archive Management {#archive-management}

### Archive Processing Pattern

```python
# Archive extraction and management
archive_processor_code = """
import zipfile
import tarfile
import gzip
import shutil
from pathlib import Path
import json

processed_archives = []
errors = []

for file_info in archive_files:
    try:
        archive_path = Path(file_info["path"])
        extract_dir = Path(extraction_directory) / archive_path.stem
        extract_dir.mkdir(parents=True, exist_ok=True)

        archive_data = {
            "path": str(archive_path),
            "name": archive_path.name,
            "type": "",
            "files": [],
            "total_size": 0,
            "compressed_size": archive_path.stat().st_size,
            "extraction_path": str(extract_dir)
        }

        # Determine archive type and extract
        if archive_path.suffix.lower() in ['.zip']:
            archive_data["type"] = "zip"
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                # List contents
                for info in zip_ref.infolist():
                    if not info.is_dir():
                        archive_data["files"].append({
                            "filename": info.filename,
                            "compressed_size": info.compress_size,
                            "uncompressed_size": info.file_size,
                            "compression_type": info.compress_type,
                            "date_time": str(info.date_time)
                        })
                        archive_data["total_size"] += info.file_size

                # Extract with filters
                for info in zip_ref.infolist():
                    if apply_filters:
                        # Check file patterns
                        if include_patterns and not any(pattern in info.filename for pattern in include_patterns):
                            continue
                        if exclude_patterns and any(pattern in info.filename for pattern in exclude_patterns):
                            continue
                        # Check size limits
                        if max_file_size_mb and info.file_size > max_file_size_mb * 1024 * 1024:
                            continue

                    # Extract file
                    if extract_files:
                        zip_ref.extract(info, extract_dir)

        elif archive_path.suffix.lower() in ['.tar', '.tgz', '.tar.gz', '.tar.bz2']:
            archive_data["type"] = "tar"
            mode = 'r:gz' if archive_path.suffix in ['.tgz', '.gz'] else 'r:bz2' if archive_path.suffix == '.bz2' else 'r'

            with tarfile.open(archive_path, mode) as tar_ref:
                # List contents
                for member in tar_ref.getmembers():
                    if member.isfile():
                        archive_data["files"].append({
                            "filename": member.name,
                            "size": member.size,
                            "mode": oct(member.mode),
                            "uid": member.uid,
                            "gid": member.gid,
                            "mtime": member.mtime
                        })
                        archive_data["total_size"] += member.size

                # Extract with filters
                if extract_files:
                    for member in tar_ref.getmembers():
                        if apply_filters:
                            if include_patterns and not any(pattern in member.name for pattern in include_patterns):
                                continue
                            if exclude_patterns and any(pattern in member.name for pattern in exclude_patterns):
                                continue
                            if max_file_size_mb and member.size > max_file_size_mb * 1024 * 1024:
                                continue

                        tar_ref.extract(member, extract_dir)

        elif archive_path.suffix.lower() == '.gz' and not '.tar' in archive_path.name:
            archive_data["type"] = "gzip"
            # Handle single gzipped file
            output_path = extract_dir / archive_path.stem

            with gzip.open(archive_path, 'rb') as gz_file:
                with open(output_path, 'wb') as out_file:
                    shutil.copyfileobj(gz_file, out_file)

            archive_data["files"].append({
                "filename": archive_path.stem,
                "uncompressed_size": output_path.stat().st_size
            })
            archive_data["total_size"] = output_path.stat().st_size

        # Calculate compression ratio
        if archive_data["total_size"] > 0:
            archive_data["compression_ratio"] = archive_data["compressed_size"] / archive_data["total_size"]

        # Scan extracted files if requested
        if scan_extracted and extract_files:
            extracted_info = []
            for extracted_file in extract_dir.rglob("*"):
                if extracted_file.is_file():
                    extracted_info.append({
                        "path": str(extracted_file),
                        "size": extracted_file.stat().st_size,
                        "relative_path": str(extracted_file.relative_to(extract_dir))
                    })
            archive_data["extracted_files"] = extracted_info

        processed_archives.append(archive_data)

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "archive_processing_error"
        })

result = {
    "processed_archives": processed_archives,
    "success_count": len(processed_archives),
    "error_count": len(errors),
    "errors": errors,
    "total_extracted_size": sum(a["total_size"] for a in processed_archives)
}
"""

archive_processor = PythonCodeNode(
    name="archive_processor",
    code=archive_processor_code,
    input_types={
        "archive_files": list,
        "extraction_directory": str,
        "extract_files": bool,
        "scan_extracted": bool,
        "apply_filters": bool,
        "include_patterns": list,
        "exclude_patterns": list,
        "max_file_size_mb": float
    }
)

### Archive Creation Pattern

```python
# Create archives with compression
archive_creator_code = """
import zipfile
import tarfile
import gzip
import shutil
from pathlib import Path
import time

created_archives = []
errors = []

# Group files by archive
archive_groups = {}
for file_info in files_to_archive:
    archive_name = file_info.get("archive_name", "archive")
    if archive_name not in archive_groups:
        archive_groups[archive_name] = []
    archive_groups[archive_name].append(file_info)

# Create archives
for archive_name, files in archive_groups.items():
    try:
        output_path = Path(output_directory) / f"{archive_name}{archive_format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        archive_info = {
            "name": archive_name,
            "path": str(output_path),
            "format": archive_format,
            "files": [],
            "total_size_before": 0,
            "total_size_after": 0,
            "creation_time": time.time()
        }

        if archive_format == ".zip":
            compression = zipfile.ZIP_DEFLATED if compression_level > 0 else zipfile.ZIP_STORED

            with zipfile.ZipFile(output_path, 'w', compression=compression) as zip_file:
                for file_info in files:
                    file_path = Path(file_info["path"])
                    if file_path.exists():
                        # Determine archive path
                        if preserve_paths:
                            arcname = file_path
                        else:
                            arcname = file_path.name

                        # Add file
                        zip_file.write(file_path, arcname=arcname, compress_type=compression)

                        # Track info
                        file_size = file_path.stat().st_size
                        archive_info["files"].append({
                            "source": str(file_path),
                            "archive_name": str(arcname),
                            "size": file_size
                        })
                        archive_info["total_size_before"] += file_size

                # Add metadata if provided
                if include_metadata:
                    metadata = {
                        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "file_count": len(archive_info["files"]),
                        "compression_level": compression_level
                    }
                    zip_file.writestr("_metadata.json", json.dumps(metadata, indent=2))

        elif archive_format in [".tar", ".tar.gz", ".tgz", ".tar.bz2"]:
            if archive_format in [".tar.gz", ".tgz"]:
                mode = 'w:gz'
            elif archive_format == ".tar.bz2":
                mode = 'w:bz2'
            else:
                mode = 'w'

            with tarfile.open(output_path, mode) as tar_file:
                for file_info in files:
                    file_path = Path(file_info["path"])
                    if file_path.exists():
                        # Determine archive path
                        if preserve_paths:
                            arcname = file_path
                        else:
                            arcname = file_path.name

                        # Add file
                        tar_file.add(file_path, arcname=arcname)

                        # Track info
                        file_size = file_path.stat().st_size
                        archive_info["files"].append({
                            "source": str(file_path),
                            "archive_name": str(arcname),
                            "size": file_size
                        })
                        archive_info["total_size_before"] += file_size

                # Add metadata if provided
                if include_metadata:
                    metadata = {
                        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "file_count": len(archive_info["files"]),
                        "format": archive_format
                    }
                    metadata_info = tarfile.TarInfo(name="_metadata.json")
                    metadata_content = json.dumps(metadata, indent=2).encode('utf-8')
                    metadata_info.size = len(metadata_content)
                    metadata_info.mtime = time.time()
                    tar_file.addfile(metadata_info, io.BytesIO(metadata_content))

        # Get final archive size
        archive_info["total_size_after"] = output_path.stat().st_size
        archive_info["compression_ratio"] = (
            archive_info["total_size_after"] / archive_info["total_size_before"]
            if archive_info["total_size_before"] > 0 else 1
        )

        # Verify archive if requested
        if verify_after_creation:
            try:
                if archive_format == ".zip":
                    with zipfile.ZipFile(output_path, 'r') as zip_file:
                        bad_file = zip_file.testzip()
                        archive_info["verified"] = bad_file is None
                        if bad_file:
                            archive_info["verification_error"] = f"Bad file in archive: {bad_file}"
                else:
                    # Basic verification for tar
                    with tarfile.open(output_path, 'r') as tar_file:
                        members = tar_file.getmembers()
                        archive_info["verified"] = len(members) == len(archive_info["files"])
            except Exception as e:
                archive_info["verified"] = False
                archive_info["verification_error"] = str(e)

        created_archives.append(archive_info)

    except Exception as e:
        errors.append({
            "archive": archive_name,
            "error": str(e),
            "type": "archive_creation_error"
        })

result = {
    "created_archives": created_archives,
    "success_count": len(created_archives),
    "error_count": len(errors),
    "errors": errors,
    "total_compressed_size": sum(a["total_size_after"] for a in created_archives),
    "total_original_size": sum(a["total_size_before"] for a in created_archives)
}
"""

archive_creator = PythonCodeNode(
    name="archive_creator",
    code=archive_creator_code,
    input_types={
        "files_to_archive": list,
        "output_directory": str,
        "archive_format": str,
        "compression_level": int,
        "preserve_paths": bool,
        "include_metadata": bool,
        "verify_after_creation": bool
    }
)
```

## Real-Time File Monitoring {#real-time-monitoring}

### Event-Based File Monitor

```python
# Real-time file system monitoring with event handling
realtime_monitor_code = """
import time
import hashlib
from pathlib import Path
from datetime import datetime
import json

# Get state from previous cycle
prev_state = cycle_info.get("node_state", {})
file_registry = prev_state.get("file_registry", {})
event_queue = []

# Scan monitored paths
current_time = time.time()
monitored_paths = [Path(p) for p in monitor_paths]

for base_path in monitored_paths:
    if not base_path.exists():
        continue

    # Recursive scan based on configuration
    if recursive_monitoring:
        file_iterator = base_path.rglob("*")
    else:
        file_iterator = base_path.glob("*")

    for file_path in file_iterator:
        if not file_path.is_file():
            continue

        # Apply filters
        if file_patterns:
            if not any(file_path.match(pattern) for pattern in file_patterns):
                continue

        file_key = str(file_path)
        file_stat = file_path.stat()

        # Calculate file hash for change detection
        if detect_content_changes:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read(1024 * 1024)).hexdigest()  # First 1MB
        else:
            file_hash = None

        current_info = {
            "path": file_key,
            "size": file_stat.st_size,
            "mtime": file_stat.st_mtime,
            "hash": file_hash
        }

        # Check for events
        if file_key not in file_registry:
            # New file
            event_queue.append({
                "type": "created",
                "path": file_key,
                "timestamp": current_time,
                "details": current_info
            })
        else:
            prev_info = file_registry[file_key]

            # Check for modifications
            if prev_info["mtime"] != current_info["mtime"]:
                event_queue.append({
                    "type": "modified",
                    "path": file_key,
                    "timestamp": current_time,
                    "details": {
                        "size_change": current_info["size"] - prev_info["size"],
                        "time_since_last": current_time - prev_info["mtime"]
                    }
                })
            elif detect_content_changes and prev_info.get("hash") != current_info.get("hash"):
                event_queue.append({
                    "type": "content_changed",
                    "path": file_key,
                    "timestamp": current_time,
                    "details": {"hash_changed": True}
                })

        # Update registry
        file_registry[file_key] = current_info

# Check for deletions
if detect_deletions:
    current_files = set()
    for base_path in monitored_paths:
        if base_path.exists():
            if recursive_monitoring:
                current_files.update(str(p) for p in base_path.rglob("*") if p.is_file())
            else:
                current_files.update(str(p) for p in base_path.glob("*") if p.is_file())

    for file_key in list(file_registry.keys()):
        if file_key not in current_files:
            event_queue.append({
                "type": "deleted",
                "path": file_key,
                "timestamp": current_time,
                "details": file_registry[file_key]
            })
            del file_registry[file_key]

# Process events through filters
filtered_events = []
for event in event_queue:
    # Apply event filters
    if event_filters.get(event["type"], True):
        # Check cooldown period
        if cooldown_seconds > 0:
            last_event_time = prev_state.get("last_event_times", {}).get(event["path"], 0)
            if current_time - last_event_time < cooldown_seconds:
                continue

        filtered_events.append(event)

# Update last event times
last_event_times = prev_state.get("last_event_times", {})
for event in filtered_events:
    last_event_times[event["path"]] = current_time

# Prepare result
result = {
    "events": filtered_events,
    "event_count": len(filtered_events),
    "total_monitored_files": len(file_registry),
    "has_events": len(filtered_events) > 0,
    "continue_monitoring": True,
    "_state": {
        "file_registry": file_registry,
        "last_event_times": last_event_times
    }
}
"""

realtime_monitor = PythonCodeNode(
    name="realtime_monitor",
    code=realtime_monitor_code,
    input_types={
        "monitor_paths": list,
        "file_patterns": list,
        "recursive_monitoring": bool,
        "detect_content_changes": bool,
        "detect_deletions": bool,
        "event_filters": dict,
        "cooldown_seconds": int,
        "cycle_info": dict
    }
)

### File Change Processor

```python
# Process file change events with actions
change_processor_code = """
import shutil
from pathlib import Path
import json
import time

processed_events = []
errors = []

for event in events:
    try:
        event_type = event["type"]
        file_path = Path(event["path"])

        processing_result = {
            "event": event,
            "actions_taken": [],
            "timestamp": time.time()
        }

        # Route based on event type
        if event_type == "created":
            # New file actions
            if actions["on_create"].get("backup"):
                backup_dir = Path(backup_directory) / "created" / time.strftime("%Y%m%d")
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / file_path.name
                shutil.copy2(file_path, backup_path)
                processing_result["actions_taken"].append({
                    "action": "backup",
                    "destination": str(backup_path)
                })

            if actions["on_create"].get("notify"):
                processing_result["actions_taken"].append({
                    "action": "notify",
                    "message": f"New file created: {file_path.name}"
                })

            if actions["on_create"].get("process"):
                # Trigger processing based on file type
                if file_path.suffix.lower() in ['.csv', '.xlsx']:
                    processing_result["actions_taken"].append({
                        "action": "queue_for_processing",
                        "processor": "data_pipeline"
                    })
                elif file_path.suffix.lower() in ['.jpg', '.png', '.jpeg']:
                    processing_result["actions_taken"].append({
                        "action": "queue_for_processing",
                        "processor": "image_pipeline"
                    })

        elif event_type == "modified":
            # File modification actions
            if actions["on_modify"].get("version"):
                version_dir = Path(version_directory) / file_path.stem
                version_dir.mkdir(parents=True, exist_ok=True)
                version_name = f"{file_path.stem}_v{int(time.time())}{file_path.suffix}"
                version_path = version_dir / version_name
                shutil.copy2(file_path, version_path)
                processing_result["actions_taken"].append({
                    "action": "version",
                    "version_path": str(version_path)
                })

            if actions["on_modify"].get("validate"):
                # Validate file integrity
                is_valid = True
                validation_errors = []

                if file_path.suffix.lower() == '.json':
                    try:
                        with open(file_path, 'r') as f:
                            json.load(f)
                    except json.JSONDecodeError as e:
                        is_valid = False
                        validation_errors.append(str(e))

                processing_result["actions_taken"].append({
                    "action": "validate",
                    "valid": is_valid,
                    "errors": validation_errors
                })

        elif event_type == "deleted":
            # File deletion actions
            if actions["on_delete"].get("log"):
                processing_result["actions_taken"].append({
                    "action": "log_deletion",
                    "details": event["details"]
                })

            if actions["on_delete"].get("alert"):
                processing_result["actions_taken"].append({
                    "action": "alert",
                    "severity": "warning",
                    "message": f"File deleted: {event['path']}"
                })

        # Apply common actions
        if apply_common_actions:
            # Log all events
            log_entry = {
                "timestamp": processing_result["timestamp"],
                "event_type": event_type,
                "path": event["path"],
                "actions": processing_result["actions_taken"]
            }

            log_path = Path(log_directory) / f"file_events_{time.strftime('%Y%m%d')}.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            with open(log_path, 'a') as f:
                f.write(json.dumps(log_entry) + "\\n")

            processing_result["actions_taken"].append({
                "action": "logged",
                "log_path": str(log_path)
            })

        processed_events.append(processing_result)

    except Exception as e:
        errors.append({
            "event": event,
            "error": str(e),
            "type": "processing_error"
        })

# Generate summary
summary = {
    "total_processed": len(processed_events),
    "by_event_type": {},
    "by_action": {}
}

for result in processed_events:
    event_type = result["event"]["type"]
    summary["by_event_type"][event_type] = summary["by_event_type"].get(event_type, 0) + 1

    for action in result["actions_taken"]:
        action_type = action["action"]
        summary["by_action"][action_type] = summary["by_action"].get(action_type, 0) + 1

result = {
    "processed_events": processed_events,
    "errors": errors,
    "summary": summary,
    "continue_monitoring": len(errors) < len(events)  # Continue if not all failed
}
"""

change_processor = PythonCodeNode(
    name="change_processor",
    code=change_processor_code,
    input_types={
        "events": list,
        "actions": dict,
        "backup_directory": str,
        "version_directory": str,
        "log_directory": str,
        "apply_common_actions": bool
    }
)
```

## Production Considerations {#production-considerations}

### Error Handling and Retry Logic

```python
# Robust file processing with retry and error recovery
robust_processor_code = """
import time
import traceback
from pathlib import Path
import json

def process_with_retry(file_path, max_retries=3, backoff_factor=2):
    last_error = None

    for attempt in range(max_retries):
        try:
            # Attempt processing
            result = process_single_file(file_path)
            return {"success": True, "result": result, "attempts": attempt + 1}
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                time.sleep(sleep_time)
            continue

    return {
        "success": False,
        "error": str(last_error),
        "traceback": traceback.format_exc(),
        "attempts": max_retries
    }

def process_single_file(file_path):
    path = Path(file_path)

    # Validate file exists and is accessible
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if not path.is_file():
        raise ValueError(f"Not a file: {file_path}")

    # Check file lock (platform-specific)
    try:
        with open(path, 'rb') as f:
            # Try to read first byte to check access
            f.read(1)
    except IOError as e:
        raise IOError(f"File locked or inaccessible: {e}")

    # Process based on file type
    file_size = path.stat().st_size

    # Size validation
    if file_size > max_file_size_bytes:
        raise ValueError(f"File too large: {file_size} bytes")

    if file_size == 0:
        raise ValueError("File is empty")

    # Actual processing logic here
    processing_result = {
        "path": str(path),
        "size": file_size,
        "processed_at": time.time()
    }

    return processing_result

# Main processing loop
results = {
    "successful": [],
    "failed": [],
    "skipped": []
}

for file_info in files_to_process:
    file_path = file_info["path"]

    # Pre-processing validation
    if skip_hidden_files and Path(file_path).name.startswith('.'):
        results["skipped"].append({
            "path": file_path,
            "reason": "hidden_file"
        })
        continue

    # Process with retry
    result = process_with_retry(
        file_path,
        max_retries=retry_config["max_attempts"],
        backoff_factor=retry_config["backoff_factor"]
    )

    if result["success"]:
        results["successful"].append(result)
    else:
        results["failed"].append({
            "path": file_path,
            "error": result["error"],
            "attempts": result["attempts"]
        })

        # Error recovery actions
        if error_recovery["move_failed"]:
            try:
                failed_dir = Path(error_directory) / "failed"
                failed_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(file_path, failed_dir / Path(file_path).name)
            except:
                pass  # Don't fail on cleanup errors

# Calculate metrics
total_files = len(files_to_process)
success_rate = len(results["successful"]) / total_files if total_files > 0 else 0

result = {
    "results": results,
    "metrics": {
        "total_files": total_files,
        "successful": len(results["successful"]),
        "failed": len(results["failed"]),
        "skipped": len(results["skipped"]),
        "success_rate": success_rate
    },
    "continue_processing": success_rate > min_success_rate
}
"""

robust_processor = PythonCodeNode(
    name="robust_processor",
    code=robust_processor_code,
    input_types={
        "files_to_process": list,
        "max_file_size_bytes": int,
        "skip_hidden_files": bool,
        "retry_config": dict,
        "error_recovery": dict,
        "error_directory": str,
        "min_success_rate": float
    }
)

```

### Performance Optimization

```python
# Parallel file processing with thread pool
parallel_processor_code = """
import concurrent.futures
import multiprocessing
from pathlib import Path
import time
import os

# Determine optimal worker count
cpu_count = multiprocessing.cpu_count()
optimal_workers = min(max_workers, cpu_count * 2)  # IO-bound tasks benefit from more workers

def process_file_batch(batch):
    results = []
    for file_info in batch:
        try:
            # Simulate file processing
            file_path = Path(file_info["path"])

            # Read file in chunks for memory efficiency
            chunk_size = 1024 * 1024  # 1MB chunks
            hasher = hashlib.md5()

            with open(file_path, 'rb') as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)

            results.append({
                "path": str(file_path),
                "hash": hasher.hexdigest(),
                "size": file_path.stat().st_size,
                "success": True
            })
        except Exception as e:
            results.append({
                "path": file_info["path"],
                "error": str(e),
                "success": False
            })
    return results

# Split files into batches
batch_size = max(1, len(files_to_process) // optimal_workers)
batches = [files_to_process[i:i + batch_size] for i in range(0, len(files_to_process), batch_size)]

# Process in parallel
all_results = []
processing_times = []

start_time = time.time()

with concurrent.futures.ThreadPoolExecutor(max_workers=optimal_workers) as executor:
    # Submit all batches
    future_to_batch = {executor.submit(process_file_batch, batch): batch for batch in batches}

    # Process completed futures
    for future in concurrent.futures.as_completed(future_to_batch):
        batch_start = time.time()
        try:
            batch_results = future.result()
            all_results.extend(batch_results)
            processing_times.append(time.time() - batch_start)
        except Exception as e:
            # Handle batch failure
            batch = future_to_batch[future]
            for file_info in batch:
                all_results.append({
                    "path": file_info["path"],
                    "error": f"Batch processing failed: {str(e)}",
                    "success": False
                })

total_time = time.time() - start_time

# Calculate performance metrics
successful = [r for r in all_results if r.get("success", False)]
failed = [r for r in all_results if not r.get("success", False)]

performance_metrics = {
    "total_files": len(files_to_process),
    "successful": len(successful),
    "failed": len(failed),
    "total_time_seconds": total_time,
    "files_per_second": len(files_to_process) / total_time if total_time > 0 else 0,
    "worker_count": optimal_workers,
    "average_batch_time": sum(processing_times) / len(processing_times) if processing_times else 0
}

result = {
    "results": all_results,
    "performance_metrics": performance_metrics,
    "optimization_suggestions": []
}

# Provide optimization suggestions
if performance_metrics["files_per_second"] < 10:
    result["optimization_suggestions"].append("Consider increasing worker count for better throughput")

if len(failed) > len(successful) * 0.1:  # More than 10% failure rate
    result["optimization_suggestions"].append("High failure rate detected - review error patterns")
"""

parallel_processor = PythonCodeNode(
    name="parallel_processor",
    code=parallel_processor_code,
    input_types={
        "files_to_process": list,
        "max_workers": int
    }
)

```

## Integration Patterns {#integration-patterns}

### Complete File Processing Workflow

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes import PythonCodeNode, SwitchNode
from kailash.runtime import CyclicRunner

# Complete file processing workflow with all components
workflow = WorkflowBuilder()

# Add all nodes
workflow.add_node(realtime_monitor)
workflow.add_node(change_processor)
workflow.add_node(robust_processor)
workflow.add_node(pdf_parser)
workflow.add_node(image_analyzer)
workflow.add_node(archive_processor)

# Decision node for routing
router = SwitchNode(
    name="file_router",
    condition_field="has_events"
)

# Connect monitoring cycle
workflow.add_connection("source", "result", "target", "input")  # Fixed mapping pattern
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Route back to monitor
# Use CycleBuilder API: workflow.build().create_cycle("name").connect(...).build()

# Execute with comprehensive configuration
runner = CyclicRunner(max_iterations=1000)
result = runner.execute(
    workflow,
    parameters={
        "realtime_monitor.monitor_paths": ["/data/incoming", "/data/processing"],
        "realtime_monitor.file_patterns": ["*.pdf", "*.docx", "*.zip"],
        "realtime_monitor.recursive_monitoring": True,
        "realtime_monitor.detect_content_changes": True,
        "realtime_monitor.detect_deletions": True,
        "realtime_monitor.event_filters": {
            "created": True,
            "modified": True,
            "deleted": True
        },
        "realtime_monitor.cooldown_seconds": 5,
        "realtime_monitor.cycle_info": {},
        "change_processor.actions": {
            "on_create": {"backup": True, "process": True},
            "on_modify": {"version": True, "validate": True},
            "on_delete": {"log": True, "alert": True}
        },
        "change_processor.backup_directory": "/data/backups",
        "change_processor.version_directory": "/data/versions",
        "change_processor.log_directory": "/data/logs",
        "change_processor.apply_common_actions": True
    }
)

```

### Integration with External Systems

```python
# S3 upload integration
s3_uploader_code = """
import boto3
from pathlib import Path
import mimetypes

s3_client = boto3.client('s3')
uploaded_files = []
errors = []

for file_info in files_to_upload:
    try:
        file_path = Path(file_info["path"])

        # Determine S3 key
        if preserve_directory_structure:
            s3_key = str(file_path.relative_to(base_directory))
        else:
            s3_key = file_path.name

        if s3_prefix:
            s3_key = f"{s3_prefix}/{s3_key}"

        # Determine content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'application/octet-stream'

        # Upload with metadata
        metadata = {
            'original-path': str(file_path),
            'upload-time': str(time.time()),
            'source-system': source_system_name
        }

        # Add custom metadata
        if file_info.get("metadata"):
            metadata.update(file_info["metadata"])

        # Upload file
        with open(file_path, 'rb') as f:
            s3_client.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=f,
                ContentType=content_type,
                Metadata=metadata,
                ServerSideEncryption='AES256' if enable_encryption else None
            )

        uploaded_files.append({
            "local_path": str(file_path),
            "s3_key": s3_key,
            "bucket": s3_bucket,
            "size": file_path.stat().st_size,
            "url": f"s3://{s3_bucket}/{s3_key}"
        })

        # Delete local file if configured
        if delete_after_upload:
            file_path.unlink()

    except Exception as e:
        errors.append({
            "file": file_info["path"],
            "error": str(e),
            "type": "s3_upload_error"
        })

result = {
    "uploaded_files": uploaded_files,
    "success_count": len(uploaded_files),
    "error_count": len(errors),
    "errors": errors
}
"""

s3_uploader = PythonCodeNode(
    name="s3_uploader",
    code=s3_uploader_code,
    input_types={
        "files_to_upload": list,
        "s3_bucket": str,
        "s3_prefix": str,
        "base_directory": str,
        "preserve_directory_structure": bool,
        "source_system_name": str,
        "enable_encryption": bool,
        "delete_after_upload": bool
    }
)

```

## Best Practices

### 1. **File Locking and Concurrency**
- Always check file accessibility before processing
- Implement proper locking mechanisms for shared files
- Use atomic operations for critical file updates

### 2. **Memory Management**
- Process large files in chunks
- Use streaming for continuous data
- Implement proper cleanup and resource disposal

### 3. **Error Recovery**
- Implement comprehensive retry logic
- Maintain processing state for recovery
- Log all errors with context for debugging

### 4. **Performance Optimization**
- Use parallel processing for CPU-intensive operations
- Implement caching for frequently accessed files
- Batch operations when possible

### 5. **Security Considerations**
- Validate all file paths to prevent traversal attacks
- Implement proper access controls
- Sanitize file names and content
- Use encryption for sensitive data

### 6. **Monitoring and Alerting**
- Track processing metrics
- Set up alerts for failures
- Monitor resource usage
- Implement health checks

## Summary

This guide provides comprehensive patterns for file processing workflows including:

- **File watching** with filtering and event handling
- **Document parsing** for various formats (PDF, Word, text)
- **Image processing** with computer vision capabilities
- **Archive management** for compressed files
- **Real-time monitoring** with event-based processing
- **Production-ready** error handling and recovery
- **System integration** with external services

Each pattern is designed to be modular and can be combined to create complex file processing pipelines. The examples include proper error handling, performance optimization, and production considerations for building robust file processing systems.
