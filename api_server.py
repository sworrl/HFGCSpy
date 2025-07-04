# HFGCSpy/api_server.py
# Version: 1.0.1 # Version bump for config loading and basic routes

from flask import Flask, jsonify, request, send_from_directory
import logging
import os
import configparser
from datetime import datetime
import json

# Import DataStore and SDRManager from core
from core.data_store import DataStore
from core.sdr_manager import SDRManager

# --- Logging Configuration ---
# This needs to be set up before Flask app creation to ensure Flask uses it
log_file_path = "/app/logs/hfgcspy.log" # Default path, will be updated from config
if not os.path.exists(os.path.dirname(log_file_path)):
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler(log_file_path),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration Loading ---
# Paths are relative to the container's /app directory unless specified otherwise
CONFIG_FILE_PATH = "/app/config.ini" # This is the mounted config.ini from host

# Global variables for paths, initialized to None or defaults
STATUS_FILE = None
MESSAGES_FILE = None
RECORDINGS_DIR = None
CONFIG_JSON_FILE = None # For frontend config
INTERNAL_PORT = None
DB_PATH = None

def load_config_paths():
    global STATUS_FILE, MESSAGES_FILE, RECORDINGS_DIR, CONFIG_JSON_FILE, INTERNAL_PORT, DB_PATH
    config = configparser.ConfigParser()
    
    if not os.path.exists(CONFIG_FILE_PATH):
        logger.error(f"Config file not found at {CONFIG_FILE_PATH}. Using default paths.")
        # Fallback to hardcoded defaults if config.ini doesn't exist or isn't mounted
        # These should match the defaults in setup.py's configure_hfgcspy_app
        STATUS_FILE = "/app/data/hfgcspy_data/status.json"
        MESSAGES_FILE = "/app/data/hfgcspy_data/messages.json"
        RECORDINGS_DIR = "/app/data/hfgcspy_data/recordings"
        CONFIG_JSON_FILE = "/app/data/hfgcspy_data/config.json"
        INTERNAL_PORT = 8002
        DB_PATH = "/app/data/hfgcspy.db"
        return False

    try:
        config.read(CONFIG_FILE_PATH)
        
        # Paths from config.ini are relative to the container's /app
        # For mounted volumes, these paths need to reflect the *container's* view
        app_paths_section = config['app_paths'] if 'app_paths' in config else {}
        app_section = config['app'] if 'app' in config else {}
        logging_section = config['logging'] if 'logging' in config else {}

        STATUS_FILE = app_paths_section.get('status_file', "/app/data/hfgcspy_data/status.json")
        MESSAGES_FILE = app_paths_section.get('messages_file', "/app/data/hfgcspy_data/messages.json")
        RECORDINGS_DIR = app_paths_section.get('recordings_dir', "/app/data/hfgcspy_data/recordings")
        CONFIG_JSON_FILE = app_paths_section.get('config_json_file', "/app/data/hfgcspy_data/config.json")
        INTERNAL_PORT = int(app_section.get('internal_port', 8002))
        DB_PATH = app_section.get('database_path', "/app/data/hfgcspy.db")

        # Update logger to use path from config.ini
        new_log_file_path = logging_section.get('log_file', "/app/logs/hfgcspy.log")
        if new_log_file_path != log_file_path:
            # Reconfigure logging to the new path
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)
            logging.basicConfig(level=logging.INFO,
                                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                handlers=[
                                    logging.FileHandler(new_log_file_path),
                                    logging.StreamHandler()
                                ])
            logger.info(f"Logging reconfigured to: {new_log_file_path}")

        logger.info("Configuration paths loaded successfully.")
        return True
    except Exception as e:
        logger.error(f"Error loading configuration from {CONFIG_FILE_PATH}: {e}", exc_info=True)
        return False

# Load config paths at startup
load_config_paths()

# Ensure data directories exist within the container
os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_JSON_FILE), exist_ok=True)

