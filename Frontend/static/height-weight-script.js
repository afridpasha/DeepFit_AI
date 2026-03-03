class HeightWeightTracker {
    constructor() {
        console.log('✅ Height & Weight WebSocket Tracker Loaded');
        this.isRunning = false;
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.resetBtn = document.getElementById('reset-btn');
        this.videoFeed = document.getElementById('video-feed');
        this.placeholder = document.getElementById('placeholder');
        this.heightValue = document.getElementById('height-value');
        this.weightValue = document.getElementById('weight-value');
        this.bmiValue = document.getElementById('bmi-value');
        this.confidenceValue = document.getElementById('confidence-value');
        this.statusValue = document.getElementById('status-value');
    }

    bindEvents() {
        this.startBtn.addEventListener('click', () => this.startMeasurement());
        this.stopBtn.addEventListener('click', () => this.stopMeasurement());
        this.resetBtn.addEventListener('click', () => this.resetMeasurement());
    }

    async startMeasurement() {
        try {
            if (!window.webcamCapture) {
                alert('WebSocket system not loaded. Please refresh the page.');
                return;
            }
            
            const webcamReady = await window.webcamCapture.init();
            if (!webcamReady) {
                alert('Failed to access webcam. Please grant camera permissions.');
                return;
            }
            
            const response = await fetch('/height_weight/start_measurement');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.isRunning = true;
                window.webcamCapture.startStreaming('height_weight_frame');
                
                this.videoFeed.style.display = 'block';
                this.placeholder.style.display = 'none';
                this.startBtn.disabled = true;
                this.stopBtn.disabled = false;
            } else {
                alert('Failed to start: ' + data.message);
                window.webcamCapture.stopStreaming();
            }
        } catch (error) {
            console.error('Start error:', error);
            alert('Error starting measurement: ' + error.message);
            if (window.webcamCapture) {
                window.webcamCapture.stopStreaming();
            }
        }
    }

    async stopMeasurement() {
        try {
            await fetch('/height_weight/stop_measurement');
            window.webcamCapture.stopStreaming();
            
            this.isRunning = false;
            this.videoFeed.style.display = 'none';
            this.placeholder.style.display = 'flex';
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            
            alert('Measurement saved successfully!');
        } catch (error) {
            console.error('Stop error:', error);
            window.webcamCapture.stopStreaming();
            this.isRunning = false;
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
        }
    }

    async resetMeasurement() {
        try {
            if (this.isRunning) {
                await this.stopMeasurement();
            }
            
            const response = await fetch('/height_weight/reset_measurement');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.updateMeasurement({
                    height_cm: 0,
                    weight_kg: 0,
                    bmi: 0,
                    confidence: 0,
                    status: 'Ready'
                });
            }
        } catch (error) {
            console.error('Reset error:', error);
        }
    }

    updateMeasurement(measurement) {
        if (this.heightValue) this.heightValue.textContent = (measurement.height_cm || 0).toFixed(1) + ' cm';
        if (this.weightValue) this.weightValue.textContent = (measurement.weight_kg || 0).toFixed(1) + ' kg';
        if (this.bmiValue) this.bmiValue.textContent = (measurement.bmi || 0).toFixed(1);
        if (this.confidenceValue) this.confidenceValue.textContent = Math.round((measurement.confidence || 0) * 100) + '%';
        if (this.statusValue) this.statusValue.textContent = measurement.status || 'Ready';
    }
}

// WebSocket handler for height/weight
if (typeof io !== 'undefined') {
    const socket = io();
    
    socket.on('processed_height_weight_frame', (data) => {
        const videoFeed = document.getElementById('video-feed');
        if (videoFeed) {
            videoFeed.src = data.image;
            videoFeed.style.display = 'block';
        }
        
        if (window.heightWeightTracker && data.measurement) {
            window.heightWeightTracker.updateMeasurement(data.measurement);
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    window.heightWeightTracker = new HeightWeightTracker();
});
