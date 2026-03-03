from flask import Blueprint, jsonify, session, render_template
from flask_socketio import emit
from db_config import get_db
import cv2
import numpy as np
import base64
from datetime import datetime
import time
from collections import Counter
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
VALID_MEASUREMENT_STATUSES = {'good_position', 'measuring_stable', 'auto_saved'}
MIN_SUBMIT_SAMPLES = 10
WEB_AUTOSAVE_COOLDOWN_SECONDS = 1.2
MAX_SESSION_MEASUREMENTS = 200

def get_current_user():
    try:
        db = get_db()
        # Prefer email already held in session when available.
        session_email = (session.get('user_email') or '').strip().lower()
        if session_email:
            return {'email': session_email}

        if db is not None and 'user_id' in session:
            user = db.users.find_one({'_id': ObjectId(session['user_id'])})
            if user:
                return {'email': user.get('email', 'user@example.com')}
        return {'email': 'anonymous@deepfit.local'}
    except Exception:
        return {'email': (session.get('user_email') or 'anonymous@deepfit.local')}

@height_weight_bp.route('/')
def index():
    response = render_template('index_height_weight.html')
    return response

def _is_valid_measurement_result(result):
    """Treat only valid 'tick-mark style' detection states as saveable measurements."""
    if result is None:
        return False

    status = getattr(result.detection_status, 'value', '')
    return (
        status in VALID_MEASUREMENT_STATUSES and
        result.height_cm > 0 and
        result.weight_kg > 0 and
        result.confidence_score > 0
    )

def _build_measurement_data(result):
    bmi = result.weight_kg / ((result.height_cm / 100) ** 2) if result.height_cm > 0 else 0
    return {
        "height_cm": float(result.height_cm),
        "weight_kg": float(result.weight_kg),
        "confidence_score": float(result.confidence_score),
        "uncertainty_height": float(result.uncertainty_height),
        "uncertainty_weight": float(result.uncertainty_weight),
        "detection_status": result.detection_status.value,
        "calibration_quality": float(result.calibration_quality),
        "bmi": float(bmi),
        "timestamp": datetime.utcnow()
    }

def _append_session_measurement(measurement_data):
    """Store auto/manual measurement for this session and MongoDB."""
    global integrated_system

    integrated_system.session_instances.append(measurement_data)
    integrated_system.all_measurements.append(measurement_data)

    # Bound memory growth in long sessions.
    if len(integrated_system.session_instances) > MAX_SESSION_MEASUREMENTS:
        integrated_system.session_instances = integrated_system.session_instances[-MAX_SESSION_MEASUREMENTS:]
    if len(integrated_system.all_measurements) > MAX_SESSION_MEASUREMENTS:
        integrated_system.all_measurements = integrated_system.all_measurements[-MAX_SESSION_MEASUREMENTS:]

    integrated_system.mongo_manager.store_height_weight_instance(
        measurement_data, integrated_system.user_email
    )

def _compute_mode_final(instances):
    """Compute final result using mode-based filtering from supplied measurements."""
    if not instances:
        return None

    heights_rounded = [round(inst['height_cm'] * 2) / 2 for inst in instances]
    weights_rounded = [round(inst['weight_kg'] * 2) / 2 for inst in instances]

    height_counts = Counter(heights_rounded)
    weight_counts = Counter(weights_rounded)

    most_common_height = height_counts.most_common(1)[0][0]
    most_common_weight = weight_counts.most_common(1)[0][0]

    common_instances = [
        inst for inst in instances
        if (abs(inst['height_cm'] - most_common_height) <= 1.0 and
            abs(inst['weight_kg'] - most_common_weight) <= 1.5)
    ]
    final_instances = common_instances if len(common_instances) >= 2 else instances

    final_height = float(np.mean([inst['height_cm'] for inst in final_instances]))
    final_weight = float(np.mean([inst['weight_kg'] for inst in final_instances]))
    height_uncertainty = float(np.std([inst['height_cm'] for inst in final_instances])) if len(final_instances) > 1 else 1.0
    weight_uncertainty = float(np.std([inst['weight_kg'] for inst in final_instances])) if len(final_instances) > 1 else 2.0
    avg_confidence = float(np.mean([inst['confidence_score'] for inst in final_instances]))
    bmi = final_weight / ((final_height / 100.0) ** 2) if final_height > 0 else 0.0

    return {
        "final_height_cm": round(final_height, 2),
        "final_weight_kg": round(final_weight, 2),
        "bmi": round(bmi, 2),
        "height_uncertainty": round(height_uncertainty, 2),
        "weight_uncertainty": round(weight_uncertainty, 2),
        "confidence_level": f"{avg_confidence * 100:.1f}%",
        "total_instances": len(final_instances)
    }

