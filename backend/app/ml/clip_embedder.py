"""
CLIP embedding generation using SigLIP
"""
import torch
import open_clip
from PIL import Image
import numpy as np
from typing import Union, List
import logging

from app.core.config import settings
from app.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class CLIPEmbedder:
    """Generate SigLIP embeddings for images and text"""
    
    def __init__(self):
        self.manager = get_model_manager()
        logger.info("CLIPEmbedder initialized for model: ViT-B-16-SigLIP")
    
    def _load_model(self):
        """Loader function for ModelManager"""
        model_name = "ViT-B-16-SigLIP"
        pretrained = "webli"
        logger.info(f"Loading SigLIP model: {model_name}")
        
        device = "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name,
            pretrained=pretrained,
            device=device
        )
        
        tokenizer = open_clip.get_tokenizer(model_name)
        model.eval()
        
        return {"model": model, "preprocess": preprocess, "tokenizer": tokenizer, "device": device}
    
    def embed_image(self, image: Union[Image.Image, np.ndarray]) -> np.ndarray:
        """
        Generate embedding for a single image
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)
            
            bundle = self.manager.get_model("siglip", self._load_model)
            model = bundle["model"]
            preprocess = bundle["preprocess"]
            device = bundle["device"]
            
            # Preprocess and convert to tensor
            image_input = preprocess(image).unsqueeze(0).to(device)
            
            # Generate embedding
            with torch.no_grad():
                embedding = model.encode_image(image_input)
                embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            
            # Convert to numpy
            return embedding.cpu().numpy()[0]
        
        except Exception as e:
            logger.error(f"Failed to generate image embedding: {e}")
            raise
    
    def embed_text(self, text: Union[str, List[str]]) -> np.ndarray:
        """
        Generate embedding for text query
        """
        try:
            bundle = self.manager.get_model("siglip", self._load_model)
            model = bundle["model"]
            tokenizer = bundle["tokenizer"]
            device = bundle["device"]
            
            # Tokenize text
            if isinstance(text, str):
                text = [text]
            
            text_input = tokenizer(text).to(device)
            
            # Generate embedding
            with torch.no_grad():
                embedding = model.encode_text(text_input)
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
