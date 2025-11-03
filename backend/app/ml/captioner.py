"""
Image captioning using BLIP
"""
import torch
from transformers import BlipProcessor, BlipForConditionalGeneration
from PIL import Image
import numpy as np
from typing import Union
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ImageCaptioner:
    """Generate natural language captions for images using BLIP"""
    
    def __init__(self):
        self.device = "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        logger.info(f"Initializing BLIP on device: {self.device}")
        
        # Load BLIP model and processor
        self.processor = BlipProcessor.from_pretrained(settings.BLIP_MODEL)
        self.model = BlipForConditionalGeneration.from_pretrained(settings.BLIP_MODEL).to(self.device)
        
        logger.info(f"BLIP model loaded: {settings.BLIP_MODEL}")
    
    def generate_caption(
        self, 
        image: Union[Image.Image, np.ndarray],
        max_length: int = 50,
        num_beams: int = 4
    ) -> str:
        """
        Generate caption for image
        
        Args:
            image: PIL Image or numpy array
            max_length: Maximum caption length
            num_beams: Number of beams for beam search
            
        Returns:
            Generated caption
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Convert to RGB if needed
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Process image
            inputs = self.processor(image, return_tensors="pt").to(self.device)
            
            # Generate caption
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_length=max_length,
                    num_beams=num_beams
                )
            
            # Decode caption
            caption = self.processor.decode(outputs[0], skip_special_tokens=True)
            
            logger.info(f"Generated caption: {caption}")
            return caption
        
        except Exception as e:
            logger.error(f"Failed to generate caption: {e}")
            raise
    
    def generate_conditional_caption(
        self,
        image: Union[Image.Image, np.ndarray],
        prompt: str,
        max_length: int = 50
    ) -> str:
        """
        Generate caption conditioned on a text prompt
        
        Args:
            image: PIL Image or numpy array
            prompt: Text prompt to condition on
            max_length: Maximum caption length
            
        Returns:
            Generated caption
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Process with prompt
            inputs = self.processor(image, prompt, return_tensors="pt").to(self.device)
            
            # Generate
            with torch.no_grad():
                outputs = self.model.generate(**inputs, max_length=max_length)
            
            caption = self.processor.decode(outputs[0], skip_special_tokens=True)
            
            return caption
        
        except Exception as e:
            logger.error(f"Failed to generate conditional caption: {e}")
            raise


# Global instance
_image_captioner = None


def get_image_captioner() -> ImageCaptioner:
    """Get or create global image captioner instance"""
    global _image_captioner
    if _image_captioner is None:
        _image_captioner = ImageCaptioner()
    return _image_captioner
