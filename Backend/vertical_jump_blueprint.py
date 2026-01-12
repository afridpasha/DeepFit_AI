from flask import Blueprint, render_template, Response, jsonify, request, session
import cv2
import mediapipe as mp
import numpy as np
import threading
import time
import json
import os
from datetime import datetime
from pathlib import Path
from bson import ObjectId
from db_config import get_db
from advanced_jump_detector import AdvancedJumpDetector

vertical_jump_bp = Blueprint('vertical_jump', __name__,
                           template_folder='templates',
                           static_folder='static',
                           url_prefix='/vertical_jump')

# Global variables
camera = None
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

def generate_frames():
    global camera, is_recording, exercise_stats
    
    while is_recording and camera is not None:
        success, frame = camera.read()
        if not success:
            break
        
        # Process frame with jump detector
        frame = jump_detector.process_frame(frame)
        
        # Update stats
        stats = jump_detector.get_performance_stats()
        exercise_stats.update({
            'total_jumps': stats['total_jumps'],
            'current_height': stats['current_height'],
            'max_height': stats['max_height'],
            'state': stats['state'],
            'calibrated': stats['calibrated'],
            'feedback': stats['feedback']
        })
        
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@vertical_jump_bp.route('/start_camera')
def start_camera():
    global camera, is_recording, session_active, start_time
    
    try:
        if camera is not None:
            camera.release()
            camera = None
        
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            return jsonify({'status': 'error', 'message': 'Camera unavailable'})
        
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, 30)
        
        is_recording = True
        session_active = True
        start_time = time.time()
        
        jump_detector.reset_session()
        
        return jsonify({'status': 'success', 'message': 'Started'})
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/stop_camera')
def stop_camera():
    global camera, is_recording, session_active
    
    try:
        is_recording = False
        session_active = False
        
        if camera:
            camera.release()
            camera = None
        
        # Get user info
        user = get_current_user()
        user_email = user['email']
        
        # Get jump detector stats
        stats = jump_detector.get_performance_stats()
        
        print(f"\n🔥 SAVING VERTICAL JUMP RESULTS 🔥")
        print(f"✅ User Email: {user_email}")
        print(f"📊 Total Jumps: {stats['total_jumps']}, Max Height: {stats['max_height']:.1f} cm")
        
        # Save to MongoDB using jump_detector's method
        try:
            db = get_db()
            if db:
                # Get session data from jump detector
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
                
                print(f"💾 Data to save: Total jumps={session_data['total_jumps']}, Max height={session_data['max_height']}")
                
                collection = db['Vertical_Jump']
                insert_result = collection.insert_one(session_data)
                print(f"✅ MongoDB Save SUCCESS! ID: {insert_result.inserted_id}")
                print(f"📁 Saved to: Database=sih2573, Collection=Vertical_Jump")
            else:
                print("❌ Database connection not available")
        except Exception as e:
            print(f"❌ MongoDB save error: {e}")
            import traceback
            traceback.print_exc()
        
        return jsonify({'status': 'success', 'message': 'Stopped and saved'})
        
    except Exception as e:
        print(f"❌ Error in stop_camera: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)})

@vertical_jump_bp.route('/reset_counter')
def reset_counter():
    global exercise_stats, session_active, camera, is_recording
    
    try:
        if is_recording:
            is_recording = False
        
        if camera is not None:
            camera.release()
            camera = None
        
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

@vertical_jump_bp.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

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

@vertical_jump_bp.route('/cleanup', methods=['POST'])
def cleanup():
    global camera, is_recording, session_active
    
    try:
        is_recording = False
        session_active = False
        
        if camera is not None:
            camera.release()
            camera = None
        
        return '', 204
    except Exception:
        return '', 204