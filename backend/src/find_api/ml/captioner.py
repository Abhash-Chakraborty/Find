"""Local image captioning using the native BLIP model implementation."""

import torch
from transformers import BlipForConditionalGeneration, BlipProcessor
from PIL import Image
import numpy as np
from typing import Union
import logging

from find_api.core.config import settings
from find_api.core.hardware import current_torch_device
from find_api.core.model_manager import get_model_manager
from find_api.core.runtime_profile import current_accel_mode

logger = logging.getLogger(__name__)


class ImageCaptioner:
    """Generate natural-language captions with a local BLIP checkpoint."""

    def __init__(self):
        self.manager = get_model_manager()
        logger.info("ImageCaptioner initialized for model: %s", settings.BLIP_MODEL)

    def _load_model(self):
        """Loader function for ModelManager"""
        model_id = settings.BLIP_MODEL
        logger.info("Loading BLIP caption model: %s", model_id)

        device = current_torch_device()
        torch_dtype = torch.float16 if device == "cuda" else torch.float32

        model = BlipForConditionalGeneration.from_pretrained(
            model_id,
            trust_remote_code=False,
            dtype=torch_dtype,
        ).to(device)
        processor = BlipProcessor.from_pretrained(
            model_id,
            trust_remote_code=False,
            use_fast=False,
        )

        return {
            "model": model,
            "processor": processor,
            "device": device,
            "dtype": torch_dtype,
        }

    def generate_caption(
        self,
        image: Union[Image.Image, np.ndarray],
        max_length: int = 256,
        num_beams: int = 3,
    ) -> str:
        """
        Generate detailed caption for image
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)

            if image.mode != "RGB":
                image = image.convert("RGB")

            config_key = f"model={settings.BLIP_MODEL}|accel={current_accel_mode()}"
            with self.manager.use_model(
                "captioner", self._load_model, config_key=config_key
            ) as bundle:
                model = bundle["model"]
                processor = bundle["processor"]
                device = bundle["device"]
                dtype = bundle["dtype"]

                inputs = processor(images=image, return_tensors="pt")
                inputs = {
                    k: v.to(device, dtype)
                    if v.dtype == torch.float32 or v.dtype == torch.float16
                    else v.to(device)
                    for k, v in inputs.items()
                }

                # Generate
                with torch.inference_mode():
                    generated_ids = model.generate(
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=max_length,
                        num_beams=num_beams,
                        do_sample=False,
                        use_cache=True,
                    )

                caption = processor.decode(
                    generated_ids[0], skip_special_tokens=True
                ).strip()

            logger.info(f"Generated caption: {caption[:50]}...")
            return caption

        except Exception as e:
            logger.error(f"Failed to generate caption: {e}")
            raise

    def generate_conditional_caption(
        self, image: Union[Image.Image, np.ndarray], prompt: str, max_length: int = 256
    ) -> str:
        """
        Generate caption conditioned on a text prompt (VQA style)
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)

            if image.mode != "RGB":
                image = image.convert("RGB")

            config_key = f"model={settings.BLIP_MODEL}|accel={current_accel_mode()}"
            with self.manager.use_model(
                "captioner", self._load_model, config_key=config_key
            ) as bundle:
                model = bundle["model"]
                processor = bundle["processor"]
                device = bundle["device"]
                dtype = bundle["dtype"]

                inputs = processor(text=prompt, images=image, return_tensors="pt")
                inputs = {
                    k: v.to(device, dtype)
                    if v.dtype == torch.float32 or v.dtype == torch.float16
                    else v.to(device)
                    for k, v in inputs.items()
                }

                with torch.inference_mode():
                    generated_ids = model.generate(
                        input_ids=inputs["input_ids"],
                        pixel_values=inputs["pixel_values"],
                        max_new_tokens=max_length,
                        do_sample=False,
                        use_cache=True,
                    )

                return processor.decode(
                    generated_ids[0], skip_special_tokens=True
                ).strip()

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
