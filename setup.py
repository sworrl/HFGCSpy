# HFGCSpy/setup.py
# Python-based installer for HFGCSpy application.
# This script handles all installation, configuration, and service management.
# Version: 2.1.0 # Major version bump for fully automated Docker installation

import os
import sys
import subprocess
import configparser
import shutil
import re
import argparse

# Import constants from the new constants.py file
try:
    # Add current directory to path to allow importing constants.py
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from constants import (
        HFGCSPY_REPO, HFGCSPY_SERVICE_NAME, HFGCSPY_DOCKER_IMAGE_NAME,
        HFGCSPY_DOCKER_CONTAINER_NAME, HFGCSpy_INTERNAL_PORT,
        APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT, DOCKER_VOLUME_NAME
    )
except ImportError as e:
    print(f"ERROR: Could not import constants.py. Make sure it's in the same directory as setup.py. Error: {e}")
    sys.exit(1)


# --- Script Version ---
__version__ = "2.1.0" # Updated version


# --- Global Path Variables (Initialized to None, will be set by _set_global_paths_runtime) ---
# These are the variables that will hold the *actual* paths during script execution.
# They are declared here, and their concrete values (derived from defaults or user input)
# will be assigned ONLY within the _set_global_paths_runtime function.
HFGCSpy_APP_DIR = None 
HFGCSpy_VENV_DIR = None # Not used for host-side venv anymore, but kept for consistency
HFGCSpy_CONFIG_FILE = None

WEB_ROOT_DIR = None
HFGCSPY_DATA_DIR = None
HFGCSPY_RECORDINGS_PATH = None
HFGCSPY_CONFIG_JSON_PATH = None


# --- Helper Functions ---

def log_info(message):
    print(f"\n\033[0;32mINFO: {message}\033[0m") # Green text for info

def log_warn(message):
    print(f"\n\033[0;33mWARNING: {message}\033[0m") # Yellow text for warnings

def log_error(message, exit_code=1):
    print(f"\n\033[0;31mERROR: {message}\033[0m") # Red text for errors
    sys.exit(exit_code)

def ask_yes_no(question):
    while True:
        response = input(f"{question} (y/n): ").lower().strip()
        if response == 'y':
            return True
        elif response == 'n':
            return False
        else:
            print("Please answer y or n.")

def run_command(command, check_return=True, capture_output=False, shell=False):
    log_info(f"Executing: {' '.join(command) if isinstance(command, list) else command}")
    try:
        if isinstance(command, list) and (command[0] == sys.executable or command[0].endswith("/python3") or command[0].endswith("/pip")): 
             result = subprocess.run(command, check=check_return, capture_output=capture_output, text=True)
        else:
            result = subprocess.run(command, check=check_return, capture_output=capture_output, text=True, shell=shell)
        if capture_output:
            return result.stdout.strip()
        return result
    except subprocess.CalledProcessError as e:
        log_error(f"Command failed with exit code {e.returncode}.\nStderr: {e.stderr}\nStdout: {e.stdout}")
    except FileNotFoundError:
        log_error(f"Command not found: {command[0] if isinstance(command, list) else command.split(' ')[0]}")
    except Exception as e:
        log_error(f"An unexpected error occurred while running command: {e}")

def check_root():
    if os.geteuid() != 0:
        log_error("This script must be run with sudo. Please run: sudo python3 setup.py --install") # Updated command for user

# --- Path Management Functions ---

def _set_global_paths_runtime(app_dir_val, web_root_dir_val):
    """
    Calculates and updates all global path variables based on the provided
    app and web root directories.
    This function should be called explicitly in main() after base paths are determined.
    """
    global HFGCSpy_APP_DIR, HFGCSpy_VENV_DIR, HFGCSpy_CONFIG_FILE
    global WEB_ROOT_DIR, HFGCSpy_DATA_DIR, HFGCSpy_RECORDINGS_PATH, HFGCSpy_CONFIG_JSON_PATH

    HFGCSpy_APP_DIR = app_dir_val
    HFGCSpy_VENV_DIR = os.path.join(HFGCSpy_APP_DIR, "venv") # Still defined, but not used by Docker app directly
    HFGCSpy_CONFIG_FILE = os.path.join(HFGCSpy_APP_DIR, "config.ini")
    
    WEB_ROOT_DIR = web_root_dir_val
    HFGCSpy_DATA_DIR = os.path.join(WEB_ROOT_DIR, "hfgcspy_data")
    HFGCSPY_RECORDINGS_PATH = os.path.join(HFGCSpy_DATA_DIR, "recordings")
    HFGCSPY_CONFIG_JSON_PATH = os.path.join(HFGCSpy_DATA_DIR, "config.json")

