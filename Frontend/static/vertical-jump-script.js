class VerticalJumpTracker {
    constructor() {
        console.log('✅ WEBSOCKET VERSION LOADED - vertical-jump-script.js v2');
        this.isRunning = false;
        this.isStopping = false;
        this.isSaving = false;
        this.autoRedirectTriggered = false;
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
        this.saveBtn = document.getElementById('save-btn');
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
        this.saveBtn.addEventListener('click', () => this.saveResults());
        this.stopBtn.addEventListener('click', () => this.stopCamera({ autoRedirect: false }));
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
                this.autoRedirectTriggered = false;
                
                // Start WebSocket streaming
                window.webcamCapture.startStreaming('jump_frame');
                
                // Update UI
                this.videoFeed.style.display = 'block';
                this.placeholder.style.display = 'none';
                this.startBtn.disabled = true;
                this.saveBtn.disabled = false;
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

    async stopCamera(options = {}) {
        const { autoRedirect = false } = options;
        if (this.isStopping) return;
        this.isStopping = true;

        let stopResponse = null;
        try {
            const response = await fetch('/vertical_jump/stop_camera');
            stopResponse = await response.json().catch(() => ({}));
            window.webcamCapture.stopStreaming();
            
            this.isRunning = false;
            this.videoFeed.style.display = 'none';
            this.placeholder.style.display = 'flex';
            this.startBtn.disabled = false;
            this.saveBtn.disabled = true;
            this.stopBtn.disabled = true;
            this.stopTimer();
            this.stopStatsUpdate();

            if (
                autoRedirect &&
                !this.autoRedirectTriggered &&
                stopResponse &&
                stopResponse.status === 'success'
            ) {
                this.autoRedirectTriggered = true;
                if (this.sessionStatus) this.sessionStatus.textContent = 'Session completed - redirecting...';
                setTimeout(() => {
                    window.location.href = '/displayVerticalJump';
                }, 450);
            } else if (autoRedirect && stopResponse && stopResponse.status !== 'success') {
                const failureReason = stopResponse.message || 'Session save failed.';
                if (this.sessionStatus) this.sessionStatus.textContent = 'Save failed';
                alert(`Session completed but could not save results: ${failureReason}`);
            }
        } catch (error) {
            console.error('Stop error:', error);
            window.webcamCapture.stopStreaming();
            this.isRunning = false;
            this.startBtn.disabled = false;
            this.saveBtn.disabled = true;
            this.stopBtn.disabled = true;
            this.stopTimer();
            this.stopStatsUpdate();
        } finally {
            this.isStopping = false;
        }
    }

    async resetCounter() {
        try {
            if (this.isRunning) {
                await this.stopCamera({ autoRedirect: false });
            }
            
            const response = await fetch('/vertical_jump/reset_counter');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.resetTimer();
                this.saveBtn.disabled = true;
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

    async saveResults() {
        if (this.isSaving) return;
        if (!this.isRunning) {
            alert('Start the session before saving results.');
            return;
        }

        const jumpCountValue = Number.parseInt(this.jumpCount?.textContent || '0', 10);
        const maxHeightValue = Number.parseFloat((this.maxHeight?.textContent || '0').replace(' cm', ''));
        if (!Number.isFinite(jumpCountValue) || jumpCountValue <= 0 || !Number.isFinite(maxHeightValue) || maxHeightValue <= 0) {
            alert('No valid jump results to save yet. Complete at least one valid jump first.');
            return;
        }

        const previousLabel = this.saveBtn.textContent;
        this.isSaving = true;
        this.saveBtn.disabled = true;
        this.saveBtn.textContent = 'Saving...';

        try {
            const response = await fetch('/vertical_jump/save_results');
            const result = await response.json().catch(() => ({}));

            if (response.ok && result.status === 'success') {
                if (this.sessionStatus) this.sessionStatus.textContent = 'Results saved';
                alert('Results saved successfully.');
            } else {
                const reason = result.message || 'Unable to save results.';
                alert(reason);
            }
        } catch (error) {
            console.error('Save error:', error);
            alert('Error saving results: ' + error.message);
        } finally {
            this.isSaving = false;
            this.saveBtn.textContent = previousLabel;
            this.saveBtn.disabled = !this.isRunning;
        }
    }

    startTimer() {
        this.startTime = new Date();
        this.timeRemaining = 180;
        this.updateTimerDisplay();
        
        this.timerInterval = setInterval(() => {
            this.timeRemaining = Math.max(0, this.timeRemaining - 1);
            this.updateTimerDisplay();
            
            if (this.timeRemaining <= 0) {
                this.stopTimer();
                this.stopCamera({ autoRedirect: true });
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
