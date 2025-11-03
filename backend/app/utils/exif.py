"""
Extract EXIF data from images
"""
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def extract_exif_data(image: Image.Image) -> Dict[str, Any]:
    """
    Extract EXIF metadata from image
    
    Args:
        image: PIL Image object
        
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
                    value = value.decode('utf-8', errors='ignore')
                except:
                    value = str(value)
            
            # Handle GPS info specially
            if tag == "GPSInfo":
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
