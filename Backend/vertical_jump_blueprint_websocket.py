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

def resolve_user_email():
    """Resolve authenticated user email from session/DB."""
    try:
        session_email = (session.get('user_email') or '').strip().lower()
        if session_email:
            return session_email

        db = get_db()
        if db is not None and 'user_id' in session:
            user = db.users.find_one({'_id': ObjectId(session['user_id'])})
            if user and user.get('email'):
                resolved = str(user.get('email')).strip().lower()
                session['user_email'] = resolved
                return resolved
    except Exception:
        pass
    return None

def _has_valid_jump_results():
    """Allow save only when there is meaningful jump data."""
    jump_count = int(getattr(jump_detector, 'jump_count', 0) or 0)
    max_height = float(getattr(jump_detector, 'max_height_cm', 0.0) or 0.0)
    jump_history = getattr(jump_detector, 'jump_history', []) or []
    return jump_count > 0 and max_height > 0 and len(jump_history) > 0

def _build_session_data(user_email, save_mode='manual'):
    session_start = getattr(jump_detector, 'session_start', None)
    session_start_iso = session_start.isoformat() if session_start else datetime.utcnow().isoformat()
    return {
        'user_email': user_email,
        'email': user_email,
        'session_start': session_start_iso,
        'total_jumps': jump_detector.jump_count,
        'max_height': jump_detector.max_height_cm,
        'average_height': (
            sum(j['height_cm'] for j in jump_detector.jump_history) / len(jump_detector.jump_history)
            if jump_detector.jump_history else 0
        ),
        'calibration_data': {
            'pixels_per_cm': jump_detector.pixels_per_cm,
            'baseline_y': jump_detector.baseline_y if hasattr(jump_detector, 'baseline_y') else 0
        },
        'jumps': jump_detector.jump_history,
        'save_mode': save_mode,
        'submission_time': datetime.utcnow()
    }

def _save_vertical_jump_results(user_email, save_mode='manual'):
    """Persist current jump session with strict validation."""
    if not _has_valid_jump_results():
        return False, 'No valid jump results to save. Complete at least one valid jump first.', None, 400

    db = get_db()
    if db is None:
        return False, 'Database unavailable. Could not save results.', None, 500

    session_data = _build_session_data(user_email, save_mode=save_mode)
    try:
        collection = db['Vertical_Jump']
        session_filter = {
            'user_email': user_email,
            'session_start': session_data['session_start']
        }
        update_result = collection.update_one(
            session_filter,
            {
                '$set': session_data,
                '$setOnInsert': {'created_at': datetime.utcnow()}
            },
            upsert=True
        )
        saved_id = str(update_result.upserted_id) if update_result.upserted_id else None
        if saved_id:
            print(f'MongoDB Save SUCCESS! Created ID: {saved_id}')
        else:
            print('MongoDB Save SUCCESS! Existing session updated.')
        return True, 'Results saved successfully', saved_id, 200
    except Exception as save_error:
        print(f'MongoDB save error: {save_error}')
        return False, f'Failed to save results: {save_error}', None, 500

@vertical_jump_bp.route('/start_camera')
def start_camera():
    global is_recording, session_active, start_time
    
    try:
        if not resolve_user_email():
            return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

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
        
        user_email = resolve_user_email()
        if not user_email:
            return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

        saved, message, result_id, status_code = _save_vertical_jump_results(
            user_email,
            save_mode='auto_stop'
        )
        if not saved:
            return jsonify({'status': 'error', 'message': message}), status_code

        return jsonify({
            'status': 'success',
            'message': 'Stopped and saved',
            'result_id': result_id
        })

    except Exception as e:
        print(f'Error in stop_camera: {e}')
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/save_results')
def save_results():
    """Manual save endpoint for current in-progress jump session."""
    try:
        user_email = resolve_user_email()
        if not user_email:
            return jsonify({'status': 'error', 'message': 'Authentication required'}), 401

        saved, message, result_id, status_code = _save_vertical_jump_results(
            user_email,
            save_mode='manual'
        )
        if not saved:
            return jsonify({'status': 'error', 'message': message}), status_code

        return jsonify({
            'status': 'success',
            'message': message,
            'result_id': result_id
        })
    except Exception as e:
        print(f'Error in save_results: {e}')
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
            
            # Keep a slightly larger processing frame (aspect-ratio preserved)
            # so the displayed video is clearer and less cramped.
            h, w = frame.shape[:2]
            target_width = 640
            if w > target_width:
                target_height = int(h * (target_width / float(w)))
                frame = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
            
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
