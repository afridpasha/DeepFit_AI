class DumbbellTracker {
    constructor() {
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
        this.leftReps = document.getElementById('left-reps');
        this.rightReps = document.getElementById('right-reps');
        this.totalReps = document.getElementById('total-reps');
        this.estimatedWeight = document.getElementById('estimated-weight');
        this.leftStatus = document.getElementById('left-status');
        this.rightStatus = document.getElementById('right-status');
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
            const webcamReady = await window.webcamCapture.init();
            if (!webcamReady) {
                alert('Failed to access webcam. Please grant camera permissions.');
                return;
            }
            
            const response = await fetch('/dumbbell/start_camera');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.isRunning = true;
                window.webcamCapture.startStreaming('dumbbell_frame');
                
                this.videoFeed.style.display = 'block';
                this.placeholder.style.display = 'none';
                this.startBtn.disabled = true;
                this.stopBtn.disabled = false;
                this.startTimer();
                this.startStatsUpdate();
            } else {
                alert('Failed to start: ' + data.message);
                window.webcamCapture.stopStreaming();
            }
        } catch (error) {
            console.error('Start error:', error);
            alert('Error: ' + error.message);
            window.webcamCapture.stopStreaming();
        }
    }

    async stopCamera() {
        try {
            await fetch('/dumbbell/stop_camera');
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
            
            const response = await fetch('/dumbbell/reset_counter');
            const data = await response.json();
            
            if (data.status === 'success') {
                this.resetTimer();
                this.updateStats({
                    left_reps: 0,
                    right_reps: 0,
                    total_reps: 0,
                    estimated_weight: 0,
                    left_status: 'Not visible',
                    right_status: 'Not visible'
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
                    const response = await fetch('/dumbbell/get_stats');
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
        if (this.leftReps) this.leftReps.textContent = stats.left_reps || 0;
        if (this.rightReps) this.rightReps.textContent = stats.right_reps || 0;
        if (this.totalReps) this.totalReps.textContent = stats.total_reps || 0;
        if (this.estimatedWeight) this.estimatedWeight.textContent = (stats.estimated_weight || 0) + ' kg';
        if (this.leftStatus) this.leftStatus.textContent = stats.left_status || 'Not visible';
        if (this.rightStatus) this.rightStatus.textContent = stats.right_status || 'Not visible';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new DumbbellTracker();
});

window.addEventListener('beforeunload', async () => {
    try {
        await fetch('/dumbbell/cleanup', { method: 'POST' });
    } catch (error) {
        console.log('Cleanup error:', error);
    }
});
