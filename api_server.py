# HFGCSpy/api_server.py
# Flask API server for HFGCSpy, runs inside the Docker container.
# This API serves data to the web UI and handles configuration updates.
# Version: 2.0.0

import os
import sys
import json
import configparser
import logging
from flask import Flask, jsonify, request, send_from_directory
from datetime import datetime

# Add parent directory to path to allow importing core modules
# This assumes /app is the working directory inside the Docker container
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))

from data_store import DataStore
from sdr_manager import SDRManager # For listing detected SDRs

# --- Configuration Loading ---
config = configparser.ConfigParser()
CONFIG_FILE_PATH = "/app/config.ini" # Path inside Docker container
CONFIG_JSON_FILE_PATH = "/app/data/hfgcspy_data/config.json" # Path inside Docker container for UI to read

try:
    config.read(CONFIG_FILE_PATH)
    DB_PATH = config.get('app', 'database_path', fallback='/app/data/hfgcspy.db')
    LOG_FILE = config.get('logging', 'log_file', fallback='/app/logs/hfgcspy.log')
    INTERNAL_PORT = config.get('app', 'internal_port', fallback='8002')
    RECORDINGS_DIR = config.get('app_paths', 'recordings_dir', fallback='/app/data/recordings')

except configparser.Error as e:
    print(f"ERROR: Could not read config.ini in api_server: {e}. Using default paths.")
    DB_PATH = '/app/data/hfgcspy.db'
    LOG_FILE = '/app/logs/hfgcspy.log'
    INTERNAL_PORT = '8002'
    RECORDINGS_DIR = '/app/data/recordings'

# --- Logging Setup for Flask API ---
# Use a separate logger for Flask API if desired, or share with main app logger
logging.basicConfig(
    level=logging.INFO, # Default to INFO for API logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE), # Log to the same file as main app
        logging.StreamHandler(sys.stdout)
    ]
)
flask_logger = logging.getLogger('HFGCSpy.API')
flask_logger.info("HFGCSpy Flask API server starting...")


# Initialize Flask app
app = Flask(__name__, 
            static_folder='/app/web_ui', # Static files for web UI (served by Apache, but Flask can serve for dev)
            template_folder='/app/web_ui') # Templates for web UI (not used much if JS renders)

