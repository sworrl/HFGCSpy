# HFGCSpy/setup.py
# Python-based installer for HFGCSpy application.
# This script handles all installation, configuration, and service management.
# Version: 1.2.19 # Version bump for refactoring and critical fix

import os
import sys
import subprocess
import configparser
import shutil
import re
import argparse

# --- Script Version ---
__version__ = "1.2.19" # Updated version

# --- Configuration Constants (Defined at module top-level for absolute clarity and immediate availability) ---
HFGCSPY_REPO = "https://github.com/sworrl/HFGCSpy.git" # IMPORTANT: Ensure this is correct!
HFGCSPY_SERVICE_NAME = "hfgcspy.service" # Service name is constant

# Default base installation directories (THESE ARE THE TRUE CONSTANTS, always available)
APP_DIR_DEFAULT = "/opt/hfgcspy"
WEB_ROOT_DIR_DEFAULT = "/var/www/html/hfgcspy"

# --- Global Path Variables (Initialized to None, will be set by set_global_installation_paths) ---
# These are the variables that will hold the *actual* paths during script execution.
# They are declared here, and their concrete values (derived from defaults or user input)
# will be assigned ONLY within the set_global_installation_paths function.
hfgcs_app_dir = None 
hfgcs_venv_dir = None
hfgcs_config_file = None
hfgcs_db_path = None  
hfgcs_log_path = None 

web_root_dir = None
hfgcs_data_dir = None
hfgcs_recordings_path = None
hfgcs_config_json_path = None


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
        # Special handling for python/pip commands to avoid shell=True issues
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
        log_error("This script must be run with sudo. Please run: sudo python3 setup.py --install")

# --- Path Management Functions ---

def set_global_installation_paths(app_dir_val, web_root_dir_val):
    """
    Calculates and updates all global path variables based on the provided
    app and web root directories.
    This function should be called explicitly in main() after base paths are determined.
    """
    global hfgcs_app_dir, hfgcs_venv_dir, hfgcs_config_file, hfgcs_db_path, hfgcs_log_path
    global web_root_dir, hfgcs_data_dir, hfgcs_recordings_path, hfgcs_config_json_path

    hfgcs_app_dir = app_dir_val
    hfgcs_venv_dir = os.path.join(hfgcs_app_dir, "venv")
    hfgcs_config_file = os.path.join(hfgcs_app_dir, "config.ini")
    hfgcs_db_path = os.path.join(hfgcs_app_dir, "data", "hfgcspy.db") # Derived DB path
    hfgcs_log_path = os.path.join(hfgcs_app_dir, "logs", "hfgcspy.log") # Derived Log path
    
    web_root_dir = web_root_dir_val
    # hfgcs_data_dir is always created as a sub-directory of the web root
    hfgcs_data_dir = os.path.join(web_root_dir, "hfgcspy_data") 
    hfgcs_recordings_path = os.path.join(hfgcs_data_dir, "recordings")
    hfgcs_config_json_path = os.path.join(hfgcs_data_dir, "config.json")

