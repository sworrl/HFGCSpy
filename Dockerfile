# HFGCSpy/Dockerfile
# Version: 1.0.1 # Version bump for robust pyrtlsdr installation

FROM debian:bookworm-slim

# Install system dependencies required for rtl-sdr and Python
# librtlsdr-dev is crucial for pyrtlsdr to compile and link correctly
RUN apt update && apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    libusb-1.0-0-dev \
    rtl-sdr \
    librtlsdr-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ldconfig # Update shared library cache after installing librtlsdr-dev

# Set working directory inside the container
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Create Python virtual environment and install dependencies
# IMPORTANT: Explicitly activate venv and set PATH for subsequent commands
RUN python3 -m venv venv && \
    . venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Set environment variables for the virtual environment for all subsequent commands
ENV VIRTUAL_ENV=/app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy the rest of the application code
COPY . .

# Create persistent data directories that will be mounted as a Docker volume
# These paths must match the container-side paths in config.ini
RUN mkdir -p /app/data/hfgcspy_data/recordings \
             /app/logs \
             /app/data/online_sdr_data # For future online SDR data if needed

# Expose the port Flask/Gunicorn will listen on
EXPOSE 8002

# Define the command to run your Flask app with Gunicorn
# Gunicorn will automatically use the python from the PATH (which is now our venv)
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8002", "api_server:app"]
