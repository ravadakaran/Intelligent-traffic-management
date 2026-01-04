# detector.py
from ultralytics import YOLO
import cv2
import numpy as np

class TrafficDetector:
    def __init__(self, vehicle_model_path, ambulance_model_path):
        """
        Initializes the object detector with TWO YOLOv8 models.
        :param vehicle_model_path: Path to the standard vehicle model (e.g., 'yolov8n.pt')
        :param ambulance_model_path: Path to the custom ambulance model (e.g., 'best.pt')
        """
        # Load the standard model for general vehicles
        self.vehicle_model = YOLO(vehicle_model_path)
        # Load the custom-trained model for ambulances
        self.ambulance_model = YOLO(ambulance_model_path)

        # COCO class IDs for standard vehicles
        # (2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck')
        self.vehicle_classes = [2, 3, 5, 7]

        # Class ID for ambulance in your custom model
        # Based on your App.py, "Ambulance" is the first class (index 0)
        self.ambulance_class = [0] 
        
        print("Vehicle and Ambulance models loaded successfully.")

    def process_frame(self, frame):
        """
        Processes a single video frame with both models.
        :param frame: The video frame (numpy array).
        :return: A tuple containing:
                 - processed_frame: The frame with all bounding boxes drawn.
                 - density: The total count of all vehicles (including ambulances).
                 - ambulance_detected: Boolean, True if an ambulance is found.
        """
        
        # 1. Run detection for standard vehicles
        vehicle_results = self.vehicle_model(
            frame, 
            classes=self.vehicle_classes, 
            verbose=False
        )
        
        # Get the count and draw the boxes
        vehicle_count = len(vehicle_results[0].boxes)
        processed_frame = vehicle_results[0].plot() # This draws boxes on the frame

        # 2. Run detection for ambulances on the *same frame*
        ambulance_results = self.ambulance_model(
            frame, 
            classes=self.ambulance_class, 
            verbose=False
        )
        
        ambulance_count = len(ambulance_results[0].boxes)
        ambulance_detected = ambulance_count > 0
        
        # 3. Plot ambulance boxes ON TOP of the vehicle boxes
        # We pass 'processed_frame' (which already has vehicle boxes) to the plot()
        # function so it adds the new ambulance boxes to it.
        if ambulance_detected:
            processed_frame = ambulance_results[0].plot(img=processed_frame)

        # 4. Calculate total density
        total_density = vehicle_count + ambulance_count
        
        return processed_frame, total_density, ambulance_detected