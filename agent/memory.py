"""Per-chat memory backed by SQLite.

Two kinds of memory:
- conversation history: the last N turns, so the model has short-term context
- notes: facts the user explicitly asked the assistant to remember

It also keeps a daily token tally per chat, used for the optional budget.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Note:
    id: int
    text: str
    created_at: float


class Memory:
    def __init__(self, path: str | Path = ":memory:", history_limit: int = 20) -> None:
        self.history_limit = history_limit
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id);
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS token_usage (
                chat_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chat_id, day)
            );
            """
        )

    # Conversation history -------------------------------------------------

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        self._db.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, time.time()),
        )
        self._db.commit()

    def history(self, chat_id: int) -> list[dict[str, str]]:
        """Most recent turns, oldest first, always starting with a user turn."""
        rows = self._db.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, self.history_limit),
        ).fetchall()
        turns = [{"role": role, "content": content} for role, content in reversed(rows)]
        while turns and turns[0]["role"] != "user":
            turns.pop(0)
        return turns

    def clear_history(self, chat_id: int) -> None:
        self._db.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        self._db.commit()

    # Notes ----------------------------------------------------------------

    def save_note(self, chat_id: int, text: str) -> Note:
        now = time.time()
        cursor = self._db.execute(
            "INSERT INTO notes (chat_id, text, created_at) VALUES (?, ?, ?)",
            (chat_id, text.strip(), now),
        )
        self._db.commit()
        return Note(id=int(cursor.lastrowid or 0), text=text.strip(), created_at=now)

    def search_notes(self, chat_id: int, query: str = "", limit: int = 10) -> list[Note]:
        words = [w for w in query.lower().split() if len(w) > 2]
        rows = self._db.execute(
            "SELECT id, text, created_at FROM notes WHERE chat_id = ? ORDER BY id DESC",
            (chat_id,),
        ).fetchall()
        notes = [Note(id=r[0], text=r[1], created_at=r[2]) for r in rows]
        if words:
            notes = [n for n in notes if any(w in n.text.lower() for w in words)]
        return notes[:limit]

    def delete_note(self, chat_id: int, note_id: int) -> bool:
        cursor = self._db.execute(
            "DELETE FROM notes WHERE chat_id = ? AND id = ?", (chat_id, note_id)
        )
        self._db.commit()
        return cursor.rowcount > 0

    # Token usage ----------------------------------------------------------

    def add_usage(self, chat_id: int, day: str, input_tokens: int, output_tokens: int) -> None:
        """Add tokens to a chat's tally for one day (an ISO date string, e.g. 2026-11-11)."""
        self._db.execute(
            """
            INSERT INTO token_usage (chat_id, day, input_tokens, output_tokens) VALUES (?, ?, ?, ?)
            ON CONFLICT (chat_id, day) DO UPDATE SET
                input_tokens = input_tokens + excluded.input_tokens,
                output_tokens = output_tokens + excluded.output_tokens
            """,
            (chat_id, day, input_tokens, output_tokens),
        )
        self._db.commit()

    def tokens_used(self, chat_id: int, day: str) -> int:
        """Input plus output tokens a chat has used on the given day."""
        row = self._db.execute(
            "SELECT input_tokens + output_tokens FROM token_usage WHERE chat_id = ? AND day = ?",
            (chat_id, day),
        ).fetchone()
        return int(row[0]) if row else 0
