from flask import Blueprint, jsonify, session, render_template
from flask_socketio import emit
from db_config import get_db
import cv2
import numpy as np
import time
import base64
from datetime import datetime
from bson import ObjectId
from advanced_jump_detector import AdvancedJumpDetector

vertical_jump_bp = Blueprint('vertical_jump', __name__,
                           template_folder='../Frontend/templates',
                           static_folder='../Frontend/static',
                           url_prefix='/vertical_jump')

@vertical_jump_bp.route('/')
def index():
    """Main vertical jump page with WebSocket support"""
    from flask import make_response
    response = make_response(render_template('index_verticaljump_new.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

is_recording = False
session_active = False
start_time = None
jump_detector = AdvancedJumpDetector()
exercise_stats = {
    'total_jumps': 0,
    'current_height': 0.0,
    'max_height': 0.0,
    'state': 'GROUND',
    'calibrated': False,
    'feedback': 'System Ready'
}

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

@vertical_jump_bp.route('/start_camera')
def start_camera():
    global is_recording, session_active, start_time
    
    try:
        is_recording = True
        session_active = True
        start_time = time.time()
        
        jump_detector.reset_session()
        
        return jsonify({'status': 'success', 'message': 'Started'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/stop_camera')
def stop_camera():
    global is_recording, session_active
    
    try:
        is_recording = False
        session_active = False
        
        user = get_current_user()
        user_email = user['email']
        
        stats = jump_detector.get_performance_stats()
        
        try:
            db = get_db()
            if db:
                session_data = {
                    'user_email': user_email,
                    'session_start': jump_detector.session_start.isoformat(),
                    'total_jumps': jump_detector.jump_count,
                    'max_height': jump_detector.max_height_cm,
                    'average_height': sum(j['height_cm'] for j in jump_detector.jump_history) / len(jump_detector.jump_history) if jump_detector.jump_history else 0,
                    'calibration_data': {
                        'pixels_per_cm': jump_detector.pixels_per_cm,
                        'baseline_y': jump_detector.baseline_y if hasattr(jump_detector, 'baseline_y') else 0
                    },
                    'jumps': jump_detector.jump_history,
                    'submission_time': datetime.utcnow()
                }
                
                collection = db['Vertical_Jump']
                insert_result = collection.insert_one(session_data)
                print(f"✅ MongoDB Save SUCCESS! ID: {insert_result.inserted_id}")
        except Exception as e:
            print(f"❌ MongoDB save error: {e}")
        
        return jsonify({'status': 'success', 'message': 'Stopped and saved'})
        
    except Exception as e:
        print(f"❌ Error in stop_camera: {e}")
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/reset_counter')
def reset_counter():
    global exercise_stats, session_active, is_recording
    
    try:
        if is_recording:
            is_recording = False
        
        session_active = False
        jump_detector.reset_session()
        
        exercise_stats.update({
            'total_jumps': 0,
            'current_height': 0.0,
            'max_height': 0.0,
            'state': 'GROUND',
            'calibrated': False,
            'feedback': 'System Ready'
        })
        
        return jsonify({'status': 'success', 'message': 'Reset'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/get_stats')
def get_stats():
    if is_recording:
        stats = jump_detector.get_performance_stats()
        exercise_stats.update({
            'total_jumps': stats['total_jumps'],
            'current_height': stats['current_height'],
            'max_height': stats['max_height'],
            'state': stats['state'],
            'calibrated': stats['calibrated'],
            'feedback': stats['feedback']
        })
    
    return jsonify(exercise_stats)

@vertical_jump_bp.route('/video_feed')
def video_feed():
    """Dummy route - video is handled via WebSocket"""
    return jsonify({'message': 'Video streaming via WebSocket'}), 200

def process_frame_websocket(socketio_instance):
    """WebSocket handler for processing vertical jump frames from browser"""
    
    @socketio_instance.on('jump_frame')
    def handle_jump_frame(data):
        global is_recording, exercise_stats
        
        if not is_recording:
            return
        
        try:
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Resize for faster processing
            frame = cv2.resize(frame, (480, 360), interpolation=cv2.INTER_LINEAR)
            
            processed_frame = jump_detector.process_frame(frame)
            
            stats = jump_detector.get_performance_stats()
            exercise_stats.update({
                'total_jumps': stats['total_jumps'],
                'current_height': stats['current_height'],
                'max_height': stats['max_height'],
                'state': stats['state'],
                'calibrated': stats['calibrated'],
                'feedback': stats['feedback']
            })
            
            _, buffer = cv2.imencode('.jpg', processed_frame)
            processed_img = base64.b64encode(buffer).decode('utf-8')
            
            emit('processed_jump_frame', {
                'image': f'data:image/jpeg;base64,{processed_img}',
                'stats': exercise_stats
            })
            
        except Exception as e:
            print(f"Error processing jump frame: {e}")
            emit('error', {'message': str(e)})
    
    return handle_jump_frame