def _load_paths_from_config():
    """Attempts to load installed paths from config.ini into global variables."""
    # This function will call _update_global_paths_runtime once it has determined the base directories.
    
    config_read = configparser.ConfigParser()
    installed_config_path = os.path.join(APP_DIR_DEFAULT, "config.ini") # Use constant APP_DIR_DEFAULT 

    if os.path.exists(installed_config_path):
        try:
            config_read.read(installed_config_path)
            # Database path is absolute, use it to deduce installed app_dir
            # For Dockerized app, database_path in config.ini is now relative to container's /app
            # So we need to derive host path from WEB_ROOT_DIR
            app_dir_from_config = APP_DIR_DEFAULT # Assume app is always cloned to default host path

            web_root_dir_from_config = WEB_ROOT_DIR_DEFAULT # Default fallback
            if config_read.has_section('app_paths') and config_read.has_option('app_paths', 'status_file'):
                full_status_path = config_read.get('app_paths', 'status_file')
                match = re.search(r"^(.*)/hfgcspy_data/status\.json$", full_status_path)
                if match:
                    web_root_dir_from_config = match.group(1)
                else:
                    log_warn(f"Could not reliably deduce WEB_ROOT_DIR from status_file path in config.ini: {full_status_path}. Using default.")
            else:
                log_warn("app_paths section or status_file option missing in config.ini. Using default WEB_ROOT_DIR.")

            # If app_dir_from_config is empty (e.g., config.ini is minimal or old), use default base
            if not app_dir_from_config: app_dir_from_config = APP_DIR_DEFAULT

            _set_global_paths_runtime(app_dir_from_config, web_root_dir_from_config)
            log_info(f"Loaded install paths from config: App='{HFGCSpy_APP_DIR}', Web='{WEB_ROOT_DIR}'")
            return True # Paths loaded successfully
        except configparser.Error as e:
            log_warn(f"Error reading config.ini for paths: {e}. Falling back to default paths.")
            _set_global_paths_runtime(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) # Ensure paths are reset to defaults
            return False
    else:
        log_warn("config.ini not found at default app directory. Using default paths.")
        _set_global_paths_runtime(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) # Ensure paths are set even if config not found
        return False

# --- Installation Steps ---

def prompt_for_paths():
    # No prompts for paths as per new requirements. Use defaults.
    log_info(f"Using default application installation directory: {APP_DIR_DEFAULT}")
    log_info(f"Using default web UI hosting directory: {WEB_ROOT_DIR_DEFAULT}")
    
    # Update global paths with defaults (no user input)
    _set_global_paths_runtime(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT)

def install_docker():
    log_info("Installing Docker Engine...")
    # Add Docker's official GPG key
    run_command("sudo mkdir -p /etc/apt/keyrings", shell=True)
    run_command("curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg", shell=True)

    # Set up the stable Docker repository
    docker_repo_line = f"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable"
    run_command(f"echo \"{docker_repo_line}\" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null", shell=True)
    
    run_command("apt update", shell=True)
    run_command("apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin", shell=True)

    log_info("Adding current user to 'docker' group to run Docker commands without sudo (requires logout/login)...")
    current_user = os.getenv("SUDO_USER") or os.getlogin() # Get original user
    run_command(f"usermod -aG docker {current_user}", shell=True)
    log_info("Docker installed. Please log out and log back in, or reboot, for Docker group changes to take effect.")
    log_info("You can then run 'docker run hello-world' to test Docker installation.")


