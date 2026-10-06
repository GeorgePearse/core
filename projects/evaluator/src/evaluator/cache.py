"""Caching system for LLM-as-judge evaluations."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class CacheEntry(Base):
    """Database model for cached LLM judge evaluations."""

    __tablename__ = "judge_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String(64), index=True, nullable=False)
    judge_model = Column(String(100), nullable=False)
    response_hash = Column(String(64), nullable=False)
    result = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    def __init__(
        self,
        cache_key: str,
        judge_model: str,
        response_hash: str,
        result: str,
        ttl_hours: Optional[int] = None,
    ) -> None:
        """Initialize cache entry."""
        self.cache_key = cache_key
        self.judge_model = judge_model
        self.response_hash = response_hash
        self.result = result
        self.created_at = datetime.now(timezone.utc)
        if ttl_hours:
            self.expires_at = self.created_at + timedelta(hours=ttl_hours)


class JudgeCache:
    """SQLite cache for LLM judge results."""

    def __init__(self, db_path: str = ".evaluator_cache.db") -> None:
        """Initialize cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _make_cache_key(
        self,
        model_under_test: str,
        agent_response: str,
        judge_prompt: str,
    ) -> str:
        """Create cache key from inputs.

        Args:
            model_under_test: Model being tested
            agent_response: The agent's response text
            judge_prompt: The judge's system prompt

        Returns:
            Cache key hash
        """
        key_data = f"{model_under_test}|{agent_response}|{judge_prompt}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(
        self,
        model_under_test: str,
        agent_response: str,
        judge_prompt: str,
        judge_model: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve cached judge result.

        Args:
            model_under_test: Model being tested
            agent_response: The agent's response
            judge_prompt: Judge system prompt
            judge_model: Judge model used

        Returns:
            Cached result dict or None if not found/expired
        """
        cache_key = self._make_cache_key(model_under_test, agent_response, judge_prompt)

        with self.SessionLocal() as session:
            from sqlalchemy import and_

            entry = (
                session.query(CacheEntry)
                .filter(
                    and_(
                        CacheEntry.cache_key == cache_key,
                        CacheEntry.judge_model == judge_model,
                    )
                )
                .first()
            )

            if not entry:
                return None

            # Check if expired (handle timezone-naive datetimes from SQLite)
            if entry.expires_at:
                expires_at = entry.expires_at
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at < datetime.now(timezone.utc):
                    session.delete(entry)
                    session.commit()
                    return None

            try:
                return json.loads(entry.result)
            except json.JSONDecodeError:
                return None

    def set(
        self,
        model_under_test: str,
        agent_response: str,
        judge_prompt: str,
        judge_model: str,
        result: dict[str, Any],
        ttl_hours: Optional[int] = 24,
    ) -> None:
        """Cache judge result.

        Args:
            model_under_test: Model being tested
            agent_response: The agent's response
            judge_prompt: Judge system prompt
            judge_model: Judge model used
            result: The judge result to cache
            ttl_hours: Time to live in hours (default 24)
        """
        cache_key = self._make_cache_key(model_under_test, agent_response, judge_prompt)

        with self.SessionLocal() as session:
            entry = CacheEntry(
                cache_key=cache_key,
                judge_model=judge_model,
                response_hash=hashlib.sha256(agent_response.encode()).hexdigest(),
                result=json.dumps(result),
                ttl_hours=ttl_hours,
            )
            session.add(entry)
            session.commit()

    def clear(self) -> None:
        """Clear all cache entries."""
        with self.SessionLocal() as session:
            session.query(CacheEntry).delete()
            session.commit()

    def cleanup_expired(self) -> int:
        """Remove expired entries.

        Returns:
            Number of entries deleted
        """
        with self.SessionLocal() as session:
            from sqlalchemy import and_

            result = (
                session.query(CacheEntry)
                .filter(
                    and_(
                        CacheEntry.expires_at is not None,
                        CacheEntry.expires_at < datetime.now(timezone.utc),
                    )
                )
                .delete()
            )
            session.commit()
            return result