# Initialize DataStore after config is loaded
data_store = DataStore(db_path=DB_PATH)
data_store.initialize_db()

# Initialize SDRManager (device_identifier will be set via config later)
sdr_manager = SDRManager()

# --- Utility Functions ---
def update_status_file(status_data):
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=4)
        logger.debug("Status file updated.")
    except Exception as e:
        logger.error(f"Error updating status file {STATUS_FILE}: {e}")

def get_current_status():
    status = {
        "hfgcs_service": "Stopped",
        "js8_service": "Stopped",
        "sdr_devices": {},
        "online_sdrs": {},
        "current_frequency": 0,
        "signal_power": 0,
        "last_updated": datetime.now().isoformat()
    }
    
    # Attempt to read existing status
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                existing_status = json.load(f)
                status.update(existing_status)
        except Exception as e:
            logger.warning(f"Could not read existing status file: {e}")

    # Update SDR device status dynamically
    sdr_serials = sdr_manager.list_sdr_devices_serials()
    for serial in sdr_serials:
        status["sdr_devices"][serial] = "Detected" # Or "Active" if actively scanning

    # Placeholder for actual service states and SDR parameters
    # In a real implementation, these would come from the running SDR threads/processes
    
    return status

# --- Flask Routes ---

@app.route('/')
def index():
    # Serve the index.html from the root of the app
    # Assumes index.html is in the /app directory (Docker WORKDIR)
    return send_from_directory('/app', 'index.html')

@app.route('/hfgcspy-api/status', methods=['GET'])
def get_status():
    status = get_current_status()
    # Placeholder for actual SDR status, freq, power
    # This would be updated by background SDR scanning threads
    return jsonify(status)

@app.route('/hfgcspy-api/messages', methods=['GET'])
def get_messages():
    messages = data_store.get_recent_messages(table_name='hfgcs_messages', limit=50)
    js8_messages = data_store.get_recent_messages(table_name='js8_messages', limit=50)
    adsb_messages = data_store.get_recent_messages(table_name='adsb_messages', limit=50)
    
    all_messages = messages + js8_messages + adsb_messages
    # Sort by timestamp descending
    all_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return jsonify(all_messages)

@app.route('/hfgcspy-api/messages/<table_name>/<int:message_id>', methods=['DELETE'])
def delete_message(table_name, message_id):
    if data_store.delete_message(table_name, message_id):
        return jsonify({"status": "Success", "message": f"Message {message_id} from {table_name} deleted."})
    return jsonify({"status": "Error", "message": f"Failed to delete message {message_id} from {table_name}."}), 400

@app.route('/hfgcspy-api/config', methods=['POST'])
def update_config():
    data = request.json
    # This endpoint would typically write changes back to config.ini
    # and then signal the background processes to reload config.
    # For now, it's a placeholder.
    logger.info(f"Received config update request: {data}")
    return jsonify({"status": "Success", "message": "Config update received (not fully implemented)."})

@app.route('/hfgcspy-api/decode-with-gemini', methods=['POST'])
def decode_with_gemini():
    # Placeholder for Gemini API call
    data = request.json
    message_id = data.get('message_id')
    decoded_text = data.get('decoded_text')

    if not decoded_text:
        return jsonify({"status": "Error", "message": "No decoded text provided for Gemini analysis."}), 400

    logger.info(f"Attempting Gemini decode for message ID {message_id}: {decoded_text[:50]}...")
    
    # --- Gemini API Call Placeholder ---
    # This is where the actual Gemini API call would go.
    # For now, we return a mock response.
    #
    # Example structure for Gemini API call (requires API key and proper setup):
    #
    # chatHistory = []
    # prompt = f"Analyze the following HFGCS message and explain its likely meaning, context, and any notable elements: '{decoded_text}'"
    # chatHistory.push({ role: "user", parts: [{ text: prompt }] });
    # payload = { contents: chatHistory };
    # apiKey = "" # If you want to use models other than gemini-2.0-flash, provide an API key here. Otherwise, leave this as-is.
    # apiUrl = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`;
    # response = await fetch(apiUrl, {
    #            method: 'POST',
    #            headers: { 'Content-Type': 'application/json' },
    #            body: JSON.stringify(payload)
    #        });
    # result = response.json();
    # gemini_analysis = result.candidates[0].content.parts[0].text;
    #
    # ------------------------------------

    mock_gemini_analysis = f"Gemini mock analysis for: '{decoded_text}'. This would be a detailed interpretation of the HFGCS code."
    
    # Update the database with Gemini's response
    # This requires a new column in hfgcs_messages table: gemini_analysis_text
    # And a method in DataStore to update it.
    # data_store.update_hfgcs_message_gemini_analysis(message_id, mock_gemini_analysis)
    
    return jsonify({"status": "Success", "message": "Gemini analysis complete.", "gemini_analysis": mock_gemini_analysis})

