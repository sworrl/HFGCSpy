# HFGCSpy/setup.py
# Python-based installer for HFGCSpy application.
# This script handles all installation, configuration, and service management.
# Version: 2.2.49 # Version bump for AttributeError fix in diagnose_and_fix_sdr_host

import os
import sys
import subprocess
import configparser
import shutil
import re
import argparse
import time # Import time module for sleep

# --- Script Version ---
__version__ = "2.2.49" # Updated version for AttributeError fix in diagnose_and_fix_sdr_host

# --- Configuration Constants (Defined directly in setup.py) ---
# All constants are now embedded directly in this file to avoid import issues.
HFGCSPY_REPO = "https://github.com/sworrl/HFGCSpy.git" # IMPORTANT: Ensure this is correct!
HFGCSPY_SERVICE_NAME = "hfgcspy_docker.service" # Service name is constant
HFGCSPY_DOCKER_IMAGE_NAME = "hfgcspy_image"
HFGCSPY_DOCKER_CONTAINER_NAME = "hfgcspy_app" 
HFGCSPY_INTERNAL_PORT = "8002" # Port for Flask/Gunicorn INSIDE Docker container

# Default installation paths on the HOST system
APP_DIR_DEFAULT = "/opt/hfgcspy" # Where the git repo is cloned on host
WEB_ROOT_DIR_DEFAULT = "/var/www/html/hfgcspy" # Where static web UI files are copied (still defined for consistency, but not used for Apache)
DOCKER_VOLUME_NAME = "hfgcspy_data_vol" # Docker volume for SQLite DB and recordings

# --- Global Path Variables (Initialized to None, will be set by _set_global_paths_runtime) ---
# These are the variables that will hold the *actual* paths during script execution.
# They are declared here, and their concrete values (derived from defaults or user input)
# will be assigned ONLY within the _set_global_paths_runtime function.
HFGCSpy_APP_DIR = None 
HFGCSpy_VENV_DIR = None 
HFGCSpy_CONFIG_FILE = None

WEB_ROOT_DIR = None # No longer directly used for serving, but kept for consistency with data paths
HFGCSPY_DATA_DIR = None
HFGCSPY_RECORDINGS_PATH = None
HFGCSPY_CONFIG_JSON_PATH = None


# --- Helper Functions (Ensured to be correctly defined and callable) ---

# Define colors for output globally
RED='\033[0;31m'
GREEN='\033[1;32m' # Light green for info
YELLOW='\033[0;33m'
CYAN='\033[1;36m' # Bold cyan for sections
NC='\033[0m' # No Color - MUST be defined globally for f-strings

def log_info(message):
    print(f"\n\033[1;32mINFO: {message}{NC}") # Light Green text for info

def log_warn(message):
    print(f"\n\033[0;33mWARNING: {message}{NC}") # Yellow text for warnings

def log_error(message, exit_code=1):
    print(f"\n\033[0;31mERROR: {message}{NC}") # Red text for errors
    sys.exit(exit_code)

def log_success(message):
    print(f"\n\033[1;32mSUCCESS: {message}{NC}") # Light Green text for success

def log_section(title):
    # Explicitly concatenate NC to ensure it's always part of the string literal
    print("\n\033[1;36m--- " + title + " ---" + NC) # Bold cyan for sections


def ask_yes_no(question, default_yes=True): # Modified to accept default
    while True:
        if default_yes:
            response = input(f"{question} (Y/n): ").lower().strip()
            if response == '' or response == 'y':
                return True
            elif response == 'n':
                return False
            else:
                print("Please answer Y or n.")
        else:
            response = input(f"{question} (y/N): ").lower().strip()
            if response == 'y':
                return True
            elif response == '' or response == 'n':
                return False
            else:
                print("Please answer y or N.")

