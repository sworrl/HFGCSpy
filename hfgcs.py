import os
import json
import time
import threading
import requests
import speech_recognition as sr
from pydub import AudioSegment
from io import BytesIO
import logging
import sqlite3
from datetime import datetime

# Configure logging for debugging and status updates
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Directory to store recorded audio
DATA_DIR = 'hfgcspy_data'
os.makedirs(DATA_DIR, exist_ok=True)

# SQLite database setup
DB_FILE = os.path.join(DATA_DIR, 'hfgcspy.db')

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create messages table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_name TEXT,
            source TEXT,
            message_type TEXT,
            frequency_hz REAL,
            mode TEXT,
            callsign TEXT,
            decoded_text TEXT,
            notes TEXT,
            timestamp TEXT,
            raw_content_path TEXT
        )
    ''')
    # Create status table (for simplicity, using a single row for current status)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS status (
            id INTEGER PRIMARY KEY,
            hfgcs_service TEXT,
            js8_service TEXT,
            sdr_devices TEXT,
            online_sdrs TEXT,
            current_frequency REAL,
            signal_power REAL
        )
    ''')
    # Insert initial status if not exists
    cursor.execute('INSERT OR IGNORE INTO status (id) VALUES (1)')
    conn.commit()
    conn.close()

init_db()

# Preconfigured WebSDRs with their streaming URLs
WEBSDRS = {
    'Twente': {'url': 'http://websdr.ewi.utwente.nl:8901/~~stream', 'type': 'WebSDR'},
    'K3FEF': {'url': 'http://k3fef.com:8901/~~stream', 'type': 'WebSDR'},
    'W7RNA': {'url': 'http://w7rna.ddns.net:8073/~~stream', 'type': 'KiwiSDR'}
}

# Frequencies to monitor (in kHz)
HFGCS_FREQS = [4724, 6739, 8992, 11175, 13200, 15016]  # HFGCS voice frequencies
JS8CALL_FREQS = [7078, 14078]  # JS8Call digital frequencies

# Function to stream audio from a WebSDR
def stream_audio(websdr_name, freq, mode):
    websdr = WEBSDRS[websdr_name]
    url = f"{websdr['url']}?freq={freq}&mode={mode}"
    try:
        with requests.get(url, stream=True, timeout=10) as response:
            if response.status_code == 200:
                audio_data = BytesIO()
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        audio_data.write(chunk)
                        # Process audio in chunks (e.g., every 10 seconds worth of data)
                        if audio_data.tell() > 10 * 1024 * 1024:  # Roughly 10 MB
                            process_audio(websdr_name, freq, mode, audio_data)
                            audio_data = BytesIO()
            else:
                logging.error(f"Failed to stream from {websdr_name}: {response.status_code}")
    except Exception as e:
        logging.error(f"Error streaming from {websdr_name}: {e}")

# Function to process audio chunks
def process_audio(websdr_name, freq, mode, audio_data):
    try:
        audio_data.seek(0)
        audio = AudioSegment.from_file(audio_data, format='wav')
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        audio_file = os.path.join(DATA_DIR, f"{websdr_name}_{freq}_{mode}_{timestamp}.wav")
        audio.export(audio_file, format='wav')
        logging.info(f"Recorded audio: {audio_file}")

        # Process based on mode
        if mode == 'usb':  # HFGCS voice
            transcription = transcribe_audio(audio_file)
            save_message(websdr_name, freq, mode, 'HFGCS Voice', transcription, audio_file)
        elif mode == 'js8':  # JS8Call digital
            decoded_text = decode_js8call(audio_file)
            save_message(websdr_name, freq, mode, 'S2 GhostNet', decoded_text, audio_file)
    except Exception as e:
        logging.error(f"Error processing audio: {e}")

# Function to transcribe audio using PocketSphinx (offline speech recognition)
def transcribe_audio(audio_file):
    recognizer = sr.Recognizer()
    with sr.AudioFile(audio_file) as source:
        audio = recognizer.record(source)
    try:
        return recognizer.recognize_sphinx(audio)
    except sr.UnknownValueError:
        return "Could not understand audio"
    except sr.RequestError as e:
        return f"Error with speech recognition: {e}"

# Placeholder function to decode JS8Call messages
def decode_js8call(audio_file):
    # TODO: Implement JS8Call decoding logic or integrate with an external library/tool
    # This requires demodulating the audio and decoding the JS8Call protocol
    return "Decoded JS8Call message (placeholder)"

# Function to save message data to SQLite
def save_message(source, freq, mode, message_type, text, audio_file):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (table_name, source, message_type, frequency_hz, mode, callsign, decoded_text, notes, timestamp, raw_content_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        'hfgcs_messages' if mode == 'usb' else 'online_sdr_messages',
        source,
        message_type,
        freq * 1000,  # Convert kHz to Hz
        mode,
        'UNKNOWN',
        text,
        f"Processed from {source}",
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        os.path.relpath(audio_file, DATA_DIR)
    ))
    conn.commit()
    conn.close()
    logging.info(f"Saved message from {source} to database")

# Main function to start monitoring all WebSDRs and frequencies
def main():
    threads = []
    for websdr_name in WEBSDRS:
        # Start threads for HFGCS frequencies (voice)
        for freq in HFGCS_FREQS:
            thread = threading.Thread(target=stream_audio, args=(websdr_name, freq, 'usb'))
            threads.append(thread)
            thread.start()
        # Start threads for JS8Call frequencies (digital)
        for freq in JS8CALL_FREQS:
            thread = threading.Thread(target=stream_audio, args=(websdr_name, freq, 'js8'))
            threads.append(thread)
            thread.start()
    # Wait for all threads to complete (runs indefinitely unless interrupted)
    for thread in threads:
        thread.join()

if __name__ == '__main__':
    logging.info("Starting hfgcs.py - HFGCS and S2 message capture system")
    main()