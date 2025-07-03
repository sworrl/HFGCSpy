# HFGCSpy/constants.py
# Version: 2.0.0

# --- Configuration Constants (Base values only) ---
HFGCSPY_REPO = "https://github.com/sworrl/HFGCSpy.git" # IMPORTANT: Ensure this is correct!
HFGCSPY_SERVICE_NAME = "hfgcspy_docker.service" # Service name is constant
HFGCSPY_DOCKER_IMAGE_NAME = "hfgcspy_image"
HFGCSPY_DOCKER_CONTAINER_NAME = "hfgcspy_app"
HFGCSPY_INTERNAL_PORT = "8002" # Port for Flask/Gunicorn INSIDE Docker container

# Default installation paths on the HOST system
APP_DIR_DEFAULT = "/opt/hfgcspy" # Where the git repo is cloned on host
WEB_ROOT_DIR_DEFAULT = "/var/www/html/hfgcspy" # Where static web UI files are copied
DOCKER_VOLUME_NAME = "hfgcspy_data_vol" # Docker volume for SQLite DB and recordings
