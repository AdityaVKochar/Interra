"""Extension domain rules: guide lookup, duplicate-safe ticket writes, request versions."""
import json
import tempfile
import unittest
from pathlib import Path

from agent.troubleshooting import TicketDesk, TurnGuard, classify, lookup_guide, _DEVICE_ALIASES


class GuideLookupTests(unittest.TestCase):
    def test_device_and_problem_in_the_persons_words(self):
        guide = lookup_guide("my wifi router", "the internet light is red and nothing connects")
        self.assertEqual((guide["device"], guide["problem"], guide["matched"]), ("router", "no_internet", True))
        self.assertGreaterEqual(len(guide["checks"]), 3)

    def test_correction_changes_the_guide(self):
        router = lookup_guide("router", "no power")
        strip = lookup_guide("power strip", "no power")
        self.assertEqual(strip["device"], "power_strip")
        self.assertNotEqual(router["checks"], strip["checks"])

    def test_hazard_stops_troubleshooting(self):
        guide = lookup_guide("laptop charger", "it smells burnt and is hot")
        self.assertTrue(guide["stop_first"])
        self.assertIn("Unplug", guide["checks"][0])

    def test_unknown_device_gets_a_safe_fallback(self):
        guide = lookup_guide("coffee grinder", "weird noise")
        self.assertFalse(guide["matched"])
        self.assertTrue(guide["checks"])

    def test_short_phrases_need_word_boundaries(self):
        self.assertIsNone(classify("please repair it", {"x": ("pair",)}))
        self.assertEqual(classify("the tv is off", _DEVICE_ALIASES), "television")


class TicketDeskTests(unittest.TestCase):
    def desk(self, journal=None):
        ids = iter(["T-000001", "T-000002", "T-000003"])
        return TicketDesk(journal, clock=lambda: 100.0, new_id=lambda: next(ids))

    def test_repeated_open_returns_the_same_ticket(self):
        desk = self.desk()
        first, created = desk.open("router", "internet light off", "restarted twice")
        again, created_again = desk.open("wifi router", "no internet", "asked again")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.ticket_id, again.ticket_id)
        self.assertEqual(len(desk.tickets()), 1)

    def test_cancel_once_then_reopen_is_a_new_ticket(self):
        desk = self.desk()
        ticket, _ = desk.open("router", "no internet", "s")
        _, changed = desk.cancel(ticket.ticket_id, "wrong device")
        _, changed_again = desk.cancel(ticket.ticket_id.lower(), "again")
        reopened, created = desk.open("router", "no internet", "s")
        self.assertEqual((changed, changed_again, created), (True, False, True))
        self.assertNotEqual(reopened.ticket_id, ticket.ticket_id)

    def test_unknown_ticket_cannot_be_cancelled(self):
        self.assertEqual(self.desk().cancel("T-404", "x"), (None, False))

    def test_journal_records_each_real_change_once(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "tickets.jsonl"
            desk = self.desk(journal)
            ticket, _ = desk.open("printer", "paper jam", "s")
            desk.open("printer", "jam", "duplicate")
            desk.cancel(ticket.ticket_id, "fixed")
            desk.cancel(ticket.ticket_id, "fixed again")
            events = [json.loads(line)["event"] for line in journal.read_text().splitlines()]
        self.assertEqual(events, ["opened", "cancelled"])


class TurnGuardTests(unittest.TestCase):
    def test_older_versions_are_stale(self):
        guard = TurnGuard()
        version = guard.advance("turn")
        self.assertTrue(guard.is_current(version))
        guard.advance("correction")
        self.assertFalse(guard.is_current(version))
        self.assertEqual(guard.reasons, ["turn", "correction"])


if __name__ == "__main__":
    unittest.main()