def run_command(command, check_return=True, capture_output=False, shell=False):
    log_info(f"Executing: {' '.join(command) if isinstance(command, list) else command}")
    try:
        # Always capture output to display on error, regardless of capture_output flag
        result = subprocess.run(command, check=False, capture_output=True, text=True, shell=shell) 
        
        if check_return and result.returncode != 0:
            log_error(f"Command failed with exit code {result.returncode}.\nStderr: {result.stderr.strip()}\nStdout: {result.stdout.strip()}")
        
        # Always print stdout and stderr if not explicitly capturing output for return value
        if not capture_output:
            if result.stdout:
                print(result.stdout.strip())
            if result.stderr:
                print(result.stderr.strip())
        
        if capture_output:
            return result.stdout.strip()
        return result # Return the CompletedProcess object for non-captured output calls
    except subprocess.CalledProcessError as e:
        # This block might not be reached with check=False, but keep for robustness
        log_error(f"Command failed with exit code {e.returncode}.\nStderr: {e.stderr.strip()}\nStdout: {e.stdout.strip()}")
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
    global WEB_ROOT_DIR, HFGCSpy_DATA_DIR, HFGCSPY_RECORDINGS_PATH, HFGCSPY_CONFIG_JSON_PATH

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

def diagnose_and_fix_sdr_host():
    log_info("Starting host-level SDR diagnostic and fix process.")
    
    # --- Initial SDR Hardware Detection on Host ---
    log_section("Initial SDR Hardware Detection on Host")
    log_info("Checking if SDR is detected by USB (lsusb).")
    run_command(["lsusb"])

    log_info("Running initial rtl_test -t to confirm 'PLL not locked!' status.")
    # Now, rtl_test_result is directly the string output
    # The run_command function now returns the string output directly when capture_output=True
    rtl_test_output_str = run_command(["rtl_test", "-t"], capture_output=True, check_return=False)
    
    sdr_working_initially = True
    if "PLL not locked!" in rtl_test_output_str or "No devices found" in rtl_test_output_str: # Use string directly
        sdr_working_initially = False
        log_warn("Initial rtl_test reported problems ('PLL not locked!' or 'No devices found'). Attempting to fix.")
    else:
        log_success("Initial rtl_test ran successfully. SDR appears to be working on host.")
        return True # SDR is working, no need to proceed with fixes

    log_section("Checking dmesg for recent SDR-related Kernel Messages")
    log_info("Looking for messages from the last 50 lines.")
    run_command(["dmesg", "|", "tail", "-n", "50", "|", "grep", "-i", "rtl"], shell=True, check_return=False)
    run_command(["dmesg", "|", "tail", "-n", "50", "|", "grep", "-i", "dvb"], shell=True, check_return=False)

    log_section("Thorough Purge and Alternative Reinstallation of rtl-sdr Tools and Libraries")
    log_info("Purging existing rtl-sdr packages and development libraries.")
    run_command(["sudo", "apt-get", "remove", "--purge", "rtl-sdr", "librtlsdr-dev", "-y"], check_return=False)
    run_command(["sudo", "apt", "autoremove", "-y"])

    log_info("Updating package lists.")
    run_command(["sudo", "apt", "update", "-y"])

    log_info("Installing build dependencies for rtl-sdr-blog.")
    run_command(["sudo", "apt", "install", "cmake", "build-essential", "pkg-config", "debhelper", "-y"])

    log_info("Cloning rtl-sdr-blog repository.")
    if os.path.exists("rtl-sdr-blog"):
        log_warn("rtl-sdr-blog directory already exists. Removing and re-cloning.")
        shutil.rmtree("rtl-sdr-blog")
    run_command(["git", "clone", "https://github.com/rtlsdrblog/rtl-sdr-blog"])

    log_info("Building Debian packages from rtl-sdr-blog source.")
    current_dir = os.getcwd()
    os.chdir("rtl-sdr-blog")
    build_result = run_command(["sudo", "dpkg-buildpackage", "-b", "--no-sign"], check_return=False)
    if build_result.returncode != 0:
        log_error("Failed to build rtl-sdr-blog packages. Check build output above for details.")
    os.chdir(current_dir)

    log_info("Installing the newly built Debian packages.")
    deb_files = [f for f in os.listdir(".") if f.endswith(".deb") and ("librtlsdr0" in f or "librtlsdr-dev" in f or "rtl-sdr" in f)]
    if not deb_files:
        log_error("No .deb packages found after building rtl-sdr-blog. Build might have failed.")
    else:
        install_deb_result = run_command(["sudo", "dpkg", "-i"] + deb_files, check_return=False)
        if install_deb_result.returncode != 0:
            log_error("Failed to install some .deb packages. Check output above.")

    log_info("Cleaning up rtl-sdr-blog source directory.")
    if os.path.exists("rtl-sdr-blog"):
        shutil.rmtree("rtl-sdr-blog")

    log_section("Verifying and Reloading Kernel Module Blacklisting")
    BLACKLIST_FILE="/etc/modprobe.d/blacklist-rtl.conf"
    log_info(f"Checking content of {BLACKLIST_FILE}.")
    if os.path.exists(BLACKLIST_FILE):
        run_command(["cat", BLACKLIST_FILE])
        with open(BLACKLIST_FILE, 'r') as f:
            content = f.read()
            if not ("blacklist dvb_usb_rtl28xxu" in content and \
                    "blacklist rtl2832" in content and \
                    "blacklist rtl2830" in content):
                log_warn("Blacklist file exists but might be incomplete. Appending missing lines.")
                subprocess.run(['sudo', 'tee', '-a', BLACKLIST_FILE], input="blacklist dvb_usb_rtl28xxu\nblacklist rtl2832\nblacklist rtl2830\n", text=True, check=True)
            else:
                log_info("Blacklist file appears correctly configured.")
    else:
        log_warn(f"{BLACKLIST_FILE} not found. Creating it with necessary blacklists.")
        subprocess.run(['sudo', 'tee', BLACKLIST_FILE], input="blacklist dvb_usb_rtl28xxu\nblacklist rtl2832\nblacklist rtl2830\n", text=True, check=True)

    log_info("Updating kernel module dependencies (depmod -a) and initramfs (update-initramfs -u).")
    run_command(["sudo", "depmod", "-a"])
    run_command(["sudo", "update-initramfs", "-u"])

    log_section("Verifying and Reloading udev Rules for Device Permissions")
    UDEV_RULES_DIR="/etc/udev/rules.d/"
    UDEV_RULES_FILE="${UDEV_RULES_DIR}20-rtlsdr.rules" # Common name, sometimes 99-rtl-sdr.rules

    log_info(f"Checking existence and permissions of /etc/udev/.")
    run_command(["ls", "-ld", "/etc/udev/"], check_return=False)
    log_info(f"Checking existence and permissions of {UDEV_RULES_DIR}.")
    run_command(["ls", "-ld", UDEV_RULES_DIR], check_return=False)


    # Ensure the udev rules directory exists
    if not os.path.isdir(UDEV_RULES_DIR):
        log_warn(f"udev rules directory {UDEV_RULES_DIR} not found. Attempting to create it.")
        run_command(["sudo", "mkdir", "-p", UDEV_RULES_DIR])
    else:
        log_info(f"udev rules directory {UDEV_RULES_DIR} exists.")

    log_info(f"Checking for udev rules file: {UDEV_RULES_FILE}.")

    # Check if the common udev rules file exists or create a generic one
    if not os.path.exists(UDEV_RULES_FILE) and not os.path.exists(os.path.join(UDEV_RULES_DIR, "99-rtl-sdr.rules")):
        log_warn("No standard RTL-SDR udev rules file found. Creating a generic one.")
        log_info(f"Creating {UDEV_RULES_FILE} with basic read/write permissions for common RTL-SDRs.")
        udev_rules_content = """SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2832", MODE="0666", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="2838", MODE="0666", GROUP="plugdev", TAG+="uaccess"
""" # Add other common RTL-SDR dongle IDs if needed
        subprocess.run(['sudo', 'tee', UDEV_RULES_FILE], input=udev_rules_content, text=True, check=True)
        log_info("Created a new udev rules file.")
    else:
        log_info("RTL-SDR udev rules file already exists. Content (if found):")
        run_command(["cat", UDEV_RULES_FILE], check_return=False)
        run_command(["cat", os.path.join(UDEV_RULES_DIR, "99-rtl-sdr.rules")], check_return=False)

    log_info("Reloading udev rules and triggering device re-scan.")
    run_command(["sudo", "udevadm", "control", "--reload-rules"])
    run_command(["sudo", "udevadm", "trigger"])

    log_section("Verifying Current User's Group Membership")
    CURRENT_USER = os.getenv("SUDO_USER") or os.getlogin()
    log_info(f"Checking groups for current user ({CURRENT_USER}).")
    user_groups_output = run_command(["groups", CURRENT_USER], capture_output=True)
    print(user_groups_output)

    if "plugdev" not in user_groups_output:
        log_warn(f"User '{CURRENT_USER}' is NOT in the 'plugdev' group.")
        log_info(f"Attempting to add user '{CURRENT_USER}' to the 'plugdev' group.")
        run_command(["sudo", "usermod", "-aG", "plugdev", CURRENT_USER])
        log_warn("IMPORTANT: Please LOG OUT and LOG BACK IN (or REBOOT) for the group changes to take full effect!")
    else:
        log_info(f"User '{CURRENT_USER}' is already in the 'plugdev' group.")

    log_section("Final Test After Host-Level Fixes")
    log_info("Running rtl_test -t again to confirm SDR is now working on the host.")
    final_rtl_test_result = run_command(["rtl_test", "-t"], capture_output=True, check_return=False)
    print(final_rtl_test_result.stdout)
    print(final_rtl_test_result.stderr)

    if "PLL not locked!" in final_rtl_test_result.stdout or "No devices found" in final_rtl_test_result.stdout:
        log_error("SDR troubleshooting failed: rtl_test still reported problems after fixes. "
                  "Please review the output carefully. A fresh OS reinstallation might be necessary for this Raspberry Pi.")
    else:
        log_success("SDR appears to be working on the host now!")
        log_warn("A system REBOOT is still highly recommended to ensure all kernel module and user group changes are fully applied.")
        return True # SDR is now working on the host

