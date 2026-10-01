"""Small in-process event broker for local SSE development.

Production deployments replace this object with Redis Pub/Sub or a managed event bus,
while retaining the same event shape at the HTTP boundary.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class DashboardEvent:
    id: str
    event_type: str
    tenant_id: str
    payload: dict[str, Any]
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.event_type,
            "tenant_id": self.tenant_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }


class EventBroker:
    """Fan-out broker for connected SSE clients in one API process."""

    def __init__(self) -> None:
        self._subscribers: dict[str, tuple[str | None, asyncio.Queue[DashboardEvent]]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, tenant_id: str | None = None) -> tuple[str, asyncio.Queue[DashboardEvent]]:
        subscription_id = str(uuid4())
        queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[subscription_id] = (tenant_id, queue)
        return subscription_id, queue

    async def unsubscribe(self, subscription_id: str) -> None:
        async with self._lock:
            self._subscribers.pop(subscription_id, None)

    async def publish(self, event_type: str, tenant_id: str, payload: dict[str, Any]) -> DashboardEvent:
        event = DashboardEvent(
            id=str(uuid4()),
            event_type=event_type,
            tenant_id=tenant_id,
            payload=payload,
            created_at=datetime.now(UTC).isoformat(),
        )
        async with self._lock:
            subscribers = list(self._subscribers.values())
        for subscribed_tenant, queue in subscribers:
            if subscribed_tenant and subscribed_tenant != tenant_id:
                continue
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
        return event
