"""
Extract EXIF data from images
"""

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

GPS_INFO_TAG = 0x8825


def _gps_degrees(value: Any, reference: Any) -> Optional[float]:
    """Convert an EXIF DMS tuple into signed decimal degrees."""
    try:
        degrees, minutes, seconds = (float(part) for part in value)
        coordinate = degrees + minutes / 60 + seconds / 3600
        if str(reference).upper() in {"S", "W"}:
            coordinate *= -1
        return coordinate
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def extract_gps_coordinates(image: Image.Image) -> Optional[tuple[float, float]]:
    """Return ``(latitude, longitude)`` from EXIF, without network geocoding.

    Callers must opt in before storing this sensitive location metadata. The
    helper intentionally does no reverse geocoding or tile/provider request.
    """
    try:
        exif = image.getexif()
        if not exif:
            return None
        gps_ifd = exif.get_ifd(GPS_INFO_TAG)
        if not gps_ifd:
            return None
        latitude = _gps_degrees(gps_ifd.get(2), gps_ifd.get(1))
        longitude = _gps_degrees(gps_ifd.get(4), gps_ifd.get(3))
        if latitude is None or longitude is None:
            return None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        return (round(latitude, 7), round(longitude, 7))
    except Exception as exc:  # malformed EXIF must not fail image indexing
        logger.warning("Failed to parse GPS coordinates: %s", exc)
        return None


def extract_exif_data(
    image: Image.Image, *, include_gps: bool = False
) -> Dict[str, Any]:
    """
    Extract EXIF metadata from image

    Args:
        image: PIL Image object
        include_gps: When False (default) GPS/location tags are dropped so
            stored metadata cannot leak the photo's location.

    Returns:
        Dictionary of EXIF data
    """
    exif_data = {}

    try:
        # Get EXIF data
        exif = image.getexif()

        if exif is None:
            return exif_data

        # Parse EXIF tags
        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)

            # Convert bytes to string
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", errors="ignore")
                except Exception:
                    value = str(value)

            # Handle GPS info specially
            if tag == "GPSInfo":
                if not include_gps:
                    # Drop location data entirely.
                    continue
                gps_data = {}
                for gps_tag_id, gps_value in value.items():
                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                    gps_data[gps_tag] = str(gps_value)
                exif_data["GPSInfo"] = gps_data
            else:
                exif_data[tag] = str(value)

        return exif_data

    except Exception as e:
        logger.error(f"Failed to extract EXIF data: {e}")
        return {}
