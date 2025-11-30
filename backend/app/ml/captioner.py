"""
Image captioning using Florence-2
"""

import torch
from transformers import AutoProcessor, AutoModelForCausalLM
from PIL import Image
import numpy as np
from typing import Union
import logging

from app.core.config import settings
from app.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class ImageCaptioner:
    """Generate natural language captions for images using Florence-2"""

    def __init__(self):
        self.manager = get_model_manager()
        logger.info("ImageCaptioner initialized for model: microsoft/Florence-2-base")

    def _load_model(self):
        """Loader function for ModelManager"""
        model_id = "microsoft/Florence-2-base"
        logger.info(f"Loading Florence-2 model: {model_id}")

        device = "cuda" if settings.USE_GPU and torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if device == "cuda" else torch.float32

        model = AutoModelForCausalLM.from_pretrained(
            model_id, trust_remote_code=True, torch_dtype=torch_dtype
        ).to(device)

        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)

        return {
            "model": model,
            "processor": processor,
            "device": device,
            "dtype": torch_dtype,
        }

    def generate_caption(
        self,
        image: Union[Image.Image, np.ndarray],
        max_length: int = 1024,
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

            # Get model bundle
            bundle = self.manager.get_model("florence-2", self._load_model)
            model = bundle["model"]
            processor = bundle["processor"]
            device = bundle["device"]
            dtype = bundle["dtype"]

            # Florence-2 uses task prompts
            task_prompt = "<DETAILED_CAPTION>"

            inputs = processor(text=task_prompt, images=image, return_tensors="pt")
            inputs = {
                k: v.to(device, dtype)
                if v.dtype == torch.float32 or v.dtype == torch.float16
                else v.to(device)
                for k, v in inputs.items()
            }

            # Generate
            with torch.no_grad():
                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=max_length,
                    num_beams=num_beams,
                    do_sample=False,
                )

            generated_text = processor.batch_decode(
                generated_ids, skip_special_tokens=False
            )[0]

            # Post-process
            parsed_answer = processor.post_process_generation(
                generated_text, task=task_prompt, image_size=(image.width, image.height)
            )

            caption = parsed_answer.get(task_prompt, "")

            logger.info(f"Generated caption: {caption[:50]}...")
            return caption

        except Exception as e:
            logger.error(f"Failed to generate caption: {e}")
            raise

    def generate_conditional_caption(
        self, image: Union[Image.Image, np.ndarray], prompt: str, max_length: int = 1024
    ) -> str:
        """
        Generate caption conditioned on a text prompt (VQA style)
        """
        try:
            if isinstance(image, np.ndarray):
                image = Image.fromarray(image)

            if image.mode != "RGB":
                image = image.convert("RGB")

            bundle = self.manager.get_model("florence-2", self._load_model)
            model = bundle["model"]
            processor = bundle["processor"]
            device = bundle["device"]
            dtype = bundle["dtype"]

            # For VQA or specific prompts
            # For VQA or specific prompts
            # task_prompt = "<CAPTION>"  # Fallback or use prompt as VQA?
            # Florence-2 supports <VQA> prompt
            # If prompt is a question, use <VQA>
            # But for general conditional captioning, maybe just append?
            # Let's assume prompt is a question or task for now

            full_prompt = f"<VQA>{prompt}" if "?" in prompt else f"<CAPTION>{prompt}"

            inputs = processor(text=full_prompt, images=image, return_tensors="pt")
            inputs = {
                k: v.to(device, dtype)
                if v.dtype == torch.float32 or v.dtype == torch.float16
                else v.to(device)
                for k, v in inputs.items()
            }

            with torch.no_grad():
                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=max_length,
                    do_sample=False,
                )

            generated_text = processor.batch_decode(
                generated_ids, skip_special_tokens=False
            )[0]

            # We might need manual parsing if post_process doesn't handle custom prompts well
            # But let's try standard
            caption = processor.post_process_generation(
                generated_text, task="<CAPTION>", image_size=(image.width, image.height)
            )

            # If it returns dict
            if isinstance(caption, dict):
                caption = list(caption.values())[0]

            return str(caption)

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
