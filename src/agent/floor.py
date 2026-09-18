"""Truthful acknowledgments with no dependency on the reasoning provider."""


class FloorManager:
    def __init__(self):
        self.text_active = False

    def acknowledge(self, event):
        if event.type == "TEXT_CHUNK":
            first = not self.text_active
            self.text_active = not event.payload["end_of_turn"]
            if first:
                return "I’m checking your request."
        elif event.type == "INTERRUPTION":
            self.text_active = False
            return "I’ve paused the current work. What would you like to change?"
        elif event.type == "AUDIO_CLIP":
            return "I’m listening to the audio update."
        elif event.type == "VIDEO_FRAME":
            return "I’m checking what’s visible in the frame."
        return None
