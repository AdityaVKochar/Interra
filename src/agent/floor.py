"""Truthful acknowledgments with no dependency on the reasoning provider."""


class FloorManager:
    def __init__(self):
        self.count = 0
        self.used = set()

    def correction(self, slots, changed):
        details = [f'{name.replace("_", " ")} to {slots[name]}' for name in sorted(changed)
                   if name in slots and isinstance(slots[name], (str, int, float, bool))]
        text = ('I updated ' + ', '.join(details[:2]) + '.') if details else "I'll continue from your latest request."
        if text in self.used:
            return None
        self.used.add(text)
        self.count += 1
        return text

    def acknowledge(self, event):
        if event.type == "INTERRUPTION":
            choices = ("I'll pause and use your update.", "I'll reconsider the request.",
                       "Let me adjust to that change.", "I'm checking your latest instruction.")
        elif event.type in {"TEXT_CHUNK", "AUDIO_CLIP"} and event.payload.get("end_of_turn", True):
            if self.count >= 4:
                return None
            choices = ("I'm checking your request.", "Let me consider that update.",
                       "I'll work from what you just said.", "I'm reviewing the next step.")
        else:
            return None  # Partial turns and passive frames do not take the floor.
        text = next((text for text in choices if text not in self.used), None)
        if text is not None:
            self.used.add(text)
            self.count += 1
        return text
