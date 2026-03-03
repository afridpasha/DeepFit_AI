---
title: DeepFit AI
emoji: 💪
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

# DeepFit AI - AI-Powered Fitness Assessment System

## 🎯 Overview

DeepFit is an advanced AI-powered fitness assessment platform developed for the Sports Authority of India (SAI). Using cutting-edge computer vision and machine learning, it provides accurate, real-time fitness assessments through a simple webcam.

## ✨ Features

- **📏 Height & Weight Estimation**: AI-based body measurement using single camera
- **💪 Exercise Tracking**: Real-time tracking of Situps, Dumbbell Curls, and Vertical Jumps
- **📊 Performance Analytics**: Comprehensive fitness dashboards and progress tracking
- **🎯 Dynamic Benchmarks**: Personalized fitness goals based on athlete data
- **🏆 Leaderboard**: Competitive rankings based on performance metrics

## 🚀 Technology Stack

- **Backend**: Flask, MongoDB Atlas
- **AI/ML**: MediaPipe, OpenCV, PyTorch, MiDaS
- **Frontend**: HTML5, CSS3, JavaScript

## 🔧 Configuration

This Space requires the following environment variables (add in Settings → Variables):

- `MONGODB_URI`: Your MongoDB Atlas connection string
- `DB_NAME`: Database name (default: sih2573)
- `PORT`: Application port (default: 7860)
- `FLASK_DEBUG`: Debug mode (default: False)

## 📚 Documentation

For complete documentation, see the project repository.

## 👥 Team

Developed for Smart India Hackathon 2024
**Problem Statement by:** Sports Authority of India (SAI)

## 📄 License

MIT License
