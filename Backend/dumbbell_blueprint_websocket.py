from flask import Blueprint, jsonify, session
from flask_socketio import emit
from db_config import get_db
import cv2
import mediapipe as mp
import numpy as np
import time
import math
import base64
from datetime import datetime
from bson import ObjectId
from collections import deque

dumbbell_bp = Blueprint('dumbbell', __name__,
                       template_folder='templates',
                       static_folder='static',
                       url_prefix='/dumbbell')

is_recording = False
session_active = False
start_time = None

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
UP_ANGLE_THRESHOLD = 55
DOWN_ANGLE_THRESHOLD = 150
SMOOTH_WINDOW = 5
VISIBILITY_THRESHOLD = 0.5

state = {'left': 'down', 'right': 'down'}
counts = {'left': 0, 'right': 0}
angle_buffers = {'left': deque(maxlen=SMOOTH_WINDOW), 'right': deque(maxlen=SMOOTH_WINDOW)}
estimated_weight = 0.0

exercise_stats = {
    'left_reps': 0,
    'right_reps': 0,
    'total_reps': 0,
    'left_status': 'Not visible',
    'right_status': 'Not visible',
    'estimated_weight': 0.0
}

def angle_between(a, b, c):
    ax, ay = a
    bx, by = b
    cx, cy = c
    v1 = (ax - bx, ay - by)
    v2 = (cx - bx, cy - by)
    dot = v1[0]*v2[0] + v1[1]*v2[1]
    mag1 = math.hypot(v1[0], v1[1])
    mag2 = math.hypot(v2[0], v2[1])
    if mag1 * mag2 == 0:
        return 0.0
    cosang = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cosang))

def get_current_user():
    try:
        db = get_db()
        if db and 'user_id' in session:
            user = db.users.find_one({'_id': ObjectId(session['user_id'])})
            if user:
                return {'email': user.get('email', 'user@example.com')}
        return {'email': 'test_user_001@example.com'}
    except:
        return {'email': 'test_user_001@example.com'}

