"""
Object detection using YOLOv8
"""
from ultralytics import YOLO
from PIL import Image
import numpy as np
from typing import List, Dict, Union
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class ObjectDetector:
    """Detect objects in images using YOLOv8"""
    
    def __init__(self):
        logger.info(f"Initializing YOLO model: {settings.YOLO_MODEL}")
        
        # Load YOLO model
        self.model = YOLO(settings.YOLO_MODEL)
        
        # Set device
        if settings.USE_GPU:
            self.model.to('cuda')
        
        logger.info("YOLO model loaded successfully")
    
    def detect(self, image: Union[Image.Image, np.ndarray], conf_threshold: float = 0.25) -> List[Dict]:
        """
        Detect objects in image
        
        Args:
            image: PIL Image or numpy array
            conf_threshold: Confidence threshold for detections
            
        Returns:
            List of detected objects with bounding boxes and labels
        """
        try:
            # Run inference
            results = self.model(image, conf=conf_threshold, verbose=False)
            
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
                    class_name = self.model.names[class_id]
                    
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
