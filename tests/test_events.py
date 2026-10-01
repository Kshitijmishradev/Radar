import asyncio
import unittest

from app.events import EventBroker


class EventBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_are_only_sent_to_matching_tenant(self) -> None:
        broker = EventBroker()
        _, acme_queue = await broker.subscribe("acme")
        _, other_queue = await broker.subscribe("other")
        await broker.publish("action.approved", "acme", {"action_id": "action-1"})

        event = await asyncio.wait_for(acme_queue.get(), timeout=0.1)
        self.assertEqual(event.event_type, "action.approved")
        self.assertEqual(event.tenant_id, "acme")
        self.assertTrue(other_queue.empty())

    async def test_unscoped_subscriber_receives_all_events(self) -> None:
        broker = EventBroker()
        _, queue = await broker.subscribe()
        await broker.publish("action.succeeded", "acme", {"action_id": "action-1"})
        self.assertEqual((await asyncio.wait_for(queue.get(), timeout=0.1)).tenant_id, "acme")
