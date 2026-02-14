"""In-memory session storage with TTL for flow state."""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UserSession:
    """User session data with creation timestamp."""

    user_id: str
    created_at: float = field(default_factory=time.time)
    answers: dict[str, str] = field(default_factory=dict)
    hint: str | None = None
    awaiting_hint: bool = False
    last_rec_id: str | None = None
    last_item_id: str | None = None
    last_ref: dict[str, str] | None = None  # Deep-link ref info


class SessionStore:
    """Thread-safe in-memory session store with TTL cleanup."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        """Initialize session store.

        Args:
            ttl_seconds: Time-to-live for sessions (default 10 minutes)
        """
        self._sessions: dict[str, UserSession] = {}
        self._ttl = ttl_seconds

    def get(self, user_id: str) -> UserSession | None:
        """Get session for user, returns None if expired or missing."""
        self._cleanup_expired()
        session = self._sessions.get(user_id)
        if session and (time.time() - session.created_at) > self._ttl:
            del self._sessions[user_id]
            return None
        return session

    def get_or_create(self, user_id: str) -> UserSession:
        """Get existing session or create a new one."""
        session = self.get(user_id)
        if session is None:
            session = UserSession(user_id=user_id)
            self._sessions[user_id] = session
        return session

    def set_answers(self, user_id: str, answers: dict[str, str]) -> None:
        """Update session answers."""
        session = self.get_or_create(user_id)
        session.answers = answers

    def set_last_rec(self, user_id: str, rec_id: str, item_id: str) -> None:
        """Store last recommendation info."""
        session = self.get_or_create(user_id)
        session.last_rec_id = rec_id
        session.last_item_id = item_id

    def set_ref(self, user_id: str, ref: dict[str, str]) -> None:
        """Store deep-link reference info."""
        session = self.get_or_create(user_id)
        session.last_ref = ref

    def get_ref(self, user_id: str) -> dict[str, str] | None:
        """Get deep-link reference info."""
        session = self.get(user_id)
        return session.last_ref if session else None

    def clear(self, user_id: str) -> None:
        """Clear session for user."""
        self._sessions.pop(user_id, None)

    def reset_flow(self, user_id: str) -> None:
        """Reset flow state but keep ref info."""
        session = self.get(user_id)
        if session:
            session.answers = {}
            session.hint = None
            session.awaiting_hint = False
            session.created_at = time.time()

    def _cleanup_expired(self) -> None:
        """Remove expired sessions."""
        now = time.time()
        expired = [
            uid for uid, s in self._sessions.items()
            if (now - s.created_at) > self._ttl
        ]
        for uid in expired:
            del self._sessions[uid]


# Global session stores
flow_sessions = SessionStore(ttl_seconds=600)  # 10 min for flow
rec_sessions = SessionStore(ttl_seconds=1800)  # 30 min for rec tracking
