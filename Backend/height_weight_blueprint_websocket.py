from flask import Blueprint, jsonify, session, render_template
from flask_socketio import emit
from db_config import get_db
import cv2
import numpy as np
import base64
from datetime import datetime
from bson import ObjectId
import sys
import os

# Add Backend directory to path to import integrated_system
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the EXACT same logic from integrated_system.py
from integrated_system import IntegratedHeightWeightSystem

height_weight_bp = Blueprint('height_weight', __name__,
                            template_folder='../Frontend/templates',
                            static_folder='../Frontend/static',
                            url_prefix='/height_weight')

# Initialize the integrated system (same as desktop version)
integrated_system = None
is_recording = False
session_active = False

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
    global is_recording, session_active, integrated_system
    
    try:
        # Get user email
        user = get_current_user()
        user_email = user['email']
        
        # Initialize integrated system with SAME logic as desktop
        integrated_system = IntegratedHeightWeightSystem(
            use_gpu=False,  # Use CPU for web to avoid GPU conflicts
            calibration_file="camera_calibration.yaml",
            user_email=user_email
        )
        
        is_recording = True
        session_active = True
        
        return jsonify({'status': 'success', 'message': 'Started'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/stop_measurement')
def stop_measurement():
    global is_recording, session_active, integrated_system
    
    try:
        is_recording = False
        session_active = False
        
        # Compute final estimate using SAME logic
        if integrated_system and integrated_system.session_instances:
            integrated_system._compute_final_estimate()
        
        return jsonify({'status': 'success', 'message': 'Stopped and saved'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/reset_measurement')
def reset_measurement():
    global session_active, is_recording, integrated_system
    
    try:
        if is_recording:
            is_recording = False
        
        session_active = False
        
        # Reset using SAME logic
        if integrated_system:
            integrated_system.stability_buffer.clear()
            integrated_system.consecutive_stable_frames = 0
        
        return jsonify({'status': 'success', 'message': 'Reset'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/save_measurement')
def save_measurement():
    """Save current measurement (S key functionality)"""
    global integrated_system
    
    try:
        if integrated_system and integrated_system.measurement_history:
            latest = integrated_system.measurement_history[-1]
            if latest.detection_status.value == 'good_position':
                measurement_data = {
                    "height_cm": latest.height_cm,
                    "weight_kg": latest.weight_kg,
                    "confidence_score": latest.confidence_score,
                    "uncertainty_height": latest.uncertainty_height,
                    "uncertainty_weight": latest.uncertainty_weight,
                    "detection_status": latest.detection_status.value,
                    "calibration_quality": latest.calibration_quality,
                    "bmi": latest.weight_kg / ((latest.height_cm / 100) ** 2) if latest.height_cm > 0 else 0
                }
                integrated_system.session_instances.append(measurement_data)
                integrated_system.mongo_manager.store_height_weight_instance(measurement_data, integrated_system.user_email)
                return jsonify({'status': 'success', 'message': f'Saved! Total: {len(integrated_system.session_instances)}'})
        return jsonify({'status': 'error', 'message': 'No valid measurement'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/final_estimate')
def final_estimate():
    """Compute final estimate (F key functionality)"""
    global integrated_system
    
    try:
        if integrated_system and integrated_system.session_instances:
            integrated_system._compute_final_estimate()
            return jsonify({'status': 'success', 'message': 'Final estimate computed'})
        return jsonify({'status': 'error', 'message': 'No measurements to compute'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/toggle_autosave')
def toggle_autosave():
    """Toggle auto-save (C key functionality)"""
    global integrated_system
    
    try:
        if integrated_system:
            integrated_system.auto_save_enabled = not integrated_system.auto_save_enabled
            status = "ON" if integrated_system.auto_save_enabled else "OFF"
            return jsonify({'status': 'success', 'message': f'Auto-save: {status}', 'enabled': integrated_system.auto_save_enabled})
        return jsonify({'status': 'error', 'message': 'System not initialized'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

def process_frame_websocket(socketio_instance):
    """WebSocket handler using EXACT same processing logic as desktop version"""
    
    @socketio_instance.on('height_weight_frame')
    def handle_height_weight_frame(data):
        global is_recording, integrated_system
        
        if not is_recording or not integrated_system:
            return
        
        try:
            # Decode frame from browser
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Process using EXACT same logic as desktop version
            result = integrated_system.process_frame_integrated(frame)
            
            # Draw UI using EXACT same enhanced_ui.py logic
            status_str = result.detection_status.value.upper()
            frame = integrated_system.ui.draw_positioning_guides(
                frame, status_str, result.body_parts_status or {}
            )
            
            # Draw measurement panel if good position
            if result.detection_status.value in ['good_position', 'measuring_stable']:
                bmi = result.weight_kg / ((result.height_cm / 100) ** 2) if result.height_cm > 0 else 0
                frame = integrated_system.ui.draw_measurement_panel(
                    frame, result.height_cm, result.weight_kg, result.confidence_score,
                    result.uncertainty_height, result.uncertainty_weight, bmi
                )
            
            # Draw controls and status
            frame = integrated_system.ui.draw_controls_panel(frame)
            calibration_status = f"Calibrated ({result.calibration_quality:.2f}px)" if integrated_system.camera_calibration.is_calibrated else "Uncalibrated"
            frame = integrated_system.ui.draw_status_bar(
                frame, result.position_message, calibration_status, integrated_system.current_fps
            )
            
            # Auto-save using SAME logic when position is PERFECT
            if result.detection_status.value in ['good_position', 'measuring_stable']:
                measurement_data = {
                    "height_cm": result.height_cm,
                    "weight_kg": result.weight_kg,
                    "confidence_score": result.confidence_score,
                    "uncertainty_height": result.uncertainty_height,
                    "uncertainty_weight": result.uncertainty_weight,
                    "detection_status": result.detection_status.value,
                    "calibration_quality": result.calibration_quality,
                    "bmi": result.weight_kg / ((result.height_cm / 100) ** 2) if result.height_cm > 0 else 0,
                    "timestamp": datetime.utcnow()
                }
                
                # AUTO-MEASUREMENT: Save automatically when position is perfect and stable
                if (result.detection_status.value == 'measuring_stable' and 
                    integrated_system.auto_save_enabled and
                    integrated_system.consecutive_stable_frames >= integrated_system.stability_threshold):
                    
                    # Check if enough time passed since last auto-save
                    import time
                    current_time = time.time()
                    if current_time - integrated_system.last_auto_save > integrated_system.auto_save_cooldown:
                        integrated_system.session_instances.append(measurement_data)
                        integrated_system.mongo_manager.store_height_weight_instance(measurement_data, integrated_system.user_email)
                        integrated_system.last_auto_save = current_time
                        print(f"AUTO-SAVED: H={result.height_cm:.1f}cm, W={result.weight_kg:.1f}kg (Total: {len(integrated_system.session_instances)})")
            
            # Encode and send back
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            processed_img = base64.b64encode(buffer).decode('utf-8')
            
            emit('processed_height_weight_frame', {
                'image': f'data:image/jpeg;base64,{processed_img}',
                'measurement': {
                    'height_cm': round(result.height_cm, 1),
                    'weight_kg': round(result.weight_kg, 1),
                    'bmi': round(result.weight_kg / ((result.height_cm / 100) ** 2), 1) if result.height_cm > 0 else 0,
                    'confidence': round(result.confidence_score, 2),
                    'status': result.position_message,
                    'calibrated': integrated_system.camera_calibration.is_calibrated
                }
            })
            
        except Exception as e:
            print(f"Error processing height/weight frame: {e}")
            emit('error', {'message': str(e)})
    
    return handle_height_weight_frame