def install_system_dependencies():
    log_info("Updating package lists and installing core system dependencies...")
    run_command("apt update", shell=True)
    run_command([
        "apt", "install", "-y", 
        "git", "python3", "python3-venv", "build-essential", # python3-pip, curl, gnupg, lsb-release already handled by Docker install
        "libusb-1.0-0-dev", "libatlas-base-dev", "libopenblas-dev", "net-tools", "apache2"
    ])

    log_info("Installing rtl-sdr tools...")
    run_command(["apt", "install", "-y", "rtl-sdr"])
    
    log_info("Blacklisting conflicting DVB-T kernel modules...")
    blacklist_conf = "/etc/modprobe.d/blacklist-rtl.conf"
    with open(blacklist_conf, "w") as f:
        f.write("blacklist dvb_usb_rtl28xxu\n")
        f.write("blacklist rtl2832\n")
        f.write("blacklist rtl2830\n")
    run_command("depmod -a", shell=True)
    run_command("update-initramfs -u", shell=True)
    log_info("Conflicting kernel modules blacklisted. A reboot might be required for this to take effect.")

def clone_hfgcspy_app_code(): # Renamed from clone_and_setup_venv
    log_info(f"Cloning HFGCSpy application from GitHub to {HFGCSpy_APP_DIR}...")
    if os.path.exists(HFGCSpy_APP_DIR):
        log_warn(f"HFGCSpy directory {HFGCSpy_APP_DIR} already exists. Skipping clone. Use --uninstall first if you want a fresh install.")
        return False # Indicate no fresh clone
    else:
        run_command(["git", "clone", HFGCSpy_REPO, HFGCSpy_APP_DIR]) # HFGCSpy_REPO is global constant
    
    # Removed host-side venv setup and pip install. Dockerfile handles this.
    log_info("Python virtual environment and dependencies will be set up inside the Docker image.")
    return True # Indicate fresh clone

def build_and_run_docker_container():
    log_info(f"Building Docker image '{HFGCSPY_DOCKER_IMAGE_NAME}' for HFGCSpy...")
    current_dir = os.getcwd()
    os.chdir(HFGCSpy_APP_DIR) # Change to app dir to build Dockerfile
    run_command(f"docker build -t {HFGCSPY_DOCKER_IMAGE_NAME} .", shell=True)
    os.chdir(current_dir) # Change back

    log_info(f"Stopping and removing any existing Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}'...")
    run_command(f"docker stop {HFGCSPY_DOCKER_CONTAINER_NAME}", shell=True, check_return=False)
    run_command(f"docker rm {HFGCSPY_DOCKER_CONTAINER_NAME}", shell=True, check_return=False)

    log_info(f"Creating Docker volume '{DOCKER_VOLUME_NAME}' for persistent data...")
    run_command(f"docker volume create {DOCKER_VOLUME_NAME}", shell=True, check_return=False) # check_return=False if volume might exist

    log_info(f"Running Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' for HFGCSpy...")
    # Mount config.ini from host into container for easy editing
    # Mount the data volume for DB and recordings
    # Pass SDR device
    # Map internal Flask port to a host port (e.g., 8002) for Apache2 proxy
    run_command([
        "docker", "run", "-d",
        "--name", HFGCSPY_DOCKER_CONTAINER_NAME,
        "--restart", "unless-stopped",
        "--device", "/dev/bus/usb:/dev/bus/usb", # Pass SDR device
        "-p", f"127.0.0.1:{HFGCSpy_INTERNAL_PORT}:{HFGCSpy_INTERNAL_PORT}", # Map internal port to localhost on host
        "-v", f"{HFGCSpy_CONFIG_FILE}:/app/config.ini:ro", # Mount config.ini read-only
        "-v", f"{DOCKER_VOLUME_NAME}:/app/data", # Mount data volume
        HFGCSPY_DOCKER_IMAGE_NAME
    ])
    log_info(f"Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' started.")


