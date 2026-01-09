import os
import cv2
import traceback
import sqlite3
import hashlib
from flask import (
    Flask, render_template, request, redirect,
    url_for, Response, jsonify, session, flash
)

from detector import TrafficDetector
from traffic_logic import TrafficLogic

# =====================================================
# PATHS & CONFIGURATION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "mkv"}
DATABASE = os.path.join(BASE_DIR, "users.db")

VEHICLE_MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.pt")
AMBULANCE_MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

# =====================================================
# FLASK APP
# =====================================================

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["SECRET_KEY"] = "your_super_secret_key_for_sessions"

# =====================================================
# DATABASE SETUP
# =====================================================

def setup_database():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    cursor.execute("SELECT * FROM users WHERE username=?", ("traffic-admin",))
    if cursor.fetchone() is None:
        password = "adminpassword"
        hashed = hashlib.sha256(password.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            ("traffic-admin", hashed)
        )

    conn.commit()
    conn.close()

# =====================================================
# GLOBAL STATE
# =====================================================

video_paths = {1: None, 2: None, 3: None, 4: None}
video_caps  = {1: None, 2: None, 3: None, 4: None}

try:
    detector = TrafficDetector(
        vehicle_model_path=VEHICLE_MODEL_PATH,
        ambulance_model_path=AMBULANCE_MODEL_PATH
    )
except Exception as e:
    print("YOLO model loading failed:", e)
    detector = None

traffic_manager = TrafficLogic()

# =====================================================
# HELPERS
# =====================================================

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def draw_ui_elements(frame, lane_id, density, ambulance, status):
    cv2.rectangle(frame, (10, 10), (70, 170), (40, 40, 40), -1)
    cv2.rectangle(frame, (10, 10), (70, 170), (255, 255, 255), 1)

    red    = (0, 0, 255) if status == "red" else (60, 60, 60)
    orange = (0, 165, 255) if status == "orange" else (60, 60, 60)
    green  = (0, 255, 0) if status == "green" else (60, 60, 60)

    cv2.circle(frame, (40, 40), 20, red, -1)
    cv2.circle(frame, (40, 90), 20, orange, -1)
    cv2.circle(frame, (40, 140), 20, green, -1)

    cv2.putText(frame, f"Lane {lane_id}", (10, 200),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
    cv2.putText(frame, f"Density: {density}", (10, 230),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)

    if ambulance:
        cv2.putText(frame, "AMBULANCE!",
                    (10, 260),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0,0,255), 2)

    return frame


def generate_frames(lane_id):
    global video_caps

    path = video_paths.get(lane_id)
    if not path:
        return

    if video_caps[lane_id] is None:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return
        video_caps[lane_id] = cap

    cap = video_caps[lane_id]

    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue

            if detector:
                frame, ambulance, counts = detector.process_frame(frame)
                density = sum(counts.values())
            else:
                ambulance = False
                density = 0
                counts = {}

            traffic_manager.update_lane_data(
                lane_id, density, ambulance, counts
            )

            state = traffic_manager.get_system_state()
            status = state[lane_id]["status"]

            frame = draw_ui_elements(
                frame, lane_id, density, ambulance, status
            )

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes() +
                b"\r\n"
            )

        except Exception:
            traceback.print_exc()
            break

# =====================================================
# ROUTES
# =====================================================

@app.route("/", methods=["GET", "POST"])
def login():
    if "logged_in" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        user = request.form["username"]
        pwd  = hashlib.sha256(request.form["password"].encode()).hexdigest()

        conn = sqlite3.connect(DATABASE)
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (user, pwd)
        )
        ok = cur.fetchone()
        conn.close()

        if ok:
            session["logged_in"] = True
            session["username"] = user
            return redirect(url_for("home"))
        else:
            flash("Invalid credentials", "danger")

    return render_template("login.html")


@app.route("/home")
def home():
    if "logged_in" not in session:
        return redirect(url_for("login"))
    return render_template("project_home.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    if "logged_in" not in session:
        return redirect(url_for("login"))

    global video_caps

    if request.method == "POST":
        video_caps = {1: None, 2: None, 3: None, 4: None}

        for i in range(1, 5):
            f = request.files.get(f"video{i}")
            if not f or f.filename == "" or not allowed_file(f.filename):
                continue

            ext = f.filename.rsplit(".", 1)[1]
            filename = f"lane_{i}.{ext}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)

            f.save(save_path)
            video_paths[i] = save_path

        return redirect(url_for("dashboard"))

    return render_template("upload.html")


@app.route("/dashboard")
def dashboard():
    if "logged_in" not in session:
        return redirect(url_for("login"))
    if not all(video_paths.values()):
        return redirect(url_for("upload_page"))
    return render_template("dashboard.html")


@app.route("/analysis")
def analysis_page():
    if "logged_in" not in session:
        return redirect(url_for("login"))
    return render_template("analysis.html")


@app.route("/video_feed/<int:lane_id>")
def video_feed(lane_id):
    if "logged_in" not in session:
        return "Unauthorized", 401
    return Response(
        generate_frames(lane_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status_api")
def status_api():
    return jsonify(traffic_manager.get_system_state())


@app.route("/api/analysis_data")
def analysis_data():
    return jsonify(traffic_manager.get_analysis_data())

# =====================================================
# APP ENTRY POINT (RAILWAY SAFE)
# =====================================================

if __name__ == "__main__":
    setup_database()

    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
