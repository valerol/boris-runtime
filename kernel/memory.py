import sqlite3
import json
import time

class Memory:

    def __init__(self, path="boris.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
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

    def read_recent(self, limit=10):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT ts, state, data FROM events ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        rows = cur.fetchall()
        return [
            {"ts": ts, "state": state, "data": json.loads(data)}
            for ts, state, data in rows
        ]

    def write(self, state, data):
        cur = self.conn.cursor()

        cur.execute(
            "INSERT INTO events (ts, state, data) VALUES (?, ?, ?)",
            (time.time(), state, json.dumps(data))
        )

        self.conn.commit()
