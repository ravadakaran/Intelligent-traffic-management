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
        # Load models
        self.vehicle_model = YOLO(vehicle_model_path)
        self.ambulance_model = YOLO(ambulance_model_path)

        # --- Vehicle Model Config ---
        # COCO class IDs for standard vehicles
        # (2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck')
        self.vehicle_model.classes_to_detect = [2, 3, 5, 7] 
        self.vehicle_class_names = {
            2: 'Car',
            3: 'Motorcycle',
            5: 'Bus',
            7: 'Truck'
        }
        
        # --- Ambulance Model Config ---
        # Based on your App.py, "Ambulance" is the first class (index 0)
        self.ambulance_model.classes_to_detect = [0]
        self.ambulance_class_names = {
            0: 'Ambulance'
        }
        
        # --- NEW 70% THRESHOLD ---
        self.ambulance_threshold = 0.70
        
        # --- Plotting Config (Adapted from your App.py) ---
        all_names = list(self.vehicle_class_names.values()) + list(self.ambulance_class_names.values())
        self.colors = np.random.uniform(0, 255, size=(len(all_names), 3))
        self.class_name_to_color_index = {name: i for i, name in enumerate(all_names)}

        print("Vehicle and Ambulance models loaded successfully.")
        print(f"Ambulance detection threshold set to {self.ambulance_threshold * 100}%")

    # --- Helper functions adapted from your App.py ---
    def yolo2bbox(self, bboxes):
        """Converts YOLO format to [xmin, ymin, xmax, ymax]"""
        xmin, ymin = bboxes[0] - bboxes[2] / 2, bboxes[1] - bboxes[3] / 2
        xmax, ymax = bboxes[0] + bboxes[2] / 2, bboxes[1] + bboxes[3] / 2
        return xmin, ymin, xmax, ymax

    def plot_box(self, image, bboxes, labels):
        """Draws boxes and labels on the image."""
        h, w, _ = image.shape
        for box_num, box in enumerate(bboxes):
            x1, y1, x2, y2 = self.yolo2bbox(box)
            xmin, ymin, xmax, ymax = int(x1 * w), int(y1 * h), int(x2 * w), int(y2 * h)
            
            class_name = labels[box_num] # Label is now the class name string

            # Get color for this class
            color = self.colors[self.class_name_to_color_index[class_name]]

            cv2.rectangle(
                image,
                (xmin, ymin),
                (xmax, ymax),
                color=color,
                thickness=2,
            )

            font_scale = min(1, max(3, int(w / 500)))
            font_thickness = min(2, max(10, int(w / 50)))
            
            cv2.putText(
                image,
                class_name,
                (xmin + 1, ymin - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (255, 255, 255), # White text
                font_thickness,
            )
        return image
    # --- End of helper functions ---
    
    def process_frame(self, frame):
        """
        Processes a single video frame with both models.
        :param frame: The video frame (numpy array).
        :return: A tuple containing:
                 - processed_frame: The frame with filtered boxes drawn.
                 - density: The total count of valid vehicles.
                 - ambulance_detected: Boolean, True if ambulance > 70% conf is found.
        """
        
        # Lists to hold all valid detections for plotting
        bboxes_to_plot = []
        labels_to_plot = []
        
        vehicle_count = 0
        ambulance_count = 0
        ambulance_detected = False
        frame_height, frame_width = frame.shape[:2]

        # 1. Run detection for standard vehicles
        vehicle_results = self.vehicle_model(
            frame, 
            classes=self.vehicle_model.classes_to_detect, 
            verbose=False
        )
        
        for det in vehicle_results[0].boxes:
            vehicle_count += 1
            # Add to plot list
            cls = int(det.cls[0].item())
            xywh = det.xywh[0].cpu().numpy()
            bboxes_to_plot.append([
                xywh[0] / frame_width, xywh[1] / frame_height,
                xywh[2] / frame_width, xywh[3] / frame_height
            ])
            labels_to_plot.append(self.vehicle_class_names[cls])

        # 2. Run detection for ambulances
        ambulance_results = self.ambulance_model(
            frame, 
            classes=self.ambulance_model.classes_to_detect, 
            verbose=False
        )
        
        # --- MODIFIED AMBULANCE LOGIC WITH 70% THRESHOLD ---
        for det in ambulance_results[0].boxes:
            conf = det.conf[0].item() # Get the confidence score
            
            # Check if confidence is above the threshold
            if conf >= self.ambulance_threshold:
                ambulance_detected = True
                ambulance_count += 1
                
                # Add to plot list
                cls = int(det.cls[0].item())
                xywh = det.xywh[0].cpu().numpy()
                bboxes_to_plot.append([
                    xywh[0] / frame_width, xywh[1] / frame_height,
                    xywh[2] / frame_width, xywh[3] / frame_height
                ])
                labels_to_plot.append(self.ambulance_class_names[cls])
        # --- END OF MODIFIED LOGIC ---

        # 3. Plot all valid boxes
        # We pass the original 'frame' and draw all boxes at once
        processed_frame = self.plot_box(frame, bboxes_to_plot, labels_to_plot)

        # 4. Calculate total density (all valid vehicles + all valid ambulances)
        total_density = vehicle_count + ambulance_count
        
        return processed_frame, total_density, ambulance_detected