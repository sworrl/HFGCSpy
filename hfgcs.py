# HFGCSpy/hfgcs.py
# Main entry point for HFGCSpy application.
# Version: 2.0.0 # Updated version for Dockerization

__version__ = "2.0.0"

import os
import time
import logging
import sys
import json
import configparser
import threading
from datetime import datetime
import requests # For making requests to the internal Flask API (self-communication)

# Import core modules
# Assuming /app is the working directory inside the Docker container
sys.path.append(os.path.join(os.path.dirname(__file__), 'core'))

from sdr_manager import SDRManager
from data_store import DataStore
# No direct import of api_server.app here, as hfgcs.py will manage its lifecycle or interact via HTTP

# --- Configuration Loading and Global Paths ---
config = configparser.ConfigParser()
# config.ini is mounted at /app/config.ini inside the Docker container
CONFIG_FILE_PATH = "/app/config.ini" 

try:
    config.read(CONFIG_FILE_PATH)
    APP_MODE = config.get('app', 'mode', fallback='standalone')
    DB_PATH = config.get('app', 'database_path', fallback='/app/data/hfgcspy.db') # Path inside container
    LOG_FILE = config.get('logging', 'log_file', fallback='/app/logs/hfgcspy.log') # Path inside container
    LOG_LEVEL = config.get('logging', 'log_level', fallback='INFO').upper()
    INTERNAL_PORT = config.get('app', 'internal_port', fallback='8002') # Internal port for Flask API

    # Paths for files exposed via web server (Apache2) - these are paths *inside the container*
    # that map to the Docker volume, which Apache then serves from the host.
    STATUS_FILE = config.get('app_paths', 'status_file', fallback='/app/data/hfgcspy_data/status.json')
    MESSAGES_FILE = config.get('app_paths', 'messages_file', fallback='/app/data/hfgcspy_data/messages.json')
    RECORDINGS_DIR = config.get('app_paths', 'recordings_dir', fallback='/app/data/recordings')
    CONFIG_JSON_FILE = config.get('app_paths', 'config_json_file', fallback='/app/data/hfgcspy_data/config.json')

except configparser.Error as e:
    print(f"ERROR: Could not read config.ini: {e}. Using default paths/settings.")
    APP_MODE = 'standalone'
    DB_PATH = '/app/data/hfgcspy.db'
    LOG_FILE = '/app/logs/hfgcspy.log'
    LOG_LEVEL = 'INFO'
    STATUS_FILE = '/app/data/hfgcspy_data/status.json'
    MESSAGES_FILE = '/app/data/hfgcspy_data/messages.json'
    RECORDINGS_DIR = '/app/data/recordings'
    CONFIG_JSON_FILE = '/app/data/hfgcspy_data/config.json'

# Create necessary directories inside the Docker container
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True) 
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_JSON_FILE), exist_ok=True)

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
adsb_scan_enabled = False # New service for ADS-B

# SDR devices selected from config (list of serials or indices)
selected_sdr_devices = []

