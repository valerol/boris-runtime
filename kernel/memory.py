import sqlite3
import json
import time

class Memory:

    def __init__(self):
        self.conn = sqlite3.connect("boris.db")
        self._init()

    def _init(self):
        cur = self.conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            ts FLOAT,
            state TEXT,
            data TEXT
        )
        """)

        self.conn.commit()

    def write(self, state, data):
        cur = self.conn.cursor()

        cur.execute(
            "INSERT INTO events (ts, state, data) VALUES (?, ?, ?)",
            (time.time(), state, json.dumps(data))
        )

        self.conn.commit()
