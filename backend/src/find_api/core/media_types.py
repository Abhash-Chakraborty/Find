"""
File-type filter values shared by gallery and search
"""

_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
}


def content_type_for_file_type(file_type: str) -> str:
    """Map a filter value like "jpg" or ".PNG" to the stored MIME type."""
    normalized = file_type.strip().lower().lstrip(".")
    return _CONTENT_TYPES.get(normalized, normalized)