def load_paths_from_config():
    """Attempts to load installed paths from config.ini into global variables."""
    # This function will call set_global_installation_paths once it has determined the base directories.
    
    config_read = configparser.ConfigParser()
    installed_config_path = os.path.join(APP_DIR_DEFAULT, "config.ini") # Use constant APP_DIR_DEFAULT 

    if os.path.exists(installed_config_path):
        try:
            config_read.read(installed_config_path)
            
            # Get the app directory from the database_path in config.ini
            app_dir_from_config = config_read.get('app', 'database_path', fallback='').replace('/data/hfgcspy.db', '').strip()
            
            # Get the web root directory from the status_file path in config.ini
            web_root_dir_from_config = WEB_ROOT_DIR_DEFAULT # Default fallback
            if config_read.has_section('app_paths') and config_read.has_option('app_paths', 'status_file'):
                full_status_path = config_read.get('app_paths', 'status_file')
                # Regex to extract the part before /hfgcspy_data/status.json
                match = re.search(r"^(.*)/hfgcspy_data/status\.json$", full_status_path)
                if match:
                    web_root_dir_from_config = match.group(1)
                else:
                    log_warn(f"Could not reliably deduce WEB_ROOT_DIR from status_file path in config.ini: {full_status_path}. Using default.")
            else:
                log_warn("app_paths section or status_file option missing in config.ini. Using default WEB_ROOT_DIR.")

            # If app_dir_from_config is empty (e.g., config.ini is minimal or old), use default base
            if not app_dir_from_config: app_dir_from_config = APP_DIR_DEFAULT

            set_global_installation_paths(app_dir_from_config, web_root_dir_from_config)
            log_info(f"Loaded install paths from config: App='{hfgcs_app_dir}', Web='{web_root_dir}'")
            return True # Paths loaded successfully
        except configparser.Error as e:
            log_warn(f"Error reading config.ini for paths: {e}. Falling back to default paths.")
            set_global_installation_paths(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) # Ensure paths are reset to defaults
            return False
    else:
        log_warn("config.ini not found at default app directory. Using default paths.")
        set_global_installation_paths(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) # Ensure paths are set even if config not found
        return False

# --- Installation Steps ---

def prompt_for_paths():
    log_info("Determining HFGCSpy installation paths:")

    user_app_dir = input(f"Enter desired application installation directory (default: {APP_DIR_DEFAULT}): ").strip()
    new_app_dir = user_app_dir if user_app_dir else APP_DIR_DEFAULT
    
    user_web_root_dir = input(f"Enter desired web UI hosting directory (default: {WEB_ROOT_DIR_DEFAULT}): ").strip()
    new_web_root_dir = user_web_root_dir if user_web_root_dir else WEB_ROOT_DIR_DEFAULT
    
    # Update global paths AFTER user input
    set_global_installation_paths(new_app_dir, new_web_root_dir)
    
    log_info(f"HFGCSpy application will be installed to: {hfgcs_app_dir}")
    log_info(f"HFGCSpy web UI will be hosted at: {web_root_dir}")

def install_system_and_python_deps():
    # HFGCSPY_REPO is a module-level global constant, it's always available
    log_info("Updating package lists and installing core system dependencies...")
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
    run_command("depmod -a", shell=True)
    run_command("update-initramfs -u", shell=True)
    log_info("Conflicting kernel modules blacklisted. A reboot might be required for this to take effect.")

    log_info(f"Cloning HFGCSpy application from GitHub to {hfgcs_app_dir}...")
    if os.path.exists(hfgcs_app_dir):
        log_warn(f"HFGCSpy directory {hfgcs_app_dir} already exists. Skipping clone. Use --uninstall first if you want a fresh install.")
        return False # Indicate that it was an no fresh clone
    else:
        run_command(["git", "clone", HFGCSPY_REPO, hfgcs_app_dir]) 
    
    log_info(f"Setting up Python virtual environment in {hfgcs_venv_dir} and installing dependencies...")
    run_command([sys.executable, "-m", "venv", hfgcs_venv_dir]) 
    pip_path = os.path.join(hfgcs_venv_dir, "bin", "pip")
    requirements_path = os.path.join(hfgcs_app_dir, "requirements.txt")
    run_command([pip_path, "install", "--upgrade", "pip"])
    run_command([pip_path, "install", "-r", requirements_path])
    return True # Indicate fresh clone

