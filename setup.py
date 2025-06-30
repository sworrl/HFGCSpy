# HFGCSpy/setup.py
# Python-based installer for HFGCSpy application.
# This script handles all installation, configuration, and service management.
# Version: 1.2.36 # Version bump for default ServerName to hostname

import os
import sys
import subprocess
import configparser
import shutil
import re
import argparse
import hashlib # Added for checksum calculation
import time # Added for sleep function

# --- Script Version ---
__version__ = "1.2.36" # Updated version

# --- Configuration Constants (Defined at module top-level for absolute clarity and immediate availability) ---
# Corrected: This should be the Git clone URL, not the raw content URL
HFGCSPY_REPO = "https://github.com/sworrl/HFGCSpy.git" 
HFGCSPY_SERVICE_NAME = "hfgcspy.service" # Service name is constant

# Default base installation directories (THESE ARE THE TRUE CONSTANTS, always available)
APP_DIR_DEFAULT = "/opt/hfgcspy"
WEB_ROOT_DIR_DEFAULT = "/var/www/html/hfgcspy" # This is where the web UI files will be copied

# --- Global Path Variables (Initialized to None, will be set by set_global_installation_paths) ---
# These are the variables that will hold the *actual* paths during script execution.
# They are declared here, and their concrete values (derived from defaults or user input)
# will be assigned ONLY within the set_global_installation_paths function.
hfgcs_app_dir = None 
hfgcs_config_file = None
hfgcs_db_path = None  
hfgcs_log_path = None 

web_root_dir = None # The directory where HFGCSpy's web UI files are served from
hfgcs_data_dir = None # The directory for status.json, messages.json, recordings
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
        # No special handling for python/pip commands as they are removed
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

def calculate_file_checksum(filepath, algorithm='sha256', block_size=65536):
    """Calculates the checksum of a file using the specified algorithm."""
    if not os.path.exists(filepath):
        return None
    
    if algorithm == 'sha256':
        hasher = hashlib.sha256()
    elif algorithm == 'md5': # Example for another algorithm
        hasher = hashlib.md5()
    else:
        log_error(f"Unsupported checksum algorithm: {algorithm}")

    with open(filepath, 'rb') as f:
        buf = f.read(block_size)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(block_size)
    return hasher.hexdigest()

# --- Path Management Functions ---

def set_global_installation_paths(app_dir_val, web_root_dir_val):
    """
    Calculates and updates all global path variables based on the provided
    app and web root directories.
    This function should be called explicitly in main() after base paths are determined.
    """
    global hfgcs_app_dir, hfgcs_config_file, hfgcs_db_path, hfgcs_log_path
    global web_root_dir, hfgcs_data_dir, hfgcs_recordings_path, hfgcs_config_json_path

    hfgcs_app_dir = app_dir_val
    hfgcs_config_file = os.path.join(hfgcs_app_dir, "config.ini")
    hfgcs_db_path = os.path.join(hfgcs_app_dir, "data", "hfgcspy.db") # Derived DB path
    hfgcs_log_path = os.path.join(hfgcs_app_dir, "logs", "hfgcspy.log") # Derived Log path
    
    web_root_dir = web_root_dir_val
    # hfgcs_data_dir is always created as a sub-directory of the web root where actual data files reside
    hfgcs_data_dir = os.path.join(web_root_dir, "hfgcs_data") 
    hfgcs_recordings_path = os.path.join(hfgcs_data_dir, "recordings")
    hfgcs_config_json_path = os.path.join(hfgcs_data_dir, "config.json")

def load_paths_from_config():
    """Attempts to load installed paths from config.ini into global variables.
    Returns True if paths were successfully loaded, False otherwise."""
    
    config_read = configparser.ConfigParser()
    installed_config_path = os.path.join(APP_DIR_DEFAULT, "config.ini") 

    if os.path.exists(installed_config_path):
        try:
            config_read.read(installed_config_path)
            
            # Get the app directory from the database_path in config.ini
            app_dir_from_config = config_read.get('app', 'database_path', fallback='').replace('/data/hfgcspy.db', '').strip()
            
            # Get the web root directory from the status_file path in config.ini
            web_root_dir_from_config = WEB_ROOT_DIR_DEFAULT # Default fallback
            if config_read.has_section('app_paths') and config_read.has_option('app_paths', 'status_file'):
                full_status_path = config_read.get('app_paths', 'status_file')
                # Regex to extract the part before /hfgcs_data/status.json
                match = re.search(r"^(.*)/hfgcs_data/status\.json$", full_status_path)
                if match:
                    web_root_dir_from_config = match.group(1)
                else:
                    log_warn(f"Could not reliably deduce web_root_dir from status_file path in config.ini: {full_status_path}. Using default.")
            else:
                log_warn("app_paths section or status_file option missing in config.ini. Using default web_root_dir.")

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