def install_docker():
    log_info("Checking if Docker Engine is already installed.")
    try:
        subprocess.run(["docker", "--version"], check=True, capture_output=True, text=True)
        log_info("Docker Engine detected. Skipping installation.")
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        log_info("Docker Engine not found. Proceeding with installation.")

    log_info("Installing Docker Engine.")
    run_command(["sudo", "mkdir", "-p", "/etc/apt/keyrings"])
    run_command(["curl", "-fsSL", "https://download.docker.com/linux/debian/gpg", "|", "sudo", "gpg", "--dearmor", "-o", "/etc/apt/keyrings/docker.gpg"], shell=True)

    docker_repo_line = "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable"
    run_command(["echo", docker_repo_line, "|", "sudo", "tee", "/etc/apt/sources.list.d/docker.list", ">", "/dev/null"], shell=True)
    
    run_command(["sudo", "apt", "update"])
    run_command(["sudo", "apt", "install", "-y", "docker-ce", "docker-ce-cli", "containerd.io", "docker-buildx-plugin", "docker-compose-plugin"])

    log_info("Adding current user to 'docker' group to run Docker commands without sudo (requires logout/login).")
    current_user = os.getenv("SUDO_USER") or os.getlogin()
    run_command(["sudo", "usermod", "-aG", "docker", current_user])
    log_info("Docker installed. Please log out and log back in, or reboot, for Docker group changes to take effect.")
    log_info("You can then run 'docker run hello-world' to test Docker installation.")


