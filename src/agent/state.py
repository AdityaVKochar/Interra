from .models import Patch, State


class StateManager:
    def __init__(self, session_id):
        self._state = State(session_id=session_id)

    @property
    def snapshot(self):
        return self._state.model_copy(deep=True)

    def preview(self, patch: Patch):
        old = self._state
        switched = patch.intent is not None and patch.intent != old.intent
        slots = {} if switched else dict(old.slots)
        for key in patch.remove_slots:
            slots.pop(key, None)
        slots.update(patch.set_slots)
        changed = {key for key in old.slots.keys() | slots.keys()
                   if (key in old.slots) != (key in slots) or old.slots.get(key) != slots.get(key)}
        new = State(session_id=old.session_id, version=old.version + bool(changed or switched),
                    intent=patch.intent if patch.intent is not None else old.intent, slots=slots,
                    pending_clarification=None if switched else old.pending_clarification)
        return new, changed, switched

    def apply(self, patch: Patch):
        result = self.preview(patch)
        self._state = result[0].model_copy(deep=True)
        return result

    def clarify(self, question):
        if question != self._state.pending_clarification:
            self._state = self._state.model_copy(update={
                "pending_clarification": question, "version": self._state.version + 1})
