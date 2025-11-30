"""
Object detection using YOLOv10
"""
from ultralytics import YOLO
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging
import asyncio

from app.core.config import settings
from app.core.model_manager import get_model_manager

logger = logging.getLogger(__name__)


class ObjectDetector:
    """Detect objects in images using YOLOv10"""
    
    def __init__(self):
        self.manager = get_model_manager()
        # We don't load here anymore, we load on demand via manager
        logger.info(f"ObjectDetector initialized for model: yolov10b.pt")
    
    def _load_model(self):
        """Loader function for ModelManager"""
        logger.info(f"Loading YOLO model: yolov10b.pt")
        model = YOLO("yolov10b.pt")  # Auto-downloads from Ultralytics
        if settings.USE_GPU:
            model.to('cuda')
        return model
    
    def detect(self, image: Union[Image.Image, np.ndarray], conf_threshold: float = 0.25) -> List[Dict]:
        """
        Detect objects in image
        """
        try:
            # Get model from manager
            model = self.manager.get_model("yolov10", self._load_model)
            
            # Run inference
            # Note: In a single-worker setup, we don't strictly need the lock for safety,
            # but we use it to ensure we don't accidentally run multiple GPU tasks if threaded.
            # Since this is synchronous code called from a thread/process, we can't easily use 
            # the async lock here without an event loop.
            # For now, we rely on the single-worker architecture for serialization.
            
            results = model(image, conf=conf_threshold, verbose=False)
            
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
                            "y2": float(y2)
                        }
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
