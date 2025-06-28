#!/bin/bash

# HFGCSpy Installer Script
# Manages installation, configuration, and execution of the HFGCSpy application.
# HFGCSpy is a Python-based SDR scanner, recorder, and parser,
# designed for standalone operation with a static web interface served by Apache2.

# --- Force working directory to /tmp to avoid getcwd errors ---
cd /tmp || { echo "ERROR: Cannot change to /tmp. Exiting."; exit 1; }

# --- Script Version ---
SCRIPT_VERSION="1.1.1" # Updated version for this fix

# --- Configuration Variables (Defaults) ---
# GitHub repository for HFGCSpy application (replace with your actual repo later)
HFGCSPY_REPO="https://github.com/sworrl/HFGCSpy.git" # IMPORTANT: Ensure this is correct!

# Default installation paths
DEFAULT_APP_DIR="/opt/hfgcspy"
DEFAULT_WEB_ROOT_DIR="/var/www/html/hfgcspy"

# Internal variables derived from installation paths
HFGCSPY_APP_DIR="$DEFAULT_APP_DIR" # Will be set by user prompt or default
HFGCSPY_VENV_DIR="${HFGCSPY_APP_DIR}/venv"
HFGCSPY_CONFIG_FILE="${HFGCSPY_APP_DIR}/config.ini"
HFGCSPY_SERVICE_NAME="hfgcspy.service"

WEB_ROOT_DIR="$DEFAULT_WEB_ROOT_DIR" # Will be set by user prompt or default
HFGCSPY_DATA_DIR="${WEB_ROOT_DIR}/hfgcspy_data" # Directory for status.json, messages.json, recordings

# Internal paths used by hfgcs.py for data persistence (derived from above)
HFGCSPY_DB_PATH="${HFGCSPY_APP_DIR}/data/hfgcspy.db"
HFGCSPY_LOG_PATH="${HFGCSPY_APP_DIR}/logs/hfgcspy.log"
HFGCSPY_RECORDINGS_PATH="${HFGCSPY_DATA_DIR}/recordings" # Recordings served by Apache2
HFGCSPY_CONFIG_JSON_PATH="${HFGCSPY_DATA_DIR}/config.json" # Config JSON for UI


# --- Helper Functions ---

log_info() {
    echo -e "\n\033[0;32mINFO: $1\033[0m" # Green text for info
}

log_warn() {
    echo -e "\n\033[0;33mWARNING: $1\033[0m" # Yellow text for warnings
}

log_error() {
    echo -e "\n\033[0;31mERROR: $1\033[0m" # Red text for errors
    exit 1
}

ask_yes_no() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "Please answer yes or no.";;
        esac
    done
}

# Function to check for root privileges
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run with sudo or as root. Please run: sudo ./$(basename "$0") $@"
    fi
}

