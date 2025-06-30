# HFGCSpy/setup.py
# Python-based installer for HFGCSpy application.
# This script handles all installation, configuration, and service management.
# Version: 1.2.3 # Version bump for this fix

import os
import sys
import subprocess
import configparser
import shutil
import re
import argparse

# --- Script Version ---
__version__ = "1.2.3" # Updated version

# --- Configuration Variables (Defaults - always initialized) ---
HFGCSPY_REPO = "https://github.com/sworrl/HFGCSpy.git" # IMPORTANT: Ensure this is correct!

# Default installation paths
DEFAULT_APP_DIR = "/opt/hfgcspy"
DEFAULT_WEB_ROOT_DIR = "/var/www/html/hfgcspy"

# Global variables, initialized with defaults, possibly updated later by prompts or config loading
HFGCSPY_APP_DIR = DEFAULT_APP_DIR
HFGCSPY_VENV_DIR = os.path.join(HFGCSPY_APP_DIR, "venv")
HFGCSPY_CONFIG_FILE = os.path.join(HFGCSPY_APP_DIR, "config.ini")
HFGCSPY_SERVICE_NAME = "hfgcspy.service"

WEB_ROOT_DIR = DEFAULT_WEB_ROOT_DIR
HFGCSPY_DATA_DIR = os.path.join(WEB_ROOT_DIR, "hfgcspy_data")
HFGCSPY_RECORDINGS_PATH = os.path.join(HFGCSPY_DATA_DIR, "recordings")
HFGCSPY_CONFIG_JSON_PATH = os.path.join(HFGCSpy_DATA_DIR, "config.json")


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
        # Use shell=True for commands with pipes or redirects often found in apt/bash calls
        # Use current sys.executable for python calls to ensure correct interpreter
        if isinstance(command, list) and command[0] == sys.executable: # Check if it's explicitly python call
             result = subprocess.run(command, check=check_return, capture_output=capture_output, text=True)
        else: # For shell commands
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
        log_error("This script must be run with sudo. Please run: sudo python3 setup.py --install")

# --- Installation Steps ---

def prompt_for_paths():
    # Use global to update variables defined at the module level
    global HFGCSpy_APP_DIR, HFGCSpy_VENV_DIR, HFGCSpy_CONFIG_FILE
    global WEB_ROOT_DIR, HFGCSpy_DATA_DIR, HFGCSpy_RECORDINGS_PATH, HFGCSpy_CONFIG_JSON_PATH

    log_info("Determining HFGCSpy installation paths:")

    user_app_dir = input(f"Enter desired application installation directory (default: {DEFAULT_APP_DIR}): ").strip()
    HFGCSPY_APP_DIR = user_app_dir if user_app_dir else DEFAULT_APP_DIR
    HFGCSPY_VENV_DIR = os.path.join(HFGCSPY_APP_DIR, "venv")
    HFGCSPY_CONFIG_FILE = os.path.join(HFGCSPY_APP_DIR, "config.ini")
    
    log_info(f"HFGCSpy application will be installed to: {HFGCSPY_APP_DIR}")

    user_web_root_dir = input(f"Enter desired web UI hosting directory (default: {DEFAULT_WEB_ROOT_DIR}): ").strip()
    WEB_ROOT_DIR = user_web_root_dir if user_web_root_dir else DEFAULT_WEB_ROOT_DIR
    HFGCSPY_DATA_DIR = os.path.join(WEB_ROOT_DIR, "hfgcspy_data")
    HFGCSPY_RECORDINGS_PATH = os.path.join(HFGCSPY_DATA_DIR, "recordings")
    HFGCSPY_CONFIG_JSON_PATH = os.path.join(HFGCSpy_DATA_DIR, "config.json")
    
    log_info(f"HFGCSpy web UI will be hosted at: {WEB_ROOT_DIR}")

