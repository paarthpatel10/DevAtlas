"""
In-Memory Conversation Memory — lightweight fallback when DynamoDB is unavailable.

Stores conversation history in a Python dict. Data is lost when the process
restarts, but this is perfectly fine for local development and Docker Compose
environments where DynamoDB is not provisioned.
"""

import collections
import time
from typing import Dict, List

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class InMemoryConversationMemory:
    """Thread-safe, in-process conversation memory implementation."""

    def __init__(self) -> None:
        # session_id -> list of (timestamp, role, content)
        self._store: Dict[str, List[tuple]] = collections.defaultdict(list)
        logger.info("Using IN-MEMORY conversation memory (non-persistent)")

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Adds a message to the conversation history."""
        self._store[session_id].append(
            (time.time(), role, content)
        )

    def get_history(
        self, session_id: str, limit: int = 10
    ) -> List[Dict[str, str]]:
        """Retrieves conversation history for a session in chronological order."""
        messages = self._store.get(session_id, [])
        # Already in chronological order; take the last `limit` entries
        recent = messages[-limit:] if limit else messages
        return [{"role": role, "content": content} for _, role, content in recent]
