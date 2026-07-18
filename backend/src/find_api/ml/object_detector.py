"""
Object detection using Ultralytics YOLO
"""

from ultralytics import YOLO
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging

from find_api.core.config import settings
from find_api.core.hardware import current_torch_device
from find_api.core.model_manager import get_model_manager
from find_api.core.runtime_profile import current_accel_mode

logger = logging.getLogger(__name__)


class ObjectDetector:
    """Detect objects in images using Ultralytics YOLO"""

    def __init__(self):
        self.manager = get_model_manager()
        # We don't load here anymore, we load on demand via manager
        logger.info(f"ObjectDetector initialized for model: {settings.YOLO_MODEL}")

    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info(f"Loading YOLO model: {settings.YOLO_MODEL}")
        model = YOLO(settings.YOLO_MODEL)  # Auto-downloads from Ultralytics
        device = current_torch_device()
        if device != "cpu":
            model.to(device)
        return model

    def detect(
        self, image: Union[Image.Image, np.ndarray], conf_threshold: float = 0.25
    ) -> List[Dict]:
        """
        Detect objects in image
        """
        try:
            config_key = (
                f"model={settings.YOLO_MODEL}|accel={current_accel_mode()}|"
                f"half={settings.YOLO_HALF}"
            )
            with self.manager.use_model(
                "yolo", self._load_model, config_key=config_key
            ) as model:
                # Run inference
                # Note: In a single-worker setup, we don't strictly need the lock for safety,
                # but we use it to ensure we don't accidentally run multiple GPU tasks if threaded.
                # Since this is synchronous code called from a thread/process, we can't easily use
                # the async lock here without an event loop.
                # For now, we rely on the single-worker architecture for serialization.

                device = current_torch_device()
                use_cuda = device == "cuda"
                results = model(
                    image,
                    conf=conf_threshold,
                    verbose=False,
                    device=0 if use_cuda else (device if device != "cpu" else None),
                    half=use_cuda and settings.YOLO_HALF,
                )

            detections = []

            for result in results:
                boxes = result.boxes

                for i in range(len(boxes)):
                    box = boxes[i]

                    # Get box coordinates
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                    # Get class and confidence
                    class_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    class_name = model.names[class_id]

                    detection = {
                        "class": class_name,
                        "confidence": confidence,
                        "bbox": {
                            "x1": float(x1),
                            "y1": float(y1),
                            "x2": float(x2),
                            "y2": float(y2),
                        },
                    }

                    detections.append(detection)

            logger.info(f"Detected {len(detections)} objects")
            return detections

        except Exception as e:
            logger.error(f"Failed to detect objects: {e}")
            raise


# Global instance
_object_detector = None


def get_object_detector() -> ObjectDetector:
    """Get or create global object detector instance"""
    global _object_detector
    if _object_detector is None:
        _object_detector = ObjectDetector()
    return _object_detector
