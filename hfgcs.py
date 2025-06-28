# HFGCSpy/hfgcs.py
# Main entry point for HFGCSpy application.
# Version: 0.0.3 # Updated version

__version__ = "0.0.3"

import argparse
import os
import time
import logging
import sys
import json
import configparser
import threading
from datetime import datetime

# Import core modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.sdr_manager import SDRManager
from core.data_store import DataStore

# --- Configuration Loading and Global Paths ---
config = configparser.ConfigParser()
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), 'config.ini')

# Default paths if config.ini isn't fully loaded or specified
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'hfgcspy.db')
DEFAULT_LOG_PATH = os.path.join(os.path.dirname(__file__), 'logs', 'hfgcspy.log')
DEFAULT_STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'var', 'www', 'html', 'hfgcspy', 'hfgcspy_data', 'status.json')
DEFAULT_MESSAGES_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'var', 'www', 'html', 'hfgcspy', 'hfgcspy_data', 'messages.json')
DEFAULT_RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'var', 'www', 'html', 'hfgcspy', 'hfgcspy_data', 'recordings')
DEFAULT_CONFIG_JSON_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'var', 'www', 'html', 'hfgcspy', 'hfgcspy_data', 'config.json')


try:
    config.read(CONFIG_FILE_PATH)
    APP_MODE = config.get('app', 'mode', fallback='standalone')
    DB_PATH = config.get('app', 'database_path', fallback=DEFAULT_DB_PATH)
    LOG_FILE = config.get('logging', 'log_file', fallback=DEFAULT_LOG_PATH)
    LOG_LEVEL = config.get('logging', 'log_level', fallback='INFO').upper()
    
    # Paths for files exposed via Apache2
    STATUS_FILE = config.get('app_paths', 'status_file', fallback=DEFAULT_STATUS_FILE)
    MESSAGES_FILE = config.get('app_paths', 'messages_file', fallback=DEFAULT_MESSAGES_FILE)
    RECORDINGS_DIR = config.get('app_paths', 'recordings_dir', fallback=DEFAULT_RECORDINGS_DIR)
    CONFIG_JSON_FILE = config.get('app_paths', 'config_json_file', fallback=DEFAULT_CONFIG_JSON_FILE)


except configparser.Error as e:
    print(f"ERROR: Could not read config.ini: {e}. Using default paths/settings.")
    APP_MODE = 'standalone'
    DB_PATH = DEFAULT_DB_PATH
    LOG_FILE = DEFAULT_LOG_PATH
    LOG_LEVEL = 'INFO'
    STATUS_FILE = DEFAULT_STATUS_FILE
    MESSAGES_FILE = DEFAULT_MESSAGES_FILE
    RECORDINGS_DIR = DEFAULT_RECORDINGS_DIR
    CONFIG_JSON_FILE = DEFAULT_CONFIG_JSON_FILE

# Create necessary directories
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True) # Ensure web-accessible data dir exists
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_JSON_FILE), exist_ok=True) # Ensure config.json dir exists

# --- Logging Setup ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('HFGCSpy')
logger.info(f"HFGCSpy application started. Version: {__version__}")

# --- Global State for SDR Operations and Services ---
sdr_threads = {} # Dict to hold SDRManager instances and their threads
data_store = DataStore(DB_PATH) # Initialize DataStore globally
data_store.initialize_db()

# Service status flags (managed by polling config.ini)
hfgcs_scan_enabled = False
js8_scan_enabled = False

# SDR devices selected from config (list of serials or indices)
selected_sdr_devices = []