# Function to install system packages and clone HFGCSpy
install_system_and_python_deps() {
    log_info "Updating package lists and installing core dependencies..."
    sudo apt update || log_error "Failed to update package lists."
    # Ensure all necessary packages for Docker and system utilities are here explicitly
    sudo apt install -y git python3 python3-pip python3-venv build-essential libusb-1.0-0-dev \
        libatlas-base-dev libopenblas-dev net-tools apache2 \
        apt-transport-https ca-certificates curl gnupg lsb-release || log_error "Failed to install core system dependencies or Apache2."

    # Install rtl-sdr tools
    log_info "Installing rtl-sdr tools..."
    sudo apt install -y rtl-sdr || log_error "Failed to install rtl-sdr tools."
    
    # Blacklist the default DVB-T driver which can conflict with RTL-SDR
    log_info "Blacklisting conflicting DVB-T kernel modules..."
    echo 'blacklist dvb_usb_rtl28xxu' | sudo tee /etc/modprobe.d/blacklist-rtl.conf > /dev/null
    echo 'blacklist rtl2832' | sudo tee -a /etc/modprobe.d/blacklist-rtl.conf > /dev/null
    echo 'blacklist rtl2830' | sudo tee -a /etc/modprobe.d/blacklist-rtl.conf > /dev/null
    sudo depmod -a
    sudo update-initramfs -u
    log_info "Conflicting kernel modules blacklisted. A reboot might be required for this to take effect."

    log_info "Cloning HFGCSpy application from GitHub to $HFGCSPY_APP_DIR..."
    if [ -d "$HFGCSPY_APP_DIR" ]; then
        log_warn "HFGCSpy directory already exists. Attempting to update instead. Use --uninstall first if you want a fresh install."
        update_hfgcspy
        return
    fi
    sudo git clone "$HFGCSPY_REPO" "$HFGCSPY_APP_DIR" || log_error "Failed to clone HFGCSpy repository. Check HFGCS_REPO variable and network connectivity."

    log_info "Setting up Python virtual environment and installing dependencies in $HFGCSPY_VENV_DIR..."
    sudo python3 -m venv "$HFGCSPY_VENV_DIR" || log_error "Failed to create virtual environment."
    sudo "$HFGCSPY_VENV_DIR"/bin/pip install --upgrade pip || log_error "Failed to upgrade pip in venv."
    sudo "$HFGCSPY_VENV_DIR"/bin/pip install -r "${HFGCSPY_APP_DIR}/requirements.txt" || log_error "Failed to install Python dependencies. Ensure requirements.txt is correct and complete."
}