# Initialize DataStore
data_store = DataStore(DB_PATH)
data_store.initialize_db()

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main HFGCSpy web dashboard HTML."""
    # This endpoint is primarily for direct access during development/testing.
    # In production, Apache2 will serve index.html directly.
    return send_from_directory('/app/web_ui', 'index.html')

@app.route('/styles.css')
def serve_styles():
    return send_from_directory('/app/web_ui', 'styles.css')

@app.route('/script.js')
def serve_script():
    return send_from_directory('/app/web_ui', 'script.js')

@app.route('/recordings/<path:filename>')
def serve_recording(filename):
    """Serves recorded audio files."""
    return send_from_directory(RECORDINGS_DIR, filename)


@app.route('/hfgcspy-api/status')
def get_status():
    """Returns the current status of the HFGCSpy application and detected SDRs."""
    status_data = {
        "hfgcs_service": "Running", # These will be updated by main hfgcs.py loop
        "js8_service": "Running",
        "adsb_service": "Running",
        "sdr_devices": {}, # Operational status of SDRs managed by main loop
        "detected_sdr_devices": SDRManager.list_sdr_devices_serials(), # Live detection
        "selected_sdr_devices": [], # From config, will be updated by main loop
        "app_version": config.get('app', 'version', fallback='N/A'), # Get version from config
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    # Read actual status from a file written by hfgcs.py if needed, for now use dummy
    try:
        with open(STATUS_FILE, 'r') as f:
            live_status = json.load(f)
            status_data.update(live_status)
    except FileNotFoundError:
        flask_logger.warn(f"Status file {STATUS_FILE} not found. Using default status.")
    except json.JSONDecodeError:
        flask_logger.error(f"Error decoding status file {STATUS_FILE}. Using default status.")
    
    flask_logger.debug(f"API status requested: {status_data}")
    return jsonify(status_data)

@app.route('/hfgcspy-api/messages')
def get_messages():
    """Retrieves recent HFGCS messages from the database."""
    # This endpoint can be extended to take table_name and sdr_id as args
    table_name = request.args.get('table', 'hfgcs_messages')
    sdr_id = request.args.get('sdr_id', None)
    limit = request.args.get('limit', config.getint('app', 'messages_per_page', fallback=50), type=int)

    messages = data_store.get_recent_messages(table_name=table_name, limit=limit, sdr_id=sdr_id)
    
    # Ensure timestamp is string for JSON serialization if not already
    for msg in messages:
        if 'timestamp' in msg and isinstance(msg['timestamp'], datetime):
            msg['timestamp'] = msg['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
        elif 'timestamp' not in msg:
            msg['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg['table_name'] = table_name # Ensure table_name is in message for UI delete action

    flask_logger.debug(f"API messages requested from {table_name}, sdr_id={sdr_id}, limit={limit}. Returning {len(messages)} messages.")
    return jsonify(messages)


@app.route('/hfgcspy-api/config')
def get_config():
    """Retrieves current configuration settings for the UI."""
    config_data = {}
    try:
        # Read config.ini and export relevant parts as JSON
        config_obj = configparser.ConfigParser()
        config_obj.read(CONFIG_FILE_PATH)

        config_data['app'] = {
            'dark_mode': config_obj.getboolean('app', 'dark_mode', fallback=True), # Default dark mode
            'messages_per_page': config_obj.getint('app', 'messages_per_page', fallback=50),
            'internal_port': config_obj.get('app', 'internal_port', fallback='8002')
        }
        config_data['scan_services'] = {
            'hfgcs': config_obj.get('scan_services', 'hfgcs', fallback='no'),
            'js8': config_obj.get('scan_services', 'js8', fallback='no'),
            'adsb': config_obj.get('scan_services', 'adsb', fallback='no')
        }
        config_data['sdr_selection'] = {
            'selected_devices': [s.strip() for s in config_obj.get('sdr_selection', 'selected_devices', fallback='').split(',') if s.strip()]
        }
        online_sdrs_list = {}
        if config_obj.has_section('online_sdrs'):
            for name, url_type in config_obj.items('online_sdrs'):
                parts = url_type.split(',', 1)
                url = parts[0].strip()
                sdr_type = parts[1].strip() if len(parts) > 1 else 'unknown'
                online_sdrs_list[name] = {'url': url, 'type': sdr_type}
        config_data['online_sdrs'] = {'list_of_sdrs': online_sdrs_list}

        # Add detected SDRs from SDRManager (live data)
        config_data['detected_sdr_devices'] = SDRManager.list_sdr_devices_serials()

        # Write this JSON to a file for the UI to read (Apache serves it)
        with open(CONFIG_JSON_FILE_PATH, 'w') as f:
            json.dump(config_data, f, indent=4)
        
        flask_logger.debug(f"Config exported to {CONFIG_JSON_FILE_PATH}")
        return jsonify(config_data)

    except Exception as e:
        flask_logger.error(f"Error getting config: {e}", exc_info=True)
        return jsonify({"error": "Failed to load config"}), 500

@app.route('/hfgcspy-api/config', methods=['POST'])
def save_config():
    """Receives config updates from the UI and writes them to config.ini."""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    new_config_data = request.get_json()
    flask_logger.info(f"Received config update from UI: {new_config_data}")

    try:
        config_obj = configparser.ConfigParser()
        config_obj.read(CONFIG_FILE_PATH) # Read current config to preserve other settings

        # Update sections based on new_config_data
        if 'app' in new_config_data:
            if not config_obj.has_section('app'): config_obj.add_section('app')
            for key, value in new_config_data['app'].items():
                config_obj.set('app', key, str(value))
        
        if 'scan_services' in new_config_data:
            if not config_obj.has_section('scan_services'): config_obj.add_section('scan_services')
            for key, value in new_config_data['scan_services'].items():
                config_obj.set('scan_services', key, str(value))

        if 'sdr_selection' in new_config_data:
            if not config_obj.has_section('sdr_selection'): config_obj.add_section('sdr_selection')
            selected_devices_str = ','.join(new_config_data['sdr_selection'].get('selected_devices', []))
            config_obj.set('sdr_selection', 'selected_devices', selected_devices_str)
        
        if 'online_sdrs' in new_config_data and 'list_of_sdrs' in new_config_data['online_sdrs']:
            if not config_obj.has_section('online_sdrs'): config_obj.add_section('online_sdrs')
            # Clear existing online_sdrs to rewrite
            for option in config_obj.options('online_sdrs'):
                config_obj.remove_option('online_sdrs', option)
            # Add new online SDRs
            for name, sdr_info in new_config_data['online_sdrs']['list_of_sdrs'].items():
                config_obj.set('online_sdrs', name, f"{sdr_info['url']},{sdr_info['type']}")

        with open(CONFIG_FILE_PATH, 'w') as f:
            config_obj.write(f)
        
        flask_logger.info("Config.ini updated successfully from UI.")
        # Trigger a restart of the main hfgcs.py loop to apply changes
        # This requires hfgcs.py to expose a mechanism to restart its loop.
        # For now, we'll just log that a restart is needed.
        flask_logger.info("HFGCSpy service restart needed to apply new config.ini changes.")
        return jsonify({"status": "Success", "message": "Config saved. Restart HFGCSpy service for changes to take effect."})

    except Exception as e:
        flask_logger.error(f"Error saving config: {e}", exc_info=True)
        return jsonify({"status": "Error", "message": "Failed to save config."}), 500

@app.route('/hfgcspy-api/messages/<table_name>/<int:message_id>', methods=['DELETE'])
def delete_message_api(table_name, message_id):
    """Deletes a message from a specified table."""
    try:
        success = data_store.delete_message(table_name, message_id)
        if success:
            flask_logger.info(f"Deleted message ID {message_id} from table {table_name}.")
            return jsonify({"status": "Success", "message": "Message deleted."})
        else:
            return jsonify({"status": "Error", "message": "Message not found or failed to delete."}), 404
    except Exception as e:
        flask_logger.error(f"Error deleting message: {e}", exc_info=True)
        return jsonify({"status": "Error", "message": "Failed to delete message."}), 500

# This part runs the Flask app when api_server.py is executed directly (e.g., by Gunicorn)
if __name__ == '__main__':
    flask_logger.info(f"Flask API running on port {INTERNAL_PORT}")
    app.run(host='0.0.0.0', port=INTERNAL_PORT, debug=False)

