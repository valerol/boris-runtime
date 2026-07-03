import sqlite3
import json
import time

class Memory:

    def __init__(self, path="boris.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.question_memory = {
            "asked_questions": [],
            "clarification_count": {},
            "last_inputs": []
        }
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

    def remember_input(self, session_id, user_input):
        self.question_memory["last_inputs"].append({
            "session_id": session_id,
            "input": user_input
        })

    def remember_clarification(self, session_id, topic, question):
        key = self._clarification_key(session_id, topic)
        self.question_memory["clarification_count"][key] = (
            self.question_memory["clarification_count"].get(key, 0) + 1
        )
        self.question_memory["asked_questions"].append({
            "session_id": session_id,
            "topic": topic,
            "question": question
        })

    def clarification_count(self, session_id, topic):
        key = self._clarification_key(session_id, topic)
        return self.question_memory["clarification_count"].get(key, 0)

    def has_asked_clarification(self, session_id, topic, question):
        return any(
            item["session_id"] == session_id
            and item["topic"] == topic
            and item["question"] == question
            for item in self.question_memory["asked_questions"]
        )

    def _clarification_key(self, session_id, topic):
        return f"{session_id}:{topic}"