# Function to configure HFGCSpy
configure_hfgcspy_app() {
    log_info "Configuring HFGCSpy application settings..."
    # Create necessary internal directories for HFGCSpy's operation
    sudo mkdir -p "$(dirname "$HFGCSPY_DB_PATH")" || log_error "Failed to create DB directory."
    sudo mkdir -p "$(dirname "$HFGCSPY_LOG_PATH")" || log_error "Failed to create logs directory."
    
    # Ensure a config.ini exists (copy from template if needed)
    if [ ! -f "$HFGCSPY_CONFIG_FILE" ]; then
        if [ -f "${HFGCSPY_APP_DIR}/config.ini.template" ]; then
            log_info "Copying config.ini.template to config.ini."
            sudo cp "${HFGCSPY_APP_DIR}/config.ini.template" "$HFGCSPY_CONFIG_FILE"
        else
            log_error "config.ini and config.ini.template not found. Cannot proceed with app configuration."
        fi
    else
        log_info "Existing config.ini found. Using existing configuration."
    fi

    # Set initial run mode to standalone (as per requirement)
    if ! sudo grep -q "mode =" "$HFGCSPY_CONFIG_FILE"; then
        log_info "Adding 'mode = standalone' to config.ini."
        echo "" | sudo tee -a "$HFGCSPY_CONFIG_FILE" > /dev/null # Add newline if file is new
        echo "[app]" | sudo tee -a "$HFGCSPY_CONFIG_FILE" > /dev/null
        echo "mode = standalone" | sudo tee -a "$HFGCSPY_CONFIG_FILE" > /dev/null
    else
        log_info "Ensuring 'mode = standalone' in config.ini."
        sudo sed -i '/^mode =/ s/= .*/= standalone/' "$HFGCSPY_CONFIG_FILE"
    fi

    # Add/Update app_paths section in config.ini dynamically from current install paths
    log_info "Updating app_paths in config.ini with correct absolute paths."
    # Ensure the [app_paths] section exists
    if ! sudo grep -q "^\[app_paths\]" "$HFGCSPY_CONFIG_FILE"; then
        echo -e "\n[app_paths]" | sudo tee -a "$HFGCSPY_CONFIG_FILE" > /dev/null
    fi

    # Using awk for safer in-place replacement/addition within sections
    # It attempts to replace lines if they exist, otherwise adds them under [app_paths]
    AWK_SCRIPT='
    BEGIN { in_app_paths=0; status_found=0; messages_found=0; recordings_found=0; config_json_found=0 }
    /^\[app_paths\]$/ { in_app_paths=1 }
    /^\s*status_file\s*=/ && in_app_paths { print "status_file = '"$STATUS_FILE"'"; status_found=1; next }
    /^\s*messages_file\s*=/ && in_app_paths { print "messages_file = '"$MESSAGES_FILE"'"; messages_found=1; next }
    /^\s*recordings_dir\s*=/ && in_app_paths { print "recordings_dir = '"$RECORDINGS_PATH"'"; recordings_found=1; next }
    /^\s*config_json_file\s*=/ && in_app_paths { print "config_json_file = '"$CONFIG_JSON_FILE"'"; config_json_found=1; next }
    { print }
    END {
        if (in_app_paths) {
            if (!status_found) print "status_file = '"$STATUS_FILE"'";
            if (!messages_found) print "messages_file = '"$MESSAGES_FILE"'";
            if (!recordings_found) print "recordings_dir = '"$RECORDINGS_PATH"'";
            if (!config_json_found) print "config_json_file = '"$CONFIG_JSON_FILE"'";
        }
    }'
    sudo awk "$AWK_SCRIPT" "$HFGCSPY_CONFIG_FILE" > /tmp/config_hfgcspy_temp && sudo mv /tmp/config_hfgcspy_temp "$HFGCSPY_CONFIG_FILE"


    # Set up user/group ownership for app directory for proper file access by service
    local HFGCS_USER=$(whoami)
    if [ "$HFGCS_USER" == "root" ]; then
        HFGCS_USER="pi" # Default to 'pi' if script run directly as root
        log_warn "Script run as root. Defaulting HFGCSpy service user to 'pi'. Adjust manually if needed for file permissions."
    fi
    sudo chown -R "$HFGCS_USER":"$HFGCS_USER" "$HFGCSPY_APP_DIR" || log_warn "Failed to set ownership for $HFGCSPY_APP_DIR. Check permissions."
    
    # Create web-accessible data directories and set permissions for Apache
    log_info "Creating web-accessible data directories: ${HFGCSPY_DATA_DIR} and ${HFGCSPY_RECORDINGS_PATH}."
    sudo mkdir -p "$HFGCSPY_DATA_DIR" || log_error "Failed to create HFGCSpy data directory."
    sudo mkdir -p "$HFGCSPY_RECORDINGS_PATH" || log_error "Failed to create HFGCSpy recordings directory."
    sudo chown -R www-data:www-data "$HFGCSPY_DATA_DIR" || log_warn "Failed to set www-data ownership for data directory. Web UI might have issues."
    sudo chmod -R 775 "$HFGCSPY_DATA_DIR" || log_warn "Failed to set permissions for data directory. Web UI might have issues."
    
    log_info "HFGCSpy application configured."
}

