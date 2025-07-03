# HFGCSpy/Dockerfile
# Version: 2.0.0

# Use a slim Debian-based image for smaller size
FROM debian:bookworm-slim

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED 1

# Install system dependencies
RUN apt update && apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    libusb-1.0-0-dev \
    rtl-sdr \
    # Add other libs if needed for specific decoders later (e.g., for sound processing)
    # libatlas-base-dev \
    # libopenblas-dev \
    # alsa-utils \
    # sox \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN python3 -m venv venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Create necessary runtime directories inside the container
RUN mkdir -p /app/data/hfgcspy_data/recordings \
           /app/logs \
           /app/data/online_sdr_data # For future online SDR data if needed

# Expose the internal Flask/Gunicorn port
EXPOSE 8002

# Command to run the application
# Use gunicorn to serve the Flask API (api_server.py)
# The hfgcs.py script will run its SDR logic in a background thread
CMD ["/app/venv/bin/gunicorn", "--workers", "1", "--bind", "0.0.0.0:8002", "api_server:app"]

# Alternative CMD if you want hfgcs.py to be the direct entrypoint and manage Flask internally
# CMD ["/app/venv/bin/python3", "hfgcs.py", "--run"]