def configure_hfgcspy_app():
    log_info("Configuring HFGCSpy application settings...")
    # These directories are derived from hfgcs_app_dir
    os.makedirs(os.path.dirname(hfgcs_db_path), exist_ok=True)
    os.makedirs(os.path.dirname(hfgcs_log_path), exist_ok=True)
    
    if not os.path.exists(hfgcs_config_file):
        template_path = os.path.join(hfgcs_app_dir, "config.ini.template")
        if os.path.exists(template_path):
            log_info(f"Copying {os.path.basename(template_path)} to {os.path.basename(hfgcs_config_file)}.")
            shutil.copyfile(template_path, hfgcs_config_file)
        else:
            log_error(f"config.ini and config.ini.template not found in {hfgcs_app_dir}. Cannot proceed with app configuration.")
    else:
        log_info("Existing config.ini found. Using existing configuration. Please verify it points to correct paths.")

    # Update app_paths section in config.ini dynamically from current install paths
    config_obj = configparser.ConfigParser()
    config_obj.read(hfgcs_config_file)

    if not config_obj.has_section('app_paths'):
        config_obj.add_section('app_paths')
    if not config_obj.has_section('app'):
        config_obj.add_section('app')
    if not config_obj.has_section('logging'):
        config_obj.add_section('logging')
    # Add sdr section if it doesn't exist, to ensure fallbacks are always there
    if not config_obj.has_section('sdr'):
        config_obj.add_section('sdr')
        config_obj.set('sdr', 'sample_rate', '2048000')
        config_obj.set('sdr', 'center_freq_hz', '8992000')
        config_obj.set('sdr', 'gain', 'auto')
        config_obj.set('sdr', 'ppm_correction', '0')
    if not config_obj.has_section('scan_services'):
        config_obj.add_section('scan_services')
        config_obj.set('scan_services', 'hfgcs', 'yes')
        config_obj.set('scan_services', 'js8', 'no')
    if not config_obj.has_section('sdr_selection'):
        config_obj.add_section('sdr_selection')
        config_obj.set('sdr_selection', 'selected_devices', 'all')
    if not config_obj.has_section('online_sdrs'): # Ensure online_sdrs section exists
        config_obj.add_section('online_sdrs')


    config_obj.set('app', 'mode', 'standalone') # Ensure mode is standalone
    config_obj.set('app', 'database_path', hfgcs_db_path) # Use the global derived path
    config_obj.set('logging', 'log_file', hfgcs_log_path) # Use the global derived path

    # Store absolute paths for web-accessible files in config.ini
    config_obj.set('app_paths', 'status_file', os.path.join(hfgcs_data_dir, "status.json"))
    config_obj.set('app_paths', 'messages_file', os.path.join(hfgcs_data_dir, "messages.json"))
    config_obj.set('app_paths', 'recordings_dir', hfgcs_recordings_path) # Recordings dir is directly served
    config_obj.set('app_paths', 'config_json_file', hfgcs_config_json_path) # Use the global derived path

    with open(hfgcs_config_file, 'w') as f:
        config_obj.write(f)
    log_info(f"Paths in config.ini updated: {hfgcs_config_file}")

    # Set up user/group ownership for app directory for proper file access by service
    hfgcs_user = os.getenv("SUDO_USER") or "pi" # Get original user for ownership
    log_info(f"Setting ownership of {hfgcs_app_dir} to {hfgcs_user}...")
    run_command(["chown", "-R", f"{hfgcs_user}:{hfgcs_user}", hfgcs_app_dir])
    run_command(["chmod", "-R", "u+rwX,go-w", hfgcs_app_dir]) # Restrict write from others

    # Create web-accessible data directories and set permissions for Apache
    log_info(f"Creating web-accessible data directories: {hfgcs_data_dir} and {hfgcs_recordings_path}.")
    os.makedirs(hfgcs_data_dir, exist_ok=True)
    os.makedirs(hfgcs_recordings_path, exist_ok=True)
    run_command(["chown", "-R", "www-data:www-data", hfgcs_data_dir])
    run_command(["chmod", "-R", "775", hfgcs_data_dir]) # Allow www-data write, others read/execute

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

    log_info(f"Copying HFGCSpy web UI files to Apache web root: {web_root_dir}")
    if os.path.exists(web_root_dir):
        log_warn(f"Existing web UI directory {web_root_dir} found. Removing contents before copying new files.")
        shutil.rmtree(web_root_dir) # Clean up previous install if any
    os.makedirs(web_root_dir, exist_ok=True)
    
    # Copy contents of web_ui directory
    src_web_ui_dir = os.path.join(hfgcs_app_dir, "web_ui")
    for item in os.listdir(src_web_ui_dir):
        s = os.path.join(src_web_ui_dir, item)
        d = os.path.join(web_root_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    # Ensure Apache has correct ownership/permissions
    run_command(["chown", "-R", "www-data:www-data", web_root_dir])
    run_command(["chmod", "-R", "755", web_root_dir])

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
    DocumentRoot {web_root_dir}

    <Directory {web_root_dir}>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    Alias /hfgcspy_data "{hfgcs_data_dir}"
    <Directory "{hfgcs_data_dir}">
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
    DocumentRoot {web_root_dir}

    <Directory {web_root_dir}>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    Alias /hfgcspy_data "{hfgcs_data_dir}"
    <Directory "{hfgcs_data_dir}">
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
WorkingDirectory={hfgcs_app_dir}
ExecStart={os.path.join(hfgcs_venv_dir, "bin", "python3")} {os.path.join(hfgcs_app_dir, "hfgcs.py")} --run
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
        run_command(["systemctl", "enable", HFGCSPY_SERVICE_NAME])
        log_info("HFGCSpy service enabled to start automatically at boot.")
    else:
        run_command(["systemctl", "disable", HFGCSPY_SERVICE_NAME])
        log_info(f"HFGCSpy service will NOT start automatically at boot. You'll need to start it manually: sudo systemctl start {HFGCSPY_SERVICE_NAME}")

    run_command(["systemctl", "start", HFGCSPY_SERVICE_NAME])
    log_info("HFGCSpy service setup and started.")

def update_hfgcspy_app_code():
    log_info("Stopping HFGCSpy service for update...")
    run_command(["systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    
    if not os.path.exists(hfgcs_app_dir):
        log_error(f"HFGCSpy application directory {hfgcs_app_dir} not found. Please run --install first.")
    
    log_info(f"Pulling latest changes from HFGCSpy repository in {hfgcs_app_dir}...")
    current_dir = os.getcwd() # Save current working directory
    os.chdir(hfgcs_app_dir) # Change to app dir for git pull
    run_command(["git", "pull"])
    os.chdir(current_dir) # Change back
    

    log_info("Reinstalling Python dependencies (if any new ones exist)...")
    pip_path = os.path.join(hfgcs_venv_dir, "bin", "pip")
    requirements_path = os.path.join(hfgcs_app_dir, "requirements.txt")
    run_command([pip_path, "install", "-r", requirements_path])

    log_info(f"Re-copying web UI files to Apache web root: {web_root_dir}...")
    if os.path.exists(web_root_dir):
        shutil.rmtree(web_root_dir) # Clean up old files
    os.makedirs(web_root_dir, exist_ok=True)
    # Copy contents of web_ui directory
    src_web_ui_dir = os.path.join(hfgcs_app_dir, "web_ui")
    for item in os.listdir(src_web_ui_dir):
        s = os.path.join(src_web_ui_dir, item)
        d = os.path.join(web_root_dir, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

    run_command(["chown", "-R", "www-data:www-data", web_root_dir])
    run_command(["chmod", "-R", "755", web_root_dir])
    
    log_info(f"Restarting HFGCSpy service {HFGCSPY_SERVICE_NAME}...")
    run_command(["systemctl", "start", HFGCSPY_SERVICE_NAME])
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
    run_command(["systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    run_command(["systemctl", "disable", HFGCSPY_SERVICE_NAME], check_return=False)
    if os.path.exists(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}"):
        os.remove(f"/etc/systemd/system/{HFGCSPY_SERVICE_NAME}")
    run_command("systemctl daemon-reload", shell=True)
    
    # Ensure paths are set before attempting to remove
    load_paths_from_config() # Attempt to load installed paths, if not, uses defaults

    if os.path.exists(hfgcs_app_dir):
        log_warn(f"Removing HFGCSpy application directory: {hfgcs_app_dir}...")
        shutil.rmtree(hfgcs_app_dir)
    else:
        log_warn(f"HFGCSpy application directory {hfgcs_app_dir} not found. Skipping removal.")

    if os.path.exists(web_root_dir):
        log_warn(f"Removing Apache2 web UI directory: {web_root_dir}...")
        shutil.rmtree(web_root_dir)
    else:
        log_warn(f"Apache2 web UI directory {web_root_dir} not found. Skipping removal.")

    log_warn("Removing Apache2 configuration for HFGCSpy web UI (if it exists)...")
    run_command(["a2dissite", "hfgcspy.conf"], check_return=False)
    if os.path.exists("/etc/apache2/sites-available/hfgcspy.conf"):
        os.remove("/etc/apache2/sites-available/hfgcspy.conf")
    if os.path.exists("/etc/apache2/sites-enabled/hfgcspy.conf"):
        os.remove("/etc/apache2/sites-enabled/hfgcspy.conf")
    run_command(["systemctl", "restart", "apache2"], check_return=False)
    
    log_info("HFGCSpy uninstallation complete.")
    log_info("You may want to manually remove the DVB-T blacklisting file: /etc/modprobe.d/blacklist-rtl.conf")

def run_hfgcspy():
    """Runs the main hfgcs.py application (for debugging/manual start)."""
    log_info("Attempting to run HFGCSpy application directly...")
    python_exec = os.path.join(hfgcs_venv_dir, "bin", "python3")
    hfgcs_script = os.path.join(hfgcs_app_dir, "hfgcs.py")
    if not os.path.exists(python_exec):
        log_error(f"Python virtual environment executable not found at {python_exec}. Is HFGCSpy installed?")
    if not os.path.exists(hfgcs_script):
        log_error(f"HFGCSpy main script not found at {hfgcs_script}. Is HFGCSpy installed?")
    
    # Run the main application, capturing its output
    run_command([python_exec, hfgcs_script, "--run"])

def stop_hfgcspy():
    """Stops the HFGCSpy service."""
    log_info("Stopping HFGCSpy service...")
    run_command(["systemctl", "stop", HFGCSPY_SERVICE_NAME], check_return=False)
    log_info("HFGCSpy service stopped (if it was running).")

def status_hfgcspy():
    """Checks the status of HFGCSpy and Apache2 services."""
    log_info("Checking HFGCSpy service status:")
    run_command(["systemctl", "status", HFGCSPY_SERVICE_NAME], check_return=False)
    log_info("\nChecking Apache2 service status:")
    run_command(["systemctl", "status", "apache2"], check_return=False)

# --- Main Script Logic ---

def main():
    # --- Path Initialization for main execution flow ---
    # These global variables are initialized at the module level.
    # For --install, prompt_for_paths() will update them.
    # For other commands, load_paths_from_config() will attempt to update them.
    # This structure ensures they always have *some* value before being used.
    global hfgcs_app_dir, hfgcs_venv_dir, hfgcs_config_file, hfgcs_db_path, hfgcs_log_path
    global web_root_dir, hfgcs_data_dir, hfgcs_recordings_path, hfgcs_config_json_path

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

    # Always set paths with defaults first to ensure they are never None
    set_global_installation_paths(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) 

    # If not performing a fresh install, attempt to load paths from existing config.ini
    # This will override the defaults set above if a config is found.
    if not args.install:
        load_paths_from_config() # This function will call set_global_installation_paths with loaded paths


    # Process arguments
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.install:
        check_root()
        prompt_for_paths() # Prompt to get user-defined paths if installing (updates globals)
        install_system_and_python_deps()
        configure_hfgcspy_app()
        configure_apache2_webui()
        setup_systemd_service()
        log_info("HFGCSpy installation complete. Please consider rebooting your Raspberry Pi for full effect.")
    elif args.run:
        check_root() # Running main app requires root for SDR
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
