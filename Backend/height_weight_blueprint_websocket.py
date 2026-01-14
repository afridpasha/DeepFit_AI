from flask import Blueprint, jsonify, session, render_template
from flask_socketio import emit
from db_config import get_db
import cv2
import numpy as np
import mediapipe as mp
import base64
from datetime import datetime
from bson import ObjectId

height_weight_bp = Blueprint('height_weight', __name__,
                            template_folder='../Frontend/templates',
                            static_folder='../Frontend/static',
                            url_prefix='/height_weight')

is_recording = False
session_active = False
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

measurement_data = {
    'height_cm': 0.0,
    'weight_kg': 0.0,
    'bmi': 0.0,
    'confidence': 0.0,
    'status': 'Ready',
    'calibrated': False
}

def get_current_user():
    try:
        db = get_db()
        if db and 'user_id' in session:
            user = db.users.find_one({'_id': ObjectId(session['user_id'])})
            if user:
                return {'email': user.get('email', 'user@example.com')}
        return {'email': 'test_user@example.com'}
    except:
        return {'email': 'test_user@example.com'}

@height_weight_bp.route('/')
def index():
    response = render_template('index_height_weight.html')
    return response

@height_weight_bp.route('/start_measurement')
def start_measurement():
    global is_recording, session_active
    
    try:
        is_recording = True
        session_active = True
        
        measurement_data.update({
            'height_cm': 0.0,
            'weight_kg': 0.0,
            'bmi': 0.0,
            'confidence': 0.0,
            'status': 'Measuring...',
            'calibrated': False
        })
        
        return jsonify({'status': 'success', 'message': 'Started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/stop_measurement')
def stop_measurement():
    global is_recording, session_active
    
    try:
        is_recording = False
        session_active = False
        
        user = get_current_user()
        user_email = user['email']
        
        if measurement_data['height_cm'] > 0:
            try:
                db = get_db()
                if db:
                    result_data = {
                        'user_email': user_email,
                        'height_cm': measurement_data['height_cm'],
                        'weight_kg': measurement_data['weight_kg'],
                        'bmi': measurement_data['bmi'],
                        'confidence_score': measurement_data['confidence'],
                        'timestamp': datetime.utcnow(),
                        'submission_time': datetime.utcnow()
                    }
                    
                    collection = db['Height_and_Weight']
                    insert_result = collection.insert_one(result_data)
                    print(f"✅ Height/Weight saved! ID: {insert_result.inserted_id}")
            except Exception as e:
                print(f"❌ MongoDB save error: {e}")
        
        return jsonify({'status': 'success', 'message': 'Stopped and saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/reset_measurement')
def reset_measurement():
    global measurement_data, session_active, is_recording
    
    try:
        if is_recording:
            is_recording = False
        
        session_active = False
        
        measurement_data.update({
            'height_cm': 0.0,
            'weight_kg': 0.0,
            'bmi': 0.0,
            'confidence': 0.0,
            'status': 'Ready',
            'calibrated': False
        })
        
        return jsonify({'status': 'success', 'message': 'Reset'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/get_measurement')
def get_measurement():
    return jsonify(measurement_data)

def process_frame_websocket(socketio_instance):
    """WebSocket handler for height/weight measurement"""
    
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    )
    
    @socketio_instance.on('height_weight_frame')
    def handle_height_weight_frame(data):
        global is_recording, measurement_data
        
        if not is_recording:
            return
        
        try:
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
            
            h, w = frame.shape[:2]
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb_frame)
            
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                
                # Calculate height (head to feet)
                nose = landmarks[mp_pose.PoseLandmark.NOSE.value]
                left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
                right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
                
                avg_ankle_y = (left_ankle.y + right_ankle.y) / 2
                height_pixels = abs(avg_ankle_y - nose.y) * h
                
                # Estimate height (assuming person is ~2m from camera)
                pixels_per_cm = 3.5
                height_cm = height_pixels / pixels_per_cm
                
                # Estimate weight based on body proportions
                left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
                right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
                right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
                
                shoulder_width = abs(left_shoulder.x - right_shoulder.x) * w
                torso_height = abs(((left_shoulder.y + right_shoulder.y) / 2) - 
                                  ((left_hip.y + right_hip.y) / 2)) * h
                
                # Simple weight estimation (BMI-based)
                height_m = height_cm / 100
                estimated_bmi = 22.0  # Average BMI
                weight_kg = estimated_bmi * (height_m ** 2)
                
                # Adjust based on body width
                width_factor = shoulder_width / 100
                weight_kg *= (0.8 + width_factor * 0.4)
                
                bmi = weight_kg / (height_m ** 2)
                confidence = min(left_ankle.visibility, right_ankle.visibility, nose.visibility)
                
                measurement_data.update({
                    'height_cm': round(height_cm, 1),
                    'weight_kg': round(weight_kg, 1),
                    'bmi': round(bmi, 1),
                    'confidence': round(confidence, 2),
                    'status': 'Measuring...',
                    'calibrated': True
                })
                
                # Draw landmarks
                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                
                # Draw measurements
                cv2.putText(frame, f"Height: {height_cm:.1f} cm", (10, 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"Weight: {weight_kg:.1f} kg", (10, 60),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"BMI: {bmi:.1f}", (10, 90),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                measurement_data['status'] = 'No person detected'
            
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            processed_img = base64.b64encode(buffer).decode('utf-8')
            
            emit('processed_height_weight_frame', {
                'image': f'data:image/jpeg;base64,{processed_img}',
                'measurement': measurement_data
            })
            
        except Exception as e:
            print(f"Error processing height/weight frame: {e}")
            emit('error', {'message': str(e)})
    
    return handle_height_weight_frame
