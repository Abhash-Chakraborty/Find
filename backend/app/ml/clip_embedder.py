"""
CLIP embedding generation using OpenCLIP
"""
import torch
import open_clip
from PIL import Image
import numpy as np
from typing import Union, List
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class CLIPEmbedder:
    """Generate CLIP embeddings for images and text"""
    
    def __init__(self):
        self.device = "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        logger.info(f"Initializing CLIP on device: {self.device}")
        
        # Load CLIP model
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            settings.CLIP_MODEL,
            pretrained=settings.CLIP_PRETRAINED,
            device=self.device
        )
        
        self.tokenizer = open_clip.get_tokenizer(settings.CLIP_MODEL)
        self.model.eval()
        
        logger.info(f"CLIP model loaded: {settings.CLIP_MODEL}")
    
    def embed_image(self, image: Union[Image.Image, np.ndarray]) -> np.ndarray:
        """
        Generate embedding for a single image
        
        Args:
            image: PIL Image or numpy array
            
        Returns:
            Normalized embedding vector
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            # Preprocess and convert to tensor
            image_input = self.preprocess(image).unsqueeze(0).to(self.device)
            
            # Generate embedding
            with torch.no_grad():
                embedding = self.model.encode_image(image_input)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            return embedding.cpu().numpy()[0]
        
        except Exception as e:
            logger.error(f"Failed to generate image embedding: {e}")
            raise
    
    def embed_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Generate embedding for text query
        
        Args:
            text: Single text string or list of strings
            
        Returns:
            Normalized embedding vector(s)
        """
        try:
            # Tokenize text
            if isinstance(text, str):
                text = [text]
            
            text_input = self.tokenizer(text).to(self.device)
            
            # Generate embedding
            with torch.no_grad():
                embedding = self.model.encode_text(text_input)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            result = embedding.cpu().numpy()
            return result[0] if len(text) == 1 else result
        
        except Exception as e:
            logger.error(f"Failed to generate text embedding: {e}")
            raise
    
    def compute_similarity(self, image_embedding: np.ndarray, text_embedding: np.ndarray) -> float:
        """
        Compute cosine similarity between image and text embeddings
        
        Args:
            image_embedding: Image embedding vector
            text_embedding: Text embedding vector
            
        Returns:
            Similarity score (0-1)
        """
        return float(np.dot(image_embedding, text_embedding))


# Global instance
_clip_embedder = None


def get_clip_embedder() -> CLIPEmbedder:
    """Get or create global CLIP embedder instance"""
    global _clip_embedder
    if _clip_embedder is None:
        _clip_embedder = CLIPEmbedder()
    return _clip_embedder