def install_system_and_python_deps(force_install=False):
    # Define a marker file to indicate if system-level dependencies have been installed
    # This marker is now placed in a more reliable location within the app directory
    install_marker_file = os.path.join(APP_DIR_DEFAULT, ".hfgcspy_system_installed")

    system_deps_needed = not os.path.exists(install_marker_file) or force_install
    if os.path.exists(install_marker_file) and not force_install:
        try:
            with open(install_marker_file, 'r') as f:
                installed_version = f.read().strip()
            if installed_version != __version__:
                log_warn(f"System dependencies marker file version ({installed_version}) does not match script version ({__version__}). Consider re-running with --force-system-install if issues arise.")
        except Exception as e:
            log_warn(f"Could not read system install marker file: {e}. Proceeding assuming installed.")

    if system_deps_needed:
        log_info("Performing initial system dependency installation (this may take a while)...")
        run_command("apt update", shell=True)
        # Install core system dependencies and Python packages via apt-get
        run_command([
            "apt", "install", "-y", 
            "git", "python3", "python3-pip", "python3-venv", "build-essential", # python3-pip and python3-venv are still here for general system readiness, but not used by this script for HFGCSpy's specific dependencies.
            "libusb-1.0-0-dev", "libatlas-base-dev", "libopenblas-dev", "net-tools", "apache2",
            "apt-transport-https", "ca-certificates", "curl", "gnupg", "lsb-release",
            # Python dependencies from requirements.txt, now via apt-get
            "python3-numpy", "python3-scipy", "python3-flask", "python3-gunicorn", 
            "python3-dotenv", "python3-requests", "python3-pyrtlsdr" # pyrtlsdr might be python3-rtlsdr or similar, check your distro
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
        os.makedirs(os.path.dirname(install_marker_file), exist_ok=True)
        with open(install_marker_file, 'w') as f:
            f.write(__version__)
        log_info(f"System dependencies installation marked by {install_marker_file}.")
    else:
        log_info("System dependencies and RTL-SDR tools appear to be already installed. Skipping system-level updates.")

    # Handle cloning/pulling the application repository
    app_cloned = False
    if not os.path.exists(hfgcs_app_dir):
        log_info(f"Cloning HFGCSpy application from GitHub to {hfgcs_app_dir}...")
        run_command(["git", "clone", HFGCSPY_REPO, hfgcs_app_dir])
        app_cloned = True
    elif not os.path.isdir(os.path.join(hfgcs_app_dir, '.git')):
        log_warn(f"Directory {hfgcs_app_dir} exists but is not a Git repository. Attempting to remove and re-clone.")
        shutil.rmtree(hfgcs_app_dir)
        run_command(["git", "clone", HFGCSPY_REPO, hfgcs_app_dir])
        app_cloned = True
    else:
        log_info(f"HFGCSpy application directory {hfgcs_app_dir} already exists and is a Git repository. Pulling latest changes.")
        current_dir = os.getcwd()
        os.chdir(hfgcs_app_dir)
        run_command(["git", "pull"])
        os.chdir(current_dir)
        app_cloned = False # Not a fresh clone

    # No pip or venv installation for HFGCSpy's Python dependencies
    log_info("Skipping Python virtual environment setup and pip installations as per requirements.")
    
    return app_cloned # Return whether the app was freshly cloned or just updated.

def configure_hfgcspy_app():
    log_info("Configuring HFGCSpy application settings...")
    
    # Ensure parent directories for DB and logs exist
    os.makedirs(os.path.dirname(hfgcs_db_path), exist_ok=True)
    log_info(f"Ensured DB directory exists: {os.path.dirname(hfgcs_db_path)}")
    os.makedirs(os.path.dirname(hfgcs_log_path), exist_ok=True)
    log_info(f"Ensured log directory exists: {os.path.dirname(hfgcs_log_path)}")
    
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
        config_obj.set('sdr', 'sample_rate', '20480_00')
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
    log_info(f"Attempting to create web-accessible data directories: {hfgcs_data_dir} and {hfgcs_recordings_path}.")
    os.makedirs(hfgcs_data_dir, exist_ok=True)
    log_info(f"Ensured web data directory exists: {hfgcs_data_dir}")
    os.makedirs(hfgcs_recordings_path, exist_ok=True)
    log_info(f"Ensured recordings directory exists: {hfgcs_recordings_path}")
    run_command(["chown", "-R", "www-data:www-data", hfgcs_data_dir])
    run_command(["chmod", "-R", "775", hfgcs_data_dir]) # Allow www-data write, others read/execute

    log_info("HFGCSpy application configured.")

def configure_apache2_webui(is_update=False):
    log_info("Configuring Apache2 to serve HFGCSpy's web UI...")

    log_info("Ensuring Apache2 is installed and enabled...")
    try:
        run_command(["systemctl", "is-active", "--quiet", "apache2"])
    except subprocess.CalledProcessError:
        log_info("Apache2 not running. Installing...")
        run_command(["apt", "install", "-y", "apache2"])
        run_command(["systemctl", "enable", "apache2"])
        run_command(["systemctl", "start", "apache2"])
    
    log_info("Enabling Apache2 modules: headers, ssl, proxy, proxy_http, alias...") # Added 'alias'
    run_command("a2enmod headers ssl proxy proxy_http alias", shell=True, check_return=False)

    log_info(f"Copying HFGCSpy web UI files to Apache web root: {web_root_dir}")
    # Instead of shutil.rmtree and shutil.copytree, we'll use checksums for selective copying
    src_web_ui_dir = os.path.join(hfgcs_app_dir, "web_ui")

    log_info(f"Updating web UI files in Apache web root: {web_root_dir} based on checksums...")
    for root, _, files in os.walk(src_web_ui_dir):
        for file in files:
            src_file_path = os.path.join(root, file)
            # Calculate relative path from src_web_ui_dir
            relative_path = os.path.relpath(src_file_path, src_web_ui_dir)
            dest_file_path = os.path.join(web_root_dir, relative_path)

            src_checksum = calculate_file_checksum(src_file_path)
            dest_checksum = calculate_file_checksum(dest_file_path)

            if src_checksum != dest_checksum:
                log_info(f"Copying changed file: {relative_path}")
                os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                shutil.copy2(src_file_path, dest_file_path)
            else:
                log_info(f"File unchanged: {relative_path} (checksums match)")

    # Ensure correct permissions after selective copy
    run_command(["chown", "-R", "www-data:www-data", web_root_dir])
    run_command(["chmod", "-R", "755", web_root_dir])

    http_conf_path = "/etc/apache2/sites-available/hfgcspy-http.conf"
    https_conf_path = "/etc/apache2/sites-available/hfgcspy-https.conf"
    
    # --- Intelligent Prompting for ServerName and SSL ---
    server_name = ""
    ssl_cert_path = ""
    ssl_key_path = ""
    ssl_domain = ""
    use_ssl = False

    # Try to load existing ServerName from HTTP config if it exists
    if os.path.exists(http_conf_path):
        try:
            with open(http_conf_path, 'r') as f:
                http_content_read = f.read()
            server_name_match = re.search(r"^\s*ServerName\s+(.+)$", http_content_read, re.MULTILINE)
            if server_name_match:
                server_name = server_name_match.group(1).strip()
        except Exception as e:
            log_warn(f"Could not read existing HTTP config for ServerName: {e}")

    # Try to load existing SSL config from HTTPS config if it exists
    if os.path.exists(https_conf_path):
        try:
            with open(https_conf_path, 'r') as f:
                https_content_read = f.read()
            ssl_cert_match = re.search(r"^\s*SSLCertificateFile\s+\"(.+)\"$", https_content_read, re.MULTILINE)
            ssl_key_match = re.search(r"^\s*SSLCertificateKeyFile\s+\"(.+)\"$", https_content_read, re.MULTILINE)
            if ssl_cert_match and ssl_key_match:
                ssl_cert_path = ssl_cert_match.group(1).strip()
                ssl_key_path = ssl_key_match.group(1).strip()
                le_domain_match = re.search(r"/etc/letsencrypt/live/([^/]+)/", ssl_cert_path)
                if le_domain_match:
                    ssl_domain = le_domain_match.group(1)
                use_ssl = True
                log_info("Found existing SSL configuration.")
            else:
                log_info("No existing SSL configuration found in HTTPS config.")
        except Exception as e:
            log_warn(f"Could not read existing HTTPS config for SSL paths: {e}")


    # Prompt for ServerName
    # Prioritize hostname for better network accessibility by default
    hostname_cmd = run_command(["hostname"], capture_output=True).strip()
    server_ip_cmd = run_command(["hostname", "-I"], capture_output=True).strip()
    server_ip = server_ip_cmd.split()[0] if server_ip_cmd else "" # Get first IP or empty string
    
    # If a previous server_name was loaded, use that. Otherwise, use hostname, then IP.
    default_server_name_prompt = server_name if server_name else (hostname_cmd if hostname_cmd else server_ip)

    user_server_name = input(f"Enter the domain name or IP address to access HFGCSpy web UI (default: {default_server_name_prompt}): ").strip()
    server_name = user_server_name if user_server_name else default_server_name_prompt
    log_info(f"HFGCSpy web UI will be accessible via: {server_name}")

    # Prompt for SSL
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
            if use_ssl and ssl_domain and ssl_domain in le_domains:
                if ask_yes_no(f"Do you want to continue using existing HTTPS configuration for {ssl_domain}? (Recommended: Yes)"):
                    use_ssl = True
                else:
                    use_ssl = False # User chose not to use existing SSL
            elif ask_yes_no("Do you want to configure HFGCSpy web UI to use HTTPS with one of these certificates?"):
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


    # --- Clean up existing HFGCSpy Apache configs ---
    conf_files_to_clean = ["hfgcspy.conf", "hfgcspy-http.conf", "hfgcspy-https.conf"]
    for conf_file_name in conf_files_to_clean:
        site_avail_path = os.path.join("/etc/apache2/sites-available", conf_file_name)
        site_enabled_path = os.path.join("/etc/apache2/sites-enabled", conf_file_name)
        
        if os.path.exists(site_enabled_path):
            log_info(f"Disabling existing Apache site link: {conf_file_name}...")
            run_command(["a2dissite", conf_file_name], check_return=False)
        if os.path.exists(site_avail_path):
            log_info(f"Removing existing Apache site file: {site_avail_path}...")
            os.remove(site_avail_path)
        if os.path.exists(site_enabled_path): # Check again in case a2dissite didn't remove symlink
             log_info(f"Removing lingering symlink: {site_enabled_path}...")
             os.remove(site_enabled_path)


    # --- Write and Enable new HTTP config ---
    with open(http_conf_path, "w") as f:
        f.write(f"""
<VirtualHost *:80>
    ServerName {server_name}
    DocumentRoot /var/www/html

    Alias /hfgcspy "{web_root_dir}"
    <Directory "{web_root_dir}">
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
""")
    log_info(f"Wrote HTTP Apache config to {http_conf_path}")
    run_command(["a2ensite", os.path.basename(http_conf_path)])
    log_info(f"Enabled HTTP Apache site {os.path.basename(http_conf_path)}")

    # --- Write and Enable new HTTPS config (if applicable) ---
    if use_ssl and ssl_cert_path and ssl_key_path:
        with open(https_conf_path, "w") as f:
            f.write(f"""
<IfModule mod_ssl.c>
<VirtualHost *:443>
    ServerName {server_name}
    DocumentRoot /var/www/html

    Alias /hfgcspy "{web_root_dir}"
    <Directory "{web_root_dir}">
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
    # SSLCertificateChainFile is often included in fullchain.pem.
    # If your setup requires a separate chain file, uncomment and set the path below.
    # SSLCertificateChainFile ""

    <FilesMatch "\.(cgi|shtml|phtml|php)$">
            SSLOptions +StdEnvVars
    </FilesMatch>
    <Directory /usr/lib/cgi-bin>
            SSLOptions +StdEnvVars
    </Directory>

    BrowserMatch "MSIE [2-6]" \
            nokeepalive ssl-unclean-shutdown \
            downgrade-1.0 force-response-1.0
    BrowserMatch "MSIE [17-9]" ssl-unclean-shutdown

    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
</VirtualHost>
</IfModule>
""")
        log_info(f"Wrote HTTPS Apache config to {https_conf_path}")
        run_command(["a2ensite", os.path.basename(https_conf_path)])
        log_info(f"Enabled HTTPS Apache site {os.path.basename(https_conf_path)}")
    elif not use_ssl:
        log_info("Skipping HTTPS Apache configuration as SSL was not chosen or certs are missing.")


    # Only attempt to disable if the default site is actually enabled
    if os.path.exists("/etc/apache2/sites-enabled/000-default.conf"):
        log_info("Disabling default Apache site 000-default.conf...")
        run_command(["a2dissite", "000-default.conf"], check_return=False) 
    else:
        log_info("Default Apache site 000-default.conf is not enabled or does not exist. Skipping disabling.")

    # Run configtest before restarting to catch any new syntax errors immediately
    log_info("Running apache2ctl configtest before restarting Apache...")
    run_command(["apache2ctl", "configtest"]) # This will now halt if there's a syntax error

    log_info("Restarting Apache2 service...")
    run_command(["systemctl", "restart", "apache2"])
    # Add a sleep here to allow Apache to fully restart before the script exits
    time.sleep(5) # Give Apache 5 seconds to stabilize
    log_info("Apache2 configured and restarted to serve HFGCSpy web UI.")
    log_info(f"Access HfgcsPy at http://{server_name}/hfgcspy (and https://{server_name}/hfgcspy if SSL was configured).")


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
ExecStart=/usr/bin/python3 {os.path.join(hfgcs_app_dir, "hfgcs.py")} --run
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
    # No pip installation for HFGCSpy's Python dependencies, rely on apt-get
    log_info("Skipping pip installations as per requirements. Relying on apt-get for Python dependencies.")

    log_info(f"Updating web UI files in Apache web root: {web_root_dir} based on checksums...")
    src_web_ui_dir = os.path.join(hfgcs_app_dir, "web_ui")

    # Iterate through source files and compare with destination
    for root, _, files in os.walk(src_web_ui_dir):
        for file in files:
            src_file_path = os.path.join(root, file)
            # Calculate relative path from src_web_ui_dir
            relative_path = os.path.relpath(src_file_path, src_web_ui_dir)
            dest_file_path = os.path.join(web_root_dir, relative_path)

            src_checksum = calculate_file_checksum(src_file_path)
            dest_checksum = calculate_file_checksum(dest_file_path)

            if src_checksum != dest_checksum:
                log_info(f"Copying changed file: {relative_path}")
                os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                shutil.copy2(src_file_path, dest_file_path)
            else:
                log_info(f"File unchanged: {relative_path} (checksums match)")

    # Ensure correct permissions after selective copy
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
    # Use /usr/bin/python3 directly
    python_exec = "/usr/bin/python3" 
    hfgcs_script = os.path.join(hfgcs_app_dir, "hfgcs.py")
    if not os.path.exists(python_exec):
        log_error(f"Python executable not found at {python_exec}. Please ensure python3 is installed.")
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
    global hfgcs_app_dir, hfgcs_config_file, hfgcs_db_path, hfgcs_log_path
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
    parser.add_argument('--force-system-install', action='store_true', help="Force re-installation of system dependencies.")
    
    args = parser.parse_args()

    # Always set paths with defaults first to ensure they are never None
    set_global_installation_paths(APP_DIR_DEFAULT, WEB_ROOT_DIR_DEFAULT) 

    # Determine if HFGCSpy is already installed in the default location
    is_already_installed = os.path.exists(APP_DIR_DEFAULT) and \
                           os.path.isdir(os.path.join(APP_DIR_DEFAULT, '.git')) and \
                           os.path.exists(os.path.join(APP_DIR_DEFAULT, 'config.ini'))

    # Process arguments
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    if args.install:
        check_root()
        if is_already_installed:
            log_info(f"HFGCSpy appears to be already installed at {APP_DIR_DEFAULT}. Proceeding with update logic.")
            load_paths_from_config() # Load existing paths for update
            install_system_and_python_deps(force_install=args.force_system_install) # Check/install system deps
            update_hfgcspy_app_code() # Pull latest code, reinstall python deps, recopy web UI
            configure_hfgcspy_app() # Reconfigure app's config.ini
            configure_apache2_webui(is_update=True) # Use update logic for Apache prompts
            setup_systemd_service() # Re-setup service in case of changes
            log_info("HFGCSpy installation/update complete. Please consider rebooting your Raspberry Pi for full effect.")
        else:
            log_info("Performing a fresh HFGCSpy installation.")
            prompt_for_paths() # Only prompt if it's truly a fresh install
            install_system_and_python_deps(force_install=args.force_system_install)
            configure_hfgcspy_app()
            configure_apache2_webui(is_update=False) # Fresh install, no update logic for prompts
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
        # For update, load paths from config first
        load_paths_from_config()
        # Then proceed with update steps
        install_system_and_python_deps(force_install=args.force_system_install) # Check/install system deps
        update_hfgcspy_app_code()
        configure_apache2_webui(is_update=True) # Use update logic for prompts
        setup_systemd_service() # Re-setup service in case of changes
        log_info("HFGCSpy update complete. Please consider rebooting your Raspberry Pi for full effect.")
    elif args.check_sdr:
        check_sdr()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
