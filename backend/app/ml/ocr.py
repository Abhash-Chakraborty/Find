"""
OCR (Optical Character Recognition) using Tesseract
"""
import pytesseract
from PIL import Image
import numpy as np
from typing import Union, Dict, List
import logging

logger = logging.getLogger(__name__)


class OCRExtractor:
    """Extract text from images using Tesseract OCR"""
    
    def __init__(self):
        logger.info("Initializing OCR extractor")
        # Tesseract should be installed system-wide
        # On Docker: apt-get install tesseract-ocr
    
    def extract_text(self, image: Union[Image.Image, np.ndarray], lang: str = 'eng') -> str:
        """
        Extract text from image
        
        Args:
            image: PIL Image or numpy array
            lang: Language code (default: English)
            
        Returns:
            Extracted text
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Extract text
            text = pytesseract.image_to_string(image, lang=lang)
            text = text.strip()
            
            if text:
                logger.info(f"Extracted {len(text)} characters")
            else:
                logger.info("No text detected")
            
            return text
        
        except Exception as e:
            logger.error(f"Failed to extract text: {e}")
            return ""
    
    def extract_text_with_boxes(
        self, 
        image: Union[Image.Image, np.ndarray], 
        lang: str = 'eng'
    ) -> List[Dict]:
        """
        Extract text with bounding boxes
        
        Args:
            image: PIL Image or numpy array
            lang: Language code
            
        Returns:
            List of text blocks with bounding boxes
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Get detailed OCR data
            data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)
            
            text_blocks = []
            n_boxes = len(data['text'])
            
            for i in range(n_boxes):
                text = data['text'][i].strip()
                if text:  # Only include non-empty text
                    block = {
                        "text": text,
                        "confidence": float(data['conf'][i]),
                        "bbox": {
                            "x": int(data['left'][i]),
                            "y": int(data['top'][i]),
                            "width": int(data['width'][i]),
                            "height": int(data['height'][i])
                        }
                    }
                    text_blocks.append(block)
            
            logger.info(f"Extracted {len(text_blocks)} text blocks")
            return text_blocks
        
        except Exception as e:
            logger.error(f"Failed to extract text with boxes: {e}")
            return []


# Global instance
_ocr_extractor = None


def get_ocr_extractor() -> OCRExtractor:
    """Get or create global OCR extractor instance"""
    global _ocr_extractor
    if _ocr_extractor is None:
        _ocr_extractor = OCRExtractor()
    return _ocr_extractor