def _store_final_estimate_from_latest_samples():
    """Store final estimate from latest MIN_SUBMIT_SAMPLES measurements."""
    global integrated_system

    if not integrated_system:
        return None

    collected = len(integrated_system.session_instances)
    if collected < MIN_SUBMIT_SAMPLES:
        return None

    submit_samples = integrated_system.session_instances[-MIN_SUBMIT_SAMPLES:]
    final_data = _compute_mode_final(submit_samples)
    if not final_data:
        return None

    integrated_system.mongo_manager.store_final_estimate(final_data, integrated_system.user_email)
    integrated_system.final_estimate_data = final_data
    integrated_system.auto_final_saved = True
    integrated_system.auto_final_saved_count = collected
    return final_data

@height_weight_bp.route('/start_measurement')
def start_measurement():
    global is_recording, session_active, integrated_system
    
    try:
        # Get user email
        user = get_current_user()
        user_email = user['email']
        session['user_email'] = user_email
        
        # Initialize integrated system with SAME logic as desktop
        integrated_system = IntegratedHeightWeightSystem(
            use_gpu=False,  # Use CPU for web to avoid GPU conflicts
            calibration_file="camera_calibration.yaml",
            user_email=user_email
        )
        # Web sessions need faster automatic collection while user stands away from buttons.
        integrated_system.auto_save_enabled = True
        integrated_system.auto_save_cooldown = WEB_AUTOSAVE_COOLDOWN_SECONDS
        integrated_system.stability_threshold = 5
        integrated_system.last_web_auto_save = 0.0
        integrated_system.measurement_history.clear()
        integrated_system.session_instances.clear()
        integrated_system.all_measurements.clear()
        integrated_system.final_estimate_data = None
        integrated_system.auto_final_saved = False
        integrated_system.auto_final_saved_count = 0
        
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

        # Stop only: keep current collected measurements until explicit Submit.
        collected = len(integrated_system.session_instances) if integrated_system else 0
        return jsonify({'status': 'success', 'message': f'Camera stopped. Collected measurements: {collected}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/reset_measurement')
def reset_measurement():
    global session_active, is_recording, integrated_system
    
    try:
        # Reset should discard current session measurements (do not consider old values).
        if integrated_system:
            cleared_count = len(integrated_system.session_instances)
            integrated_system.session_instances.clear()
            integrated_system.all_measurements.clear()
            integrated_system.measurement_history.clear()
            integrated_system.stability_buffer.clear()
            integrated_system.consecutive_stable_frames = 0
            integrated_system.last_web_auto_save = 0.0
            integrated_system.last_auto_save = 0.0
            integrated_system.final_estimate_data = None
            integrated_system.auto_final_saved = False
            integrated_system.auto_final_saved_count = 0
        else:
            cleared_count = 0

        return jsonify({'status': 'success', 'message': f'Reset complete. Cleared {cleared_count} session measurements.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/save_measurement')
def save_measurement():
    """Save current measurement (S key functionality)"""
    global integrated_system
    
    try:
        if integrated_system and integrated_system.measurement_history:
            latest = integrated_system.measurement_history[-1]
            if _is_valid_measurement_result(latest):
                measurement_data = _build_measurement_data(latest)
                _append_session_measurement(measurement_data)
                return jsonify({'status': 'success', 'message': f'Saved! Total: {len(integrated_system.session_instances)}'})
        return jsonify({'status': 'error', 'message': 'No valid measurement'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/final_estimate')
def final_estimate():
    """Submit final result from required auto-collected valid measurements."""
    global integrated_system
    
    try:
        if not integrated_system:
            return jsonify({'status': 'error', 'message': 'System not initialized'})

        # If already auto-stored after threshold completion, return same final result.
        if getattr(integrated_system, 'auto_final_saved', False) and integrated_system.final_estimate_data:
            return jsonify({
                'status': 'success',
                'message': 'Final result already auto-stored.',
                'final_result': integrated_system.final_estimate_data
            })

        collected = len(integrated_system.session_instances)
        if collected < MIN_SUBMIT_SAMPLES:
            return jsonify({
                'status': 'error',
                'message': f'Need at least {MIN_SUBMIT_SAMPLES} valid auto-saved measurements before Submit. Current: {collected}'
            })

        # Use latest required valid measurements, then compute mode-based final estimate.
        final_data = _store_final_estimate_from_latest_samples()
        if not final_data:
            return jsonify({'status': 'error', 'message': 'Unable to compute submit result'})

        return jsonify({
            'status': 'success',
            'message': 'Submit successful. Final result stored.',
            'final_result': final_data
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@height_weight_bp.route('/toggle_autosave')
def toggle_autosave():
    """Auto-save is intentionally locked ON for unattended standing workflow."""
    global integrated_system
    
    try:
        if integrated_system:
            integrated_system.auto_save_enabled = True
            return jsonify({
                'status': 'success',
                'message': 'Auto-save is fixed ON by default for this flow.',
                'enabled': True,
                'locked': True
            })
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
            auto_finalized_now = False

            # Decode frame from browser
            img_data = base64.b64decode(data['image'].split(',')[1])
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is None or frame.size == 0:
                return

            # Keep UI overlays aligned with the real frame resolution from browser.
            frame_h, frame_w = frame.shape[:2]
            integrated_system.ui.frame_width = frame_w
            integrated_system.ui.frame_height = frame_h
            
            # Process using EXACT same logic as desktop version
            result = integrated_system.process_frame_integrated(frame)
            integrated_system.measurement_history.append(result)
            if len(integrated_system.measurement_history) > 120:
                integrated_system.measurement_history = integrated_system.measurement_history[-120:]
            
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
            
            # Web auto-save: capture valid standing measurements without requiring button presses.
            if integrated_system.auto_save_enabled and _is_valid_measurement_result(result):
                current_time = time.time()
                last_web_auto_save = getattr(integrated_system, 'last_web_auto_save', 0.0)
                if current_time - last_web_auto_save >= WEB_AUTOSAVE_COOLDOWN_SECONDS:
                    measurement_data = _build_measurement_data(result)
                    _append_session_measurement(measurement_data)
                    integrated_system.last_web_auto_save = current_time
                    print(
                        f"AUTO-SAVED: H={measurement_data['height_cm']:.1f}cm, "
                        f"W={measurement_data['weight_kg']:.1f}kg "
                        f"(Total: {len(integrated_system.session_instances)})"
                    )

                    # Auto-store final estimate immediately after collecting required samples.
                    if (len(integrated_system.session_instances) >= MIN_SUBMIT_SAMPLES and
                        not getattr(integrated_system, 'auto_final_saved', False)):
                        final_data = _store_final_estimate_from_latest_samples()
                        if final_data:
                            auto_finalized_now = True
                            print(
                                f"AUTO-FINAL-SAVED: H={final_data['final_height_cm']:.2f}cm, "
                                f"W={final_data['final_weight_kg']:.2f}kg, "
                                f"Samples={MIN_SUBMIT_SAMPLES}, User={integrated_system.user_email}"
                            )
            
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
                    'calibrated': integrated_system.camera_calibration.is_calibrated,
                    'auto_saved_count': len(integrated_system.session_instances),
                    'ready_to_submit': len(integrated_system.session_instances) >= MIN_SUBMIT_SAMPLES,
                    'auto_finalized': auto_finalized_now
                }
            })
            
        except Exception as e:
            print(f"Error processing height/weight frame: {e}")
            emit('error', {'message': str(e)})
    
    return handle_height_weight_frame