@app.route('/control_sdr', methods=['POST'])
def control_sdr():
    data = request.json
    action = data.get('action')
    sdr_id = data.get('sdr_id')

    if action == 'start':
        sdr_manager.open_sdr()
        return jsonify({"status": "Success", "message": f"SDR {sdr_id} started."})
    elif action == 'stop':
        sdr_manager.close_sdr()
        return jsonify({"status": "Success", "message": f"SDR {sdr_id} stopped."})
    elif action == 'set_frequency':
        frequency = float(data.get('frequency')) * 1e6 # Convert MHz to Hz
        sdr_manager.set_frequency(frequency)
        return jsonify({"status": "Success", "message": f"SDR {sdr_id} frequency set to {frequency/1e6} MHz."})
    
    return jsonify({"status": "Error", "message": "Invalid SDR control action."}), 400

@app.route('/control_online_sdr', methods=['POST'])
def control_online_sdr():
    data = request.json
    action = data.get('action')
    sdr_name = data.get('sdr_name')
    sdr_url = data.get('sdr_url')
    sdr_type = data.get('sdr_type')

    # This functionality would involve managing a list of online SDRs,
    # potentially storing them in the config.ini or a separate DB table.
    # For now, it's a placeholder.
    if action == 'add':
        logger.info(f"Adding online SDR: {sdr_name} ({sdr_url}, {sdr_type})")
        return jsonify({"status": "Success", "message": f"Online SDR {sdr_name} added (placeholder)."})
    elif action == 'remove':
        logger.info(f"Removing online SDR: {sdr_name}")
        return jsonify({"status": "Success", "message": f"Online SDR {sdr_name} removed (placeholder)."})
    
    return jsonify({"status": "Error", "message": "Invalid online SDR control action."}), 400

# Route to serve static files (recordings, status.json, etc.)
@app.route('/hfgcspy_data/<path:filename>')
def serve_hfgcspy_data(filename):
    # Ensure RECORDINGS_DIR is correctly configured
    if not RECORDINGS_DIR:
        load_config_paths() # Attempt to load config if not already loaded

    # Security: Ensure filename is within the allowed data directory
    # This is a basic check; more robust path validation might be needed in production
    base_dir = os.path.dirname(STATUS_FILE) # Use the base data directory
    
    # Prevent directory traversal
    abs_path = os.path.join(base_dir, filename)
    if not os.path.abspath(abs_path).startswith(os.path.abspath(base_dir)):
        return "Forbidden", 403

    return send_from_directory(base_dir, filename)


if __name__ == '__main__':
    logger.info("HFGCSpy Flask API server starting...")
    # This block is for direct Python execution, not for Gunicorn.
    # Gunicorn will call the 'app' callable directly.
    # For development, you might run app.run(host='0.0.0.0', port=INTERNAL_PORT, debug=True)
    # However, in Docker with Gunicorn, this __main__ block is typically not executed.
    # The Gunicorn command in Dockerfile points directly to 'api_server:app'
    pass
