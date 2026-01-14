// Client-side webcam capture and WebSocket communication
console.log('✅ WEBSOCKET WEBCAM CAPTURE LOADED - webcam-capture.js v2');
const socket = io();

let videoElement = null;
let canvasElement = null;
let localStream = null;
let isStreaming = false;
let frameInterval = null;
let isProcessing = false; // Prevent frame queue buildup

// Initialize webcam capture
async function initWebcam() {
    try {
        videoElement = document.createElement('video');
        videoElement.autoplay = true;
        videoElement.playsInline = true;
        
        canvasElement = document.createElement('canvas');
        
        // Request webcam access with optimized settings
        localStream = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 480 },  // Reduced from 640
                height: { ideal: 360 }, // Reduced from 480
                facingMode: 'user',
                frameRate: { ideal: 15, max: 20 } // Limit frame rate
            },
            audio: false
        });
        
        videoElement.srcObject = localStream;
        
        await new Promise((resolve) => {
            videoElement.onloadedmetadata = () => {
                videoElement.play();
                resolve();
            };
        });
        
        return true;
    } catch (error) {
        console.error('Error accessing webcam:', error);
        alert('Unable to access webcam. Please ensure camera permissions are granted.');
        return false;
    }
}

// Start streaming frames to server
function startFrameStreaming(eventName = 'video_frame') {
    if (isStreaming) return;
    
    isStreaming = true;
    isProcessing = false;
    
    // Send frames at 5 FPS (every 200ms) - REDUCED from 10 FPS
    frameInterval = setInterval(() => {
        if (!videoElement || !isStreaming) return;
        
        // Skip frame if previous frame still processing
        if (isProcessing) {
            console.log('Skipping frame - server busy');
            return;
        }
        
        isProcessing = true;
        
        // Set canvas size to match video
        canvasElement.width = videoElement.videoWidth;
        canvasElement.height = videoElement.videoHeight;
        
        // Draw current video frame to canvas
        const ctx = canvasElement.getContext('2d');
        ctx.drawImage(videoElement, 0, 0);
        
        // Convert canvas to base64 image with reduced quality
        const imageData = canvasElement.toDataURL('image/jpeg', 0.6); // Reduced from 0.8
        
        // Send frame to server via WebSocket
        socket.emit(eventName, { image: imageData });
    }, 200); // Changed from 100ms to 200ms (5 FPS)
}

// Stop streaming
function stopFrameStreaming() {
    isStreaming = false;
    isProcessing = false;
    
    if (frameInterval) {
        clearInterval(frameInterval);
        frameInterval = null;
    }
    
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }
}

// Display processed frame from server
function displayProcessedFrame(imageData) {
    const videoFeed = document.getElementById('video-feed');
    if (videoFeed) {
        videoFeed.src = imageData;
        videoFeed.style.display = 'block';
        
        const placeholder = document.getElementById('placeholder');
        if (placeholder) {
            placeholder.style.display = 'none';
        }
    }
    
    // Mark processing complete
    isProcessing = false;
}

// Update stats display
function updateStatsDisplay(stats) {
    const repsElement = document.getElementById('reps-count');
    if (repsElement && stats.reps !== undefined) {
        repsElement.textContent = stats.reps;
    }
    
    const totalRepsElement = document.getElementById('total-reps');
    if (totalRepsElement && stats.total_reps !== undefined) {
        totalRepsElement.textContent = stats.total_reps;
    }
    
    const formElement = document.getElementById('form-percentage');
    if (formElement && stats.form_percentage !== undefined) {
        formElement.textContent = stats.form_percentage + '%';
    }
    
    const feedbackElement = document.getElementById('feedback');
    if (feedbackElement && stats.feedback) {
        feedbackElement.textContent = stats.feedback;
    }
    
    const jumpCountElement = document.getElementById('jump-count');
    if (jumpCountElement && stats.total_jumps !== undefined) {
        jumpCountElement.textContent = stats.total_jumps;
    }
    
    const maxHeightElement = document.getElementById('max-height');
    if (maxHeightElement && stats.max_height !== undefined) {
        maxHeightElement.textContent = stats.max_height.toFixed(1) + ' cm';
    }
}

// Situp-specific handlers
socket.on('processed_frame', (data) => {
    displayProcessedFrame(data.image);
    updateStatsDisplay(data.stats);
});

// Dumbbell-specific handlers
socket.on('processed_dumbbell_frame', (data) => {
    displayProcessedFrame(data.image);
    updateStatsDisplay(data.stats);
});

// Vertical jump-specific handlers
socket.on('processed_jump_frame', (data) => {
    displayProcessedFrame(data.image);
    updateStatsDisplay(data.stats);
});

// Height/Weight-specific handlers
socket.on('processed_height_weight_frame', (data) => {
    displayProcessedFrame(data.image);
    if (data.measurement) {
        // Update measurement display
        const heightEl = document.getElementById('height-value');
        const weightEl = document.getElementById('weight-value');
        const bmiEl = document.getElementById('bmi-value');
        const confidenceEl = document.getElementById('confidence-value');
        const statusEl = document.getElementById('status-value');
        
        if (heightEl) heightEl.textContent = (data.measurement.height_cm || 0).toFixed(1) + ' cm';
        if (weightEl) weightEl.textContent = (data.measurement.weight_kg || 0).toFixed(1) + ' kg';
        if (bmiEl) bmiEl.textContent = (data.measurement.bmi || 0).toFixed(1);
        if (confidenceEl) confidenceEl.textContent = Math.round((data.measurement.confidence || 0) * 100) + '%';
        if (statusEl) statusEl.textContent = data.measurement.status || 'Ready';
    }
});

// Error handler
socket.on('error', (data) => {
    console.error('WebSocket error:', data.message);
    isProcessing = false; // Reset on error
});

// Export functions for use in page-specific scripts
window.webcamCapture = {
    init: initWebcam,
    startStreaming: startFrameStreaming,
    stopStreaming: stopFrameStreaming
};
