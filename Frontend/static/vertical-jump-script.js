class VerticalJumpTracker {
    constructor() {
        console.log('✅ WEBSOCKET VERSION LOADED - vertical-jump-script.js v2');
        this.isRunning = false;
        this.statsInterval = null;
        this.timerInterval = null;
        this.timeRemaining = 180;
        this.totalTime = 180;
        this.startTime = null;
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        this.startBtn = document.getElementById('start-btn');
        this.stopBtn = document.getElementById('stop-btn');
        this.resetBtn = document.getElementById('reset-btn');
        this.videoFeed = document.getElementById('video-feed');
        this.placeholder = document.getElementById('placeholder');
        this.jumpCount = document.getElementById('jump-count');
        this.currentHeight = document.getElementById('current-height');
        this.maxHeight = document.getElementById('max-height');
        this.jumpState = document.getElementById('jump-state');
        this.feedback = document.getElementById('feedback');
        this.calibrationStatus = document.getElementById('calibration-status');
        this.timerDisplay = document.getElementById('timer-display');
        this.sessionStatus = document.getElementById('session-status');
    }

    bindEvents() {
        this.startBtn.addEventListener('click', () => this.startCamera());
        this.stopBtn.addEventListener('click', () => this.stopCamera());
        this.resetBtn.addEventListener('click', () => this.resetCounter());
    }

    async startCamera() {
        try {
            // Initialize webcam first
            if (!window.webcamCapture) {
                alert('WebSocket system not loaded. Please refresh the page.');
                return;
            }
            
            const webcamReady = await window.webcamCapture.init();
            if (!webcamReady) {
                alert('Failed to access webcam. Please grant camera permissions.');
                return;
            }
            
            // Start backend session
            const response = await fetch('/vertical_jump/start_camera');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.isRunning = true;
                
                // Start WebSocket streaming
                window.webcamCapture.startStreaming('jump_frame');
                
                // Update UI
                this.videoFeed.style.display = 'block';
                this.placeholder.style.display = 'none';
                this.startBtn.disabled = true;
                this.stopBtn.disabled = false;
                
                // Start timer and stats
                this.startTimer();
                this.startStatsUpdate();
            } else {
                alert('Failed to start: ' + data.message);
                window.webcamCapture.stopStreaming();
            }
        } catch (error) {
            console.error('Start error:', error);
            alert('Error starting camera: ' + error.message);
            if (window.webcamCapture) {
                window.webcamCapture.stopStreaming();
            }
        }
    }

    async stopCamera() {
        try {
            await fetch('/vertical_jump/stop_camera');
            window.webcamCapture.stopStreaming();
            
            this.isRunning = false;
            this.videoFeed.style.display = 'none';
            this.placeholder.style.display = 'flex';
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            this.stopTimer();
            this.stopStatsUpdate();
        } catch (error) {
            console.error('Stop error:', error);
            window.webcamCapture.stopStreaming();
            this.isRunning = false;
            this.startBtn.disabled = false;
            this.stopBtn.disabled = true;
            this.stopTimer();
            this.stopStatsUpdate();
        }
    }

    async resetCounter() {
        try {
            if (this.isRunning) {
                await this.stopCamera();
            }
            
            const response = await fetch('/vertical_jump/reset_counter');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.resetTimer();
                this.updateStats({
                    total_jumps: 0,
                    current_height: 0,
                    max_height: 0,
                    state: 'GROUND',
                    calibrated: false,
                    feedback: 'System Ready'
                });
            }
        } catch (error) {
            console.error('Reset error:', error);
        }
    }

    startTimer() {
        this.startTime = new Date();
        this.timeRemaining = 180;
        this.updateTimerDisplay();
        
        this.timerInterval = setInterval(() => {
            this.timeRemaining--;
            this.updateTimerDisplay();
            
            if (this.timeRemaining <= 0) {
                this.stopCamera();
            }
        }, 1000);
        
        if (this.sessionStatus) this.sessionStatus.textContent = 'Session in progress';
    }

    stopTimer() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
        if (this.sessionStatus) this.sessionStatus.textContent = 'Session paused';
    }

    resetTimer() {
        this.stopTimer();
        this.timeRemaining = 180;
        this.totalTime = 180;
        this.startTime = null;
        this.updateTimerDisplay();
        if (this.sessionStatus) this.sessionStatus.textContent = 'Ready to start';
    }

    updateTimerDisplay() {
        if (!this.timerDisplay) return;
        
        const minutes = Math.floor(this.timeRemaining / 60);
        const seconds = this.timeRemaining % 60;
        this.timerDisplay.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
    }

    startStatsUpdate() {
        this.statsInterval = setInterval(async () => {
            if (this.isRunning) {
                try {
                    const response = await fetch('/vertical_jump/get_stats');
                    const stats = await response.json();
                    this.updateStats(stats);
                } catch (error) {
                    console.error('Stats error:', error);
                }
            }
        }, 500);
    }

    stopStatsUpdate() {
        if (this.statsInterval) {
            clearInterval(this.statsInterval);
            this.statsInterval = null;
        }
    }

    updateStats(stats) {
        if (this.jumpCount) this.jumpCount.textContent = stats.total_jumps || 0;
        if (this.currentHeight) this.currentHeight.textContent = (stats.current_height || 0).toFixed(1) + ' cm';
        if (this.maxHeight) this.maxHeight.textContent = (stats.max_height || 0).toFixed(1) + ' cm';
        if (this.jumpState) this.jumpState.textContent = stats.state || 'GROUND';
        if (this.feedback) this.feedback.textContent = stats.feedback || 'System Ready';
        if (this.calibrationStatus) {
            this.calibrationStatus.textContent = stats.calibrated ? 'Calibrated' : 'Calibrating...';
            this.calibrationStatus.className = stats.calibrated ? 'status-success' : 'status-warning';
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new VerticalJumpTracker();
});
