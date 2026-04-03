# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Leader Elector — single-leader coordination for fabric background tasks.

Only the leader runs background tasks (polls, pipelines, scheduler).
All workers serve endpoints. On leader death, followers detect expired
TTL and compete for the lock.

Backends:
- Redis: SETNX with TTL (default 30s), heartbeat every 10s
- PostgreSQL: pg_advisory_lock (non-blocking try)
- Auto-detect: Redis if redis_url configured, else PostgreSQL
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["LeaderElector", "RedisLeaderBackend", "InMemoryLeaderBackend"]

_LEADER_KEY = "fabric:leader"
_DEFAULT_TTL = 30  # seconds
_DEFAULT_HEARTBEAT = 10  # seconds


class LeaderBackend(ABC):
    """Abstract backend for leader election."""

    @abstractmethod
    async def try_acquire(self, leader_id: str, ttl: int) -> bool:
        """Attempt to acquire leadership. Returns True if acquired."""

    @abstractmethod
    async def renew(self, leader_id: str, ttl: int) -> bool:
        """Renew leadership TTL. Returns True if still leader."""

    @abstractmethod
    async def release(self, leader_id: str) -> None:
        """Release leadership."""

    @abstractmethod
    async def get_leader(self) -> Optional[str]:
        """Get current leader ID, or None if no leader."""


class RedisLeaderBackend(LeaderBackend):
    """Redis-based leader election using SETNX + TTL."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: Optional[object] = None

    async def _ensure_client(self) -> object:
        if self._client is None:
            try:
                import redis.asyncio as aioredis
            except ImportError as exc:
                raise ImportError(
                    "redis[asyncio] is required for Redis leader election. "
                    "Install with: pip install redis"
                ) from exc
            self._client = aioredis.from_url(self._redis_url)
        return self._client

    async def try_acquire(self, leader_id: str, ttl: int) -> bool:
        client = await self._ensure_client()
        acquired = await client.set(  # type: ignore[union-attr]
            _LEADER_KEY, leader_id, nx=True, ex=ttl
        )
        return bool(acquired)

    async def renew(self, leader_id: str, ttl: int) -> bool:
        client = await self._ensure_client()
        current = await client.get(_LEADER_KEY)  # type: ignore[union-attr]
        if current and current.decode("utf-8") == leader_id:
            await client.expire(_LEADER_KEY, ttl)  # type: ignore[union-attr]
            return True
        return False

    async def release(self, leader_id: str) -> None:
        client = await self._ensure_client()
        current = await client.get(_LEADER_KEY)  # type: ignore[union-attr]
        if current and current.decode("utf-8") == leader_id:
            await client.delete(_LEADER_KEY)  # type: ignore[union-attr]

    async def get_leader(self) -> Optional[str]:
        client = await self._ensure_client()
        current = await client.get(_LEADER_KEY)  # type: ignore[union-attr]
        if current:
            return current.decode("utf-8")
        return None

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()  # type: ignore[union-attr]
            self._client = None


class InMemoryLeaderBackend(LeaderBackend):
    """In-memory leader backend for dev mode (single worker)."""

    def __init__(self) -> None:
        self._leader_id: Optional[str] = None

    async def try_acquire(self, leader_id: str, ttl: int) -> bool:
        if self._leader_id is None:
            self._leader_id = leader_id
            return True
        return self._leader_id == leader_id

    async def renew(self, leader_id: str, ttl: int) -> bool:
        return self._leader_id == leader_id

    async def release(self, leader_id: str) -> None:
        if self._leader_id == leader_id:
            self._leader_id = None

    async def get_leader(self) -> Optional[str]:
        return self._leader_id


class LeaderElector:
    """Manages leader election and heartbeat for fabric runtime.

    In production, uses Redis SETNX with TTL. In dev mode, uses in-memory
    backend (single worker always becomes leader).
    """

    def __init__(
        self,
        backend: Optional[LeaderBackend] = None,
        redis_url: Optional[str] = None,
        ttl: int = _DEFAULT_TTL,
        heartbeat_interval: int = _DEFAULT_HEARTBEAT,
        dev_mode: bool = False,
    ) -> None:
        self._leader_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self._ttl = ttl
        self._heartbeat_interval = heartbeat_interval
        self._is_leader = False
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._shutting_down = False

        if backend is not None:
            self._backend = backend
        elif dev_mode or not redis_url:
            self._backend = InMemoryLeaderBackend()
        else:
            self._backend = RedisLeaderBackend(redis_url)

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    @property
    def leader_id(self) -> str:
        return self._leader_id

    async def try_elect(self) -> bool:
        """Attempt to become the leader.

        Returns True if this instance is now the leader.
        """
        try:
            acquired = await self._backend.try_acquire(self._leader_id, self._ttl)
            if acquired:
                self._is_leader = True
                logger.debug("Leader elected: %s (TTL=%ds)", self._leader_id, self._ttl)
            else:
                current = await self._backend.get_leader()
                logger.debug("Leader election lost. Current leader: %s", current)
            return acquired
        except Exception:
            logger.exception("Leader election failed")
            return False

    async def start_heartbeat(self) -> None:
        """Start the heartbeat loop to maintain leadership."""
        if self._heartbeat_task is not None:
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Periodically renew the leader lock."""
        while not self._shutting_down:
            try:
                if self._is_leader:
                    renewed = await self._backend.renew(self._leader_id, self._ttl)
                    if not renewed:
                        logger.warning(
                            "Lost leadership — lock expired or taken by another worker"
                        )
                        self._is_leader = False
                else:
                    # Try to acquire if not leader (failover)
                    acquired = await self._backend.try_acquire(
                        self._leader_id, self._ttl
                    )
                    if acquired:
                        self._is_leader = True
                        logger.debug("Acquired leadership via failover")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Heartbeat error")

            try:
                await asyncio.sleep(self._heartbeat_interval)
            except asyncio.CancelledError:
                break

    async def release(self) -> None:
        """Release leadership and stop heartbeat."""
        self._shutting_down = True

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._is_leader:
            try:
                await self._backend.release(self._leader_id)
                logger.debug("Released leadership: %s", self._leader_id)
            except Exception:
                logger.exception("Failed to release leader lock")
            self._is_leader = False

        if isinstance(self._backend, RedisLeaderBackend):
            await self._backend.close()

    async def get_current_leader(self) -> Optional[str]:
        """Get the current leader ID."""
        return await self._backend.get_leader()
