"""Vision utilities for AI providers - lazy loaded to avoid overhead."""

from pathlib import Path
from typing import Optional, Tuple


def encode_image(image_path: str) -> str:
    """
    Encode image file to base64 string.

    Args:
        image_path: Path to the image file

    Returns:
        Base64 encoded string of the image

    Raises:
        FileNotFoundError: If image file doesn't exist
        IOError: If unable to read the image file
    """
    # Lazy import to avoid overhead when not using vision
    import base64

    image_path = Path(image_path).resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        raise IOError(f"Failed to read image file: {e}")


def get_media_type(image_path: str) -> str:
    """
    Get media type from file extension.

    Args:
        image_path: Path to the image file

    Returns:
        Media type string (e.g., "image/jpeg")
    """
    ext = Path(image_path).suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
    }
    return media_types.get(ext, "image/jpeg")


def validate_image_size(
    image_path: str, max_size_mb: float = 20.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate image file size.

    Args:
        image_path: Path to the image file
        max_size_mb: Maximum allowed size in megabytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    import os

    try:
        size_bytes = os.path.getsize(image_path)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > max_size_mb:
            return False, f"Image size {size_mb:.1f}MB exceeds maximum {max_size_mb}MB"

        return True, None
    except Exception as e:
        return False, f"Failed to check image size: {e}"


def resize_image_if_needed(
    image_path: str, max_size_mb: float = 20.0, max_dimension: int = 4096
) -> Optional[str]:
    """
    Resize image if it exceeds size or dimension limits.

    Args:
        image_path: Path to the image file
        max_size_mb: Maximum file size in MB
        max_dimension: Maximum width or height in pixels

    Returns:
        Base64 encoded resized image, or None if no resize needed
    """
    try:
        # Lazy import to avoid PIL dependency when not using vision
        import base64
        import io

        from PIL import Image

        # Check if resize is needed
        is_valid, _ = validate_image_size(image_path, max_size_mb)

        with Image.open(image_path) as img:
            # Check dimensions
            needs_resize = (
                not is_valid or img.width > max_dimension or img.height > max_dimension
            )

            if not needs_resize:
                return None

            # Calculate new size maintaining aspect ratio
            ratio = min(max_dimension / img.width, max_dimension / img.height, 1.0)
            new_size = (int(img.width * ratio), int(img.height * ratio))

            # Resize image
            img = img.resize(new_size, Image.Resampling.LANCZOS)

            # Convert to RGB if necessary (for JPEG)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Save to bytes
            output = io.BytesIO()
            img_format = (
                "JPEG"
                if Path(image_path).suffix.lower() in [".jpg", ".jpeg"]
                else "PNG"
            )
            img.save(output, format=img_format, optimize=True, quality=85)

            # Encode to base64
            output.seek(0)
            return base64.b64encode(output.read()).decode("utf-8")

    except ImportError:
        # PIL not available, skip resizing
        return None
    except Exception:
        # Any error in resizing, return None to use original
        return None
