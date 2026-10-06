"""Camera-assisted device troubleshooting: guides, a support-ticket desk, and stale-result guarding.

This is the extension use case, outside the benchmark domains. Everything here
is provider-agnostic and synchronous, so the LiveKit adapter in
``agent.extension_livekit`` stays thin and these rules are unit-tested directly.

* ``lookup_guide`` maps what the person names (and the camera shows) to an
  ordered list of safe checks from a local guide library.
* ``TicketDesk`` is the one state-changing service. Opening a ticket for the same
  device and problem while one is open returns the existing ticket instead of a
  second one; cancelling twice is a no-op. Tickets are appended to a local JSONL
  file, so the side effect is real and auditable.
* ``TurnGuard`` versions the person's request. A lookup that finishes after the
  person corrected the device or the problem carries an old version and is
  discarded instead of answering the obsolete request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import threading
import time
from typing import Callable
import uuid


@dataclass(frozen=True)
class Guide:
    device: str
    problem: str
    checks: tuple[str, ...]
    safety: str = ""
    escalate_when: str = ""


_DEVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "router": ("router", "modem", "wifi", "wi-fi", "access point", "gateway", "ont", "internet box"),
    "printer": ("printer", "inkjet", "laserjet", "laser printer", "scanner"),
    "power_strip": ("power strip", "extension", "surge protector", "power board", "multi plug", "multiplug", "socket strip"),
    "laptop_charger": ("charger", "power adapter", "adapter", "power brick", "charging cable", "usb-c cable"),
    "smart_bulb": ("bulb", "smart light", "lamp", "light bulb"),
    "television": ("tv", "television", "smart tv", "monitor", "screen", "remote"),
    "headphones": ("headphones", "earbuds", "headset", "earphones", "airpods"),
    "phone": ("phone", "smartphone", "mobile", "iphone", "android"),
}

_PROBLEM_ALIASES: dict[str, tuple[str, ...]] = {
    "no_power": ("no power", "won't turn on", "wont turn on", "dead", "not turning on", "doesn't turn on",
                 "light is off", "lights are off", "no light", "not working at all", "off"),
    "no_internet": ("no internet", "offline", "not connecting", "can't connect", "cannot connect",
                    "no connection", "internet light", "disconnect", "drops", "dropping"),
    "slow": ("slow", "lag", "buffering", "weak signal"),
    "blinking": ("blinking", "flashing", "red light", "orange light", "amber", "error light"),
    "not_charging": ("not charging", "won't charge", "wont charge", "charging slowly", "battery"),
    "paper_jam": ("jam", "paper stuck", "stuck paper", "won't feed", "not feeding"),
    "not_printing": ("not printing", "won't print", "wont print", "blank page", "faded", "streaks"),
    "no_sound": ("no sound", "no audio", "can't hear", "cannot hear", "muted", "one side"),
    "not_pairing": ("pair", "pairing", "bluetooth", "not connecting to bluetooth", "won't connect"),
    "overheating": ("hot", "overheat", "burning smell", "smell", "smoke", "sparks", "scorch"),
}

_HAZARD_PROBLEMS = {"overheating"}

GUIDES: tuple[Guide, ...] = (
    Guide("router", "no_internet", (
        "Check that the power light is on and the cable from the wall or fibre box is clicked into the WAN or internet port.",
        "Look at the internet or globe light: off or red means the line is down, blinking usually means it is still syncing.",
        "Restart it: unplug power for 30 seconds, plug back in, and wait two minutes for the lights to settle.",
        "Test one device with a cable if possible, to separate a Wi-Fi problem from a line problem.",
    ), escalate_when="the internet light stays red or off for five minutes after a restart"),
    Guide("router", "no_power", (
        "Confirm the adapter is the router's own adapter and is pushed fully into the round power port.",
        "Try the adapter in a wall socket you know works, not a power strip.",
        "If the router has a power button on the back, press it once and wait ten seconds.",
    ), escalate_when="no light appears on a known-good socket"),
    Guide("router", "slow", (
        "Move closer, or check that nothing metal or a microwave sits between you and the router.",
        "Restart the router to clear a stuck connection table.",
        "Check how many devices are streaming or downloading at the same time.",
    ), escalate_when="a cabled device is also slow after a restart"),
    Guide("router", "blinking", (
        "Read which light is blinking: power, internet or Wi-Fi each mean something different.",
        "A blinking internet light usually means the router is still negotiating the line; wait two minutes.",
        "A red or amber light after two minutes points at the line or the account, not the Wi-Fi.",
    ), escalate_when="the light stays red or amber after a restart"),
    Guide("printer", "paper_jam", (
        "Switch the printer off before reaching inside.",
        "Open the front and rear access doors and pull jammed paper out slowly in the direction it travels.",
        "Check for torn scraps left on the rollers, then reload a short, aligned stack.",
    ), safety="Let a laser printer's fuser cool for ten minutes; it can be hot.",
       escalate_when="the jam warning stays on with no visible paper"),
    Guide("printer", "not_printing", (
        "Check the display for an error, and that the right printer is selected on the computer.",
        "Print a self-test page from the printer's own menu to separate printer from computer problems.",
        "Clear the print queue on the computer and resend one page.",
        "For faded or streaky pages, run the head-cleaning or toner check from the printer menu.",
    ), escalate_when="the self-test page is blank or streaked after cleaning"),
    Guide("printer", "no_power", (
        "Check the power cable at both ends; printers often use a separate cable into the back.",
        "Try a wall socket you know works.",
    ), escalate_when="no display or light on a known-good socket"),
    Guide("power_strip", "no_power", (
        "Check the strip's own switch; many have an illuminated rocker that is easy to knock off.",
        "Look for a reset or overload button on the side and press it once.",
        "Plug a lamp you know works straight into the wall socket, then into the strip, to find which one has failed.",
        "Unplug high-draw devices such as heaters or kettles; strips trip when overloaded.",
    ), safety="Never daisy-chain one strip into another.",
       escalate_when="the strip trips again with only light loads"),
    Guide("laptop_charger", "not_charging", (
        "Check that both ends are fully seated and the cable is not kinked or frayed near the plugs.",
        "Look for the charging light on the laptop or the adapter.",
        "Try a different wall socket, then a different port on the laptop if it has more than one USB-C port.",
        "Check the adapter's wattage label matches what the laptop needs.",
    ), safety="Stop using a charger with exposed wires or a melted plug.",
       escalate_when="a known-good charger also fails on this laptop"),
    Guide("smart_bulb", "no_internet", (
        "Make sure the wall switch for the lamp is on; smart bulbs drop off the network when switched off.",
        "Check the bulb is on the 2.4 GHz Wi-Fi band if the app requires it.",
        "Reset the bulb with its on-off sequence from the manufacturer's app, then pair it again.",
    ), escalate_when="the bulb will not enter pairing mode after a reset"),
    Guide("smart_bulb", "no_power", (
        "Check the wall switch and the lamp's own switch.",
        "Try the bulb in a fitting you know works.",
    ), escalate_when="the bulb stays dark in a known-good fitting"),
    Guide("television", "no_power", (
        "Look for the standby light; if it is on, the TV has power and the problem is the remote or input.",
        "Press the power button on the TV itself, not the remote.",
        "Check the remote's batteries and point it straight at the TV.",
    ), escalate_when="no standby light on a known-good socket"),
    Guide("television", "no_sound", (
        "Check the TV is not muted and the volume is up on the TV, not only the remote's device.",
        "Check the sound output setting: TV speakers or an external speaker.",
        "Unplug and reconnect any HDMI cable going to a soundbar.",
    ), escalate_when="no sound from the TV's own speakers with every input"),
    Guide("headphones", "not_pairing", (
        "Put the headphones in pairing mode; usually hold the power or pairing button until the light flashes.",
        "Remove the old pairing from the phone's Bluetooth list, then pair again.",
        "Turn Bluetooth off and on on the phone, and keep the headphones within a metre.",
    ), escalate_when="they do not appear in the phone's Bluetooth list in pairing mode"),
    Guide("headphones", "no_sound", (
        "Check the phone's output is set to the headphones, not its own speaker.",
        "Check the volume on both the phone and the headphones.",
        "Clean the earbud mesh gently if only one side is quiet.",
    ), escalate_when="one side stays silent after cleaning and re-pairing"),
    Guide("phone", "not_charging", (
        "Look inside the charging port with a light for lint, and remove it gently with a wooden toothpick.",
        "Try another cable and another adapter.",
        "Restart the phone and check whether a charging icon appears.",
    ), escalate_when="no charging icon with known-good cables after cleaning the port"),
)

_FALLBACK_CHECKS = (
    "Name the device and what it is doing, or show its lights and labels to the camera.",
    "Check power first: the cable at both ends and a wall socket you know works.",
    "Restart the device once, then describe what changes.",
)


def _matches(text: str, phrases: tuple[str, ...]) -> int:
    text = f" {re.sub(r'[^a-z0-9+ -]', ' ', text.lower())} "
    return max((len(phrase) for phrase in phrases if f" {phrase} " in text or (len(phrase) > 4 and phrase in text)),
               default=0)


def classify(text: str, aliases: dict[str, tuple[str, ...]]) -> str | None:
    """Pick the category whose longest matching phrase is longest, or ``None``."""
    scores = {name: _matches(text, phrases) for name, phrases in aliases.items()}
    best = max(scores, key=lambda name: scores[name])
    return best if scores[best] else None


def lookup_guide(device: str, symptom: str) -> dict[str, object]:
    """Return ordered checks for a device and symptom, or a safe fallback."""
    device_key = classify(device, _DEVICE_ALIASES) or classify(symptom, _DEVICE_ALIASES)
    problem_key = classify(symptom, _PROBLEM_ALIASES)
    if problem_key in _HAZARD_PROBLEMS:
        return {
            "device": device_key or device, "problem": problem_key, "matched": True, "stop_first": True,
            "checks": ["Unplug the device at the wall now if it is safe to reach, and do not touch it if it is hot or smoking."],
            "safety": "Heat, smoke, sparks or a burning smell are a fire risk; do not keep troubleshooting.",
            "escalate_when": "always: have it inspected before using it again",
        }
    candidates = [guide for guide in GUIDES if guide.device == device_key]
    guide = next((g for g in candidates if g.problem == problem_key), None)
    if guide is None and candidates and problem_key is None:
        guide = candidates[0]
    if guide is None:
        return {"device": device_key or device, "problem": problem_key or symptom, "matched": False,
                "checks": list(_FALLBACK_CHECKS), "safety": "", "escalate_when": ""}
    return {"device": guide.device, "problem": guide.problem, "matched": True, "checks": list(guide.checks),
            "safety": guide.safety, "escalate_when": guide.escalate_when}


@dataclass
class Ticket:
    ticket_id: str
    device: str
    problem: str
    summary: str
    status: str = "open"
    opened_at: float = 0.0
    cancelled_at: float | None = None
    cancel_reason: str = ""
    history: list[str] = field(default_factory=list)


class TicketDesk:
    """A session's support tickets with duplicate protection for every write."""

    def __init__(
        self, journal: Path | None = None, *, clock: Callable[[], float] = time.time,
        new_id: Callable[[], str] = lambda: "T-" + uuid.uuid4().hex[:6].upper(),
    ) -> None:
        self._journal = journal
        self._clock = clock
        self._new_id = new_id
        self._tickets: dict[str, Ticket] = {}
        self._lock = threading.Lock()

    def _key(self, device: str, problem: str) -> tuple[str, str]:
        return (classify(device, _DEVICE_ALIASES) or device.strip().lower(),
                classify(problem, _PROBLEM_ALIASES) or problem.strip().lower())

    def open(self, device: str, problem: str, summary: str) -> tuple[Ticket, bool]:
        """Open a ticket, or return the open one for the same device and problem."""
        key = self._key(device, problem)
        with self._lock:
            for ticket in self._tickets.values():
                if ticket.status == "open" and (ticket.device, ticket.problem) == key:
                    ticket.history.append("duplicate open request suppressed")
                    return ticket, False
            ticket = Ticket(self._new_id(), key[0], key[1], summary.strip(), opened_at=self._clock())
            ticket.history.append("opened")
            self._tickets[ticket.ticket_id] = ticket
        self._write("opened", ticket)
        return ticket, True

    def cancel(self, ticket_id: str, reason: str) -> tuple[Ticket | None, bool]:
        """Cancel once. Returns the ticket and whether this call changed it."""
        with self._lock:
            ticket = self._tickets.get(ticket_id.strip().upper())
            if ticket is None or ticket.status == "cancelled":
                return ticket, False
            ticket.status = "cancelled"
            ticket.cancelled_at = self._clock()
            ticket.cancel_reason = reason.strip()
            ticket.history.append("cancelled")
        self._write("cancelled", ticket)
        return ticket, True

    def tickets(self) -> list[Ticket]:
        with self._lock:
            return list(self._tickets.values())

    def _write(self, event: str, ticket: Ticket) -> None:
        if self._journal is None:
            return
        self._journal.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": event, "time": self._clock(), "ticket": asdict(ticket)}) + "\n")


class TurnGuard:
    """Version the person's current request; results from older versions are stale."""

    def __init__(self) -> None:
        self._version = 0
        self.reasons: list[str] = []

    @property
    def version(self) -> int:
        return self._version

    def advance(self, reason: str) -> int:
        self._version += 1
        self.reasons.append(reason)
        return self._version

    def is_current(self, version: int) -> bool:
        return version == self._version
