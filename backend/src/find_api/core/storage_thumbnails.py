"""Provider-neutral thumbnail generation and upload helpers."""

import logging
from io import BytesIO

from PIL import Image, ImageOps

from find_api.core.storage_abstract import StorageBackend

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = (256, 256)
THUMBNAIL_CONTENT_TYPE = "image/webp"
THUMBNAIL_EXTENSION = ".webp"
THUMBNAIL_QUALITY = 78


def generate_thumbnail(file_data: bytes) -> tuple[bytes, int, int]:
    """Generate a small WEBP thumbnail from image bytes."""
    with Image.open(BytesIO(file_data)) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)

        output = BytesIO()
        image.save(
            output,
            format="WEBP",
            quality=THUMBNAIL_QUALITY,
            method=4,
        )
        thumbnail_data = output.getvalue()

    return thumbnail_data, image.width, image.height


async def upload_thumbnail(
    backend: StorageBackend, file_data: bytes, file_hash: str
) -> dict | None:
    """Generate and upload a thumbnail for an image."""
    thumbnail_key = f"thumbnails/{file_hash[:2]}/{file_hash}{THUMBNAIL_EXTENSION}"

    try:
        thumbnail_data, width, height = generate_thumbnail(file_data)
        await backend.upload_file(thumbnail_data, thumbnail_key, THUMBNAIL_CONTENT_TYPE)
    except Exception as exc:
        logger.warning(
            "Failed to generate thumbnail for image hash %s: %s",
            file_hash,
            exc,
        )
        return None

    return {
        "thumbnail_key": thumbnail_key,
        "thumbnail_content_type": THUMBNAIL_CONTENT_TYPE,
        "thumbnail_size": len(thumbnail_data),
        "thumbnail_width": width,
        "thumbnail_height": height,
    }