@dumbbell_bp.route('/start_camera')
def start_camera():
    global is_recording, session_active, start_time, state, counts, angle_buffers, estimated_weight
    
    try:
        is_recording = True
        session_active = True
        start_time = time.time()
        
        state = {'left': 'down', 'right': 'down'}
        counts = {'left': 0, 'right': 0}
        angle_buffers = {'left': deque(maxlen=SMOOTH_WINDOW), 'right': deque(maxlen=SMOOTH_WINDOW)}
        estimated_weight = 0.0
        
        exercise_stats.update({
            'left_reps': 0,
            'right_reps': 0,
            'total_reps': 0,
            'left_status': 'Not visible',
            'right_status': 'Not visible',
            'estimated_weight': 0.0
        })
        
        return jsonify({'status': 'success', 'message': 'Started'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@dumbbell_bp.route('/stop_camera')
def stop_camera():
    global is_recording, session_active
    
    try:
        is_recording = False
        session_active = False
        
        user = get_current_user()
        user_email = user['email']
        
        session_duration = round(time.time() - start_time, 2) if start_time else 0
        
        data = {
            "user_email": user_email,
            "timestamp": datetime.now().strftime('%Y%m%d_%H%M%S'),
            "exercise_type": "dumbbell_curls",
            "estimated_weight": round(estimated_weight, 2),
            "left_reps": counts['left'],
            "right_reps": counts['right'],
            "total_reps": counts['left'] + counts['right'],
            "session_duration": session_duration,
            "analysis_date": datetime.now().isoformat(),
            "submission_time": datetime.utcnow()
        }
        
        try:
            db = get_db()
            if db:
                collection = db['DumbBell']
                insert_result = collection.insert_one(data)
                print(f"✅ MongoDB Save SUCCESS! ID: {insert_result.inserted_id}")
        except Exception as e:
            print(f"❌ MongoDB save error: {e}")
        
        return jsonify({'status': 'success', 'message': 'Stopped and saved'})
        
    except Exception as e:
        print(f"❌ Error in stop_camera: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@dumbbell_bp.route('/reset_counter')
def reset_counter():
    global exercise_stats, session_active, is_recording, state, counts, angle_buffers, estimated_weight
    
    try:
        if is_recording:
            is_recording = False
        
        session_active = False
        
        state = {'left': 'down', 'right': 'down'}
        counts = {'left': 0, 'right': 0}
        angle_buffers = {'left': deque(maxlen=SMOOTH_WINDOW), 'right': deque(maxlen=SMOOTH_WINDOW)}
        estimated_weight = 0.0
        
        exercise_stats.update({
            'left_reps': 0,
            'right_reps': 0,
            'total_reps': 0,
            'left_status': 'Not visible',
            'right_status': 'Not visible',
            'estimated_weight': 0.0
        })
        
        return jsonify({'status': 'success', 'message': 'Reset'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@dumbbell_bp.route('/get_stats')
def get_stats():
    return jsonify(exercise_stats)

def process_frame_websocket(socketio_instance):
    """WebSocket handler for processing dumbbell frames from browser"""
    
    # Optimize MediaPipe for speed
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,  # Fastest model
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    @socketio_instance.on('dumbbell_frame')
    def handle_dumbbell_frame(data):
        global is_recording, exercise_stats, state, counts, angle_buffers, estimated_weight
        
        if not is_recording:
            return
        
        try:
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Resize for faster processing
            frame = cv2.resize(frame, (480, 360), interpolation=cv2.INTER_LINEAR)
            
            h, w = frame.shape[:2]
            img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(img_rgb)
            
            if results.pose_landmarks:
                lm = results.pose_landmarks.landmark
                def xy(idx): return (int(lm[idx].x * w), int(lm[idx].y * h))
                
                L_SHOULDER = mp_pose.PoseLandmark.LEFT_SHOULDER.value
                L_ELBOW = mp_pose.PoseLandmark.LEFT_ELBOW.value
                L_WRIST = mp_pose.PoseLandmark.LEFT_WRIST.value
                R_SHOULDER = mp_pose.PoseLandmark.RIGHT_SHOULDER.value
                R_ELBOW = mp_pose.PoseLandmark.RIGHT_ELBOW.value
                R_WRIST = mp_pose.PoseLandmark.RIGHT_WRIST.value
                
                visible_left = (lm[L_SHOULDER].visibility > VISIBILITY_THRESHOLD and
                               lm[L_ELBOW].visibility > VISIBILITY_THRESHOLD and
                               lm[L_WRIST].visibility > VISIBILITY_THRESHOLD)
                
                if visible_left:
                    left_angle = angle_between(xy(L_SHOULDER), xy(L_ELBOW), xy(L_WRIST))
                    angle_buffers['left'].append(left_angle)
                    if len(angle_buffers['left']) > 0:
                        left_angle_smooth = sum(angle_buffers['left']) / len(angle_buffers['left'])
                    
                    cur_state = state['left']
                    if cur_state == 'down' and left_angle_smooth <= UP_ANGLE_THRESHOLD:
                        state['left'] = 'up'
                        counts['left'] += 1
                    elif cur_state == 'up' and left_angle_smooth >= DOWN_ANGLE_THRESHOLD:
                        state['left'] = 'down'
                    
                    exercise_stats['left_status'] = f"L: {int(left_angle_smooth)}°"
                else:
                    exercise_stats['left_status'] = "L: Not visible"
                
                visible_right = (lm[R_SHOULDER].visibility > VISIBILITY_THRESHOLD and
                                lm[R_ELBOW].visibility > VISIBILITY_THRESHOLD and
                                lm[R_WRIST].visibility > VISIBILITY_THRESHOLD)
                
                if visible_right:
                    right_angle = angle_between(xy(R_SHOULDER), xy(R_ELBOW), xy(R_WRIST))
                    angle_buffers['right'].append(right_angle)
                    if len(angle_buffers['right']) > 0:
                        right_angle_smooth = sum(angle_buffers['right']) / len(angle_buffers['right'])
                    
                    cur_state = state['right']
                    if cur_state == 'down' and right_angle_smooth <= UP_ANGLE_THRESHOLD:
                        state['right'] = 'up'
                        counts['right'] += 1
                    elif cur_state == 'up' and right_angle_smooth >= DOWN_ANGLE_THRESHOLD:
                        state['right'] = 'down'
                    
                    exercise_stats['right_status'] = f"R: {int(right_angle_smooth)}°"
                else:
                    exercise_stats['right_status'] = "R: Not visible"
                
                exercise_stats['left_reps'] = counts['left']
                exercise_stats['right_reps'] = counts['right']
                exercise_stats['total_reps'] = counts['left'] + counts['right']
                
                total_reps = counts['left'] + counts['right']
                if total_reps > 0:
                    estimated_weight = max(5.0, min(25.0, 10 + (total_reps * 0.5)))
                    exercise_stats['estimated_weight'] = round(estimated_weight, 1)
                
                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
            
            _, buffer = cv2.imencode('.jpg', frame)
            processed_img = base64.b64encode(buffer).decode('utf-8')
            
            emit('processed_dumbbell_frame', {
                'image': f'data:image/jpeg;base64,{processed_img}',
                'stats': exercise_stats
            })
            
        except Exception as e:
            print(f"Error processing dumbbell frame: {e}")
            emit('error', {'message': str(e)})
    
    return handle_dumbbell_frame
