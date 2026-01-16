FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY Backend/ ./Backend/
COPY Frontend/ ./Frontend/
COPY Datasets/ ./Datasets/

# Create necessary directories
RUN mkdir -p Backend/logs Backend/uploads Backend/measurements Backend/jump_data Backend/validation_results

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Note: .env file should be in Backend/ folder or use HuggingFace Secrets
# HuggingFace will inject environment variables automatically

WORKDIR /app/Backend

# Expose HuggingFace default port
EXPOSE 7860

# Run the application
CMD ["python", "app.py"]