def install_system_dependencies():
    log_info("Updating package lists and installing core system dependencies.")
    run_command(["sudo", "apt", "update"])
    run_command([
        "sudo", "apt", "install", "-y", 
        "git", "python3", "python3-venv", "build-essential", 
        "libusb-1.0-0-dev", "libatlas-base-dev", "libopenblas-dev", "net-tools"
    ])

    log_info("Installing rtl-sdr tools (apt version).")
    run_command(["sudo", "apt", "install", "-y", "rtl-sdr"])
    
    log_info("Blacklisting conflicting DVB-T kernel modules.")
    blacklist_conf = "/etc/modprobe.d/blacklist-rtl.conf"
    if not os.path.exists(blacklist_conf):
        log_warn(f"{blacklist_conf} not found. Creating it.")
        subprocess.run(['sudo', 'tee', blacklist_conf], input="blacklist dvb_usb_rtl28xxu\nblacklist rtl2832\nblacklist rtl2830\n", text=True, check=True)
    else:
        log_info(f"{blacklist_conf} already exists.")
    run_command(["sudo", "depmod", "-a"])
    run_command(["sudo", "update-initramfs", "-u"])
    log_info("Conflicting kernel modules blacklisted. A reboot might be required for this to take effect.")

def clone_hfgcspy_app_code():
    log_info(f"Cloning HFGCSpy application from GitHub to {HFGCSpy_APP_DIR}.")
    if os.path.exists(HFGCSpy_APP_DIR):
        log_warn(f"HFGCSpy directory {HFGCSpy_APP_DIR} already exists. Wiping contents for dev install.")
        shutil.rmtree(HFGCSpy_APP_DIR)
    
    run_command(["git", "clone", HFGCSPY_REPO, HFGCSpy_APP_DIR])
    
    log_info(f"Verifying contents of cloned directory: {HFGCSpy_APP_DIR}.")
    run_command(["ls", "-l", HFGCSpy_APP_DIR], shell=False)
    
    log_info("Python virtual environment and dependencies will be set up inside the Docker image.")
    return True

