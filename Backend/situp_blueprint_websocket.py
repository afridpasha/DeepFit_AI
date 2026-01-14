from flask import Blueprint, render_template, jsonify, request, session
from flask_socketio import emit
from error_logger import log_error, log_warning, log_info
from session_manager import get_current_user
from db_config import get_db
import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import json
import os
import base64
from datetime import datetime
from pathlib import Path
from bson import ObjectId

situp_bp = Blueprint('situp', __name__,
                    template_folder='templates',
                    static_folder='static',
                    url_prefix='/situp')

SITUP_DURATION = 180
RESULTS_DIR = Path("validation_results/Exercises/Situps")

is_recording = False
session_active = False
session_completed = False
start_time = None
timer_thread = None
exercise_stats = {
    'reps': 0,
    'feedback': 'Get Ready',
    'exercise': 'situps',
    'form_percentage': 0,
    'elapsed_time': 0,
    'remaining_time': SITUP_DURATION
}

class SitupsCounter:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        # Optimize MediaPipe settings for speed
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=0,  # Changed from default to 0 (fastest)
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.count = 0
        self.stage = None
        self.feedback = "Get Ready"
        
    def calculate_angle(self, a, b, c):
        a = np.array(a)
        b = np.array(b)
        c = np.array(c)
        radians = np.arctan2(c[1]-b[1], c[0]-b[0]) - np.arctan2(a[1]-b[1], a[0]-b[0])
        angle = np.abs(radians*180.0/np.pi)
        if angle > 180.0:
            angle = 360-angle
        return angle
    
    def detect_situps(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        
        if results.pose_landmarks:
            landmarks = results.pose_landmarks.landmark
            
            try:
                left_shoulder = [landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value].x,
                               landmarks[self.mp_pose.PoseLandmark.LEFT_SHOULDER.value].y]
                left_hip = [landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value].x,
                          landmarks[self.mp_pose.PoseLandmark.LEFT_HIP.value].y]
                left_knee = [landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value].x,
                           landmarks[self.mp_pose.PoseLandmark.LEFT_KNEE.value].y]
                
                right_shoulder = [landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value].x,
                                landmarks[self.mp_pose.PoseLandmark.RIGHT_SHOULDER.value].y]
                right_hip = [landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value].x,
                           landmarks[self.mp_pose.PoseLandmark.RIGHT_HIP.value].y]
                right_knee = [landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value].x,
                            landmarks[self.mp_pose.PoseLandmark.RIGHT_KNEE.value].y]
                
                left_angle = self.calculate_angle(left_shoulder, left_hip, left_knee)
                right_angle = self.calculate_angle(right_shoulder, right_hip, right_knee)
                angle = (left_angle + right_angle) / 2
                
                if angle > 150:
                    if self.stage != "down":
                        self.stage = "down"
                        self.feedback = "Go Up!"
                elif angle < 100 and self.stage == "down":
                    global exercise_stats
                    if exercise_stats.get('remaining_time', 180) > 0:
                        self.stage = "up"
                        self.count += 1
                        self.feedback = f"Rep {self.count}! Go Down"
                    else:
                        self.feedback = "Time's up! Stop exercising"
                elif self.stage == "down" and 100 <= angle <= 150:
                    self.feedback = "Keep Going Up!"
                elif self.stage == "up" and 100 <= angle <= 150:
                    self.feedback = "Go Down Slowly"
                
                self.mp_draw.draw_landmarks(
                    frame, results.pose_landmarks, self.mp_pose.POSE_CONNECTIONS,
                    self.mp_draw.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                    self.mp_draw.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                )
                
                h, w, _ = frame.shape
                cv2.putText(frame, f'Count: {self.count}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(frame, self.feedback, (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
                cv2.putText(frame, f'Angle: {int(angle)}°', (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                
            except Exception as e:
                self.feedback = "Position yourself properly"
        else:
            self.feedback = "No pose detected"
            cv2.putText(frame, self.feedback, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        return frame
    
    def get_stats(self):
        form_percentage = 0
        if self.count > 0:
            form_percentage = min(95, max(60, 75 + (self.count * 2)))
        
        return {
            'reps': self.count,
            'feedback': self.feedback,
            'form_percentage': form_percentage
        }
    
    def reset(self):
        self.count = 0
        self.stage = None
        self.feedback = "Get Ready"

situps_detector = SitupsCounter()
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def timer_countdown():
    global start_time, is_recording, session_active, exercise_stats
    
    while session_active and is_recording:
        if start_time:
            elapsed = time.time() - start_time
            remaining = max(0, SITUP_DURATION - elapsed)
            
            exercise_stats['elapsed_time'] = int(elapsed)
            exercise_stats['remaining_time'] = int(remaining)
            
            if remaining <= 0:
                auto_save_results()
                break
                
        time.sleep(1)

def save_results(duration, is_manual_stop=False):
    try:
        user = get_current_user()
        user_email = user.get('email', 'test_user_001@example.com')
        
        stats = situps_detector.get_stats()
        reps = stats.get('reps', 0)
        form_quality = stats.get('form_percentage', 0)
        
        result_data = {
            "user_email": user_email,
            "reps_completed": int(reps),
            "form_quality": int(form_quality),
            "timer_time": f"{int(duration // 60)}:{int(duration % 60):02d}",
            "submission_time": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        
        db = get_db()
        if db:
            try:
                collection = db['situps']
                insert_result = collection.insert_one(result_data)
                print(f"✅ MongoDB Save SUCCESS! ID: {insert_result.inserted_id}")
            except Exception as mongo_error:
                print(f"❌ MongoDB save error: {mongo_error}")
        
        os.makedirs(RESULTS_DIR, exist_ok=True)
        safe_user_id = user_email.replace('@', '_').replace('.', '_')
        timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        filename = f"situp_result_{safe_user_id}_{timestamp_str}.json"
        filepath = RESULTS_DIR / filename
        
        with open(filepath, 'w') as f:
            result_data_json = result_data.copy()
            result_data_json['submission_time'] = result_data['submission_time'].isoformat()
            result_data_json['created_at'] = result_data['created_at'].isoformat()
            json.dump(result_data_json, f, indent=2)
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving results: {e}")
        return False

def auto_save_results():
    global is_recording, session_active, session_completed
    
    is_recording = False
    session_active = False
    session_completed = True
    
    result = save_results(SITUP_DURATION, is_manual_stop=False)
    return result

@situp_bp.route('/')
def index():
    user = get_current_user()
    return render_template('index_situp.html', user=user)

@situp_bp.route('/start_camera')
def start_camera():
    global is_recording, session_active, session_completed, start_time, timer_thread
    
    try:
        if session_completed:
            session_completed = False
            session_active = False
        
        is_recording = True
        session_active = True
        start_time = time.time()
        
        situps_detector.reset()
        
        if timer_thread is None or not timer_thread.is_alive():
            timer_thread = threading.Thread(target=timer_countdown)
            timer_thread.daemon = True
            timer_thread.start()
        
        return jsonify({
            'status': 'success', 
            'message': 'Started',
            'duration': SITUP_DURATION
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@situp_bp.route('/stop_camera')
def stop_camera():
    global is_recording, session_active, session_completed, start_time
    
    if not session_active:
        return jsonify({'status': 'error', 'message': 'No active session'})
    
    try:
        elapsed_time = int(time.time() - start_time) if start_time else 0
        
        is_recording = False
        session_active = False
        session_completed = True
        
        save_results(elapsed_time, is_manual_stop=True)
        
        return jsonify({
            'status': 'success', 
            'message': 'Stopped',
            'elapsed_time': elapsed_time
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@situp_bp.route('/reset_counter')
def reset_counter():
    global exercise_stats, session_active, session_completed, is_recording
    
    try:
        if is_recording:
            is_recording = False
        
        session_active = False
        session_completed = False
        
        situps_detector.reset()
        
        exercise_stats.update({
            'reps': 0,
            'feedback': 'Get Ready',
            'form_percentage': 0,
            'elapsed_time': 0,
            'remaining_time': SITUP_DURATION
        })
        
        return jsonify({'status': 'success', 'message': 'Reset'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@situp_bp.route('/get_stats')
def get_stats():
    if is_recording:
        detector_stats = situps_detector.get_stats()
        exercise_stats.update(detector_stats)
    
    exercise_stats['session_active'] = session_active
    exercise_stats['session_completed'] = session_completed
    
    return jsonify(exercise_stats)

@situp_bp.route('/session_status')
def session_status():
    return jsonify({
        'session_active': session_active,
        'session_completed': session_completed,
        'duration': SITUP_DURATION,
        'elapsed_time': exercise_stats.get('elapsed_time', 0),
        'remaining_time': exercise_stats.get('remaining_time', SITUP_DURATION)
    })

@situp_bp.route('/new_session')
def new_session():
    global session_active, session_completed, start_time, exercise_stats
    
    if session_active:
        return jsonify({'status': 'error', 'message': 'Session in progress'})
    
    session_completed = False
    start_time = None
    
    exercise_stats = {
        'reps': 0,
        'feedback': 'Get Ready',
        'exercise': 'situps',
        'form_percentage': 0,
        'elapsed_time': 0,
        'remaining_time': SITUP_DURATION
    }
    
    situps_detector.reset()
    
    return jsonify({'status': 'success', 'message': 'Ready'})

def process_frame_websocket(socketio_instance):
    """WebSocket handler for processing frames from browser"""
    
    @socketio_instance.on('video_frame')
    def handle_video_frame(data):
        global is_recording, exercise_stats
        
        if not is_recording:
            return
        
        try:
            # Decode base64 image from browser
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Resize frame for faster processing (optional but recommended)
            frame = cv2.resize(frame, (480, 360), interpolation=cv2.INTER_LINEAR)
            
            # Process frame with situps detector
            processed_frame = situps_detector.detect_situps(frame)
            
            # Update stats
            stats = situps_detector.get_stats()
            exercise_stats.update(stats)
            
            # Encode processed frame back to base64
            _, buffer = cv2.imencode('.jpg', processed_frame)
            processed_img = base64.b64encode(buffer).decode('utf-8')
            
            # Send processed frame and stats back to browser
            emit('processed_frame', {
                'image': f'data:image/jpeg;base64,{processed_img}',
                'stats': exercise_stats
            })
            
        except Exception as e:
            print(f"Error processing frame: {e}")
            emit('error', {'message': str(e)})

    return handle_video_frame