def configure_hfgcspy_app():
    log_info("Configuring HFGCSpy application settings (config.ini on host)...")
    os.makedirs(os.path.dirname(HFGCSpy_CONFIG_FILE), exist_ok=True) # Ensure app dir exists for config
    
    if not os.path.exists(HFGCSpy_CONFIG_FILE):
        template_path = os.path.join(HFGCSpy_APP_DIR, "config.ini.template")
        if os.path.exists(template_path):
            log_info(f"Copying {os.path.basename(template_path)} to {os.path.basename(HFGCSpy_CONFIG_FILE)}.")
            shutil.copyfile(template_path, HFGCSpy_CONFIG_FILE)
        else:
            log_error(f"config.ini.template not found in {HFGCSpy_APP_DIR}. Cannot proceed with app configuration.")
    else:
        log_info("Existing config.ini found. Using existing configuration. Please verify it points to correct paths.")

    # Update app_paths section in config.ini dynamically from current install paths
    config_obj = configparser.ConfigParser()
    config_obj.read(HFGCSpy_CONFIG_FILE)

    if not config_obj.has_section('app_paths'):
        config_obj.add_section('app_paths')
    if not config_obj.has_section('app'):
        config_obj.add_section('app')

    config_obj.set('app', 'mode', 'standalone') # Ensure mode is standalone
    config_obj.set('app', 'database_path', "/app/data/hfgcspy.db") # Path inside Docker container
    config_obj.set('app', 'internal_port', HFGCSpy_INTERNAL_PORT) # Internal port for Flask

    # These paths are now relative to the container's /app directory,
    # as they are accessed by the Python app *inside* the container.
    # The Docker volume mount handles the host-side persistence.
    config_obj.set('app_paths', 'status_file', os.path.join(HFGCSpy_DATA_DIR, "status.json"))
    config_obj.set('app_paths', 'messages_file', os.path.join(HFGCSpy_DATA_DIR, "messages.json"))
    config_obj.set('app_paths', 'recordings_dir', HFGCSpy_RECORDINGS_PATH) # Recordings dir is directly served
    config_obj.set('app_paths', 'config_json_file', os.path.join(HFGCSpy_DATA_DIR, "config.json"))

    if not config_obj.has_section('logging'):
        config_obj.add_section('logging')
    config_obj.set('logging', 'log_file', "/app/logs/hfgcspy.log") # Log file inside container

    with open(HFGCSpy_CONFIG_FILE, 'w') as f:
        config_obj.write(f)
    log_info(f"Paths in config.ini updated: {HFGCSpy_CONFIG_FILE}")

    # Set up user/group ownership for app directory on host for proper file access by service
    # This is for the cloned repo on the host, not inside Docker
    hfgcs_user = os.getenv("SUDO_USER") or "pi" 
    log_info(f"Setting ownership of {HFGCSpy_APP_DIR} to {hfgcs_user}...")
    run_command(["chown", "-R", f"{hfgcs_user}:{hfgcs_user}", HFGCSpy_APP_DIR])
    run_command(["chmod", "-R", "u+rwX,go-w", HFGCSpy_APP_DIR]) 

    # Create web-accessible data directories on HOST and set permissions for Apache
    log_info(f"Creating web-accessible data directories on host: {HFGCSpy_DATA_DIR} and {HFGCSpy_RECORDINGS_PATH}.")
    os.makedirs(HFGCSpy_DATA_DIR, exist_ok=True)
    os.makedirs(HFGCSpy_RECORDINGS_PATH, exist_ok=True)
    run_command(["chown", "-R", "www-data:www-data", HFGCSpy_DATA_DIR])
    run_command(["chmod", "-R", "775", HFGCSpy_DATA_DIR]) # Allow www-data read/write, others read/execute

    log_info("HFGCSpy application configured.")