def install_system_and_python_deps():
    log_info("Updating package lists and installing core system dependencies...")
    # Use shell=True for apt update to handle redirects/complexities correctly
    run_command("apt update", shell=True)
    run_command([
        "apt", "install", "-y", 
        "git", "python3", "python3-pip", "python3-venv", "build-essential", 
        "libusb-1.0-0-dev", "libatlas-base-dev", "libopenblas-dev", "net-tools", "apache2",
        "apt-transport-https", "ca-certificates", "curl", "gnupg", "lsb-release"
    ])

    log_info("Installing rtl-sdr tools...")
    run_command(["apt", "install", "-y", "rtl-sdr"])
    
    log_info("Blacklisting conflicting DVB-T kernel modules...")
    blacklist_conf = "/etc/modprobe.d/blacklist-rtl.conf"
    with open(blacklist_conf, "w") as f:
        f.write("blacklist dvb_usb_rtl28xxu\n")
        f.write("blacklist rtl2832\n")
        f.write("blacklist rtl2830\n")
    run_command("depmod -a", shell=True) # Use shell=True for depmod
    run_command("update-initramfs -u", shell=True) # Use shell=True for update-initramfs
    log_info("Conflicting kernel modules blacklisted. A reboot might be required for this to take effect.")

    log_info(f"Cloning HFGCSpy application from GitHub to {HFGCSPY_APP_DIR}...")
    if os.path.exists(HFGCSPY_APP_DIR):
        log_warn(f"HFGCSpy directory {HFGCSPY_APP_DIR} already exists. Skipping clone. Use --uninstall first if you want a fresh install.")
        return False # Indicate that it was an no fresh clone
    else:
        run_command(["git", "clone", HFGCSpy_REPO, HFGCSpy_APP_DIR])
    
    log_info(f"Setting up Python virtual environment in {HFGCSpy_VENV_DIR} and installing dependencies...")
    # Explicitly use sys.executable to ensure we're using the python3 that ran this script
    run_command([sys.executable, "-m", "venv", HFGCSpy_VENV_DIR]) 
    pip_path = os.path.join(HFGCSpy_VENV_DIR, "bin", "pip")
    requirements_path = os.path.join(HFGCSpy_APP_DIR, "requirements.txt")
    run_command([pip_path, "install", "--upgrade", "pip"])
    run_command([pip_path, "install", "-r", requirements_path])
    return True # Indicate fresh clone

