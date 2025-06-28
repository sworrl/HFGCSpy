# HFGCSpy/core/data_store.py
# Version: 0.0.1

import sqlite3
import os
import logging

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None

    def initialize_db(self):
        try:
            # Ensure database directory exists
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS hfcgs_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    frequency_hz REAL NOT NULL,
                    mode TEXT,         -- e.g., 'USB', 'JS8', 'AM', 'NFM'
                    message_type TEXT, -- e.g., 'EAM', 'Skyking', 'Voice', 'ALE', 'JS8Call'
                    callsign TEXT,
                    raw_content_path TEXT,  -- Path to raw IQ/audio file if saved
                    decoded_text TEXT, -- Parsed human-readable message
                    notes TEXT
                )
            ''')
            self.conn.commit()
            logger.info(f"SQLite database initialized at {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}", exc_info=True)
            self.conn = None
            self.cursor = None

    def close_db(self):
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed.")
        self.conn = None
        self.cursor = None

    def insert_message(self, message_data):
        if not self.conn:
            logger.error("Database not initialized. Cannot insert message.")
            return

        try:
            # Define columns and get data safely, handling potential missing keys
            columns = [
                'frequency_hz', 'mode', 'message_type', 'callsign',
                'raw_content_path', 'decoded_text', 'notes'
            ]
            # Ensure values are prepared for SQL insert, None for missing keys
            values = [message_data.get(col) for col in columns]
            
            placeholders = ', '.join(['?'] * len(columns))
            column_names = ', '.join(columns)

            self.cursor.execute(f'''
                INSERT INTO hfcgs_messages ({column_names})
                VALUES ({placeholders})
            ''', values)
            self.conn.commit()
            logger.info(f"Inserted message: Type={message_data.get('message_type')}, Freq={message_data.get('frequency_hz')}")
        except sqlite3.Error as e:
            logger.error(f"Error inserting message: {e}", exc_info=True)

    def get_recent_messages(self, limit=10):
        if not self.conn:
            logger.error("Database not initialized. Cannot retrieve messages.")
            return []
        try:
            self.cursor.execute(f"SELECT * FROM hfcgs_messages ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = self.cursor.fetchall()
            # Get column names to return as dicts
            column_names = [description[0] for description in self.cursor.description]
            return [dict(zip(column_names, row)) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Error retrieving recent messages: {e}", exc_info=True)
            return []

    # Add more methods for querying, filtering, updating data as needed
