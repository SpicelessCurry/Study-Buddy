"""SQLite Database manager for Study Buddy RAG application.

Provides thread-safe access to ~/.studybuddy/studybuddy.db for managing
conversations, chat messages, and generated study files.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

# Base path for Study Buddy data
STUDYBUDDY_DIR = Path.home() / ".studybuddy"
DB_FILE_PATH = STUDYBUDDY_DIR / "studybuddy.db"


class Database:
    """Thread-safe SQLite database manager for Study Buddy."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize Database manager with database file path.

        Args:
            db_path: Optional custom path to SQLite database. Defaults to
                ~/.studybuddy/studybuddy.db.
        """
        self.db_path = Path(db_path) if db_path else DB_FILE_PATH
        self._lock = threading.RLock()
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self) -> None:
        """Ensure parent directory for database exists."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create directory {self.db_path.parent}: {e}")
            raise

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite database connections.

        Ensures connections have foreign keys enabled, WAL mode configured,
        row factory enabled, and commits on exit or rollbacks on error.
        Thread-safe via internal RLock.
        """
        with self._lock:
            conn = sqlite3.connect(
                str(self.db_path),
                timeout=30.0,
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            try:
                conn.execute("PRAGMA foreign_keys = ON;")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database transaction error: {e}")
                raise
            finally:
                conn.close()

    def _init_db(self) -> None:
        """Create database tables and indexes if they do not exist."""
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    file_names TEXT NOT NULL DEFAULT '[]',
                    summary TEXT DEFAULT ''
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    message_type TEXT NOT NULL DEFAULT 'chat' 
                        CHECK(message_type IN ('chat', 'study_material', 'question_paper')),
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generated_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL 
                        CHECK(file_type IN ('study_material', 'question_paper')),
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
                """
            )

            # Indexes for faster queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_generated_conv_id ON generated_files(conversation_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at);"
            )

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC timestamp in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()

    def create_conversation(
        self, title: str, file_names: list[str] | str | None = None
    ) -> str:
        """Create a new conversation record.

        Args:
            title: Title of conversation.
            file_names: List of original file names or serialized JSON string.

        Returns:
            The newly created conversation UUID.
        """
        conv_id = str(uuid.uuid4())
        now = self._now_iso()

        if file_names is None:
            files_json = "[]"
        elif isinstance(file_names, list):
            files_json = json.dumps(file_names, ensure_ascii=False)
        elif isinstance(file_names, str):
            # Verify if already valid JSON or single filename
            try:
                parsed = json.loads(file_names)
                if isinstance(parsed, list):
                    files_json = file_names
                else:
                    files_json = json.dumps([file_names], ensure_ascii=False)
            except json.JSONDecodeError:
                files_json = json.dumps([file_names], ensure_ascii=False)
        else:
            files_json = json.dumps(list(file_names), ensure_ascii=False)

        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at, file_names, summary)
                VALUES (?, ?, ?, ?, ?, '')
                """,
                (conv_id, title.strip() or "Untitled Conversation", now, now, files_json),
            )

        logger.info(f"Created conversation {conv_id} with title: '{title}'")
        return conv_id

    def get_all_conversations(self) -> list[dict[str, Any]]:
        """Get all conversations ordered by recent activity.

        Returns:
            List of dictionaries with keys:
            id, title, created_at, updated_at, file_names, summary, message_count.
        """
        query = """
            SELECT 
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                c.file_names,
                c.summary,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            GROUP BY c.id
            ORDER BY c.updated_at DESC;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query)
            rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            data = dict(r)
            try:
                data["file_names"] = json.loads(data["file_names"])
            except (json.JSONDecodeError, TypeError):
                data["file_names"] = []
            results.append(data)

        return results

    def get_conversation(self, conv_id: str) -> dict[str, Any] | None:
        """Get conversation details including message count and messages.

        Args:
            conv_id: Conversation UUID.

        Returns:
            Dictionary with conversation details and associated messages,
            or None if not found.
        """
        query = """
            SELECT 
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                c.file_names,
                c.summary,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.id = ?
            GROUP BY c.id;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (conv_id,))
            row = cursor.fetchone()

        if row is None:
            return None

        conv_dict = dict(row)
        try:
            conv_dict["file_names"] = json.loads(conv_dict["file_names"])
        except (json.JSONDecodeError, TypeError):
            conv_dict["file_names"] = []

        conv_dict["messages"] = self.get_messages(conv_id)
        conv_dict["generated_files"] = self.get_generated_files(conv_id)
        return conv_dict

    def update_conversation_title(self, conv_id: str, title: str) -> bool:
        """Update conversation title.

        Args:
            conv_id: Conversation UUID.
            title: New title string.

        Returns:
            True if conversation was updated, False otherwise.
        """
        now = self._now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (title.strip(), now, conv_id),
            )
            return cursor.rowcount > 0

    def update_conversation_summary(self, conv_id: str, summary: str) -> bool:
        """Update conversation summary.

        Args:
            conv_id: Conversation UUID.
            summary: Brief summary text.

        Returns:
            True if updated, False otherwise.
        """
        now = self._now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE conversations
                SET summary = ?, updated_at = ?
                WHERE id = ?
                """,
                (summary.strip(), now, conv_id),
            )
            return cursor.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        """Delete conversation and all related messages and generated files.

        Args:
            conv_id: Conversation UUID.

        Returns:
            True if deleted, False otherwise.
        """
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted conversation {conv_id} and associated records.")
            return deleted

    def add_message(
        self,
        conv_id: str,
        role: str,
        content: str,
        message_type: str = "chat",
    ) -> int:
        """Add a message to a conversation.

        Args:
            conv_id: Conversation UUID.
            role: Role of the message author ('user', 'assistant', 'system').
            content: Message body.
            message_type: Type ('chat', 'study_material', 'question_paper').

        Returns:
            The generated message ID.
        """
        now = self._now_iso()
        valid_roles = {"user", "assistant", "system"}
        if role not in valid_roles:
            raise ValueError(f"Invalid role '{role}'. Must be one of {valid_roles}")

        valid_types = {"chat", "study_material", "question_paper"}
        if message_type not in valid_types:
            raise ValueError(f"Invalid message_type '{message_type}'. Must be one of {valid_types}")

        with self.get_connection() as conn:
            # Check conversation exists
            cursor = conn.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,))
            if not cursor.fetchone():
                raise ValueError(f"Conversation with id '{conv_id}' does not exist.")

            cursor = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, message_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conv_id, role, content, message_type, now),
            )
            msg_id = cursor.lastrowid

            # Update updated_at on conversation
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id),
            )

        return msg_id

    def get_messages(self, conv_id: str) -> list[dict[str, Any]]:
        """Get all messages for a given conversation ordered chronologically.

        Args:
            conv_id: Conversation UUID.

        Returns:
            List of message dictionaries.
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, conversation_id, role, content, message_type, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conv_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def add_generated_file(
        self,
        conv_id: str,
        file_name: str,
        file_path: str,
        file_type: str,
    ) -> int:
        """Record a generated study material or question paper file.

        Args:
            conv_id: Conversation UUID.
            file_name: Name of generated file.
            file_path: Absolute filesystem path where file is saved.
            file_type: Type of file ('study_material' or 'question_paper').

        Returns:
            The ID of the inserted generated file record.
        """
        valid_types = {"study_material", "question_paper"}
        if file_type not in valid_types:
            raise ValueError(f"Invalid file_type '{file_type}'. Must be one of {valid_types}")

        now = self._now_iso()
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO generated_files (conversation_id, file_name, file_path, file_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conv_id, file_name.strip(), str(file_path), file_type, now),
            )
            file_id = cursor.lastrowid

            # Update conversation updated_at
            conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conv_id),
            )

        return file_id

    def get_generated_files(self, conv_id: str) -> list[dict[str, Any]]:
        """Get all generated files for a conversation.

        Args:
            conv_id: Conversation UUID.

        Returns:
            List of generated file record dictionaries.
        """
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, conversation_id, file_name, file_path, file_type, created_at
                FROM generated_files
                WHERE conversation_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (conv_id,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def search_conversations(self, query: str) -> list[dict[str, Any]]:
        """Search conversations by title or summary matching the query.

        Args:
            query: Search query string.

        Returns:
            List of matching conversation dictionaries.
        """
        pattern = f"%{query.strip()}%"
        sql = """
            SELECT 
                c.id,
                c.title,
                c.created_at,
                c.updated_at,
                c.file_names,
                c.summary,
                COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON c.id = m.conversation_id
            WHERE c.title LIKE ? OR c.summary LIKE ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (pattern, pattern))
            rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for r in rows:
            data = dict(r)
            try:
                data["file_names"] = json.loads(data["file_names"])
            except (json.JSONDecodeError, TypeError):
                data["file_names"] = []
            results.append(data)

        return results


# Global default instance
db = Database()
