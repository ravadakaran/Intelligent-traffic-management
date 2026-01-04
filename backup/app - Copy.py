# app.py
import os
import cv2
from flask import Flask, render_template, request, redirect, url_for, Response, jsonify
from detector import TrafficDetector  # <-- Import your two-model class
from traffic_logic import TrafficLogic

# --- Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = 'your_secret_key_here' 

# --- Global Variables ---
video_paths = { 1: None, 2: None, 3: None, 4: None }
video_caps = { 1: None, 2: None, 3: None, 4: None }

# --- Initialize Detector and Logic ---
try:
    # *** THIS IS THE MAIN CHANGE ***
    # Load both models. 'yolov8n.pt' will be auto-downloaded.
    detector = TrafficDetector(
        vehicle_model_path='yolov8n.pt',
        ambulance_model_path='best.pt' # Your custom model
    )
except Exception as e:
    print(f"Error loading YOLO models: {e}")
    print("Please make sure 'best.pt' is in the project directory.")
    detector = None

traffic_manager = TrafficLogic()

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def draw_ui_elements(frame, lane_id, density, ambulance, status):
    """Draws the traffic light status and info on the frame."""
    
    # Draw Traffic Light (as in your reference image)
    cv2.rectangle(frame, (10, 10), (70, 170), (50, 50, 50), -1) 
    cv2.rectangle(frame, (10, 10), (70, 170), (255, 255, 255), 1)
    cv2.circle(frame, (40, 40), 20, (0,0,255) if status=='red' else (40,40,40), -1) 
    cv2.circle(frame, (40, 90), 20, (40,40,40), -1) # Yellow
    cv2.circle(frame, (40, 140), 20, (0,255,0) if status=='green' else (40,40,40), -1) 
    
    # Draw Info Text
    cv2.putText(frame, f"Lane: {lane_id}", (10, 200), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(frame, f"Density: {density}", (10, 230), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    if ambulance:
        cv2.putText(frame, "AMBULANCE!", (10, 260), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    
    return frame

# --- Video Streaming Generator (No changes inside, but uses new detector) ---
def generate_frames(lane_id):
    global video_caps
    
    video_path = video_paths.get(lane_id)
    if not video_path: return

    if video_caps[lane_id] is None:
        video_caps[lane_id] = cv2.VideoCapture(video_path)
        if not video_caps[lane_id].isOpened():
            print(f"Error opening video file: {video_path}")
            return
            
    cap = video_caps[lane_id]

    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        
        if detector:
            # This single call now runs BOTH models
            processed_frame, density, ambulance = detector.process_frame(frame)
        else:
            processed_frame, density, ambulance = frame, 0, False
            cv2.putText(processed_frame, "YOLO Models Not Loaded", (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

        traffic_manager.update_lane_data(lane_id, density, ambulance)
        current_state = traffic_manager.get_system_state()
        lane_status = current_state[lane_id]['status']

        final_frame = draw_ui_elements(processed_frame, lane_id, density, ambulance, lane_status)
        
        (flag, encodedImage) = cv2.imencode(".jpg", final_frame)
        if not flag:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')

# --- Flask Routes (No Changes) ---
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_page():
    global video_paths, video_caps
    if request.method == 'POST':
        video_caps = {1: None, 2: None, 3: None, 4: None}
        
        for i in range(1, 5):
            file_key = f'video{i}'
            if file_key not in request.files: continue
            
            file = request.files[file_key]
            if file.filename == '' or not allowed_file(file.filename): continue
                
            filename = f'lane_{i}.' + file.filename.rsplit('.', 1)[1].lower()
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            video_paths[i] = save_path
            
        return redirect(url_for('dashboard'))
        
    return render_template('upload.html')

@app.route('/dashboard')
def dashboard():
    if not all(video_paths.values()):
        return redirect(url_for('upload_page'))
    return render_template('dashboard.html')

@app.route('/video_feed/<int:lane_id>')
def video_feed(lane_id):
    if lane_id not in [1, 2, 3, 4]:
        return "Invalid Lane ID", 404
    return Response(generate_frames(lane_id),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/status_api')
def status_api():
    return jsonify(traffic_manager.get_system_state())

# --- Run Application ---
if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(debug=True, host='0.0.0.0', threaded=True)