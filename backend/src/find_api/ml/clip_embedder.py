"""
CLIP embedding generation using SigLIP
"""

import torch
import open_clip
from PIL import Image
import numpy as np
from typing import Union, List
import logging

from find_api.core.config import settings
from find_api.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class CLIPEmbedder:
    """Generate SigLIP embeddings for images and text"""

    def __init__(self):
        self.manager = get_model_manager()
        logger.info("CLIPEmbedder initialized for model: %s", settings.CLIP_MODEL)

    def _load_model(self):
        """Loader function for ModelManager"""
        model_name = settings.CLIP_MODEL
        pretrained = settings.CLIP_PRETRAINED
        logger.info("Loading SigLIP model: %s (%s)", model_name, pretrained)

        device = "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"

        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained, device=device
        )

        tokenizer = open_clip.get_tokenizer(model_name)
        model.eval()

        return {
            "model": model,
            "preprocess": preprocess,
            "tokenizer": tokenizer,
            "device": device,
        }

    def _config_key(self) -> str:
        return (
            f"model={settings.CLIP_MODEL}|pretrained={settings.CLIP_PRETRAINED}|"
            f"gpu={settings.USE_GPU}"
        )

    def embed_image(self, image: Union[Image.Image, np.ndarray]) -> np.ndarray:
        """
        Generate embedding for a single image
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)

            with self.manager.use_model(
                "siglip", self._load_model, config_key=self._config_key()
            ) as bundle:
                model = bundle["model"]
                preprocess = bundle["preprocess"]
                device = bundle["device"]

                # Preprocess and convert to tensor
                image_input = preprocess(image).unsqueeze(0).to(device)

                # Generate embedding
                with (
                    torch.inference_mode(),
                    torch.autocast(
                        device_type="cuda",
                        dtype=torch.float16,
                        enabled=device == "cuda",
                    ),
                ):
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
            with self.manager.use_model(
                "siglip", self._load_model, config_key=self._config_key()
            ) as bundle:
                model = bundle["model"]
                tokenizer = bundle["tokenizer"]
                device = bundle["device"]

                # Tokenize text
                if isinstance(text, str):
                    text = [text]

                text_input = tokenizer(text).to(device)

                # Generate embedding
                with (
                    torch.inference_mode(),
                    torch.autocast(
                        device_type="cuda",
                        dtype=torch.float16,
                        enabled=device == "cuda",
                    ),
                ):
                    embedding = model.encode_text(text_input)
                    embedding = embedding / embedding.norm(dim=-1, keepdim=True)

            # Convert to numpy
            result = embedding.cpu().numpy()
            return result[0] if len(text) == 1 else result

        except Exception as e:
            logger.error(f"Failed to generate text embedding: {e}")
            raise

    def compute_similarity(
        self, image_embedding: np.ndarray, text_embedding: np.ndarray
    ) -> float:
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