# --- Functions for Status and Config Export to JSON ---
def update_web_status_file(detected_sdr_serials, selected_sdr_serials):
    """Writes the current service and SDR status to status.json for the web UI."""
    status_data = {
        "hfgcs_service": "Running" if hfgcs_scan_enabled else "Stopped",
        "js8_service": "Running" if js8_scan_enabled else "Stopped",
        "adsb_service": "Running" if adsb_scan_enabled else "Stopped", # New ADS-B status
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
        
        for msg in messages:
            if 'timestamp' in msg and isinstance(msg['timestamp'], datetime):
                msg['timestamp'] = msg['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            elif 'timestamp' not in msg: # Ensure timestamp is always present
                msg['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            msg['table_name'] = table_name # Add table_name for UI delete action to know which table to target

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
        config_data['app'] = {
            'mode': config.get('app', 'mode', fallback='standalone'),
            'messages_per_page': config.getint('app', 'messages_per_page', fallback=50),
            'internal_port': config.get('app', 'internal_port', fallback='8002')
        }
        config_data['scan_services'] = {
            'hfgcs': config.get('scan_services', 'hfgcs', fallback='no'),
            'js8': config.get('scan_services', 'js8', fallback='no'),
            'adsb': config.get('scan_services', 'adsb', fallback='no') # New ADS-B config
        }
        config_data['sdr_selection'] = {
            'selected_devices': [s.strip() for s in config.get('sdr_selection', 'selected_devices', fallback='').split(',') if s.strip()]
        }
        online_sdrs_list = {}
        if config.has_section('online_sdrs'):
            for name, url_type in config.items('online_sdrs'):
                parts = url_type.split(',', 1)
                url = parts[0].strip()
                sdr_type = parts[1].strip() if len(parts) > 1 else 'unknown'
                online_sdrs_list[name] = {'url': url, 'type': sdr_type}
        config_data['online_sdrs'] = {'list_of_sdrs': online_sdrs_list}

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
            "adsb": [1090000000], # ADS-B frequency (1090 MHz)
        }
        
        current_freq_idx = 0
        
        while running_flag.is_set(): # Check if this specific SDR's thread is active
            try:
                # --- Polling config for service enable/disable ---
                config.read(CONFIG_FILE_PATH) # Re-read config periodically
                hfgcs_enabled_in_config = config.getboolean('scan_services', 'hfgcs', fallback=False)
                js8_enabled_in_config = config.getboolean('scan_services', 'js8', fallback=False)
                adsb_enabled_in_config = config.getboolean('scan_services', 'adsb', fallback=False) # New ADS-B enable flag

                active_frequencies = []
                if hfgcs_enabled_in_config:
                    active_frequencies.extend(scan_frequencies["hfgcs"])
                if js8_enabled_in_config:
                    active_frequencies.extend(scan_frequencies["js8"])
                if adsb_enabled_in_config: # Add ADS-B frequencies if enabled
                    active_frequencies.extend(scan_frequencies["adsb"])
                
                if not active_frequencies:
                    logger.debug(f"Device {sdr_id}: No scanning services enabled. Sleeping.")
                    time.sleep(5) # Sleep if nothing to scan
                    continue

                # Cycle through active frequencies
                target_freq = active_frequencies[current_freq_idx % len(active_frequencies)]
                manager_instance.set_frequency(target_freq)
                current_freq_idx += 1

                # Capture samples
                # Adjust sample rate for ADS-B if needed, as it's a very wideband signal
                capture_samples_duration = 2 # seconds
                if target_freq == 1090000000: # For ADS-B
                    # ADS-B typically needs higher sample rates, but RTL-SDR limits us.
                    # For a real ADS-B decoder, you'd use a dedicated tool like dump1090.
                    # Here, we just simulate capture.
                    capture_samples_duration = 1 # Shorter capture for high freq
                    samples = manager_instance.capture_samples(manager_instance.sample_rate * capture_samples_duration)
                else:
                    samples = manager_instance.capture_samples(manager_instance.sample_rate * capture_samples_duration)
                
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

                # Dummy ADS-B Decoder (very basic simulation)
                if adsb_enabled_in_config and (time.time() % 20 < 2) and (target_freq == 1090000000): # Simulate every 20s
                    decoded_message = f"Simulated ADS-B: Aircraft ABCDEF, Lat: 36.1, Lon: -86.7, Alt: 10000ft"
                    callsign = "N/A" # ADS-B typically uses ICAO hex codes, not callsigns
                    raw_content_path = save_audio_recording(samples, target_freq, "ADS-B", sdr_id) # Even though it's not audio
                    message_data = {
                        "frequency_hz": target_freq,
                        "mode": "ADS-B",
                        "message_type": "Commercial Aircraft",
                        "callsign": callsign,
                        "raw_content_path": raw_content_path,
                        "decoded_text": decoded_message,
                        "notes": f"Simulated ADS-B message from {sdr_id}."
                    }
                    data_store.insert_message(message_data)
                    logger.info(f"Simulated ADS-B message recorded on {target_freq/1e6} MHz from {sdr_id}.")


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
    # Sanitize sdr_id for filename
    sanitized_sdr_id = re.sub(r'[^a-zA-Z0-9_.-]', '_', str(sdr_id))
    filename = f"rec_{sanitized_sdr_id}_{int(frequency_hz/1000)}_{mode}_{datetime.now().strftime('%Y%m%d%H%M%S')}.mp3"
    filepath = os.path.join(RECORDINGS_DIR, filename)
    
    # Create a dummy file for now. Real implementation would save actual audio.
    try:
        with open(filepath, 'w') as f:
            f.write(f"Dummy audio content for {filename} from SDR {sdr_id}")
        logger.info(f"Dummy audio file created: {filepath}")
        # Return path relative to the hfgcspy_data alias in Apache
        # This path is what the web UI will use
        return f"recordings/{filename}" 
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
    global hfgcs_scan_enabled, js8_scan_enabled, adsb_scan_enabled # Add adsb_scan_enabled
    global selected_sdr_devices

    logger.info("HFGCSpy main application loop started.")

    # Create dummy sample recordings on startup
    create_sample_recordings()

    # Main loop for managing services and exporting data
    while True:
        try:
            # Periodically re-read config for updated service enablement and SDR selection
            config.read(CONFIG_FILE_PATH)
            
            # Update service enable flags
            hfgcs_scan_enabled = config.getboolean('scan_services', 'hfgcs', fallback=False)
            js8_scan_enabled = config.getboolean('scan_services', 'js8', fallback=False)
            adsb_scan_enabled = config.getboolean('scan_services', 'adsb', fallback=False) # Read ADS-B flag

            # Update selected SDR devices
            available_sdr_serials = SDRManager.list_sdr_devices_serials()
            sdr_selection_str = config.get('sdr_selection', 'selected_devices', fallback='')
            
            if sdr_selection_str == 'all':
                newly_selected_sdr_devices = available_sdr_serials
            elif sdr_selection_str:
                newly_selected_sdr_devices = [s.strip() for s in sdr_selection_str.split(',') if s.strip() in available_sdr_serials]
            else:
                logger.warn("No SDRs selected in config.ini. Defaulting to all detected SDRs if any.")
                newly_selected_sdr_devices = available_sdr_serials

            # Stop SDR threads that are no longer selected or are no longer detected
            for sdr_serial in list(sdr_threads.keys()):
                if sdr_serial not in newly_selected_sdr_devices or sdr_serial not in available_sdr_serials:
                    logger.info(f"Stopping unselected or disconnected SDR thread for: {sdr_serial}")
                    manager, thread, running_flag = sdr_threads[sdr_serial]
                    running_flag.clear() # Signal thread to stop
                    thread.join(timeout=10)
                    if thread.is_alive():
                        logger.warning(f"SDR thread for {sdr_serial} did not terminate gracefully.")
                    manager.close_sdr() # Ensure SDR is closed
                    del sdr_threads[sdr_serial]
            
            # Start new SDR threads for newly selected and detected SDRs
            for sdr_serial in newly_selected_sdr_devices:
                if sdr_serial not in sdr_threads: # Only start if not already running
                    manager = SDRManager(device_index=sdr_serial, # Use serial for better identification
                                         sample_rate=config.getint('sdr', 'sample_rate', fallback=2048000),
                                         center_freq=config.getint('sdr', 'center_freq_hz', fallback=8992000),
                                         gain=config.get('sdr', 'gain', fallback='auto'),
                                         ppm_correction=config.getint('sdr', 'ppm_correction', fallback=0))
                    
                    running_flag = threading.Event() 
                    running_flag.set() 

                    thread = threading.Thread(target=sdr_scan_and_decode_thread, args=(sdr_serial, manager, running_flag))
                    thread.daemon = True
                    sdr_threads[sdr_serial] = (manager, thread, running_flag)
                    thread.start()
                    logger.info(f"Started scanning thread for SDR: {sdr_serial}")
            
            selected_sdr_devices = newly_selected_sdr_devices # Update global list

            # Update status file for web UI
            update_web_status_file(available_sdr_serials, selected_sdr_devices)
            
            # Export messages for web UI (only for hfcgs_messages table for now)
            export_recent_messages_to_json(table_name='hfcgs_messages')
            
            # Export full config to JSON for web UI to read for options
            export_config_to_json()

        except configparser.Error as e:
            logger.error(f"Error re-reading config.ini in main loop: {e}. Check config file syntax.")
        except Exception as e:
            logger.error(f"Error in main app loop: {e}", exc_info=True)
        
        time.sleep(5) # Main loop runs every 5 seconds


# --- Command Line Interface (CLI) ---

def main():
    parser = argparse.ArgumentParser(description=f"HFGCSpy SDR Scanner and Parser (Version: {__version__})")
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