def configure_apache2_webui():
    log_info("Configuring Apache2 to serve HFGCSpy's web UI and proxy to Docker container...")

    log_info("Ensuring Apache2 is installed and enabled...")
    try:
        run_command(["systemctl", "is-active", "--quiet", "apache2"])
    except subprocess.CalledProcessError:
        log_info("Apache2 not running. Installing...")
        run_command(["apt", "install", "-y", "apache2"])
        run_command(["systemctl", "enable", "apache2"])
        run_command(["systemctl", "start", "apache2"])
    
    log_info("Enabling Apache2 modules: headers, ssl, proxy, proxy_http...")
    run_command("a2enmod headers ssl proxy proxy_http", shell=True, check_return=False)

    log_info(f"Copying HFGCSpy web UI files to Apache web root: {WEB_ROOT_DIR}")
    if os.path.exists(WEB_ROOT_DIR):
        log_warn(f"Existing web UI directory {WEB_ROOT_DIR} found. Removing contents before copying new files.")
        shutil.rmtree(WEB_ROOT_DIR) 
    os.makedirs(WEB_ROOT_DIR, exist_ok=True)
    
    # Copy contents of web_ui directory
    src_web_ui_dir = os.path.join(HFGCSpy_APP_DIR, "web_ui")
    for item in os.listdir(src_web_ui_dir):
        s = os.path.join(src_web_ui_dir, item)
        d = os.path.join(WEB_ROOT_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    # Ensure Apache has correct ownership/permissions
    run_command(["chown", "-R", "www-data:www-data", WEB_ROOT_DIR])
    run_command(["chmod", "-R", "755", WEB_ROOT_DIR])

    server_ip = run_command(["hostname", "-I"], capture_output=True).split()[0]
    # Automated SSL certificate selection
    ssl_cert_path = ""
    ssl_key_path = ""
    use_ssl = False
    ssl_domain = ""

    letsencrypt_base_dir = "/etc/letsencrypt/live"
    le_domains = []
    if os.path.exists(letsencrypt_base_dir):
        try:
            result = run_command(["find", letsencrypt_base_dir, "-maxdepth", "1", "-mindepth", "1", "-type", "d", "-printf", "%P\n"], capture_output=True)
            le_domains = [d for d in result.splitlines() if d and d != 'README']
        except Exception as e:
            log_warn(f"Could not list Let's Encrypt domains: {e}. Proceeding without SSL auto-config.")
            le_domains = []
        
        if len(le_domains) == 1:
            ssl_domain = le_domains[0]
            ssl_cert_path = os.path.join(letsencrypt_base_dir, ssl_domain, "fullchain.pem")
            ssl_key_path = os.path.join(letsencrypt_base_dir, ssl_domain, "privkey.pem")
            use_ssl = True
            log_info(f"Automatically selected single Let's Encrypt certificate for domain: {ssl_domain}")
        elif len(le_domains) > 1:
            log_info(f"Detected multiple Let's Encrypt certificates: {', '.join(le_domains)}")
            if ask_yes_no("Do you want to configure HFGCSpy web UI to use HTTPS with one of these certificates?"):
                use_ssl = True
                print("Available domains with certificates:")
                for i, domain in enumerate(le_domains):
                    print(f"{i+1}) {domain}")
                
                while True:
                    try:
                        choice = int(input("Enter the number of the domain to use: "))
                        if 1 <= choice <= len(le_domains):
                            ssl_domain = le_domains[choice - 1]
                            ssl_cert_path = os.path.join(letsencrypt_base_dir, ssl_domain, "fullchain.pem")
                            ssl_key_path = os.path.join(letsencrypt_base_dir, ssl_domain, "privkey.pem")
                            break
                        else:
                            print("Invalid number. Please try again.")
                    except ValueError:
                        print("Invalid input. Please enter a number.")
            else:
                log_info("Skipping HTTPS configuration via Let's Encrypt.")
        else:
            log_info("No Let's Encrypt certificates found. HTTPS will not be automatically configured.")
    else:
        log_info(f"Let's Encrypt directory {letsencrypt_base_dir} not found. HTTPS will not be automatically configured.")


    # Generate Apache config content
    # ProxyPass /hfgcspy-api/ will forward to the Docker container's Flask API
    # DocumentRoot /hfgcspy will serve the static files
    apache_conf_content = f"""
<VirtualHost *:80>
    ServerName {server_name}
    DocumentRoot {WEB_ROOT_DIR}

    <Directory {WEB_ROOT_DIR}>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    Alias /hfgcspy-api/ http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/ # Proxy to Docker container's Flask API
    <Location /hfgcspy-api/>
        ProxyPass http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/
        ProxyPassReverse http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/
    </Location>

    # Alias for data directory (status.json, messages.json, recordings)
    Alias /hfgcspy_data "{HFGCSpy_DATA_DIR}"
    <Directory "{HFGCSpy_DATA_DIR}">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ErrorLog ${{APACHE_LOG_DIR}}/hfgcspy_webui_error.log
    CustomLog ${{APACHE_LOG_DIR}}/hfgcspy_webui_access.log combined
</VirtualHost>
"""
    if use_ssl and os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        apache_conf_content += f"""
<VirtualHost *:443>
    ServerName {server_name}
    DocumentRoot {WEB_ROOT_DIR}

    <Directory {WEB_ROOT_DIR}>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ProxyPass /hfgcspy-api/ http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/
    ProxyPassReverse /hfgcspy-api/ http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/

    # Alias for data directory
    Alias /hfgcspy_data "{HFGCSpy_DATA_DIR}"
    <Directory "{HFGCSpy_DATA_DIR}">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ErrorLog ${{APACHE_LOG_DIR}}/hfgcspy_webui_ssl_error.log
    CustomLog ${{APACHE_LOG_DIR}}/hfgcspy_webui_ssl_access.log combined

    SSLEngine on
    SSLCertificateFile "{ssl_cert_path}"
    SSLCertificateKeyFile "{ssl_key_path}"
"""
        chain_path = os.path.join(letsencrypt_base_dir, ssl_domain, "chain.pem")
        if os.path.exists(chain_path) and ssl_cert_path != os.path.join(letsencrypt_base_dir, ssl_domain, "fullchain.pem"):
             apache_conf_content += f"    SSLCertificateChainFile \"{chain_path}\"\n"
        
        apache_conf_content += """
    # HSTS (optional, highly recommended for security)
    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
</VirtualHost>
"""
        log_info(f"Apache2 SSL configuration included for {ssl_domain}.")
    else:
        log_info("HTTPS will not be configured automatically. Web UI will be available via HTTP only.")

    with open(apache_conf_path, "w") as f:
        f.write(apache_conf_content)

    run_command(["a2dissite", "000-default.conf"], check_return=False)
    run_command(["a2ensite", os.path.basename(apache_conf_path)])
    
    run_command(["systemctl", "restart", "apache2"])
    log_info("Apache2 configured and restarted to serve HFGCSpy web UI.")
    log_info(f"Access HFGCSpy at http://{server_name}/hfgcspy (and https://{server_name}/hfgcspy if SSL was configured).")


def setup_systemd_service():
    log_info("Setting up HFGCSpy as a systemd service...")
    
    hfgcs_user = os.getenv("SUDO_USER")
    if not hfgcs_user:
        hfgcs_user = "pi" 
        log_warn(f"SUDO_USER environment variable not set. Defaulting HFGCSpy service user to '{hfgcs_user}'. Please confirm this is correct or manually adjust.")

    service_file_path = f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"
    service_content = f"""
[Unit]
Description=HFGCSpy SDR Scanner and Parser (Docker Container)
After=network.target docker.service
Requires=docker.service

[Service]
ExecStart=/usr/bin/docker start -a {HFGCSPY_DOCKER_CONTAINER_NAME}
ExecStop=/usr/bin/docker stop {HFGCSPY_DOCKER_CONTAINER_NAME}
ExecReload=/usr/bin/docker restart {HFGCSPY_DOCKER_CONTAINER_NAME}
Restart=always
User={hfgcs_user} # User to run docker commands (must be in docker group)

[Install]
WantedBy=multi-user.target
"""
    with open(service_file_path, "w") as f:
        f.write(service_content)
    
    run_command(["systemctl", "daemon-reload"])
    
    if ask_yes_no("Do you want HFGCSpy Docker container to start automatically at machine boot? (Recommended: Yes)"):
        run_command(["systemctl", "enable", HFGCSPY_SERVICE_NAME])
        log_info("HFGCSpy Docker service enabled to start automatically at boot.")
    else:
        run_command(["systemctl", "disable", HFGCSPY_SERVICE_NAME])
        log_info(f"HFGCSpy Docker service will NOT start automatically at boot. You'll need to start it manually: sudo systemctl start {HFGCSPY_SERVICE_NAME}")

    # Start the Docker container via systemd
    run_command(["systemctl", "start", HFGCSPY_SERVICE_NAME])
    log_info("HFGCSpy Docker service setup and started.")

def update_hfgcspy_app_code():
    log_info("Stopping HFGCSpy Docker container for update...")
    run_command(["systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    
    if not os.path.exists(HFGCSpy_APP_DIR):
        log_error(f"HFGCSpy application directory {HFGCSpy_APP_DIR} not found. Please run --install first.")
    
    log_info(f"Pulling latest changes from HFGCSpy repository in {HFGCSpy_APP_DIR}...")
    current_dir = os.getcwd() 
    os.chdir(HFGCSpy_APP_DIR) 
    run_command(["git", "pull"])
    os.chdir(current_dir) 
    
    log_info(f"Rebuilding Docker image '{HFGCSPY_DOCKER_IMAGE_NAME}' with latest code...")
    run_command(f"docker build -t {HFGCSPY_DOCKER_IMAGE_NAME} {HFGCSpy_APP_DIR}", shell=True)

    log_info(f"Re-copying web UI files to Apache web root: {WEB_ROOT_DIR}...")
    if os.path.exists(WEB_ROOT_DIR):
        shutil.rmtree(WEB_ROOT_DIR) 
    os.makedirs(WEB_ROOT_DIR, exist_ok=True)
    src_web_ui_dir = os.path.join(HFGCSpy_APP_DIR, "web_ui")
    for item in os.listdir(src_web_ui_dir):
        s = os.path.join(src_web_ui_dir, item)
        d = os.path.join(WEB_ROOT_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    run_command(["chown", "-R", "www-data:www-data", WEB_ROOT_DIR])
    run_command(["chmod", "-R", "755", WEB_ROOT_DIR])
    
    log_info(f"Restarting HFGCSpy Docker service {HFGCSPY_SERVICE_NAME}...")
    run_command(["systemctl", "start", HFGCSPY_SERVICE_NAME])
    log_info("HFGCSpy updated and restarted.")
    log_info("Remember to restart Apache2 if there were any issues or config changes: sudo systemctl restart apache2")

def check_sdr():
    log_info("Checking for RTL-SDR dongle presence on host system...")
    try:
        run_command(["which", "rtl_test"], check_return=True, capture_output=True)
        log_info("rtl_test command found. Running test...")
        # Execute rtl_test and capture output for 5 seconds
        result = run_command(["timeout", "5s", "rtl_test", "-t", "-s", "1M", "-d", "0", "-r"], capture_output=True, text=True, check_return=False)
        
        if "Found" in result.stdout:
            log_info("RTL-SDR dongle detected and appears to be working.")
        else:
            log_warn("No RTL-SDR dongle detected or it's not working correctly.")
            log_warn("Ensure your RTL-SDR is plugged in and the blacklisting of DVB-T modules has taken effect (may require reboot).")
        log_info("Full rtl_test output:\n" + result.stdout + result.stderr)
    except subprocess.CalledProcessError as e:
        log_warn(f"rtl_test command failed: {e.stderr}. Please ensure rtl-sdr tools are properly installed.")
    except FileNotFoundError:
        log_warn("rtl_test not found. It should have been installed. Please ensure build-essential and rtl-sdr packages are installed.")
    except Exception as e:
        log_error(f"An unexpected error occurred during SDR check: {e}")


def uninstall_hfgcspy():
    log_warn(f"Stopping and disabling HFGCSpy Docker service {HFGCSPY_SERVICE_NAME}...")
    run_command(["systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    run_command(["systemctl", "disable", HFGCSPY_SERVICE_NAME], check_return=False)
    if os.path.exists(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"):
        os.remove(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}")
    run_command("systemctl daemon-reload", shell=True)
    
    log_warn(f"Stopping and removing Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}'...")
    run_command(f"docker stop {HFGCSPY_DOCKER_CONTAINER_NAME}", shell=True, check_return=False)
    run_command(f"docker rm {HFGCSPY_DOCKER_CONTAINER_NAME}", shell=True, check_return=False)

    log_warn(f"Removing Docker volume '{DOCKER_VOLUME_NAME}' (this will delete persistent data)...")
    run_command(f"docker volume rm {DOCKER_VOLUME_NAME}", shell=True, check_return=False)

    log_warn(f"Removing HFGCSpy application directory: {HFGCSpy_APP_DIR}...")
    if os.path.exists(HFGCSpy_APP_DIR):
        shutil.rmtree(HFGCSpy_APP_DIR)
    else:
        log_warn(f"HFGCSpy application directory {HFGCSpy_APP_DIR} not found. Skipping removal.")

    if os.path.exists(WEB_ROOT_DIR):
        log_warn(f"Removing Apache2 web UI directory: {WEB_ROOT_DIR}...")
        shutil.rmtree(WEB_ROOT_DIR)
    else:
        log_warn(f"Apache2 web UI directory {WEB_ROOT_DIR} not found. Skipping removal.")

    log_warn("Removing Apache2 configuration for HFGCSpy web UI (if it exists)...")
    run_command(["a2dissite", "hfgcspy.conf"], check_return=False)
    if os.path.exists("/etc/apache2/sites-available/hfgcspy.conf"):
        os.remove("/etc/apache2/sites-available/hfgcspy.conf")
    if os.path.exists("/etc/apache2/sites-enabled/hfgcspy.conf"):
        os.remove("/etc/apache2/sites-enabled/hfgcspy.conf")
    run_command(["systemctl", "restart", "apache2"], check_return=False)
    
    log_info("HFGCSpy uninstallation complete.")
    log_info("You may want to manually remove the DVB-T blacklisting file: /etc/modprobe.d/blacklist-rtl.conf")


# --- Main Script Logic ---

def main():
    log_info(f"HFGCSpy Installer (Version: {__version__})")

    parser = argparse.ArgumentParser(description=f"HFGCSpy Installer (Version: {__version__})")
    parser.add_argument('--install', action='store_true', help="Install HFGCSpy application and configure services.")
    parser.add_argument('--run', action='store_true', help="Run HFGCSpy main application directly (for debugging).")
    parser.add_argument('--stop', action='store_true', help="Stop HFGCSpy service.")
    parser.add_argument('--status', action='store_true', help="Check HFGCSpy and Apache2 service status.")
    parser.add_argument('--uninstall', action='store_true', help="Uninstall HFGCSpy application and associated files.")
    parser.add_argument('--update', action='store_true', help="Update HFGCSpy application code from Git and restart service.")
    parser.add_argument('--check_sdr', action='store_true', help="Check for RTL-SDR dongle presence.")
    
    args = parser.parse_args()

    # Call _set_global_paths_runtime initially with defaults.
    # This guarantees all global path variables are set to a baseline
    # using the module-level constants APP_DIR_DEFAULT and WEB_ROOT_DIR_DEFAULT.
    # This call must happen before any conditional logic that might use these globals
    _set_global_paths_runtime(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) 

    # If not performing a fresh install, attempt to load paths from existing config.ini
    # This will override the defaults set above if a config is found.
    if not args.install:
        _load_paths_from_config() # This function will call _update_global_paths_runtime with loaded paths


    # Process arguments
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.install:
        check_root()
        prompt_for_paths() # Prompt to get user-defined paths if installing (updates globals)
        install_docker() # Install Docker first
        install_system_dependencies() # Install other system deps (rtl-sdr, apache2, etc.)
        clone_hfgcspy_app_code() # Clone app code and setup venv (on host)
        configure_hfgcspy_app() # Configure config.ini on host
        build_and_run_docker_container() # Build image and run container
        configure_apache2_webui() # Configure Apache to proxy to container
        setup_systemd_service() # Setup systemd for Docker container
        log_info("HFGCSpy installation complete. Please consider rebooting your Raspberry Pi for full effect.")
    elif args.run:
        check_root() # Running main app requires root for SDR
        # This case is now for running the Docker container directly, not the Python script
        log_info(f"Attempting to run HFGCSpy Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' directly...")
        log_info(f"To manage as a service, use 'sudo systemctl start {HFGCSPY_SERVICE_NAME}'.")
        run_command(f"docker start -a {HFGCSPY_DOCKER_CONTAINER_NAME}", shell=True)
    elif args.stop:
        check_root()
        stop_hfgcspy()
    elif args.status:
        status_hfgcspy()
    elif args.uninstall:
        check_root()
        uninstall_hfgcspy()
    elif args.update:
        check_root()
        update_hfgcspy_app_code()
    elif args.check_sdr:
        check_sdr()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