def build_and_run_docker_container():
    os.system('clear') 
    log_info(f"Building Docker image '{HFGCSPY_DOCKER_IMAGE_NAME}' for HFGCSpy.")
    current_dir = os.getcwd()
    os.chdir(HFGCSpy_APP_DIR) 
    
    req_path = os.path.join(HFGCSpy_APP_DIR, "requirements.txt")
    with open(req_path, "a") as f:
        f.write(f"\n# Build-time unique identifier: {time.time()}\n")

    run_command(["sudo", "docker", "build", "--no-cache", "-t", HFGCSPY_DOCKER_IMAGE_NAME, "."])
    os.chdir(current_dir) 

    log_info(f"Stopping and removing any existing Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}'.")
    run_command(["sudo", "docker", "stop", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)
    run_command(["sudo", "docker", "rm", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)

    log_info(f"Creating Docker volume '{DOCKER_VOLUME_NAME}' for persistent data.")
    run_command(["sudo", "docker", "volume", "create", DOCKER_VOLUME_NAME], check_return=False)

    log_info(f"Running Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' for HFGCSpy.")
    run_command([
        "sudo", "docker", "run", "-d",
        "--name", HFGCSPY_DOCKER_CONTAINER_NAME,
        "--restart", "unless-stopped",
        "--device", "/dev/bus/usb:/dev/bus/usb",
        "-p", f"127.0.0.1:{HFGCSPY_INTERNAL_PORT}:{HFGCSPY_INTERNAL_PORT}",
        "-v", f"{HFGCSpy_CONFIG_FILE}:/app/config.ini:ro",
        "-v", f"{DOCKER_VOLUME_NAME}:/app/data",
        HFGCSPY_DOCKER_IMAGE_NAME
    ])
    log_info(f"Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' started.")

    log_info(f"Verifying Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' is running.")
    time.sleep(10) 
    container_status_output = run_command(["sudo", "docker", "inspect", "-f", '{{.State.Status}}', HFGCSPY_DOCKER_CONTAINER_NAME], capture_output=True)
    container_status = container_status_output.strip()
    log_info(f"Container '{HFGCSPY_DOCKER_CONTAINER_NAME}' status: {container_status}")

    if container_status == "running":
        log_info(f"Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' is active and running.")
    else:
        log_error(f"Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' is not running. Current status: {container_status}. "
                  f"Please check container logs for details: 'docker logs {HFGCSPY_DOCKER_CONTAINER_NAME}'")
        log_info(f"Displaying Docker container logs for '{HFGCSPY_DOCKER_CONTAINER_NAME}':")
        run_command(["sudo", "docker", "logs", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)


def configure_hfgcspy_app():
    log_info("Configuring HFGCSpy application settings (config.ini on host).")
    os.makedirs(os.path.dirname(HFGCSpy_CONFIG_FILE), exist_ok=True) 
    
    if not os.path.exists(HFGCSpy_CONFIG_FILE):
        template_path = os.path.join(HFGCSpy_APP_DIR, "config.ini.template")
        if os.path.exists(template_path):
            log_info(f"Copying {os.path.basename(template_path)} to {os.path.basename(HFGCSpy_CONFIG_FILE)}.")
            shutil.copyfile(template_path, HFGCSpy_CONFIG_FILE)
        else:
            log_error(f"config.ini.template not found in {HFGCSpy_APP_DIR}. Cannot proceed with app configuration.")
    else:
        log_info("Existing config.ini found. Using existing configuration. Please verify it points to correct paths.")

    config_obj = configparser.ConfigParser()
    config_obj.read(HFGCSpy_CONFIG_FILE)

    if not config_obj.has_section('app_paths'):
        config_obj.add_section('app_paths')
    if not config_obj.has_section('app'):
        config_obj.add_section('app')

    config_obj.set('app', 'mode', str('standalone'))
    config_obj.set('app', 'database_path', str("/app/data/hfgcspy.db"))
    config_obj.set('app', 'internal_port', str(HFGCSPY_INTERNAL_PORT)) 
    
    config_obj.set('app_paths', 'status_file', str(os.path.join(HFGCSpy_DATA_DIR, "status.json")))
    config_obj.set('app_paths', 'messages_file', str(os.path.join(HFGCSpy_DATA_DIR, "messages.json")))
    config_obj.set('app_paths', 'recordings_dir', str(HFGCSPY_RECORDINGS_PATH))
    config_obj.set('app_paths', 'config_json_file', str(os.path.join(HFGCSpy_DATA_DIR, "config.json")))

    if not config_obj.has_section('logging'):
        config_obj.add_section('logging')
    config_obj.set('logging', 'log_file', str("/app/logs/hfgcspy.log"))

    with open(HFGCSpy_CONFIG_FILE, 'w') as f:
        config_obj.write(f)
    log_info(f"Paths in config.ini updated: {HFGCSpy_CONFIG_FILE}")

    hfgcs_user = os.getenv("SUDO_USER") or os.getlogin() 
    log_info(f"Setting ownership of {HFGCSpy_APP_DIR} to {hfgcs_user}.")
    run_command(["sudo", "chown", "-R", f"{hfgcs_user}:{hfgcs_user}", HFGCSpy_APP_DIR])
    run_command(["sudo", "chmod", "-R", "u+rwX,go-w", HFGCSpy_APP_DIR]) 

    log_info(f"Creating web-accessible data directories on host: {HFGCSpy_DATA_DIR} and {HFGCSPY_RECORDINGS_PATH}.")
    os.makedirs(HFGCSpy_DATA_DIR, exist_ok=True)
    os.makedirs(HFGCSPY_RECORDINGS_PATH, exist_ok=True)
    run_command(["sudo", "chown", "-R", "www-data:www-data", HFGCSpy_DATA_DIR])
    run_command(["sudo", "chmod", "-R", "775", HFGCSpy_DATA_DIR])

    log_info("HFGCSpy application configured.")

def setup_systemd_service():
    log_info("Setting up HFGCSpy as a systemd service.")
    
    hfgcs_user = os.getenv("SUDO_USER")
    if not hfgcs_user:
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
    
    run_command(["sudo", "systemctl", "daemon-reload"])
    
    if ask_yes_no("Do you want HFGCSpy Docker container to start automatically at machine boot?", default_yes=True):
        run_command(["sudo", "systemctl", "enable", HFGCSPY_SERVICE_NAME])
        log_info("HFGCSpy Docker service enabled to start automatically at boot.")
    else:
        run_command(["sudo", "systemctl", "disable", HFGCSPY_SERVICE_NAME])
        log_info(f"HFGCSpy Docker service will NOT start automatically at boot. You'll need to start it manually: sudo systemctl start {HFGCSPY_SERVICE_NAME}")

    run_command(["sudo", "systemctl", "start", HFGCSPY_SERVICE_NAME])
    log_info("HFGCSpy Docker service setup and started.")

def update_hfgcspy_app_code():
    log_info("Stopping HFGCSpy Docker container for update.")
    run_command(["sudo", "systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    
    if not os.path.exists(HFGCSpy_APP_DIR):
        log_error(f"HFGCSpy application directory {HFGCSpy_APP_DIR} not found. Please run --install first.")
    
    log_info(f"Pulling latest changes from {HFGCSPY_REPO} in {HFGCSpy_APP_DIR}.")
    current_dir = os.getcwd() 
    os.chdir(HFGCSpy_APP_DIR) 
    run_command(["git", "pull"])
    os.chdir(current_dir) 
    
    log_info(f"Rebuilding Docker image '{HFGCSPY_DOCKER_IMAGE_NAME}' with latest code.")
    run_command(["sudo", "docker", "build", "-t", HFGCSPY_DOCKER_IMAGE_NAME, HFGCSPY_APP_DIR])

    log_info(f"Restarting HFGCSpy Docker service {HFGCSPY_SERVICE_NAME}.")
    run_command(["sudo", "systemctl", "start", HFGCSPY_SERVICE_NAME])
    log_info("HFGCSpy updated and restarted.")

def check_sdr():
    log_info("Checking for RTL-SDR dongle presence on host system.")
    try:
        run_command(["which", "rtl_test"], check_return=True, capture_output=True)
        log_info("rtl_test command found. Running test.")
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
    log_warn(f"Stopping and disabling HFGCSpy Docker service {HFGCSPY_SERVICE_NAME}.")
    run_command(["sudo", "systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    run_command(["sudo", "systemctl", "disable", HFGCSPY_SERVICE_NAME], check_return=False)
    if os.path.exists(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"):
        os.remove(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}")
    run_command(["sudo", "systemctl", "daemon-reload"])
    
    log_warn(f"Stopping and removing Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}'.")
    run_command(["sudo", "docker", "stop", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)
    run_command(["sudo", "docker", "rm", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)

    log_warn(f"Removing Docker volume '{DOCKER_VOLUME_NAME}' (this will delete persistent data).")
    run_command(["sudo", "docker", "volume", "rm", DOCKER_VOLUME_NAME], check_return=False)

    log_warn(f"Removing HFGCSpy application directory: {HFGCSpy_APP_DIR}.")
    if os.path.exists(HFGCSpy_APP_DIR):
        shutil.rmtree(HFGCSpy_APP_DIR)
    else:
        log_warn(f"HFGCSpy application directory {HFGCSpy_APP_DIR} not found. Skipping removal.")
    
    log_info("HFGCSpy uninstallation complete.")
    log_info("You may want to manually remove the DVB-T blacklisting file: /etc/modprobe.d/blacklist-rtl.conf")

def stop_hfgcspy():
    log_info(f"Stopping HFGCSpy Docker service {HFGCSPY_SERVICE_NAME}.")
    run_command(["sudo", "systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    log_info("HFGCSpy service stopped.")

def status_hfgcspy():
    log_info("Checking HFGCSpy Docker service status.")
    run_command(["sudo", "systemctl", "status", HFGCSPY_SERVICE_NAME], shell=True)


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

    _set_global_paths_runtime(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) 

    if not args.install:
        _load_paths_from_config() 

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.install:
        check_root()
        install_docker()
        install_system_dependencies()
        clone_hfgcspy_app_code()
        configure_hfgcspy_app()
        
        log_section("SDR Host-Level Diagnosis and Fix")
        sdr_fixed = diagnose_and_fix_sdr_host()
        if not sdr_fixed:
            log_error("SDR could not be fixed on the host system. Please resolve this manually before proceeding with HFGCSpy installation.")

        build_and_run_docker_container()
        setup_systemd_service()
        log_info("HFGCSpy installation complete. Please consider rebooting your Raspberry Pi for full effect.")

        log_info("\n--- HFGCSpy Access Information ---")
        log_info(f"Web UI (via Docker directly): http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/")
        log_info(f"Docker API (local only for debugging): http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/hfgcspy-api/status")
        
        log_info("\n--- Post-Installation Diagnostic Report ---")
        log_info(f"Verifying Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' status...")
        container_status_output = run_command(["sudo", "docker", "inspect", "-f", '{{.State.Status}}', HFGCSPY_DOCKER_CONTAINER_NAME], capture_output=True)
        container_status = container_status_output.strip()
        log_info(f"Container '{HFGCSPY_DOCKER_CONTAINER_NAME}' status: {container_status}")

        log_info("\nShowing active Docker containers ('docker ps'):")
        run_command(["sudo", "docker", "ps"], check_return=False)

        log_info(f"\nShowing Docker container stats for '{HFGCSPY_DOCKER_CONTAINER_NAME}' ('docker stats --no-stream'):")
        run_command(["sudo", "docker", "stats", HFGCSPY_DOCKER_CONTAINER_NAME, "--no-stream"], check_return=False)

        log_info(f"\nShowing listening ports on host ('sudo netstat -tulnp | grep {HFGCSPY_INTERNAL_PORT}'):")
        run_command(["sudo", "netstat", "-tulnp", "|", "grep", str(HFGCSPY_INTERNAL_PORT)], shell=True, check_return=False)

        log_info(f"\nAttempting curl to Web UI root (http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/):")
        run_command(["curl", f"http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/"], check_return=False)

        log_info(f"\nAttempting curl to API status (http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/hfgcspy-api/status):")
        run_command(["curl", f"http://127.0.0.1:{HFGCSPY_INTERNAL_PORT}/hfgcspy-api/status"], check_return=False)
        
        log_info("\n--- Docker Application Logs (last 50 lines) ---")
        run_command(["sudo", "docker", "logs", "--tail", "50", HFGCSPY_DOCKER_CONTAINER_NAME], check_return=False)
        log_info("--- End Docker Application Logs ---")

        log_info("\n**IMPORTANT:** Please review the 'Post-Installation Diagnostic Report' above carefully.")
        log_info("If the container status is 'restarting' or 'exited', the application has failed to start.")
        log_info("The detailed application logs are displayed above this message. This is the key to debugging.")
        log_info("----------------------------------")

    elif args.run:
        check_root()
        log_info(f"Attempting to run HFGCSpy Docker container '{HFGCSPY_DOCKER_CONTAINER_NAME}' directly.")
        log_info(f"To manage as a service, use 'sudo systemctl start {HFGCSPY_SERVICE_NAME}'.")
        run_command(["sudo", "docker", "start", "-a", HFGCSPY_DOCKER_CONTAINER_NAME])
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
