"""Console event feed: ordered, bounded, thread-safe, and never able to break the agent."""
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent.fdb_livekit import TraceWriter
from agent.ui_events import MAX_PACKET_BYTES, TOPIC, RoomEventPublisher, encode_event


class FakeParticipant:
    def __init__(self, fail_first: int = 0) -> None:
        self.sent: list[tuple[dict, str]] = []
        self.fail_first = fail_first

    async def publish_data(self, payload, *, reliable=True, topic=""):
        if self.fail_first:
            self.fail_first -= 1
            raise RuntimeError("not connected")
        self.sent.append((json.loads(payload), topic))


def fake_room(participant):
    return SimpleNamespace(local_participant=participant)


async def drain(publisher, expected, participant):
    for _ in range(200):
        if len(participant.sent) + publisher.failed >= expected:
            return
        await asyncio.sleep(0.005)


class PublisherTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_are_sent_in_order_on_the_console_topic(self):
        participant = FakeParticipant()
        publisher = RoomEventPublisher(fake_room(participant))
        publisher.publish("tool_started", call_id="a")
        publisher.start()
        publisher.publish("tool_finished", call_id="a")
        await drain(publisher, 2, participant)
        await publisher.aclose()
        self.assertEqual([(e["kind"], t) for e, t in participant.sent], [("tool_started", TOPIC), ("tool_finished", TOPIC)])

    async def test_failed_send_is_counted_and_the_loop_continues(self):
        participant = FakeParticipant(fail_first=1)
        publisher = RoomEventPublisher(fake_room(participant))
        publisher.start()
        publisher.publish("one")
        publisher.publish("two")
        await drain(publisher, 2, participant)
        await publisher.aclose()
        self.assertEqual(publisher.failed, 1)
        self.assertEqual([e["kind"] for e, _ in participant.sent], ["two"])

    async def test_full_queue_drops_the_oldest_event(self):
        participant = FakeParticipant()
        publisher = RoomEventPublisher(fake_room(participant), max_queue=2)
        for kind in ("a", "b", "c"):
            publisher.publish(kind)
        publisher.start()
        await drain(publisher, 2, participant)
        await publisher.aclose()
        self.assertEqual(publisher.dropped, 1)
        self.assertEqual([e["kind"] for e, _ in participant.sent], ["b", "c"])

    async def test_publish_from_another_thread(self):
        participant = FakeParticipant()
        publisher = RoomEventPublisher(fake_room(participant))
        publisher.start()
        thread = threading.Thread(target=publisher.publish, args=("from_thread",), kwargs={"n": 1})
        thread.start()
        thread.join()
        await drain(publisher, 1, participant)
        await publisher.aclose()
        self.assertEqual(participant.sent[0][0]["kind"], "from_thread")

    async def test_close_cancels_the_owned_task(self):
        publisher = RoomEventPublisher(fake_room(FakeParticipant()))
        publisher.start()
        task = publisher._task
        await publisher.aclose()
        self.assertTrue(task.cancelled())
        await publisher.aclose()  # idempotent

    async def test_trace_records_reach_the_listener_after_the_file(self):
        participant = FakeParticipant()
        publisher = RoomEventPublisher(fake_room(participant))
        publisher.start()
        with tempfile.TemporaryDirectory() as directory:
            trace = TraceWriter(Path(directory), listener=publisher.forward)
            trace.append("tool_call", room="r", call={"function": "track_order", "args": {"order_id": "X1"}})
            written = json.loads((Path(directory) / "livekit-agent.jsonl").read_text())
        await drain(publisher, 1, participant)
        await publisher.aclose()
        self.assertEqual(written["kind"], "tool_call")
        self.assertEqual(participant.sent[0][0]["call"]["function"], "track_order")


class EncodeTests(unittest.TestCase):
    def test_oversized_thumbnail_is_dropped_not_the_event(self):
        data = json.loads(encode_event("frame_attached", {"width": 640, "thumbnail": "x" * (MAX_PACKET_BYTES + 10)}))
        self.assertEqual(data["width"], 640)
        self.assertTrue(data["thumbnail_dropped"])
        self.assertNotIn("thumbnail", data)

    def test_listener_failure_never_breaks_the_trace(self):
        def broken(_record):
            raise RuntimeError("console down")

        with tempfile.TemporaryDirectory() as directory:
            trace = TraceWriter(Path(directory), listener=broken)
            trace.append("tool_call", room="r")
            self.assertEqual(len((Path(directory) / "livekit-agent.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