# Function to configure Apache2 to serve HFGCSpy's web UI
configure_apache2_webui() {
    log_info "Configuring Apache2 to serve HFGCSpy's web UI..."

    # Ensure Apache2 mods are enabled for basic serving and SSL
    sudo a2enmod headers proxy proxy_http ssl || log_error "Failed to enable Apache2 required modules."
    
    # Copy web UI files to Apache's web root
    log_info "Copying HFGCSpy web UI files to Apache web root: $WEB_ROOT_DIR"
    sudo rm -rf "$WEB_ROOT_DIR" # Clean up previous install if any
    sudo mkdir -p "$WEB_ROOT_DIR" || log_error "Failed to create web root directory."
    sudo cp -r "${HFGCSPY_APP_DIR}/web_ui/." "$WEB_ROOT_DIR/" || log_error "Failed to copy web UI files."
    sudo chown -R www-data:www-data "$WEB_ROOT_DIR" || log_warn "Failed to set www-data ownership for web UI. Web UI might have issues."
    sudo chmod -R 755 "$WEB_ROOT_DIR" || log_warn "Failed to set permissions for web UI. Web UI might have issues."

    # Determine server name (IP address or domain) for Apache config
    SERVER_IP=$(hostname -I | awk '{print $1}')
    read -p "Enter the domain name or IP address to access HFGCSpy web UI (default: $SERVER_IP): " USER_SERVER_NAME
    SERVER_NAME="${USER_SERVER_NAME:-$SERVER_IP}"
    log_info "HFGCSpy web UI will be accessible via: $SERVER_NAME"

    APACHE_CONF="/etc/apache2/sites-available/hfgcspy-webui.conf"

    # Check for existing Let's Encrypt certificates
    LETSENCRYPT_CERTS_BASE_DIR="/etc/letsencrypt/live"
    LE_DOMAINS=()
    USE_SSL="no" # Default to no SSL
    SSL_CERT_PATH=""
    SSL_KEY_PATH=""

    if [ -d "$LETSENCRYPT_CERTS_BASE_DIR" ]; then
        mapfile -t LE_DOMAINS < <(sudo find "$LETSENCRYPT_CERTS_BASE_DIR" -maxdepth 1 -mindepth 1 -type d -printf '%P\n' | grep -v '^README$')
        if [ ${#LE_DOMAINS[@]} -gt 0 ]; then
            log_info "Detected Let's Encrypt certificates for domains: ${LE_DOMAINS[*]}"
            if ask_yes_no "Do you want to configure HFGCSpy web UI to use HTTPS with one of these certificates?"; then
                USE_SSL="yes"
                echo "Available domains with certificates:"
                select DOMAIN_CHOICE in "${LE_DOMAINS[@]}"; do
                    if [ -n "$DOMAIN_CHOICE" ]; then
                        SSL_DOMAIN="$DOMAIN_CHOICE"
                        SSL_CERT_PATH="${LETSENCRYPT_CERTS_BASE_DIR}/${SSL_DOMAIN}/fullchain.pem"
                        SSL_KEY_PATH="${LETSENCRYPT_CERTS_BASE_DIR}/${SSL_DOMAIN}/privkey.pem"
                        break
                    else
                        echo "Invalid selection. Please try again."
                    fi
                done
                log_info "Selected SSL domain: $SSL_DOMAIN"
            else
                log_info "Skipping HTTPS configuration via Let's Encrypt."
            fi
        else
            log_info "No Let's Encrypt certificates found. HTTPS will not be automatically configured."
        fi
    else
        log_info "Let's Encrypt directory $LETSENCRYPT_CERTS_BASE_DIR not found. HTTPS will not be automatically configured."
    fi

    # Create Apache2 configuration for HFGCSpy web UI
    sudo tee "$APACHE_CONF" > /dev/null <<EOF
<VirtualHost *:80>
    ServerName $SERVER_NAME
    DocumentRoot $WEB_ROOT_DIR

    <Directory $WEB_ROOT_DIR>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    # Alias for data directory (status.json, messages.json, recordings)
    Alias /hfgcspy_data "$HFGCSPY_DATA_DIR"
    <Directory "$HFGCSPY_DATA_DIR">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ErrorLog \${APACHE_LOG_DIR}/hfgcspy_webui_error.log
    CustomLog \${APACHE_LOG_DIR}/hfgcspy_webui_access.log combined
</VirtualHost>
EOF

    if [ "$USE_SSL" == "yes" ] && [ -n "$SSL_CERT_PATH" ] && [ -n "$SSL_KEY_PATH" ]; then
        sudo tee -a "$APACHE_CONF" > /dev/null <<EOF
<VirtualHost *:443>
    ServerName $SERVER_NAME
    DocumentRoot $WEB_ROOT_DIR

    <Directory $WEB_ROOT_DIR>
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    # Alias for data directory
    Alias /hfgcspy_data "$HFGCSPY_DATA_DIR"
    <Directory "$HFGCSPY_DATA_DIR">
        Options Indexes FollowSymLinks
        AllowOverride None
        Require all granted
    </Directory>

    ErrorLog \${APACHE_LOG_DIR}/hfgcspy_webui_ssl_error.log
    CustomLog \${APACHE_LOG_DIR}/hfgcspy_webui_ssl_access.log combined

    SSLEngine on
    SSLCertificateFile "$SSL_CERT_PATH"
    SSLCertificateKeyFile "$SSL_KEY_PATH"
    # Certbot usually creates chain.pem and fullchain.pem. Use fullchain.pem often includes chain.
    # If fullchain.pem is used for SSLCertificateFile, chain.pem is often not needed separately.
    # However, if explicitly needed for older setups or specific configurations, it can be added.
    # For robust compatibility, explicitly try to include chain.pem if available and different from fullchain.
    if [ -f "${LETSENCRYPT_CERTS_BASE_DIR}/${SSL_DOMAIN}/chain.pem" ] && [ "$SSL_CERT_PATH" != "${LETSENCRYPT_CERTS_BASE_DIR}/${SSL_DOMAIN}/fullchain.pem" ]; then
        echo "SSLCertificateChainFile \"${LETSENCRYPT_CERTS_BASE_DIR}/${SSL_DOMAIN}/chain.pem\"" | sudo tee -a "$APACHE_CONF" > /dev/null
    fi

    # HSTS (optional, highly recommended for security)
    Header always set Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
</VirtualHost>
EOF
        log_info "Apache2 SSL configuration added for $SSL_DOMAIN. Ensure permissions are correct for Apache to read cert files."
    else
        log_info "HTTPS will not be automatically configured. HFGCSpy web UI will be available via HTTP only."
    fi

    # Disable default Apache site and enable HFGCSpy web UI site
    sudo a2dissite 000-default.conf 2>/dev/null || true
    sudo a2ensite hfgcspy-webui.conf || log_error "Failed to enable HFGCSpy web UI Apache2 site."
    
    sudo systemctl restart apache2 || log_error "Failed to restart Apache2. Check its logs for errors."
    log_info "Apache2 configured to serve HFGCSpy web UI."
    log_info "Access HFGCSpy at http://${SERVER_NAME}/hfgcspy (and https://${SERVER_NAME}/hfgcspy if SSL was configured)."
}


# Function to setup HFGCSpy systemd service
setup_systemd_service() {
    log_info "Setting up HFGCSpy as a systemd service..."
    local HFGCS_USER=$(whoami) # Use the user running the script
    if [ "$HFGCS_USER" == "root" ]; then
        HFGCS_USER="pi" # Default to 'pi' if script run directly as root
        log_warn "Script run as root. Defaulting HFGCSpy service user to 'pi'. Adjust manually if needed."
    fi

    SERVICE_FILE="/etc/systemd/system/${HFGCSPY_SERVICE_NAME}"
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=HFGCSpy SDR Scanner and Parser
After=network.target

[Service]
WorkingDirectory=${HFGCSPY_APP_DIR}
ExecStart=${HFGCSPY_VENV_DIR}/bin/python3 ${HFGCSPY_APP_DIR}/hfgcs.py --run
StandardOutput=inherit
StandardError=inherit
Restart=always
User=${HFGCS_USER}

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload || log_error "Failed to reload systemd daemon."
    
    if ask_yes_no "Do you want HFGCSpy to start automatically at machine boot? (Recommended: Yes)"; then
        sudo systemctl enable "$HFGCSPY_SERVICE_NAME" || log_error "Failed to enable HFGCSpy service at boot."
        log_info "HFGCSpy service enabled to start automatically at boot."
    else
        sudo systemctl disable "$HFGCSPY_SERVICE_NAME" || log_error "Failed to disable HFGCSpy service at boot."
        log_info "HFGCSpy service will NOT start automatically at boot. You'll need to start it manually: sudo systemctl start ${HFGCSPY_SERVICE_NAME}"
    fi

    sudo systemctl start "$HFGCSPY_SERVICE_NAME" || log_error "Failed to start HFGCSpy service immediately."
    
    log_info "HFGCSpy service setup complete."
}

# Main installation logic
install_hfgcspy() {
    prompt_for_paths # Ask user for install paths first
    install_system_and_python_deps
    configure_hfgcspy_app # Configure HFGCSpy app settings and directories
    configure_apache2_webui # Configure Apache2 to serve static web UI
    setup_systemd_service # Setup and start the hfgcs.py daemon
}

# Function to run HFGCSpy application directly (for debugging or manual start)
run_hfgcspy() {
    log_info "Attempting to run HFGCSpy directly (this will block the terminal).."
    log_info "To run as a service in the background, use 'sudo systemctl start ${HFGCSPY_SERVICE_NAME}'."
    cd "$HFGCSPY_APP_DIR" || log_error "HFGCSpy application directory not found. Ensure it is installed at $HFGCSPY_APP_DIR or specify correct path."
    # Direct execution of hfgcs.py
    "$HFGCSPY_VENV_DIR"/bin/python3 hfgcs.py --run || log_error "Failed to start HFGCSpy directly."
}

# Function to stop HFGCSpy service
stop_hfgcspy() {
    log_info "Stopping HFGCSpy service..."
    sudo systemctl stop "$HFGCSPY_SERVICE_NAME" || log_warn "HFGCSpy service not running or failed to stop."
    log_info "HFGCSpy service stopped."
}

# Function to display status
status_hfgcspy() {
    log_info "Checking HFGCSpy service status..."
    sudo systemctl status "$HFGCSPY_SERVICE_NAME"
    
    log_info "Checking Apache2 service status..."
    sudo systemctl status apache2

    log_info "Checking listening ports for Apache2..."
    sudo netstat -tuln | grep ":80 " || sudo netstat -tuln | grep ":443 "
    
    log_info "SDR dongle status:"
    check_sdr # Reusing check_sdr from previous script
}

# Function to uninstall HFGCSpy
uninstall_hfgcspy() {
    log_warn "Stopping and disabling HFGCSpy service..."
    sudo systemctl stop "$HFGCSPY_SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$HFGCSPY_SERVICE_NAME" 2>/dev/null || true
    sudo rm -f /etc/systemd/system/"$HFGCSPY_SERVICE_NAME"
    sudo systemctl daemon-reload
    
    log_warn "Removing HFGCSpy application directory: $HFGCSPY_APP_DIR..."
    sudo rm -rf "$HFGCSPY_APP_DIR" || log_error "Failed to remove $HFGCSPY_APP_DIR. Manual removal might be needed."

    log_warn "Removing Apache2 web UI directory: $WEB_ROOT_DIR..."
    sudo rm -rf "$WEB_ROOT_DIR" || log_warn "Failed to remove web UI directory. Manual removal might be needed."

    log_warn "Removing Apache2 configuration for HFGCSpy web UI (if it exists)..."
    sudo a2dissite hfgcspy-webui.conf 2>/dev/null || true
    sudo rm -f /etc/apache2/sites-available/hfgcspy-webui.conf
    sudo rm -f /etc/apache2/sites-enabled/hfgcspy-webui.conf
    sudo systemctl restart apache2 2>/dev/null || true
    
    log_info "HFGCSpy uninstallation complete."
    log_info "You may want to manually remove the DVB-T blacklisting file: /etc/modprobe.d/blacklist-rtl.conf"
}

# Function to update HFGCSpy
update_hfgcspy() {
    log_info "Stopping HFGCSpy service for update..."
    sudo systemctl stop "$HFGCSPY_SERVICE_NAME" || log_warn "HFGCSpy service not running or failed to stop, proceeding with update anyway."
    
    if [ ! -d "$HFGCSPY_APP_DIR" ]; then
        log_error "HFGCSpy not found at $HFGCSPY_APP_DIR. Please run '--install' first."
    fi
    
    log_info "Pulling latest changes from HFGCSpy repository..."
    cd "$HFGCSPY_APP_DIR" || log_error "Failed to change directory to "$HFGCSPY_APP_DIR"."
    sudo git pull || log_error "Failed to pull latest changes from Git."
    
    log_info "Reinstalling Python dependencies (if any new ones exist)..."
    sudo "$HFGCSPY_VENV_DIR"/bin/pip install -r "${HFGCSPY_APP_DIR}/requirements.txt" || log_warn "Failed to reinstall Python dependencies. Continuing."

    log_info "Re-copying web UI files to Apache web root..."
    sudo rm -rf "$WEB_ROOT_DIR" # Clean up old files
    sudo mkdir -p "$WEB_ROOT_DIR" || log_error "Failed to create web root directory."
    sudo cp -r "${HFGCSPY_APP_DIR}/web_ui/." "$WEB_ROOT_DIR/" || log_error "Failed to copy web UI files."
    sudo chown -R www-data:www-data "$WEB_ROOT_DIR" || log_warn "Failed to set www-data ownership for web UI. Web UI might have issues."
    sudo chmod -R 755 "$WEB_ROOT_DIR" || log_warn "Failed to set permissions for web UI. Web UI might have issues."
    
    log_info "Restarting HFGCSpy service..."
    sudo systemctl start "$HFGCSPY_SERVICE_NAME" || log_error "Failed to start HFGCSpy service after update."
    log_info "HFGCSpy updated and restarted."
    log_info "Remember to restart Apache2 if there were any issues or config changes: sudo systemctl restart apache2"
}

# Function to check SDR presence (reused from previous script)
check_sdr() {
    log_info "Checking for RTL-SDR dongle presence on host system..."
    if command -v rtl_test &> /dev/null; then
        log_info "rtl_test command found. Running test..."
        if timeout 5s rtl_test -t -s 1M -d 0 -r 2>&1 | grep -q "Found"; then
            log_info "RTL-SDR dongle detected and appears to be working."
        else
            log_warn "No RTL-SDR dongle detected or it's not working correctly."
            log_warn "Ensure your RTL-SDR is plugged in and the blacklisting of DVB-T modules has taken effect (may require reboot)."
            log_info "Full rtl_test output (if available):"
            timeout 5s rtl_test -t || echo "rtl_test timed out or produced no output."
        fi
    else
        log_warn "rtl_test not found. It should have been installed. Please ensure build-essential and rtl-sdr packages are installed."
    fi
}

# --- Main Script Logic ---

log_info "HFGCSpy Installer (Version: ${SCRIPT_VERSION})"

if [ "$#" -eq 0 ]; then
    log_error "No arguments provided. Usage: $(basename "$0") [--install|--run|--stop|--status|--uninstall|--update|--check_sdr]"
fi

# Parse command line arguments
case "$1" in
    --install)
        check_root "$@"
        install_hfgcspy
        log_info "HFGCSpy installation complete. Please consider rebooting your Raspberry Pi for full effect."
        ;;
    --run)
        # Note: --run is for direct execution of the hfgcs.py main script, not for service management
        run_hfgcspy
        ;;
    --stop)
        check_root "$@"
        stop_hfgcspy
        ;;
    --status)
        status_hfgcspy
        ;;
    --uninstall)
        check_root "$@"
        uninstall_hfgcspy
        ;;
    --update)
        check_root "$@"
        update_hfgcspy
        ;;
    --check_sdr)
        check_sdr
        ;;
    *)
        log_error "Invalid argument: $1. Usage: $(basename "$0") [--install|--run|--stop|--status|--uninstall|--update|--check_sdr]"
        ;;
esac

log_info "Operation finished."
