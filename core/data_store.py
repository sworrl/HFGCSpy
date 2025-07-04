# HFGCSpy/core/data_store.py
# Version: 2.0.1 # Version bump for circular import fix

import sqlite3
import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self, db_path='hfgcspy.db'):
        self.db_path = db_path
        self.conn = None

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row # Allows accessing columns by name
            logger.debug(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Database connection error: {e}")
            self.conn = None

    def _close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.debug("Database connection closed.")

    def initialize_db(self):
        try:
            self._connect()
            if not self.conn:
                return False
            cursor = self.conn.cursor()
            # Table for HFGCS messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hfgcs_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    frequency_hz INTEGER,
                    mode TEXT,
                    message_type TEXT,
                    callsign TEXT,
                    decoded_text TEXT,
                    raw_content_path TEXT, -- Path to raw audio/data file
                    notes TEXT,
                    source TEXT DEFAULT 'local_sdr' -- 'local_sdr' or name of online SDR
                )
            """)
            # Table for JS8 messages
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS js8_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    frequency_hz INTEGER,
                    mode TEXT,
                    message_type TEXT,
                    callsign TEXT,
                    decoded_text TEXT,
                    raw_content_path TEXT,
                    notes TEXT,
                    source TEXT DEFAULT 'local_sdr'
                )
            """)
            # Table for ADS-B messages (new)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS adsb_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                    frequency_hz INTEGER,
                    icao_hex TEXT,
                    callsign TEXT,
                    latitude REAL,
                    longitude REAL,
                    altitude INTEGER,
                    velocity INTEGER,
                    heading INTEGER,
                    raw_content_path TEXT,
                    notes TEXT,
                    source TEXT DEFAULT 'local_sdr'
                )
            """)
            self.conn.commit()
            logger.info("Database initialized successfully (tables created if not exist).")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
            return False
        finally:
            self._close()

    def insert_message(self, message_data, table_name='hfgcs_messages'):
        if table_name not in ['hfgcs_messages', 'js8_messages', 'adsb_messages']:
            logger.error(f"Invalid table name: {table_name}. Message not inserted.")
            return False

        self._connect()
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()
            if table_name == 'hfgcs_messages':
                cursor.execute("""
                    INSERT INTO hfgcs_messages (timestamp, frequency_hz, mode, message_type, callsign, decoded_text, raw_content_path, notes, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    message_data.get('frequency_hz'),
                    message_data.get('mode'),
                    message_data.get('message_type'),
                    message_data.get('callsign'),
                    message_data.get('decoded_text'),
                    message_data.get('raw_content_path'),
                    message_data.get('notes'),
                    message_data.get('source', 'local_sdr')
                ))
            elif table_name == 'js8_messages':
                cursor.execute("""
                    INSERT INTO js8_messages (timestamp, frequency_hz, mode, message_type, callsign, decoded_text, raw_content_path, notes, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    message_data.get('frequency_hz'),
                    message_data.get('mode'),
                    message_data.get('message_type'),
                    message_data.get('callsign'),
                    message_data.get('decoded_text'),
                    message_data.get('raw_content_path'),
                    message_data.get('notes'),
                    message_data.get('source', 'local_sdr')
                ))
            elif table_name == 'adsb_messages':
                cursor.execute("""
                    INSERT INTO adsb_messages (timestamp, frequency_hz, icao_hex, callsign, latitude, longitude, altitude, velocity, heading, raw_content_path, notes, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    message_data.get('frequency_hz'),
                    message_data.get('icao_hex'),
                    message_data.get('callsign'),
                    message_data.get('latitude'),
                    message_data.get('longitude'),
                    message_data.get('altitude'),
                    message_data.get('velocity'),
                    message_data.get('heading'),
                    message_data.get('raw_content_path'),
                    message_data.get('notes'),
                    message_data.get('source', 'local_sdr')
                ))
            self.conn.commit()
            logger.info(f"Message inserted into {table_name}.")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error inserting message into {table_name}: {e}")
            return False
        finally:
            self._close()

    def get_recent_messages(self, table_name='hfgcs_messages', limit=50, sdr_id=None):
        if table_name not in ['hfgcs_messages', 'js8_messages', 'adsb_messages']:
            logger.error(f"Invalid table name: {table_name}. Cannot retrieve messages.")
            return []

        self._connect()
        if not self.conn:
            return []

        messages = []
        try:
            cursor = self.conn.cursor()
            query = f"SELECT * FROM {table_name}"
            params = []
            if sdr_id:
                query += " WHERE source = ?"
                params.append(sdr_id)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                messages.append(dict(row)) # Convert Row object to dictionary
        except sqlite3.Error as e:
            logger.error(f"Error retrieving messages from {table_name}: {e}")
        finally:
            self._close()
        return messages

    def delete_message(self, table_name, message_id):
        if table_name not in ['hfgcs_messages', 'js8_messages', 'adsb_messages']:
            logger.error(f"Invalid table name: {table_name}. Message not deleted.")
            return False

        self._connect()
        if not self.conn:
            return False

        try:
            cursor = self.conn.cursor()
            cursor.execute(f"DELETE FROM {table_name} WHERE id = ?", (message_id,))
            self.conn.commit()
            return cursor.rowcount > 0 # True if a row was deleted
        except sqlite3.Error as e:
            logger.error(f"Error deleting message ID {message_id} from {table_name}: {e}")
            return False
        finally:
            self._close()
