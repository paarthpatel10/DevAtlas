"""
Conversation Memory — abstract protocol for conversation memory backends.
Defines the interface that all memory implementations must follow.
"""

from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class ConversationMemory(Protocol):
    """Protocol defining the conversation memory interface."""

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """
        Stores a message in the conversation history.

        Args:
            session_id: Unique session identifier.
            role: Message role — 'user' or 'assistant'.
            content: Message content text.
        """
        ...

    def get_history(
        self, session_id: str, limit: int = 10
    ) -> List[Dict[str, str]]:
        """
        Retrieves conversation history for a session.

        Args:
            session_id: Unique session identifier.
            limit: Maximum number of messages to return.

        Returns:
            List of dicts with 'role' and 'content' keys, in chronological order.
        """
        ...