# --- Functions for Status and Config Export to JSON ---
def update_web_status_file(detected_sdr_serials, selected_sdr_serials):
    """Writes the current service and SDR status to status.json for the web UI."""
    status_data = {
        "hfgcs_service": "Running" if hfgcs_scan_enabled else "Stopped", # Placeholder status
        "js8_service": "Running" if js8_scan_enabled else "Stopped",     # Placeholder status
        "sdr_devices": { # Actual operational status of each SDR thread
            sdr_id: "Active" if thread.is_alive() else "Inactive"
            for sdr_id, (manager, thread, _) in sdr_threads.items()
        },
        "detected_sdr_devices": detected_sdr_serials, # All SDRs found on system
        "selected_sdr_devices": selected_sdr_serials, # SDRs chosen in config
        "app_version": __version__,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(status_data, f, indent=4)
        logger.debug(f"Status written to {STATUS_FILE}")
    except IOError as e:
        logger.error(f"Failed to write status file {STATUS_FILE}: {e}")

def export_recent_messages_to_json(table_name='hfgcs_messages'):
    """Exports recent messages from a specific SQLite table to messages.json for the web UI."""
    try:
        limit = config.getint('app', 'messages_per_page', fallback=50)
        messages = data_store.get_recent_messages(table_name=table_name, limit=limit)
        
        # Ensure timestamp is string for JSON serialization
        for msg in messages:
            # Ensure timestamp is present before formatting
            if 'timestamp' in msg and isinstance(msg['timestamp'], str):
                # If it's already a string, assume it's in a format compatible with JS Date
                # or ensure it's converted to ISO format for consistent parsing
                pass # Already a string, no re-conversion needed unless format is wrong
            elif 'timestamp' in msg and isinstance(msg['timestamp'], datetime):
                msg['timestamp'] = msg['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            else:
                msg['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Fallback
            
            # Add table_name for UI delete action to know which table to target
            msg['table_name'] = table_name

        with open(MESSAGES_FILE, 'w') as f: # Currently writes all to one file, could be dynamic per table
            json.dump(messages, f, indent=4)
        logger.debug(f"Exported {len(messages)} messages from {table_name} to {MESSAGES_FILE}")
    except IOError as e:
        logger.error(f"Failed to write messages file {MESSAGES_FILE}: {e}")
    except Exception as e:
        logger.error(f"Error exporting messages from {table_name}: {e}", exc_info=True)

def export_config_to_json():
    """Exports a simplified version of config.ini to config.json for the web UI."""
    config_data = {}
    try:
        # App section
        config_data['app'] = {
            'mode': config.get('app', 'mode', fallback='standalone'),
            'messages_per_page': config.getint('app', 'messages_per_page', fallback=50),
            # Add dark_mode to config, based on default or assumed UI state for now
            'dark_mode': True # Default to dark mode in backend for now, UI will read this
        }
        # Scan services
        config_data['scan_services'] = {
            'hfgcs': config.get('scan_services', 'hfgcs', fallback='no'),
            'js8': config.get('scan_services', 'js8', fallback='no')
        }
        # SDR selection
        config_data['sdr_selection'] = {
            'selected_devices': [s.strip() for s in config.get('sdr_selection', 'selected_devices', fallback='').split(',') if s.strip()]
        }
        # Online SDRs (dynamic list)
        online_sdrs_list = {}
        if config.has_section('online_sdrs'):
            for name, url_type in config.items('online_sdrs'):
                # Format: name = url,type (e.g., SDR_Europe = http://sdr.example.com,web_sdr)
                parts = url_type.split(',', 1)
                url = parts[0].strip()
                sdr_type = parts[1].strip() if len(parts) > 1 else 'unknown'
                online_sdrs_list[name] = {'url': url, 'type': sdr_type}
        config_data['online_sdrs'] = {'list_of_sdrs': online_sdrs_list}

        # Detected SDRs (live from SDRManager)
        config_data['detected_sdr_devices'] = SDRManager.list_sdr_devices_serials()

        with open(CONFIG_JSON_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        logger.debug(f"Config exported to {CONFIG_JSON_FILE}")
    except IOError as e:
        logger.error(f"Failed to write config JSON file {CONFIG_JSON_FILE}: {e}")
    except Exception as e:
        logger.error(f"Error exporting config to JSON: {e}", exc_info=True)


# --- SDR Scanning Loop Functions ---

def sdr_scan_and_decode_thread(sdr_id, manager_instance, running_flag):
    """
    Dedicated thread for a single SDR device to scan and decode.
    `running_flag` is a threading.Event to control thread lifecycle.
    """
    logger.info(f"SDR scanning and decoding thread for device {sdr_id} started.")
    try:
        manager_instance.open_sdr()
        if not manager_instance.sdr:
            logger.error(f"Device {sdr_id}: SDR could not be opened. Exiting thread.")
            running_flag.clear() # Stop this thread if SDR can't open
            return

        scan_frequencies = {
            "hfgcs": [4724000, 6739000, 8992000, 11175000, 13200000, 15016000],
            "js8": [7078000, 14078000], # Example JS8 frequencies
        }
        
        current_freq_idx = 0
        
        while running_flag.is_set(): # Check if this specific SDR's thread is active
            try:
                # --- Polling config for service enable/disable ---
                config.read(CONFIG_FILE_PATH) # Re-read config periodically
                hfgcs_enabled_in_config = config.getboolean('scan_services', 'hfgcs', fallback=False)
                js8_enabled_in_config = config.getboolean('scan_services', 'js8', fallback=False)

                active_frequencies = []
                if hfgcs_enabled_in_config:
                    active_frequencies.extend(scan_frequencies["hfgcs"])
                if js8_enabled_in_config:
                    active_frequencies.extend(scan_frequencies["js8"])
                
                if not active_frequencies:
                    logger.debug(f"Device {sdr_id}: No scanning services enabled in config. Sleeping.")
                    time.sleep(5) # Sleep if nothing to scan
                    continue

                # Cycle through active frequencies
                target_freq = active_frequencies[current_freq_idx % len(active_frequencies)]
                manager_instance.set_frequency(target_freq)
                current_freq_idx += 1

                # Capture samples
                samples = manager_instance.capture_samples(manager_instance.sample_rate * 2) # Capture 2 seconds of samples
                if samples.size == 0:
                    logger.warn(f"Device {sdr_id}: No samples captured. Skipping decoding for this cycle.")
                    time.sleep(1) # Small pause to avoid tight loop
                    continue

                # --- Placeholder for DSP and Decoding ---
                # Dummy HFGCS Decoder
                if hfgcs_enabled_in_config and (time.time() % 30 < 2) and (target_freq in scan_frequencies["hfgcs"]): # Simulate every 30s
                    decoded_message = "Simulated HFGCS Voice Message: 'TEST TEST, OVER!'"
                    callsign = "DUMMY_C"
                    raw_content_path = save_audio_recording(samples, target_freq, "USB", sdr_id)
                    message_data = {
                        "frequency_hz": target_freq,
                        "mode": "USB",
                        "message_type": "HFGCS Voice",
                        "callsign": callsign,
                        "raw_content_path": raw_content_path,
                        "decoded_text": decoded_message,
                        "notes": f"Simulated HFGCS message from {sdr_id}."
                    }
                    data_store.insert_message(message_data)
                    logger.info(f"Simulated HFGCS message recorded on {target_freq/1e3} kHz from {sdr_id}.")

                # Dummy JS8 Decoder
                if js8_enabled_in_config and (time.time() % 40 < 2) and (target_freq in scan_frequencies["js8"]): # Simulate every 40s
                    decoded_message = "Simulated JS8 Message: 'CQ CQ CQ DE K1SPY'"
                    callsign = "K1SPY"
                    raw_content_path = save_audio_recording(samples, target_freq, "JS8", sdr_id)
                    message_data = {
                        "frequency_hz": target_freq,
                        "mode": "JS8",
                        "message_type": "S2 GhostNet",
                        "callsign": callsign,
                        "raw_content_path": raw_content_path,
                        "decoded_text": decoded_message,
                        "notes": f"Simulated JS8 GhostNet message from {sdr_id}."
                    }
                    data_store.insert_message(message_data)
                    logger.info(f"Simulated JS8 message recorded on {target_freq/1e3} kHz from {sdr_id}.")

                time.sleep(5) # Pause between frequency tunes/checks

            except Exception as e:
                logger.error(f"Error in SDR scanning thread for device {sdr_id}: {e}", exc_info=True)
                time.sleep(10) # Longer pause on error

    except Exception as e:
        logger.critical(f"Critical error in SDR thread setup for device {sdr_id}: {e}", exc_info=True)
    finally:
        manager_instance.close_sdr()
        logger.info(f"SDR scanning and decoding thread for device {sdr_id} stopped.")

def save_audio_recording(samples, frequency_hz, mode, sdr_id):
    """
    Saves a dummy audio recording (real audio saving requires scipy.io.wavfile)
    and returns its web-accessible path.
    For now, this just creates a dummy file.
    """
    filename = f"rec_{sdr_id.replace(':', '_').replace('.', '_')}_{int(frequency_hz/1000)}_{mode}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    filepath = os.path.join(RECORDINGS_DIR, filename)
    
    # Create a dummy file for now. Real implementation would save actual audio.
    try:
        with open(filepath, 'w') as f:
            f.write(f"Dummy audio content for {filename} from SDR {sdr_id}")
        logger.info(f"Dummy audio file created: {filepath}")
        # Return path relative to web root's hfgcspy_data
        return f"recordings/{filename}" # Path relative to hfgcspy_data
    except IOError as e:
        logger.error(f"Failed to save dummy audio recording {filepath}: {e}")
        return None

def create_sample_recordings():
    """
    Creates dummy audio files for the sample messages in index.html,
    so playback and waveform drawing works on initial load.
    """
    sample_recordings = [
        "sample1.mp3",
        "sample2.mp3",
        "sample3.mp3",
        "online_sample1.mp3",
        "online_sample2.mp3",
        "online_sample3.mp3"
    ]
    for filename in sample_recordings:
        filepath = os.path.join(RECORDINGS_DIR, filename)
        if not os.path.exists(filepath):
            try:
                with open(filepath, 'w') as f:
                    f.write(f"Dummy content for {filename}")
                logger.info(f"Created dummy sample recording: {filename}")
            except IOError as e:
                logger.error(f"Failed to create dummy sample recording {filepath}: {e}")


# --- Main Application Loop ---

def main_app_loop():
    """
    Main loop for HFGCSpy, managing SDR threads and periodic tasks.
    """
    global hfgcs_scan_enabled, js8_scan_enabled, selected_sdr_devices

    logger.info("HFGCSpy main application loop started.")

    # Detect available SDRs once at startup
    available_sdr_serials = SDRManager.list_sdr_devices_serials()
    logger.info(f"Detected SDRs: {available_sdr_serials}")

    # Create dummy sample recordings on startup
    create_sample_recordings()

    # Initial read of config (should be done once unless dynamically reloaded)
    config.read(CONFIG_FILE_PATH)
    hfgcs_scan_enabled = config.getboolean('scan_services', 'hfgcs', fallback=False)
    js8_scan_enabled = config.getboolean('scan_services', 'js8', fallback=False)

    sdr_selection_str = config.get('sdr_selection', 'selected_devices', fallback='')
    if sdr_selection_str == 'all':
        selected_sdr_devices = available_sdr_serials
    elif sdr_selection_str:
        selected_sdr_devices = [s.strip() for s in sdr_selection_str.split(',') if s.strip()]
    else:
        logger.warn("No SDRs selected in config.ini or 'selected_devices' is empty. Defaulting to all detected SDRs if any.")
        selected_sdr_devices = available_sdr_serials # Default to all detected if none specified

    if not selected_sdr_devices:
        logger.error("No SDR devices detected or selected. HFGCSpy cannot function.")
        update_web_status_file(available_sdr_serials, selected_sdr_devices) # Update status to reflect no SDR
        # Keep app running so web UI can fetch status, but no SDR threads will start
        # sys.exit(1) # Don't exit, keep main loop for status updates

    # Start/Manage SDR threads for selected SDRs
    # Only start if not already running for an update/restart scenario
    active_sdr_threads_this_cycle = {}
    for sdr_serial in selected_sdr_devices:
        if sdr_serial not in sdr_threads or not sdr_threads[sdr_serial][1].is_alive():
            manager = SDRManager(device_index=sdr_serial, # Use serial for better identification
                                 sample_rate=config.getint('sdr', 'sample_rate', fallback=2048000),
                                 center_freq=config.getint('sdr', 'center_freq_hz', fallback=8992000),
                                 gain=config.get('sdr', 'gain', fallback='auto'),
                                 ppm_correction=config.getint('sdr', 'ppm_correction', fallback=0))
            
            # Use a threading.Event to signal thread stop
            running_flag = threading.Event() 
            running_flag.set() # Set initially to run

            thread = threading.Thread(target=sdr_scan_and_decode_thread, args=(sdr_serial, manager, running_flag))
            thread.daemon = True
            sdr_threads[sdr_serial] = (manager, thread, running_flag)
            thread.start()
            logger.info(f"Started scanning thread for SDR: {sdr_serial}")
        active_sdr_threads_this_cycle[sdr_serial] = sdr_threads[sdr_serial]
    
    # Stop any SDR threads that are no longer selected
    for sdr_serial in list(sdr_threads.keys()): # Iterate over copy of keys
        if sdr_serial not in selected_sdr_devices:
            logger.info(f"Stopping unselected SDR thread for: {sdr_serial}")
            manager, thread, running_flag = sdr_threads[sdr_serial]
            running_flag.clear() # Signal thread to stop
            thread.join(timeout=10)
            if thread.is_alive():
                logger.warning(f"SDR thread for {sdr_serial} did not terminate gracefully.")
            manager.close_sdr() # Ensure SDR is closed
            del sdr_threads[sdr_serial] # Remove from active list

    # Re-assign sdr_threads to the currently active ones
    sdr_threads.clear()
    sdr_threads.update(active_sdr_threads_this_cycle)


    # Main loop for managing services and exporting data
    while True:
        try:
            # Periodically re-read config for updated service enablement
            # This is how the web UI "controls" the backend
            config.read(CONFIG_FILE_PATH)
            hfgcs_scan_enabled = config.getboolean('scan_services', 'hfgcs', fallback=False)
            js8_scan_enabled = config.getboolean('scan_services', 'js8', fallback=False)

            # Update status file for web UI
            update_web_status_file(available_sdr_serials, selected_sdr_devices)
            
            # Export messages for web UI (only for hfcgs_messages table for now)
            export_recent_messages_to_json(table_name='hfgcs_messages')
            
            # Export full config to JSON for web UI to read for options
            export_config_to_json()

        except configparser.Error as e:
            logger.error(f"Error re-reading config.ini in main loop: {e}. Check config file syntax.")
        except Exception as e:
            logger.error(f"Error in main app loop: {e}", exc_info=True)
        
        time.sleep(5) # Main loop runs every 5 seconds


# --- Command Line Interface (CLI) ---

def main():
    parser = argparse.ArgumentParser(description="HFGCSpy SDR Scanner and Parser")
    parser.add_argument('--run', action='store_true', help="Run HFGCSpy as a background service.")
    
    args = parser.parse_args()

    if args.run:
        logger.info("HFGCSpy starting as a service. Managing SDR operations.")
        try:
            main_app_loop() # Start the main application loop
        except KeyboardInterrupt:
            logger.info("HFGCSpy main service interrupted by user (Ctrl+C). Stopping all SDR threads.")
            for sdr_id, (manager, thread, running_flag) in sdr_threads.items():
                running_flag.clear() # Signal thread to stop
                thread.join(timeout=10)
                if thread.is_alive():
                    logger.warning(f"SDR thread for {sdr_id} did not terminate gracefully.")
                manager.close_sdr() # Ensure SDR is closed
            logger.info("HFGCSpy main service stopped.")
        except Exception as e:
            logger.critical(f"Unhandled critical error in HFGCSpy main process: {e}", exc_info=True)
            sys.exit(1)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