def configure_hfgcspy_app():
    log_info("Configuring HFGCSpy application settings...")
    os.makedirs(os.path.dirname(HFGCSPY_DB_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(HFGCSPY_LOG_PATH), exist_ok=True)
    
    if not os.path.exists(HFGCSpy_CONFIG_FILE):
        template_path = os.path.join(HFGCSpy_APP_DIR, "config.ini.template")
        if os.path.exists(template_path):
            log_info(f"Copying {os.path.basename(template_path)} to {os.path.basename(HFGCSpy_CONFIG_FILE)}.")
            shutil.copyfile(template_path, HFGCSpy_CONFIG_FILE)
        else:
            log_error(f"config.ini and config.ini.template not found in {HFGCSpy_APP_DIR}. Cannot proceed with app configuration.")
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

    # Store absolute paths in config.ini for the Python application
    config_obj.set('app_paths', 'status_file', os.path.join(HFGCSpy_DATA_DIR, "status.json"))
    config_obj.set('app_paths', 'messages_file', os.path.join(HFGCSpy_DATA_DIR, "messages.json"))
    config_obj.set('app_paths', 'recordings_dir', HFGCSpy_RECORDINGS_PATH) # Recordings dir is directly served
    config_obj.set('app_paths', 'config_json_file', os.path.join(HFGCSpy_DATA_DIR, "config.json"))

    config_obj.set('app', 'database_path', os.path.join(HFGCSpy_APP_DIR, "data", "hfgcspy.db"))
    if not config_obj.has_section('logging'):
        config_obj.add_section('logging')
    config_obj.set('logging', 'log_file', os.path.join(HFGCSpy_APP_DIR, "logs", "hfgcspy.log"))

    with open(HFGCSpy_CONFIG_FILE, 'w') as f:
        config_obj.write(f)
    log_info(f"Paths in config.ini updated: {HFGCSpy_CONFIG_FILE}")

    # Set up user/group ownership for app directory for proper file access by service
    hfgcs_user = os.getenv("SUDO_USER") or "pi" # Get original user for ownership
    log_info(f"Setting ownership of {HFGCSPY_APP_DIR} to {hfgcs_user}...")
    run_command(["chown", "-R", f"{hfgcs_user}:{hfgcs_user}", HFGCSpy_APP_DIR])
    run_command(["chmod", "-R", "u+rwX,go-w", HFGCSpy_APP_DIR]) # Restrict write from others

    # Create web-accessible data directories and set permissions for Apache
    log_info(f"Creating web-accessible data directories: {HFGCSPY_DATA_DIR} and {HFGCSPY_RECORDINGS_PATH}.")
    os.makedirs(HFGCSPY_DATA_DIR, exist_ok=True)
    os.makedirs(HFGCSPY_RECORDINGS_PATH, exist_ok=True)
    run_command(["chown", "-R", "www-data:www-data", HFGCSpy_DATA_DIR])
    run_command(["chmod", "-R", "775", HFGCSpy_DATA_DIR]) # Allow www-data write, others read/execute

    log_info("HFGCSpy application configured.")

def configure_apache2_webui():
    log_info("Configuring Apache2 to serve HFGCSpy's web UI...")

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
        shutil.rmtree(WEB_ROOT_DIR) # Clean up previous install if any
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
    user_server_name = input(f"Enter the domain name or IP address to access HFGCSpy web UI (default: {server_ip}): ").strip()
    server_name = user_server_name if user_server_name else server_ip
    log_info(f"HFGCSpy web UI will be accessible via: {server_name}")

    apache_conf_path = "/etc/apache2/sites-available/hfgcspy.conf" # Renamed from hfgcspy-webui.conf for simplicity
    
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
        
        if le_domains:
            log_info(f"Detected Let's Encrypt certificates for domains: {', '.join(le_domains)}")
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
    apache_conf_content = f"""
<VirtualHost *:80>
    ServerName {server_name}
    DocumentRoot {WEB_ROOT_DIR}

    <Directory {WEB_ROOT_DIR}>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

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
        # Add SSLCertificateChainFile if chain.pem exists and is not the fullchain (common setup)
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
    
    # Get the user who invoked sudo
    hfgcs_user = os.getenv("SUDO_USER")
    if not hfgcs_user:
        hfgcs_user = "pi" # Fallback to 'pi' if SUDO_USER is not set (e.g., direct root login)
        log_warn(f"SUDO_USER environment variable not set. Defaulting HFGCSpy service user to '{hfgcs_user}'. Please confirm this is correct or manually adjust.")

    service_file_path = f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"
    service_content = f"""
[Unit]
Description=HFGCSpy SDR Scanner and Parser
After=network.target

[Service]
WorkingDirectory={HFGCSPY_APP_DIR}
ExecStart={os.path.join(HFGCSpy_VENV_DIR, "bin", "python3")} {os.path.join(HFGCSpy_APP_DIR, "hfgcs.py")} --run
StandardOutput=inherit
StandardError=inherit
Restart=always
User={hfgcs_user}

[Install]
WantedBy=multi-user.target
"""
    with open(service_file_path, "w") as f:
        f.write(service_content)
    
    run_command(["systemctl", "daemon-reload"])
    
    if ask_yes_no("Do you want HFGCSpy to start automatically at machine boot? (Recommended: Yes)"):
        run_command(["systemctl", "enable", HFGCSpy_SERVICE_NAME])
        log_info("HFGCSpy service enabled to start automatically at boot.")
    else:
        run_command(["systemctl", "disable", HFGCSpy_SERVICE_NAME])
        log_info(f"HFGCSpy service will NOT start automatically at boot. You'll need to start it manually: sudo systemctl start {HFGCSPY_SERVICE_NAME}")

    run_command(["systemctl", "start", HFGCSpy_SERVICE_NAME])
    log_info("HFGCSpy service setup and started.")

def update_hfgcspy_app_code():
    log_info("Stopping HFGCSpy service for update...")
    run_command(["systemctl", "stop", HFGCSpy_SERVICE_NAME], check_return=False)
    
    if not os.path.exists(HFGCSpy_APP_DIR):
        log_error(f"HFGCSpy application directory {HFGCSpy_APP_DIR} not found. Please run --install first.")
    
    log_info(f"Pulling latest changes from HFGCSpy repository in {HFGCSpy_APP_DIR}...")
    current_dir = os.getcwd() # Save current working directory
    os.chdir(HFGCSpy_APP_DIR) # Change to app dir for git pull
    run_command(["git", "pull"])
    os.chdir(current_dir) # Change back
    

    log_info("Reinstalling Python dependencies (if any new ones exist)...")
    pip_path = os.path.join(HFGCSpy_VENV_DIR, "bin", "pip")
    requirements_path = os.path.join(HFGCSpy_APP_DIR, "requirements.txt")
    run_command([pip_path, "install", "-r", requirements_path])

    log_info(f"Re-copying web UI files to Apache web root: {WEB_ROOT_DIR}...")
    if os.path.exists(WEB_ROOT_DIR):
        shutil.rmtree(WEB_ROOT_DIR) # Clean up old files
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

    run_command(["chown", "-R", "www-data:www-data", WEB_ROOT_DIR])
    run_command(["chmod", "-R", "755", WEB_ROOT_DIR])
    
    log_info(f"Restarting HFGCSpy service {HFGCSPY_SERVICE_NAME}...")
    run_command(["systemctl", "start", HFGCSpy_SERVICE_NAME])
    log_info("HFGCSpy updated and restarted.")
    log_info("Remember to restart Apache2 if there were any issues or config changes: sudo systemctl restart apache2")

def check_sdr():
    log_info("Checking for RTL-SDR dongle presence on host system...")
    try:
        # Check if rtl_test is available
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
    log_warn(f"Stopping and disabling HFGCSpy service {HFGCSPY_SERVICE_NAME}...")
    run_command(["systemctl", "stop", HFGCSpy_SERVICE_NAME], check_return=False)
    run_command(["systemctl", "disable", HFGCSpy_SERVICE_NAME], check_return=False)
    if os.path.exists(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"):
        run_command(["rm", f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"])
    run_command("systemctl daemon-reload", shell=True) # Use shell=True for daemon-reload
    
    if os.path.exists(HFGCSpy_APP_DIR):
        log_warn(f"Removing HFGCSpy application directory: {HFGCSpy_APP_DIR}...")
        shutil.rmtree(HFGCSpy_APP_DIR)
    else:
        log_warn(f"HFGCSpy application directory {HFGCSPY_APP_DIR} not found. Skipping removal.")

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
    run_command(["systemctl", "restart", "apache2"], check_return=False) # Restart Apache2 if it was running
    
    log_info("HFGCSpy uninstallation complete.")
    log_info("You may want to manually remove the DVB-T blacklisting file: /etc/modprobe.d/blacklist-rtl.conf")


# --- Main Script Logic ---

def main():
    parser = argparse.ArgumentParser(description=f"HFGCSpy Installer (Version: {__version__})")
    parser.add_argument('--install', action='store_true', help="Install HFGCSpy application and configure services.")
    parser.add_argument('--run', action='store_true', help="Run HFGCSpy main application directly (for debugging).")
    parser.add_argument('--stop', action='store_true', help="Stop HFGCSpy service.")
    parser.add_argument('--status', action='store_true', help="Check HFGCSpy and Apache2 service status.")
    parser.add_argument('--uninstall', action='store_true', help="Uninstall HFGCSpy application and associated files.")
    parser.add_argument('--update', action='store_true', help="Update HFGCSpy application code from Git and restart service.")
    parser.add_argument('--check_sdr', action='store_true', help="Check for RTL-SDR dongle presence.")
    
    args = parser.parse_args()

    # Determine global paths based on defaults, which might be overridden by prompt_for_paths
    global HFGCSpy_APP_DIR, HFGCSpy_VENV_DIR, HFGCSpy_CONFIG_FILE
    global WEB_ROOT_DIR, HFGCSpy_DATA_DIR, HFGCSpy_RECORDINGS_PATH, HFGCSpy_CONFIG_JSON_PATH
    
    # Initialize paths with defaults (they will be updated if prompt_for_paths is called)
    HFGCSPY_APP_DIR = DEFAULT_APP_DIR
    HFGCSPY_VENV_DIR = os.path.join(HFGCSPY_APP_DIR, "venv")
    HFGCSPY_CONFIG_FILE = os.path.join(HFGCSPY_APP_DIR, "config.ini")
    
    WEB_ROOT_DIR = DEFAULT_WEB_ROOT_DIR
    HFGCSPY_DATA_DIR = os.path.join(WEB_ROOT_DIR, "hfgcspy_data")
    HFGCSPY_RECORDINGS_PATH = os.path.join(HFGCSPY_DATA_DIR, "recordings")
    HFGCSPY_CONFIG_JSON_PATH = os.path.join(HFGCSpy_DATA_DIR, "config.json")


    log_info(f"HFGCSpy Installer (Version: {__version__})")

    # For commands that need existing installation paths, try to load them from config.ini
    # This logic is outside main if/else to ensure paths are set before operations
    # like stop, status, uninstall, update are called.
    if not args.install: # Only try to load paths from config if not doing a fresh install
        if os.path.exists(DEFAULT_APP_DIR) and os.path.exists(os.path.join(DEFAULT_APP_DIR, "config.ini")):
            temp_config = configparser.ConfigParser()
            temp_config.read(os.path.join(DEFAULT_APP_DIR, "config.ini"))
            
            if temp_config.has_option('app', 'database_path'): # A proxy for app_paths being set
                HFGCSPY_APP_DIR = DEFAULT_APP_DIR
                HFGCSPY_VENV_DIR = os.path.join(HFGCSPY_APP_DIR, "venv")
                HFGCSPY_CONFIG_FILE = os.path.join(HFGCSPY_APP_DIR, "config.ini")

                # Try to load app_paths values, otherwise keep defaults
                if temp_config.has_section('app_paths'):
                    try:
                        # Reconstruct WEB_ROOT_DIR from recordings_dir path
                        full_recordings_path_from_config = temp_config.get('app_paths', 'recordings_dir')
                        # Assume recordings_dir is like /var/www/html/hfgcspy/hfgcspy_data/recordings
                        # And WEB_ROOT_DIR is /var/www/html/hfgcspy
                        # This regex attempts to extract the base web root from the configured recordings_dir
                        match = re.search(r"(/.*)/hfgcspy_data/recordings/?", full_recordings_path_from_config)
                        if match:
                            WEB_ROOT_DIR = match.group(1)
                        else:
                            # Fallback if the path structure is unexpected
                            WEB_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(full_recordings_path_from_config), os.pardir, os.pardir))
                            log_warn(f"Deduced WEB_ROOT_DIR as {WEB_ROOT_DIR}. If incorrect, please manually set path vars in script or reinstall.")
                            
                        HFGCSPY_DATA_DIR = os.path.join(WEB_ROOT_DIR, "hfgcspy_data")
                        HFGCSPY_RECORDINGS_PATH = full_recordings_path_from_config
                        HFGCSPY_CONFIG_JSON_PATH = os.path.join(HFGCSpy_DATA_DIR, "config.json")

                    except configparser.NoOptionError:
                        log_warn("app_paths section in config.ini incomplete. Using default web paths.")
                    except Exception as e:
                        log_warn(f"Error parsing app_paths from config.ini: {e}. Using default web paths.")
                else:
                    log_warn("app_paths section not found in config.ini. Using default web paths.")

                log_info(f"Using detected install paths: App={HFGCSPY_APP_DIR}, Web={WEB_ROOT_DIR}")
            else:
                log_warn("Could not determine installed paths from config.ini. Using default paths for operations.")
        else:
            log_warn("HFGCSpy config.ini not found. Using default paths for operations.")


    if args.install:
        check_root()
        prompt_for_paths() # Ask for paths during install only
        install_system_and_python_deps()
        configure_hfgcspy_app()
        configure_apache2_webui()
        setup_systemd_service()
        log_info("HFGCSpy installation complete. Please consider rebooting your Raspberry Pi for full effect.")
    elif args.run:
        # For --run, paths are derived as above or from default.
        # hfgcs.py script itself uses config.ini for its internal paths.
        # So we just need to ensure the working directory is correct for it to find config.ini
        run_hfgcspy()
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
